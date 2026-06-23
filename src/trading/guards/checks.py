"""G1–G10 Murphy-guard checks — pure deterministic functions, fail CLOSED (Increment 6 PART B).

Each check maps the injected ``GuardState`` to a ``GuardResult`` with a graduated level. Thresholds
are module-level constants (LAW, like ``risk/constants.py``) — NOT YAML-tunable, so a config
edit can
never weaken a guard. Anything missing/non-finite/degenerate resolves to ORANGE or RED, NEVER GREEN.

§4.3 split: G1/G2/G4/G6/G7/G8 read HARD/STRUCTURED state and may GATE an order. G5 (LLM heartbeat),
G9 (correlation), G10 (prompt-injection) are DERIVED/TEXTUAL — they page and can hard_stop the
LOOP on
RED but their ``gates_orders`` is False, so they can NEVER block a specific order. G3
(reconciliation
drift) is delegated to the reconciler and assembled in ``panel`` from a ``ReconResult``.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Final

from trading.guards.inputs import GuardState
from trading.guards.levels import GuardLevel, GuardResult
from trading.risk import constants as C

StateCheck = Callable[[GuardState], GuardResult]

# --- thresholds (law) ---
G1_STALE_ORANGE_S: Final[float] = C.MAX_BAR_AGE_SECONDS  # 300s (= M17 freshness ceiling)
G1_STALE_RED_S: Final[float] = 2 * C.MAX_BAR_AGE_SECONDS  # 600s
G2_FILL_ORANGE_S: Final[float] = 30.0
G2_FILL_RED_S: Final[float] = 120.0
G4_BROKER_ORANGE_S: Final[float] = 60.0  # §5.1 G4: broker unreachable > 60s
G4_BROKER_RED_S: Final[float] = 180.0
G5_LLM_RED_S: Final[float] = (
    300.0  # §5.1 G5: LLM unreachable > 5 min ⇒ fall back to last-known-good
)
G6_NTP_MAX_S: Final[float] = 1.0  # §5.1 G6: clock vs NTP > 1s ⇒ halt
G7_EQUITY_WINDOW_S: Final[float] = (
    60.0  # an equity jump WITHIN this window is the manipulation signal
)
G7_EQUITY_ORANGE_PCT: Final[float] = 0.10
G7_EQUITY_RED_PCT: Final[float] = 0.20
G8_BURST_MULT: Final[float] = 3.0  # §5.1 G8: orders/window > 3x baseline
G10_INJECTION_ORANGE: Final[int] = 10  # §5.1 G10: sanitizer flags > X in 24h


def _result(guard_id: str, level: GuardLevel, reason: str, *, gates_orders: bool) -> GuardResult:
    return GuardResult(guard_id=guard_id, level=level, reason=reason, gates_orders=gates_orders)


def g1_data_staleness(s: GuardState) -> GuardResult:
    age = s.now_epoch - s.data_as_of_epoch
    if age < 0:
        return _result(
            "G1_data_staleness",
            GuardLevel.RED,
            f"future bar (age {age:.1f}s < 0)",
            gates_orders=True,
        )
    if age > G1_STALE_RED_S:
        return _result(
            "G1_data_staleness",
            GuardLevel.RED,
            f"data {age:.0f}s stale > {G1_STALE_RED_S:.0f}s",
            gates_orders=True,
        )
    if age > G1_STALE_ORANGE_S:
        return _result(
            "G1_data_staleness",
            GuardLevel.ORANGE,
            f"data {age:.0f}s stale > {G1_STALE_ORANGE_S:.0f}s",
            gates_orders=True,
        )
    return _result(
        "G1_data_staleness", GuardLevel.GREEN, f"data {age:.0f}s fresh", gates_orders=True
    )


def g2_fill_delay(s: GuardState) -> GuardResult:
    age = s.pending_order_age_s
    if age is None:
        return _result("G2_fill_delay", GuardLevel.GREEN, "no pending order", gates_orders=True)
    if age < 0:
        return _result(
            "G2_fill_delay", GuardLevel.RED, f"negative fill age {age:.1f}s", gates_orders=True
        )
    if age > G2_FILL_RED_S:
        return _result(
            "G2_fill_delay",
            GuardLevel.RED,
            f"order unfilled {age:.0f}s > {G2_FILL_RED_S:.0f}s",
            gates_orders=True,
        )
    if age > G2_FILL_ORANGE_S:
        return _result(
            "G2_fill_delay",
            GuardLevel.ORANGE,
            f"order unfilled {age:.0f}s > {G2_FILL_ORANGE_S:.0f}s",
            gates_orders=True,
        )
    return _result("G2_fill_delay", GuardLevel.GREEN, f"pending {age:.0f}s", gates_orders=True)


def g4_broker_heartbeat(s: GuardState) -> GuardResult:
    gap = s.now_epoch - s.last_broker_ok_epoch
    if gap > G4_BROKER_RED_S:
        return _result(
            "G4_broker_heartbeat",
            GuardLevel.RED,
            f"broker silent {gap:.0f}s > {G4_BROKER_RED_S:.0f}s",
            gates_orders=True,
        )
    if gap > G4_BROKER_ORANGE_S:
        return _result(
            "G4_broker_heartbeat",
            GuardLevel.ORANGE,
            f"broker silent {gap:.0f}s > {G4_BROKER_ORANGE_S:.0f}s",
            gates_orders=True,
        )
    return _result(
        "G4_broker_heartbeat", GuardLevel.GREEN, f"broker ok {gap:.0f}s ago", gates_orders=True
    )


def g5_llm_heartbeat(s: GuardState) -> GuardResult:
    # DERIVED/§4.3: advisory only — caps at ORANGE and only pages. The LLM is slow-loop
    # advisory; the
    # deterministic submit path does not need it, so an outage DEGRADES (use last-known-good) +
    # pages,
    # it never halts. A non-gating guard must NEVER mutate the kill switch (DERIVED can't trigger).
    gap = s.now_epoch - s.last_llm_ok_epoch
    if gap > G5_LLM_RED_S:
        return _result(
            "G5_llm_heartbeat",
            GuardLevel.ORANGE,
            f"LLM silent {gap:.0f}s > {G5_LLM_RED_S:.0f}s (fallback to last-known-good)",
            gates_orders=False,
        )
    return _result(
        "G5_llm_heartbeat", GuardLevel.GREEN, f"LLM ok {gap:.0f}s ago", gates_orders=False
    )


def g6_time_drift(s: GuardState) -> GuardResult:
    if s.ntp_offset_s is None:
        return _result(
            "G6_time_drift",
            GuardLevel.RED,
            "NTP offset unavailable (fail closed)",
            gates_orders=True,
        )
    if abs(s.ntp_offset_s) > G6_NTP_MAX_S:
        return _result(
            "G6_time_drift",
            GuardLevel.RED,
            f"clock drift {s.ntp_offset_s:.3f}s > {G6_NTP_MAX_S}s",
            gates_orders=True,
        )
    return _result(
        "G6_time_drift", GuardLevel.GREEN, f"clock drift {s.ntp_offset_s:.3f}s", gates_orders=True
    )


def g7_equity_velocity(s: GuardState) -> GuardResult:
    if s.equity_dt_s <= 0:
        return _result(
            "G7_equity_velocity",
            GuardLevel.RED,
            f"non-positive sample dt {s.equity_dt_s}s (fail closed)",
            gates_orders=True,
        )
    base = abs(s.equity_prev)
    if base == 0:
        return _result(
            "G7_equity_velocity",
            GuardLevel.RED,
            "zero prior equity (fail closed)",
            gates_orders=True,
        )
    pct = abs(s.equity_now - s.equity_prev) / base
    within = s.equity_dt_s <= G7_EQUITY_WINDOW_S
    if within and pct >= G7_EQUITY_RED_PCT:
        return _result(
            "G7_equity_velocity",
            GuardLevel.RED,
            f"equity moved {pct:.0%} in {s.equity_dt_s:.0f}s",
            gates_orders=True,
        )
    if within and pct >= G7_EQUITY_ORANGE_PCT:
        return _result(
            "G7_equity_velocity",
            GuardLevel.ORANGE,
            f"equity moved {pct:.0%} in {s.equity_dt_s:.0f}s",
            gates_orders=True,
        )
    return _result(
        "G7_equity_velocity", GuardLevel.GREEN, f"equity moved {pct:.0%}", gates_orders=True
    )


def g8_order_frequency(s: GuardState) -> GuardResult:
    if not math.isfinite(s.order_baseline) or s.order_baseline <= 0:
        return _result(
            "G8_order_frequency",
            GuardLevel.RED,
            f"invalid order baseline {s.order_baseline!r} (fail closed)",
            gates_orders=True,
        )
    if s.orders_in_window > G8_BURST_MULT * s.order_baseline:
        return _result(
            "G8_order_frequency",
            GuardLevel.ORANGE,
            f"{s.orders_in_window} orders > {G8_BURST_MULT}x baseline {s.order_baseline:.2f}",
            gates_orders=True,
        )
    return _result(
        "G8_order_frequency",
        GuardLevel.GREEN,
        f"{s.orders_in_window} orders within baseline",
        gates_orders=True,
    )


def g9_correlation_spike(s: GuardState) -> GuardResult:
    # STRUCTURAL until >1 live strategy; advisory only (§4.3).
    nonzero = [e for e in s.exposures if e != 0]
    if len(nonzero) >= 2 and (all(e > 0 for e in nonzero) or all(e < 0 for e in nonzero)):
        return _result(
            "G9_correlation_spike",
            GuardLevel.ORANGE,
            f"{len(nonzero)} strategies same-direction",
            gates_orders=False,
        )
    return _result(
        "G9_correlation_spike", GuardLevel.GREEN, "no correlation spike", gates_orders=False
    )


def g10_prompt_injection(s: GuardState) -> GuardResult:
    # TEXTUAL/§4.3: advisory only.
    if s.injection_flags_24h > G10_INJECTION_ORANGE:
        return _result(
            "G10_prompt_injection",
            GuardLevel.ORANGE,
            f"{s.injection_flags_24h} sanitizer flags in 24h",
            gates_orders=False,
        )
    return _result(
        "G10_prompt_injection",
        GuardLevel.GREEN,
        f"{s.injection_flags_24h} sanitizer flags in 24h",
        gates_orders=False,
    )


#: G1–G2, G4–G10 over GuardState (G3 = reconciler, assembled in ``panel``). Order is stable.
STATE_CHECKS: Final[tuple[StateCheck, ...]] = (
    g1_data_staleness,
    g2_fill_delay,
    g4_broker_heartbeat,
    g5_llm_heartbeat,
    g6_time_drift,
    g7_equity_velocity,
    g8_order_frequency,
    g9_correlation_spike,
    g10_prompt_injection,
)
