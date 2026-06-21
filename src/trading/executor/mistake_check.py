"""Pre-trade mistake-fingerprint check (M1-M20) — pure, deterministic, NO LLM.

Consults a CACHED pattern file (a JSON list); it never calls an LLM in the hot path.
Patterns expire (default 90 days) and expired ones are ignored. A missing file is an
empty ledger (nothing to block); a corrupt/unreadable file FAILS CLOSED (blocks every
order) — it never silently passes. Implements the ``MistakeChecker`` callable used by
the pre-submit invariant chain.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from trading.executor.intent import OrderIntent
from trading.executor.invariants import AccountSnapshot

SECONDS_PER_DAY = 86_400.0
DEFAULT_PATTERNS_PATH = Path("state/mistake_patterns.json")


@dataclass(frozen=True, slots=True)
class MistakePattern:
    """A fingerprint of a past mistake. Matches HARD/STRUCTURED intent fields only."""

    id: str
    category: str
    symbol: str | None = None
    strategy_id: str | None = None
    reason: str = ""
    last_occurrence_epoch: float = 0.0
    expiry_days: float = 90.0

    def is_active(self, now_epoch: float) -> bool:
        return (now_epoch - self.last_occurrence_epoch) <= self.expiry_days * SECONDS_PER_DAY

    def matches(self, intent: OrderIntent) -> bool:
        symbol_ok = self.symbol is None or self.symbol == intent.symbol
        strategy_ok = self.strategy_id is None or self.strategy_id == intent.strategy_id
        return symbol_ok and strategy_ok


class PatternMistakeChecker:
    """Callable checker: ``(intent, snapshot) -> block reason | None``."""

    def __init__(self, patterns: list[MistakePattern], *, corrupt: bool = False) -> None:
        self._patterns = patterns
        self._corrupt = corrupt

    @classmethod
    def from_file(cls, path: Path = DEFAULT_PATTERNS_PATH) -> PatternMistakeChecker:
        if not path.exists():
            return cls([])  # empty ledger: nothing known to block
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                return cls([], corrupt=True)
            patterns = [MistakePattern(**item) for item in raw]
            return cls(patterns)
        except (OSError, ValueError, TypeError):
            return cls([], corrupt=True)

    def __call__(self, intent: OrderIntent, snapshot: AccountSnapshot) -> str | None:
        if self._corrupt:
            return "BLOCKED: mistake-patterns file is corrupt (fail-closed)"
        for pattern in self._patterns:
            if pattern.is_active(snapshot.now_epoch) and pattern.matches(intent):
                return (
                    f"BLOCKED: matches pattern {pattern.id} ({pattern.category}): {pattern.reason}"
                )
        return None
