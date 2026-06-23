"""The FINAL ``BacktestEngine`` — the structural look-ahead defense for the backtest layer.

``run()`` is ``@final``: it owns the ENTIRE look-ahead-sensitive sequence and there is no subclass
override point on it. The position->return JOIN is the one new attack surface (no Inc-3 gate covers
it), so the base pins it:

* ONE base-owned EXECUTION shift: ``executed = target_w.shift(1)`` (you observe the signal at the
  close of t, you can only trade at t+1). Combined with the factor layer's own ``shift(1)`` (signal
  availability), a decision from data <= t-1 earns ``r_contemp = close.pct_change()`` (the move
  realized at t's close), strictly after the decision. Both series are strictly trailing, so the
  causality property below sees only causal series.
* GUARD A (alignment) + GUARD B (no ``inf`` weight — an inf "max leverage" bet is the position-layer
  analogue of factor inf-laundering) on the author hook's output.
* A registry-derived warmup-adequacy floor (re-derived from the strategy's own factors, NOT an
  author constant — the registry-2 lesson) and a value-adequacy floor (>= 1 non-zero realized
  return), else ``FrameAdequacyError``.

Look-ahead is proven a TEST failure, not a review call: ``PositionView`` (the signal->position map)
and ``RealizedView`` (the position->return join) are ``PrefixComputation`` adapters the committed
engine tests run through ``data.prefix_stability`` on adversarial panels, alongside a perfect-
foresight off-by-one MUST-FAIL canary. ``run`` is COMPUTE-AND-REPORT ONLY: it records the trial,
computes statistics, and returns a verdict-free ``BacktestResult`` — it NEVER gates/approves/kills.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import final

import numpy as np
import pandas as pd

from trading.backtest.cost_model import CostModel
from trading.backtest.errors import BacktestContractError, FrameAdequacyError
from trading.backtest.ledger_integration import record_strategy_trial
from trading.backtest.resolve import ResolvedStrategy
from trading.backtest.spec import PositionMode
from trading.backtest.statistics import (
    BacktestResult,
    annualized_return,
    annualized_sharpe,
    average_turnover,
    fraction_positive,
    max_drawdown,
    total_return,
)
from trading.backtest.walk_forward import WalkForwardConfig, walk_forward_folds
from trading.data.pit import AsOf
from trading.factors.trial_ledger import TrialLedger

_REQUIRED_COLUMNS = frozenset({"open", "high", "low", "close", "volume"})
#: ADR §8 small-sample floor (bars) — REPORTED on the result, never used to gate.
MIN_OOS_BARS = 60


@dataclass(frozen=True, slots=True)
class SymbolPanel:
    """The market input: per-symbol canonical OHLCV frames sharing one session index.

    All symbols MUST share one tz-aware ``DatetimeIndex`` (cross-calendar alignment is deferred, so
    no calendar-misalignment leak is possible here). ``survivorship_unverified`` carries the non-PIT
    operator-universe provenance into the result (never silently a clean pass).
    """

    bars: Mapping[str, pd.DataFrame]
    survivorship_unverified: bool = field(default=True)


# --- pure, prefix-stable building blocks (the signal -> position -> return chain) ---


def factor_matrix(strategy: ResolvedStrategy, bars: pd.DataFrame) -> pd.DataFrame:
    """The matrix of each leg's factor signal (each already ``shift(1)``-published by the base)."""
    return pd.DataFrame(
        {rl.factor.id: rl.factor.compute(bars) for rl in strategy.legs}, index=bars.index
    )


def compose_positions(strategy: ResolvedStrategy, signals: pd.DataFrame) -> pd.Series:
    """Map factor signals to a bar-t target position (the author hook for ``Z_WEIGHTED_SUM``).

    composite = composite_scale * sum_i(signed_weight_i * z_i), then clipped to the position mode's
    range. Element-wise and same-bar, so it is prefix-stable for prefix-stable factor inputs.
    """
    legs = strategy.legs
    composite = signals[legs[0].factor.id] * legs[0].leg.signed_weight
    for rl in legs[1:]:
        composite = composite + signals[rl.factor.id] * rl.leg.signed_weight
    composite = composite * strategy.composite_scale
    if strategy.spec.position_mode is PositionMode.LONG_SHORT:
        return composite.clip(-1.0, 1.0)
    return composite.clip(lower=0.0, upper=1.0)


