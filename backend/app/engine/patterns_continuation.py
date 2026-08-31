"""Continuation pattern detectors built on swing structure (TRADEBOT §16–§25).

Pure functions: take a ``SwingStructure`` (alternating swings + HH/HL/LH/LL
labels) plus the candle series and return pattern hits with a full trade plan
(entry / SL / targets) and an explicit invalidation condition.

This module implements TRADEBOT's strict rules only. Do NOT apply textbook
pattern definitions that are not specified in the engine spec. A Kotlin port
mirrors this file EXACTLY, so keep the logic simple, deterministic and
well-commented (no randomness, no float-order dependence beyond these trivial
helpers, no I/O).

Status vocabulary (spec §4): FORMING → FULLY_FORMED → INVALIDATED.

Continuation patterns covered here:
  §16 BULLISH_FLAG,  §17 BEARISH_FLAG     (channel consolidation after a pole)
  §18 BULLISH_PENNANT, §19 BEARISH_PENNANT (H→L→LH→HL / L→H→HL→LH setup)
  §20 RISING_WEDGE,  §21 FALLING_WEDGE    (compressing trendlines + breakout)
  §22 WOLFE_WAVE                          (false breakout + real breakout)
  §23 ELLIOTT_WAVE                        (0-1-2-3-4-5 impulse, wave 3 longest)
  §24 DRIVE_PATTERN                       (XABCD with strict fib relationships)
  §25 DIAMOND_PATTERN                     (expanding-then-contracting breakout)
"""

from collections.abc import Sequence

from app.engine.config import DEFAULT_PATTERN_CONFIG, PatternConfig
from app.engine.models import EngineCandle
from app.engine.patterns import (
    PatternStatus,
    PatternDirection,
    PatternHit,
    _pct_diff,
    _span_days,
    _find_close_break,
    _between,
    _any_close_above,
    _any_close_below,
)
from app.engine.swings import Swing, SwingStructure, Trend


# ── local helpers ──────────────────────────────────────────────────────────

def _confidence(status: PatternStatus, quality: float = 1.0) -> float:
    """Rule-satisfaction score in [0,1].

    FORMING hits cap at 0.5 (structure is there, confirmation is pending);
    any other terminal state is scored straight from geometry. ``quality`` is
    an optional 0..1 geometry signal already normalized by the caller.
    """
    geo = max(0.0, min(1.0, quality))
    if status is PatternStatus.FORMING:
        geo *= 0.5
    return round(max(0.0, min(1.0, geo)), 3)


class _Line:
    """Best-fit line over an ordered set of swing points (price vs candle index).

    Built from a 2-point line when only two points exist (deterministic,
    simple, mirrors what the Kotlin port can reproduce exactly); for 3+ points
    a least-squares fit is used so every touch contributes. The engine only
    ever compares relative line slopes to test convergence and side-of-line
    positioning, so the exact fitting choice is not load-bearing.
    """

    __slots__ = ("a", "b")

    def __init__(self, pts: Sequence[Swing]) -> None:
        xs = [p.index for p in pts]
        ys = [p.price for p in pts]
        if len(pts) == 2:
            dx = xs[1] - xs[0]
            a = (ys[1] - ys[0]) / dx if dx else 0.0
            b = ys[0] - a * xs[0]
            self.a, self.b = a, b
            return
        n = len(pts)
        mx = sum(xs) / n
        my = sum(ys) / n
        sxx = sum((x - mx) ** 2 for x in xs)
        sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        a = sxy / sxx if sxx else 0.0
        self.a, self.b = a, my - a * mx

    def at(self, x: int) -> float:
        return self.a * x + self.b


def _ratio(a: float, b: float, c: float) -> float:
    """Retracement/extension ratio (b - a) / (c - a).

    Leg from ``a`` to ``b`` expressed as a fraction of the anchor leg from
    ``a`` to ``c``. Used for harmonic (drive) checks where the swing sequence
    is price-ordered so the sign of the leg is already known.
    """
    denom = c - a
    return (b - a) / denom if denom else 0.0


def _line_intersection_x(l1: _Line, l2: _Line) -> float | None:
    """Candle-index x where two lines intersect, or None if (near-)parallel."""
    da = l1.a - l2.a
    if abs(da) < 1e-12:
        return None
    return (l2.b - l1.b) / da


def _bullish_before(structure: SwingStructure, idx: int) -> bool:
    """True when the structure strictly before candle `idx` is an Uptrend
    (two higher highs AND two higher lows), ignoring the counter-trend
    consolidation itself (spec §16/§17 flags must form in a pre-existing
    trend)."""
    ph = [s.price for s in structure.highs if s.index < idx]
    pl = [s.price for s in structure.lows if s.index < idx]
    return len(ph) >= 2 and len(pl) >= 2 and ph[-1] > ph[-2] and pl[-1] > pl[-2]


