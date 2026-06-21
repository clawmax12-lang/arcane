"""Canonical OHLCV bar schema (pandera, strict, fail-closed) + ``BarMeta`` provenance.

The schema enforces dtypes, non-null, ``ge=0``, column order, a unique tz-aware UTC index,
and the OHLC cross-field invariant. Finiteness (``inf``) is deliberately NOT enforced here —
pandera ``ge(0)`` admits ``inf`` and NaN compares False to everything (the Inc-1 trap) — so
the quality gate (``data/quality.py``) runs ``np.isfinite`` FIRST. ``BarMeta`` travels
end-to-end so a frame's provenance (feed, adjustment, reliability, survivorship) cannot be
stripped, and the loud ``FEED_IEX`` stamp makes the thin-IEX-coverage caveat explicit.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final

import pandas as pd
import pandera.pandas as pa
from pandera.errors import SchemaError as PanderaSchemaError
from pandera.errors import SchemaErrors as PanderaSchemaErrors

from trading.data.errors import FeedMismatchError, SchemaError
from trading.data.reliability import Reliability

FEED_IEX: Final[str] = "iex"
ADJUSTMENT_ALL: Final[str] = "all"

UTC_DTYPE: Final[str] = "datetime64[ns, UTC]"


def _ohlc_consistent(df: pd.DataFrame) -> pd.Series:
    high_ok = df["high"] >= df[["open", "close", "low"]].max(axis=1)
    low_ok = df["low"] <= df[["open", "close", "high"]].min(axis=1)
    return high_ok & low_ok


BAR_SCHEMA: Final[pa.DataFrameSchema] = pa.DataFrameSchema(
    columns={
        "open": pa.Column("Float64", pa.Check.ge(0), nullable=False),
        "high": pa.Column("Float64", pa.Check.ge(0), nullable=False),
        "low": pa.Column("Float64", pa.Check.ge(0), nullable=False),
        "close": pa.Column("Float64", pa.Check.ge(0), nullable=False),
        "volume": pa.Column("Int64", pa.Check.ge(0), nullable=False),
        "trade_count": pa.Column("Int64", pa.Check.ge(0), nullable=False),
        "vwap": pa.Column("Float64", pa.Check.ge(0), nullable=True),
        "ingest_ts": pa.Column(UTC_DTYPE, nullable=False),
    },
    index=pa.Index(UTC_DTYPE, name="ts", unique=True),
    checks=pa.Check(_ohlc_consistent, name="ohlc_consistency"),
    strict=True,
    ordered=True,
    coerce=False,
)


def validate_bars(df: pd.DataFrame) -> pd.DataFrame:
    """Validate a bar frame against the canonical schema; raise ``SchemaError`` on failure."""
    try:
        return BAR_SCHEMA.validate(df, lazy=False)
    except (PanderaSchemaError, PanderaSchemaErrors) as exc:
        raise SchemaError(f"bar schema validation failed: {exc}") from exc


@dataclass(frozen=True, slots=True)
class BarMeta:
    """Immutable provenance for a bar frame — travels end-to-end and cannot be stripped."""

    symbol: str
    timeframe: str
    feed: str
    adjustment: str
    reliability: Reliability
    as_of: datetime
    survivorship_unverified: bool
    is_sip_consolidated: bool
    publish_lag_seconds: float
    cache_key: str
    row_count: int


def assert_feed(meta: BarMeta, requested_feed: str) -> None:
    """Fail closed if a frame's feed tag does not match the requested feed (IEX vs SIP)."""
    if meta.feed != requested_feed:
        raise FeedMismatchError(f"bar feed {meta.feed!r} != requested {requested_feed!r}")
