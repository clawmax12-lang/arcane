"""Tests for OrderIntent validation (Increment 1 safety spine)."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from trading.executor.intent import OrderIntent, OrderType, Side

BASE: dict[str, Any] = {
    "strategy_id": "orb_momentum",
    "symbol": "AAPL",
    "side": "buy",
    "qty": 1.0,
    "intended_risk_usd": 1.0,
    "est_position_value_usd": 10.0,
}


def test_valid_market_intent() -> None:
    intent = OrderIntent(**BASE)
    assert intent.side is Side.BUY
    assert intent.order_type is OrderType.MARKET


def test_limit_requires_price() -> None:
    with pytest.raises(ValidationError):
        OrderIntent(**{**BASE, "order_type": "limit"})


def test_limit_with_positive_price_ok() -> None:
    intent = OrderIntent(**{**BASE, "order_type": "limit", "limit_price": 150.0})
    assert intent.limit_price == 150.0


def test_market_with_price_rejected() -> None:
    with pytest.raises(ValidationError):
        OrderIntent(**{**BASE, "limit_price": 150.0})


def test_qty_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        OrderIntent(**{**BASE, "qty": 0})


def test_negative_risk_rejected() -> None:
    with pytest.raises(ValidationError):
        OrderIntent(**{**BASE, "intended_risk_usd": -1.0})


def test_extra_field_forbidden() -> None:
    with pytest.raises(ValidationError):
        OrderIntent(**{**BASE, "sneaky": 1})


def test_intent_is_frozen() -> None:
    intent = OrderIntent(**BASE)
    with pytest.raises(ValidationError):
        intent.qty = 2.0  # type: ignore[misc]
