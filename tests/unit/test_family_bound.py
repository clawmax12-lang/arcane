"""C6 — the family-size bound (skeptic A3): no irreversible n_trials inflation via an oversized fam.

``evaluate_family`` records every member × cost to the monotonic ``NTrialsHighWaterMark`` BEFORE
reading ``n_trials``; the high-water-mark NEVER decreases, so an oversized or duplicate-spec family
would PERMANENTLY inflate ``n_trials`` (an irreversible gate self-DoS). The bound rejects such a
family fail-closed BEFORE any ledger write — ZERO ledger writes, ZERO grants, all members KILLED.
"""

from __future__ import annotations

from pathlib import Path

import _gate_fixtures as fx

from trading.backtest.statistics import BacktestResult
from trading.bias_gate.gate import FamilyMember, evaluate_family
from trading.bias_gate.high_water_mark import NTrialsHighWaterMark
from trading.bias_gate.thresholds import MAX_FAMILY_SIZE


def _synthetic_result(spec_hash: str) -> BacktestResult:
    return BacktestResult(
        spec_hash=spec_hash,
        cost_model_id="conservative_v1",
        n_bars=300,
        total_return=0.1,
        annualized_return=0.1,
        annualized_sharpe=1.0,
        max_drawdown=-0.1,
        average_turnover=0.05,
        oos_total_return=0.05,
        oos_annualized_sharpe=0.8,
        oos_max_drawdown=-0.08,
        per_fold_oos_sharpe=(0.8, 0.9),
        fraction_folds_positive=1.0,
        n_trials_at_eval=17,
        survivorship_biased=True,
        survivorship_unverified=True,
        enough_samples=True,
        train_months=12,
        test_months=3,
        step_months=3,
        anchored=True,
        equity_curve=(1.0, 1.1),
    )


def _member(strat: object, panel: object, folds: object, spec_hash: str) -> FamilyMember:
    # The bound guard returns BEFORE Phase 0 (it reads only m.result.spec_hash), so the shared
    # strategy/panel/cost/folds are never exercised — only the synthetic result's hash matters.
    return FamilyMember(
        strategy=strat,  # type: ignore[arg-type]
        panel=panel,  # type: ignore[arg-type]
        cost=fx.CostModel(),
        folds=folds,  # type: ignore[arg-type]
        as_of=fx.AS_OF,
        result=_synthetic_result(spec_hash),
    )


def test_oversized_family_is_rejected_with_no_ledger_write(tmp_path: Path) -> None:
    led = fx.ledger(tmp_path)
    reg = fx.registry(led)
    n_before = led.n_trials()
    strat = fx.resolved("ts_momentum_blend", reg)
    panel = fx.panel(300)
    folds = fx.WalkForwardConfig(purge_bars=200)
    members = [
        _member(strat, panel, folds, f"arcane-strategy-{i}") for i in range(MAX_FAMILY_SIZE + 1)
    ]
    hwm = NTrialsHighWaterMark(tmp_path / "hwm.json")
    decisions = evaluate_family(members, ledger=led, hwm=hwm)
    assert len(decisions) == MAX_FAMILY_SIZE + 1
    assert all(d.allocated is False for d in decisions)
    assert all(any("MAX" in r or "family size" in r for r in d.reasons) for d in decisions)
    assert led.n_trials() == n_before  # ZERO ledger writes — n_trials NOT inflated (the A3 close)


def test_duplicate_spec_family_is_rejected_with_no_ledger_write(tmp_path: Path) -> None:
    led = fx.ledger(tmp_path)
    reg = fx.registry(led)
    n_before = led.n_trials()
    strat = fx.resolved("ts_momentum_blend", reg)
    panel = fx.panel(300)
    folds = fx.WalkForwardConfig(purge_bars=200)
    members = [_member(strat, panel, folds, "arcane-strategy-DUP") for _ in range(2)]  # same hash
    hwm = NTrialsHighWaterMark(tmp_path / "hwm.json")
    decisions = evaluate_family(members, ledger=led, hwm=hwm)
    assert len(decisions) == 2
    assert all(d.allocated is False for d in decisions)
    assert all(any("duplicate" in r for r in d.reasons) for d in decisions)
    assert led.n_trials() == n_before  # ZERO ledger writes
