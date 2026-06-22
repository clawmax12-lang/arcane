"""Point-in-time universe + survivorship verdict (Increment 2 STEP 7).

The universe is the set of eligible symbols *as-of* a date. Survivorship-cleanliness is made
STRUCTURALLY UNREACHABLE while Polygon (the only real PIT membership-history source) is deferred:

  * ``SourceTier`` + ``TIER_IS_PIT`` is the SINGLE authority on "can this be survivorship-clean?";
  * ``UniverseMeta.survivorship_unverified`` is a DERIVED read-only property (no field to forge),
    and ``__post_init__`` rejects a "clean-but-non-PIT" meta;
  * ``PITUniverse.as_of_members`` is ``@final`` and the BASE builds the verdict from the subclass's
    ``SOURCE_TIER`` class-attr — a subclass has no override point to mint a clean verdict
    (mirrors ``DataLoader`` re-deriving provenance from the loader class, not the fetched data);
  * ``survivorship_t2`` therefore returns ``passed=False`` on every reachable path today; the
    ``passed=True`` branch is dead code until a real ``POLYGON_PIT`` source — which ``UniverseMeta``
    refuses unless it carries a real ``membership_vintage`` (the upgrade tripwire: no flat
    today-set relabeled as PIT).

No hardcoded symbol list: every member set must carry a content-addressed artifact hash. UTC
end-to-end; the snapshot is dated to a real PRIOR session via the calendar authority (never future).
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import ClassVar, Final, final

import pandas as pd

from trading.data import calendar
from trading.data.errors import (
    HardcodedUniverseError,
    NonPITMembershipError,
    RestatedMembershipError,
    UniverseConfigError,
    UniverseEmptyError,
    UniverseSourceError,
)
from trading.data.pit import AsOf
from trading.data.reliability import Reliability

logger = logging.getLogger(__name__)

# Reject-on-bad (never sanitize-and-accept): 1–10 chars, A–Z start, A–Z/0–9/./- thereafter.
_SYMBOL_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


class SourceTier(StrEnum):
    """Where a universe came from — the one place survivorship-cleanliness is decided."""

    OPERATOR_FILE = "operator_file"  # operator-curated watchlist — honest, NON-PIT
    ALPACA_TODAY = "alpaca_today"  # reserved: today-tradable snapshot (deferred), NON-PIT
    POLYGON_PIT = "polygon_pit"  # reserved: real PIT membership history (deferred), PIT


# The SINGLE structural authority. A new enum member with no entry here stays fail-closed
# (``assert_known`` raises), so survivorship-cleanliness can never be granted by omission.
TIER_IS_PIT: Final[Mapping[SourceTier, bool]] = {
    SourceTier.OPERATOR_FILE: False,
    SourceTier.ALPACA_TODAY: False,
    SourceTier.POLYGON_PIT: True,
}


def assert_known(tier: SourceTier) -> None:
    """Fail closed if a tier has no PIT mapping (a new member added without a decision)."""
    if tier not in TIER_IS_PIT:
        raise UniverseSourceError(f"SourceTier {tier!r} has no TIER_IS_PIT mapping (fail-closed)")


def is_pit(tier: SourceTier) -> bool:
    """True only for a tier that can carry real point-in-time, survivorship-clean membership."""
    assert_known(tier)
    return TIER_IS_PIT[tier]


@dataclass(frozen=True, slots=True)
class UniverseMeta:
    """Immutable provenance for a snapshot — the ``BarMeta`` analogue; cannot be stripped."""

    as_of: datetime
    session: pd.Timestamp
    source_tier: SourceTier
    is_pit_membership: bool
    member_count: int
    universe_hash: str
    loader: str
    membership_vintage: datetime | None = None  # real vintage for PIT sources; None otherwise
    # §4.3: STRUCTURED may advise factor scope but cannot directly gate an order.
    reliability: Reliability = Reliability.STRUCTURED

    def __post_init__(self) -> None:
        # The clean bit is a function of the tier, never an independent input → a forged
        # "clean but non-PIT" meta cannot be instantiated.
        if self.is_pit_membership != is_pit(self.source_tier):
            raise NonPITMembershipError(
                f"is_pit_membership={self.is_pit_membership} contradicts tier "
                f"{self.source_tier} (is_pit={is_pit(self.source_tier)})"
            )
        # A PIT tier MUST carry a real membership vintage — a flat set relabeled as PIT is refused
        # (the upgrade tripwire: the tier label alone can never make "fake PIT" pass T2).
        if self.is_pit_membership and self.membership_vintage is None:
            raise RestatedMembershipError(
                f"tier {self.source_tier} claims PIT membership but supplied no membership vintage"
            )
        # The vintage must not POST-DATE the as_of clock — a forward-dated membership is a
        # survivorship look-ahead, the mirror of pit_guard's ingest_ts<=as_of and AsOf's
        # reject-future. Guarded on any non-None vintage (defense-in-depth, not only PIT tiers) so
        # the upgrade tripwire cannot be bypassed by post-dating instead of by omission (SURV-1).
        if self.membership_vintage is not None and (
            pd.Timestamp(self.membership_vintage) > pd.Timestamp(self.as_of)
        ):
            raise RestatedMembershipError(
                f"membership_vintage {self.membership_vintage} is after as_of {self.as_of} "
                f"(future-dated membership is a survivorship look-ahead)"
            )

    @property
    def survivorship_unverified(self) -> bool:
        """Derived, read-only — there is NO writable field to forge."""
        return not self.is_pit_membership


@dataclass(frozen=True, slots=True)
class UniverseSnapshot:
    """Consumer-facing result (``LoadResult`` analogue): immutable symbols + inseparable provenance.

    No public path returns the symbols without the meta attached, so survivorship status can never
    be read off the symbol set alone.
    """

    symbols: frozenset[str]
    meta: UniverseMeta

    @property
    def as_of(self) -> datetime:
        return self.meta.as_of

    def contains(self, symbol: str) -> bool:
        return symbol in self.symbols

    def sorted_symbols(self) -> tuple[str, ...]:
        """Deterministic ordering for cache keys / spec_hash binding."""
        return tuple(sorted(self.symbols))


class PITUniverse(ABC):
    """Abstract universe. Subclasses implement ONLY ``_members``; ``as_of_members`` is ``@final``.

    The base re-derives the survivorship verdict from ``type(self).SOURCE_TIER`` after the subclass
    hook returns — an untrusted ``_members``, a trusted re-derivation (same guarantee as
    ``DataLoader``). ``as_of`` is a required kw-only ``AsOf`` — omitting the PIT clock is a
    TypeError.
    """

    SOURCE_TIER: ClassVar[SourceTier]
    SCHEMA_VERSION: ClassVar[int] = 1

    @final
    def as_of_members(self, *, as_of: AsOf, session: str = "XNYS") -> UniverseSnapshot:
        sess = calendar.as_of_session(pd.Timestamp(as_of.ts))  # prior session, never future
        symbols, artifact_hash = self._members(as_of, sess)
        if not artifact_hash:
            raise HardcodedUniverseError(
                f"{type(self).__name__} returned members with no content-addressed artifact hash"
            )
        if not symbols:
            raise UniverseEmptyError(
                f"{type(self).__name__} resolved an empty universe at {as_of.ts}"
            )
        self._assert_well_formed(symbols)
        tier = type(self).SOURCE_TIER
        meta = UniverseMeta(
            as_of=as_of.ts,
            session=sess,
            source_tier=tier,
            is_pit_membership=is_pit(tier),  # BASE owns the verdict, derived from the class tier
            member_count=len(symbols),
            universe_hash=artifact_hash,
            loader=type(self).__name__,
        )
        logger.info(
            "universe.snapshot as_of=%s session=%s source_tier=%s member_count=%d "
            "universe_hash=%s degraded=%s",
            as_of.ts.isoformat(),
            sess,
            tier,
            len(symbols),
            artifact_hash[:8],
            meta.survivorship_unverified,
        )
        return UniverseSnapshot(symbols=frozenset(symbols), meta=meta)

    @abstractmethod
    def _members(self, as_of: AsOf, session: pd.Timestamp) -> tuple[frozenset[str], str]:
        """Return ``(symbols, content-addressed artifact hash)``. The ONLY subclass hook."""

    @staticmethod
    def _assert_well_formed(symbols: frozenset[str]) -> None:
        bad = sorted(s for s in symbols if not _SYMBOL_RE.match(s))
        if bad:
            raise UniverseConfigError(f"malformed symbols (reject-on-bad): {bad}")


@dataclass(frozen=True, slots=True)
class BiasTestResult:
    """The contract the Increment-5 bias gate consumes (JSON-serializable for the gate artifact)."""

    test_id: str
    passed: bool
    reason: str
    as_of: datetime
    evidence: Mapping[str, str]

    def __post_init__(self) -> None:
        if not self.reason:
            raise ValueError("BiasTestResult.reason must be non-empty (a silent verdict misleads)")


def survivorship_t2(meta: UniverseMeta) -> BiasTestResult:
    """Bias-gate test T2 (survivorship). PURE + total (no I/O, no LLM).

    ``passed`` is structurally False while Polygon is deferred: it equals
    ``meta.is_pit_membership``, which every shipped source sets False, and a PIT meta is itself
    unconstructible without a real vintage. A real Polygon T2 will also validate per-date intervals.
    """
    passed = meta.is_pit_membership
    reason = (
        "survivorship-clean PIT membership verified"
        if passed
        else f"universe unverified: tier {meta.source_tier} is not PIT (Polygon deferred)"
    )
    result = BiasTestResult(
        test_id="T2",
        passed=passed,
        reason=reason,
        as_of=meta.as_of,
        evidence={
            "source_tier": str(meta.source_tier),
            "universe_hash": meta.universe_hash,
            "is_pit_membership": str(meta.is_pit_membership),
            "membership_vintage": (
                meta.membership_vintage.isoformat()
                if meta.membership_vintage is not None
                else "none"
            ),
        },
    )
    logger.info(
        "universe.t2 test_id=T2 passed=%s reason=%r source_tier=%s universe_hash=%s",
        result.passed,
        reason,
        meta.source_tier,
        meta.universe_hash[:8],
    )
    return result


@dataclass(frozen=True, slots=True)
class ExpectedGrid:
    """The expected (symbol x session) grid for the quality-gate G4 coverage report.

    Built from the calendar authority ONLY and clamped to PIT visibility, so it never expects a bar
    from a session that had not closed at ``as_of``. Carries the snapshot's survivorship flag so
    coverage of a biased universe is itself stamped biased. NEVER imputes — it only states what
    SHOULD exist; ``quality.coverage_report`` consumes it.
    """

    sessions: pd.DatetimeIndex
    symbols: tuple[str, ...]
    coverage_is_survivorship_biased: bool

    def expected_daily_instants(self, symbol: str) -> pd.DatetimeIndex:
        """Midnight-ET->UTC instants a daily-bar loader stamps for ``symbol`` (DST-safe)."""
        if symbol not in self.symbols:
            raise KeyError(f"{symbol!r} is not in this universe grid")
        return pd.DatetimeIndex([calendar.daily_bar_instant(s) for s in self.sessions], name="ts")


def expected_grid(
    snapshot: UniverseSnapshot, *, start: pd.Timestamp, end: pd.Timestamp
) -> ExpectedGrid:
    """Build the PIT-honest expected grid for ``snapshot`` over ``[start, end]`` (closes G4).

    Only sessions whose close is at/before ``snapshot.as_of`` are included — the grid can never ask
    coverage to expect a bar not yet published at the point-in-time the snapshot is dated to.
    """
    as_of = pd.Timestamp(snapshot.as_of)
    visible = [
        s for s in calendar.sessions_in_range(start, end) if calendar.daily_bar_visible(s, as_of)
    ]
    return ExpectedGrid(
        sessions=pd.DatetimeIndex(visible),
        symbols=snapshot.sorted_symbols(),
        coverage_is_survivorship_biased=snapshot.meta.survivorship_unverified,
    )
