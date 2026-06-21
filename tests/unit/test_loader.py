"""Tests for the FINAL DataLoader structural pipeline (Increment 2 STEP 5)."""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest
from pydantic import TypeAdapter

from trading.data.cache import ParquetCache
from trading.data.loader import DataLoader, LoadParams
from trading.data.pit import AsOf
from trading.data.reliability import Reliability

_START = pd.Timestamp("2024-07-01", tz="UTC")
_END = pd.Timestamp("2024-07-10", tz="UTC")


def _raw_daily(n: int = 5) -> pd.DataFrame:
    idx = pd.date_range("2024-07-01", periods=n, freq="D", tz="UTC", name="ts").as_unit("ns")
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
        index=idx,
    )


class _FakeLoader(DataLoader):
    def __init__(self, cache: ParquetCache) -> None:
        super().__init__(cache)
        self.fetch_calls = 0

    def _fetch(self, p: LoadParams) -> pd.DataFrame:
        self.fetch_calls += 1
        return _raw_daily(5)


def test_load_requires_as_of(tmp_path: Path) -> None:
    loader = _FakeLoader(ParquetCache(tmp_path))
    with pytest.raises(TypeError):
        loader.load(symbol="AAPL", start=_START, end=_END)  # type: ignore[call-arg]


def test_pit_drops_future_bars(tmp_path: Path) -> None:
    loader = _FakeLoader(ParquetCache(tmp_path))
    as_of = AsOf(datetime(2024, 7, 3, tzinfo=UTC))
    res = loader.load(symbol="AAPL", start=_START, end=_END, as_of=as_of)
    df = res.frame.df
    # ingest_ts = ts + 1 day; as_of 07-03 keeps 07-01 (ing 07-02) and 07-02 (ing 07-03).
    assert len(df) == 2
    assert df["ingest_ts"].max() <= pd.Timestamp(as_of.ts)


def test_cache_hit_skips_fetch(tmp_path: Path) -> None:
    loader = _FakeLoader(ParquetCache(tmp_path))
    as_of = AsOf(datetime(2024, 7, 9, tzinfo=UTC))
    loader.load(symbol="AAPL", start=_START, end=_END, as_of=as_of)
    loader.load(symbol="AAPL", start=_START, end=_END, as_of=as_of)
    assert loader.fetch_calls == 1  # second call served from cache


def test_immutable_frame_isolation(tmp_path: Path) -> None:
    loader = _FakeLoader(ParquetCache(tmp_path))
    res = loader.load(
        symbol="AAPL", start=_START, end=_END, as_of=AsOf(datetime(2024, 7, 9, tzinfo=UTC))
    )
    first = res.frame.df
    first.loc[first.index[0], "close"] = 999.0  # mutate the caller's copy
    assert res.frame.df.loc[res.frame.df.index[0], "close"] != 999.0  # wrapped data untouched


def test_meta_provenance(tmp_path: Path) -> None:
    loader = _FakeLoader(ParquetCache(tmp_path))
    res = loader.load(
        symbol="AAPL", start=_START, end=_END, as_of=AsOf(datetime(2024, 7, 9, tzinfo=UTC))
    )
    assert res.meta.feed == "iex"
    assert res.meta.reliability is Reliability.HARD
    assert res.meta.survivorship_unverified is True
    assert res.meta.is_sip_consolidated is False


def test_no_data_loader_subclass_overrides_load() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "trading" / "data"
    offenders: list[str] = []
    for py in root.glob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                bases = {b.id for b in node.bases if isinstance(b, ast.Name)}
                if "DataLoader" in bases:
                    methods = {
                        n.name
                        for n in node.body
                        if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)
                    }
                    if "load" in methods:
                        offenders.append(f"{py.name}:{node.name}")
    assert not offenders, f"@final load overridden in: {offenders}"


_PYDANTIC_DT = TypeAdapter(datetime)


def _vendor_tz_daily(n: int = 5) -> pd.DataFrame:
    """Like ``_raw_daily`` but with a pydantic ``TzInfo`` index, as alpaca-py returns."""
    stamps = [_PYDANTIC_DT.validate_python(f"2024-07-0{i + 1}T00:00:00Z") for i in range(n)]
    df = _raw_daily(n)
    df.index = pd.DatetimeIndex(stamps, name="ts").as_unit("ns")
    return df


class _VendorTzLoader(DataLoader):
    def _fetch(self, p: LoadParams) -> pd.DataFrame:
        return _vendor_tz_daily(5)


def test_non_canonical_vendor_utc_index_is_normalized(tmp_path: Path) -> None:
    """A pydantic-``TzInfo`` (alpaca-py) UTC index must validate, not be rejected by pandera.

    Pre-fix this raised SchemaError('expected datetime64[ns, UTC], got datetime64[ns, UTC]')
    because the vendor tz object != stdlib timezone.utc. Regression for the STEP 6 live bug.
    """
    loader = _VendorTzLoader(ParquetCache(tmp_path))
    res = loader.load(
        symbol="AAPL", start=_START, end=_END, as_of=AsOf(datetime(2024, 7, 9, tzinfo=UTC))
    )
    df = res.frame.df
    assert df.index.dtype == pd.api.types.pandas_dtype("datetime64[ns, UTC]")
    assert str(df["ingest_ts"].dtype) == "datetime64[ns, UTC]"
    assert len(df) == 5
