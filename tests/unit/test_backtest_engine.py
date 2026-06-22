"""Tests for the @final BacktestEngine + the causality gate — Increment 4 cluster 8.

The position->return JOIN is the one new look-ahead surface (no Inc-3 gate covers it). These tests
are the engine's teeth:

* PositionView (signal->position) and RealizedView (position->return join) are prefix-stable for an
  honest strategy (reusing data.prefix_stability) — and MUST FAIL for a future-peeking mapping
  (signal.shift(-1) / full-sample normalization) and a forward-return join.
* the perfect-foresight off-by-one CANARY: a contemporaneous-foresight position earns ~flat under
  the correct execution lag but a blatant profit without it — proving the shift is load-bearing.
* GUARD-B (inf weight), net <= gross, cost_scale monotonicity, survivorship propagation, frame/value
  adequacy, the as_of PIT re-check, and that run rejects a raw unresolved StrategySpec.
"""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from trading.backtest.cost_model import CostModel
from trading.backtest.engine import (
    BacktestEngine,
    PositionView,
    RealizedView,
    SymbolPanel,
    compose_positions,
    factor_matrix,
    gross_returns,
)
from trading.backtest.errors import BacktestContractError, FrameAdequacyError
from trading.backtest.resolve import ResolvedStrategy, resolve_spec
from trading.backtest.statistics import BacktestResult
from trading.backtest.strategies import default_strategies
from trading.backtest.walk_forward import WalkForwardConfig
from trading.data.pit import AsOf
from trading.data.prefix_stability import (
    PrefixStabilityError,
    assert_prefix_stable,
    first_violation,
)
from trading.factors.registry import default_registry
from trading.factors.trial_ledger import TrialLedger


def _bars(n: int, *, seed: int, start: str = "2015-01-02") -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.DatetimeIndex(pd.bdate_range(start, periods=n, tz="UTC"), name="ts")
    close = 100.0 * np.exp(np.cumsum(rng.normal(0.0003, 0.015, n)))
    intraday = rng.uniform(0.003, 0.02, n)
    open_ = close * (1.0 + rng.normal(0.0, 0.004, n))
    high = np.maximum.reduce([close * (1.0 + intraday), open_, close])
    low = np.minimum.reduce([close * (1.0 - intraday), open_, close])
    vol = rng.integers(100_000, 5_000_000, n)
    return pd.DataFrame(
        {
            "open": pd.Series(open_, index=idx, dtype="Float64"),
            "high": pd.Series(high, index=idx, dtype="Float64"),
            "low": pd.Series(low, index=idx, dtype="Float64"),
            "close": pd.Series(close, index=idx, dtype="Float64"),
            "volume": pd.Series(vol, index=idx, dtype="Int64"),
        }
    )


def _panel(n: int, *, symbols: int = 2) -> SymbolPanel:
    return SymbolPanel(bars={f"SYM{i}": _bars(n, seed=10 + i) for i in range(symbols)})


def _ledger(tmp_path: object) -> TrialLedger:
    return TrialLedger(tmp_path / "trials.sqlite", clock=lambda: 1.0)  # type: ignore[operator]


def _resolved(tmp_path: object, which: int = 0) -> ResolvedStrategy:
    reg = default_registry(_ledger(tmp_path))
    return resolve_spec(default_strategies()[which], reg)


_AS_OF = AsOf(datetime(2024, 1, 1, tzinfo=UTC))


# --- causality: honest strategy is prefix-stable on BOTH views ---


def test_position_and_realized_views_are_prefix_stable(tmp_path: object) -> None:
    resolved = _resolved(tmp_path)
    bars = _bars(380, seed=3)
    assert_prefix_stable(PositionView(resolved), bars)  # signal -> position mapping is causal
    assert_prefix_stable(RealizedView(resolved), bars)  # position -> return join is causal


# --- causality MUST-FAIL: future-peeking mapping / forward-return join are CAUGHT ---


class _FutureSignalView:
    """Adversarial mapping that peeks one bar ahead (signal.shift(-1))."""

    def __init__(self, strategy: ResolvedStrategy) -> None:
        self.id = "future_signal"
        self._s = strategy

    def compute(self, df: pd.DataFrame) -> pd.Series:
        composed = compose_positions(self._s, factor_matrix(self._s, df))
        return composed.shift(-1)  # pulls a future row into t


class _FullSampleNormView:
    """Adversarial mapping that normalizes by the FULL-sample std (depends on all rows)."""

    def __init__(self, strategy: ResolvedStrategy) -> None:
        self.id = "full_sample_norm"
        self._s = strategy

    def compute(self, df: pd.DataFrame) -> pd.Series:
        composed = compose_positions(self._s, factor_matrix(self._s, df))
        return composed / composed.std()  # whole-sample stat -> not prefix-stable


