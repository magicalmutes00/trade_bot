"""BOF engine configuration — every threshold lives here (docs/bof-engine.md)."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BOFConfig:
    # --- market structure ---
    pivot_left: int = 3
    pivot_right: int = 3

    # --- breakout detection ---
    min_break_pct: float = 0.0005      # close ≥ level * (1 + 0.05%)
    volume_sma: int = 20
    volume_mult_min: float = 0.0       # optional filter; 0 disables

    # --- failure / invalidation ---
    failure_window: int = 3            # bars after breakout to print a failure
    rebreak_pct: float = 0.0015        # further close beyond level → invalidated
    max_open_candidates: int = 8       # per side; oldest candidates dropped first

    # --- strength scoring weights (sum = 1.0) ---
    w_speed: float = 0.30              # faster failure = stronger trap
    w_depth: float = 0.20              # deeper false break = more trapped traders
    w_volume: float = 0.20             # breakout vs average volume
    w_wick: float = 0.15               # rejection wick on the failure bar
    w_trend: float = 0.15              # alignment with same-TF trend context
    depth_cap_pct: float = 0.015       # penetration normalised against this cap
    vol_expansion_cap: float = 2.0     # vol/sma20 capped here → [0,1] scale

    # --- strength mapping ---
    weak_below: float = 40.0
    moderate_below: float = 60.0
    strong_below: float = 80.0         # ≥ this → VERY_STRONG

    def validate(self) -> None:
        total = self.w_speed + self.w_depth + self.w_volume + self.w_wick + self.w_trend
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"strength weights must sum to 1.0 (got {total})")


DEFAULT_CONFIG = BOFConfig()


@dataclass(frozen=True)
class PatternConfig:
    # --- double top / bottom (TRADEBOT §8, §9 — Traditional) ---
    double_slippage: float = 0.0032        # ≤ 0.32% between the two peaks / bottoms
    double_max_days: float = 274.0         # < 9 months between the two tops / bottoms
    double_min_bars_between: int = 3       # structural: valley must sit between the two
    double_confirm_bars: int = 1           # one candle CLOSE beyond the neckline suffices

    # --- head & shoulders (§5, §6) ---
    hs_shoulder_tolerance: float = 0.03    # head vs shoulder tolerance
    hs_min_bars_between: int = 10
    hs_confirm_bars: int = 1               # one close beyond neckline suffices

    # --- triangles / channels (§11-15, §16-17) ---
    triangle_min_touches: int = 3          # minimum touches on the sloped line
    triangle_max_slope_divergence: float = 0.25   # max 25% divergence between two lines
    triangle_min_bars: int = 15
    channel_confirm_bars: int = 2          # two consecutive closes beyond the line

    # --- harmonics (§26-28) ---
    harmonic_tolerance: float = 0.05       # ±5% ratio tolerance band
    harmonic_targets: tuple[float, ...] = (0.618, 1.0, 1.414)  # fib reversal of BC

    # --- fib (§29) ---
    fib_last_swing_bars: int = 30          # look back for major swing

    def validate(self) -> None:
        pass


DEFAULT_PATTERN_CONFIG = PatternConfig()
