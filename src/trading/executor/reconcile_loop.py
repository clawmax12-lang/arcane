"""Reconciliation loop — broker-authoritative drift handling (G3 / §8.4) (Increment 6 PART C).

Thin wrapper over the SEALED ``reconciler``: assess drift, escalate the kill switch (ORANGE→trip,
RED→hard_stop — reused, not re-encoded), and on a RED (auto-flat) drift perform the protective
flat-all + a RED operator page. The kill-switch escalation happens FIRST (durable) so a flat or page
failure can never undo the halt. Also exposes a startup reconciliation that resolves claimed-but-
unconfirmed orders via the broker (closes the claim/submit crash window).
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from trading.executor.kill_switch import KillSwitch
from trading.executor.reconciler import (
    DRIFT_RED_POSITIONS,
    DRIFT_RED_SECONDS,
    ReconResult,
    assess_drift,
    escalate_kill_switch,
)
from trading.notify.telegram import Severity

#: A minimal pager (TelegramNotifier satisfies it).
Pager = Callable[..., None]


@dataclass(frozen=True, slots=True)
class ReconcileOutcome:
    result: ReconResult
    auto_flatted: bool
    paged: bool


def _try_page(notifier: object, reason: str) -> bool:
    page = getattr(notifier, "page_operator", None)
    if page is None:
        return False
    try:
        page(Severity.RED, reason)
        return True
    except Exception:
        return False


def reconcile_once(
    local: Mapping[str, float],
    broker_positions: Mapping[str, float],
    drift_since_epoch: float | None,
    now_epoch: float,
    *,
    kill_switch: KillSwitch,
    notifier: object,
    broker_flat_fn: Callable[[], object],
    red_positions: int = DRIFT_RED_POSITIONS,
    red_seconds: float = DRIFT_RED_SECONDS,
) -> ReconcileOutcome:
    """Assess drift, escalate the kill switch, and on RED auto-flat + page. Total (never raises)."""
    result = assess_drift(
        local,
        broker_positions,
        drift_since_epoch,
        now_epoch,
        red_positions=red_positions,
        red_seconds=red_seconds,
    )
    escalate_kill_switch(result, kill_switch)  # durable FIRST (ORANGE→trip, RED→hard_stop)
    auto_flatted = False
    paged = False
    if result.require_auto_flat:
        with contextlib.suppress(Exception):  # a flat failure must not undo the latched hard_stop
            broker_flat_fn()
            auto_flatted = True
        paged = _try_page(notifier, f"reconciliation RED auto-flat: {result.reason}")
    return ReconcileOutcome(result, auto_flatted, paged)


def reconcile_claimed_orders(
    claimed_unconfirmed: Sequence[str], lookup_status: Callable[[str], str]
) -> dict[str, str]:
    """Resolve claimed-but-unconfirmed client_order_ids via the broker (startup orphan reconcile).

    Returns ``{coid: status}``. A claim with no broker order surfaces as a non-accepted status the
    operator can inspect — never a blind re-submit (the duplicate-order cardinal sin).
    """
    return {coid: lookup_status(coid) for coid in claimed_unconfirmed}