class _ForwardReturnJoinView:
    """Adversarial JOIN that earns the FORWARD return (the off-by-one look-ahead)."""

    def __init__(self, strategy: ResolvedStrategy) -> None:
        self.id = "forward_return_join"
        self._s = strategy

    def compute(self, df: pd.DataFrame) -> pd.Series:
        target_w = compose_positions(self._s, factor_matrix(self._s, df))
        close = df["close"].astype("float64")
        return target_w.shift(1).where(target_w.shift(1).notna(), 0.0) * (
            close.shift(-1) / close - 1
        )


def test_future_signal_mapping_is_caught(tmp_path: object) -> None:
    with pytest.raises(PrefixStabilityError):
        assert_prefix_stable(_FutureSignalView(_resolved(tmp_path)), _bars(380, seed=3))


def test_full_sample_normalization_is_caught(tmp_path: object) -> None:
    assert first_violation(_FullSampleNormView(_resolved(tmp_path)), _bars(380, seed=3)) is not None


def test_forward_return_join_is_caught(tmp_path: object) -> None:
    with pytest.raises(PrefixStabilityError):
        assert_prefix_stable(_ForwardReturnJoinView(_resolved(tmp_path)), _bars(380, seed=3))


# --- the perfect-foresight off-by-one canary (the alignment proof) ---


def test_offbyone_canary_correct_lag_is_flat_offbyone_is_blatant() -> None:
    rng = np.random.default_rng(7)
    idx = pd.DatetimeIndex(pd.bdate_range("2016-01-04", periods=600, tz="UTC"), name="ts")
    r = rng.normal(0.0, 0.015, 600)
    close = pd.Series(100.0 * np.exp(np.cumsum(r)), index=idx, dtype="float64")
    contemp = close.pct_change()
    target_w = pd.Series(
        np.sign(contemp.to_numpy()), index=idx, dtype="float64"
    )  # contemp foresight

    correct = gross_returns(target_w, close)  # executed = target_w.shift(1) -> sign(r[t-1]) * r[t]
    leaky = (
        target_w.where(target_w.notna(), 0.0) * contemp
    )  # NO execution shift -> sign(r[t]) * r[t]

    correct_sum = float(correct.sum())
    leaky_sum = float(leaky.sum())
    assert leaky_sum > 1.0  # |return| accumulates to a blatant profit under the off-by-one
    assert leaky_sum > 5.0 * abs(correct_sum)  # the correct lag earns ~nothing from foresight


def test_per_bar_value_matches_hand_computed() -> None:
    idx = pd.DatetimeIndex(pd.bdate_range("2020-01-01", periods=3, tz="UTC"), name="ts")
    close = pd.Series([100.0, 110.0, 99.0], index=idx, dtype="float64")  # pct: NaN, +0.10, -0.10
    target_w = pd.Series([1.0, 1.0, -1.0], index=idx, dtype="float64")
    g = gross_returns(target_w, close)  # executed = [0, 1, 1]
    assert g.iloc[1] == pytest.approx(0.10)
    assert g.iloc[2] == pytest.approx(-0.10)


# --- GUARD-B + contract checks ---


def test_inf_weight_fails_closed() -> None:
    idx = pd.DatetimeIndex(pd.bdate_range("2020-01-01", periods=3, tz="UTC"), name="ts")
    bad = pd.Series([0.1, float("inf"), 0.2], index=idx, dtype="float64")
    with pytest.raises(BacktestContractError):
        BacktestEngine._assert_positions(bad, idx, "x")


def test_run_rejects_raw_unresolved_spec(tmp_path: object) -> None:
    spec = default_strategies()[0]
    with pytest.raises(BacktestContractError):
        BacktestEngine().run(
            spec,  # type: ignore[arg-type]
            _panel(400),
            as_of=_AS_OF,
            ledger=_ledger(tmp_path),
            cost=CostModel(),
            folds=WalkForwardConfig(),
        )


def test_cost_model_id_mismatch_fails_closed(tmp_path: object) -> None:
    resolved = _resolved(tmp_path)
    with pytest.raises(BacktestContractError):
        BacktestEngine().run(
            resolved,
            _panel(400),
            as_of=_AS_OF,
            ledger=_ledger(tmp_path),
            cost=CostModel(cost_model_id="other_v9"),
            folds=WalkForwardConfig(),
        )


