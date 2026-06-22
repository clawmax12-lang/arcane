"""End-to-end backtest integration + leak-lint root — Increment 4 cluster 9.

Mirrors test_default_registry_validates_clean: the 4 default strategies resolve and run cleanly
through the @final engine over a multi-year panel (n_trials ends at 17 = 13 factors + 4 strategies),
exercising BOTH long-short and long-only position modes. Also pins the remaining fail-closed panel
contracts and confirms leak-lint (which `make inc4` runs over src/trading/backtest) has teeth on a
planted look-ahead / hardcoded-universe in a backtest-style source.
"""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from trading.backtest.cost_model import CostModel
from trading.backtest.engine import BacktestEngine, SymbolPanel
from trading.backtest.errors import BacktestContractError, FrameAdequacyError
from trading.backtest.resolve import resolve_spec
from trading.backtest.spec import Direction, FactorLeg, StrategySpec
from trading.backtest.strategies import default_strategies
from trading.backtest.walk_forward import WalkForwardConfig
from trading.data.leak_lint import scan_source
from trading.data.pit import AsOf
from trading.factors.registry import default_registry
from trading.factors.trial_ledger import TrialLedger

_AS_OF = AsOf(datetime(2024, 1, 1, tzinfo=UTC))


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


def _panel(n: int = 1300) -> SymbolPanel:
    return SymbolPanel(bars={f"SYM{i}": _bars(n, seed=20 + i) for i in range(2)})


def _ledger(tmp_path: object) -> TrialLedger:
    return TrialLedger(tmp_path / "trials.sqlite", clock=lambda: 1.0)  # type: ignore[operator]


# --- the 4 defaults run clean end-to-end (long-short AND long-only) ---


def test_all_four_default_strategies_run_clean(tmp_path: object) -> None:
    led = _ledger(tmp_path)
    reg = default_registry(led)  # 13 factors recorded
    panel = _panel(1300)
    engine = BacktestEngine()
    for spec in default_strategies():
        resolved = resolve_spec(spec, reg)
        result = engine.run(
            resolved, panel, as_of=_AS_OF, ledger=led, cost=CostModel(), folds=WalkForwardConfig()
        )
        assert result.spec_hash == spec.spec_hash
        assert result.survivorship_biased is True
        assert len(result.per_fold_oos_sharpe) >= 1
        # every reported stat is finite-or-NaN, never inf (the honest-hole contract)
        sharpe = result.annualized_sharpe
        assert (sharpe != sharpe) or np.isfinite(sharpe)  # NaN or finite, never inf
        assert np.isfinite(result.equity_curve[-1])
    assert led.n_trials() == 17  # 13 factors + 4 strategies, one shared ledger


# --- remaining fail-closed panel contracts ---


def test_empty_panel_fails_closed(tmp_path: object) -> None:
    reg = default_registry(_ledger(tmp_path))
    resolved = resolve_spec(default_strategies()[0], reg)
    with pytest.raises(BacktestContractError):
        BacktestEngine().run(
            resolved,
            SymbolPanel(bars={}),
            as_of=_AS_OF,
            ledger=_ledger(tmp_path),
            cost=CostModel(),
            folds=WalkForwardConfig(),
        )


def test_naive_index_panel_fails_closed(tmp_path: object) -> None:
    reg = default_registry(_ledger(tmp_path))
    resolved = resolve_spec(default_strategies()[0], reg)
    naive = _bars(400, seed=1)
    naive.index = naive.index.tz_localize(None)  # strip tz -> must be rejected
    with pytest.raises(BacktestContractError):
        BacktestEngine().run(
            resolved,
            SymbolPanel(bars={"X": naive}),
            as_of=_AS_OF,
            ledger=_ledger(tmp_path),
            cost=CostModel(),
            folds=WalkForwardConfig(),
        )


def test_missing_ohlcv_column_fails_closed(tmp_path: object) -> None:
    reg = default_registry(_ledger(tmp_path))
    resolved = resolve_spec(default_strategies()[0], reg)
    bars = _bars(400, seed=1).drop(columns=["volume"])
    with pytest.raises(BacktestContractError):
        BacktestEngine().run(
            resolved,
            SymbolPanel(bars={"X": bars}),
            as_of=_AS_OF,
            ledger=_ledger(tmp_path),
            cost=CostModel(),
            folds=WalkForwardConfig(),
        )


def test_warmup_inadequate_fails_closed(tmp_path: object) -> None:
    # a 1-month train window starts the first OOS fold ~21 bars in, far below the 169-bar pipeline
    # warmup of mom_126_skip21 -> FrameAdequacyError (the registry-derived warmup floor).
    reg = default_registry(_ledger(tmp_path))
    resolved = resolve_spec(default_strategies()[0], reg)
    tiny = WalkForwardConfig(train_months=1, test_months=1, step_months=1)
    with pytest.raises(FrameAdequacyError):
        BacktestEngine().run(
            resolved,
            _panel(400),
            as_of=_AS_OF,
            ledger=_ledger(tmp_path),
            cost=CostModel(),
            folds=tiny,
        )


def test_run_rejects_unknown_factor_via_resolution(tmp_path: object) -> None:
    from trading.backtest.errors import UnknownFactorError

    reg = default_registry(_ledger(tmp_path))
    bad = StrategySpec(
        name="bad", legs=(FactorLeg(factor_id="mom_999d", weight=1.0, direction=Direction.LONG),)
    )
    with pytest.raises(UnknownFactorError):
        resolve_spec(bad, reg)  # a phantom factor_id never reaches the engine


# --- leak-lint over the backtest root (make inc4) has teeth ---

_PLANTED_LEAKS = """
import pandas as pd
TICKERS = ["AAPL", "MSFT", "GOOG"]  # hardcoded survivorship-biased universe

def leak(s: pd.Series) -> pd.Series:
    a = s.shift(-1)            # future row pulled into the present
    b = s.resample("D").last()  # re-bucket across time
    c = s.sort_values()         # destroys time alignment
    return a + b + c
"""


def test_planted_leaks_in_backtest_style_source_are_flagged() -> None:
    rules = {v.rule for v in scan_source(_PLANTED_LEAKS, "backtest/planted.py")}
    assert {"SHIFT_NEG", "RESAMPLE", "SORT", "MODULE_TICKERS"} <= rules


def test_real_backtest_sources_are_leak_lint_clean() -> None:
    from pathlib import Path

    from trading.data.leak_lint import scan_paths

    pkg = Path(__file__).resolve().parents[2] / "src" / "trading" / "backtest"
    assert scan_paths([pkg]) == []  # the shipped backtest layer trips no banned primitive
