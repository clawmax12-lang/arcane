"""C5 — the DERIVED-can't-gate boundary + the subtractive 'regime only subtracts' posture (PART B).

The load-bearing safety property of the regime classifier: a DERIVED regime label can NEVER gate an
order, size a position, or override the bias gate or a cap (§4.3). This is proven THREE ways:
  1. TYPE-DISJOINT (mypy --strict): passing a ``RegimeAssessment`` into ``size_order`` /
     ``submit_allocated`` / ``judge_member`` / ``evaluate_family`` is a type error — there is no
     regime parameter on any gate/sizing/cap signature.
  2. STRUCTURALLY UNIMPORTABLE: an AST scan asserts no module in ``bias_gate`` / ``executor`` /
     ``risk`` imports the ``regime`` package (it cannot even reference the type).
  3. RUNTIME fail-closed: ``require_gateable(reliability)`` raises (DERIVED is not gateable).
Plus the posture can ONLY SUBTRACT (UNKNOWN is non-narrowing; no add/size/grant surface).
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

from trading.data.errors import ReliabilityError
from trading.data.reliability import Reliability, require_gateable
from trading.regime.labels import PRODUCT_LABELS, RegimeLabel
from trading.regime.model import RegimeAssessment
from trading.regime.posture import RegimePosture, posture_from

_REPO = Path(__file__).resolve().parents[2]
_SRC = _REPO / "src"


# --- (1) TYPE-DISJOINT: a RegimeAssessment is not an accepted gate/sizing/cap input (mypy) ---


_MISUSE_SNIPPET = """
from trading.executor.sizing import size_order
from trading.executor.submit import submit_allocated
from trading.bias_gate.gate import judge_member, evaluate_family
from trading.regime.model import RegimeAssessment
from trading.regime.labels import RegimeLabel

a = RegimeAssessment(RegimeLabel.HIGH_VOL_UP, 1.0, "m")
size_order(a, a, a, a, a)                  # arg 1 is not an AllocationGrant
submit_allocated(a, a, a, a, a, a, a, a)   # arg 1 is not an AllocationGrant
judge_member(a, a, a, a, a)                # arg 1 is not GateEvidence
evaluate_family(a, ledger=a, hwm=a)        # arg 1 is not a Sequence[FamilyMember]
"""


def test_regime_assessment_is_a_mypy_type_error_as_a_gate_or_sizing_input(tmp_path: Path) -> None:
    snippet = tmp_path / "_regime_misuse.py"
    snippet.write_text(_MISUSE_SNIPPET, encoding="utf-8")
    env = {**os.environ, "MYPYPATH": str(_SRC)}
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--strict",
            "--follow-imports=silent",
            "--no-error-summary",
            "--no-incremental",
            str(snippet),
        ],
        cwd=str(_REPO),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert (
        proc.returncode != 0
    ), f"mypy unexpectedly accepted a regime as a gate input:\n{proc.stdout}"
    assert "RegimeAssessment" in proc.stdout and "incompatible type" in proc.stdout


# --- (2) STRUCTURALLY UNIMPORTABLE: no gate/sizing/cap module imports the regime package ---


def test_no_gate_sizing_or_cap_module_imports_the_regime_package() -> None:
    offenders: list[str] = []
    for pkg in ("bias_gate", "executor", "risk"):
        for py in (_SRC / "trading" / pkg).rglob("*.py"):
            tree = ast.parse(py.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                mods: list[str] = []
                if isinstance(node, ast.Import):
                    mods = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module is not None:
                    mods = [node.module]
                if any(m == "trading.regime" or m.startswith("trading.regime.") for m in mods):
                    offenders.append(f"{pkg}/{py.name}")
    assert not offenders, f"a gate/sizing/cap module imports the regime package: {offenders}"


# --- (3) RUNTIME fail-closed: a DERIVED regime reliability may not gate ---


def test_regime_reliability_is_derived_and_not_gateable() -> None:
    a = RegimeAssessment(RegimeLabel.HIGH_VOL_UP, 1.0, "m")
    assert a.reliability is Reliability.DERIVED
    with pytest.raises(ReliabilityError):
        require_gateable(a.reliability)  # §4.3: DERIVED may not gate a trading decision


def test_regime_assessment_reliability_is_read_only_no_field_to_forge() -> None:
    a = RegimeAssessment(RegimeLabel.HIGH_VOL_UP, 1.0, "m")
    with pytest.raises(AttributeError):
        a.reliability = Reliability.HARD  # type: ignore[misc]  # cannot forge it gateable
    with pytest.raises(AttributeError):
        a.label = RegimeLabel.LOW_VOL_DOWN  # type: ignore[misc]  # frozen


# --- (4) the posture can ONLY SUBTRACT; UNKNOWN is non-narrowing ---


def test_unknown_regime_is_non_narrowing() -> None:
    # warmup must NOT narrow the family — a warmup zero is the gate's KILL, not 'regime not warmed'.
    p = RegimePosture(RegimeLabel.UNKNOWN)
    assert p.is_eligible(frozenset({RegimeLabel.HIGH_VOL_UP})) is True
    assert p.is_eligible(frozenset()) is True


def test_no_declared_affinity_is_eligible_in_every_regime() -> None:
    for label in PRODUCT_LABELS:
        assert (
            RegimePosture(label).is_eligible(frozenset()) is True
        )  # the toy default (no affinity)


def test_declared_affinity_is_a_pure_subtractive_filter() -> None:
    p = RegimePosture(RegimeLabel.LOW_VOL_UP)
    assert p.is_eligible(frozenset({RegimeLabel.LOW_VOL_UP, RegimeLabel.MID_VOL_UP})) is True
    assert p.is_eligible(frozenset({RegimeLabel.HIGH_VOL_DOWN})) is False  # narrowed OUT


def test_posture_exposes_only_a_boolean_eligibility_no_add_or_size_surface() -> None:
    # structural: the posture's only public method is is_eligible -> bool. It has NO way to add a
    # strategy, raise a size, or mint a grant (a high-confidence regime cannot manufacture a trade).
    public = {m for m in dir(RegimePosture) if not m.startswith("_")}
    assert public == {"is_eligible", "label"}
    p = posture_from(RegimeAssessment(RegimeLabel.HIGH_VOL_UP, 1.0, "m"))
    assert isinstance(p.is_eligible(frozenset({RegimeLabel.HIGH_VOL_UP})), bool)
