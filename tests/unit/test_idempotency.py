"""Tests for deterministic idempotency keys and dedup stores (Increment 1 spine)."""

from __future__ import annotations

from pathlib import Path

from trading.executor.idempotency import (
    InMemoryIdempotencyStore,
    SqliteIdempotencyStore,
    client_order_id,
)
from trading.executor.intent import OrderIntent

INTENT = OrderIntent(
    strategy_id="orb",
    symbol="AAPL",
    side="buy",
    qty=1.0,
    intended_risk_usd=1.0,
    est_position_value_usd=10.0,
)


def test_client_order_id_is_deterministic() -> None:
    assert client_order_id(INTENT) == client_order_id(INTENT)
    assert client_order_id(INTENT).startswith("arcane-")


def test_client_order_id_changes_with_fields() -> None:
    other = OrderIntent(
        strategy_id="orb",
        symbol="AAPL",
        side="buy",
        qty=2.0,  # different qty -> different identity
        intended_risk_usd=1.0,
        est_position_value_usd=10.0,
    )
    assert client_order_id(other) != client_order_id(INTENT)


def test_in_memory_store_dedup() -> None:
    store = InMemoryIdempotencyStore()
    coid = client_order_id(INTENT)
    assert store.seen(coid) is False
    assert store.remember(coid) is True  # newly inserted
    assert store.remember(coid) is False  # duplicate
    assert store.seen(coid) is True


def test_sqlite_store_dedup_and_persistence(tmp_path: Path) -> None:
    db = tmp_path / "idem.sqlite"
    store = SqliteIdempotencyStore(db)
    coid = client_order_id(INTENT)
    assert store.seen(coid) is False
    assert store.remember(coid) is True
    assert store.remember(coid) is False
    # A fresh store on the same DB still sees it (restart-safe).
    assert SqliteIdempotencyStore(db).seen(coid) is True
