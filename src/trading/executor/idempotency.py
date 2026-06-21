"""Deterministic idempotency keys + a dedup store (prevents M10 duplicate orders).

The ``client_order_id`` is a deterministic hash of the order's identity fields — NOT
the wall clock — so the same intent retried after a crash maps to the same id, and both
our local store (unique constraint) and the broker reject the duplicate. At-most-once.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Protocol, runtime_checkable

from trading.executor.intent import OrderIntent


def client_order_id(intent: OrderIntent) -> str:
    """Deterministic id from the fields that define order identity (no wall clock).

    Canonical JSON encoding (no delimiter collisions) over lossless ``float.hex`` (no
    %g precision collisions). OrderIntent already canonicalizes the identity strings, so
    cosmetic symbol/strategy variants map to the same id.
    """
    fields = [
        intent.strategy_id,
        intent.symbol,
        intent.side.value,
        intent.qty.hex(),
        intent.order_type.value,
        "none" if intent.limit_price is None else intent.limit_price.hex(),
        intent.time_in_force.value,
    ]
    payload = json.dumps(fields, separators=(",", ":"), ensure_ascii=True)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"arcane-{digest[:32]}"


@runtime_checkable
class IdempotencyStore(Protocol):
    """A store that records which client_order_ids have been submitted."""

    def seen(self, client_order_id: str) -> bool: ...

    def remember(self, client_order_id: str) -> bool:
        """Atomically record the id. Returns True only if it was newly inserted."""
        ...


class InMemoryIdempotencyStore:
    """Process-local dedup store (tests, single-run)."""

    def __init__(self) -> None:
        self._ids: set[str] = set()

    def seen(self, client_order_id: str) -> bool:
        return client_order_id in self._ids

    def remember(self, client_order_id: str) -> bool:
        if client_order_id in self._ids:
            return False
        self._ids.add(client_order_id)
        return True


class SqliteIdempotencyStore:
    """Crash-safe dedup store backed by a SQLite unique constraint (restart-safe)."""

    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._path)
        try:
            with conn:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS submitted_orders "
                    "(client_order_id TEXT PRIMARY KEY)"
                )
        finally:
            conn.close()

    def seen(self, client_order_id: str) -> bool:
        conn = sqlite3.connect(self._path)
        try:
            cur = conn.execute(
                "SELECT 1 FROM submitted_orders WHERE client_order_id = ?",
                (client_order_id,),
            )
            return cur.fetchone() is not None
        finally:
            conn.close()

    def remember(self, client_order_id: str) -> bool:
        conn = sqlite3.connect(self._path)
        try:
            with conn:
                conn.execute(
                    "INSERT INTO submitted_orders (client_order_id) VALUES (?)",
                    (client_order_id,),
                )
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()
