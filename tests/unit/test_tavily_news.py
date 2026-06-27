"""C1 — HttpxTavilyNews fail-closed adapter (Increment 8.6 PART A, PRIMARY).

Fakes mirror the REAL Tavily ``/search`` response shape (live-probed this session): a 200 with a
``results`` list of ``{title, url, content, published_date(RFC-2822), raw_content, score}``. Every
transport/HTTP/shape failure aborts the WHOLE fetch (``NewsSourceError``); an empty ``results`` is a
valid "no news" (``[]``); a single malformed ROW is dropped (never a fabricated timestamp).
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from trading.slowloop.agents.news import NewsItem
from trading.slowloop.sources.errors import NewsSourceError
from trading.slowloop.sources.tavily_news import (
    HttpxTavilyNews,
    _domain,
    _parse_rfc2822,
    items_from_results,
)

# Real-shaped Tavily results (the exact keys returned live this session).
_REAL_RESULTS = {
    "results": [
        {
            "title": "Stock market today: S&P 500, Nasdaq snap 2-week win streak",
            "url": "https://finance.yahoo.com/markets/live/stock-market-today",
            "content": "Stocks fell as AI jitters pressured tech.",
            "published_date": "Fri, 26 Jun 2026 20:01:39 GMT",
            "raw_content": None,
            "score": 0.91,
        },
        {
            "title": "Gold prices today: reversal of trend, strong recovery",
            "url": "https://www.investopedia.com/gold-today",
            "content": "Gold recovered.",
            "published_date": "Sat, 27 Jun 2026 04:30:14 GMT",
            "raw_content": None,
            "score": 0.74,
        },
    ]
}


def _client(handler: object) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))  # type: ignore[arg-type]


def _ok_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=_REAL_RESULTS)


def _src(handler: object, **kw: object) -> HttpxTavilyNews:
    return HttpxTavilyNews(
        "tok123", client=_client(handler), sleeper=lambda _f: None, **kw  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------- pure mapping


def test_items_from_real_results() -> None:
    items = items_from_results(_REAL_RESULTS)
    assert len(items) == 2
    assert items[0].title.startswith("Stock market today")  # RAW title preserved (not sanitized)
    assert items[0].source == "finance.yahoo.com"  # www-stripped host
    assert items[0].published_at == datetime(2026, 6, 26, 20, 1, 39, tzinfo=UTC)


def test_empty_results_is_valid_no_news() -> None:
    assert items_from_results({"results": []}) == []


def test_non_dict_payload_raises() -> None:
    with pytest.raises(NewsSourceError):
        items_from_results([1, 2, 3])


def test_missing_results_list_raises() -> None:
    with pytest.raises(NewsSourceError):
        items_from_results({"answer": "no results key"})


def test_bad_title_row_is_dropped_not_raised() -> None:
    payload = {
        "results": [
            {
                "title": "",
                "url": "https://x.com",
                "published_date": "Fri, 26 Jun 2026 20:01:39 GMT",
            },
            {
                "title": 123,
                "url": "https://y.com",
                "published_date": "Fri, 26 Jun 2026 20:01:39 GMT",
            },
            {
                "title": "good one",
                "url": "https://reuters.com/a",
                "published_date": "Fri, 26 Jun 2026 20:01:39 GMT",
            },
        ]
    }
    items = items_from_results(payload)
    assert [i.title for i in items] == ["good one"]  # only the well-formed row survives


def test_unparseable_date_row_is_dropped_never_fabricated() -> None:
    payload = {
        "results": [
            {"title": "no date", "url": "https://x.com", "published_date": "not-a-date"},
            {"title": "null date", "url": "https://x.com", "published_date": None},
            {
                "title": "dated",
                "url": "https://x.com",
                "published_date": "Fri, 26 Jun 2026 20:01:39 GMT",
            },
        ]
    }
    items = items_from_results(payload)
    assert [i.title for i in items] == ["dated"]  # dateless rows dropped, never now()-stamped


def test_all_rows_bad_yields_empty_list() -> None:
    payload = {"results": [{"title": "x", "published_date": "garbage"}, "not-a-dict"]}
    assert items_from_results(payload) == []


def test_parse_rfc2822_aware_utc_and_offset_conversion() -> None:
    assert _parse_rfc2822("Fri, 26 Jun 2026 20:01:39 GMT") == datetime(
        2026, 6, 26, 20, 1, 39, tzinfo=UTC
    )
    # an offset date is converted to UTC
    assert _parse_rfc2822("Fri, 26 Jun 2026 22:01:39 +0200") == datetime(
        2026, 6, 26, 20, 1, 39, tzinfo=UTC
    )
    assert _parse_rfc2822("") is None
    assert _parse_rfc2822("nonsense") is None


def test_domain_strips_www_and_is_total() -> None:
    assert _domain("https://www.reuters.com/markets/x") == "reuters.com"
    assert _domain("https://ca.finance.yahoo.com/news") == "ca.finance.yahoo.com"
    assert _domain(None) == "unknown"
    assert _domain("not a url") == "unknown"


# ---------------------------------------------------------------- transport (fail-closed)


def test_call_returns_items_on_200() -> None:
    items = _src(_ok_handler)()
    assert len(items) == 2 and all(isinstance(i, NewsItem) for i in items)


def test_non_2xx_fails_closed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate limited"})

    with pytest.raises(NewsSourceError) as ei:
        _src(handler)()
    assert "429" in str(ei.value)


def test_malformed_json_fails_closed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"{not valid json")

    with pytest.raises(NewsSourceError):
        _src(handler)()


def test_transport_error_fails_closed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with pytest.raises(NewsSourceError):
        _src(handler)()


def test_empty_token_fails_closed() -> None:
    with pytest.raises(NewsSourceError):
        HttpxTavilyNews("")


# ---------------------------------------------------------------- token discipline


def test_token_is_in_the_bearer_header_only() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("Authorization")
        seen["body"] = request.content.decode("utf-8")
        seen["url"] = str(request.url)
        return httpx.Response(200, json=_REAL_RESULTS)

    _src(handler)()
    assert seen["auth"] == "Bearer tok123"
    assert "tok123" not in str(seen["body"])  # never in the request body
    assert "tok123" not in str(seen["url"])  # never in the URL/query


def test_token_bearing_transport_error_is_type_only() -> None:
    # An exception whose message embeds the token must surface only the exception TYPE.
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("auth failed for Bearer tok123 SUPERSECRET")

    with pytest.raises(NewsSourceError) as ei:
        _src(handler)()
    assert "tok123" not in str(ei.value)
    assert "SUPERSECRET" not in str(ei.value)


def test_throttle_spaces_calls_via_injected_clock() -> None:
    slept: list[float] = []
    t = {"now": 0.0}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": []})

    src = HttpxTavilyNews(
        "tok",
        client=_client(handler),
        min_interval_s=12.0,
        sleeper=lambda s: slept.append(s),
        clock=lambda: t["now"],
    )
    src()  # first call: no sleep
    assert slept == []
    src()  # second call at the same clock time: must sleep ~12s (the full interval)
    assert slept and abs(slept[0] - 12.0) < 1e-9
