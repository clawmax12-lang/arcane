"""Content-addressed Parquet cache with a byte-capped LRU (SQLite manifest).

The key is a SHA-256 over EVERY data-affecting parameter, so an IEX frame can never serve a
SIP request (nor a ``raw`` frame an ``all`` request). Writes are atomic (temp -> fsync ->
``os.replace``, mirroring the kill switch). Reads RE-VALIDATE the parquet; a corrupt/partial
or schema-invalid file is a MISS (self-healed), never served. A single-transaction LRU keeps
total bytes <= ``MAX_CACHE_BYTES`` so the cache can never fill the disk; an object larger than
the ceiling is refused. A clock is injectable so LRU ordering is deterministic in tests.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Final

import pandas as pd

from trading.data.errors import CacheError

MAX_CACHE_BYTES: Final[int] = 512 * 1024 * 1024


def cache_key(params: Mapping[str, Any]) -> str:
    """Deterministic content key over the full param set (sorted, str-coerced for stability)."""
    payload = json.dumps(params, sort_keys=True, separators=(",", ":"), default=str)
    return "arcane-bars-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:40]


class ParquetCache:
    """File cache keyed by content hash, capped at ``max_bytes`` with LRU eviction."""

    def __init__(
        self,
        directory: Path,
        *,
        max_bytes: int = MAX_CACHE_BYTES,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._dir = directory
        self._max = max_bytes
        self._clock = clock
        self._dir.mkdir(parents=True, exist_ok=True)
        self._manifest = self._dir / "manifest.sqlite"
        self._init_manifest()
        self._reconcile()

    def get(
        self, key: str, validate: Callable[[pd.DataFrame], object] | None = None
    ) -> pd.DataFrame | None:
        """Return the cached frame, or None on a miss / corrupt / invalid entry (self-heals)."""
        path = self._path(key)
        if not path.exists():
            return None
        try:
            df = pd.read_parquet(path)
            if validate is not None:
                validate(df)
        except Exception:
            path.unlink(missing_ok=True)
            self._delete_row(key)
            return None
        self._touch(key)
        return df

    def put(self, key: str, df: pd.DataFrame) -> None:
        """Atomically store a frame; refuse an oversize object; evict LRU under the ceiling."""
        tmp = self._dir / f"{key}.parquet.tmp"
        df.to_parquet(tmp, engine="pyarrow", index=True)
        size = tmp.stat().st_size
        if size > self._max:
            tmp.unlink(missing_ok=True)
            raise CacheError(f"object {size} bytes exceeds cache ceiling {self._max}")
        with open(tmp, "rb") as fh:
            os.fsync(fh.fileno())
        os.replace(tmp, self._path(key))
        now = self._clock()
        conn = self._connect()
        try:
            with conn:
                conn.execute(
                    "INSERT OR REPLACE INTO entries (key, bytes, last_access, created) "
                    "VALUES (?, ?, ?, ?)",
                    (key, size, now, now),
                )
                self._evict(conn)
        finally:
            conn.close()

    # --- internals ---

    def _path(self, key: str) -> Path:
        return self._dir / f"{key}.parquet"

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._manifest)

    def _init_manifest(self) -> None:
        conn = self._connect()
        try:
            with conn:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS entries "
                    "(key TEXT PRIMARY KEY, bytes INTEGER NOT NULL, "
                    "last_access REAL NOT NULL, created REAL NOT NULL)"
                )
        finally:
            conn.close()

    def _reconcile(self) -> None:
        """Drop manifest rows whose files vanished; unlink orphan parquet files (self-heal)."""
        conn = self._connect()
        try:
            with conn:
                for (key,) in conn.execute("SELECT key FROM entries").fetchall():
                    if not self._path(key).exists():
                        conn.execute("DELETE FROM entries WHERE key = ?", (key,))
                known = {k for (k,) in conn.execute("SELECT key FROM entries").fetchall()}
        finally:
            conn.close()
        for f in self._dir.glob("*.parquet"):
            if f.stem not in known:
                f.unlink(missing_ok=True)

    def _evict(self, conn: sqlite3.Connection) -> None:
        total = int(conn.execute("SELECT COALESCE(SUM(bytes), 0) FROM entries").fetchone()[0])
        if total <= self._max:
            return
        rows = conn.execute("SELECT key, bytes FROM entries ORDER BY last_access ASC").fetchall()
        for key, nbytes in rows:
            if total <= self._max:
                break
            conn.execute("DELETE FROM entries WHERE key = ?", (key,))
            self._path(key).unlink(missing_ok=True)
            total -= int(nbytes)

    def _touch(self, key: str) -> None:
        conn = self._connect()
        try:
            with conn:
                conn.execute(
                    "UPDATE entries SET last_access = ? WHERE key = ?", (self._clock(), key)
                )
        finally:
            conn.close()

    def _delete_row(self, key: str) -> None:
        conn = self._connect()
        try:
            with conn:
                conn.execute("DELETE FROM entries WHERE key = ?", (key,))
        finally:
            conn.close()