def _bearish_before(structure: SwingStructure, idx: int) -> bool:
    """Mirror of ``_bullish_before``: two lower highs AND two lower lows."""
    ph = [s.price for s in structure.highs if s.index < idx]
    pl = [s.price for s in structure.lows if s.index < idx]
    return len(ph) >= 2 and len(pl) >= 2 and ph[-1] < ph[-2] and pl[-1] < pl[-2]


# ── §16 / §17 Flags ────────────────────────────────────────────────────────

def detect_bull_flag(
    structure: SwingStructure,
    candles: Sequence[EngineCandle],
    cfg: PatternConfig = DEFAULT_PATTERN_CONFIG,
) -> list[PatternHit]:
    """BULLISH_FLAG (§16).

    Must form in an Uptrend. After a strong pole the price forms a small
    descending channel (counter-trend: lower highs + lower lows) before
    resuming up. Entry = channel-top breakout (a candle CLOSES above the upper
    bound); target = pole length (the height of the impulse preceding the
    flag); stop = the consolidation low.
    """
    highs, lows = structure.highs, structure.lows
    if len(highs) < 2 or len(lows) < 2:
        return []

    hits: list[PatternHit] = []
    for i in range(len(highs) - 1):
        h1, h2 = highs[i], highs[i + 1]          # first two swing highs of the flag
        if not _bullish_before(structure, h1.index):
            continue  # spec §16: requires a pre-existing Uptrend

        l1 = _between(lows, h1.index, h2.index)  # first consolidation low
        if l1 is None:
            continue
        after = [l for l in lows if l.index > h2.index]
        if not after:
            continue
        l2 = after[0]                            # second consolidation low
        if not (h2.price < h1.price and l2.price < l1.price):
            continue  # descending channel: lower high AND lower low

        # Channel bounds: highest consolidation high on top, lowest low below.
        flag_high = max(h1.price, h2.price)
        flag_low = min(l1.price, l2.price)

        # Pole = the prior impulse that preceded the flag (strongest low of the
        # run before the flag's first high).
        pole_low = None
        for sw in lows:
            if sw.index >= h1.index:
                break
            pole_low = sw if pole_low is None or sw.price < pole_low.price else pole_low
        start_price = flag_low if pole_low is None else pole_low.price
        pole_height = flag_high - start_price
        flag_width = h2.price - l2.price
        if pole_height <= 0 or flag_width >= pole_height:
            continue  # a real pole needs to be taller than its channel is wide

        entry_break = _find_close_break(
            candles, start=h2.index + 1, level=flag_high, direction="above",
            consecutive=cfg.channel_confirm_bars,
        )
        if entry_break is not None:
            status = PatternStatus.FULLY_FORMED
        elif _any_close_below(candles, start=h2.index + 1, level=flag_low):
            status = PatternStatus.INVALIDATED  # channel base broke → no flag
        else:
            status = PatternStatus.FORMING

        entry = flag_high
        target = entry + pole_height
        hits.append(PatternHit(
            name="BULLISH_FLAG",
            direction=PatternDirection.BULLISH,
            status=status,
            confirm_index=entry_break,
            neckline_price=entry,
            entry=entry,
            stop_loss=flag_low,
            targets=[round(target, 4)],
            invalidation=(
                f"A candle CLOSES below the flag consolidation low {flag_low:.2f} "
                "(spec §33: flag base broken, no continuation)"
            ),
            peak_price=flag_high,
            swing_indices=(h1.index, l1.index, h2.index),
            confidence=_confidence(status),
            notes=(
                f"descending channel {h1.index}-{h2.index}, "
                f"pole_height={pole_height:.2f}, target=flag_top+pole"
            ),
        ))
    return hits


