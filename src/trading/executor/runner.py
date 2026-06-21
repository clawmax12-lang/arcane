"""No-op paper executor (Increment 1).

Runs the full pre-submit invariant chain and, on acceptance, records the idempotency
key — but submits NOTHING to a broker yet (Increment 2 wires the paper submit). This
proves the end-to-end decision path is sound while the system stays inert.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from trading.executor.idempotency import IdempotencyStore
from trading.executor.intent import OrderIntent
from trading.executor.invariants import (
    AccountSnapshot,
    GateDecision,
    MistakeChecker,
    _no_mistakes,
    evaluate_pre_submit,
)
from trading.executor.kill_switch import KillSwitch
from trading.risk.schema import RiskConfig

_log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    """Outcome of a runner pass. ``submitted`` is always False in Increment 1."""

    submitted: bool
    decision: GateDecision


def execute_paper(
    intent: OrderIntent,
    snapshot: AccountSnapshot,
    cfg: RiskConfig,
    kill_switch: KillSwitch,
    store: IdempotencyStore,
    *,
    mistake_checker: MistakeChecker = _no_mistakes,
) -> ExecutionResult:
    """Gate an intent through the full chain; record it if accepted; submit nothing."""
    decision = evaluate_pre_submit(
        intent, snapshot, cfg, kill_switch, store.seen, mistake_checker=mistake_checker
    )
    if not decision.accepted:
        _log.info(
            "order_rejected",
            gate=decision.failed_gate,
            reason=decision.reason,
            client_order_id=decision.client_order_id,
        )
        return ExecutionResult(submitted=False, decision=decision)

    # Accepted: atomically claim the idempotency key, but DO NOT submit (Increment 1).
    newly_recorded = store.remember(decision.client_order_id)
    if not newly_recorded:
        race = GateDecision(
            accepted=False,
            client_order_id=decision.client_order_id,
            failed_gate="idempotency",
            reason="lost idempotency race (concurrent submit)",
        )
        _log.warning("idempotency_race", client_order_id=decision.client_order_id)
        return ExecutionResult(submitted=False, decision=race)

    _log.info(
        "order_accepted_noop",
        client_order_id=decision.client_order_id,
        note="paper no-op: no broker submission in Increment 1",
    )
    return ExecutionResult(submitted=False, decision=decision)
