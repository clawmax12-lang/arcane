"""Injected HARD/STRUCTURED state the Murphy guards read (Increment 6 PART B).

Frozen, finite-guarded DTOs with NO I/O — the loop populates them from broker/clock/ledger
reads, the
guards are pure functions over them. Non-finite numerics are rejected at construction (mirrors
``executor.invariants.AccountSnapshot``) so a NaN can never silently pass a comparison-based guard.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class GuardState:
    """The HARD/STRUCTURED inputs to G1–G10 (G3 is fed separately from the reconciler)."""

    now_epoch: float
    data_as_of_epoch: float  # G1: freshest bar's vintage
    last_broker_ok_epoch: float  # G4: last successful broker-API call
    last_llm_ok_epoch: float  # G5: last successful slow-loop LLM call (advisory)
    equity_now: float  # G7: latest equity sample
    equity_prev: float  # G7: previous equity sample
    equity_dt_s: float  # G7: seconds between the two equity samples
    orders_in_window: int  # G8: submitted orders in the rolling window
    order_baseline: float  # G8: rolling baseline orders/window (must be positive)
    ntp_offset_s: float | None = None  # G6: NTP offset; None ⇒ unavailable ⇒ fail closed (RED)
    pending_order_age_s: float | None = None  # G2: age of an unfilled order; None ⇒ none pending
    exposures: tuple[float, ...] = field(default_factory=tuple)  # G9: signed per-strategy exposure
    injection_flags_24h: int = 0  # G10: sanitizer flag count in 24h (advisory)

    def __post_init__(self) -> None:
        for name in (
            "now_epoch",
            "data_as_of_epoch",
            "last_broker_ok_epoch",
            "last_llm_ok_epoch",
            "equity_now",
            "equity_prev",
            "equity_dt_s",
            "order_baseline",
        ):
            value = getattr(self, name)
            if not math.isfinite(value):
                raise ValueError(f"GuardState.{name} must be finite, got {value!r}")
        for name in ("ntp_offset_s", "pending_order_age_s"):
            value = getattr(self, name)
            if value is not None and not math.isfinite(value):
                raise ValueError(f"GuardState.{name} must be finite or None, got {value!r}")
        for exposure in self.exposures:
            if not math.isfinite(exposure):
                raise ValueError(f"GuardState.exposures has a non-finite value {exposure!r}")