def detect_bear_flag(
    structure: SwingStructure,
    candles: Sequence[EngineCandle],
    cfg: PatternConfig = DEFAULT_PATTERN_CONFIG,
) -> list[PatternHit]:
    """BEARISH_FLAG (§17) — mirror of §16 in a Downtrend.

    Ascending channel (counter-trend higher lows / higher highs) after a down
    pole. Entry = channel-bottom breakout (close below); target = pole length;
    stop = the consolidation high.
    """
    highs, lows = structure.highs, structure.lows
    if len(highs) < 2 or len(lows) < 2:
        return []

    hits: list[PatternHit] = []
    for i in range(len(lows) - 1):
        l1, l2 = lows[i], lows[i + 1]            # first two swing lows of the flag
        if not _bearish_before(structure, l1.index):
            continue  # spec §17: requires a pre-existing Downtrend

        h1 = _between(highs, l1.index, l2.index)  # first consolidation high
        if h1 is None:
            continue
        after = [h for h in highs if h.index > l2.index]
        if not after:
            continue
        h2 = after[0]                            # second consolidation high
        if not (l2.price > l1.price and h2.price > h1.price):
            continue  # ascending channel: higher low AND higher high

        # Channel bounds: highest consolidation high on top, lowest low below.
        flag_high = max(h1.price, h2.price)
        flag_low = min(l1.price, l2.price)

        # Pole = the prior impulse that preceded the flag (strongest high of the
        # run before the flag's first low).
        pole_high = None
        for sw in highs:
            if sw.index >= l1.index:
                break
            pole_high = sw if pole_high is None or sw.price > pole_high.price else pole_high
        start_price = flag_high if pole_high is None else pole_high.price
        pole_height = start_price - flag_low
        flag_width = l2.price - h2.price
        if pole_height <= 0 or flag_width >= pole_height:
            continue  # a real pole needs to be taller than its channel is wide

        entry_break = _find_close_break(
            candles, start=l2.index + 1, level=flag_low, direction="below",
            consecutive=cfg.channel_confirm_bars,
        )
        if entry_break is not None:
            status = PatternStatus.FULLY_FORMED
        elif _any_close_above(candles, start=l2.index + 1, level=flag_high):
            status = PatternStatus.INVALIDATED  # channel top broke → no flag
        else:
            status = PatternStatus.FORMING

        entry = flag_low
        target = entry - pole_height
        hits.append(PatternHit(
            name="BEARISH_FLAG",
            direction=PatternDirection.BEARISH,
            status=status,
            confirm_index=entry_break,
            neckline_price=entry,
            entry=entry,
            stop_loss=flag_high,
            targets=[round(target, 4)],
            invalidation=(
                f"A candle CLOSES above the flag consolidation high {flag_high:.2f} "
                "(spec §33: flag top broken, no continuation)"
            ),
            peak_price=flag_high,
            swing_indices=(l1.index, h1.index, l2.index),
            confidence=_confidence(status),
            notes=(
                f"ascending channel {l1.index}-{l2.index}, "
                f"pole_height={pole_height:.2f}, target=flag_low-pole"
            ),
        ))
    return hits


# ── §18 / §19 Pennants ─────────────────────────────────────────────────────

def _pennant_swings(
    structure: SwingStructure, direction: PatternDirection,
) -> tuple[Swing, Swing, Swing, Swing, float, float, float] | None:
    """Return (h1, l1, h2, l2, upper, lower, pole_height) for a pennant.

    The two most recent swing highs/lows are labelled h1/h2 and l1/l2 in
    chronological order. The required (spec §18/§19) point order is enforced
    via candle-index ordering *and* the relative-price constraints:

      BULLISH : H(h1) -> L(l1) -> LH(h2) -> HL(l2)   h1<l1<h2<l2, h2<h1, l2>l1
      BEARISH : L(l1) -> H(h1) -> HL(l2) -> LH(h2)   l1<h1<l2<h2, l2>l1, h2<h1

    The converging sideways range sits between the LH (upper) and the HL
    (lower); the pole is the H→L (bull) / L→H (bear) move.
    """
    bull = direction is PatternDirection.BULLISH
    highs, lows = structure.highs, structure.lows
    if len(highs) < 2 or len(lows) < 2:
        return None
    h1, h2 = highs[-2], highs[-1]
    l1, l2 = lows[-2], lows[-1]

    if bull:
        if not (l1.index > h1.index and h2.index > l1.index and l2.index > h2.index):
            return None
        if not (h2.price < h1.price and l2.price > l1.price):
            return None
    else:
        if not (h1.index > l1.index and l2.index > h1.index and h2.index > l2.index):
            return None
        if not (l2.price > l1.price and h2.price < h1.price):
            return None

    upper, lower = h2.price, l2.price   # sideways range: LH on top, HL below
    if upper <= lower:
        return None
    pole_height = h1.price - l1.price
    if pole_height <= 0:
        return None
    # A genuine pennant: the converging range is narrow relative to the pole.
    if upper - lower >= 0.6 * pole_height:
        return None
    return h1, l1, h2, l2, upper, lower, pole_height


