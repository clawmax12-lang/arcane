"""Reliability tiers (CLAUDE.md §4.3): only HARD/STRUCTURED data may gate a decision.

TEXTUAL (sanitized free text) and DERIVED (agent estimates) are evidence/advisory only.
STEP 1 provides the enum and the runtime fail-closed guard. The TYPE-level enforcement
(phantom-typed frames, so passing a TEXTUAL/DERIVED frame to a gate is a mypy error) is
added in STEP 5 by branding the fully-typed ``ImmutableFrame`` carrier — branding our own
class avoids depending on ``pandas-stubs`` (pandas is intentionally untyped here; data
correctness is enforced at runtime by the pandera schema + finiteness + quality gate).
"""

from __future__ import annotations

from enum import StrEnum

from trading.data.errors import ReliabilityError


class Reliability(StrEnum):
    HARD = "hard"  # prices, fills, balances — source of truth
    STRUCTURED = "structured"  # schema-validated events (filings, calendar)
    TEXTUAL = "textual"  # sanitized free text — evidence, never a command
    DERIVED = "derived"  # agent-generated — advisory, needs a confidence score


GATEABLE: frozenset[Reliability] = frozenset({Reliability.HARD, Reliability.STRUCTURED})


def is_gateable(reliability: Reliability) -> bool:
    return reliability in GATEABLE


def require_gateable(reliability: Reliability) -> None:
    """Fail closed if a non-HARD/STRUCTURED reliability reaches a runtime gate (§4.3)."""
    if reliability not in GATEABLE:
        raise ReliabilityError(
            f"{reliability} data may not gate a trading decision (only HARD/STRUCTURED, §4.3)"
        )
