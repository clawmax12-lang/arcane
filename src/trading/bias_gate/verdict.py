"""The gate's frozen verdict types — a leaf module (no intra-package deps; avoids import cycles).

These bias-gate symbols (``allocated`` / ``passed`` / verdict) are banned in the backtest package
and legal ONLY in this package. ``GateComponent`` is one named pass/fail with a reason;
``GateDecision`` is the per-strategy accept/kill verdict. Re-exported from ``gate`` for either path.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GateComponent:
    """One named gate test outcome. ``passed`` False carries a human-readable ``reason``."""

    name: str
    passed: bool
    reason: str = ""


@dataclass(frozen=True, slots=True)
class GateDecision:
    """The frozen per-strategy verdict. ``allocated`` is the accept/kill call (ALL-of)."""

    spec_hash: str
    allocated: bool
    components: tuple[GateComponent, ...]
    n_trials: int
    reasons: tuple[str, ...]  # the failing component reasons (empty iff allocated)
