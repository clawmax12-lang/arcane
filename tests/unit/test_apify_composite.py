"""C2 — ApifyNewsSource (fallback) + CompositeNewsSource + the news factory (Increment 8.6 PART A).

Apify is the composite FALLBACK: on the FREE plan the live actor returns 0 items (proxy-blocked), so
its mapping is faked from the DOCUMENTED google-news item shape. The composite returns the first
NON-raising source (even ``[]``) and never merges; it reaches a fallback only if the primary RAISES.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest

from trading.slowloop.agents.news import NewsItem
from trading.slowloop.sources.apify_news import (
    ApifyNewsSource,
    _parse_apify_dt,
    items_from_dataset,
)
from trading.slowloop.sources.composite import CompositeNewsSource
from trading.slowloop.sources.errors import NewsSourceError
from trading.slowloop.sources.factory import build_news_source
from trading.slowloop.sources.tavily_news import HttpxTavilyNews

# A plausible google-news dataset item (documented shape; ISO-8601 date).
_DATASET = [
    {
        "title": "Apple unveils new chip",
        "link": "https://www.reuters.com/tech/apple",
        "source": "Reuters",
        "published": "2026-06-26T20:01:00Z",
    },
    {
        "title": "Markets steady ahead of data",
        "url": "https://apnews.com/markets",
        "publishedAt": "Fri, 26 Jun 2026 18:00:00 GMT",
    },
]


def _client(handler: object) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))  # type: ignore[arg-type]


def _src(handler: object, **kw: object) -> ApifyNewsSource:
    return ApifyNewsSource(
        "apify_tok", client=_client(handler), sleeper=lambda _f: None, **kw  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------- apify mapping


def test_items_from_dataset_maps_documented_shape() -> None:
    items = items_from_dataset(_DATASET)
    assert [i.title for i in items] == ["Apple unveils new chip", "Markets steady ahead of data"]
    assert items[0].source == "Reuters"  # explicit source field
    assert items[0].published_at == datetime(2026, 6, 26, 20, 1, tzinfo=UTC)
    assert items[1].source == "apnews.com"  # derived from url when no source field


def test_apify_empty_dataset_is_no_news() -> None:
    assert items_from_dataset([]) == []  # the FREE-plan reality: SUCCEEDED but empty -> no news


def test_apify_non_list_raises() -> None:
    with pytest.raises(NewsSourceError):
        items_from_dataset({"not": "a list"})


def test_apify_bad_rows_dropped() -> None:
    bad = [{"title": ""}, {"no": "title"}, "string", {"title": "ok", "published": "garbage"}]
    assert items_from_dataset(bad) == []  # all unusable -> []


def test_parse_apify_dt_iso_and_rfc() -> None:
    assert _parse_apify_dt("2026-06-26T20:01:00Z") == datetime(2026, 6, 26, 20, 1, tzinfo=UTC)
    assert _parse_apify_dt("Fri, 26 Jun 2026 18:00:00 GMT") == datetime(
        2026, 6, 26, 18, 0, tzinfo=UTC
    )
    assert _parse_apify_dt("nonsense") is None
    assert _parse_apify_dt(None) is None


# ---------------------------------------------------------------- apify transport (fail-closed)


def test_apify_call_returns_items() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json=_DATASET)

    items = _src(handler)()
    assert len(items) == 2 and all(isinstance(i, NewsItem) for i in items)


def test_apify_non_2xx_fails_closed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "bad input"})

    with pytest.raises(NewsSourceError):
        _src(handler)()


def test_apify_transport_error_fails_closed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom with apify_tok in message")

    with pytest.raises(NewsSourceError) as ei:
        _src(handler)()
    assert "apify_tok" not in str(ei.value)  # token never in the error


def test_apify_empty_token_fails_closed() -> None:
    with pytest.raises(NewsSourceError):
        ApifyNewsSource("")


def test_apify_token_in_bearer_header_and_maxitems_floored() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("Authorization")
        seen["body"] = request.content.decode("utf-8")
        return httpx.Response(201, json=[])

    _src(handler, max_items=5)()  # below the 100 floor
    assert seen["auth"] == "Bearer apify_tok"
    body = json.loads(str(seen["body"]))
    assert body["maxItems"] == 100  # floored to the actor's minimum
    assert "apify_tok" not in str(seen["body"])


# ---------------------------------------------------------------- composite


def test_composite_returns_first_success() -> None:
    item = NewsItem(title="x", source="s", published_at=datetime(2026, 6, 26, tzinfo=UTC))
    calls = {"second": 0}

    def second() -> list[NewsItem]:
        calls["second"] += 1
        return []

    comp = CompositeNewsSource([lambda: [item], second])
    assert comp() == [item]
    assert calls["second"] == 0  # the fallback is NEVER reached when the primary succeeds


def test_composite_empty_is_a_success_not_a_fallthrough() -> None:
    calls = {"second": 0}

    def second() -> list[NewsItem]:
        calls["second"] += 1
        return []

    comp = CompositeNewsSource([lambda: [], second])
    assert comp() == []
    assert calls["second"] == 0  # "no news" is authoritative; never falls through to merge


def test_composite_falls_to_fallback_when_primary_raises() -> None:
    item = NewsItem(title="fb", source="s", published_at=datetime(2026, 6, 26, tzinfo=UTC))

    def primary() -> list[NewsItem]:
        raise NewsSourceError("primary down")

    comp = CompositeNewsSource([primary, lambda: [item]])
    assert comp() == [item]


def test_composite_all_fail_raises() -> None:
    def boom() -> list[NewsItem]:
        raise NewsSourceError("down")

    with pytest.raises(NewsSourceError):
        CompositeNewsSource([boom, boom])()


def test_composite_requires_a_source() -> None:
    with pytest.raises(NewsSourceError):
        CompositeNewsSource([])


# ---------------------------------------------------------------- factory


def test_factory_tavily_only() -> None:
    src = build_news_source(tavily_token="tv", apify_token=None)
    assert isinstance(src, HttpxTavilyNews)


def test_factory_apify_only() -> None:
    src = build_news_source(tavily_token=None, apify_token="ap")
    assert isinstance(src, ApifyNewsSource)


def test_factory_both_compose() -> None:
    src = build_news_source(tavily_token="tv", apify_token="ap")
    assert isinstance(src, CompositeNewsSource)


def test_factory_neither_is_none() -> None:
    assert build_news_source(tavily_token=None, apify_token=None) is None
