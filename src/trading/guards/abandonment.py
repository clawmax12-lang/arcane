"""§8 abandonment evaluator — engaged IN CODE (Increment 6 PART B).

When any §8 trigger fires, the executor must stop and the kill switch must be HARD_STOPPED. The
loss/equity triggers REUSE the sealed ``risk.caps`` checks (no re-encoded $30/$20 constant — two
definitions could drift, the exact M-class failure the floor-of-floors exists to prevent). The
evaluator is a PURE function over injected HARD/STRUCTURED state; ``engage_abandonment`` is the only
side-effecting part (hard_stop + RED page, idempotent because hard_stop is monotonic).

Triggers 1/2/3/8 are LIVE-fed now; 4 is fed from the reconciler's single ReconResult; 5/6/7 are
structurally present and fed by injected ledger counters — an UNFED counter is a safe no-op (it
defaults to a non-triggering value) and can never MASK a real trip.
"""

from __future__ import annotations

import contextlib
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from trading.notify.telegram import Severity
from trading.risk import constants as C
from trading.risk.caps import check_equity_floor, check_total_loss_abandon
from trading.risk.schema import RiskConfig

_LLM_FAIL_RATE = 0.30
_MISTAKE_RECURRENCE = 3
_CALIB_WEEKS = 2


class _Halter(Protocol):
    def hard_stop(self, reason: str) -> object: ...


class _Pager(Protocol):
    def page_operator(self, severity: Severity, text: str) -> None: ...


@dataclass(frozen=True, slots=True)
class AbandonmentState:
    """Injected HARD/STRUCTURED state for the 8 §8 triggers."""

    cumulative_loss_usd: float
    equity_usd: float
    consecutive_scheduler_errors: int = 0
    recon_red: bool = False
    llm_calls_24h: int = 0
    llm_failures_24h: int = 0
    mistake_counts_7d: tuple[int, ...] = field(default_factory=tuple)
    calib_weeks_over_30pct: int = 0
    abandon_marker_present: bool = False


@dataclass(frozen=True, slots=True)
class AbandonmentVerdict:
    triggered: bool
    trigger_id: str | None
    reason: str


def _fire(trigger_id: str, reason: str) -> AbandonmentVerdict:
    return AbandonmentVerdict(True, trigger_id, reason)


def _llm_failure_triggered(state: AbandonmentState) -> bool:
    calls = state.llm_calls_24h
    fails = state.llm_failures_24h
    if calls <= 0:
        return fails > 0  # fail closed: a recorded failure with no successful call is a trigger
    rate = fails / calls
    return (not math.isfinite(rate)) or rate > _LLM_FAIL_RATE


def evaluate_abandonment(state: AbandonmentState, cfg: RiskConfig) -> AbandonmentVerdict:
    """Return the FIRST §8 trigger that fires (priority order), or a no-trigger verdict."""
    if not check_total_loss_abandon(cfg, state.cumulative_loss_usd).ok:
        return _fire(
            "§8.1_total_loss",
            f"cumulative loss {state.cumulative_loss_usd} exceeds abandon "
            f"{cfg.total_loss_abandon_usd}",
        )
    if not check_equity_floor(cfg, state.equity_usd).ok:
        return _fire(
            "§8.2_equity_floor",
            f"equity {state.equity_usd} below floor {cfg.equity_floor_usd}",
        )
    if state.consecutive_scheduler_errors >= C.MAX_CONSECUTIVE_SCHEDULER_ERRORS:
        return _fire(
            "§8.3_consecutive_errors",
            f"{state.consecutive_scheduler_errors} consecutive scheduler errors "
            f">= {C.MAX_CONSECUTIVE_SCHEDULER_ERRORS}",
        )
    if state.recon_red:
        return _fire(
            "§8.4_reconciliation_drift", "reconciliation drift RED (>2 positions > 10 min)"
        )
    if _llm_failure_triggered(state):
        return _fire(
            "§8.5_llm_failure_rate",
            f"LLM failures {state.llm_failures_24h}/{state.llm_calls_24h} in 24h "
            f"> {_LLM_FAIL_RATE:.0%}",
        )
    if max(state.mistake_counts_7d, default=0) >= _MISTAKE_RECURRENCE:
        return _fire(
            "§8.6_mistake_recurrence",
            f"a mistake category recurred {max(state.mistake_counts_7d, default=0)} "
            f">= {_MISTAKE_RECURRENCE} times in 7d",
        )
    if state.calib_weeks_over_30pct >= _CALIB_WEEKS:
        return _fire(
            "§8.7_calibration_drift",
            f"calibration error > 30% for {state.calib_weeks_over_30pct} consecutive weeks",
        )
    if state.abandon_marker_present:
        return _fire("§8.8_operator_abandon", "operator `make abandon` marker present")
    return AbandonmentVerdict(False, None, "no abandonment trigger")


def engage_abandonment(
    verdict: AbandonmentVerdict,
    kill_switch: _Halter,
    notifier: _Pager,
    *,
    broker_flat_fn: Callable[[], object] | None = None,
) -> bool:
    """Engage a triggered abandonment: HARD_STOP (durable, monotonic) FIRST, then auto-flatten open
    positions (GRD-3, best-effort AFTER the latch), then a best-effort RED page.

    Returns True iff a RED page was DELIVERED (False if not triggered, or triggered but the page
    raised). The loop uses this to fail paging CLOSED — a dropped abandonment page still arms the
    §5.2 ladder + a durable PAGE_PENDING tombstone. ``broker_flat_fn`` flattens for OUT-OF-LOOP
    callers (a future CLI/agent); the loop flattens via its own auto-flat composition
    (``verdict.triggered`` folded into ``auto_flat_needed``), so it passes ``None`` here.
    """
    if not verdict.triggered:
        return False
    reason = f"ABANDON {verdict.trigger_id}: {verdict.reason}"
    kill_switch.hard_stop(reason)  # durable + idempotent FIRST (latch before the flat/page)
    if broker_flat_fn is not None:
        with contextlib.suppress(Exception):  # GRD-3: a flat failure must never un-halt us
            broker_flat_fn()
    try:
        notifier.page_operator(Severity.RED, reason)
        return True
    except Exception:  # a dropped page must not undo the engaged hard_stop (already latched)
        return False