def test_panel_with_bar_after_as_of_fails_closed(tmp_path: object) -> None:
    resolved = _resolved(tmp_path)
    panel = _panel(400)  # bars run into ~2016+; an early as_of must reject them
    early = AsOf(datetime(2015, 6, 1, tzinfo=UTC))
    with pytest.raises(BacktestContractError):
        BacktestEngine().run(
            resolved,
            panel,
            as_of=early,
            ledger=_ledger(tmp_path),
            cost=CostModel(),
            folds=WalkForwardConfig(),
        )


# --- run end-to-end: statistics-only result, trial recorded, adequacy ---


def test_run_produces_a_statistics_result_and_records_the_trial(tmp_path: object) -> None:
    led = _ledger(tmp_path)
    reg = default_registry(led)
    resolved = resolve_spec(default_strategies()[0], reg)
    assert led.n_trials() == 13
    result = BacktestEngine().run(
        resolved,
        _panel(1300),
        as_of=_AS_OF,
        ledger=led,
        cost=CostModel(),
        folds=WalkForwardConfig(),
    )
    assert isinstance(result, BacktestResult)
    assert led.n_trials() == 14  # 13 factors + this strategy
    assert result.n_trials_at_eval == 14
    assert result.spec_hash == resolved.spec_hash
    assert result.survivorship_biased is True and result.survivorship_unverified is True
    assert len(result.per_fold_oos_sharpe) >= 1
    assert result.n_bars == 1300
    assert np.isfinite(result.equity_curve[-1])


def test_net_is_never_greater_than_gross(tmp_path: object) -> None:
    resolved = _resolved(tmp_path, which=1)  # ts_meanrev_short flips fast -> lots of turnover/cost
    bars = _bars(1300, seed=5)
    target_w = compose_positions(resolved, factor_matrix(resolved, bars))
    from trading.backtest.engine import _executed

    executed = _executed(target_w)
    gross = executed * bars["close"].astype("float64").pct_change()
    net = gross - CostModel().per_bar_cost(executed)
    diff = (net - gross).to_numpy(dtype="float64", na_value=0.0)
    assert bool((diff <= 1e-12).all())  # cost only ever subtracts


def test_higher_cost_scale_lowers_net_return(tmp_path: object) -> None:
    led = _ledger(tmp_path)
    reg = default_registry(led)
    resolved = resolve_spec(default_strategies()[1], reg)  # turnover-heavy
    panel = _panel(1300)
    base = BacktestEngine().run(
        resolved, panel, as_of=_AS_OF, ledger=led, cost=CostModel(), folds=WalkForwardConfig()
    )
    stressed = BacktestEngine().run(
        resolved,
        panel,
        as_of=_AS_OF,
        ledger=led,
        cost=CostModel(cost_scale=3.0),
        folds=WalkForwardConfig(),
    )
    assert stressed.total_return <= base.total_return + 1e-12  # more cost -> no more return


def test_too_short_panel_raises_frame_adequacy(tmp_path: object) -> None:
    resolved = _resolved(tmp_path)
    with pytest.raises(FrameAdequacyError):
        BacktestEngine().run(
            resolved,
            _panel(120),
            as_of=_AS_OF,
            ledger=_ledger(tmp_path),
            cost=CostModel(),
            folds=WalkForwardConfig(),
        )


def test_value_degenerate_panel_raises(tmp_path: object) -> None:
    # a constant-price panel -> factors all-NaN/zero -> positions ~0 -> no realized return.
    idx = pd.DatetimeIndex(pd.bdate_range("2015-01-02", periods=1300, tz="UTC"), name="ts")
    flat = pd.DataFrame(
        {
            "open": pd.Series(100.0, index=idx, dtype="Float64"),
            "high": pd.Series(100.0, index=idx, dtype="Float64"),
            "low": pd.Series(100.0, index=idx, dtype="Float64"),
            "close": pd.Series(100.0, index=idx, dtype="Float64"),
            "volume": pd.Series(1_000_000, index=idx, dtype="Int64"),
        }
    )
    resolved = _resolved(tmp_path)
    with pytest.raises(FrameAdequacyError):
        BacktestEngine().run(
            resolved,
            SymbolPanel(bars={"SYM0": flat}),
            as_of=_AS_OF,
            ledger=_ledger(tmp_path),
            cost=CostModel(),
            folds=WalkForwardConfig(),
        )


def test_mismatched_symbol_calendars_fail_closed(tmp_path: object) -> None:
    resolved = _resolved(tmp_path)
    a = _bars(400, seed=1)
    b = _bars(400, seed=2, start="2015-02-02")  # different session index
    with pytest.raises(BacktestContractError):
        BacktestEngine().run(
            resolved,
            SymbolPanel(bars={"A": a, "B": b}),
            as_of=_AS_OF,
            ledger=_ledger(tmp_path),
            cost=CostModel(),
            folds=WalkForwardConfig(),
        )
