"""PHI1 teeth — the deterministic submit-path closure imports NO LLM/agent module (Inc-6 + Inc-7).

ADR §0 / CLAUDE.md PHI1: the hot loop / submit path is deterministic Python; the LLM never submits,
sizes, or overrides. This AST scan covers the FULL submit-path runtime closure — the acting packages
AND everything they reach at runtime (bias_gate/data/notify/backtest/factors/risk) AND the new Inc-7
packages (regime/allocator/driver/scheduler). The scan is RECURSIVE (``rglob``): a nested
``regime/llm/client.py`` one hop from the allocator cannot slip through (red-team A1). Any
LLM-advisory regime code lives in a SLOW-LOOP package OUTSIDE these roots, consumed via a sanitized
``regime.json`` file — never imported into the acting path (§4.3: DERIVED advises, never gates).
"""

from __future__ import annotations

import ast
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src" / "trading"

#: The full submit-path runtime closure — the acting packages plus everything they reach.
_ROOT_NAMES = (
    "executor",
    "guards",
    "bias_gate",
    "data",
    "notify",
    "backtest",
    "factors",
    "risk",
    "regime",
    "allocator",
    "driver",
    "scheduler",
)
_ROOTS = tuple(_SRC / name for name in _ROOT_NAMES)

# Any import whose top-level module matches one of these, or whose dotted name contains one of the
# substrings, is a PHI1 violation in the submit path.
_BANNED_TOP = {"anthropic", "openai", "langchain", "llm", "agents"}
_BANNED_SUBSTR = ("anthropic", "openai", "llm", "agent")

# Inc-7 red-team (defense-in-depth): the static-import scan above cannot see a DYNAMIC import. Ban
# the dynamic-import / exec / shell surface in the submit-path closure so a future LLM can never
# be loaded at runtime past the AST scan (e.g. ``importlib.import_module(...)``, ``__import__``,
# ``exec``/``eval``, ``subprocess``/``os.system``). No closure module uses any of these today.
_BANNED_DYNAMIC_MODULES = {"importlib", "runpy", "subprocess"}
_BANNED_DYNAMIC_CALLS = {"__import__", "exec", "eval"}


def _module_names(tree: ast.AST) -> list[str]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.append(node.module)
    return names


def _offenders_in(root: Path) -> list[str]:
    """Banned imports anywhere under ``root`` — RECURSIVE so nested subpackages are scanned too."""
    offenders: list[str] = []
    for py in root.rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for mod in _module_names(tree):
            top = mod.split(".")[0]
            lowered = mod.lower()
            if top in _BANNED_TOP or any(s in lowered for s in _BANNED_SUBSTR):
                offenders.append(f"{py}: imports {mod}")
    return offenders


def test_no_llm_or_agent_import_in_submit_path_closure() -> None:
    offenders: list[str] = []
    for root in _ROOTS:
        offenders.extend(_offenders_in(root))
    assert not offenders, f"PHI1 violation — LLM/agent import in the submit path: {offenders}"


def test_submit_path_roots_exist_and_are_scanned() -> None:
    # Guard against a silently-empty scan (a moved/renamed package) hiding a real violation.
    for root in _ROOTS:
        assert root.is_dir(), f"PHI1 root missing: {root}"
        assert any(root.rglob("*.py")), f"PHI1 root scanned no files: {root}"


def test_phi1_scan_is_recursive_and_catches_nested_llm_import(tmp_path: Path) -> None:
    # red-team A1: prove ``rglob`` has TEETH on a NESTED subpackage — a non-recursive ``glob`` would
    # miss ``regime/llm/_probe.py`` one hop down and pass green.
    nested = tmp_path / "regime" / "llm"
    nested.mkdir(parents=True)
    (nested / "_probe.py").write_text("from langchain.agents import Foo\n", encoding="utf-8")
    assert _offenders_in(tmp_path), "rglob must catch a banned import in a nested subpackage"
    clean = tmp_path / "clean" / "deep"
    clean.mkdir(parents=True)
    (clean / "ok.py").write_text("import numpy as np\n", encoding="utf-8")
    assert not _offenders_in(tmp_path / "clean")  # a clean nested tree has zero offenders


def test_executor_submit_modules_present() -> None:
    executor_files = {p.name for p in (_SRC / "executor").glob("*.py")}
    assert {"submit.py", "sizing.py", "grant.py", "loop.py", "broker_paper.py"} <= executor_files


def _dynamic_offenders_in(root: Path) -> list[str]:
    """Dynamic-import / exec / shell surface anywhere under ``root`` (recursive)."""
    offenders: list[str] = []
    for py in root.rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for mod in _module_names(tree):
            if mod.split(".")[0] in _BANNED_DYNAMIC_MODULES:
                offenders.append(f"{py}: imports {mod}")
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                if isinstance(fn, ast.Name) and fn.id in _BANNED_DYNAMIC_CALLS:
                    offenders.append(f"{py}: calls {fn.id}()")
                elif (
                    isinstance(fn, ast.Attribute)
                    and isinstance(fn.value, ast.Name)
                    and fn.value.id == "os"
                    and fn.attr == "system"
                ):
                    offenders.append(f"{py}: calls os.system()")
    return offenders


def test_no_dynamic_import_or_exec_surface_in_submit_path() -> None:
    # Inc-7 red-team: a dynamic import / exec / shell could load an LLM past the static AST scan.
    # The submit-path closure must contain NONE of that surface (it does not today).
    offenders: list[str] = []
    for root in _ROOTS:
        offenders.extend(_dynamic_offenders_in(root))
    assert not offenders, f"PHI1 dynamic-import/exec surface in the submit path: {offenders}"


def test_dynamic_import_scan_catches_a_planted_importlib_llm_load(tmp_path: Path) -> None:
    # teeth: a dynamic ``importlib.import_module('anthropic')`` (invisible to the static scan) IS
    # caught by the dynamic-surface scan.
    nested = tmp_path / "driver"
    nested.mkdir(parents=True)
    (nested / "_probe.py").write_text(
        "import importlib\nm = importlib.import_module('anthropic')\n", encoding="utf-8"
    )
    assert _dynamic_offenders_in(tmp_path), "must catch a dynamic importlib LLM load"
    # __import__ / exec are caught too
    (nested / "_probe2.py").write_text("x = __import__('openai')\nexec('1')\n", encoding="utf-8")
    found = _dynamic_offenders_in(tmp_path)
    assert any("__import__" in o for o in found) and any("exec" in o for o in found)
