"""The regime POSTURE — a subtractive eligibility filter for the allocator (Inc-7 PART B).

The posture is the ONLY way the DERIVED regime label influences allocation, and it can ONLY
SUBTRACT: a strategy whose declared regime affinity excludes the current label is dropped from
CONSIDERATION (toward more conservative). It has NO field/method to ADD a strategy, raise a size,
mint a grant, or loosen a cap — so a high-confidence regime can never manufacture or enlarge a trade
(ADR §0 / §4.3). ``UNKNOWN`` (warmup) is NON-NARROWING (eligible-for-all) so a warmup pass's
zero-grant outcome is attributable to the GATE's KILL, not "regime not warmed up" — keeping the
null-result signal clean.
"""

from __future__ import annotations

from dataclasses import dataclass

from trading.regime.labels import RegimeLabel
from trading.regime.model import RegimeAssessment


@dataclass(frozen=True, slots=True)
class RegimePosture:
    """The current regime label as a subtractive eligibility filter (advisory, DERIVED-sourced)."""

    label: RegimeLabel

    def is_eligible(self, eligible_regimes: frozenset[RegimeLabel]) -> bool:
        """True iff a strategy with this declared affinity may be CONSIDERED in the current regime.

        * ``UNKNOWN`` (warmup) ⇒ always eligible (non-narrowing — the gate alone causes a warmup 0).
        * an EMPTY ``eligible_regimes`` ⇒ no affinity declared ⇒ eligible in EVERY regime (the toy
          default; the strategy is never narrowed by the regime).
        * otherwise eligible iff the current label is in the declared set (a SUBTRACTIVE filter).
        """
        if self.label is RegimeLabel.UNKNOWN:
            return True
        if not eligible_regimes:
            return True
        return self.label in eligible_regimes


def posture_from(assessment: RegimeAssessment) -> RegimePosture:
    """Derive the subtractive posture from the current advisory regime read (label only)."""
    return RegimePosture(assessment.label)