def detect_bull_pennant(
    structure: SwingStructure,
    candles: Sequence[EngineCandle],
    cfg: PatternConfig = DEFAULT_PATTERN_CONFIG,
) -> list[PatternHit]:
    """BULLISH_PENNANT (§18).

    Required structure H → L → LH → HL → sideways (pole up, small pullback,
    lower-high, higher-low, then sideways with converging range). Entry =
    sideways top breakout (close above the upper bound); target = measured
    from H down to L (pole height); stop = sideways bottom.
    """
    setup = _pennant_swings(structure, PatternDirection.BULLISH)
    if setup is None:
        return []
    h1, l1, h2, l2, upper, lower, pole_height = setup

    confirm = _find_close_break(
        candles, start=h2.index + 1, level=upper, direction="above",
        consecutive=cfg.channel_confirm_bars,
    )
    if confirm is not None:
        status = PatternStatus.FULLY_FORMED
    elif _any_close_below(candles, start=h2.index + 1, level=lower):
        status = PatternStatus.INVALIDATED
    else:
        status = PatternStatus.FORMING

    entry = upper
    target = entry + pole_height
    return [PatternHit(
        name="BULLISH_PENNANT",
        direction=PatternDirection.BULLISH,
        status=status,
        confirm_index=confirm,
        neckline_price=entry,
        entry=entry,
        stop_loss=lower,
        targets=[round(target, 4)],
        invalidation=(
            f"A candle CLOSES below the pennant sideways low {lower:.2f} "
            "(spec §33: pennant floor broken)"
        ),
        peak_price=h1.price,
        swing_indices=(h1.index, l1.index, h2.index),
        confidence=_confidence(status),
        notes=(
            f"H→L→LH→HL structure {h1.index}/{l1.index}/{h2.index}/{l2.index}, "
            f"pole_height={pole_height:.2f}"
        ),
    )]


def detect_bear_pennant(
    structure: SwingStructure,
    candles: Sequence[EngineCandle],
    cfg: PatternConfig = DEFAULT_PATTERN_CONFIG,
) -> list[PatternHit]:
    """BEARISH_PENNANT (§19) — exact L → H → HL → LH structure."""
    setup = _pennant_swings(structure, PatternDirection.BEARISH)
    if setup is None:
        return []
    h1, l1, h2, l2, upper, lower, pole_height = setup

    confirm = _find_close_break(
        candles, start=l2.index + 1, level=lower, direction="below",
        consecutive=cfg.channel_confirm_bars,
    )
    if confirm is not None:
        status = PatternStatus.FULLY_FORMED
    elif _any_close_above(candles, start=l2.index + 1, level=upper):
        status = PatternStatus.INVALIDATED
    else:
        status = PatternStatus.FORMING

    entry = lower
    target = entry - pole_height
    return [PatternHit(
        name="BEARISH_PENNANT",
        direction=PatternDirection.BEARISH,
        status=status,
        confirm_index=confirm,
        neckline_price=entry,
        entry=entry,
        stop_loss=upper,
        targets=[round(target, 4)],
        invalidation=(
            f"A candle CLOSES above the pennant sideways high {upper:.2f} "
            "(spec §33: pennant ceiling broken)"
        ),
        peak_price=h1.price,
        swing_indices=(l1.index, h1.index, h2.index),
        confidence=_confidence(status),
        notes=(
            f"L→H→HL→LH structure {l1.index}/{h1.index}/{l2.index}/{h2.index}, "
            f"pole_height={pole_height:.2f}"
        ),
    )]


# ── §20 / §21 Wedges ───────────────────────────────────────────────────────

def _line_slope_at(pts: Sequence[Swing], idx: int) -> tuple[float, float]:
    """Return (slope, value-at-latest) of a line fit over up to ``idx`` points."""
    window = pts[max(0, idx - 1): idx + 1]
    line = _Line(window)
    return line.a, line.at(pts[idx].index)


