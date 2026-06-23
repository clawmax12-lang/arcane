"""Tests for backtest statistics + the Inc-5 boundary name-ban — Increment 4 cluster 6.

Proves: each reduction returns NaN (never 0 or inf) on a degenerate window (empty / zero-variance /
total wipeout); the toy values match hand-computed results; BacktestResult is frozen and carries NO
accept/kill/verdict field; and an AST name-ban over the backtest package forbids any Inc-5 bias-gate
symbol (deflated/dsr/reality_check/pbo/psr/allocated/accept/kill/verdict), so the
compute-and-report-only boundary cannot be crossed by accident.
"""

from __future__ import annotations

import ast
import math
from pathlib import Path

import pandas as pd
import pytest

from trading.backtest.statistics import (
    BacktestResult,
    annualized_return,
    annualized_sharpe,
    average_turnover,
    fraction_positive,
    max_drawdown,
    total_return,
)


def _r(values: list[float]) -> pd.Series:
    idx = pd.date_range("2020-01-01", periods=len(values), freq="D", tz="UTC")
    return pd.Series(values, index=idx, dtype="float64")


# --- degenerate windows -> NaN, never 0/inf ---


def test_sharpe_nan_on_too_few_points() -> None:
    assert math.isnan(annualized_sharpe(_r([])))
    assert math.isnan(annualized_sharpe(_r([0.01])))


def test_sharpe_nan_on_zero_variance() -> None:
    s = annualized_sharpe(_r([0.01, 0.01, 0.01, 0.01]))
    assert math.isnan(s)  # std == 0 -> NaN, never inf


def test_sharpe_positive_for_a_steady_positive_drift() -> None:
    s = annualized_sharpe(_r([0.01, 0.012, 0.009, 0.011, 0.010]))
    assert s > 0 and math.isfinite(s)


def test_total_and_annualized_return() -> None:
    r = _r([0.1, 0.1])  # (1.1*1.1 - 1) = 0.21
    assert total_return(r) == pytest.approx(0.21)
    # CAGR = 1.21 ** (252/2) - 1 -> astronomically large but finite & positive
    assert annualized_return(r) > 0 and math.isfinite(annualized_return(r))


def test_total_return_nan_on_empty() -> None:
    assert math.isnan(total_return(_r([])))


def test_annualized_return_nan_on_total_wipeout() -> None:
    # a -100% bar wipes equity to 0 -> CAGR undefined -> NaN (never a complex/garbage number)
    assert math.isnan(annualized_return(_r([-1.0, 0.5])))


def test_max_drawdown_is_nonpositive_and_correct() -> None:
    # up 10%, down ~9.09% back to par, then flat -> peak 1.1, trough 1.0 -> dd = -1/11
    dd = max_drawdown(_r([0.1, -1.0 / 11.0, 0.0]))
    assert dd <= 0.0
    assert dd == pytest.approx(-1.0 / 11.0, abs=1e-9)


def test_max_drawdown_nan_on_empty() -> None:
    assert math.isnan(max_drawdown(_r([])))


def test_average_turnover() -> None:
    assert average_turnover(_r([0.0, 1.0, 0.5])) == pytest.approx(0.5)
    assert math.isnan(average_turnover(_r([])))


def test_fraction_positive() -> None:
    assert fraction_positive([1.0, -1.0, 2.0, 0.0]) == pytest.approx(0.5)
    assert math.isnan(fraction_positive([]))
    assert math.isnan(fraction_positive([float("nan")]))


def test_statistics_ignore_nan_bars() -> None:
    # a leading NaN (warmup) is masked, not treated as 0
    assert annualized_sharpe(_r([float("nan"), 0.01, 0.012, 0.009])) == annualized_sharpe(
        _r([0.01, 0.012, 0.009])
    )


# --- BacktestResult: frozen, statistics-only ---


def _result() -> BacktestResult:
    return BacktestResult(
        spec_hash="arcane-strategy-x",
        cost_model_id="conservative_v1",
        n_bars=100,
        total_return=0.05,
        annualized_return=0.12,
        annualized_sharpe=0.8,
        max_drawdown=-0.1,
        average_turnover=0.2,
        oos_total_return=0.02,
        oos_annualized_sharpe=0.5,
        oos_max_drawdown=-0.08,
        per_fold_oos_sharpe=(0.5, -0.2, 0.7),
        fraction_folds_positive=2 / 3,
        n_trials_at_eval=17,
        survivorship_biased=True,
        survivorship_unverified=True,
        enough_samples=True,
        train_months=12,
        test_months=3,
        step_months=3,
        anchored=True,
        equity_curve=(1.0, 1.01, 1.02),
    )


def test_backtest_result_is_frozen() -> None:
    import dataclasses

    res = _result()
    with pytest.raises(dataclasses.FrozenInstanceError):
        res.annualized_sharpe = 9.9  # type: ignore[misc]


def test_backtest_result_has_no_verdict_field() -> None:
    fields = set(BacktestResult.__dataclass_fields__)
    forbidden = {"passed", "accepted", "killed", "allocated", "verdict", "approve", "is_promising"}
    assert fields.isdisjoint(forbidden)
    assert _result().survivorship_biased is True  # provenance is carried, never stripped


def test_backtest_result_carries_explicit_oos_edge_stats() -> None:
    # ADR §0: the OOS edge metric must be unambiguous (not the train+OOS blended headline).
    fields = set(BacktestResult.__dataclass_fields__)
    assert {"oos_total_return", "oos_annualized_sharpe", "oos_max_drawdown"} <= fields
    assert _result().oos_annualized_sharpe == pytest.approx(0.5)


# --- AST name-ban: the Inc-5 boundary cannot be crossed in the backtest package ---

_FORBIDDEN_SYMBOLS = {
    "deflated",
    "dsr",
    "reality_check",
    "pbo",
    "psr",
    "allocated",
    "accept",
    "approve",
    "kill",
    "verdict",
    "passed",
}


def _identifiers(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id.lower())
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            names.add(node.name.lower())
        elif isinstance(node, ast.Attribute):
            names.add(node.attr.lower())
        elif isinstance(node, ast.arg | ast.keyword):
            argname = node.arg  # str for ast.arg; str|None for a ** keyword
            if argname is not None:
                names.add(argname.lower())
    return names


def test_backtest_package_has_no_inc5_verdict_symbols() -> None:
    pkg = Path(__file__).resolve().parents[2] / "src" / "trading" / "backtest"
    py_files = sorted(pkg.glob("*.py"))
    assert py_files, "backtest package not found"
    for path in py_files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        leaked = _identifiers(tree) & _FORBIDDEN_SYMBOLS
        assert not leaked, f"{path.name} leaks Inc-5 bias-gate symbols: {sorted(leaked)}"


def test_name_ban_has_teeth() -> None:
    # the scanner MUST catch a forbidden identifier (so the ban can't silently rot)
    tree = ast.parse("def accept(x):\n    verdict = x\n    return verdict\n")
    assert _identifiers(tree) & _FORBIDDEN_SYMBOLS == {"accept", "verdict"}
