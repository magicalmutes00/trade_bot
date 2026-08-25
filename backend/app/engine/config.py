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