def detect_rising_wedge(
    structure: SwingStructure,
    candles: Sequence[EngineCandle],
    cfg: PatternConfig = DEFAULT_PATTERN_CONFIG,
) -> list[PatternHit]:
    """RISING_WEDGE (§20).

    Both trendlines ascend AND compress: the upper line (over swing highs) is
    shallower than the lower line (over swing lows) so they converge. Entry
    only after a clear candlestick breakout (close beyond the LOWER ascending
    line) → typically BEARISH. Target = 1:1 measured move (the height at the
    wide base applied from the breakout point). Stop = the previous breakout
    point (last swing high).
    """
    highs, lows = structure.highs, structure.lows
    if len(highs) < 3 or len(lows) < 3:
        return []

    up_slope, up_last = _line_slope_at(highs, len(highs) - 1)
    low_slope, low_last = _line_slope_at(lows, len(lows) - 1)

    # Compress: upper slope shallower than lower slope, both ascending.
    if not (up_slope > 0 and low_slope > up_slope):
        return []

    last_idx = max(highs[-1].index, lows[-1].index)
    lower_line = _Line(lows[-3:])
    break_idx = _find_close_break(
        candles, start=last_idx + 1, level=lower_line.at(last_idx + 1),
        direction="below", consecutive=cfg.channel_confirm_bars,
    )

    base_height = max(max(h.price for h in highs[-3:])
                      - min(l.price for l in lows[-3:]), 0.0)
    if base_height <= 0:
        return []

    if break_idx is not None:
        status = PatternStatus.FULLY_FORMED
    else:
        status = PatternStatus.FORMING
        if _any_close_above(candles, start=last_idx + 1, level=up_last):
            status = PatternStatus.INVALIDATED  # broke the upper line → not a wedge top
        else:
            status = PatternStatus.FORMING

    entry = lower_line.at(last_idx + 1)
    target = entry - base_height
    return [PatternHit(
        name="RISING_WEDGE",
        direction=PatternDirection.BEARISH,
        status=status,
        confirm_index=break_idx,
        neckline_price=round(entry, 4),
        entry=round(entry, 4),
        stop_loss=highs[-1].price,
        targets=[round(target, 4)],
        invalidation=(
            f"A candle CLOSES above the wedge upper trendline {up_last:.2f} "
            "(spec §33: rising wedge fails upward)"
        ),
        peak_price=max(h.price for h in highs[-3:]),
        swing_indices=(highs[-3].index, lows[-1].index, highs[-1].index),
        confidence=_confidence(status),
        notes=(
            f"upper_slope={up_slope:.4f}, lower_slope={low_slope:.4f} "
            f"(converging={low_slope > up_slope}), base_height={base_height:.2f}"
        ),
    )]


def detect_falling_wedge(
    structure: SwingStructure,
    candles: Sequence[EngineCandle],
    cfg: PatternConfig = DEFAULT_PATTERN_CONFIG,
) -> list[PatternHit]:
    """FALLING_WEDGE (§21) — mirror of §20, both lines descending + compressing.

    Entry after a close beyond the UPPER descending line → BULLISH. Target =
    1:1 measured move; stop = previous breakout point (last swing low).
    """
    highs, lows = structure.highs, structure.lows
    if len(highs) < 3 or len(lows) < 3:
        return []

    up_slope, up_last = _line_slope_at(highs, len(highs) - 1)
    low_slope, low_last = _line_slope_at(lows, len(lows) - 1)

    # Compress: lower line steeper (more negative) than the upper line; both down.
    if not (low_slope < 0 and up_slope > low_slope):
        return []

    last_idx = max(highs[-1].index, lows[-1].index)
    upper_line = _Line(highs[-3:])
    break_idx = _find_close_break(
        candles, start=last_idx + 1, level=upper_line.at(last_idx + 1),
        direction="above", consecutive=cfg.channel_confirm_bars,
    )

    base_height = max(max(h.price for h in highs[-3:])
                      - min(l.price for l in lows[-3:]), 0.0)
    if base_height <= 0:
        return []

    if break_idx is not None:
        status = PatternStatus.FULLY_FORMED
    elif _any_close_below(candles, start=last_idx + 1, level=low_last):
        status = PatternStatus.INVALIDATED  # broke the lower line → not a wedge bottom
    else:
        status = PatternStatus.FORMING

    entry = upper_line.at(last_idx + 1)
    target = entry + base_height
    return [PatternHit(
        name="FALLING_WEDGE",
        direction=PatternDirection.BULLISH,
        status=status,
        confirm_index=break_idx,
        neckline_price=round(entry, 4),
        entry=round(entry, 4),
        stop_loss=lows[-1].price,
        targets=[round(target, 4)],
        invalidation=(
            f"A candle CLOSES below the wedge lower trendline {low_last:.2f} "
            "(spec §33: falling wedge fails downward)"
        ),
        peak_price=max(h.price for h in highs[-3:]),
        swing_indices=(lows[-3].index, highs[-1].index, lows[-1].index),
        confidence=_confidence(status),
        notes=(
            f"upper_slope={up_slope:.4f}, lower_slope={low_slope:.4f} "
            f"(converging={up_slope > low_slope}), base_height={base_height:.2f}"
        ),
    )]


# ── §22 Wolfe Wave ─────────────────────────────────────────────────────────

