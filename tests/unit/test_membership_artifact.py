"""C2 — MembershipArtifact content-addressing (Increment 6 PART A).

The artifact is the unforgeable PIT-membership record T2 binds against by hash. Its hash must be
STABLE across runs and member insertion order (sorted-by-symbol canonical bytes), and must CHANGE on
any single field edit (drop a symbol / change a delist date / change the vintage) — so a benign
artifact cannot be swapped in for one that hides a survivorship drop.
"""

from __future__ import annotations

from datetime import UTC, datetime

from trading.data.membership_artifact import (
    MembershipArtifact,
    ProvenanceBinding,
    SymbolMembership,
    membership_artifact_hash,
)
from trading.data.universe import SourceTier

_AS_OF = datetime(2023, 6, 1, tzinfo=UTC)


def _members() -> tuple[SymbolMembership, ...]:
    return (
        SymbolMembership("AAPL", active=True, listed_utc=None, delisted_utc=None),
        SymbolMembership(
            "SIVB",
            active=True,
            listed_utc=None,
            delisted_utc=datetime(2023, 3, 28, 4, tzinfo=UTC),
        ),
    )


def _artifact(members: tuple[SymbolMembership, ...]) -> MembershipArtifact:
    return MembershipArtifact(
        schema_version=1,
        source_tier=SourceTier.POLYGON_PIT,
        as_of=_AS_OF,
        vintage=_AS_OF,
        members=members,
    )


def test_same_artifact_same_hash() -> None:
    a = _artifact(_members())
    b = _artifact(_members())
    assert membership_artifact_hash(a) == membership_artifact_hash(b)


def test_hash_is_order_independent() -> None:
    forward = _members()
    reversed_ = tuple(reversed(forward))
    assert membership_artifact_hash(_artifact(forward)) == membership_artifact_hash(
        _artifact(reversed_)
    )


def test_dropping_a_symbol_changes_the_hash() -> None:
    full = membership_artifact_hash(_artifact(_members()))
    dropped = membership_artifact_hash(_artifact(_members()[:1]))  # drop SIVB
    assert full != dropped


def test_changing_delisted_utc_changes_the_hash() -> None:
    base = membership_artifact_hash(_artifact(_members()))
    tampered = list(_members())
    tampered[1] = SymbolMembership(
        "SIVB", active=True, listed_utc=None, delisted_utc=datetime(2024, 1, 1, tzinfo=UTC)
    )
    assert base != membership_artifact_hash(_artifact(tuple(tampered)))


def test_changing_vintage_changes_the_hash() -> None:
    base = membership_artifact_hash(_artifact(_members()))
    other = MembershipArtifact(
        schema_version=1,
        source_tier=SourceTier.POLYGON_PIT,
        as_of=_AS_OF,
        vintage=datetime(2023, 5, 1, tzinfo=UTC),
        members=_members(),
    )
    assert base != membership_artifact_hash(other)


def test_changing_active_flag_changes_the_hash() -> None:
    base = membership_artifact_hash(_artifact(_members()))
    tampered = list(_members())
    tampered[0] = SymbolMembership("AAPL", active=False, listed_utc=None, delisted_utc=None)
    assert base != membership_artifact_hash(_artifact(tuple(tampered)))


def test_provenance_binding_is_frozen_data_only() -> None:
    import dataclasses

    b = ProvenanceBinding(
        membership_artifact_hash="arcane-univ-deadbeef",
        traded_symbols=("AAPL", "SIVB"),
        window_start=datetime(2021, 1, 1, tzinfo=UTC),
        window_end=_AS_OF,
        as_of=_AS_OF,
    )
    assert {f.name for f in dataclasses.fields(b)} == {
        "membership_artifact_hash",
        "traded_symbols",
        "window_start",
        "window_end",
        "as_of",
    }
    with __import__("pytest").raises(dataclasses.FrozenInstanceError):
        b.membership_artifact_hash = "x"  # type: ignore[misc]
