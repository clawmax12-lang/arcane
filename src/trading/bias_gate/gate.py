"""The gate's verdict types + (C8) the ALL-of composer — the FIRST accept/kill VERDICT in ARCANE.

``GateComponent`` is one named pass/fail with a reason; ``GateDecision`` is the frozen per-strategy
verdict (``allocated`` True ⇒ ALLOCATED, else KILLED). These bias-gate symbols (``allocated`` /
``passed`` / verdict) are banned in ``src/trading/backtest`` and legal ONLY here. The ALL-of
``evaluate_family`` composer is added in cluster C8; this module first pins the immutable verdict
shapes that the tripwire tests (A4) and the statistics judges consume.
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
