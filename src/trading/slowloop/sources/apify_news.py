"""``ApifyNewsSource`` — fail-closed Google-News FALLBACK adapter (Inc-8.6 PART A, SECONDARY).

Honest reality (live-probed this session): on the FREE Apify plan ``easyapi/google-news-scraper``
SUCCEEDS but returns 0 dataset items (Google blocks the free-tier proxy). So this is wired as the
composite FALLBACK behind the same ``NewsSource`` seam: it costs nothing while Tavily works
(the composite reaches it only when Tavily RAISES), never fabricates, and lights up with zero code
change once the plan/actor cooperates. Same fail-closed contract as the Tavily adapter.

Input contract (live-probed): ``POST /v2/acts/{actor}/run-sync-get-dataset-items`` with a Bearer
token and body ``{query, maxItems(>=100), time_period}`` returns a JSON list of dataset items. Token
in the ``Authorization`` header ONLY; every exception re-wrapped to TYPE-only.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, Final

import httpx

from trading.slowloop.agents.news import NewsItem
from trading.slowloop.sources.errors import NewsSourceError
from trading.slowloop.sources.tavily_news import _domain  # reuse the pure host parser

logger = logging.getLogger(__name__)

_APIFY_BASE: Final[str] = "https://api.apify.com"
_DEFAULT_ACTOR: Final[str] = "easyapi~google-news-scraper"
_DEFAULT_QUERY: Final[str] = "stock market"
_MIN_MAX_ITEMS: Final[int] = 100  # the actor rejects maxItems < 100 (live-probed)
_DEFAULT_TIME_PERIOD: Final[str] = "last_day"
_DEFAULT_MIN_INTERVAL_S: Final[float] = 2.0


def _parse_apify_dt(value: Any) -> datetime | None:
    """Parse a google-news date (ISO-8601 or RFC-2822) to aware UTC; None on missing/garbage."""
    if value in (None, ""):
        return None
    text = str(value)
    try:  # ISO-8601 first (the common google-news shape)
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
    except ValueError:
        pass
    try:  # then RFC-2822
        dt2 = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None
    if dt2 is None:
        return None
    return dt2.replace(tzinfo=UTC) if dt2.tzinfo is None else dt2.astimezone(UTC)


def items_from_dataset(items: Any) -> list[NewsItem]:
    """Map an Apify dataset list to ``NewsItem``s — container break RAISES, a bad ROW is DROPPED."""
    if not isinstance(items, list):
        raise NewsSourceError("apify dataset was not a JSON list (fail closed)")
    out: list[NewsItem] = []
    for row in items:
        if not isinstance(row, dict):
            continue
        title = row.get("title")
        if not isinstance(title, str) or not title.strip():
            continue
        url = row.get("url") or row.get("link")
        published_at = _parse_apify_dt(
            row.get("published_date")
            or row.get("published")
            or row.get("publishedAt")
            or row.get("date")
        )
        if published_at is None:
            continue  # never fabricate a timestamp
        source = row.get("source") or row.get("publisher") or _domain(url)
        out.append(NewsItem(title=title, source=str(source), published_at=published_at))
    logger.debug("apify.news items=%d mapped=%d", len(items), len(out))
    return out


class ApifyNewsSource:
    """Default Apify Google-News fallback: a throttled fail-closed run-sync client. Key hidden."""

    def __init__(
        self,
        token: str,
        *,
        actor_id: str = _DEFAULT_ACTOR,
        query: str = _DEFAULT_QUERY,
        max_items: int = _MIN_MAX_ITEMS,
        time_period: str = _DEFAULT_TIME_PERIOD,
        client: httpx.Client | None = None,
        base_url: str = _APIFY_BASE,
        timeout: float = 90.0,
        min_interval_s: float = _DEFAULT_MIN_INTERVAL_S,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not token:
            raise NewsSourceError("ApifyNewsSource requires a token (fail closed)")
        self._token = token
        self._actor = actor_id
        self._query = query
        self._max_items = max(max_items, _MIN_MAX_ITEMS)  # the actor requires >= 100
        self._time_period = time_period
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
        url = f"{self._base}/v2/acts/{self._actor}/run-sync-get-dataset-items"
        headers = {
            "Authorization": f"Bearer {self._token}",  # token in the header ONLY
            "content-type": "application/json",
        }
        body: dict[str, object] = {
            "query": self._query,
            "maxItems": self._max_items,
            "time_period": self._time_period,
        }
        client = self._client or httpx.Client()
        try:
            resp = client.post(url, headers=headers, json=body, timeout=self._timeout)
        except Exception as exc:
            raise NewsSourceError(f"apify news fetch failed: {type(exc).__name__}") from None
        finally:
            if self._client is None:
                client.close()
        if resp.status_code // 100 != 2:
            raise NewsSourceError(f"apify news returned HTTP {resp.status_code} (fail closed)")
        try:
            payload = resp.json()
        except Exception as exc:
            raise NewsSourceError(f"apify news malformed JSON: {type(exc).__name__}") from None
        return items_from_dataset(payload)
