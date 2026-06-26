"""C6 — the Inc-8 BOUNDARY PROOF (PART D): the LLM packages are unreachable from the submit path.

This is the structural heart of the increment. ``trading.slowloop`` (agents/orchestrator/LLM client)
and ``trading.console`` (the Claude-backed two-way console) live OUTSIDE the 12 PHI1 submit-path
roots and legitimately import ``anthropic``-class transport — so the boundary is proven NOT by the
substring scan (``slowloop``/``console`` contain no banned substring) but by an EXPLICIT
package-identity import-graph walk: no acting-path module imports ``trading.slowloop`` or
``trading.console``, statically OR dynamically (with planted-import teeth). The allowed coupling is
one-way: ``console -> executor.kill_switch`` (escalate-only) and the agents/console reading
``state/`` files; the reverse is forbidden. The advisory regime is REPORT-ONLY — the acting path
never even names its artifact.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

# Reuse the canonical PHI1 roots + dynamic-surface scanner (the single source of truth).
from test_phi1_no_llm_in_submit_path import (
    _ROOT_NAMES,
    _ROOTS,
    _dynamic_offenders_in,
    _offenders_in,
)

_SRC = Path(__file__).resolve().parents[2] / "src" / "trading"

#: The new packages where LLMs live — OUTSIDE the submit path.
_LLM_PACKAGES = ("slowloop", "console")

#: Order-placement / broker surface no LLM package may import (console may import kill_switch only).
_BROKER_PREFIXES = (
    "trading.executor.submit",
    "trading.executor.broker_paper",
    "trading.executor.sizing",
    "trading.executor.grant",
)


def _import_targets(py: Path) -> list[str]:
    """The dotted module names a file imports (absolute ``import`` + ``from`` targets)."""
    tree = ast.parse(py.read_text(encoding="utf-8"))
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None and node.level == 0:
            out.append(node.module)
    return out


def _targets_an_llm_package(target: str) -> bool:
    parts = target.split(".")
    return len(parts) >= 2 and parts[0] == "trading" and parts[1] in _LLM_PACKAGES


def _llm_import_offenders(root: Path) -> list[str]:
    """Files under ``root`` that import ``trading.slowloop`` or ``trading.console`` (recursive)."""
    offenders: list[str] = []
    for py in root.rglob("*.py"):
        for target in _import_targets(py):
            if _targets_an_llm_package(target):
                offenders.append(f"{py}: imports {target}")
    return offenders


def _acting_world_files() -> Iterator[Path]:
    """Every ``src/trading`` module EXCEPT the LLM packages themselves (the whole acting world)."""
    for py in _SRC.rglob("*.py"):
        if py.relative_to(_SRC).parts[0] in _LLM_PACKAGES:
            continue
        yield py


# ----------------------------------------------------------------- root-creep guard


def test_phi1_roots_do_not_include_the_llm_packages() -> None:
    # The boundary is allow-by-omission: slowloop/console must stay OUT of the submit-path roots,
    # or their (legal) anthropic import would be pulled into the deterministic closure.
    assert "slowloop" not in _ROOT_NAMES
    assert "console" not in _ROOT_NAMES


# ----------------------------------------------------------------- the static boundary


def test_no_acting_module_imports_slowloop_or_console_statically() -> None:
    offenders: list[str] = []
    for py in _acting_world_files():
        for target in _import_targets(py):
            if _targets_an_llm_package(target):
                offenders.append(f"{py}: imports {target}")
    assert not offenders, f"acting-world module imports an LLM package: {offenders}"


def test_the_scan_has_teeth_a_planted_import_is_flagged(tmp_path: Path) -> None:
    root = tmp_path / "driver"
    root.mkdir(parents=True)
    (root / "_probe.py").write_text(
        "from trading.slowloop.orchestrator import run_agent\n", encoding="utf-8"
    )
    assert _llm_import_offenders(tmp_path), "must flag a planted import of trading.slowloop"
    (root / "_probe2.py").write_text("import trading.console.commands\n", encoding="utf-8")
    assert any("trading.console" in o for o in _llm_import_offenders(tmp_path))
    # a clean module is not flagged
    clean = tmp_path / "clean"
    clean.mkdir()
    (clean / "ok.py").write_text("from trading.risk.errors import ArcaneError\n", encoding="utf-8")
    assert not _llm_import_offenders(clean)


# ----------------------------------------------------------------- the dynamic boundary


def test_no_dynamic_load_surface_in_the_submit_path_could_reach_the_llm_packages() -> None:
    # There is NO importlib/__import__/exec/subprocess surface in the 12 roots, so a dynamic
    # ``import_module('trading.slowloop...')`` is structurally impossible (nothing to miss).
    offenders: list[str] = []
    for root in _ROOTS:
        offenders.extend(_dynamic_offenders_in(root))
    assert not offenders, f"dynamic-import surface in the submit path: {offenders}"


# ----------------------------------------------------------------- the existing PHI1 holds


def test_existing_phi1_holds_with_the_new_packages_present() -> None:
    # Even though slowloop/console import anthropic, the 12 roots still import no LLM/agent module.
    offenders: list[str] = []
    for root in _ROOTS:
        offenders.extend(_offenders_in(root))
    assert not offenders, f"a submit-path root imports an LLM/agent module: {offenders}"


# ----------------------------------------------------------------- no broker from the LLM packages


def test_no_llm_package_imports_a_broker_or_order_placement_symbol() -> None:
    offenders: list[str] = []
    for pkg in _LLM_PACKAGES:
        for py in (_SRC / pkg).rglob("*.py"):
            for target in _import_targets(py):
                top = target.split(".")[0]
                if top == "alpaca" or any(target.startswith(p) for p in _BROKER_PREFIXES):
                    offenders.append(f"{py}: imports {target}")
    assert not offenders, f"an LLM package imports a broker/order symbol: {offenders}"


def test_console_imports_only_kill_switch_from_executor() -> None:
    # The ONE allowed executor coupling: console -> executor.kill_switch (escalate-only). Any other
    # executor import from the console would widen its surface toward the acting path.
    bad: list[str] = []
    for py in (_SRC / "console").rglob("*.py"):
        for target in _import_targets(py):
            if target.startswith("trading.executor.") and target != "trading.executor.kill_switch":
                bad.append(f"{py}: imports {target}")
    assert not bad, f"console imports an executor module other than kill_switch: {bad}"


# ----------------------------------------------------------------- report-only proof


def test_acting_path_never_references_the_advisory_regime_artifact() -> None:
    # Model A (report-only): the acting path never reads regime_advisory.json and never names the
    # slowloop/console packages in its source. (The advisory is consumed ONLY by the console.)
    offenders: list[str] = []
    for py in _acting_world_files():
        text = py.read_text(encoding="utf-8")
        for needle in ("regime_advisory", "trading.slowloop", "trading.console"):
            if needle in text:
                offenders.append(f"{py}: mentions {needle!r}")
    assert not offenders, f"the acting path references an advisory/LLM surface: {offenders}"


# ----------------------------------------------------------------- secret-shape grep


def test_no_anthropic_key_shaped_literal_anywhere_in_src() -> None:
    # Defense in depth (the Telegram-token grep already covers src/ in test_notify_telegram.py).
    for py in _SRC.rglob("*.py"):
        assert "sk-ant-" not in py.read_text(encoding="utf-8"), f"anthropic key literal in {py}"
