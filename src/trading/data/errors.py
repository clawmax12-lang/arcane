"""Typed, fail-closed error taxonomy for the data layer (all ``ArcaneError`` subclasses).

Mirrors the Increment-1 idiom: every failure is a specific, catchable exception, and the
default on any uncertainty is to RAISE (fail closed) rather than return partial/empty data.
"""

from __future__ import annotations

from trading.risk.errors import ArcaneError


class DataError(ArcaneError):
    """Base class for all data-layer errors."""


class DataFetchError(DataError):
    """A vendor/network fetch failed or returned empty for the requested window."""


class SchemaError(DataError):
    """A frame failed schema/dtype validation."""


class FinitenessError(DataError):
    """A frame contains non-finite (NaN/inf) values where finite numbers are required."""


class CalendarError(DataError):
    """A timestamp is tz-naive/non-UTC, or a session/RTH computation is invalid."""


class QualityError(DataError):
    """A frame failed a data-quality check (monotonicity, duplicates, OHLC sanity)."""


class DuplicateBarError(QualityError):
    """A timestamp has conflicting duplicate bars (differing values) — never silently picked."""


class FeedMismatchError(DataError):
    """A bar's feed tag does not match the requested feed (e.g. IEX served for a SIP request)."""


class PITViolationError(DataError):
    """A point-in-time invariant was violated (e.g. ingest_ts > as_of)."""


class RestatedSourceError(DataError):
    """A restated/STRUCTURED source did not supply the required per-row ingest_ts."""


class CacheError(DataError):
    """The content-addressed cache could not store or serve an entry safely."""


class ReliabilityError(DataError):
    """A non-gateable (TEXTUAL/DERIVED) frame reached a runtime gate (CLAUDE.md §4.3)."""


class UniverseError(DataError):
    """Base for all universe-layer (STEP 7) failures."""


class UniverseConfigError(UniverseError):
    """Universe config is missing, unreadable, not a mapping, empty, or has a bad symbol."""


class UniverseEmptyError(UniverseError):
    """The resolved membership set is empty — never returned as a valid snapshot (fail-closed)."""


class NonPITMembershipError(UniverseError):
    """A UniverseMeta claimed survivorship-clean for a non-PIT source tier (forge-proof breach)."""


class HardcodedUniverseError(UniverseError):
    """A member set lacked a content-addressed artifact hash (an inline-literal smell)."""


class RestatedMembershipError(UniverseError):
    """A PIT source supplied membership with no real vintage (a flat set relabeled as PIT)."""


class UniverseSourceError(UniverseError):
    """An unmapped/unknown SourceTier reached the PIT whitelist (fail-closed)."""


class PolygonProvenanceError(DataError):
    """A Polygon PIT reference query failed (429/timeout/non-200/network/malformed) — artifact
    construction ABORTS and NO partial/clean membership set is ever sealed (fail closed)."""


class PrefixStabilityError(DataError):
    """A registered computation broke the prefix-stability property (a look-ahead leak by
    construction): ``compute(df[:k]) != compute(df[:k+1])[:k]`` for some k."""


class LeakLintError(DataError):
    """The AST leak-linter found a banned look-ahead/leak-prone primitive in the data layer."""
