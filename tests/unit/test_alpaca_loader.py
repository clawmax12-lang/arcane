"""Tests for AlpacaBarLoader (Increment 2 STEP 6) — the only vendor surface.

The network is faked via an injected ``client`` (and a frozen ``now_fn``); the real fetch is
exercised by ``test_live_iex_daily_fetch_smoke`` behind ``@pytest.mark.live``, which the
gate excludes via ``addopts = -m 'not live'``. We assert the vendor adapter's guarantees:
the symbol MultiIndex level is dropped, µs timestamps become ns, every bar is asserted to be a
midnight-ET session instant (fail closed), ``ingest_ts`` is the DST-safe ``session_close +
publish_lag``, the request is EXPLICITLY IEX + adjustment=ALL (no silent SIP escalation /
unadjusted prices), the window end is clamped to ``now-16min`` (the IEX free-plan 403 foot-gun),
and every failure path (empty, None, vendor error, transport error, non-daily timeframe,
non-session / non-midnight bar) fails closed to a typed ``DataError``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest
import requests
from alpaca.common.enums import Sort
from alpaca.common.exceptions import APIError
from alpaca.data.enums import Adjustment, DataFeed
from alpaca.data.timeframe import TimeFrameUnit

from trading.data import calendar
from trading.data.alpaca_loader import AlpacaBarLoader
from trading.data.bar_schema import FEED_IEX
from trading.data.cache import ParquetCache
from trading.data.errors import CalendarError, DataFetchError
from trading.data.pit import AsOf
from trading.data.reliability import Reliability

_NOW = pd.Timestamp("2024-01-31 12:00", tz="UTC")  # frozen clock, safely in the past
_START = pd.Timestamp("2024-01-01", tz="UTC")
_END = pd.Timestamp("2024-01-31", tz="UTC")
_AS_OF = AsOf(datetime(2024, 1, 31, tzinfo=UTC))

_FINAL_COLUMNS = ["open", "high", "low", "close", "volume", "trade_count", "vwap", "ingest_ts"]


def _midnight_et_utc(date: str) -> pd.Timestamp:
    """Alpaca stamps a daily bar at midnight ET; express that instant in UTC."""
    return pd.Timestamp(f"{date} 00:00", tz="America/New_York").tz_convert("UTC")


def _alpaca_df(dates: list[str], symbol: str = "AAPL") -> pd.DataFrame:
    """Mimic ``barset.df``: MultiIndex (symbol, timestamp@µs/UTC) with raw float/int columns."""
    ts = pd.DatetimeIndex([_midnight_et_utc(d) for d in dates]).as_unit("us")
    n = len(dates)
    index = pd.MultiIndex.from_arrays([[symbol] * n, ts], names=["symbol", "timestamp"])
    return pd.DataFrame(
        {
            "open": [10.0 + i for i in range(n)],
            "high": [11.0 + i for i in range(n)],
            "low": [9.0 + i for i in range(n)],
            "close": [10.5 + i for i in range(n)],
            "volume": [100 + i for i in range(n)],
            "trade_count": [5 + i for i in range(n)],
            "vwap": [10.2 + i for i in range(n)],
        },
        index=index,
    )


class _FakeBarset:
    def __init__(self, df: pd.DataFrame | None) -> None:
        self.df = df


class _FakeClient:
    """Captures the last request; returns a preset barset or raises a preset error."""

    def __init__(self, *, df: pd.DataFrame | None = None, raises: Exception | None = None) -> None:
        self._df = df
        self._raises = raises
        self.last_request: object | None = None

    def get_stock_bars(self, request: object) -> _FakeBarset:
        self.last_request = request
        if self._raises is not None:
            raise self._raises
        return _FakeBarset(self._df)


def _loader(
    cache_dir: Path,
    *,
    df: pd.DataFrame | None = None,
    raises: Exception | None = None,
    now: pd.Timestamp = _NOW,
) -> AlpacaBarLoader:
    client = _FakeClient(df=df, raises=raises)
    return AlpacaBarLoader(ParquetCache(cache_dir), client=client, now_fn=lambda: now)


def test_happy_path_drops_symbol_and_converts(tmp_path: Path) -> None:
    df = _alpaca_df(["2024-01-03", "2024-01-04", "2024-01-05"])  # three real XNYS sessions
    res = _loader(tmp_path, df=df).load(symbol="AAPL", start=_START, end=_END, as_of=_AS_OF)
    out = res.frame.df
    assert len(out) == 3
    assert out.index.name == "ts"
    assert str(out.index.dtype) == "datetime64[ns, UTC]"  # µs -> ns conversion happened
    assert list(out.columns) == _FINAL_COLUMNS
    assert res.meta.feed == FEED_IEX
    assert res.meta.reliability is Reliability.HARD
    assert res.meta.row_count == 3


def test_ingest_ts_is_session_close_plus_publish_lag(tmp_path: Path) -> None:
    res = _loader(tmp_path, df=_alpaca_df(["2024-01-03"])).load(
        symbol="AAPL", start=_START, end=_END, as_of=_AS_OF
    )
    expected = calendar.session_close(pd.Timestamp("2024-01-03")) + pd.Timedelta(minutes=15)
    assert res.frame.df["ingest_ts"].iloc[0] == expected


def test_request_is_explicitly_iex_and_adjusted(tmp_path: Path) -> None:
    client = _FakeClient(df=_alpaca_df(["2024-01-03"]))
    loader = AlpacaBarLoader(ParquetCache(tmp_path), client=client, now_fn=lambda: _NOW)
    loader.load(symbol="AAPL", start=_START, end=_END, as_of=_AS_OF)
    req = client.last_request
    assert req.feed == DataFeed.IEX  # never None -> no silent SIP escalation
    assert req.adjustment == Adjustment.ALL  # never unadjusted
    assert req.sort == Sort.ASC
    assert req.symbol_or_symbols == "AAPL"
    assert req.limit is None  # SDK auto-paginates
    assert req.timeframe.amount == 1
    assert req.timeframe.unit == TimeFrameUnit.Day


def test_end_is_clamped_to_now_minus_16min(tmp_path: Path) -> None:
    now = pd.Timestamp("2024-01-10 12:00", tz="UTC")
    client = _FakeClient(df=_alpaca_df(["2024-01-03"]))
    loader = AlpacaBarLoader(ParquetCache(tmp_path), client=client, now_fn=lambda: now)
    loader.load(symbol="AAPL", start=_START, end=_END, as_of=_AS_OF)
    # alpaca-py strips tzinfo, storing a naive UTC wall-clock; compare on that basis.
    expected = (now - pd.Timedelta(minutes=16)).tz_localize(None)
    assert pd.Timestamp(client.last_request.end) == expected


def test_end_not_clamped_when_window_already_past(tmp_path: Path) -> None:
    now = pd.Timestamp("2024-06-01 12:00", tz="UTC")
    end = pd.Timestamp("2024-01-05", tz="UTC")
    client = _FakeClient(df=_alpaca_df(["2024-01-03"]))
    loader = AlpacaBarLoader(ParquetCache(tmp_path), client=client, now_fn=lambda: now)
    loader.load(symbol="AAPL", start=_START, end=end, as_of=_AS_OF)
    assert pd.Timestamp(client.last_request.end) == end.tz_localize(None)


def test_non_daily_timeframe_rejected(tmp_path: Path) -> None:
    loader = _loader(tmp_path, df=_alpaca_df(["2024-01-03"]))
    with pytest.raises(DataFetchError, match="1Day"):
        loader.load(symbol="AAPL", start=_START, end=_END, as_of=_AS_OF, timeframe="1Min")


def test_empty_result_fails_closed(tmp_path: Path) -> None:
    loader = _loader(tmp_path, df=_alpaca_df([]))
    with pytest.raises(DataFetchError, match="no IEX bars"):
        loader.load(symbol="AAPL", start=_START, end=_END, as_of=_AS_OF)


def test_none_df_fails_closed(tmp_path: Path) -> None:
    loader = _loader(tmp_path, df=None)
    with pytest.raises(DataFetchError, match="no IEX bars"):
        loader.load(symbol="AAPL", start=_START, end=_END, as_of=_AS_OF)


def test_vendor_api_error_wrapped(tmp_path: Path) -> None:
    loader = _loader(tmp_path, raises=APIError("rate limited"))
    with pytest.raises(DataFetchError, match="alpaca fetch failed"):
        loader.load(symbol="AAPL", start=_START, end=_END, as_of=_AS_OF)


def test_transport_error_wrapped(tmp_path: Path) -> None:
    # alpaca-py 0.43.4 uses the `requests` transport — a live network failure raises
    # requests.exceptions.ConnectionError, which must fail closed to DataFetchError.
    loader = _loader(tmp_path, raises=requests.exceptions.ConnectionError("dns failure"))
    with pytest.raises(DataFetchError, match="alpaca fetch failed"):
        loader.load(symbol="AAPL", start=_START, end=_END, as_of=_AS_OF)


def test_non_session_bar_fails_closed(tmp_path: Path) -> None:
    # A weekend bar must NOT be silently dropped — it must fail closed (vendor anomaly).
    loader = _loader(tmp_path, df=_alpaca_df(["2024-01-03", "2024-01-06"]))  # 01-06 = Saturday
    with pytest.raises(CalendarError, match="non-session"):
        loader.load(symbol="AAPL", start=_START, end=_END, as_of=_AS_OF)


def test_non_midnight_bar_fails_closed(tmp_path: Path) -> None:
    # A daily bar not stamped at midnight-ET signals vendor-convention drift -> fail closed.
    df = _alpaca_df(["2024-01-03"])
    bad = pd.Timestamp("2024-01-03 12:00", tz="America/New_York").tz_convert("UTC")
    df.index = pd.MultiIndex.from_arrays(
        [["AAPL"], pd.DatetimeIndex([bad]).as_unit("us")], names=["symbol", "timestamp"]
    )
    with pytest.raises(CalendarError, match="midnight-ET"):
        _loader(tmp_path, df=df).load(symbol="AAPL", start=_START, end=_END, as_of=_AS_OF)


@pytest.mark.live
def test_live_iex_daily_fetch_smoke(tmp_path: Path) -> None:
    """Operator-run only (``pytest -m live``): hits the real Alpaca IEX feed; needs .env creds."""
    loader = AlpacaBarLoader(ParquetCache(tmp_path))
    res = loader.load(
        symbol="AAPL",
        start=pd.Timestamp("2024-01-02", tz="UTC"),
        end=pd.Timestamp("2024-01-31", tz="UTC"),
        as_of=AsOf(datetime.now(UTC)),
    )
    assert res.meta.feed == FEED_IEX
    assert res.meta.row_count > 0
    assert bool(res.frame.df["close"].gt(0).all())