def detect_wolfe_wave(
    structure: SwingStructure,
    candles: Sequence[EngineCandle],
    cfg: PatternConfig = DEFAULT_PATTERN_CONFIG,
) -> list[PatternHit]:
    """WOLFE_WAVE (§22).

    Five swing points 1-2-3-4-5 with a symmetrical shape. Point 3 is a FALSE
    breakout (a high that pierces beyond the 1-4 trendline), point 5 is the
    REAL breakout (a close past point-5 confirms entry). Target = intersection
    of the two rays (line 1-4 and line 2-5). Conservative: only emitted when
    the 1-4 / 2-5 lines converge and price closes past point-5.
    """
    swings = structure.swings
    if len(swings) < 5:
        return []

    # Take the last five alternating swing points as 1-2-3-4-5.
    p1, p2, p3, p4, p5 = swings[-5:]

    # Symmetrical shape: points trend toward a common apex.
    if not (p3.price > p1.price and p3.price > p2.price):
        return []  # point 3 is not the false-altitude apex
    if not (p5.price > p4.price):
        return []  # point 5 must exceed point 4 (real breakout up)

    l14 = _Line([p1, p4])
    l25 = _Line([p2, p5])

    # The 1-4 and 2-5 rays must converge above (target region).
    apex_x = _line_intersection_x(l14, l25)
    last_idx = max(p.index for p in swings[-5:])
    if apex_x is None or apex_x <= last_idx:
        return []

    # Real breakout: a close past point-5.
    confirm = _find_close_break(
        candles, start=p5.index + 1, level=p5.price, direction="above",
        consecutive=cfg.channel_confirm_bars,
    )
    if confirm is None:
        # Not (yet) broken → FORMING, provided no invalidation.
        status = PatternStatus.FORMING
    else:
        status = PatternStatus.FULLY_FORMED

    apex_y = l14.at(apex_x)
    return [PatternHit(
        name="WOLFE_WAVE",
        direction=PatternDirection.BULLISH,
        status=status,
        confirm_index=confirm,
        neckline_price=p5.price,
        entry=p5.price,
        stop_loss=min(p3.price, p1.price),   # previous breakout region
        targets=[round(apex_y, 4)],
        invalidation=(
            f"A candle CLOSES below the point-4 swing {p4.price:.2f} "
            "(spec §33: the 1-4 ray breaks, structure invalidates)"
        ),
        peak_price=p3.price,
        swing_indices=(p1.index, p3.index, p5.index),
        confidence=_confidence(status),
        notes=(
            f"points {p1.index}/{p2.index}/{p3.index}/{p4.index}/{p5.index}, "
            f"ray_intersection @x={apex_x:.1f}"
        ),
    )]


# ── §23 Elliott Wave ───────────────────────────────────────────────────────

def detect_elliott_wave(
    structure: SwingStructure,
    candles: Sequence[EngineCandle],
    cfg: PatternConfig = DEFAULT_PATTERN_CONFIG,
) -> list[PatternHit]:
    """ELLIOTT_WAVE (§23).

    Required count 0→1→2→3→4→5. Wave 3 larger than Wave 1; wave 4 ≈ wave 2 by
    price (within ``cfg.harmonic_tolerance``). Wave 1/3/5 are impulse in the
    same direction, wave 2/4 counter-trend. Entry at wave 4 after confirmation;
    target = Wave 0→Wave 1 length. FORMING until wave 4 confirms.
    """
    swings = structure.swings
    if len(swings) < 5:
        return []
    w0, w1, w2, w3, w4 = swings[-5:]

    bull = w1.price > w0.price
    bear = w1.price < w0.price
    if not (bull or bear):
        return []

    # Impulse waves (1,3,5) same direction; corrections (2,4) opposite.
    if bull:
        if not (w3.price > w1.price > w0.price and w4.price < w3.price):
            return []
        if w2.price < w0.price or w4.price < w2.price:
            return []
    else:
        if not (w3.price < w1.price < w0.price and w4.price > w3.price):
            return []
        if w2.price > w0.price or w4.price > w2.price:
            return []

    # Wave 3 longer than wave 1 (3 is the longest impulsive leg).
    w1_len = w3_len = 0.0
    if bull:
        w1_len = w1.price - w0.price      # wave 0→1 up
        w3_len = w3.price - w2.price      # wave 2→3 up
    else:
        w1_len = w0.price - w1.price      # wave 0→1 down
        w3_len = w2.price - w3.price      # wave 2→3 down
    if w1_len <= 0 or w3_len <= w1_len:
        return []

    # Wave 4 ≈ wave 2 by price (within cfg.harmonic_tolerance).
    if bull:
        w2_len = w1.price - w2.price      # wave 1→2 down
        w4_len = w3.price - w4.price      # wave 3→4 down
    else:
        w2_len = w2.price - w1.price      # wave 1→2 up
        w4_len = w4.price - w3.price      # wave 3→4 up
    if w2_len <= 0 or w4_len <= 0:
        return []
    if abs(w4_len - w2_len) / w2_len > cfg.harmonic_tolerance:
        return []

    # Trade plan (spec §23): entry after wave 4, target = wave 0→1 length.
    target = w0.price + w1_len if bull else w0.price - w1_len
    entry = candles[-1].close if candles else (w2.price + w3.price) / 2
    stop = w4.price  # bull: below the wave-4 low; bear: above the wave-4 high

    # Wave-4 extreme is the structural invalidation line.
    inv_level = w4.price
    if bull and _any_close_below(candles, start=w4.index + 1, level=inv_level):
        status, confirm = PatternStatus.INVALIDATED, None
    elif bear and _any_close_above(candles, start=w4.index + 1, level=inv_level):
        status, confirm = PatternStatus.INVALIDATED, None
    else:
        # Wave 4 in place = the impulse count is confirmed.
        status, confirm = PatternStatus.FULLY_FORMED, w4.index

    return [PatternHit(
        name="ELLIOTT_WAVE",
        direction=PatternDirection.BULLISH if bull else PatternDirection.BEARISH,
        status=status,
        confirm_index=confirm,
        neckline_price=round(entry, 4),
        entry=round(entry, 4),
        stop_loss=round(stop, 4),
        targets=[round(target, 4)],
        invalidation=(
            f"A candle CLOSES beyond the wave-4 extreme {inv_level:.2f} in the "
            "counter-trend direction — the impulse count breaks "
            "(spec §33)"
        ),
        peak_price=w3.price,
        swing_indices=(w0.index, w1.index, w3.index),
        confidence=_confidence(status),
        notes=(
            f"count {w0.index}→{w1.index}→{w2.index}→{w3.index}→{w4.index}, "
            f"wave3>{w1} ({w3_len:.2f}>{w1_len:.2f}), "
            f"wave4≈wave2 tol={cfg.harmonic_tolerance:.2f}"
        ),
    )]


