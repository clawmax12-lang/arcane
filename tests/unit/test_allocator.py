"""C6 — the allocator: survivors-only, regime advisory-subtractive, within caps (Inc-7 PART C).

The allocator is a PURE projection from gate verdicts to submit candidates. It mints a grant ONLY
via the unforgeable ``AllocationGrant.from_decision`` chokepoint (a killed/forged verdict raises),
applies the regime posture as a SUBTRACTIVE filter (it can DROP a survivor but never ADD a
non-survivor or enlarge a size), and never builds an OrderIntent / touches a cap / calls the broker.
With the edgeless toys every verdict is killed ⇒ zero candidates for every regime label (ADR §0).
"""

from __future__ import annotations

from trading.allocator.allocate import AllocationRequest, allocate
from trading.backtest.spec import FactorLeg, StrategySpec
from trading.bias_gate.gate import FROZEN_COMPONENT_NAMES, GateComponent, GateDecision
from trading.executor.intent import Side
from trading.executor.invariants import AccountSnapshot
from trading.executor.sizing import HardQuote, NoTrade, TargetPosition, size_order
from trading.regime.labels import RegimeLabel
from trading.regime.posture import RegimePosture
from trading.risk.schema import RiskConfig

_SPEC = "arcane-strategy-x"
_HASH = "arcane-univ-x"


def _all_pass_decision(spec: str = _SPEC) -> GateDecision:
    comps = tuple(GateComponent(n, True, "") for n in FROZEN_COMPONENT_NAMES)
    return GateDecision(spec, True, comps, 17, ())


def _killed_decision(spec: str = _SPEC) -> GateDecision:
    # all pass EXCEPT the statistical DSR judge — the gate's verdict on a no-edge toy.
    comps = tuple(
        GateComponent(
            n, n != "DSR_deflated_sharpe", "no edge" if n == "DSR_deflated_sharpe" else ""
        )
        for n in FROZEN_COMPONENT_NAMES
    )
    return GateDecision(spec, False, comps, 17, ("no edge",))


def _req(
    decision: GateDecision,
    *,
    spec: str = _SPEC,
    eligible: frozenset[RegimeLabel] = frozenset(),
    price: float = 2.0,
) -> AllocationRequest:
    target = TargetPosition("strat", "AAPL", Side.BUY, spec_hash=spec)
    return AllocationRequest(decision, target, HardQuote("AAPL", price, 1000.0), eligible)


def _posture(label: RegimeLabel) -> RegimePosture:
    return RegimePosture(label)


# --- survivors-only ---


def test_genuine_survivor_yields_a_candidate() -> None:
    out = allocate(
        [_req(_all_pass_decision())],
        universe_artifact_hash=_HASH,
        posture=_posture(RegimeLabel.UNKNOWN),
    )
    assert len(out) == 1
    assert out[0].grant.spec_hash == _SPEC and out[0].grant.universe_artifact_hash == _HASH


def test_killed_decision_yields_no_candidate() -> None:
    out = allocate(
        [_req(_killed_decision())],
        universe_artifact_hash=_HASH,
        posture=_posture(RegimeLabel.UNKNOWN),
    )
    assert out == ()


def test_confused_deputy_target_spec_mismatch_drops_the_candidate() -> None:
    # the decision is for _SPEC but the target carries a DIFFERENT spec_hash -> dropped.
    req = AllocationRequest(
        _all_pass_decision(_SPEC),
        TargetPosition("strat", "AAPL", Side.BUY, spec_hash="arcane-strategy-OTHER"),
        HardQuote("AAPL", 2.0, 1000.0),
    )
    assert (
        allocate([req], universe_artifact_hash=_HASH, posture=_posture(RegimeLabel.UNKNOWN)) == ()
    )


# --- regime is advisory + SUBTRACTIVE only ---


def test_regime_cannot_manufacture_a_grant_for_a_killed_decision() -> None:
    # a confident regime + a killed verdict can NEVER produce a candidate (regime never ADDs).
    for label in RegimeLabel:
        out = allocate(
            [_req(_killed_decision())], universe_artifact_hash=_HASH, posture=_posture(label)
        )
        assert out == ()


