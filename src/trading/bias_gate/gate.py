"""The gate's verdict types + (C8) the ALL-of composer — the FIRST accept/kill VERDICT in ARCANE.

``GateComponent`` is one named pass/fail with a reason; ``GateDecision`` is the frozen per-strategy
verdict (``allocated`` True ⇒ ALLOCATED, else KILLED). These bias-gate symbols (``allocated`` /
``passed`` / verdict) are banned in ``src/trading/backtest`` and legal ONLY here. The ALL-of
``evaluate_family`` composer is added in cluster C8; this module first pins the immutable verdict
shapes that the tripwire tests (A4) and the statistics judges consume.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

import numpy as np

from trading.backtest.cost_model import CostModel
from trading.backtest.engine import BacktestEngine, SymbolPanel
from trading.backtest.ledger_integration import STRATEGY_KIND
from trading.backtest.resolve import ResolvedStrategy
from trading.backtest.statistics import BacktestResult
from trading.backtest.walk_forward import WalkForwardConfig
from trading.bias_gate.errors import BiasGateError
from trading.bias_gate.evidence import (
    GateEvidence,
    assert_purge_adequate,
    build_evidence,
)
from trading.bias_gate.high_water_mark import NTrialsHighWaterMark
from trading.bias_gate.stats import (
    Matrix,
    dsr_probability,
    pbo_fraction,
    per_obs_sharpe,
    psr_probability,
    spa_pvalue,
)
from trading.bias_gate.tests_t2 import t2_survivorship
from trading.bias_gate.thresholds import (
    COST_STRESS_SCALES,
    DSR_THRESHOLD,
    MIN_FAMILY_SIZE,
    MIN_FOLDS,
    PBO_THRESHOLD,
    PSR_THRESHOLD,
    SPA_ALPHA,
    WF_MIN_FRACTION_FOLDS,
    WF_STEP_MONTHS,
    WF_TEST_MONTHS,
    WF_TRAIN_MONTHS,
)
from trading.bias_gate.trial_identity import eval_trial_params
from trading.bias_gate.verdict import GateComponent, GateDecision
from trading.data.membership_artifact import MembershipArtifact, ProvenanceBinding
from trading.data.pit import AsOf
from trading.factors.trial_ledger import TrialLedger

__all__ = [
    "FROZEN_COMPONENT_NAMES",
    "FamilyMember",
    "GateComponent",
    "GateDecision",
    "combine_member_verdict",
    "evaluate_family",
    "judge_member",
    "wf_oos_ok",
]

#: The frozen ADR-§8 component slice this gate evaluates (any one failing ⇒ KILL). A test pins it.
FROZEN_COMPONENT_NAMES: Final[tuple[str, ...]] = (
    "T1_consistency",
    "T2_survivorship",
    "DSR_deflated_sharpe",
    "PSR_prob_sharpe",
    "WF_OOS",
    "enough_samples",
    "cost_stress",
    "PBO_overfit",
    "SPA_superiority",
)


@dataclass(frozen=True, slots=True)
class FamilyMember:
    """One candidate bundle: the resolved strategy, its panel/cost/folds, and the sealed result.

    The driver runs ``BacktestEngine.run`` to produce ``result`` (and assert A3 purge) BEFORE the
    gate sees it; the gate re-derives the OOS series and re-checks consistency (T1). ``binding`` +
    ``artifact`` carry the hash-bound Polygon PIT membership the T2 verifier checks against; absent
    (the toys, any non-PIT universe) ⇒ T2 fails CLOSED and the member is KILLED.
    """

    strategy: ResolvedStrategy
    panel: SymbolPanel
    cost: CostModel
    folds: WalkForwardConfig
    as_of: AsOf
    result: BacktestResult
    binding: ProvenanceBinding | None = None
    artifact: MembershipArtifact | None = None


def _wf_ok(sharpe: float, frac: float, n_folds: int, train: int, test: int, step: int) -> bool:
    """Positive-form WF-OOS criterion; a NaN/short/mis-geometry input returns False (KILL)."""
    return (
        math.isfinite(sharpe)
        and sharpe > 0.0
        and math.isfinite(frac)
        and frac >= WF_MIN_FRACTION_FOLDS
        and n_folds >= MIN_FOLDS
        and train == WF_TRAIN_MONTHS
        and test == WF_TEST_MONTHS
        and step == WF_STEP_MONTHS
    )


def wf_oos_ok(result: BacktestResult) -> bool:
    """The ADR-§8 walk-forward OOS criterion read off the sealed ``BacktestResult``."""
    return _wf_ok(
        result.oos_annualized_sharpe,
        result.fraction_folds_positive,
        len(result.per_fold_oos_sharpe),
        result.train_months,
        result.test_months,
        result.step_months,
    )


def _wf_ok_evidence(ev: GateEvidence) -> bool:
    return _wf_ok(
        ev.oos_annualized_sharpe,
        ev.fraction_folds_positive,
        len(ev.per_fold_oos_sharpe),
        ev.train_months,
        ev.test_months,
        ev.step_months,
    )


def _passes_above(name: str, metric: float, threshold: float) -> GateComponent:
    """``passed = metric > threshold`` (POSITIVE form: a NaN metric ⇒ False ⇒ KILL — never open)."""
    passed = bool(math.isfinite(metric) and metric > threshold)
    return GateComponent(name, passed, f"{name}={metric:.6f}; need > {threshold}")


def _passes_below(name: str, metric: float, threshold: float) -> GateComponent:
    """``passed = metric < threshold`` (POSITIVE form: a NaN metric ⇒ False ⇒ KILL — never open)."""
    passed = bool(math.isfinite(metric) and metric < threshold)
    return GateComponent(name, passed, f"{name}={metric:.6f}; need < {threshold}")


def combine_member_verdict(
    spec_hash: str, components: tuple[GateComponent, ...], n_trials: int
) -> GateDecision:
    """ALL-of: ``allocated`` iff there ARE components AND every one passed; reasons name failures.

    ``bool(components) and ...`` guards the vacuous ``all([]) == True`` fail-open (FC-3): an
    empty component set is never an allocation.
    """
    allocated = bool(components) and all(c.passed for c in components)
    reasons = tuple(c.reason for c in components if not c.passed) or (
        () if components else ("no gate components evaluated",)
    )
    return GateDecision(spec_hash, allocated, components, n_trials, reasons)


def judge_member(
    evidence: GateEvidence,
    result: BacktestResult,
    n_trials: int,
    family_sharpes: Sequence[float],
    stressed_evidences: Sequence[GateEvidence],
    *,
    binding: ProvenanceBinding | None = None,
    artifact: MembershipArtifact | None = None,
) -> tuple[GateComponent, ...]:
    """The 7 PER-MEMBER components (T1/T2/DSR/PSR/WF/enough_samples/cost_stress); fail-closed.

    T1 already passed (``build_evidence`` raised otherwise). DSR/PSR read the per-obs recompute; the
    cost-stress requires DSR/PSR/WF to STILL hold on each higher-cost re-run. T2 binds against the
    hash-bound PIT membership artifact (absent ⇒ fail closed).
    """
    dsr = dsr_probability(evidence.oos_returns, n_trials, family_sharpes)
    psr = psr_probability(evidence.oos_returns)
    stress_ok = len(stressed_evidences) == len(COST_STRESS_SCALES) and all(
        dsr_probability(se.oos_returns, n_trials, family_sharpes) > DSR_THRESHOLD
        and psr_probability(se.oos_returns) > PSR_THRESHOLD
        and _wf_ok_evidence(se)
        for se in stressed_evidences
    )
    return (
        GateComponent("T1_consistency", True, "recompute matched the sealed result"),
        t2_survivorship(result, binding, artifact),
        _passes_above("DSR_deflated_sharpe", dsr, DSR_THRESHOLD),
        _passes_above("PSR_prob_sharpe", psr, PSR_THRESHOLD),
        GateComponent("WF_OOS", wf_oos_ok(result), "walk-forward OOS criterion"),
        GateComponent(
            "enough_samples", bool(result.enough_samples), "OOS sample-size floor (ADR §8)"
        ),
        GateComponent(
            "cost_stress",
            bool(stress_ok),
            f"DSR/PSR/WF hold at cost_scale {COST_STRESS_SCALES}",
        ),
    )


def _align_family_matrix(evidences: Sequence[GateEvidence]) -> Matrix | None:
    """Stack members' per-obs OOS returns into a time-aligned (T, S) matrix, or None if unusable."""
    if len(evidences) < 2:
        return None
    arrays = [np.asarray(ev.oos_returns, dtype="float64") for ev in evidences]
    if len({a.size for a in arrays}) != 1:
        return None  # different OOS lengths ⇒ not time-aligned (cannot form CSCV blocks)
    stacked = np.column_stack(arrays)
    finite_rows = np.isfinite(stacked).all(axis=1)
    aligned: Matrix = stacked[finite_rows]
    if aligned.shape[0] < 0.5 * stacked.shape[0]:
        return None  # lost > 50% of rows to NaN alignment ⇒ untrustworthy
    return aligned


