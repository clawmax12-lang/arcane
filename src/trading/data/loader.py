"""The FINAL ``DataLoader`` — the structural point-in-time data spine.

``load()`` is ``@final``: subclasses implement only ``_fetch``. After ``_fetch`` returns raw
vendor data, the base re-derives EVERY correctness property — dtype coercion, ``ingest_ts``
stamping, the PIT drop, calendar alignment, the quality gate, schema validation — so a buggy
or adversarial ``_fetch`` cannot open a leak. ``as_of`` is a required kw-only arg (omitting the
PIT clock is a ``TypeError``). Results are cached by content hash; cache reads re-validate.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import timedelta
from typing import Final, final

import pandas as pd

from trading.data import calendar
from trading.data.bar_schema import (
    ADJUSTMENT_ALL,
    FEED_IEX,
    BarMeta,
    validate_bars,
)
from trading.data.cache import ParquetCache, cache_key
from trading.data.errors import CalendarError, RestatedSourceError
from trading.data.pit import AsOf, pit_guard
from trading.data.quality import run_quality_gate
from trading.data.reliability import Reliability

_CANONICAL_DTYPES: Final[dict[str, str]] = {
    "open": "Float64",
    "high": "Float64",
    "low": "Float64",
    "close": "Float64",
    "volume": "Int64",
    "trade_count": "Int64",
    "vwap": "Float64",
}


@dataclass(frozen=True, slots=True)
class LoadParams:
    """Canonical, validated load parameters. The cache key is derived from ALL of them."""

    symbol: str
    timeframe: str
    start: pd.Timestamp
    end: pd.Timestamp
    as_of: AsOf
    feed: str
    adjustment: str
    session: str
    loader: str
    schema_version: int

    @staticmethod
    def build(
        *,
        symbol: str,
        timeframe: str,
        start: pd.Timestamp,
        end: pd.Timestamp,
        as_of: AsOf,
        feed: str,
        adjustment: str,
        session: str,
        loader: str,
        schema_version: int,
    ) -> LoadParams:
        s, e = pd.Timestamp(start), pd.Timestamp(end)
        if s.tz is None or e.tz is None:
            raise CalendarError("start/end must be tz-aware")
        if e < s:
            raise CalendarError(f"end {e} precedes start {s}")
        return LoadParams(
            symbol=symbol,
            timeframe=timeframe,
            start=s,
            end=e,
            as_of=as_of,
            feed=feed,
            adjustment=adjustment,
            session=session,
            loader=loader,
            schema_version=schema_version,
        )

    def key(self) -> str:
        return cache_key(
            {
                "symbol": self.symbol,
                "timeframe": self.timeframe,
                "start": self.start.isoformat(),
                "end": self.end.isoformat(),
                "as_of": self.as_of.ts.isoformat(),
                "feed": self.feed,
                "adjustment": self.adjustment,
                "session": self.session,
                "loader": self.loader,
                "schema_version": self.schema_version,
            }
        )


class ImmutableFrame:
    """Wraps a frame; ``.df`` returns a CoW copy so callers can't mutate the cached data."""

    __slots__ = ("_df",)

    def __init__(self, df: pd.DataFrame) -> None:
        owned = df.copy()
        owned.flags.allows_duplicate_labels = False
        self._df = owned

    @property
    def df(self) -> pd.DataFrame:
        return self._df.copy()


@dataclass(frozen=True, slots=True)
class LoadResult:
    frame: ImmutableFrame
    meta: BarMeta


class DataLoader(ABC):
    """Abstract loader. Subclasses implement only ``_fetch``; ``load`` is final and structural."""

    SCHEMA_VERSION: int = 1
    requires_pit_ingest_ts: bool = False
    PUBLISH_LAG: timedelta = timedelta(days=1)  # conservative default (one daily timeframe)

    def __init__(self, cache: ParquetCache) -> None:
        self._cache = cache

    @final
    def load(
        self,
        *,
        symbol: str,
        start: pd.Timestamp,
        end: pd.Timestamp,
        as_of: AsOf,
        timeframe: str = "1Day",
        feed: str = FEED_IEX,
        adjustment: str = ADJUSTMENT_ALL,
        session: str = "XNYS",
    ) -> LoadResult:
        p = LoadParams.build(
            symbol=symbol,
            timeframe=timeframe,
            start=start,
            end=end,
            as_of=as_of,
            feed=feed,
            adjustment=adjustment,
            session=session,
            loader=type(self).__name__,
            schema_version=self.SCHEMA_VERSION,
        )
        key = p.key()
        cached = self._cache.get(key, validate=validate_bars)
        if cached is not None:
            return LoadResult(frame=ImmutableFrame(cached), meta=self._meta(p, cached))

        df = self._coerce_dtypes(self._fetch(p))
        df = self._stamp_ingest_ts(df, p)
        df = pit_guard(df, p.as_of)
        df = self._align_calendar(df, p)
        df = run_quality_gate(df)
        validated = validate_bars(df)
        self._cache.put(key, validated)
        return LoadResult(frame=ImmutableFrame(validated), meta=self._meta(p, validated))

    @abstractmethod
    def _fetch(self, p: LoadParams) -> pd.DataFrame: ...

    def _align_calendar(self, df: pd.DataFrame, p: LoadParams) -> pd.DataFrame:
        """Default: assert UTC only. Timeframe-specific RTH/session filtering is a subclass hook."""
        calendar.assert_utc(df.index)
        return df

    def _coerce_dtypes(self, df: pd.DataFrame) -> pd.DataFrame:
        present = {c: t for c, t in _CANONICAL_DTYPES.items() if c in df.columns}
        return df.astype(present)

    def _stamp_ingest_ts(self, df: pd.DataFrame, p: LoadParams) -> pd.DataFrame:
        if "ingest_ts" in df.columns:
            if bool(df["ingest_ts"].isna().any()):
                raise RestatedSourceError("ingest_ts contains nulls")
            return df
        if self.requires_pit_ingest_ts:
            raise RestatedSourceError(
                f"{type(self).__name__} is a restated source and must supply per-row ingest_ts"
            )
        out = df.copy()
        out["ingest_ts"] = df.index + self.PUBLISH_LAG
        return out

    def _meta(self, p: LoadParams, df: pd.DataFrame) -> BarMeta:
        return BarMeta(
            symbol=p.symbol,
            timeframe=p.timeframe,
            feed=p.feed,
            adjustment=p.adjustment,
            reliability=Reliability.HARD,
            as_of=p.as_of.ts,
            survivorship_unverified=True,
            is_sip_consolidated=(p.feed == "sip"),
            publish_lag_seconds=self.PUBLISH_LAG.total_seconds(),
            cache_key=p.key(),
            row_count=len(df),
        )
