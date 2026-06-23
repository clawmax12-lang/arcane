"""``PolygonPITUniverse`` — a point-in-time, survivorship-correct universe source (Inc-6 PART A).

Survivorship-correctness comes from Polygon's reconstructed reference data: for an ``as_of`` date,
``GET /v3/reference/tickers?ticker=SYM&date=as_of`` returns the symbol's state AS OF that date —
``active:true`` ONLY during its real trading life (a delisted-later name like SIVB still shows
``active:true`` with ``delisted_utc:null`` when queried at a date inside its trading interval;
verified live). This is the membership a flat watchlist gets WRONG by dropping delisted names.

Discipline:
  * ALLOWLIST: a symbol is included for an ``as_of`` ONLY on an explicit ``active:true`` at that
    date. Empty / inactive / ambiguous → EXCLUDED. Default-on-ambiguity is forbidden.
  * FAIL CLOSED, never partial: ANY fetch failure (429/timeout/non-200/network/malformed/shape
    mismatch) raises ``PolygonProvenanceError`` and ABORTS the whole snapshot — no partial or
    "best-effort" member set is ever sealed.
  * Rate limit: the free tier is ~5 calls/min; the default fetcher SPACES calls (sleep, not fail).
  * The sealed ``MembershipArtifact`` is content-addressed; its hash becomes the snapshot's
    ``universe_hash`` and the provenance the bias-gate T2 verifier binds against.

The vendor adapter is the ONLY surface that touches Polygon; the token is never logged.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar, Final

import httpx
import pandas as pd

from trading.data.errors import PolygonProvenanceError
from trading.data.membership_artifact import (
    MembershipArtifact,
    SymbolMembership,
    membership_artifact_hash,
)
from trading.data.membership_cache import MembershipCache
from trading.data.pit import AsOf
from trading.data.universe import MembershipProvenance, PITUniverse, SourceTier

logger = logging.getLogger(__name__)

_POLYGON_BASE: Final[str] = "https://api.polygon.io"
_REFERENCE_PATH: Final[str] = "/v3/reference/tickers"
_FREE_TIER_MIN_INTERVAL_S: Final[float] = 12.0  # ~5 calls/min
_SCHEMA_VERSION: Final[int] = 1

#: A fetcher returns the raw Polygon ``results`` list for ``(symbol, yyyy-mm-dd)``; it RAISES
#: ``PolygonProvenanceError`` on any transport/HTTP/parse failure (never returns a partial/empty
#: result to signify an error — empty means "not listed at that date", a valid exclusion).
PolygonReference = Callable[[str, str], list[dict[str, Any]]]


class HttpxPolygonReference:
    """Default fetcher: a throttled, fail-closed Polygon reference client. Token never logged."""

    def __init__(
        self,
        token: str,
        *,
        client: httpx.Client | None = None,
        base_url: str = _POLYGON_BASE,
        timeout: float = 20.0,
        min_interval_s: float = _FREE_TIER_MIN_INTERVAL_S,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._token = token
        self._client = client
        self._base = base_url
        self._timeout = timeout
        self._min_interval = min_interval_s
        self._sleeper = sleeper
        self._clock = clock
        self._last_call: float | None = None

    def _throttle(self) -> None:
        if self._last_call is not None:
            wait = self._min_interval - (self._clock() - self._last_call)
            if wait > 0:
                self._sleeper(wait)
        self._last_call = self._clock()

    def __call__(self, symbol: str, date_str: str) -> list[dict[str, Any]]:
        self._throttle()
        url = self._base + _REFERENCE_PATH
        params = {"ticker": symbol, "date": date_str, "apiKey": self._token}
        client = self._client or httpx.Client()
        try:
            resp = client.get(url, params=params, timeout=self._timeout)
        except Exception as exc:
            # Re-wrap ANY error to the TYPE only — the request URL embeds the apiKey; never leak it.
            raise PolygonProvenanceError(
                f"polygon reference fetch failed for {symbol}: {type(exc).__name__}"
            ) from None
        finally:
            if self._client is None:
                client.close()
        if resp.status_code != 200:
            raise PolygonProvenanceError(
                f"polygon reference returned HTTP {resp.status_code} for {symbol} (fail closed)"
            )
        try:
            payload = resp.json()
        except Exception as exc:
            raise PolygonProvenanceError(
                f"polygon reference malformed JSON for {symbol}: {type(exc).__name__}"
            ) from None
        results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(results, list):
            raise PolygonProvenanceError(f"polygon reference malformed results for {symbol}")
        return results


def _parse_polygon_dt(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        return datetime.fromisoformat(text)
    except ValueError as exc:
        raise PolygonProvenanceError(f"malformed Polygon date {value!r}: {exc}") from exc


def _membership_for(symbol: str, results: list[dict[str, Any]]) -> SymbolMembership | None:
    """Map a Polygon ``results`` list for ONE ticker query to a membership, or None if not active.

    ALLOWLIST: returns a member ONLY on an explicit ``active:true`` for the exact ticker. Empty ⇒
    not listed at that date ⇒ excluded (None). An ambiguous/mismatched shape ⇒ fail closed.
    """
    matching = [r for r in results if r.get("ticker") == symbol]
    if not matching:
        if results:  # results present but none match the requested ticker ⇒ a shape we don't trust
            raise PolygonProvenanceError(
                f"polygon reference returned no row for {symbol} among {len(results)} results"
            )
        return None  # count 0 ⇒ not listed at that date ⇒ correctly excluded (allowlist)
    if len(matching) > 1:
        raise PolygonProvenanceError(
            f"polygon reference ambiguous: {len(matching)} rows for {symbol}"
        )
    row = matching[0]
    if "active" not in row:
        raise PolygonProvenanceError(f"polygon reference row for {symbol} missing 'active'")
    if row.get("active") is not True:
        return None  # not active at as_of ⇒ excluded (allowlist; never default-include)
    return SymbolMembership(
        symbol=symbol,
        active=True,
        listed_utc=_parse_polygon_dt(row.get("list_date")),
        delisted_utc=_parse_polygon_dt(row.get("delisted_utc")),
    )


class PolygonPITUniverse(PITUniverse):
    """PIT universe sourced from Polygon reference data. The FIRST source where T2 can pass."""

    SOURCE_TIER: ClassVar[SourceTier] = SourceTier.POLYGON_PIT

    def __init__(
        self,
        candidates: tuple[str, ...],
        *,
        fetch: PolygonReference,
        cache: MembershipCache | None = None,
    ) -> None:
        if not candidates:
            raise PolygonProvenanceError("PolygonPITUniverse requires a non-empty candidate set")
        self._candidates = tuple(candidates)
        self._fetch = fetch
        self._cache = cache
        self._memo: dict[str, MembershipProvenance] = {}

    def _members(self, as_of: AsOf, session: pd.Timestamp) -> tuple[frozenset[str], str]:
        date_str = pd.Timestamp(as_of.ts).strftime("%Y-%m-%d")
        members: list[SymbolMembership] = []
        for symbol in self._candidates:
            results = self._fetch(symbol, date_str)  # may RAISE PolygonProvenanceError -> abort
            m = _membership_for(symbol, results)
            if m is not None:
                members.append(m)
        artifact = MembershipArtifact(
            schema_version=_SCHEMA_VERSION,
            source_tier=SourceTier.POLYGON_PIT,
            as_of=as_of.ts,
            vintage=as_of.ts,  # single-as_of reconstruction: vintage == as_of
            members=tuple(sorted(members, key=lambda x: x.symbol)),
        )
        art_hash = membership_artifact_hash(artifact)
        if self._cache is not None:
            self._cache.put(artifact)  # seal AFTER the whole set built (never a partial)
        self._memo[as_of.ts.isoformat()] = MembershipProvenance(
            vintage=as_of.ts, artifact_hash=art_hash
        )
        active_symbols = frozenset(m.symbol for m in members)
        logger.info(
            "polygon.universe as_of=%s candidates=%d active=%d artifact=%s",
            date_str,
            len(self._candidates),
            len(active_symbols),
            art_hash[:16],
        )
        return active_symbols, art_hash

    def _membership_provenance(self, as_of: AsOf, session: pd.Timestamp) -> MembershipProvenance:
        prov = self._memo.get(as_of.ts.isoformat())
        if prov is None:  # pragma: no cover - the @final base always calls _members first
            raise PolygonProvenanceError(
                "membership provenance requested before members were built"
            )
        return prov


def polygon_universe_from_config(
    candidates: tuple[str, ...],
    token: str,
    *,
    cache_dir: Path | None = None,
) -> PolygonPITUniverse:
    """Wire a live ``PolygonPITUniverse`` from a candidate set + a token (operator/script path)."""
    cache = MembershipCache(cache_dir) if cache_dir is not None else None
    return PolygonPITUniverse(candidates, fetch=HttpxPolygonReference(token), cache=cache)
