"""Typed, fail-closed error taxonomy for the backtest layer (all ``ArcaneError`` subclasses).

The backtest is a SIBLING layer to the data spine and the factor layer (it CONSUMES bar frames and
factor signals), so ``BacktestError`` roots at ``ArcaneError`` — the SAME root as
``data.errors.DataError`` and ``factors.errors.FactorError`` — and NOT under either of them, so a
backtest fault is never mis-bucketed by an ``except DataError`` / ``except FactorError`` handler.
Mirrors the proven taxonomy idiom: every failure is a specific, catchable exception; the default on
any uncertainty is to RAISE (fail closed) rather than return a partial/fabricated result.
"""

from __future__ import annotations

from trading.risk.errors import ArcaneError


class BacktestError(ArcaneError):
    """Base class for all backtest-layer errors."""


class StrategySpecError(BacktestError):
    """A ``StrategySpec`` is malformed (bad shape, duplicate/empty legs, un-hashable field)."""


class UnknownFactorError(StrategySpecError):
    """A ``StrategySpec`` references a ``factor_id`` not present in the registry (fail-closed at
    resolution — never a ``KeyError``, never a silently-shorter leg list)."""


class CostModelError(BacktestError):
    """The cost model was configured outside its conservative floor / contract (fail-closed)."""


class WalkForwardError(BacktestError):
    """The walk-forward split is ill-formed (bad window / purge / embargo, or an OOS overlap)."""


class BacktestContractError(BacktestError):
    """The engine's structural contract was violated — a position frame that is not a row-aligned
    finite (no ``inf``) frame, a broken pnl alignment, or an un-resolved spec reaching ``run``."""


class FrameAdequacyError(BacktestError):
    """The backtest panel is too short or value-degenerate to exercise the causality property
    non-vacuously (a too-short / all-zero-position panel is a false-green; fail closed)."""
