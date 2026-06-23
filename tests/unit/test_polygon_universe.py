"""C3 — PolygonPITUniverse fail-closed adapter (Increment 6 PART A).

Fakes mirror REAL Polygon ``/v3/reference/tickers`` response shapes (verified live this session):
an active name returns a single ``results`` row with ``active:true``; a name not listed at the query
date returns ``count 0`` (empty results). Every transport/HTTP failure aborts the WHOLE snapshot —
no
partial/clean member set is ever sealed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from trading.data.errors import PolygonProvenanceError, UniverseEmptyError
from trading.data.membership_cache import MembershipCache
from trading.data.pit import AsOf
from trading.data.polygon_universe import (
    HttpxPolygonReference,
    PolygonPITUniverse,
    _membership_for,
)

_AS_OF = AsOf(ts=datetime(2023, 6, 1, tzinfo=UTC))

# Real-shaped Polygon results. At 2023-06-01: AAPL/MSFT active; SIVB already delisted (2023-03-28)
# so its as-of query returns count 0 — the exact survivorship distinction.
_RESP: dict[str, list[dict[str, Any]]] = {
    "AAPL": [{"ticker": "AAPL", "active": True, "delisted_utc": None, "list_date": "1980-12-12"}],
    "MSFT": [{"ticker": "MSFT", "active": True, "delisted_utc": None, "list_date": "1986-03-13"}],
    "SIVB": [],  # not listed at 2023-06-01 (post-delist) -> excluded by the allowlist
}


def _fake_fetch(symbol: str, date_str: str) -> list[dict[str, Any]]:
    return _RESP[symbol]


def test_builds_pit_snapshot_and_seals_artifact(tmp_path: Path) -> None:
    cache = MembershipCache(tmp_path)
    uni = PolygonPITUniverse(("AAPL", "MSFT", "SIVB"), fetch=_fake_fetch, cache=cache)
    snap = uni.as_of_members(as_of=_AS_OF)
    assert snap.symbols == frozenset({"AAPL", "MSFT"})  # SIVB excluded (count 0)
    assert snap.meta.is_pit_membership is True
    assert snap.meta.survivorship_unverified is False
    assert snap.meta.membership_vintage == _AS_OF.ts
    art = cache.get(snap.meta.universe_hash)  # universe_hash IS the membership-artifact hash
    assert art is not None
    assert {m.symbol for m in art.members} == {"AAPL", "MSFT"}


def test_all_inactive_yields_empty_universe_fail_closed() -> None:
    def inactive(symbol: str, date_str: str) -> list[dict[str, Any]]:
        return [{"ticker": symbol, "active": False, "delisted_utc": None, "list_date": None}]

    uni = PolygonPITUniverse(("AAPL",), fetch=inactive, cache=None)
    with pytest.raises(UniverseEmptyError):
        uni.as_of_members(as_of=_AS_OF)


def test_fetch_error_aborts_and_seals_no_partial_artifact(tmp_path: Path) -> None:
    def failing(symbol: str, date_str: str) -> list[dict[str, Any]]:
        if symbol == "MSFT":
            raise PolygonProvenanceError("simulated 429 on MSFT")
        return _RESP[symbol]

    cache = MembershipCache(tmp_path)
    uni = PolygonPITUniverse(("AAPL", "MSFT"), fetch=failing, cache=cache)
    with pytest.raises(PolygonProvenanceError):
        uni.as_of_members(as_of=_AS_OF)
    assert list(tmp_path.glob("*.json")) == []  # teeth: NO partial artifact sealed


def test_membership_for_allowlist_and_shape_guards() -> None:
    # active:true -> member
    m = _membership_for("AAPL", _RESP["AAPL"])
    assert m is not None and m.active is True
    # count 0 -> excluded (None), not an error
    assert _membership_for("SIVB", []) is None
    # results present but no matching ticker -> fail closed
    with pytest.raises(PolygonProvenanceError):
        _membership_for("AAPL", [{"ticker": "MSFT", "active": True}])
    # ambiguous (2 matching rows) -> fail closed
    dup = {"ticker": "AAPL", "active": True}
    with pytest.raises(PolygonProvenanceError):
        _membership_for("AAPL", [dup, dup])
    # missing 'active' -> fail closed
    with pytest.raises(PolygonProvenanceError):
        _membership_for("AAPL", [{"ticker": "AAPL"}])


def _ref_with(handler: Any) -> HttpxPolygonReference:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return HttpxPolygonReference("secret-token", client=client, sleeper=lambda s: None)


def test_httpx_reference_returns_results_on_200() -> None:
    def ok(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": _RESP["AAPL"], "status": "OK"})

    assert _ref_with(ok)("AAPL", "2023-06-01")[0]["ticker"] == "AAPL"


@pytest.mark.parametrize("status", [429, 500, 403])
def test_httpx_reference_non_200_fails_closed(status: int) -> None:
    def bad(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={})

    with pytest.raises(PolygonProvenanceError):
        _ref_with(bad)("AAPL", "2023-06-01")


def test_httpx_reference_network_error_fails_closed_without_leaking_token() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with pytest.raises(PolygonProvenanceError) as ei:
        _ref_with(boom)("AAPL", "2023-06-01")
    assert "secret-token" not in str(ei.value)  # token never surfaced


def test_httpx_reference_malformed_results_fails_closed() -> None:
    def weird(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": "not-a-list"})

    with pytest.raises(PolygonProvenanceError):
        _ref_with(weird)("AAPL", "2023-06-01")
