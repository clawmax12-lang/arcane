"""Tests for the AST leak-linter — Increment 2 STEP 8.

Two guarantees, both with teeth: (1) the real ``src/trading/data/`` tree is CLEAN, and (2) every
banned primitive is actually CAUGHT while the look-alikes that must NOT be flagged
(``unicodedata.normalize(form, s)``, ``schema.validate(df)``, ``np.floor(arr)``, the calendar's
own ``get_calendar``, the sanctioned daily-bar helpers, lowercase config sets) stay clean. AST,
never substring — that distinction is the whole point.
"""

from __future__ import annotations

from pathlib import Path

from trading.data.leak_lint import (
    Violation,
    main,
    scan_paths,
    scan_source,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "src" / "trading" / "data"


def _rules(src: str, path: str = "foo.py") -> set[str]:
    return {v.rule for v in scan_source(src, path)}


# --- the real data layer is clean (the actual guarantee the gate enforces) ---


def test_data_layer_is_clean() -> None:
    violations = scan_paths([DATA_DIR])
    assert violations == [], "leak-lint found banned primitives in data/:\n" + "\n".join(
        str(v) for v in violations
    )


# --- date/normalize/floor truncation: caught, with arity discrimination ---


def test_catches_timestamp_date_call() -> None:
    assert "DATE_TRUNC" in _rules("def f(ts):\n    return ts.date()\n")


def test_catches_timestamp_normalize_call() -> None:
    assert "DATE_TRUNC" in _rules("def f(ts):\n    return ts.normalize()\n")


def test_catches_floor_with_freq() -> None:
    assert "DATE_TRUNC" in _rules('def f(ts):\n    return ts.floor("D")\n')


def test_unicodedata_normalize_is_not_flagged() -> None:
    # 2 args -> not a tz-truncation; the substring ".normalize(" trap a grep linter would hit.
    assert "DATE_TRUNC" not in _rules('import unicodedata\nx = unicodedata.normalize("NFKC", s)\n')


def test_validate_call_is_not_flagged() -> None:
    # "validate(" contains the substring "date(" — AST sees the method name is "validate".
    assert _rules("def f(schema, df):\n    return schema.validate(df)\n") == set()


def test_np_floor_is_not_flagged() -> None:
    assert "DATE_TRUNC" not in _rules("import numpy as np\nx = np.floor(arr)\n")


def test_date_with_args_is_not_flagged() -> None:
    # only the 0-arg timestamp truncation is banned; a .date(x) call is something else.
    assert "DATE_TRUNC" not in _rules("def f(o):\n    return o.date(2024)\n")


def test_module_scope_annotation_without_value_is_ignored() -> None:
    # `x: list[str]` (AnnAssign with no value) must not crash the module-ticker scan.
    assert scan_source("x: list[str]\n", "foo.py") == []


# --- get_calendar: banned outside calendar.py, allowed inside it ---


def test_catches_get_calendar_outside_calendar() -> None:
    src = "import exchange_calendars as xc\nc = xc.get_calendar('XNYS')\n"
    assert "GET_CALENDAR" in _rules(src)


def test_catches_bare_get_calendar_call() -> None:
    assert "GET_CALENDAR" in _rules("c = get_calendar('XNYS')\n")


def test_catches_import_of_get_calendar_outside_calendar() -> None:
    assert "GET_CALENDAR" in _rules("from exchange_calendars import get_calendar\n")


def test_get_calendar_allowed_in_calendar_py() -> None:
    src = "import exchange_calendars as xc\nXNYS = xc.get_calendar('XNYS', side='left')\n"
    assert _rules(src, path="src/trading/data/calendar.py") == set()


# --- imputation (the design's "CRITICAL fabricated-data leak") ---


def test_catches_fillna() -> None:
    assert "IMPUTATION" in _rules("def f(s):\n    return s.fillna(0)\n")


def test_catches_ffill_and_bfill() -> None:
    assert "IMPUTATION" in _rules("def f(s):\n    return s.ffill()\n")
    assert "IMPUTATION" in _rules("def f(s):\n    return s.bfill()\n")


# --- whitelisted sanctioned helpers may use otherwise-banned primitives ---


def test_whitelisted_helper_may_normalize_in_calendar() -> None:
    src = "def session_label_for_daily_bar(ts):\n    return ts.normalize()\n"
    assert _rules(src, path="src/trading/data/calendar.py") == set()


def test_whitelisted_daily_bar_instant_helper_in_calendar() -> None:
    src = "def daily_bar_instant(s):\n    return s.floor('D')\n"
    assert _rules(src, path="src/trading/data/calendar.py") == set()


def test_whitelist_does_not_apply_outside_calendar() -> None:
    # SURV/LEAKLINT (sealing red-team): the whitelist is the calendar AUTHORITY, scoped to
    # calendar.py — a same-named helper in any other data/ module gets no pass.
    src = "def session_label_for_daily_bar(ts):\n    return ts.normalize()\n"
    assert "DATE_TRUNC" in _rules(src, path="src/trading/data/alpaca_loader.py")


def test_same_primitive_outside_whitelist_is_flagged() -> None:
    src = "def some_other_fn(ts):\n    return ts.normalize()\n"
    assert "DATE_TRUNC" in _rules(src)


# --- module-scope hardcoded ticker literals (survivorship smell) ---


def test_catches_module_scope_ticker_literals() -> None:
    assert "MODULE_TICKERS" in _rules('TICKERS = ["AAPL", "MSFT", "GOOG"]\n')


def test_catches_frozenset_ticker_literals() -> None:
    assert "MODULE_TICKERS" in _rules('U = frozenset({"AAPL", "MSFT", "GOOG"})\n')


def test_lowercase_string_set_is_not_a_ticker_list() -> None:
    # exactly the shape of leak_lint's own DATE_TRUNC_METHODS = {"date","normalize","floor"}
    assert "MODULE_TICKERS" not in _rules('METHODS = frozenset({"date", "normalize", "floor"})\n')


def test_function_scope_ticker_list_is_not_module_scope() -> None:
    src = 'def f():\n    xs = ["AAPL", "MSFT", "GOOG"]\n    return xs\n'
    assert "MODULE_TICKERS" not in _rules(src)


def test_two_tickers_below_threshold() -> None:
    assert "MODULE_TICKERS" not in _rules('U = ["AAPL", "MSFT"]\n')


# --- Violation formatting + CLI ---


def test_violation_str_is_actionable() -> None:
    v = Violation(path="foo.py", lineno=3, col=7, rule="DATE_TRUNC", message="banned .date()")
    s = str(v)
    assert "foo.py:3:7" in s
    assert "DATE_TRUNC" in s


def test_main_clean_returns_zero() -> None:
    assert main([str(DATA_DIR)]) == 0


def test_main_dirty_returns_one(tmp_path: Path) -> None:
    bad = tmp_path / "leaky.py"
    bad.write_text("def f(ts):\n    return ts.date()\n", encoding="utf-8")
    assert main([str(tmp_path)]) == 1


def test_main_defaults_to_data_package_when_no_args() -> None:
    assert main([]) == 0
