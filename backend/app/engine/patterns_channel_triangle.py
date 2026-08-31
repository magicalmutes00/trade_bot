"""Channel and triangle pattern detectors (TRADEBOT spec §§11-15).

Pure functions: take a SwingStructure + candle series + config and return
PatternHit objects with geometry, trade plan, and invalidation rules.

Patterns implemented:
  - ASCENDING_CHANNEL   (§11) — two parallel ascending trendlines
  - DESCENDING_CHANNEL  (§12) — mirror of ascending channel
  - ASCENDING_TRIANGLE  (§13) — flat top, rising lows → bearish breakout
  - DESCENDING_TRIANGLE (§14) — flat bottom, falling highs → bullish breakout
  - SYMMETRICAL_TRIANGLE (§15) — converging lines, direction from breakout

Approach: fit linear trendlines through swing points via two-point regression,
count touches within a tolerance band, detect breakouts via consecutive closes
using `_find_close_break`.  No textbook rules beyond what the spec states.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.engine.config import DEFAULT_PATTERN_CONFIG, PatternConfig
from app.engine.models import EngineCandle
from app.engine.patterns import _any_close_above, _any_close_below, _confidence, _find_close_break
from app.engine.types import PatternDirection, PatternHit, PatternStatus
from app.engine.swings import Swing, SwingStructure


# ── internal helpers ──────────────────────────────────────────────────────────


def _line_params(
    p1_idx: int, p1_price: float, p2_idx: int, p2_price: float
) -> tuple[float, float] | None:
    """Two-point line y = slope*x + intercept.  None if indices coincide."""
    if p2_idx == p1_idx:
        return None
    slope = (p2_price - p1_price) / (p2_idx - p1_idx)
    intercept = p1_price - slope * p1_idx
    return slope, intercept


def _line_value(params: tuple[float, float], idx: int) -> float:
    """Evaluate y = slope*x + intercept at a given index."""
    slope, intercept = params
    return slope * idx + intercept


def _count_touches(
    points: list[tuple[int, float]],
    params: tuple[float, float],
    tolerance: float,
) -> int:
    """Count how many (index, price) points lie on or near the line."""
    return sum(
        1 for idx, price in points
        if abs(price - _line_value(params, idx)) <= tolerance
    )


def _find_trendline(
    points: list[tuple[int, float]],
    tolerance: float,
) -> tuple[tuple[float, float], int] | None:
    """Fit a two-point line through the first and last qualifying points.

    Returns (line_params, num_touches) if at least 2 points touch the line
    within the tolerance band, else None.
    """
    if len(points) < 2:
        return None
    p1_idx, p1_price = points[0]
    p2_idx, p2_price = points[-1]
    params = _line_params(p1_idx, p1_price, p2_idx, p2_price)
    if params is None:
        return None
    touches = _count_touches(points, params, tolerance)
    return params, touches


def _flat_line_params(
    points: list[tuple[int, float]], tolerance: float
) -> tuple[tuple[float, float], int] | None:
    """Fit a two-point line and verify the slope is near-zero (a flat level).

    Returns (line_params, touches) or None if the fitted line trends too
    steeply (|slope| > 1.0) or has fewer than 2 touches.  Used for the flat
    top of an ascending triangle / flat bottom of a descending triangle.
    """
    line = _find_trendline(points, tolerance)
    if line is None:
        return None
    params, touches = line
    slope = params[0]
    if abs(slope) > 1.0:
        return None
    return params, touches


def _swing_prices(swings: Sequence[Swing]) -> list[tuple[int, float]]:
    """Extract (index, price) pairs from swing points (chronological)."""
    return [(s.index, s.price) for s in swings]


# ── detectors ─────────────────────────────────────────────────────────────────


def detect_ascending_channel(
    structure: SwingStructure,
    candles: Sequence[EngineCandle],
    cfg: PatternConfig = DEFAULT_PATTERN_CONFIG,
) -> list[PatternHit]:
    """Ascending channel (spec §11): two parallel ascending trendlines.

    Requirements:
      - upper (through swing highs) and lower (through swing lows) lines both
        have positive slope
      - slopes are roughly parallel (divergence ≤ cfg.triangle_max_slope_divergence)
      - ≥2 touches on each line and ≥4 total
    STATUS: FORMING until a breakout; FULLY_FORMED on two closes below the
    lower line; INVALIDATED on two closes above the upper line.
    ENTRY at the lower line, target = HH projection (channel height above).
    """
    highs = _swing_prices(structure.highs)
    lows = _swing_prices(structure.lows)
    tol = cfg.triangle_max_slope_divergence

    upper = _find_trendline(highs, tol)
    lower = _find_trendline(lows, tol)
    if upper is None or lower is None:
        return []

    u_params, u_touches = upper
    l_params, l_touches = lower
    u_slope = u_params[0]
    l_slope = l_params[0]

    # §11: both trendlines ascending (positive slope)
    if u_slope <= 0 or l_slope <= 0:
        return []
    if u_touches < 2 or l_touches < 2 or (u_touches + l_touches) < 4:
        return []

    # Roughly parallel: slope divergence ≤ cfg threshold
    avg_slope = (u_slope + l_slope) / 2
    slope_div = abs(u_slope - l_slope) / avg_slope if avg_slope > 0 else 0.0
    if slope_div > cfg.triangle_max_slope_divergence:
        return []

    # Chronological ordering: the upper touches must lead the lower touches
    last_upper = highs[-1][0]
    last_lower = lows[-1][0]
    if last_upper >= last_lower:
        return []

    # Neckline = upper trendline price at the last upper touch
    neckline = _line_value(u_params, last_upper)

    # Breakout (confirmed): two consecutive closes below the lower line
    start_search = max(last_upper, last_lower) + 1
    confirm_idx = _find_close_break(
        candles, start=start_search, level=_line_value(l_params, start_search),
        direction="below", consecutive=cfg.channel_confirm_bars,
    )

    # Invalidation: two consecutive closes above the upper line
    upper_broken = _any_close_above(
        candles, start=start_search, level=_line_value(u_params, start_search)
    )

    if confirm_idx is not None:
        status = PatternStatus.FULLY_FORMED
    elif upper_broken:
        status = PatternStatus.INVALIDATED
    else:
        status = PatternStatus.FORMING

    # Trade plan (spec §11): buy at lower line, target = HH (channel height above)
    lower_at_last = _line_value(l_params, last_lower)
    channel_height = neckline - lower_at_last
    target = lower_at_last + channel_height

    conf = _confidence(
        slippage_ratio=slope_div,
        depth_ratio=(channel_height / neckline) / 0.05 if neckline else 1.0,
        status=status,
    )

    return [PatternHit(
        name="ASCENDING_CHANNEL",
        direction=PatternDirection.BULLISH,
        status=status,
        confirm_index=confirm_idx,
        neckline_price=neckline,
        entry=lower_at_last,
        stop_loss=lows[-1][1],  # previous (lowest) swing low
        targets=[target],
        invalidation=(
            "Two consecutive candles close beyond the upper channel (spec §11)"
        ),
        peak_price=neckline,
        swing_indices=(highs[0][0], lows[0][0], highs[-1][0]),
        confidence=conf,
        notes=(
            f"upper_slope={u_slope:.4f}, lower_slope={l_slope:.4f}, "
            f"upper_touches={u_touches}, lower_touches={l_touches}, "
            f"channel_height={channel_height:.2f}"
        ),
    )]


def detect_descending_channel(
    structure: SwingStructure,
    candles: Sequence[EngineCandle],
    cfg: PatternConfig = DEFAULT_PATTERN_CONFIG,
) -> list[PatternHit]:
    """Descending channel (spec §12): mirror of ascending channel.

    Both trendlines descending; sell at the upper line, target = LL (channel
    height projected below).  Same status / breakout / invalidation logic.
    """
    highs = _swing_prices(structure.highs)
    lows = _swing_prices(structure.lows)
    tol = cfg.triangle_max_slope_divergence

    upper = _find_trendline(highs, tol)
    lower = _find_trendline(lows, tol)
    if upper is None or lower is None:
        return []

    u_params, u_touches = upper
    l_params, l_touches = lower
    u_slope = u_params[0]
    l_slope = l_params[0]

    # §12: both trendlines descending (negative slope)
    if u_slope >= 0 or l_slope >= 0:
        return []
    if u_touches < 2 or l_touches < 2 or (u_touches + l_touches) < 4:
        return []

    avg_slope = (abs(u_slope) + abs(l_slope)) / 2
    slope_div = abs(u_slope - l_slope) / avg_slope if avg_slope > 0 else 0.0
    if slope_div > cfg.triangle_max_slope_divergence:
        return []

    last_upper = highs[-1][0]
    last_lower = lows[-1][0]
    if last_upper >= last_lower:
        return []

    neckline = _line_value(u_params, last_upper)

    start_search = max(last_upper, last_lower) + 1
    confirm_idx = _find_close_break(
        candles, start=start_search, level=_line_value(l_params, start_search),
        direction="below", consecutive=cfg.channel_confirm_bars,
    )
    upper_broken = _any_close_above(
        candles, start=start_search, level=_line_value(u_params, start_search)
    )

    if confirm_idx is not None:
        status = PatternStatus.FULLY_FORMED
    elif upper_broken:
        status = PatternStatus.INVALIDATED
    else:
        status = PatternStatus.FORMING

    # Trade plan (spec §12): sell at upper line, target = LL
    lower_at_last = _line_value(l_params, last_lower)
    channel_height = neckline - lower_at_last
    target = lower_at_last  # LL projection below the lower line

    conf = _confidence(
        slippage_ratio=slope_div,
        depth_ratio=(channel_height / neckline) / 0.05 if neckline else 1.0,
        status=status,
    )

    return [PatternHit(
        name="DESCENDING_CHANNEL",
        direction=PatternDirection.BEARISH,
        status=status,
        confirm_index=confirm_idx,
        neckline_price=neckline,
        entry=neckline,
        stop_loss=highs[-1][1],  # previous (highest) swing high
        targets=[target],
        invalidation=(
            "Two consecutive candles close beyond the upper channel (spec §12)"
        ),
        peak_price=neckline,
        swing_indices=(highs[0][0], lows[0][0], highs[-1][0]),
        confidence=conf,
        notes=(
            f"upper_slope={u_slope:.4f}, lower_slope={l_slope:.4f}, "
            f"upper_touches={u_touches}, lower_touches={l_touches}, "
            f"channel_height={channel_height:.2f}"
        ),
    )]


def detect_ascending_triangle(
    structure: SwingStructure,
    candles: Sequence[EngineCandle],
    cfg: PatternConfig = DEFAULT_PATTERN_CONFIG,
) -> list[PatternHit]:
    """Ascending triangle — SELL (spec §13).

    Flat top (swing highs at roughly equal prices) + ascending trendline
    (rising swing lows).  Minimum 3 touches on the ascending (sloped) line.

    Entry: close below the flat-top resistance → BEARISH.
    Stop Loss: previous high (the highest swing high).
    Target: 1:1 measured move — triangle height below the breakout.
    """
    highs = _swing_prices(structure.highs)
    lows = _swing_prices(structure.lows)
    tol = cfg.triangle_max_slope_divergence

    # ── flat top from swing highs ──
    flat = _flat_line_params(highs, tol)
    if flat is None:
        return []
    flat_params, flat_touches = flat
    if flat_touches < 2:
        return []

    # ── ascending (sloped) line from swing lows ──
    sloped = _find_trendline(lows, tol)
    if sloped is None:
        return []
    sloped_params, sloped_touches = sloped
    sloped_slope = sloped_params[0]

    # §13: ascending line must slope up, with ≥ cfg.triangle_min_touches touches
    if sloped_slope <= 0:
        return []
    if sloped_touches < cfg.triangle_min_touches:
        return []

    # ── breakout / invalidation ──
    flat_price = _line_value(flat_params, highs[-1][0])
    start_search = lows[-1][0] + 1

    # §13: breakouts on closes below the flat top (2 consecutive closes)
    confirm_idx = _find_close_break(
        candles, start=start_search, level=flat_price,
        direction="below", consecutive=cfg.channel_confirm_bars,
    )
    # Invalidation: a close above the flat top (resistance broken)
    any_above = _any_close_above(candles, start=start_search, level=flat_price)

    if confirm_idx is not None:
        status = PatternStatus.FULLY_FORMED
    elif any_above:
        status = PatternStatus.INVALIDATED
    else:
        status = PatternStatus.FORMING

    # ── trade plan (spec §13) ──
    # Height at the wide (left) end: flat price − sloped line at the first low
    height = flat_price - _line_value(sloped_params, lows[0][0])
    entry = flat_price
    stop_loss = max(sw.price for sw in structure.highs)  # previous high
    target = entry - height  # 1:1 measured move below the breakout

    conf = _confidence(
        slippage_ratio=0.0,  # flat top → no slippage between equal highs
        depth_ratio=(height / flat_price) / 0.05 if flat_price else 1.0,
        status=status,
    )

    return [PatternHit(
        name="ASCENDING_TRIANGLE",
        direction=PatternDirection.BEARISH,
        status=status,
        confirm_index=confirm_idx,
        neckline_price=flat_price,
        entry=entry,
        stop_loss=stop_loss,
        targets=[target],
        invalidation=(
            f"Two consecutive candles close beyond the flat top "
            f"{flat_price:.2f} (spec §13)"
        ),
        peak_price=flat_price,
        swing_indices=(highs[0][0], lows[0][0], highs[-1][0]),
        confidence=conf,
        notes=(
            f"flat_touches={flat_touches}, sloped_touches={sloped_touches}, "
            f"sloped_slope={sloped_slope:.4f}, height={height:.2f}"
        ),
    )]


def detect_descending_triangle(
    structure: SwingStructure,
    candles: Sequence[EngineCandle],
    cfg: PatternConfig = DEFAULT_PATTERN_CONFIG,
) -> list[PatternHit]:
    """Descending triangle — BUY (spec §14).

    Flat bottom (swing lows at roughly equal prices) + descending trendline
    (falling swing highs).  Minimum 3 touches on the descending (sloped) line.

    Entry: close above the flat-bottom support → BULLISH.
    Stop Loss: previous low (the lowest swing low).
    Target: 1:1 measured move — triangle height above the breakout.
    """
    highs = _swing_prices(structure.highs)
    lows = _swing_prices(structure.lows)
    tol = cfg.triangle_max_slope_divergence

    # ── flat bottom from swing lows ──
    flat = _flat_line_params(lows, tol)
    if flat is None:
        return []
    flat_params, flat_touches = flat
    if flat_touches < 2:
        return []

    # ── descending (sloped) line from swing highs ──
    sloped = _find_trendline(highs, tol)
    if sloped is None:
        return []
    sloped_params, sloped_touches = sloped
    sloped_slope = sloped_params[0]

    # §14: descending line must slope down, with ≥ cfg.triangle_min_touches
    if sloped_slope >= 0:
        return []
    if sloped_touches < cfg.triangle_min_touches:
        return []

    # ── breakout / invalidation ──
    flat_price = _line_value(flat_params, lows[-1][0])
    start_search = highs[-1][0] + 1

    # §14: breakouts on closes above the flat bottom (2 consecutive closes)
    confirm_idx = _find_close_break(
        candles, start=start_search, level=flat_price,
        direction="above", consecutive=cfg.channel_confirm_bars,
    )
    # Invalidation: a close below the flat bottom (support broken)
    any_below = _any_close_below(candles, start=start_search, level=flat_price)

    if confirm_idx is not None:
        status = PatternStatus.FULLY_FORMED
    elif any_below:
        status = PatternStatus.INVALIDATED
    else:
        status = PatternStatus.FORMING

    # ── trade plan (spec §14) ──
    # Height at the wide (left) end: sloped line at first high − flat price
    height = _line_value(sloped_params, highs[0][0]) - flat_price
    entry = flat_price
    stop_loss = min(sw.price for sw in structure.lows)  # previous low
    target = entry + height  # 1:1 measured move above the breakout

    conf = _confidence(
        slippage_ratio=0.0,  # flat bottom → no slippage between equal lows
        depth_ratio=(height / flat_price) / 0.05 if flat_price else 1.0,
        status=status,
    )

    return [PatternHit(
        name="DESCENDING_TRIANGLE",
        direction=PatternDirection.BULLISH,
        status=status,
        confirm_index=confirm_idx,
        neckline_price=flat_price,
        entry=entry,
        stop_loss=stop_loss,
        targets=[target],
        invalidation=(
            f"Two consecutive candles close beyond the flat bottom "
            f"{flat_price:.2f} (spec §14)"
        ),
        peak_price=flat_price,
        swing_indices=(highs[0][0], lows[0][0], highs[-1][0]),
        confidence=conf,
        notes=(
            f"flat_touches={flat_touches}, sloped_touches={sloped_touches}, "
            f"sloped_slope={sloped_slope:.4f}, height={height:.2f}"
        ),
    )]


def detect_symmetrical_triangle(
    structure: SwingStructure,
    candles: Sequence[EngineCandle],
    cfg: PatternConfig = DEFAULT_PATTERN_CONFIG,
) -> list[PatternHit]:
    """Symmetrical triangle (spec §15).

    Minimum 3 touches total; converging trendlines (upper slopes down, lower
    slopes up).  Direction is determined BY THE BREAKOUT, never forced before
    it.  Stop Loss = appropriate previous swing per breakout side.
    Target = 1:1 measured move (triangle height at the wide end).
    """
    highs = _swing_prices(structure.highs)
    lows = _swing_prices(structure.lows)
    tol = cfg.triangle_max_slope_divergence

    upper = _find_trendline(highs, tol)
    lower = _find_trendline(lows, tol)
    if upper is None or lower is None:
        return []

    u_params, u_touches = upper
    l_params, l_touches = lower
    u_slope = u_params[0]
    l_slope = l_params[0]

    # §15: minimum 3 touches total
    if (u_touches + l_touches) < cfg.triangle_min_touches:
        return []

    # Converging lines: upper down, lower up, and not both flat.
    if u_slope >= 0 or l_slope <= 0:
        return []
    if abs(u_slope) < 1e-9 and abs(l_slope) < 1e-9:
        return []

    # Neckline / apex reference at the wide (left) end
    left_upper = _line_value(u_params, highs[0][0])
    left_lower = _line_value(l_params, lows[0][0])
    neckline = (left_upper + left_lower) / 2

    # ── breakout / invalidation ──
    start_search = max(highs[-1][0], lows[-1][0]) + 1
    upper_at = _line_value(u_params, start_search)
    lower_at = _line_value(l_params, start_search)

    bull_break = _find_close_break(
        candles, start=start_search, level=upper_at,
        direction="above", consecutive=cfg.channel_confirm_bars,
    )
    bear_break = _find_close_break(
        candles, start=start_search, level=lower_at,
        direction="below", consecutive=cfg.channel_confirm_bars,
    )

    # Invalidation signals (a lone close beyond a line without confirmation)
    any_below = _any_close_below(candles, start=start_search, level=lower_at)
    any_above = _any_close_above(candles, start=start_search, level=upper_at)

    if bull_break is not None:
        confirm_idx, direction, stop_loss, invalidation = (
            bull_break, PatternDirection.BULLISH, lows[-1][1],
            "Two consecutive candles close below the lower trendline (spec §15)",
        )
    elif bear_break is not None:
        confirm_idx, direction, stop_loss, invalidation = (
            bear_break, PatternDirection.BEARISH, highs[-1][1],
            "Two consecutive candles close above the upper trendline (spec §15)",
        )
    elif any_below or any_above:
        confirm_idx, direction, stop_loss = None, PatternDirection.NEUTRAL, None
        invalidation = (
            "Price closed beyond a trendline without a confirmed breakout "
            "(spec §15)"
        )
    else:
        confirm_idx, direction, stop_loss = None, PatternDirection.NEUTRAL, None
        invalidation = ""

    if confirm_idx is not None:
        status = PatternStatus.FULLY_FORMED
    elif any_below or any_above:
        status = PatternStatus.INVALIDATED
    else:
        status = PatternStatus.FORMING

    # ── trade plan (spec §15) ──
    height = left_upper - left_lower  # triangle height at the wide end
    entry = neckline
    if direction is PatternDirection.BULLISH:
        target = neckline + height
    elif direction is PatternDirection.BEARISH:
        target = neckline - height
    else:
        target = neckline  # no direction determined yet

    touch_quality = 1.0 - min(u_touches + l_touches, 6) / 6.0
    conf = _confidence(
        slippage_ratio=touch_quality,
        depth_ratio=(height / neckline) / 0.05 if neckline else 1.0,
        status=status,
    )

    return [PatternHit(
        name="SYMMETRICAL_TRIANGLE",
        direction=direction,
        status=status,
        confirm_index=confirm_idx,
        neckline_price=neckline,
        entry=entry,
        stop_loss=stop_loss,
        targets=[target],
        invalidation=invalidation,
        peak_price=neckline,
        swing_indices=(highs[0][0], lows[0][0], highs[-1][0]),
        confidence=conf,
        notes=(
            f"upper_slope={u_slope:.4f}, lower_slope={l_slope:.4f}, "
            f"upper_touches={u_touches}, lower_touches={l_touches}, "
            f"height={height:.2f}"
        ),
    )]
