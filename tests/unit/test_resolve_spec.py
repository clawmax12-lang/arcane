"""Tests for resolve_spec + FactorRegistry.get — Increment 4 cluster 3 (fail-closed binding).

Proves: a valid spec binds every leg to its concrete AlphaFactor (factor.compute stays on the path);
an unregistered factor_id RAISES UnknownFactorError (a StrategySpecError), never a bare KeyError and
never a silently-shorter leg list; and FactorRegistry.get fails closed with
FactorNotFoundError on a miss.
"""

from __future__ import annotations

import pytest

from trading.backtest.errors import StrategySpecError, UnknownFactorError
from trading.backtest.resolve import ResolvedStrategy, resolve_spec
from trading.backtest.spec import Direction, FactorLeg, StrategySpec
from trading.factors.errors import FactorNotFoundError
from trading.factors.registry import FactorRegistry, default_registry
from trading.factors.trial_ledger import TrialLedger


def _ledger(tmp_path: object) -> TrialLedger:
    return TrialLedger(tmp_path / "trials.sqlite", clock=lambda: 1.0)  # type: ignore[operator]


def _spec(*legs: FactorLeg, name: str = "s") -> StrategySpec:
    return StrategySpec(name=name, legs=legs)


# --- FactorRegistry.get: fail-closed lookup ---


def test_registry_get_returns_registered_factor(tmp_path: object) -> None:
    reg = default_registry(_ledger(tmp_path))
    f = reg.get("mom_21d")
    assert f.id == "mom_21d"


def test_registry_get_raises_factor_not_found_not_keyerror() -> None:
    reg = FactorRegistry()
    with pytest.raises(FactorNotFoundError):
        reg.get("mom_999d")
    # specifically NOT a bare KeyError (the typed-error discipline)
    try:
        reg.get("nope")
    except KeyError:  # pragma: no cover - would be a regression
        pytest.fail("FactorRegistry.get leaked a bare KeyError")
    except FactorNotFoundError:
        pass


# --- resolve_spec: binds, fail-closed ---


def test_resolve_spec_binds_every_leg(tmp_path: object) -> None:
    reg = default_registry(_ledger(tmp_path))
    spec = _spec(
        FactorLeg(factor_id="mom_21d", weight=0.5, direction=Direction.LONG),
        FactorLeg(factor_id="reversal_5d", weight=0.5, direction=Direction.SHORT),
    )
    resolved = resolve_spec(spec, reg)
    assert isinstance(resolved, ResolvedStrategy)
    assert resolved.spec_hash == spec.spec_hash
    assert resolved.name == spec.name
    assert resolved.rule is spec.rule
    assert resolved.composite_scale == pytest.approx(spec.composite_scale)
    assert tuple(rl.factor.id for rl in resolved.legs) == ("mom_21d", "reversal_5d")
    # the bound factor's compute (with shift(1)) is on the path
    assert all(callable(rl.factor.compute) for rl in resolved.legs)
    # signed weight carried through
    assert resolved.legs[1].leg.signed_weight == pytest.approx(-0.5)


def test_resolve_spec_unknown_factor_raises_unknown_factor_error(tmp_path: object) -> None:
    reg = default_registry(_ledger(tmp_path))
    spec = _spec(FactorLeg(factor_id="mom_21d", weight=1.0, direction=Direction.LONG))
    # one good, one phantom -> must raise (never a silently-shorter leg list)
    bad = StrategySpec(
        name="bad",
        legs=(
            FactorLeg(factor_id="mom_21d", weight=0.5, direction=Direction.LONG),
            FactorLeg(factor_id="mom_999d", weight=0.5, direction=Direction.LONG),
        ),
    )
    resolve_spec(spec, reg)  # sanity: good spec resolves
    with pytest.raises(UnknownFactorError):
        resolve_spec(bad, reg)
    # and it is a StrategySpecError (a BacktestError), catchable at the spec layer
    with pytest.raises(StrategySpecError):
        resolve_spec(bad, reg)


def test_resolve_spec_does_not_leak_keyerror(tmp_path: object) -> None:
    reg = default_registry(_ledger(tmp_path))
    bad = StrategySpec(name="b", legs=(FactorLeg(factor_id="nope_42", weight=1.0),))
    try:
        resolve_spec(bad, reg)
    except KeyError:  # pragma: no cover - would be a regression
        pytest.fail("resolve_spec leaked a bare KeyError")
    except UnknownFactorError:
        pass
