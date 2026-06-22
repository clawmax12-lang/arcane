"""Phase-2 resolution: bind a shape-validated ``StrategySpec`` to registered factors (fail-closed).

A ``StrategySpec`` is constructed registry-free (shape only). ``resolve_spec`` is the SEPARATE step
that binds each leg's ``factor_id`` to a real ``AlphaFactor`` from the registry, RAISING
``UnknownFactorError`` (a ``StrategySpecError``) on any unregistered id: never a bare ``KeyError``,
never a silently-shorter leg list. The engine consumes a ``ResolvedStrategy``, so a phantom
``factor_id`` structurally cannot reach ``BacktestEngine.run``. Each bound factor keeps
``factor.compute`` (with its mandatory ``shift(1)``) on the critical path.
"""

from __future__ import annotations

from dataclasses import dataclass

from trading.backtest.errors import UnknownFactorError
from trading.backtest.spec import CompositionRule, FactorLeg, StrategySpec
from trading.factors.base import AlphaFactor
from trading.factors.errors import FactorNotFoundError
from trading.factors.registry import FactorRegistry


@dataclass(frozen=True, slots=True)
class ResolvedLeg:
    """One leg bound to its concrete factor (signed weight carried by ``leg.signed_weight``)."""

    leg: FactorLeg
    factor: AlphaFactor


@dataclass(frozen=True, slots=True)
class ResolvedStrategy:
    """A ``StrategySpec`` with every leg bound to a registered ``AlphaFactor`` (engine input)."""

    spec: StrategySpec
    legs: tuple[ResolvedLeg, ...]

    @property
    def name(self) -> str:
        return self.spec.name

    @property
    def spec_hash(self) -> str:
        return self.spec.spec_hash

    @property
    def rule(self) -> CompositionRule:
        return self.spec.rule

    @property
    def composite_scale(self) -> float:
        return self.spec.composite_scale


def resolve_spec(spec: StrategySpec, registry: FactorRegistry) -> ResolvedStrategy:
    """Bind ``spec``'s legs to registered factors; fail closed on any unregistered ``factor_id``."""
    resolved: list[ResolvedLeg] = []
    for leg in spec.legs:
        try:
            factor = registry.get(leg.factor_id)
        except FactorNotFoundError as exc:
            raise UnknownFactorError(
                f"strategy {spec.name!r} references unregistered factor_id {leg.factor_id!r}"
            ) from exc
        resolved.append(ResolvedLeg(leg=leg, factor=factor))
    return ResolvedStrategy(spec=spec, legs=tuple(resolved))
