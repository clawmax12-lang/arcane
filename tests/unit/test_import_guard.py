"""Import-guard: NO LLM/agent code may be imported in the order submit path (PHI1).

This mechanically enforces CLAUDE.md §0 axiom 1 / §7: the deterministic risk and
executor packages must never import an LLM client or an agent module. If a future edit
adds such an import, this test fails in CI.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GUARDED_PACKAGES = ["src/trading/risk", "src/trading/executor", "src/trading/guards"]
FORBIDDEN_TOP = {"anthropic", "openai", "cohere", "litellm", "langchain", "ollama"}
FORBIDDEN_PREFIX = ("trading.agents", "trading.regime")


def _imported_modules(py: Path) -> Iterator[str]:
    tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module


def test_no_llm_imports_in_submit_path() -> None:
    offenders: list[str] = []
    for package in GUARDED_PACKAGES:
        for py in (REPO_ROOT / package).rglob("*.py"):
            for module in _imported_modules(py):
                top = module.split(".")[0]
                if top in FORBIDDEN_TOP or module.startswith(FORBIDDEN_PREFIX):
                    offenders.append(f"{py.relative_to(REPO_ROOT)}: imports {module}")
    assert not offenders, "LLM/agent imports found in the submit path: " + "; ".join(offenders)
