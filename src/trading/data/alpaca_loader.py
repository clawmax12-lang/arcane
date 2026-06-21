"""AlpacaBarLoader — the only vendor surface; verified against the live alpaca-py 0.43.4 API.

Daily bars only (v1). ``feed=IEX`` and ``adjustment=ALL`` are EXPLICIT (never None → no silent
SIP-escalation / unadjusted-prices). Empty results or vendor/transport errors fail closed to
``DataFetchError``. The real daily-bar timestamp is midnight-ET at MICROSECOND resolution; we
convert to ns (the schema's unit), assert every bar is a midnight-ET XNYS session instant (fail
closed — a wrong-session vintage would be a look-ahead leak), and stamp ``ingest_ts`` as
``session_close + publish_lag`` (DST-safe via the calendar). The base re-derives every other
guard (dtype coercion, PIT drop, quality gate, schema), so this stays a thin vendor adapter.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pandas as pd
import requests
from alpaca.common.enums import Sort
from alpaca.common.exceptions import APIError
from alpaca.data.enums import Adjustment, DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

from trading.data import calendar
from trading.data.errors import DataFetchError
from trading.data.loader import DataLoader, LoadParams
from trading.settings import Settings, load_settings

_BAR_COLUMNS = ["open", "high", "low", "close", "volume", "trade_count", "vwap"]


class AlpacaBarLoader(DataLoader):
    """Loads daily OHLCV bars from Alpaca's IEX feed. Only ``_fetch`` touches the vendor."""

    PUBLISH_LAG = timedelta(minutes=15)  # a daily bar is available shortly after session close

    def __init__(
        self,
        cache: Any,
        *,
        settings: Settings | None = None,
        client: Any | None = None,
        now_fn: Callable[[], pd.Timestamp] | None = None,
    ) -> None:
        super().__init__(cache)
        self._settings = settings
        self._client = client
        self._now = now_fn or (lambda: pd.Timestamp.now(tz="UTC"))

    def _get_client(self) -> Any:
        if self._client is None:
            s = self._settings or load_settings()
            self._client = StockHistoricalDataClient(
                api_key=s.required["APCA_API_KEY_ID"],
                secret_key=s.required["APCA_API_SECRET_KEY"],
                raw_data=False,  # NO paper arg — market data has no paper/live distinction
            )
        return self._client

    def _fetch(self, p: LoadParams) -> pd.DataFrame:
        if p.timeframe != "1Day":
            raise DataFetchError(f"AlpacaBarLoader v1 supports only '1Day', got {p.timeframe!r}")
        # IEX free plan rejects data within ~15 min of now -> clamp the window end.
        end = min(p.end, self._now() - pd.Timedelta(minutes=16))
        req = StockBarsRequest(
            symbol_or_symbols=p.symbol,
            timeframe=TimeFrame(1, TimeFrameUnit.Day),
            start=p.start.to_pydatetime(),
            end=end.to_pydatetime(),
            adjustment=Adjustment.ALL,
            feed=DataFeed.IEX,
            sort=Sort.ASC,
            limit=None,
        )
        try:
            barset = self._get_client().get_stock_bars(req)
        except (APIError, requests.exceptions.RequestException) as exc:
            raise DataFetchError(f"alpaca fetch failed for {p.symbol}: {exc}") from exc

        df = barset.df
        if df is None or len(df) == 0:
            raise DataFetchError(f"no IEX bars for {p.symbol} in [{p.start}, {end}]")

        if isinstance(df.index, pd.MultiIndex):
            df = df.droplevel("symbol")
        df.index = pd.DatetimeIndex(df.index).as_unit("ns")  # real data is us; schema wants ns
        df.index.name = "ts"
        df = df[_BAR_COLUMNS]
        # Fail closed on vendor-convention drift: every daily bar must be a midnight-ET XNYS
        # session instant. We ASSERT (never silently drop) so a wrong-session vintage — which would
        # be a look-ahead leak — is loud. Raises CalendarError on a non-midnight or non-session bar.
        for ts in df.index:
            calendar.session_label_for_daily_bar(ts)
        return df

    def _stamp_ingest_ts(self, df: pd.DataFrame, p: LoadParams) -> pd.DataFrame:
        # A daily bar becomes visible at its session close (+ publish lag), DST-safe via calendar.
        closes = [
            calendar.session_close(calendar.session_label_for_daily_bar(ts)) + self.PUBLISH_LAG
            for ts in df.index
        ]
        out = df.copy()
        ingest = pd.DatetimeIndex(closes).as_unit("ns")
        if ingest.tz is None:  # defensive: an empty list yields tz-naive; keep the column tz-aware
            ingest = ingest.tz_localize("UTC")
        out["ingest_ts"] = ingest
        return out
