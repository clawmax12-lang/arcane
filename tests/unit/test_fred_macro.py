"""C3 — FredMacroSource fail-closed macro summary (Increment 8.6 PART A).

Fakes mirror the REAL FRED ``/fred/series/observations`` shape (live-probed this session):
``{"observations": [{"date": "2026-06-25", "value": "4.4"}, …]}`` sorted desc. Any series transport/
HTTP/parse failure, or no recent numeric observation, fails closed (``MacroSourceError``). The key
lives in the ``api_key`` query param ONLY and never appears in an error.
"""

from __future__ import annotations

import httpx
import pytest

from trading.slowloop.sources.errors import MacroSourceError
from trading.slowloop.sources.factory import build_market_summary_source
from trading.slowloop.sources.fred_macro import FredMacroSource

# Real-shaped FRED responses keyed by series_id (latest desc).
_FRED = {
    "DGS10": [{"date": "2026-06-25", "value": "4.40"}],
    "DGS2": [{"date": "2026-06-25", "value": "4.09"}],
    "T10Y2Y": [{"date": "2026-06-26", "value": "0.31"}],
    "VIXCLS": [{"date": "2026-06-25", "value": "18.89"}],
    "DFF": [{"date": "2026-06-25", "value": "3.63"}],
}


def _handler_for(table: dict[str, list[dict[str, str]]]) -> object:
    def handler(request: httpx.Request) -> httpx.Response:
        sid = request.url.params.get("series_id")
        return httpx.Response(200, json={"observations": table.get(sid or "", [])})

    return handler


def _src(handler: object, **kw: object) -> FredMacroSource:
    return FredMacroSource(
        "fred_key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),  # type: ignore[arg-type]
        sleeper=lambda _f: None,
        **kw,  # type: ignore[arg-type]
    )


def test_builds_a_compact_summary() -> None:
    summary = _src(_handler_for(_FRED))()
    assert summary.startswith("Makroläge (FRED, 2026-06-26)")  # newest obs date across the set
    assert "10y 4.40%" in summary
    assert "10y-2y +0.31" in summary  # signed for the curve
    assert "VIX 18.89" in summary
    assert "styrränta 3.63%" in summary


def test_skips_missing_dot_values_to_the_next_observation() -> None:
    table = dict(_FRED)
    table["VIXCLS"] = [
        {"date": "2026-06-27", "value": "."},  # weekend placeholder
        {"date": "2026-06-25", "value": "18.89"},
    ]
    summary = _src(_handler_for(table))()
    assert "VIX 18.89" in summary  # the "." was skipped to the most recent numeric value


def test_no_numeric_observation_fails_closed() -> None:
    table = dict(_FRED)
    table["DGS10"] = [{"date": "2026-06-27", "value": "."}]
    with pytest.raises(MacroSourceError):
        _src(_handler_for(table))()


def test_non_2xx_fails_closed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate"})

    with pytest.raises(MacroSourceError):
        _src(handler)()


def test_transport_error_is_token_free() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("failed with fred_key in the message")

    with pytest.raises(MacroSourceError) as ei:
        _src(handler)()
    assert "fred_key" not in str(ei.value)


def test_api_key_is_in_params_not_in_an_error() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["has_key"] = "api_key" in request.url.params
        return httpx.Response(200, json={"observations": _FRED["DGS10"]})

    _src(handler, series=(("DGS10", "10y", "%"),))()
    assert seen["has_key"] is True


def test_empty_token_fails_closed() -> None:
    with pytest.raises(MacroSourceError):
        FredMacroSource("")


def test_factory_builds_or_skips_on_key() -> None:
    assert build_market_summary_source(fred_token=None) is None
    src = build_market_summary_source(fred_token="fred_key")
    assert isinstance(src, FredMacroSource)
