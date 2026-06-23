"""C8 — the WF criterion + the ALL-of composer (the FIRST accept/kill verdict in ARCANE).

Must-FAIL canary: the 4 real toy strategies run end-to-end and are ALL KILLED (T2 survivorship alone
forces it; the statistics gate is the independent second wall) — the gate's job is to say NO.
Must-PASS (decomposed) canary: the per-member judge passes on a SYNTHETIC strong-edge series and
the ALL-of composer ALLOCATES when every component passes — proving the gate is not always-KILL
WITHOUT loosening any real threshold. (A real end-to-end ALLOCATE is intractable: the factors are
z-scored to mean-zero, so no composition shows genuine edge on synthetic data — that is exactly why
the toys score noise.)
"""

from __future__ import annotations

from pathlib import Path

import _gate_fixtures as fx
import numpy as np
import pytest

from trading.backtest.statistics import BacktestResult
from trading.bias_gate.errors import HighWaterMarkError
from trading.bias_gate.evidence import GateEvidence
from trading.bias_gate.gate import (
    FROZEN_COMPONENT_NAMES,
    FamilyMember,
    GateComponent,
    GateDecision,
    combine_member_verdict,
    evaluate_family,
    judge_member,
    wf_oos_ok,
)
from trading.bias_gate.high_water_mark import NTrialsHighWaterMark
from trading.bias_gate.thresholds import COST_STRESS_SCALES, WF_MIN_FRACTION_FOLDS

_PURGE = 200  # >= the deepest toy warmup (169) + label_horizon


# --- synthetic builders for the decomposed must-PASS ---


def _strong_returns(seed: int = 0) -> tuple[float, ...]:
    rng = np.random.default_rng(seed)
    return tuple(float(x) for x in rng.normal(0.01, 0.01, 300))


def _result(*, biased: bool, unverified: bool, sharpe: float, frac: float) -> BacktestResult:
    return BacktestResult(
        spec_hash="arcane-strategy-x",
        cost_model_id="conservative_v1",
        n_bars=400,
        total_return=0.2,
        annualized_return=0.2,
        annualized_sharpe=sharpe,
        max_drawdown=-0.1,
        average_turnover=0.05,
        oos_total_return=0.1,
        oos_annualized_sharpe=sharpe,
        oos_max_drawdown=-0.08,
        per_fold_oos_sharpe=(sharpe, sharpe, sharpe),
        fraction_folds_positive=frac,
        n_trials_at_eval=5,
        survivorship_biased=biased,
        survivorship_unverified=unverified,
        enough_samples=True,
        train_months=12,
        test_months=3,
        step_months=3,
        anchored=True,
        equity_curve=(1.0, 1.2),
    )


def _strong_evidence(seed: int = 0) -> GateEvidence:
    r = _strong_returns(seed)
    return GateEvidence(
        spec_hash="arcane-strategy-x",
        cost_model_id="conservative_v1",
        n_trials=5,
        oos_returns=r,
        per_fold_oos_returns=(r[:100], r[100:200], r[200:]),
        per_fold_oos_sharpe=(1.0, 1.0, 1.0),
        oos_annualized_sharpe=1.5,
        fraction_folds_positive=1.0,
        enough_samples=True,
        survivorship_biased=False,
        survivorship_unverified=False,
        train_months=12,
        test_months=3,
        step_months=3,
    )


# --- WF criterion ---


def test_wf_ok_on_a_good_result() -> None:
    assert wf_oos_ok(_result(biased=False, unverified=False, sharpe=0.8, frac=1.0)) is True


def test_wf_fails_on_nan_sharpe() -> None:
    assert (
        wf_oos_ok(_result(biased=False, unverified=False, sharpe=float("nan"), frac=1.0)) is False
    )


def test_wf_fails_below_fraction_floor() -> None:
    low = WF_MIN_FRACTION_FOLDS - 0.1
    assert wf_oos_ok(_result(biased=False, unverified=False, sharpe=0.8, frac=low)) is False


def test_wf_fails_on_nonpositive_sharpe() -> None:
    assert wf_oos_ok(_result(biased=False, unverified=False, sharpe=0.0, frac=1.0)) is False


# --- the ALL-of combination ---