def test_regime_filter_is_subtractive_and_unknown_is_non_narrowing() -> None:
    survivor = _req(_all_pass_decision(), eligible=frozenset({RegimeLabel.HIGH_VOL_UP}))
    # the current regime is OUTSIDE the strategy's affinity -> dropped (subtractive).
    assert (
        allocate(
            [survivor], universe_artifact_hash=_HASH, posture=_posture(RegimeLabel.LOW_VOL_DOWN)
        )
        == ()
    )
    # the current regime is IN the affinity -> allocated.
    assert (
        len(
            allocate(
                [survivor], universe_artifact_hash=_HASH, posture=_posture(RegimeLabel.HIGH_VOL_UP)
            )
        )
        == 1
    )
    # UNKNOWN warmup never narrows -> allocated.
    assert (
        len(
            allocate(
                [survivor], universe_artifact_hash=_HASH, posture=_posture(RegimeLabel.UNKNOWN)
            )
        )
        == 1
    )


def test_output_is_always_a_subset_of_input() -> None:
    reqs = [
        _req(_all_pass_decision("arcane-strategy-a"), spec="arcane-strategy-a"),
        _req(_killed_decision("arcane-strategy-b"), spec="arcane-strategy-b"),
        _req(
            _all_pass_decision("arcane-strategy-c"),
            spec="arcane-strategy-c",
            eligible=frozenset({RegimeLabel.LOW_VOL_UP}),
        ),
    ]
    for label in RegimeLabel:
        out = allocate(reqs, universe_artifact_hash=_HASH, posture=_posture(label))
        assert len(out) <= len(reqs)  # never ADDs
        assert all(c.grant.spec_hash in {"arcane-strategy-a", "arcane-strategy-c"} for c in out)


def test_null_result_is_regime_invariant_for_the_killed_toys() -> None:
    killed = [
        _req(_killed_decision(f"arcane-strategy-{i}"), spec=f"arcane-strategy-{i}")
        for i in range(4)
    ]
    for label in RegimeLabel:
        assert allocate(killed, universe_artifact_hash=_HASH, posture=_posture(label)) == ()


# --- allocation respects the immutable caps (the $1 cap -> NoTrade) ---


def test_allocated_candidate_sizes_to_notrade_at_the_dollar_cap() -> None:
    out = allocate(
        [_req(_all_pass_decision(), price=150.0)],
        universe_artifact_hash=_HASH,
        posture=_posture(RegimeLabel.UNKNOWN),
    )
    assert len(out) == 1
    cfg = RiskConfig(
        live_mode=False,
        per_trade_risk_usd=1.0,
        max_daily_loss_usd=5.0,
        equity_floor_usd=20.0,
        total_loss_abandon_usd=30.0,
        max_position_concentration_pct=30.0,
        max_consecutive_errors=5,
    )
    cand = out[0]
    sized = size_order(
        cand.grant, cand.target, cand.quote, AccountSnapshot(50.0, 0.0, 0.0, 1000.0, 1000.0), cfg
    )
    assert isinstance(
        sized, NoTrade
    )  # $1 cap buys 0 whole shares of a $150 stock — the expected null


# --- spec eligible_regimes folds into the hash only when declared (toys unchanged) ---


def _spec(*, eligible: tuple[RegimeLabel, ...] = ()) -> StrategySpec:
    return StrategySpec(
        name="affinity_test",
        legs=(FactorLeg(factor_id="mom_21d", weight=1.0),),
        eligible_regimes=eligible,
    )


def test_default_eligible_regimes_does_not_change_the_spec_hash() -> None:
    # a default (no-affinity) spec hashes IDENTICALLY to the pre-Inc-7 field set (toys are safe).
    assert _spec().spec_hash == _spec(eligible=()).spec_hash
    assert "eligible_regimes" not in _spec().canonical_params()


def test_declaring_an_affinity_changes_the_spec_hash() -> None:
    base = _spec().spec_hash
    narrowed = _spec(eligible=(RegimeLabel.LOW_VOL_UP,)).spec_hash
    assert narrowed != base  # an affinity edit forces a new hash + re-gate (ADR §7)
    assert "eligible_regimes" in _spec(eligible=(RegimeLabel.LOW_VOL_UP,)).canonical_params()


def test_affinity_is_order_independent_in_the_hash() -> None:
    a = _spec(eligible=(RegimeLabel.LOW_VOL_UP, RegimeLabel.HIGH_VOL_DOWN)).spec_hash
    b = _spec(eligible=(RegimeLabel.HIGH_VOL_DOWN, RegimeLabel.LOW_VOL_UP)).spec_hash
    assert a == b  # set semantics: a reorder is the SAME trial
