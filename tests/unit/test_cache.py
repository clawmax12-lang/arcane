"""Tests for the content-addressed Parquet cache (Increment 2 STEP 4)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from trading.data.cache import ParquetCache, cache_key
from trading.data.errors import CacheError


def _bars(n: int = 3, offset: float = 0.0) -> pd.DataFrame:
    ts = pd.to_datetime([f"2024-07-01 13:3{i}:00" for i in range(n)], utc=True).as_unit("ns")
    df = pd.DataFrame(
        {
            "open": [10.0 + i + offset for i in range(n)],
            "high": [10.6 + i + offset for i in range(n)],
            "low": [9.9 + i + offset for i in range(n)],
            "close": [10.5 + i + offset for i in range(n)],
            "volume": [100 + i for i in range(n)],
            "trade_count": [5 + i for i in range(n)],
            "vwap": [10.2 + i + offset for i in range(n)],
            "ingest_ts": ts,
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


def _parquet_size(df: pd.DataFrame, tmp: Path) -> int:
    p = tmp / "probe.parquet"
    df.to_parquet(p, engine="pyarrow", index=True)
    size = p.stat().st_size
    p.unlink()
    return size


def test_cache_key_deterministic_and_param_sensitive() -> None:
    a = cache_key({"symbol": "AAPL", "feed": "iex", "adjustment": "all"})
    b = cache_key({"feed": "iex", "adjustment": "all", "symbol": "AAPL"})  # order-insensitive
    c = cache_key({"symbol": "AAPL", "feed": "sip", "adjustment": "all"})  # feed -> different key
    assert a == b
    assert a != c
    assert a.startswith("arcane-bars-")


def test_round_trip_preserves_frame(tmp_path: Path) -> None:
    cache = ParquetCache(tmp_path)
    df = _bars(3)
    cache.put("k1", df)
    got = cache.get("k1")
    assert got is not None
    pd.testing.assert_frame_equal(got, df)


def test_miss_returns_none(tmp_path: Path) -> None:
    assert ParquetCache(tmp_path).get("absent") is None


def test_corrupt_file_is_miss_and_self_heals(tmp_path: Path) -> None:
    cache = ParquetCache(tmp_path)
    cache.put("k1", _bars(2))
    (tmp_path / "k1.parquet").write_bytes(b"not a parquet file")
    assert cache.get("k1") is None
    assert not (tmp_path / "k1.parquet").exists()  # self-healed


def test_validation_failure_is_miss(tmp_path: Path) -> None:
    cache = ParquetCache(tmp_path)
    cache.put("k1", _bars(2))

    def reject(_df: pd.DataFrame) -> None:
        raise ValueError("schema invalid")

    assert cache.get("k1", validate=reject) is None


def test_oversize_object_refused(tmp_path: Path) -> None:
    cache = ParquetCache(tmp_path, max_bytes=10)
    try:
        cache.put("k1", _bars(3))
        raised = False
    except CacheError:
        raised = True
    assert raised
    assert not (tmp_path / "k1.parquet").exists()


def test_lru_eviction_keeps_under_ceiling(tmp_path: Path) -> None:
    size = _parquet_size(_bars(3, 0.0), tmp_path)
    times = iter([float(i) for i in range(1, 100)])
    cache = ParquetCache(tmp_path, max_bytes=int(size * 2.5), clock=lambda: next(times))
    cache.put("A", _bars(3, 0.0))  # access t=1
    cache.put("B", _bars(3, 1.0))  # access t=2
    cache.get("A")  # touch A -> t=3 (B is now least-recently-accessed)
    cache.put("C", _bars(3, 2.0))  # t=4: total 3*size > 2.5*size -> evict LRU (B)
    assert (tmp_path / "A.parquet").exists()
    assert (tmp_path / "C.parquet").exists()
    assert not (tmp_path / "B.parquet").exists()


def test_reconcile_removes_orphans(tmp_path: Path) -> None:
    cache = ParquetCache(tmp_path)
    cache.put("k1", _bars(2))
    (tmp_path / "orphan.parquet").write_bytes(b"x")  # file with no manifest row
    ParquetCache(tmp_path)  # re-open triggers reconcile
    assert not (tmp_path / "orphan.parquet").exists()


def test_reconcile_cleans_tmp_orphans(tmp_path: Path) -> None:
    ParquetCache(tmp_path)
    orphan = tmp_path / "arcane-bars-zzz.parquet.tmp"  # crash-mid-put leftover
    orphan.write_bytes(b"partial")
    ParquetCache(tmp_path)  # re-open triggers reconcile
    assert not orphan.exists()


def test_put_pauses_when_disk_low(tmp_path: Path) -> None:
    # ADR-F7: with the free-disk floor set above any real free space, put() skips the write.
    cache = ParquetCache(tmp_path, min_free_bytes=10**18)
    cache.put("k1", _bars(2))
    assert cache.get("k1") is None  # not stored
    assert not (tmp_path / "k1.parquet").exists()
    assert not (tmp_path / "k1.parquet.tmp").exists()  # and no tmp left behind
