"""``AllocationGrant`` — the unforgeable capability token to size+submit ONE strategy (Inc-6
PART C).

An order can be produced ONLY by presenting an ``AllocationGrant``, and a grant can be minted
ONLY by
``from_decision`` re-running the full ADR-§8 ALL-of over a ``bias_gate`` ``GateDecision``. The grant
does NOT trust the decision's ``allocated`` flag (that flag is hand-constructable, the red-team
type-confusion CRITICAL): it requires every frozen component PRESENT and PASSED, T2 among them,
and a
non-blank ``spec_hash``. A killed strategy can never produce a grant, so the killed submit path is
UNREPRESENTABLE rather than guarded-by-an-if.

TRUST BOUNDARY (red-team D3): this is a STRUCTURAL re-check of the gate's OWN in-process
``GateDecision`` — NOT a recompute of the verdicts from raw OOS evidence.
``GateComponent.passed`` is
as hand-buildable as the ``allocated`` bool, so a forged all-pass ``GateDecision`` would mint a
grant.
That is the accepted boundary because ``GateDecision`` is built ONLY inside ``gate.py`` and is NEVER
deserialized from disk/JSON (a committed test pins that) — lying inside trusted gate output is
equivalent to importing the broker directly. If ``GateDecision`` ever becomes persistable, this MUST
become a recompute-from-evidence. ``universe_artifact_hash`` is recorded provenance (the
verified PIT
hash T2 bound); the survivorship gate is T2 itself, upstream, and is not re-checked downstream (D4).
"""

from __future__ import annotations

import hashlib
import json

from trading.bias_gate.gate import FROZEN_COMPONENT_NAMES
from trading.bias_gate.verdict import GateDecision as BiasGateDecision
from trading.risk.errors import ArcaneError

_MINT = object()  # module-private sentinel — the only key that opens the constructor
_REQUIRED = frozenset(FROZEN_COMPONENT_NAMES)


class AllocationDenied(ArcaneError):
    """A grant was requested for a strategy the gate did not genuinely ALLOCATE (fail closed)."""


def _decision_id(d: BiasGateDecision) -> str:
    """Stable replay key over the decision identity (spec, every component verdict, n_trials)."""
    payload = json.dumps(
        {
            "spec_hash": d.spec_hash,
            "allocated": d.allocated,
            "n_trials": d.n_trials,
            "components": sorted((c.name, c.passed) for c in d.components),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return "arcane-grant-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


class AllocationGrant:
    """Immutable capability token. Construct ONLY via ``from_decision`` (the ``_MINT`` token
    gate)."""

    __slots__ = ("spec_hash", "universe_artifact_hash", "n_trials", "decision_id")

    spec_hash: str
    universe_artifact_hash: str
    n_trials: int
    decision_id: str

    def __init__(
        self,
        *,
        spec_hash: str,
        universe_artifact_hash: str,
        n_trials: int,
        decision_id: str,
        _token: object,
    ) -> None:
        if _token is not _MINT:
            raise AllocationDenied("AllocationGrant is constructible only via from_decision")
        object.__setattr__(self, "spec_hash", spec_hash)
        object.__setattr__(self, "universe_artifact_hash", universe_artifact_hash)
        object.__setattr__(self, "n_trials", n_trials)
        object.__setattr__(self, "decision_id", decision_id)

    def __setattr__(self, name: str, value: object) -> None:  # frozen
        raise AttributeError("AllocationGrant is immutable")

    def __repr__(self) -> str:
        return (
            f"AllocationGrant(spec_hash={self.spec_hash!r}, "
            f"universe_artifact_hash={self.universe_artifact_hash!r}, n_trials={self.n_trials})"
        )

    @classmethod
    def from_decision(cls, d: BiasGateDecision, *, universe_artifact_hash: str) -> AllocationGrant:
        """Mint a grant — re-running the ALL-of. Raises ``AllocationDenied`` if not genuinely
        allocated."""
        names = {c.name for c in d.components}
        genuinely_allocated = (
            d.allocated
            and bool(d.components)
            and all(c.passed for c in d.components)
            and names >= _REQUIRED
            and "T2_survivorship" in names
            and bool(d.spec_hash)
        )
        if not genuinely_allocated:
            raise AllocationDenied(
                f"not allocatable: {d.reasons or 'vacuous/incomplete components'} "
                f"(allocated={d.allocated}, n_components={len(d.components)})"
            )
        if not universe_artifact_hash:
            raise AllocationDenied("a grant requires a verified PIT universe artifact hash")
        return cls(
            spec_hash=d.spec_hash,
            universe_artifact_hash=universe_artifact_hash,
            n_trials=d.n_trials,
            decision_id=_decision_id(d),
            _token=_MINT,
        )
