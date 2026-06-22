"""AST leak-linter — bans look-ahead / fabricated-data primitives in the data layer (STEP 8).

A static guard that complements the runtime prefix-stability property: a handful of pandas /
timestamp primitives are look-ahead (or fabricated-data) foot-guns *regardless of how they are
used*, so they are forbidden in ``src/trading/data/`` by source-scan rather than by code-review
discipline (ADR-001 §7). Mirrors the broker's paper-only pin and the calendar's single
``get_calendar`` authority.

Banned, with the rule that flags them:

* ``DATE_TRUNC`` — ``.date()`` / ``.normalize()`` (0-arg) and ``.floor("freq")`` on a timestamp.
  These drop tz/time and silently re-bucket a bar into the wrong session = a ~1-day look-ahead.
* ``GET_CALENDAR`` — any ``get_calendar`` reference/import outside ``calendar.py``; the calendar
  module is the sole, ``side='left'`` session authority.
* ``IMPUTATION`` — ``.fillna()`` / ``.ffill()`` / ``.bfill()``; in a PIT layer a hole MUST stay a
  hole (ffill/zero-fill is the design's CRITICAL fabricated-volume leak, §8).
* ``MODULE_TICKERS`` — a module-scope collection of >=3 ticker-shaped string literals (a hardcoded,
  survivorship-biased universe; real membership must come from a content-hashed source).

It is AST, never substring: it does NOT trip on ``schema.validate(df)`` (method name is
``validate``, not ``date``), ``unicodedata.normalize(form, s)`` (2 args, not 0), ``np.floor(arr)``
(no string freq), or lowercase config sets like ``frozenset({"date", "normalize", "floor"})``.

The sanctioned daily-bar helpers ``session_label_for_daily_bar`` and ``daily_bar_instant`` are the
one place instant<->session conversion is allowed, so otherwise-banned ``DATE_TRUNC`` primitives
are permitted inside their bodies (the STATE.md whitelist).

Run as a gate step: ``python -m trading.data.leak_lint src/trading/data`` (exit 1 on any finding).
"""

from __future__ import annotations

import ast
import re
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

CALENDAR_FILE: Final[str] = "calendar.py"
WHITELIST_FUNCTIONS: Final[frozenset[str]] = frozenset(
    {"session_label_for_daily_bar", "daily_bar_instant"}
)
_ZERO_ARG_TRUNC: Final[frozenset[str]] = frozenset({"date", "normalize"})
_IMPUTATION_METHODS: Final[frozenset[str]] = frozenset({"fillna", "ffill", "bfill"})
_MATH_RECEIVERS: Final[frozenset[str]] = frozenset({"np", "numpy", "math"})
_MIN_TICKERS: Final[int] = 3
_TICKER_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")

_DATA_PACKAGE: Final[Path] = Path(__file__).resolve().parent


@dataclass(frozen=True, slots=True)
class Violation:
    """One banned primitive at one source location."""

    path: str
    lineno: int
    col: int
    rule: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.lineno}:{self.col} [{self.rule}] {self.message}"


