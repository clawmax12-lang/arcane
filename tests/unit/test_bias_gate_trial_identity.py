"""C2 / tripwire A1 — the recorded trial identity folds in cost NUMERICS + WF geometry.

The Inc-4 engine records ``record_strategy_trial(ledger, spec)`` whose params carry only the
``cost_model_id`` LABEL and ZERO walk-forward geometry. A consumer that SWEEPS cost numbers (6 vs
18 bps under the same ``conservative_v1`` label) or fold geometry (12/3/3 vs 24/6/6) would collapse
distinct evaluations to ONE ``combo_hash`` → ``n_trials`` under-counts → DSR under-deflates (the M18
vector). The Inc-5 layer composes a richer identity (no Inc-4 edit) so distinct sweeps are distinct
ledger rows; an over-count is SAFE (it deflates MORE).
"""

from __future__ import annotations

from pathlib import Path

from trading.backtest.cost_model import CostModel
from trading.backtest.ledger_integration import record_strategy_trial
from trading.backtest.spec import FactorLeg, StrategySpec
from trading.backtest.walk_forward import WalkForwardConfig
from trading.bias_gate.trial_identity import cost_canonical, eval_trial_params, wf_canonical
from trading.factors.trial_ledger import TrialLedger


def _spec() -> StrategySpec:
    return StrategySpec(name="s1", legs=(FactorLeg(factor_id="mom_21d", weight=1.0),))


def _ledger(tmp_path: Path) -> TrialLedger:
    return TrialLedger(tmp_path / "trials.db")


def test_cost_canonical_covers_every_cost_model_field() -> None:
    # Reflective completeness: a new swept knob on CostModel must FAIL this until it is folded in.
    keys = set(cost_canonical(CostModel()).keys())
    assert keys == set(CostModel.model_fields.keys())


def test_wf_canonical_covers_every_walk_forward_field() -> None:
    keys = set(wf_canonical(WalkForwardConfig()).keys())
    assert keys == set(WalkForwardConfig.model_fields.keys())


def test_canonical_values_are_json_native_lossless() -> None:
    c = cost_canonical(CostModel(commission_bps=1.5))
    # floats serialized losslessly via float.hex() (str), ints/strs left native -> byte-stable JSON.
    assert c["commission_bps"] == (1.5).hex()
    assert isinstance(c["cost_model_id"], str)
    w = wf_canonical(WalkForwardConfig())
    assert w["train_months"] == 12 and isinstance(w["train_months"], int)
    assert w["embargo_frac"] == (0.01).hex()


def test_distinct_cost_numbers_under_same_label_are_distinct_trials(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    spec = _spec()
    wf = WalkForwardConfig()
    cheap = CostModel(commission_bps=1.0)  # same conservative_v1 label
    dear = CostModel(commission_bps=18.0)  # distinct numerics, SAME label
    ledger.record("strategy", spec.name, eval_trial_params(spec, cheap, wf))
    ledger.record("strategy", spec.name, eval_trial_params(spec, dear, wf))
    assert ledger.n_trials() == 2  # NOT collapsed to 1 by the shared label


def test_distinct_fold_geometry_is_a_distinct_trial(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    spec, cost = _spec(), CostModel()
    a = WalkForwardConfig(train_months=12, test_months=3, step_months=3)
    b = WalkForwardConfig(train_months=24, test_months=6, step_months=6)
    ledger.record("strategy", spec.name, eval_trial_params(spec, cost, a))
    ledger.record("strategy", spec.name, eval_trial_params(spec, cost, b))
    assert ledger.n_trials() == 2


def test_identical_config_is_idempotent(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    spec, cost, wf = _spec(), CostModel(), WalkForwardConfig()
    for _ in range(3):
        ledger.record("strategy", spec.name, eval_trial_params(spec, cost, wf))
    assert ledger.n_trials() == 1  # monotonic + idempotent (INSERT OR IGNORE)


def test_enriched_row_coexists_with_the_engine_spec_only_row(tmp_path: Path) -> None:
    # The Inc-4 engine's spec-only row and the Inc-5 enriched row are DISTINCT combo_hashes, so they
    # coexist (the +1 over-count). Over-counting is SAFE for M18 — it deflates the Sharpe MORE.
    ledger = _ledger(tmp_path)
    spec, cost, wf = _spec(), CostModel(), WalkForwardConfig()
    record_strategy_trial(ledger, spec)  # the engine's spec-only row
    ledger.record("strategy", spec.name, eval_trial_params(spec, cost, wf))  # the enriched row
    assert ledger.n_trials() == 2


def test_eval_trial_params_is_a_superset_of_spec_canonical(tmp_path: Path) -> None:
    spec, cost, wf = _spec(), CostModel(), WalkForwardConfig()
    params = eval_trial_params(spec, cost, wf)
    base = spec.canonical_params()
    assert all(params[k] == v for k, v in base.items())  # spec fields preserved
    assert params["cost"] == cost_canonical(cost)
    assert params["wf"] == wf_canonical(wf)
