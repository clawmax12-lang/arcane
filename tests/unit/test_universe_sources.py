"""Tests for OperatorFileUniverse + the wired default (Increment 2 STEP 7).

The operator watchlist is validated, content-hashed, and fail-closed — never trusted, never partial.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from trading.data.errors import UniverseConfigError
from trading.data.pit import AsOf
from trading.data.universe import SourceTier, survivorship_t2
from trading.data.universe_sources import OperatorFileUniverse, default_universe

_AS_OF = AsOf(datetime(2024, 7, 9, tzinfo=UTC))


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "universe.yaml"
    p.write_text(body, encoding="utf-8")
    return p


def test_operator_file_happy_path(tmp_path: Path) -> None:
    path = _write(tmp_path, "symbols:\n  - AAPL\n  - MSFT\n")
    snap = OperatorFileUniverse(config_path=path).as_of_members(as_of=_AS_OF)
    assert snap.sorted_symbols() == ("AAPL", "MSFT")
    assert snap.meta.source_tier is SourceTier.OPERATOR_FILE
    assert snap.meta.survivorship_unverified is True  # honest non-PIT
    assert len(snap.meta.universe_hash) == 64  # sha256 hex


def test_t2_on_operator_universe_fails_closed(tmp_path: Path) -> None:
    path = _write(tmp_path, "symbols:\n  - AAPL\n")
    snap = OperatorFileUniverse(config_path=path).as_of_members(as_of=_AS_OF)
    assert survivorship_t2(snap.meta).passed is False


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(UniverseConfigError):
        OperatorFileUniverse(config_path=tmp_path / "nope.yaml").as_of_members(as_of=_AS_OF)


def test_empty_symbols_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, "symbols: []\n")
    with pytest.raises(UniverseConfigError):
        OperatorFileUniverse(config_path=path).as_of_members(as_of=_AS_OF)


def test_non_mapping_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, "- AAPL\n- MSFT\n")  # a list, not a mapping
    with pytest.raises(UniverseConfigError, match="mapping"):
        OperatorFileUniverse(config_path=path).as_of_members(as_of=_AS_OF)


def test_extra_key_forbidden(tmp_path: Path) -> None:
    path = _write(tmp_path, "symbols:\n  - AAPL\nrebalance: daily\n")  # extra='forbid'
    with pytest.raises(UniverseConfigError):
        OperatorFileUniverse(config_path=path).as_of_members(as_of=_AS_OF)


def test_malformed_symbol_rejected(tmp_path: Path) -> None:
    path = _write(tmp_path, "symbols:\n  - aapl\n")  # lowercase -> reject-on-bad
    with pytest.raises(UniverseConfigError, match="malformed"):
        OperatorFileUniverse(config_path=path).as_of_members(as_of=_AS_OF)


def test_universe_hash_deterministic_and_content_addressed(tmp_path: Path) -> None:
    a = tmp_path / "a.yaml"
    a.write_text("symbols:\n  - AAPL\n  - MSFT\n", encoding="utf-8")
    b = tmp_path / "b.yaml"
    b.write_text("symbols:\n  - AAPL\n  - MSFT\n", encoding="utf-8")  # identical bytes to a
    c = tmp_path / "c.yaml"
    c.write_text("symbols:\n  - AAPL\n  - TSLA\n", encoding="utf-8")
    h_a = OperatorFileUniverse(config_path=a).as_of_members(as_of=_AS_OF).meta.universe_hash
    h_b = OperatorFileUniverse(config_path=b).as_of_members(as_of=_AS_OF).meta.universe_hash
    h_c = OperatorFileUniverse(config_path=c).as_of_members(as_of=_AS_OF).meta.universe_hash
    assert h_a == h_b  # identical bytes -> identical hash (reproducible)
    assert h_a != h_c  # a changed symbol -> a different hash (silent-mutation detectable)


def test_default_universe_loads_repo_config() -> None:
    # Offline: reads the committed config/universe.yaml at repo root.
    snap = default_universe().as_of_members(as_of=_AS_OF)
    assert snap.contains("AAPL")
    assert snap.meta.survivorship_unverified is True
    assert survivorship_t2(snap.meta).passed is False
