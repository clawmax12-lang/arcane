"""``run_loop_pass`` — the single restart-safe, fail-closed executor pass (Increment 6 PART C).

One deterministic pass composes the safety machinery BEFORE any submit decision, so the loop
can always
escalate (even while already TRIPPED) and a RED/abandonment pass NEVER also submits:

  1. reconcile drift (G3) → escalate kill switch (+ RED auto-flat).
  2. assess Murphy guards G1–G10 → apply (ORANGE trip / RED hard_stop + auto_flat + page).
  3. evaluate §8 abandonment → engage (hard_stop + page) if triggered.
  4. tick the §5.2 operator-page escalation ladder.
  5. if ANY disaster (a guard/recon auto-flat, an abandonment trigger, or a non-ARMED switch) →
     flat-all and RETURN with ZERO submits.
  6. ONLY if ARMED and no disaster: size + gate + (record-only / single-use-GO) submit each
     AllocationGrant candidate. With the 4 edgeless toys there are ZERO grants, so this body is
     empty.

Any exception in steps 1–4 is caught: the pass returns WITHOUT submitting and flags a scheduler
error
(the orchestrator increments the §8.3 consecutive-error counter for the next pass). No LLM module
is imported anywhere in this file or the modules it calls (PHI1) — a committed AST test pins that.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from trading.executor.broker_paper import PaperBroker
from trading.executor.grant import AllocationGrant
from trading.executor.idempotency import IdempotencyStore
from trading.executor.invariants import AccountSnapshot, MistakeChecker, _no_mistakes
from trading.executor.kill_switch import KillSwitch
from trading.executor.reconcile_loop import ReconcileOutcome, reconcile_once
from trading.executor.sizing import HardQuote, TargetPosition
from trading.executor.submit import DEFAULT_GO_MARKER, SubmitOutcome, submit_allocated
from trading.guards.abandonment import (
    AbandonmentState,
    AbandonmentVerdict,
    engage_abandonment,
    evaluate_abandonment,
)
from trading.guards.inputs import GuardState
from trading.guards.page_escalation import PageEscalation, apply_escalation
from trading.guards.panel import GuardApplication, GuardPanel, Pager, apply_guards
from trading.risk.schema import RiskConfig


@dataclass(frozen=True, slots=True)
class SubmitCandidate:
    """One allocated survivor ready to size+submit (ZERO of these with the edgeless toys)."""

    grant: AllocationGrant
    target: TargetPosition
    quote: HardQuote


@dataclass(frozen=True, slots=True)
class LoopInputs:
    """The HARD/STRUCTURED state for one pass — assembled by the orchestrator from broker/clock
    reads."""

    local_positions: Mapping[str, float]
    broker_positions: Mapping[str, float]
    drift_since_epoch: float | None
    now_epoch: float
    guard_state: GuardState
    abandonment_state: AbandonmentState
    snapshot: AccountSnapshot
    candidates: Sequence[SubmitCandidate] = ()


@dataclass(frozen=True, slots=True)
class LoopDeps:
    """The wired dependencies (sealed primitives + the gate-gated submit path)."""

    kill_switch: KillSwitch
    notifier: Pager
    broker: PaperBroker
    store: IdempotencyStore
    guard_panel: GuardPanel
    cfg: RiskConfig
    page_escalation: PageEscalation | None = None
    mistake_checker: MistakeChecker = _no_mistakes
    go_marker_path: Path = DEFAULT_GO_MARKER


@dataclass(frozen=True, slots=True)
class LoopPassResult:
    armed_at_start: bool
    recon: ReconcileOutcome | None
    guards: GuardApplication | None
    abandonment: AbandonmentVerdict | None
    disaster: bool
    auto_flatted: bool
    submitted_count: int
    outcomes: tuple[SubmitOutcome, ...]
    scheduler_error: str | None


def run_loop_pass(inputs: LoopInputs, deps: LoopDeps) -> LoopPassResult:
    """Run ONE deterministic, fail-closed pass. Safety escalation always precedes any submit."""
    armed_at_start = deps.kill_switch.allows_new_orders()
    try:
        recon = reconcile_once(
            inputs.local_positions,
            inputs.broker_positions,
            inputs.drift_since_epoch,
            inputs.now_epoch,
            kill_switch=deps.kill_switch,
            notifier=deps.notifier,
            broker_flat_fn=deps.broker.flat_all,
        )
        guard_results = deps.guard_panel.assess(inputs.guard_state, recon.result)
        guards = apply_guards(guard_results, deps.kill_switch, deps.notifier)
        verdict = evaluate_abandonment(inputs.abandonment_state, deps.cfg)
        engage_abandonment(verdict, deps.kill_switch, deps.notifier)
        if deps.page_escalation is not None:
            action = deps.page_escalation.tick(inputs.now_epoch)
            apply_escalation(
                action, deps.kill_switch, deps.notifier, broker_flat_fn=deps.broker.flat_all
            )
    except Exception as exc:
        # fail-closed: a pass error submits NOTHING and is surfaced for the §8.3 error counter.
        return LoopPassResult(
            armed_at_start, None, None, None, True, False, 0, (), type(exc).__name__
        )

    # auto_flat strictly precedes any submit: a guard RED may demand a flat the reconciler
    # didn't do.
    auto_flat_needed = guards.auto_flat or recon.result.require_auto_flat
    auto_flatted = recon.auto_flatted
    if auto_flat_needed and not auto_flatted:
        deps.broker.flat_all()
        auto_flatted = True

    disaster = auto_flat_needed or verdict.triggered or not deps.kill_switch.allows_new_orders()
    if disaster:
        return LoopPassResult(
            armed_at_start, recon, guards, verdict, True, auto_flatted, 0, (), None
        )

    # ARMED + no disaster: size + gate + submit each candidate (ZERO with the edgeless toys).
    outcomes = tuple(
        submit_allocated(
            c.grant,
            c.target,
            c.quote,
            inputs.snapshot,
            deps.cfg,
            deps.kill_switch,
            deps.store,
            deps.broker,
            mistake_checker=deps.mistake_checker,
            go_marker_path=deps.go_marker_path,
        )
        for c in inputs.candidates
    )
    submitted = sum(1 for o in outcomes if o.submitted)
    return LoopPassResult(
        armed_at_start, recon, guards, verdict, False, auto_flatted, submitted, outcomes, None
    )
