"""C1 — pure-numpy normal CDF/PPF (NO scipy). erf CDF + Acklam PPF + Halley refinement.

These two functions are the statistical backbone of DSR/PSR/SPA. They must be accurate at the
tails (DSR's deflation hurdle lives at Phi^-1(1 - 1/N)) and must NEVER silently return +-inf on a
degenerate probability (that would fail OPEN into a passing gate) — the domain is fail-closed.
"""

from __future__ import annotations

import ast
import math
from pathlib import Path

import pytest

from trading.bias_gate._normal import norm_cdf, norm_ppf
from trading.bias_gate.errors import BiasGateError

_BIAS_GATE_DIR = Path(__file__).resolve().parents[2] / "src" / "trading" / "bias_gate"


def test_norm_cdf_reference_values() -> None:
    assert norm_cdf(0.0) == pytest.approx(0.5, abs=1e-12)
    assert norm_cdf(1.96) == pytest.approx(0.9750021048517796, abs=1e-9)
    assert norm_cdf(-1.96) == pytest.approx(1.0 - 0.9750021048517796, abs=1e-9)
    assert norm_cdf(1.6448536269514722) == pytest.approx(0.95, abs=1e-9)


def test_norm_ppf_reference_values() -> None:
    assert norm_ppf(0.5) == pytest.approx(0.0, abs=1e-12)
    assert norm_ppf(0.975) == pytest.approx(1.9599639845400545, abs=1e-9)
    assert norm_ppf(0.95) == pytest.approx(1.6448536269514722, abs=1e-9)
    assert norm_ppf(0.025) == pytest.approx(-1.9599639845400545, abs=1e-9)


def test_norm_ppf_is_accurate_at_the_deflation_tails() -> None:
    # DSR deflation evaluates Phi^-1(1 - 1/N) and Phi^-1(1 - 1/(N e)); both tight at large N.
    for n in (2, 17, 100, 10_000):
        p = 1.0 - 1.0 / n
        assert norm_cdf(norm_ppf(p)) == pytest.approx(p, abs=1e-10)
        pe = 1.0 - 1.0 / (n * math.e)
        assert norm_cdf(norm_ppf(pe)) == pytest.approx(pe, abs=1e-10)


def test_norm_ppf_round_trips_cdf() -> None:
    for x in (-3.5, -1.0, -0.2, 0.0, 0.3, 1.5, 3.0):
        assert norm_ppf(norm_cdf(x)) == pytest.approx(x, abs=1e-9)


def test_norm_ppf_is_strictly_monotonic() -> None:
    prev = norm_ppf(0.001)
    for p in (0.01, 0.1, 0.4, 0.5, 0.6, 0.9, 0.99, 0.999):
        cur = norm_ppf(p)
        assert cur > prev
        prev = cur


@pytest.mark.parametrize("bad", [0.0, 1.0, -0.1, 1.1, -1.0, 2.0, float("nan")])
def test_norm_ppf_fails_closed_outside_open_unit_interval(bad: float) -> None:
    # never return +-inf / nan silently — a degenerate probability is a fail-closed BiasGateError.
    with pytest.raises(BiasGateError):
        norm_ppf(bad)


def test_norm_cdf_handles_extreme_inputs_without_raising() -> None:
    assert norm_cdf(40.0) == pytest.approx(1.0, abs=1e-12)
    assert norm_cdf(-40.0) == pytest.approx(0.0, abs=1e-12)


def test_no_scipy_anywhere_in_bias_gate() -> None:
    """A bare `import scipy` would ImportError at runtime (scipy is absent by design)."""
    offenders: list[str] = []
    for py in sorted(_BIAS_GATE_DIR.rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(
                a.name == "scipy" or a.name.startswith("scipy.") for a in node.names
            ):
                offenders.append(f"{py.name}:{node.lineno} import scipy")
            if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "scipy":
                offenders.append(f"{py.name}:{node.lineno} from scipy")
    assert not offenders, f"scipy imported in bias_gate: {offenders}"
