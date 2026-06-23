"""Tests for the paper broker adapter (Increment 1 spine; Inc-6 wires the real paper submit)."""

from __future__ import annotations

import ast
import inspect
from typing import Any

import pytest

from trading.executor import broker_paper
from trading.executor.broker_paper import ALPACA_PAPER, PaperBroker
from trading.executor.intent import OrderIntent, Side


def _intent() -> OrderIntent:
    return OrderIntent(
        strategy_id="ts_momentum_blend",
        symbol="AAPL",
        side=Side.BUY,
        qty=1.0,
        intended_risk_usd=2.0,
        est_position_value_usd=2.0,
    )


class _FakeOrder:
    id = "broker-order-123"


class _FakeClient:
    def __init__(self) -> None:
        self.submitted: list[Any] = []

    def submit_order(self, order_data: Any) -> _FakeOrder:
        self.submitted.append(order_data)
        return _FakeOrder()


class _FailingClient:
    def submit_order(self, order_data: Any) -> Any:
        raise RuntimeError("token=SECRET-should-not-leak network down")


def test_alpaca_paper_constant_is_true() -> None:
    assert ALPACA_PAPER is True


def test_broker_is_paper() -> None:
    assert PaperBroker().paper is True


def test_submit_accepts_via_injected_client() -> None:
    client = _FakeClient()
    ack = PaperBroker(client=client).submit(_intent(), "arcane-abc")
    assert ack.accepted is True
    assert ack.client_order_id == "arcane-abc"
    assert "broker-order-123" in ack.detail
    # the real Alpaca request object was built (fakes mirror reality) and carries the coid
    assert client.submitted and client.submitted[0].client_order_id == "arcane-abc"


def test_submit_fails_closed_on_broker_error_without_leaking_token() -> None:
    ack = PaperBroker(client=_FailingClient()).submit(_intent(), "arcane-abc")
    assert ack.accepted is False
    assert "SECRET" not in ack.detail and "token" not in ack.detail  # only the exception TYPE
    assert "RuntimeError" in ack.detail


def test_paper_attribute_is_read_only() -> None:
    # `paper` is a derived property (single source of truth = ALPACA_PAPER); a stray
    # assignment that tries to flip it to live must fail, not silently succeed.
    broker = PaperBroker()
    with pytest.raises(AttributeError):
        broker.paper = False  # type: ignore[misc]


def test_alpaca_paper_literal_is_true_in_source() -> None:
    # AST check (ignores docstrings/comments): the constant must literally be True.
    tree = ast.parse(inspect.getsource(broker_paper))
    found = False
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "ALPACA_PAPER"
        ):
            assert isinstance(node.value, ast.Constant) and node.value.value is True
            found = True
    assert found, "ALPACA_PAPER constant assignment not found in source"
