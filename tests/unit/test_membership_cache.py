"""C3 — MembershipCache content-addressed self-heal (Increment 6 PART A)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from trading.data.membership_artifact import (
    MembershipArtifact,
    SymbolMembership,
    membership_artifact_hash,
)
from trading.data.membership_cache import MembershipCache
from trading.data.universe import SourceTier

_AS_OF = datetime(2023, 6, 1, tzinfo=UTC)


def _artifact() -> MembershipArtifact:
    return MembershipArtifact(
        schema_version=1,
        source_tier=SourceTier.POLYGON_PIT,
        as_of=_AS_OF,
        vintage=_AS_OF,
        members=(
            SymbolMembership("AAPL", active=True, listed_utc=None, delisted_utc=None),
            SymbolMembership("MSFT", active=True, listed_utc=None, delisted_utc=None),
        ),
    )


def test_put_then_get_roundtrips(tmp_path: Path) -> None:
    cache = MembershipCache(tmp_path)
    key = cache.put(_artifact())
    assert key == membership_artifact_hash(_artifact())
    got = cache.get(key)
    assert got is not None
    assert {m.symbol for m in got.members} == {"AAPL", "MSFT"}
    assert membership_artifact_hash(got) == key


def test_missing_key_is_none(tmp_path: Path) -> None:
    assert MembershipCache(tmp_path).get("arcane-univ-doesnotexist") is None


def test_corrupt_entry_is_a_miss_and_self_heals(tmp_path: Path) -> None:
    cache = MembershipCache(tmp_path)
    key = cache.put(_artifact())
    (tmp_path / f"{key}.json").write_text("{ this is not valid json", encoding="utf-8")
    assert cache.get(key) is None  # corrupt -> miss
    assert not (tmp_path / f"{key}.json").exists()  # self-healed (unlinked)


def test_hash_mismatch_entry_is_a_miss(tmp_path: Path) -> None:
    cache = MembershipCache(tmp_path)
    key = cache.put(_artifact())
    # Tamper the stored content so its re-hash no longer matches the filename key (a swapped
    # artifact).
    other = MembershipArtifact(
        schema_version=1,
        source_tier=SourceTier.POLYGON_PIT,
        as_of=_AS_OF,
        vintage=_AS_OF,
        members=(SymbolMembership("AAPL", active=True, listed_utc=None, delisted_utc=None),),
    )
    from trading.data.membership_artifact import artifact_to_json

    (tmp_path / f"{key}.json").write_text(artifact_to_json(other), encoding="utf-8")
    assert cache.get(key) is None  # re-hash != key -> never served


def test_disk_floor_pauses_write(tmp_path: Path) -> None:
    cache = MembershipCache(tmp_path, min_free_bytes=1 << 62)  # impossible floor -> always paused
    key = cache.put(_artifact())  # returns the key but writes nothing
    assert not (tmp_path / f"{key}.json").exists()
    assert cache.get(key) is None  # a paused write is a safe miss (fail-closed downstream)
