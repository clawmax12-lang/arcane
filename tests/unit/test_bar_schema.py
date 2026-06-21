"""Tests for the canonical bar schema + BarMeta (Increment 2 STEP 2)."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime

import pandas as pd
import pytest

from trading.data.bar_schema import (
    FEED_IEX,
    BarMeta,
    assert_feed,
    validate_bars,
)
from trading.data.errors import FeedMismatchError, SchemaError
from trading.data.reliability import Reliability


def _valid_bars(n: int = 2) -> pd.DataFrame:
    ts = pd.to_datetime([f"2024-07-01 13:3{i}:00" for i in range(n)], utc=True).as_unit("ns")
    ingest = pd.to_datetime([f"2024-07-01 13:3{i + 1}:00" for i in range(n)], utc=True).as_unit(
        "ns"
    )
    df = pd.DataFrame(
        {
            "open": [10.0 + i for i in range(n)],
            "high": [10.6 + i for i in range(n)],
            "low": [9.9 + i for i in range(n)],
            "close": [10.5 + i for i in range(n)],
            "volume": [100 + i for i in range(n)],
            "trade_count": [5 + i for i in range(n)],
            "vwap": [10.2 + i for i in range(n)],
            "ingest_ts": ingest,
        },
        index=pd.DatetimeIndex(ts, name="ts"),
    )
    return df.astype(
        {
            "open": "Float64",
            "high": "Float64",
            "low": "Float64",
            "close": "Float64",
            "volume": "Int64",
            "trade_count": "Int64",
            "vwap": "Float64",
        }
    )


def _meta(feed: str = FEED_IEX) -> BarMeta:
    return BarMeta(
        symbol="AAPL",
        timeframe="1Day",
        feed=feed,
        adjustment="all",
        reliability=Reliability.HARD,
        as_of=datetime(2024, 7, 2, tzinfo=UTC),
        survivorship_unverified=True,
        is_sip_consolidated=False,
        publish_lag_seconds=86400.0,
        cache_key="arcane-bars-deadbeef",
        row_count=2,
    )


def test_valid_bars_pass() -> None:
    validate_bars(_valid_bars())  # must not raise


def test_extra_column_rejected() -> None:
    df = _valid_bars()
    df["sneaky"] = 1
    with pytest.raises(SchemaError):
        validate_bars(df)


def test_null_close_rejected() -> None:
    df = _valid_bars()
    df.loc[df.index[0], "close"] = pd.NA
    with pytest.raises(SchemaError):
        validate_bars(df)


def test_negative_price_rejected() -> None:
    df = _valid_bars()
    df.loc[df.index[0], "low"] = -1.0
    with pytest.raises(SchemaError):
        validate_bars(df)


def test_ohlc_violation_rejected() -> None:
    df = _valid_bars()
    df.loc[df.index[0], "high"] = 0.0  # high < open -> OHLC inconsistency
    with pytest.raises(SchemaError):
        validate_bars(df)


def test_wrong_dtype_rejected() -> None:
    df = _valid_bars().astype({"close": "object"})  # object dtype must be rejected (coerce=False)
    with pytest.raises(SchemaError):
        validate_bars(df)


def test_tz_naive_index_rejected() -> None:
    df = _valid_bars()
    df.index = df.index.tz_localize(None)
    with pytest.raises(SchemaError):
        validate_bars(df)


def test_duplicate_index_rejected() -> None:
    df = _valid_bars(2)
    df = pd.concat([df, df.iloc[[0]]])
    with pytest.raises(SchemaError):
        validate_bars(df)


def test_assert_feed_ok_and_mismatch() -> None:
    assert_feed(_meta(feed="iex"), "iex")  # must not raise
    with pytest.raises(FeedMismatchError):
        assert_feed(_meta(feed="iex"), "sip")


def test_barmeta_is_frozen() -> None:
    meta = _meta()
    with pytest.raises(dataclasses.FrozenInstanceError):
        meta.feed = "sip"  # type: ignore[misc]
