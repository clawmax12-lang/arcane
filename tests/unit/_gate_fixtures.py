"""Shared (non-collected) builders for the bias_gate tests — synthetic panels, strategies, results.

Underscore-prefixed so pytest does not collect it as a test module. Mirrors the Inc-4 integration
test's synthetic OHLCV builder so the gate's recompute is exercised against a REAL engine run.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from trading.backtest.cost_model import CostModel
from trading.backtest.engine import BacktestEngine, SymbolPanel
from trading.backtest.resolve import ResolvedStrategy, resolve_spec
from trading.backtest.statistics import BacktestResult
from trading.backtest.strategies import default_strategies
from trading.backtest.walk_forward import WalkForwardConfig
from trading.data.pit import AsOf
from trading.factors.registry import FactorRegistry, default_registry
from trading.factors.trial_ledger import TrialLedger

AS_OF = AsOf(datetime(2024, 1, 1, tzinfo=UTC))


def bars(n: int, *, seed: int, start: str = "2014-01-02", drift: float = 0.0003) -> pd.DataFrame:
    """One synthetic OHLCV frame on a tz-aware business-day index (Inc-4 integration idiom)."""
    rng = np.random.default_rng(seed)
    idx = pd.DatetimeIndex(pd.bdate_range(start, periods=n, tz="UTC"), name="ts")
    close = 100.0 * np.exp(np.cumsum(rng.normal(drift, 0.015, n)))
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


def panel(n: int = 1300, *, n_symbols: int = 2, seed0: int = 20) -> SymbolPanel:
    return SymbolPanel(bars={f"SYM{i}": bars(n, seed=seed0 + i) for i in range(n_symbols)})


def ledger(tmp_path: Path) -> TrialLedger:
    return TrialLedger(tmp_path / "trials.sqlite", clock=lambda: 1.0)


def registry(led: TrialLedger) -> FactorRegistry:
    return default_registry(led)


def resolved(name: str, reg: FactorRegistry) -> ResolvedStrategy:
    spec = next(s for s in default_strategies() if s.name == name)
    return resolve_spec(spec, reg)


def run_result(
    strategy: ResolvedStrategy,
    pnl_panel: SymbolPanel,
    led: TrialLedger,
    *,
    cost: CostModel | None = None,
    folds: WalkForwardConfig | None = None,
) -> BacktestResult:
    """Run the sealed Inc-4 engine to produce the verdict-free BacktestResult the gate consumes."""
    return BacktestEngine().run(
        strategy,
        pnl_panel,
        as_of=AS_OF,
        ledger=led,
        cost=cost or CostModel(),
        folds=folds or WalkForwardConfig(),
    )