class _Visitor(ast.NodeVisitor):
    """Walks one module, tracking the enclosing-function stack for the helper whitelist."""

    def __init__(self, path: str, basename: str) -> None:
        self.path = path
        self.basename = basename
        self.violations: list[Violation] = []
        self._fn_stack: list[str] = []

    # --- enclosing-function tracking (for the DATE_TRUNC whitelist) ---

    def _enter_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self._fn_stack.append(node.name)
        self.generic_visit(node)
        self._fn_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._enter_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._enter_function(node)

    def _in_whitelisted_helper(self) -> bool:
        return any(name in WHITELIST_FUNCTIONS for name in self._fn_stack)

    def _add(self, node: ast.AST, rule: str, message: str) -> None:
        lineno = getattr(node, "lineno", 0)
        col = getattr(node, "col_offset", 0)
        self.violations.append(Violation(self.path, lineno, col, rule, message))

    # --- rule checks ---

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Attribute):
            self._check_date_trunc(func, node)
            self._check_imputation(func, node)
        self.generic_visit(node)

    def _check_date_trunc(self, func: ast.Attribute, call: ast.Call) -> None:
        if self._in_whitelisted_helper():
            return
        attr = func.attr
        if attr in _ZERO_ARG_TRUNC:
            if not call.args and not call.keywords:
                self._add(
                    call,
                    "DATE_TRUNC",
                    f"banned .{attr}() drops tz/time -> wrong-session vintage (use calendar.py)",
                )
        elif attr == "floor":
            receiver = func.value
            if isinstance(receiver, ast.Name) and receiver.id in _MATH_RECEIVERS:
                return
            if (
                call.args
                and isinstance(call.args[0], ast.Constant)
                and isinstance(call.args[0].value, str)
            ):
                self._add(
                    call,
                    "DATE_TRUNC",
                    "banned .floor(freq) truncates a timestamp (use calendar.py)",
                )

    def _check_imputation(self, func: ast.Attribute, call: ast.Call) -> None:
        if func.attr in _IMPUTATION_METHODS:
            self._add(
                call,
                "IMPUTATION",
                f"banned .{func.attr}() fabricates data; a PIT hole must stay a hole (§8)",
            )

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr == "get_calendar" and self.basename != CALENDAR_FILE:
            self._add(node, "GET_CALENDAR", "get_calendar reference outside calendar.py")
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id == "get_calendar" and self.basename != CALENDAR_FILE:
            self._add(node, "GET_CALENDAR", "get_calendar reference outside calendar.py")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if self.basename != CALENDAR_FILE and any(a.name == "get_calendar" for a in node.names):
            self._add(node, "GET_CALENDAR", "imports get_calendar outside calendar.py")
        self.generic_visit(node)


def _string_collection_elts(value: ast.expr) -> list[ast.expr] | None:
    """Elements of a literal list/tuple/set, or of ``frozenset({...})`` / ``set({...})``."""
    if isinstance(value, ast.List | ast.Tuple | ast.Set):
        return list(value.elts)
    if (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Name)
        and value.func.id in {"frozenset", "set"}
        and value.args
        and isinstance(value.args[0], ast.List | ast.Tuple | ast.Set)
    ):
        return list(value.args[0].elts)
    return None


def _module_ticker_violations(tree: ast.Module, path: str) -> list[Violation]:
    """Flag MODULE-scope collections of >=3 ticker-shaped string literals (survivorship smell)."""
    out: list[Violation] = []
    for node in tree.body:  # module scope only — a function-local list is not a hardcoded universe
        if isinstance(node, ast.Assign):
            value: ast.expr | None = node.value
        elif isinstance(node, ast.AnnAssign):
            value = node.value
        else:
            continue
        if value is None:
            continue
        elts = _string_collection_elts(value)
        if elts is None:
            continue
        tickers = [
            e.value
            for e in elts
            if isinstance(e, ast.Constant)
            and isinstance(e.value, str)
            and _TICKER_RE.match(e.value)
        ]
        if len(tickers) >= _MIN_TICKERS:
            out.append(
                Violation(
                    path,
                    node.lineno,
                    node.col_offset,
                    "MODULE_TICKERS",
                    f"module-scope hardcoded ticker literals {tickers[:5]} "
                    "(survivorship smell; use a content-hashed universe source)",
                )
            )
    return out


def scan_source(source: str, path: str) -> list[Violation]:
    """Return every leak-lint violation in one module's source, sorted by location."""
    tree = ast.parse(source, filename=path)
    visitor = _Visitor(path, Path(path).name)
    visitor.visit(tree)
    out = list(visitor.violations)
    out.extend(_module_ticker_violations(tree, path))
    out.sort(key=lambda v: (v.lineno, v.col, v.rule))
    return out


def scan_file(path: str | Path) -> list[Violation]:
    p = Path(path)
    return scan_source(p.read_text(encoding="utf-8"), str(p))


def scan_paths(roots: Iterable[str | Path]) -> list[Violation]:
    """Scan files and/or directories (recursively over ``*.py``)."""
    out: list[Violation] = []
    for root in roots:
        p = Path(root)
        files = sorted(p.rglob("*.py")) if p.is_dir() else [p]
        for f in files:
            out.extend(scan_file(f))
    return out


def main(argv: Sequence[str] | None = None) -> int:
    args = list(argv) if argv is not None else sys.argv[1:]
    roots = args or [str(_DATA_PACKAGE)]
    violations = scan_paths(roots)
    for v in violations:
        print(str(v))
    if violations:
        print(f"leak-lint: FAIL — {len(violations)} violation(s)")
        return 1
    print(f"leak-lint: clean — {', '.join(roots)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