def _executed(target_w: pd.Series) -> pd.Series:
    """The position actually held: the ONE execution shift, warmup NaNs flattened to 0 (flat)."""
    shifted = target_w.shift(1)
    return shifted.where(shifted.notna(), 0.0)


def gross_returns(target_w: pd.Series, close: pd.Series) -> pd.Series:
    """Pre-cost realized returns: ``executed * close.pct_change()`` (the pinned causal join)."""
    return _executed(target_w) * close.astype("float64").pct_change()


class PositionView:
    """``PrefixComputation`` over the signal->position mapping (proves the mapping is causal)."""

    __slots__ = ("id", "_strategy")

    def __init__(self, strategy: ResolvedStrategy) -> None:
        self.id = f"{strategy.name}__positions"
        self._strategy = strategy

    def compute(self, df: pd.DataFrame) -> pd.Series:
        return compose_positions(self._strategy, factor_matrix(self._strategy, df))


class RealizedView:
    """``PrefixComputation`` over the position->return JOIN (proves the join is causal)."""

    __slots__ = ("id", "_strategy")

    def __init__(self, strategy: ResolvedStrategy) -> None:
        self.id = f"{strategy.name}__realized"
        self._strategy = strategy

    def compute(self, df: pd.DataFrame) -> pd.Series:
        target_w = compose_positions(self._strategy, factor_matrix(self._strategy, df))
        return gross_returns(target_w, df["close"])


def strategy_warmup(strategy: ResolvedStrategy) -> int:
    """Deepest factor pipeline: max(raw_lookback + z_window + 1) over the strategy's own factors."""
    return max(rl.factor.raw_lookback + rl.factor.z_window + 1 for rl in strategy.legs)


