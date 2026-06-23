"""PHI1 teeth — the deterministic submit path imports NO LLM/agent module (Increment 6 PART C).

ADR §0 / CLAUDE.md PHI1: the hot-loop / submit path is deterministic Python; the LLM never submits,
sizes, or overrides. This AST scan over ``src/trading/executor`` + ``src/trading/guards`` fails
if any
module imports an LLM SDK or an agent package — a structural guarantee that a future edit
cannot route
a model into the path that touches the broker.
"""

from __future__ import annotations

import ast
from pathlib import Path

_ROOTS = (
    Path(__file__).resolve().parents[2] / "src" / "trading" / "executor",
    Path(__file__).resolve().parents[2] / "src" / "trading" / "guards",
)

# Any import whose top-level module matches one of these is a PHI1 violation in the submit path.
_BANNED_TOP = {"anthropic", "openai", "langchain", "llm", "agents"}
_BANNED_SUBSTR = ("anthropic", "openai", "llm", "agent")


def _module_names(tree: ast.AST) -> list[str]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.append(node.module)
    return names


def test_no_llm_or_agent_import_in_executor_or_guards() -> None:
    offenders: list[str] = []
    for root in _ROOTS:
        for py in root.glob("*.py"):
            tree = ast.parse(py.read_text(encoding="utf-8"))
            for mod in _module_names(tree):
                top = mod.split(".")[0]
                lowered = mod.lower()
                if top in _BANNED_TOP or any(s in lowered for s in _BANNED_SUBSTR):
                    offenders.append(f"{py.name}: imports {mod}")
    assert not offenders, f"PHI1 violation — LLM/agent import in the submit path: {offenders}"


def test_submit_path_modules_exist_and_are_scanned() -> None:
    # guard against a silently-empty scan (e.g. a moved package) hiding a real violation
    executor_files = {p.name for p in _ROOTS[0].glob("*.py")}
    assert {"submit.py", "sizing.py", "grant.py", "loop.py", "broker_paper.py"} <= executor_files
