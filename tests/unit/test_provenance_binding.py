"""Red-team D1 — ProvenanceBinding is UNFORGEABLE: token-gated, minted only from a PIT snapshot."""

from __future__ import annotations

from datetime import UTC, datetime

import _gate_fixtures as fx
import pytest

from trading.data.errors import ProvenanceBindingError
from trading.data.membership_artifact import (
    ProvenanceBinding,
    membership_artifact_hash,
    provenance_binding_from,
)
from trading.data.pit import AsOf
from trading.data.universe_sources import default_universe

_AS_OF = datetime(2023, 6, 1, tzinfo=UTC)
_WS = datetime(2021, 1, 1, tzinfo=UTC)
_WE = datetime(2023, 6, 1, tzinfo=UTC)


def test_hand_built_binding_is_refused() -> None:
    # a caller cannot construct a binding (no _MINT token) — the FC-1 forged-hash attack is closed.
    with pytest.raises(ProvenanceBindingError):
        ProvenanceBinding(
            membership_artifact_hash="arcane-univ-forged",
            traded_symbols=("AAPL",),
            window_start=_WS,
            window_end=_WE,
            as_of=_AS_OF,
            _token=object(),
        )


def test_producer_mints_from_a_pit_snapshot_with_the_base_owned_hash() -> None:
    snap = fx.pit_snapshot(("AAPL", "MSFT"), _AS_OF)
    binding = provenance_binding_from(
        snap, traded_symbols=("MSFT", "AAPL"), window_start=_WS, window_end=_WE
    )
    # the hash is taken from the snapshot (base-owned), NOT a caller string; symbols are sorted.
    assert binding.membership_artifact_hash == snap.meta.universe_hash
    assert binding.membership_artifact_hash == membership_artifact_hash(
        fx.matching_artifact(("AAPL", "MSFT"), _AS_OF)
    )
    assert binding.traded_symbols == ("AAPL", "MSFT")
    assert binding.as_of == snap.meta.as_of


def test_producer_refuses_a_non_pit_snapshot() -> None:
    # an OPERATOR_FILE (non-PIT) snapshot can never mint a binding (only a survivorship-clean
    # source).
    operator_snap = default_universe().as_of_members(as_of=AsOf(_AS_OF))
    assert operator_snap.meta.is_pit_membership is False
    with pytest.raises(ProvenanceBindingError):
        provenance_binding_from(
            operator_snap, traded_symbols=("AAPL",), window_start=_WS, window_end=_WE
        )


def test_producer_refuses_empty_traded_symbols() -> None:
    snap = fx.pit_snapshot(("AAPL",), _AS_OF)
    with pytest.raises(ProvenanceBindingError):
        provenance_binding_from(snap, traded_symbols=(), window_start=_WS, window_end=_WE)


def test_binding_is_immutable() -> None:
    snap = fx.pit_snapshot(("AAPL",), _AS_OF)
    binding = provenance_binding_from(
        snap, traded_symbols=("AAPL",), window_start=_WS, window_end=_WE
    )
    with pytest.raises(AttributeError):
        binding.membership_artifact_hash = "x"  # type: ignore[misc]