class BacktestEngine:
    """Final, structural backtest runner; the sole author hook is the ``compose_positions`` map."""

    @final
    def run(
        self,
        strategy: ResolvedStrategy,
        panel: SymbolPanel,
        *,
        as_of: AsOf,
        ledger: TrialLedger,
        cost: CostModel,
        folds: WalkForwardConfig,
    ) -> BacktestResult:
        if not isinstance(strategy, ResolvedStrategy):
            raise BacktestContractError("run requires a ResolvedStrategy (resolve the spec first)")
        if cost.cost_model_id != strategy.spec.cost_model_id:
            raise BacktestContractError(
                f"cost_model_id mismatch: spec {strategy.spec.cost_model_id!r} "
                f"vs cost {cost.cost_model_id!r}"
            )
        # STEP 1 — record the trial FIRST: no statistic is computed on an uncounted strategy (M18).
        record_strategy_trial(ledger, strategy.spec)

        sessions = self._assert_panel(panel, as_of)
        fold_list = walk_forward_folds(sessions, folds)
        if not fold_list:
            raise FrameAdequacyError("panel too short to form a walk-forward fold")
        warmup = strategy_warmup(strategy)
        first_test_pos = int(sessions.get_loc(fold_list[0].test[0]))
        if first_test_pos < warmup:
            raise FrameAdequacyError(
                f"only {first_test_pos} warmup bars before the first OOS fold; need >= {warmup}"
            )

        net_by_symbol: dict[str, pd.Series] = {}
        gross_by_symbol: dict[str, pd.Series] = {}
        turn_by_symbol: dict[str, pd.Series] = {}
        for sym, bars in panel.bars.items():
            target_w = compose_positions(strategy, factor_matrix(strategy, bars))
            self._assert_positions(target_w, bars.index, strategy.name)
            executed = _executed(target_w)
            close = bars["close"].astype("float64")
            gross_by_symbol[sym] = executed * close.pct_change()
            turn_by_symbol[sym] = cost.turnover(executed)
            net_by_symbol[sym] = gross_by_symbol[sym] - cost.per_bar_cost(executed)

        net = pd.DataFrame(net_by_symbol).mean(axis=1)
        gross = pd.DataFrame(gross_by_symbol).mean(axis=1)
        turnover = pd.DataFrame(turn_by_symbol).mean(axis=1)
        self._assert_value_adequacy(net)
        # net <= gross by construction (cost >= 0); assert it so a cost-sign bug fails closed.
        net_arr = net.to_numpy(dtype="float64", na_value=0.0)
        gross_arr = gross.to_numpy(dtype="float64", na_value=0.0)
        if bool((net_arr > gross_arr + 1e-12).any()):  # pragma: no cover - defensive (cost >= 0)
            raise BacktestContractError("net exceeded gross — cost applied with the wrong sign")

        per_fold = tuple(annualized_sharpe(net.loc[f.test]) for f in fold_list)
        oos_bars = sum(len(f.test) for f in fold_list)
        equity = np.cumprod(1.0 + net.to_numpy(dtype="float64", na_value=0.0))

        return BacktestResult(
            spec_hash=strategy.spec_hash,
            cost_model_id=cost.cost_model_id,
            n_bars=len(sessions),
            total_return=total_return(net),
            annualized_return=annualized_return(net),
            annualized_sharpe=annualized_sharpe(net),
            max_drawdown=max_drawdown(net),
            average_turnover=average_turnover(turnover),
            per_fold_oos_sharpe=per_fold,
            fraction_folds_positive=fraction_positive(per_fold),
            n_trials_at_eval=ledger.n_trials(),
            survivorship_biased=panel.survivorship_unverified,
            survivorship_unverified=panel.survivorship_unverified,
            enough_samples=oos_bars >= MIN_OOS_BARS,
            train_months=folds.train_months,
            test_months=folds.test_months,
            step_months=folds.step_months,
            anchored=True,
            equity_curve=tuple(float(x) for x in equity),
        )

    @staticmethod
    def _assert_panel(panel: SymbolPanel, as_of: AsOf) -> pd.DatetimeIndex:
        if not panel.bars:
            raise BacktestContractError("panel has no symbols")
        frames = list(panel.bars.values())
        ref = frames[0].index
        if not isinstance(ref, pd.DatetimeIndex) or ref.tz is None:
            raise BacktestContractError("panel bars must have a tz-aware DatetimeIndex")
        if not ref.is_monotonic_increasing or not ref.is_unique:
            raise BacktestContractError(
                "panel session index must be monotonic-increasing and unique"
            )
        if len(ref) > 0 and ref[-1] > as_of.ts:
            raise BacktestContractError("panel contains bars after the as_of PIT clock")
        for sym, bars in panel.bars.items():
            if not bars.index.equals(ref):
                raise BacktestContractError(
                    f"symbol {sym} index differs (cross-calendar alignment is deferred)"
                )
            if not set(bars.columns) >= _REQUIRED_COLUMNS:
                raise BacktestContractError(f"symbol {sym} is missing required OHLCV columns")
        return ref

    @staticmethod
    def _assert_positions(target_w: pd.Series, index: pd.Index, name: str) -> None:
        if (
            not isinstance(target_w, pd.Series)
            or len(target_w) != len(index)
            or not target_w.index.equals(index)
        ):
            raise BacktestContractError(
                f"strategy {name} positions are not aligned to the bar index"
            )
        if bool(np.isinf(target_w.to_numpy(dtype="float64", na_value=np.nan)).any()):
            raise BacktestContractError(f"strategy {name} produced a non-finite (inf) weight")

    @staticmethod
    def _assert_value_adequacy(net: pd.Series) -> None:
        arr = net.to_numpy(dtype="float64", na_value=np.nan)
        finite = arr[np.isfinite(arr)]
        if finite.size == 0 or bool(np.all(finite == 0.0)):
            raise FrameAdequacyError(
                "value-degenerate panel: no non-zero realized return (a vacuous false-green)"
            )
