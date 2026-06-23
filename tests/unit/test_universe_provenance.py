"""C1 — the base-seam membership-provenance hook (Increment 6 PART A).

The @final ``as_of_members`` base must let a PIT subclass supply a real ``(vintage, artifact_hash)``
that is threaded into ``UniverseMeta.membership_vintage`` — WITHOUT giving the subclass any way to
mint a survivorship-clean verdict it did not earn. The base still derives ``is_pit_membership``
purely
from the class tier; the hook returns DATA only (no bool). A PIT subclass that forgets the hook
fails
CLOSED (``RestatedMembershipError``); a forward-dated vintage is refused by the unchanged SURV-1
guard.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from trading.data.errors import RestatedMembershipError
from trading.data.pit import AsOf
from trading.data.universe import (
    MembershipProvenance,
    PITUniverse,
    SourceTier,
)

_AS_OF = AsOf(ts=datetime(2023, 6, 1, tzinfo=UTC))
_SYMS = frozenset({"AAPL", "MSFT"})


class _FakeNonPIT(PITUniverse):
    """An operator-tier (non-PIT) fake — must NOT carry a vintage and must NOT call the hook."""

    SOURCE_TIER = SourceTier.OPERATOR_FILE

    def _members(self, as_of: AsOf, session: pd.Timestamp) -> tuple[frozenset[str], str]:
        return _SYMS, "operator-artifact-hash"


class _FakePITWithProvenance(PITUniverse):
    """A PIT-tier fake that correctly supplies provenance (vintage <= as_of)."""

    SOURCE_TIER = SourceTier.POLYGON_PIT

    def __init__(self, *, vintage: datetime, art_hash: str = "polygon-artifact-hash") -> None:
        self._vintage = vintage
        self._art_hash = art_hash

    def _members(self, as_of: AsOf, session: pd.Timestamp) -> tuple[frozenset[str], str]:
        return _SYMS, self._art_hash

    def _membership_provenance(self, as_of: AsOf, session: pd.Timestamp) -> MembershipProvenance:
        return MembershipProvenance(vintage=self._vintage, artifact_hash=self._art_hash)


class _FakePITNoProvenance(PITUniverse):
    """A PIT-tier fake that FORGETS to override the hook — must fail closed."""

    SOURCE_TIER = SourceTier.POLYGON_PIT

    def _members(self, as_of: AsOf, session: pd.Timestamp) -> tuple[frozenset[str], str]:
        return _SYMS, "polygon-artifact-hash"


def test_non_pit_subclass_builds_unverified_meta_without_vintage() -> None:
    snap = _FakeNonPIT().as_of_members(as_of=_AS_OF)
    assert snap.meta.is_pit_membership is False
    assert snap.meta.survivorship_unverified is True
    assert snap.meta.membership_vintage is None
    assert snap.meta.universe_hash == "operator-artifact-hash"


def test_pit_subclass_with_provenance_builds_clean_meta() -> None:
    vintage = datetime(2023, 6, 1, tzinfo=UTC)  # == as_of (equality allowed)
    snap = _FakePITWithProvenance(vintage=vintage).as_of_members(as_of=_AS_OF)
    assert snap.meta.is_pit_membership is True
    assert snap.meta.survivorship_unverified is False
    assert snap.meta.membership_vintage == vintage
    # For a PIT source the universe_hash IS the membership-artifact hash (the provenance).
    assert snap.meta.universe_hash == "polygon-artifact-hash"


def test_pit_subclass_missing_provenance_hook_fails_closed() -> None:
    with pytest.raises(RestatedMembershipError):
        _FakePITNoProvenance().as_of_members(as_of=_AS_OF)


def test_pit_subclass_future_dated_vintage_is_refused() -> None:
    future = _AS_OF.ts + timedelta(days=1)
    with pytest.raises(RestatedMembershipError):
        _FakePITWithProvenance(vintage=future).as_of_members(as_of=_AS_OF)


def test_provenance_hook_returns_only_data_no_verdict_field() -> None:
    """MembershipProvenance carries vintage + hash ONLY — there is no bool to forge (FC-1
    lesson)."""
    import dataclasses

    fields = {f.name for f in dataclasses.fields(MembershipProvenance)}
    assert fields == {"vintage", "artifact_hash"}
    # A subclass cannot influence is_pit_membership: it is derived from the class tier, not the
    # hook.
    snap = _FakePITWithProvenance(vintage=_AS_OF.ts).as_of_members(as_of=_AS_OF)
    assert snap.meta.is_pit_membership is True  # POLYGON_PIT tier, regardless of hook contents
