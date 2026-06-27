"""``HttpxTavilyNews`` — the real, fail-closed Tavily news adapter (Inc-8.6 PART A, PRIMARY).

Live-probed shape (this session): ``POST https://api.tavily.com/search`` with a Bearer-header token
and body ``{query, topic:"news", max_results, days:1}`` returns 200 with a ``results`` list of
``{title, url, content, published_date, raw_content, score}``; ``published_date`` is RFC-2822
(``"Fri, 26 Jun 2026 20:01:39 GMT"``). One call returns the current headlines.

Discipline (mirrors ``data/polygon_universe.py``):
  * THROTTLE: a min-interval gate that SLEEPS (never fails a request).
  * FAIL CLOSED, never partial: ANY transport/timeout/429/non-200/non-JSON/shape-mismatch raises
    ``NewsSourceError`` (the WHOLE container). An empty ``results`` is a VALID "no news" (``[]``;
    the agent maps empty to uncertain to discarded). A single malformed ROW (blank title or a bad
    ``published_date``) is DROPPED, never fabricated — siblings are kept.
  * TOKEN: in the ``Authorization`` header ONLY — never in the body/params/log; every exception is
    re-wrapped to the TYPE only, so a key-bearing transport error can never escape.
  * The adapter does NOT sanitize — the RAW title flows to ``NewsItem``; the ``NewsAgent`` sanitizes
    each title BEFORE the LLM (the sole §4.2 choke). The raw title is logged at DEBUG for audit.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, Final
from urllib.parse import urlparse

import httpx

from trading.slowloop.agents.news import NewsItem
from trading.slowloop.sources.errors import NewsSourceError

logger = logging.getLogger(__name__)

_TAVILY_BASE: Final[str] = "https://api.tavily.com"
_SEARCH_PATH: Final[str] = "/search"
_DEFAULT_QUERY: Final[str] = "US stock market today"
_DEFAULT_MAX_RESULTS: Final[int] = 12
_DEFAULT_MIN_INTERVAL_S: Final[float] = 1.0  # polite spacing; Tavily free ~1000/mo


def _parse_rfc2822(value: Any) -> datetime | None:
    """Parse Tavily's RFC-2822 ``published_date`` to aware UTC; None on missing/garbage (drop row).

    NEVER fabricates a timestamp — a missing/unparseable date drops that one headline (it cannot be
    cited with an honest ``Source.as_of``), but does not abort the whole fetch.
    """
    if value in (None, ""):
        return None
    try:
        dt = parsedate_to_datetime(str(value))
    except (TypeError, ValueError):
        return None
    if dt is None:  # parsedate_to_datetime can return None on some malformed inputs
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _domain(url: Any) -> str:
    """The lowercased host of ``url`` (``www.`` stripped); ``'unknown'`` on anything odd. Total."""
    try:
        netloc = urlparse(str(url)).netloc.lower()
    except Exception:
        return "unknown"
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc or "unknown"


def items_from_results(payload: Any) -> list[NewsItem]:
    """Map a Tavily search payload to ``NewsItem``s — container break RAISES, a bad ROW is DROPPED.

    A non-dict payload or a non-list ``results`` is a shape we do not trust (fail closed,
    ``NewsSourceError``). An empty list is valid no-news (``[]``). A row with a blank ``title`` or a
    bad ``published_date`` is dropped (best-effort TEXTUAL evidence; dropping one headline does not
    corrupt a survivorship allowlist the way Polygon's would). All rows drop -> ``[]``.
    """
    if not isinstance(payload, dict):
        raise NewsSourceError("tavily news payload was not a JSON object (fail closed)")
    results = payload.get("results")
    if not isinstance(results, list):
        raise NewsSourceError("tavily news payload missing a 'results' list (fail closed)")
    items: list[NewsItem] = []
    for row in results:
        if not isinstance(row, dict):
            continue  # drop a malformed row, keep siblings
        title = row.get("title")
        if not isinstance(title, str) or not title.strip():
            continue
        published_at = _parse_rfc2822(row.get("published_date"))
        if published_at is None:
            continue  # never fabricate a timestamp
        items.append(
            NewsItem(
                title=title,  # RAW — the NewsAgent sanitizes before the LLM
                source=_domain(row.get("url")),
                published_at=published_at,
            )
        )
    logger.debug("tavily.news results=%d mapped=%d", len(results), len(items))
    return items


class HttpxTavilyNews:
    """Default Tavily ``NewsSource``: a throttled, fail-closed search client. Token never logged."""

    def __init__(
        self,
        token: str,
        *,
        query: str = _DEFAULT_QUERY,
        max_results: int = _DEFAULT_MAX_RESULTS,
        days: int = 1,
        client: httpx.Client | None = None,
        base_url: str = _TAVILY_BASE,
        timeout: float = 20.0,
        min_interval_s: float = _DEFAULT_MIN_INTERVAL_S,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not token:
            raise NewsSourceError("TavilyNewsSource requires a token (fail closed)")
        self._token = token
        self._query = query
        self._max_results = max_results
        self._days = days
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

    def __call__(self) -> list[NewsItem]:
        self._throttle()
        url = self._base + _SEARCH_PATH
        headers = {
            "Authorization": f"Bearer {self._token}",  # token in the header ONLY
            "content-type": "application/json",
        }
        body: dict[str, object] = {
            "query": self._query,
            "topic": "news",
            "max_results": self._max_results,
            "days": self._days,
        }
        client = self._client or httpx.Client()
        try:
            resp = client.post(url, headers=headers, json=body, timeout=self._timeout)
        except Exception as exc:
            # Re-wrap to the TYPE only — a transport error can embed the headers/token; never leak.
            raise NewsSourceError(f"tavily news fetch failed: {type(exc).__name__}") from None
        finally:
            if self._client is None:
                client.close()
        if resp.status_code // 100 != 2:
            raise NewsSourceError(f"tavily news returned HTTP {resp.status_code} (fail closed)")
        try:
            payload = resp.json()
        except Exception as exc:
            raise NewsSourceError(f"tavily news malformed JSON: {type(exc).__name__}") from None
        return items_from_results(payload)