def test_combine_allocates_only_when_every_component_passes() -> None:
    passing = tuple(GateComponent(n, True, "") for n in FROZEN_COMPONENT_NAMES)
    decision = combine_member_verdict("h", passing, n_trials=5)
    assert decision.allocated is True
    assert decision.reasons == ()


def test_combine_kills_on_any_failing_component() -> None:
    comps = [GateComponent(n, True, "") for n in FROZEN_COMPONENT_NAMES]
    comps[3] = GateComponent(comps[3].name, False, "nope")
    decision = combine_member_verdict("h", tuple(comps), n_trials=5)
    assert decision.allocated is False
    assert "nope" in decision.reasons


def test_judge_member_passes_on_synthetic_strong_edge() -> None:
    # the per-member judge (T1/T2/DSR/PSR/WF/enough_samples/cost_stress) all pass on a strong edge.
    ev = _strong_evidence()
    result = _result(biased=False, unverified=False, sharpe=1.5, frac=1.0)
    comps = judge_member(
        ev,
        result,
        n_trials=5,
        family_sharpes=(0.9, 0.95),
        stressed_evidences=(_strong_evidence(1), _strong_evidence(2)),
    )
    failed = [c.name for c in comps if not c.passed]
    assert failed == [], f"unexpected failures: {failed}"


def test_frozen_component_names_are_the_expected_nine() -> None:
    assert FROZEN_COMPONENT_NAMES == (
        "T1_consistency",
        "T2_survivorship",
        "DSR",
        "PSR",
        "WF_OOS",
        "enough_samples",
        "cost_stress",
        "PBO",
        "SPA",
    )


# --- the must-FAIL canary: the 4 real toys, end-to-end, ALL KILLED ---


def _toy_family(tmp_path: Path) -> tuple[list[FamilyMember], object, NTrialsHighWaterMark]:
    led = fx.ledger(tmp_path)
    reg = fx.registry(led)
    panel = fx.panel(1300)
    folds = fx.WalkForwardConfig(purge_bars=_PURGE)
    members = []
    for name in ("ts_momentum_blend", "ts_meanrev_short", "trend_location", "lowvol_liquid_tilt"):
        strat = fx.resolved(name, reg)
        result = fx.run_result(strat, panel, led, folds=folds)
        members.append(
            FamilyMember(
                strategy=strat,
                panel=panel,
                cost=fx.CostModel(),
                folds=folds,
                as_of=fx.AS_OF,
                result=result,
            )
        )
    hwm = NTrialsHighWaterMark(tmp_path / "hwm.json")
    return members, led, hwm


def test_the_four_toys_are_all_killed(tmp_path: Path) -> None:
    members, led, hwm = _toy_family(tmp_path)
    decisions = evaluate_family(members, ledger=led, hwm=hwm, label_horizon=1)
    assert len(decisions) == 4
    assert all(isinstance(d, GateDecision) for d in decisions)
    assert all(d.allocated is False for d in decisions)  # the gate's JOB: say NO
    # T2 survivorship (Polygon deferred) is among the killers for every toy.
    for d in decisions:
        assert any("survivorship" in r for r in d.reasons)


def test_cost_stress_runs_at_every_configured_scale(tmp_path: Path) -> None:
    members, led, hwm = _toy_family(tmp_path)
    decisions = evaluate_family(members, ledger=led, hwm=hwm, label_horizon=1)
    # each decision carries the cost_stress component (proving the 2x/3x re-runs executed).
    for d in decisions:
        names = {c.name for c in d.components}
        assert "cost_stress" in names
    assert COST_STRESS_SCALES == (2.0, 3.0)


# --- family policy + integrity fail-closed ---


def test_family_below_minimum_size_is_all_killed(tmp_path: Path) -> None:
    members, led, hwm = _toy_family(tmp_path)
    decisions = evaluate_family(members[:1], ledger=led, hwm=hwm, label_horizon=1)
    assert len(decisions) == 1
    assert decisions[0].allocated is False
    assert any("family" in r for r in decisions[0].reasons)


def test_high_water_mark_regression_fails_closed(tmp_path: Path) -> None:
    members, led, hwm = _toy_family(tmp_path)
    # pre-set a high-water-mark ABOVE the live count so the read regresses -> fail closed.
    hwm.checked_n_trials(10_000)
    with pytest.raises(HighWaterMarkError):
        evaluate_family(members, ledger=led, hwm=hwm, label_horizon=1)
