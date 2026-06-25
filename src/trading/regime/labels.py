"""The regime label set — a small product space (vol tercile × trend) + UNKNOWN (Inc-7 PART B).

The regime is §4.3 DERIVED: ADVISORY posture for the allocator, NEVER a gate/sizing/cap input. The
label space is deliberately TINY (ADR §5 anti-overfit) — three volatility terciles × two trend signs
plus an ``UNKNOWN`` warmup state. ``RegimeLabel`` is a ``StrEnum`` so a label round-trips losslessly
through a sanitized ``regime.json`` and compares value-equal in a pandas object Series.
"""

from __future__ import annotations

from enum import StrEnum


class RegimeLabel(StrEnum):
    """A deterministic market-regime label (advisory, DERIVED). ``UNKNOWN`` = warmup / not-known."""

    LOW_VOL_UP = "low_vol_up"
    LOW_VOL_DOWN = "low_vol_down"
    MID_VOL_UP = "mid_vol_up"
    MID_VOL_DOWN = "mid_vol_down"
    HIGH_VOL_UP = "high_vol_up"
    HIGH_VOL_DOWN = "high_vol_down"
    UNKNOWN = "unknown"


#: The six "confident" product labels (UNKNOWN is the warmup state, deliberately excluded).
PRODUCT_LABELS: tuple[RegimeLabel, ...] = (
    RegimeLabel.LOW_VOL_UP,
    RegimeLabel.LOW_VOL_DOWN,
    RegimeLabel.MID_VOL_UP,
    RegimeLabel.MID_VOL_DOWN,
    RegimeLabel.HIGH_VOL_UP,
    RegimeLabel.HIGH_VOL_DOWN,
)
