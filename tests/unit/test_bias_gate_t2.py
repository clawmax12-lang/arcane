"""C4 / tripwire A4 — the T2 survivorship test fails CLOSED while the universe is unverified.

ADR §8: T2 returns ``passed=False`` with a reason rather than a false pass while survivorship is
unverified (Polygon deferred ⇒ ALWAYS degraded this run). T2 passes ONLY when BOTH the result's
``survivorship_biased`` AND ``survivorship_unverified`` flags are ``False`` — there is no
default-True else-branch that could leak a clean pass.
"""

from __future__ import annotations

import pytest

from trading.backtest.statistics import BacktestResult
from trading.bias_gate.gate import GateComponent
from trading.bias_gate.tests_t2 import t2_survivorship


def _result(*, biased: bool, unverified: bool) -> BacktestResult:
    return BacktestResult(
        spec_hash="arcane-strategy-x",
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
        survivorship_biased=biased,
        survivorship_unverified=unverified,
        enough_samples=True,
        train_months=12,
        test_months=3,
        step_months=3,
        anchored=True,
        equity_curve=(1.0, 1.1),
    )


def test_t2_returns_a_gate_component() -> None:
    comp = t2_survivorship(_result(biased=False, unverified=False))
    assert isinstance(comp, GateComponent)
    assert comp.name == "T2_survivorship"


def test_t2_fails_closed_even_when_flags_claim_verified(monkeypatch: pytest.MonkeyPatch) -> None:
    # red-team FC-1: a forged ``survivorship_unverified=False`` must NOT grant a pass while no PIT
    # verifier is wired — T2 fails closed UNCONDITIONALLY (the flags are self-attested/forgeable).
    comp = t2_survivorship(_result(biased=False, unverified=False))
    assert comp.passed is False
    assert "survivorship" in comp.reason


def test_t2_passes_only_with_a_wired_pit_verifier_and_clean_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # the future-wired path: ONLY when a real PIT verifier exists AND both flags are False.
    import trading.bias_gate.tests_t2 as t2

    monkeypatch.setattr(t2, "_PIT_VERIFIER_WIRED", True)
    assert t2.t2_survivorship(_result(biased=False, unverified=False)).passed is True
    assert t2.t2_survivorship(_result(biased=False, unverified=True)).passed is False
    assert t2.t2_survivorship(_result(biased=True, unverified=False)).passed is False


@pytest.mark.parametrize(
    ("biased", "unverified"),
    [(True, True), (True, False), (False, True), (False, False)],
)
def test_t2_fails_closed_while_degraded(biased: bool, unverified: bool) -> None:
    comp = t2_survivorship(_result(biased=biased, unverified=unverified))
    assert comp.passed is False
    assert comp.reason  # carries a non-empty reason (auditability)


def test_gate_component_and_decision_are_frozen() -> None:
    from dataclasses import FrozenInstanceError

    from trading.bias_gate.gate import GateDecision

    comp = GateComponent(name="x", passed=True, reason="")
    with pytest.raises(FrozenInstanceError):
        comp.passed = False  # type: ignore[misc]
    decision = GateDecision(
        spec_hash="h", allocated=False, components=(comp,), n_trials=17, reasons=("nope",)
    )
    with pytest.raises(FrozenInstanceError):
        decision.allocated = True  # type: ignore[misc]
