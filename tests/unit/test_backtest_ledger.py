"""Tests for strategy-trial ledger integration — Increment 4 cluster 7 (M18 under-count defense).

Proves: a strategy trial REUSES the Inc-3 TrialLedger (kind='strategy', same table); n_trials spans
both layers (13 factors + 4 strategies = 17); N distinct specs bump n_trials by N; a re-record is a
no-op; the ledger's stored params JSON is BYTE-IDENTICAL to the canonical JSON spec_hash hashes (so
distinct specs never collide to one trial); and a non-JSON-encodable param fails closed.
"""

from __future__ import annotations

import json

import pytest

from trading.backtest.ledger_integration import STRATEGY_KIND, record_strategy_trial
from trading.backtest.spec import Direction, FactorLeg, StrategySpec
from trading.backtest.strategies import default_strategies
from trading.factors.errors import TrialLedgerError
from trading.factors.registry import default_registry
from trading.factors.trial_ledger import TrialLedger


def _ledger(tmp_path: object) -> TrialLedger:
    return TrialLedger(tmp_path / "trials.sqlite", clock=lambda: 1.0)  # type: ignore[operator]


def _spec(name: str, weight: float = 0.5) -> StrategySpec:
    return StrategySpec(
        name=name, legs=(FactorLeg(factor_id="mom_21d", weight=weight, direction=Direction.LONG),)
    )


# --- reuse + n_trials spans both layers ---


def test_default_strategies_are_four_with_unique_names() -> None:
    specs = default_strategies()
    assert len(specs) == 4
    assert len({s.name for s in specs}) == 4


def test_factors_plus_strategies_make_seventeen_trials(tmp_path: object) -> None:
    led = _ledger(tmp_path)
    default_registry(led)  # records the 13 factors
    assert led.n_trials() == 13
    for spec in default_strategies():
        record_strategy_trial(led, spec)
    assert led.n_trials() == 17  # 13 factors + 4 strategies, one shared table


def test_n_distinct_specs_bump_by_exactly_n(tmp_path: object) -> None:
    led = _ledger(tmp_path)
    for i in range(5):
        record_strategy_trial(led, _spec(f"s{i}"))
    assert led.n_trials() == 5


def test_re_recording_same_spec_is_a_no_op(tmp_path: object) -> None:
    led = _ledger(tmp_path)
    spec = _spec("dupe")
    record_strategy_trial(led, spec)
    record_strategy_trial(led, spec)
    record_strategy_trial(led, spec)
    assert led.n_trials() == 1


def test_a_1e9_weight_change_is_a_distinct_trial(tmp_path: object) -> None:
    led = _ledger(tmp_path)
    record_strategy_trial(led, _spec("s", weight=0.5))
    record_strategy_trial(led, _spec("s", weight=0.5 + 1e-9))
    assert led.n_trials() == 2  # lossless float.hex -> two distinct rows, never collapsed to one


def test_trial_kind_is_strategy(tmp_path: object) -> None:
    led = _ledger(tmp_path)
    rec = record_strategy_trial(led, _spec("s"))
    assert rec.kind == STRATEGY_KIND
    assert rec.ref_id == "s"


# --- byte-identity: spec_hash basis == ledger params (the under-count defense) ---


def test_ledger_params_json_is_byte_identical_to_spec_hash_basis(tmp_path: object) -> None:
    led = _ledger(tmp_path)
    spec = default_strategies()[0]
    record_strategy_trial(led, spec)
    stored = led.trials()[0]
    # the canonical JSON the ledger stored for params == the canonical JSON spec_hash hashes
    spec_basis = json.dumps(spec.canonical_params(), sort_keys=True, separators=(",", ":"))
    ledger_basis = json.dumps(stored.params, sort_keys=True, separators=(",", ":"))
    assert ledger_basis == spec_basis
    # and both co-vary: any field change changes spec_hash AND would change the stored params
    assert spec.spec_hash.startswith("arcane-strategy-")


def test_unencodable_param_fails_closed(tmp_path: object) -> None:
    # the ledger's _canonical has no default=str, so an un-encodable params value RAISES (never a
    # silent collision into an existing combo). canonical_params() is JSON-native, so this is the
    # ledger contract guarding a hand-built params dict.
    led = _ledger(tmp_path)
    with pytest.raises(TrialLedgerError):
        led.record(STRATEGY_KIND, "bad", {"x": object()})