# ── §24 Drive ──────────────────────────────────────────────────────────────

def detect_drive(
    structure: SwingStructure,
    candles: Sequence[EngineCandle],
    cfg: PatternConfig = DEFAULT_PATTERN_CONFIG,
) -> list[PatternHit]:
    """DRIVE_PATTERN (§24).

    XABCD with strict (not generic) Fibonacci relationships, checked within
    ``cfg.harmonic_tolerance``:

      Buy config : AB retraces 0.618 of XA, and BC extends to 1.618.
      Sell config: AB retraces 0.382 of XA, and BC extends to 2.414.

    Target is always a 1.414 extension of the final CD leg. Entry is marked at
    point E on the LTF (the structure forms at D but E is lower-timeframe) —
    so the hit is reported FORMING (structure formed, entry pending). A generic
    ABCD that fails the fib checks is NOT a drive.
    """
    swings = structure.swings
    if len(swings) < 5:
        return []
    X, A, B, C, D = swings[-5:]

    # Leg lengths are magnitudes (a "retracement of 0.618" refers to the size
    # of the retracement leg, regardless of sign).
    xa = abs(A.price - X.price)
    ab = abs(B.price - A.price)
    bc = abs(C.price - B.price)
    if xa == 0 or ab == 0:
        return []

    # Strict (not generic) fib relationships, within cfg.harmonic_tolerance.
    rab = ab / xa
    rbc = bc / ab
    buy = abs(rab - 0.618) <= cfg.harmonic_tolerance and abs(rbc - 1.618) <= cfg.harmonic_tolerance
    sell = abs(rab - 0.382) <= cfg.harmonic_tolerance and abs(rbc - 2.414) <= cfg.harmonic_tolerance
    if not (buy or sell):
        return []

    direction = PatternDirection.BULLISH if buy else PatternDirection.BEARISH
    # Target = 1.414 extension of the CD leg, projected with the impulse.
    cd = abs(D.price - C.price)
    target = D.price + 1.414 * cd if buy else D.price - 1.414 * cd
    entry = D.price  # structural level; real fill is point E on the LTF

    # Structure is formed (the XABCD is in place) but point E lives on a
    # lower timeframe → entry is pending → FORMING.
    status = PatternStatus.FORMING
    return [PatternHit(
        name="DRIVE_PATTERN",
        direction=direction,
        status=status,
        confirm_index=None,
        neckline_price=entry,
        entry=entry,
        stop_loss=C.price if buy else D.price,
        targets=[round(target, 4)],
        invalidation=(
            "Structure fails if price retraces past point C (spec §33) — the "
            f"CD leg no longer holds {D.price:.2f}"
        ),
        peak_price=round(max(p.price for p in (A, B, C, D)), 4),
        swing_indices=(A.index, B.index, D.index),
        confidence=_confidence(status),
        notes=(
            f"XABCD {X.index}/{A.index}/{B.index}/{C.index}/{D.index}, "
            f"AB/XA={rab:.3f}, BC/AB={rbc:.3f}, "
            f"{'buy' if buy else 'sell'}-config, target=1.414*CD (point E on LTF)"
        ),
    )]


# ── §25 Diamond ────────────────────────────────────────────────────────────

