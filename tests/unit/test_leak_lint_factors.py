"""Tests for the Increment-3 factor-layer leak-lint extension — SHIFT_NEG / CENTERED_ROLLING /
RESAMPLE / SORT + interpolate, and that ``src/trading/factors/`` scans clean.

Each new rule gets a positive (CAUGHT) case and a look-alike that must stay clean — most importantly
the base's REQUIRED positive ``.shift(1)`` and the trailing ``.rolling(21)`` stay clean. AST, never
substring (the whole point).
"""

from __future__ import annotations

from pathlib import Path

from trading.data.leak_lint import scan_paths, scan_source

REPO_ROOT = Path(__file__).resolve().parents[2]
FACTORS_DIR = REPO_ROOT / "src" / "trading" / "factors"


def _rules(src: str, path: str = "foo.py") -> set[str]:
    return {v.rule for v in scan_source(src, path)}


# --- the real factor layer is clean (the actual guarantee make inc3 enforces) ---


def test_factors_layer_is_clean() -> None:
    violations = scan_paths([FACTORS_DIR])
    assert violations == [], "leak-lint found banned primitives in factors/:\n" + "\n".join(
        str(v) for v in violations
    )


# --- SHIFT_NEG: negative shifts caught (UnaryOp + periods kw); positive shifts stay clean ---


def test_catches_negative_shift() -> None:
    assert "SHIFT_NEG" in _rules("def f(s):\n    return s.shift(-1)\n")


def test_catches_negative_shift_n() -> None:
    assert "SHIFT_NEG" in _rules("def f(s):\n    return s.shift(-5)\n")


def test_catches_negative_shift_periods_keyword() -> None:
    assert "SHIFT_NEG" in _rules("def f(s):\n    return s.shift(periods=-1)\n")


def test_positive_shift_one_is_not_flagged() -> None:
    # the base's MANDATORY shift(1) — must stay clean.
    assert "SHIFT_NEG" not in _rules("def f(s):\n    return s.shift(1)\n")


def test_positive_shift_lookback_is_not_flagged() -> None:
    # momentum/atr trailing lookbacks (.shift(21), .shift(1) for prevclose) — must stay clean.
    assert "SHIFT_NEG" not in _rules("def f(s):\n    return s.shift(21)\n")
    assert "SHIFT_NEG" not in _rules("def f(s):\n    return s.shift(periods=63)\n")


# --- CENTERED_ROLLING: center=True (or non-literal-False) caught; trailing rolling stays clean ---


def test_catches_centered_rolling_true() -> None:
    assert "CENTERED_ROLLING" in _rules("def f(s):\n    return s.rolling(3, center=True).mean()\n")


def test_catches_centered_rolling_variable() -> None:
    assert "CENTERED_ROLLING" in _rules("def f(s, c):\n    return s.rolling(3, center=c).mean()\n")


def test_trailing_rolling_is_not_flagged() -> None:
    src = "def f(s):\n    return s.rolling(21, min_periods=21).std(ddof=1)\n"
    assert "CENTERED_ROLLING" not in _rules(src)


def test_explicit_center_false_is_not_flagged() -> None:
    assert "CENTERED_ROLLING" not in _rules(
        "def f(s):\n    return s.rolling(3, center=False).sum()\n"
    )


# --- RESAMPLE / asfreq ---


def test_catches_resample() -> None:
    assert "RESAMPLE" in _rules('def f(s):\n    return s.resample("D").mean()\n')


def test_catches_asfreq() -> None:
    assert "RESAMPLE" in _rules('def f(s):\n    return s.asfreq("D")\n')


# --- SORT ---


def test_catches_sort_values() -> None:
    assert "SORT" in _rules('def f(s):\n    return s.sort_values("x")\n')


def test_catches_sort_index() -> None:
    assert "SORT" in _rules("def f(s):\n    return s.sort_index()\n")


# --- interpolate folded into IMPUTATION ---


def test_catches_interpolate() -> None:
    assert "IMPUTATION" in _rules("def f(s):\n    return s.interpolate()\n")


# --- SHIFT_NEG siblings: .diff(<neg>) / .pct_change(periods=<neg>) (red-team skeptic-1) ---


def test_catches_negative_diff() -> None:
    assert "SHIFT_NEG" in _rules("def f(s):\n    return s.diff(-1)\n")


def test_catches_negative_pct_change_keyword() -> None:
    assert "SHIFT_NEG" in _rules("def f(s):\n    return s.pct_change(periods=-1)\n")


def test_positive_diff_and_pct_change_are_not_flagged() -> None:
    assert "SHIFT_NEG" not in _rules("def f(s):\n    return s.diff()\n")
    assert "SHIFT_NEG" not in _rules("def f(s):\n    return s.pct_change(1)\n")


# --- DATE_TRUNC keyword form + dict-keyed tickers (red-team leaklint-3) ---


def test_catches_floor_freq_keyword() -> None:
    assert "DATE_TRUNC" in _rules('def f(ts):\n    return ts.floor(freq="D")\n')


def test_catches_dict_keyed_ticker_universe() -> None:
    assert "MODULE_TICKERS" in _rules('U = {"AAPL": 1, "MSFT": 2, "GOOG": 3}\n')


def test_lowercase_dict_is_not_a_ticker_universe() -> None:
    assert "MODULE_TICKERS" not in _rules('CFG = {"open": 1, "high": 2, "low": 3}\n')


# --- a representative clean factor body trips NOTHING (no false positives) ---


def test_clean_factor_idioms_are_not_flagged() -> None:
    src = (
        "import numpy as np\n"
        "def f(df):\n"
        "    close = df['close'].astype('float64')\n"
        "    _ = np.log(close.where(close > 0))\n"
        "    mean = close.rolling(21, min_periods=21).mean()\n"
        "    std = close.rolling(21, min_periods=21).std(ddof=1)\n"
        "    z = ((close - mean) / std).where(std > 0)\n"
        "    return z.clip(-3, 3).shift(1)\n"
    )
    assert _rules(src) == set()
