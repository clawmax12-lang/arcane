"""The allocator — survivors-only, within caps, regime advisory-only (Inc-7 PART C).

A PURE projection from gate verdicts to submit candidates. A candidate is emitted for a request ONLY
when ALL hold: (a) the DERIVED regime posture deems the strategy ELIGIBLE (a SUBTRACTIVE filter —
UNKNOWN is non-narrowing; it can DROP a survivor but never ADD one); (b) ``from_decision`` mints a
grant (a killed/forged ``GateDecision`` raises ``AllocationDenied`` ⇒ no candidate — the single
unforgeable chokepoint); (c) the grant binds to the SAME strategy as the target (confused-deputy).
The allocator NEVER builds an ``OrderIntent``, touches a cap, or calls the broker — sizing within
caps happens later in ``submit_allocated`` (the $1 cap ⇒ ``NoTrade``). Zero survivors ⇒ empty tuple
(ADR §0). A high-confidence regime can never manufacture or enlarge a trade.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from trading.bias_gate.verdict import GateDecision
from trading.executor.grant import AllocationDenied, AllocationGrant
from trading.executor.loop import SubmitCandidate
from trading.executor.sizing import HardQuote, TargetPosition
from trading.regime.labels import RegimeLabel
from trading.regime.posture import RegimePosture


@dataclass(frozen=True, slots=True)
class AllocationRequest:
    """One gate verdict + the deterministic target/quote + the strategy's declared regime set."""

    decision: GateDecision
    target: TargetPosition
    quote: HardQuote
    eligible_regimes: frozenset[RegimeLabel] = field(default_factory=frozenset)


def allocate(
    requests: Sequence[AllocationRequest],
    *,
    universe_artifact_hash: str,
    posture: RegimePosture,
) -> tuple[SubmitCandidate, ...]:
    """Project gate-ACCEPTED survivors into submit candidates (survivors-only, subtractive regime).

    Output is a SUBSET of the input (≤ one candidate per request) — the regime can only DROP a
    survivor, never add a non-survivor or enlarge a size, and a killed verdict is unrepresentable as
    a candidate (``from_decision`` raises). With the 4 edgeless toys every decision is killed, so
    the result is empty for every regime label.
    """
    candidates: list[SubmitCandidate] = []
    for req in requests:
        if not posture.is_eligible(req.eligible_regimes):
            continue  # regime SUBTRACTIVE filter (advisory, DERIVED) — never ADDs
        try:
            grant = AllocationGrant.from_decision(
                req.decision, universe_artifact_hash=universe_artifact_hash
            )
        except AllocationDenied:
            continue  # killed/forged decision → no grant → unrepresentable as a candidate
        if grant.spec_hash != req.target.spec_hash:
            continue  # confused-deputy guard (submit_allocated re-checks before the broker call)
        candidates.append(SubmitCandidate(grant, req.target, req.quote))
    return tuple(candidates)