def detect_diamond(
    structure: SwingStructure,
    candles: Sequence[EngineCandle],
    cfg: PatternConfig = DEFAULT_PATTERN_CONFIG,
) -> list[PatternHit]:
    """DIAMOND_PATTERN (§25).

    Triangle geometry: the swing highs rise while the swing lows fall (an
    EXPANDING phase), then the formation CONVERGES at an apex (the widening /
    narrowing trendline intersection). Entry = breakout of the intersection
    point; targets measured from the intersection; direction set by the
    breakout. Never confirmed before the breakout.
    """
    highs, lows = structure.highs, structure.lows
    if len(highs) < 3 or len(lows) < 3:
        return []

    # Use the most recent three swings of each polarity for the two lines.
    upper = _Line(highs[-3:])     # rising resistance (expanding high side)
    lower = _Line(lows[-3:])      # falling support (expanding low side)

    apex_x = _line_intersection_x(upper, lower)
    last_idx = max(highs[-1].index, lows[-1].index)
    if apex_x is None or apex_x <= last_idx:
        return []  # lines must converge AHEAD of the current bar to form an apex

    # The diamond's widest part = vertical distance between the lines' widest swing.
    span = max(max(h.price for h in highs[-3:]) - min(l.price for l in lows[-3:]), 0.0)
    if span <= 0:
        return []

    apex_y = upper.at(apex_x)

    # Breakout: a close beyond the apex level establishes the direction.
    above = _find_close_break(
        candles, start=last_idx + 1, level=apex_y, direction="above",
        consecutive=cfg.channel_confirm_bars,
    )
    below = _find_close_break(
        candles, start=last_idx + 1, level=apex_y, direction="below",
        consecutive=cfg.channel_confirm_bars,
    )

    if above is not None:
        direction = PatternDirection.BULLISH
        confirm, entry = above, apex_y
        target = apex_y + span
        stop = lows[-1].price
        status = PatternStatus.FULLY_FORMED
    elif below is not None:
        direction = PatternDirection.BEARISH
        confirm, entry = below, apex_y
        target = apex_y - span
        stop = highs[-1].price
        status = PatternStatus.FULLY_FORMED
    else:
        direction = PatternDirection.NEUTRAL
        confirm, entry, target, stop, status = None, apex_y, 0.0, None, PatternStatus.FORMING

    if direction is PatternDirection.NEUTRAL:
        return []  # not confirmed before the required breakout

    return [PatternHit(
        name="DIAMOND_PATTERN",
        direction=direction,
        status=status,
        confirm_index=confirm,
        neckline_price=round(entry, 4),
        entry=round(entry, 4),
        stop_loss=round(stop, 4) if stop is not None else None,
        targets=[round(target, 4)],
        invalidation=(
            f"A candle CLOSES through the opposite diamond side "
            f"(apex {apex_y:.2f}, spec §33: expansion fails)"
        ),
        peak_price=round(apex_y, 4),
        swing_indices=(highs[-3].index, lows[-1].index, highs[-1].index),
        confidence=_confidence(status),
        notes=(
            f"expanding-then-converging apex@x={apex_x:.1f}/y={apex_y:.2f}, "
            f"span={span:.2f}, target=apex+{direction.value}span"
        ),
    )]


# ── combined runner ────────────────────────────────────────────────────────

def detect_continuation_patterns(
    structure: SwingStructure,
    candles: Sequence[EngineCandle],
    cfg: PatternConfig = DEFAULT_PATTERN_CONFIG,
) -> list[PatternHit]:
    """Run all continuation detectors, newest-first by confirm index."""
    all_hits: list[PatternHit] = []
    all_hits.extend(detect_bull_flag(structure, candles, cfg))
    all_hits.extend(detect_bear_flag(structure, candles, cfg))
    all_hits.extend(detect_bull_pennant(structure, candles, cfg))
    all_hits.extend(detect_bear_pennant(structure, candles, cfg))
    all_hits.extend(detect_rising_wedge(structure, candles, cfg))
    all_hits.extend(detect_falling_wedge(structure, candles, cfg))
    all_hits.extend(detect_wolfe_wave(structure, candles, cfg))
    all_hits.extend(detect_elliott_wave(structure, candles, cfg))
    all_hits.extend(detect_drive(structure, candles, cfg))
    all_hits.extend(detect_diamond(structure, candles, cfg))
    all_hits.sort(key=lambda h: h.confirm_index or 0, reverse=True)
    return all_hits


__all__ = [
    "detect_bull_flag",
    "detect_bear_flag",
    "detect_bull_pennant",
    "detect_bear_pennant",
    "detect_rising_wedge",
    "detect_falling_wedge",
    "detect_wolfe_wave",
    "detect_elliott_wave",
    "detect_drive",
    "detect_diamond",
    "detect_continuation_patterns",
]
