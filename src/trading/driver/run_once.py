"""``drive_once`` — the FIRST real driver of the acting path, RECORD-ONLY (Increment 7 PART C).

One deterministic pass wires the whole pipeline:

    PIT universe (fetch + seal) → backtest each strategy → bias gate (ALL-of) → allocator
    (survivors-only, subtractive regime) → ``run_loop_pass`` (record-only).

It is the first production caller of ``evaluate_family`` / ``allocate`` / ``run_loop_pass`` and the
home of the D1-residual closure: the gate derives the T2 binding from the base-produced proof-bearer
``UniverseSnapshot`` and loads the artifact from the content-addressed cache, so a forged universe
is unbindable. With the 4 edgeless toys the gate KILLS all → the allocator allocates NOBODY → the
loop submits NOTHING (ADR §0) — the locked, correct outcome.

Fail-closed by construction: ANY assembly error (a Polygon fetch failure, an unbindable universe, an
oversized family) ABORTS to ZERO candidates — never a partial submit. The safety machinery in
``run_loop_pass`` (recon → guards → §8 → §5.2) STILL runs (with zero candidates), so escalation is
never skipped. RECORD_ONLY: the driver NEVER writes the operator ``state/SUBMIT_GO`` marker, and it
imports NO LLM/agent module (PHI1 — this package is in the submit-path AST scan).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

import pandas as pd

from trading.allocator.allocate import AllocationRequest, allocate
from trading.backtest.cost_model import CostModel
from trading.backtest.engine import BacktestEngine, SymbolPanel
from trading.backtest.resolve import ResolvedStrategy
from trading.backtest.walk_forward import WalkForwardConfig
from trading.bias_gate.gate import FamilyMember, GateDecision, evaluate_family
from trading.bias_gate.high_water_mark import NTrialsHighWaterMark
from trading.bias_gate.thresholds import MAX_FAMILY_SIZE
from trading.data.membership_cache import MembershipCache
from trading.data.pit import AsOf
from trading.data.universe import PITUniverse
from trading.driver.errors import DriverError
from trading.executor.intent import Side
from trading.executor.loop import (
    LoopDeps,
    LoopInputs,
    LoopPassResult,
    SubmitCandidate,
    run_loop_pass,
)
from trading.executor.sizing import HardQuote, TargetPosition
from trading.factors.trial_ledger import TrialLedger
from trading.regime.labels import RegimeLabel
from trading.regime.model import RegimeModel, assess
from trading.regime.posture import posture_from


@dataclass(frozen=True, slots=True)
class DriverContext:
    """Everything one driver pass needs — the candidate family, market state, wired primitives."""

    strategies: Sequence[ResolvedStrategy]
    panel: SymbolPanel
    universe: (
        PITUniverse  # the proof-bearing PIT source (PolygonPITUniverse); .as_of_members may raise
    )
    market_proxy: pd.DataFrame  # bars for the (advisory, DERIVED) regime read
    as_of: AsOf
    cost: CostModel
    folds: WalkForwardConfig
    ledger: TrialLedger
    hwm: NTrialsHighWaterMark
    membership_cache: MembershipCache
    regime_model: RegimeModel
    loop_inputs: (
        LoopInputs  # the HARD/STRUCTURED safety state (its candidates field is overwritten)
    )
    loop_deps: LoopDeps


@dataclass(frozen=True, slots=True)
class DriverResult:
    snapshot_hash: str | None
    decisions: tuple[GateDecision, ...]
    candidate_count: int
    posture_label: RegimeLabel
    loop_result: LoopPassResult
    assembly_error: str | None


def _target(strategy: ResolvedStrategy, symbol: str) -> TargetPosition:
    # A DETERMINISTIC target (never an agent/LLM output): a flat BUY on the panel's first symbol. It
    # is consumed ONLY for a survivor; with the killed toys there are zero survivors, so it is moot.
    return TargetPosition(strategy.name, symbol, Side.BUY, spec_hash=strategy.spec.spec_hash)


def _quote(panel: SymbolPanel, symbol: str, now_epoch: float) -> HardQuote:
    price = float(panel.bars[symbol]["close"].astype("float64").iloc[-1])
    return HardQuote(symbol, price, now_epoch)


def drive_once(ctx: DriverContext) -> DriverResult:
    """Run one record-only driver pass; return the gate decisions + the (toys-zero) loop result."""
    candidates: tuple[SubmitCandidate, ...] = ()
    decisions: tuple[GateDecision, ...] = ()
    snapshot_hash: str | None = None
    posture_label = RegimeLabel.UNKNOWN
    assembly_error: str | None = None
    try:
        snapshot = ctx.universe.as_of_members(as_of=ctx.as_of)  # may raise (fetch / unbindable)
        snapshot_hash = snapshot.meta.universe_hash
        posture = posture_from(assess(ctx.regime_model, ctx.market_proxy))
        posture_label = posture.label

        # regime SUBTRACTIVE filter BEFORE the gate (GT-2: a regime-vetoed strategy must not consume
        # ledger n_trials); the allocator re-applies it as the structural guarantee.
        eligible = [
            s for s in ctx.strategies if posture.is_eligible(frozenset(s.spec.eligible_regimes))
        ]
        # bound + dedup BEFORE the gate (skeptic A3); evaluate_family backstops this structurally.
        seen: set[str] = set()
        deduped: list[ResolvedStrategy] = []
        for s in eligible:
            if s.spec.spec_hash not in seen:
                seen.add(s.spec.spec_hash)
                deduped.append(s)
        if len(deduped) > MAX_FAMILY_SIZE:
            raise DriverError(f"family size {len(deduped)} exceeds MAX {MAX_FAMILY_SIZE}")

        engine = BacktestEngine()
        symbol = sorted(ctx.panel.bars.keys())[0]
        members = [
            FamilyMember(
                strategy=s,
                panel=ctx.panel,
                cost=ctx.cost,
                folds=ctx.folds,
                as_of=ctx.as_of,
                result=engine.run(
                    s, ctx.panel, as_of=ctx.as_of, ledger=ctx.ledger, cost=ctx.cost, folds=ctx.folds
                ),
                universe=snapshot,
            )
            for s in deduped
        ]
        decisions = evaluate_family(
            members, ledger=ctx.ledger, hwm=ctx.hwm, membership_cache=ctx.membership_cache
        )
        requests = [
            AllocationRequest(
                d,
                _target(s, symbol),
                _quote(ctx.panel, symbol, ctx.loop_inputs.now_epoch),
                frozenset(s.spec.eligible_regimes),
            )
            for d, s in zip(decisions, deduped, strict=True)
        ]
        candidates = allocate(requests, universe_artifact_hash=snapshot_hash, posture=posture)
    except Exception as exc:
        # fail closed: a partial/failed assembly submits NOTHING (never a partial). The safety
        # machinery in run_loop_pass STILL runs below (with zero candidates) so escalation is alive.
        assembly_error = type(exc).__name__
        candidates = ()

    loop_inputs = replace(ctx.loop_inputs, candidates=candidates)
    loop_result = run_loop_pass(loop_inputs, ctx.loop_deps)
    return DriverResult(
        snapshot_hash=snapshot_hash,
        decisions=decisions,
        candidate_count=len(candidates),
        posture_label=posture_label,
        loop_result=loop_result,
        assembly_error=assembly_error,
    )
