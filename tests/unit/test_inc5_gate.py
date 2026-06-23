"""C10 — the Increment-5 seal boundary + handoff invariant + leak-lint coverage of the new packages.

These pin the structural guarantees ``make inc5`` enforces: the Inc-4 backtest name-ban still scans
ONLY the backtest package (and the bias-gate verdict symbols stay OUT of it), the bias_gate package
contains NO order-submit call site (the deferred paper submit cannot leak in), and leak-lint is
clean over bias_gate + notify yet still has teeth.
"""

from __future__ import annotations

import ast
from pathlib import Path

from trading.data.leak_lint import scan_paths, scan_source

_SRC = Path(__file__).resolve().parents[2] / "src"
_BACKTEST = _SRC / "trading" / "backtest"
_BIAS_GATE = _SRC / "trading" / "bias_gate"
_NOTIFY = _SRC / "trading" / "notify"

#: The Inc-4 AST name-ban symbols — legal ONLY in bias_gate, banned in the backtest package.
_VERDICT_SYMBOLS = {
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


def _identifiers(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id.lower())
        elif isinstance(node, ast.Attribute):
            names.add(node.attr.lower())
        elif isinstance(node, ast.arg):
            names.add(node.arg.lower())
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            names.add(node.name.lower())
    return names


def test_backtest_package_still_free_of_verdict_symbols() -> None:
    """The seal is not weakened by the new legal symbols — backtest stays verdict-free."""
    for py in sorted(_BACKTEST.glob("*.py")):
        leaked = _identifiers(py) & _VERDICT_SYMBOLS
        assert not leaked, f"{py.name} leaked Inc-5 verdict symbols: {leaked}"


def test_bias_gate_actually_uses_the_verdict_vocabulary() -> None:
    """The boundary is REAL (not vacuous): the verdict symbols genuinely live in bias_gate."""
    gate_ids = _identifiers(_BIAS_GATE / "gate.py")
    assert {"allocated", "passed"} <= gate_ids


def test_bias_gate_has_no_order_submit_call_site() -> None:
    """The deferred paper submit cannot leak in: bias_gate never references the broker path."""
    banned = ("broker_paper", "execute_paper", "PaperBroker", ".submit(", "place_stock_order")
    for py in sorted(_BIAS_GATE.glob("*.py")):
        text = py.read_text(encoding="utf-8")
        for needle in banned:
            assert needle not in text, f"{py.name} references the submit path: {needle!r}"


def test_leak_lint_is_clean_over_bias_gate_and_notify() -> None:
    assert scan_paths([_BIAS_GATE, _NOTIFY]) == []


def test_leak_lint_still_has_teeth_on_a_planted_leak() -> None:
    leaky = "import pandas as pd\n\n\ndef f(s):\n    return s.shift(-1).sort_values()\n"
    rules = {v.rule for v in scan_source(leaky, "planted.py")}
    assert "SHIFT_NEG" in rules
    assert "SORT" in rules