def _stressed_costs(cost: CostModel) -> tuple[CostModel, ...]:
    return tuple(cost.model_copy(update={"cost_scale": float(s)}) for s in COST_STRESS_SCALES)


def evaluate_family(
    members: Sequence[FamilyMember],
    *,
    ledger: TrialLedger,
    hwm: NTrialsHighWaterMark,
    label_horizon: int = 1,
) -> tuple[GateDecision, ...]:
    """The ALL-of bias/kill gate over a candidate FAMILY → one accept/kill verdict per member.

    Records EVERY evaluation's trial identity (main + cost-stress, all members) BEFORE reading the
    deflation count N through the high-water-mark (M18); a lone family (< MIN_FAMILY_SIZE) is
    structurally un-allocatable. Any failing component (per-member OR family) KILLS the member.
    """
    if len(members) < MIN_FAMILY_SIZE:
        reason = f"family size {len(members)} < required {MIN_FAMILY_SIZE} (lone candidate)"
        comp = GateComponent("family_size", False, reason)
        return tuple(
            GateDecision(m.result.spec_hash, False, (comp,), 0, (reason,)) for m in members
        )

    # Phase 0 — record every gate evaluation's identity BEFORE N is read (M18 over-count is safe).
    for m in members:
        for cost in (m.cost, *_stressed_costs(m.cost)):
            ledger.record(
                STRATEGY_KIND,
                m.strategy.spec.name,
                eval_trial_params(m.strategy.spec, cost, m.folds),
            )
    n_trials = hwm.checked_n_trials(ledger.n_trials())  # may raise HighWaterMarkError (fail loud)

    # Phase 1 — recompute evidence (main + cost-stress) per member; record build failures.
    engine = BacktestEngine()
    built: dict[int, tuple[GateEvidence, tuple[GateEvidence, ...]]] = {}
    build_error: dict[int, str] = {}
    for i, m in enumerate(members):
        try:
            assert_purge_adequate(m.folds, m.strategy, label_horizon=label_horizon)
            main_ev = build_evidence(
                m.strategy, m.panel, cost=m.cost, folds=m.folds, result=m.result, n_trials=n_trials
            )
            stressed: list[GateEvidence] = []
            for cost in _stressed_costs(m.cost):
                stressed_result = engine.run(
                    m.strategy, m.panel, as_of=m.as_of, ledger=ledger, cost=cost, folds=m.folds
                )
                stressed.append(
                    build_evidence(
                        m.strategy,
                        m.panel,
                        cost=cost,
                        folds=m.folds,
                        result=stressed_result,
                        n_trials=n_trials,
                    )
                )
            built[i] = (main_ev, tuple(stressed))
        except BiasGateError as exc:
            build_error[i] = f"evidence build failed: {exc}"

    # Phase 2 — family judges (PBO, SPA) over the successfully-built members.
    built_order = [i for i in range(len(members)) if i in built]
    matrix = _align_family_matrix([built[i][0] for i in built_order])
    pbo = pbo_fraction(matrix) if matrix is not None else float("nan")
    spa = spa_pvalue(matrix) if matrix is not None else float("nan")
    pbo_comp = _passes_below("PBO_overfit", pbo, PBO_THRESHOLD)
    spa_comp = _passes_below("SPA_superiority", spa, SPA_ALPHA)
    family_sharpes = tuple(per_obs_sharpe(built[i][0].oos_returns) for i in built_order)

    # Phase 3 — per-member ALL-of verdict (the family PBO/SPA components are shared).
    decisions: list[GateDecision] = []
    for i, m in enumerate(members):
        if i in build_error:
            comps: tuple[GateComponent, ...] = (
                GateComponent("T1_consistency", False, build_error[i]),
                pbo_comp,
                spa_comp,
            )
        else:
            main_ev, stressed_evs = built[i]
            member_comps = judge_member(
                main_ev,
                m.result,
                n_trials,
                family_sharpes,
                stressed_evs,
                binding=m.binding,
                artifact=m.artifact,
            )
            comps = (*member_comps, pbo_comp, spa_comp)
        decisions.append(combine_member_verdict(m.result.spec_hash, comps, n_trials))
    return tuple(decisions)
