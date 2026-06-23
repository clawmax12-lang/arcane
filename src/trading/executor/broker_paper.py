"""Paper broker adapter — ``paper=True`` is HARDCODED and cannot become live (Inc-6 wires submit).

Defense in depth behind the LIVE_MODE triple-lock gate: even if every other guard failed, the broker
client is constructed with ``paper=ALPACA_PAPER`` (the module constant) regardless of any config or
LIVE_MODE state. ``paper`` is a read-only property; a source-grep test forbids a ``paper=False``
literal. The Alpaca client is INJECTED (a fake in unit tests, the real ``TradingClient`` only behind
``pytest -m live``), so no unit/inc-gate test ever touches the network. Any broker/transport
error is
caught and re-wrapped to a non-accepted ack — the token is NEVER logged (only exception types).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Final

from trading.executor.intent import OrderIntent, OrderType, Side
from trading.settings import Settings, load_settings

logger = logging.getLogger(__name__)

#: Hardcoded, grep-able. Never wired to config or LIVE_MODE. Always paper.
ALPACA_PAPER: Final[bool] = True


@dataclass(frozen=True, slots=True)
class BrokerOrderAck:
    client_order_id: str
    accepted: bool
    detail: str


class PaperBroker:
    """Broker adapter pinned to paper trading; ``paper`` is read-only and always True."""

    def __init__(self, *, client: Any | None = None, settings: Settings | None = None) -> None:
        self._client = client
        self._settings = settings

    @property
    def paper(self) -> bool:
        return ALPACA_PAPER

    def _get_client(self) -> Any:
        if self._client is None:  # pragma: no cover - real client only built behind pytest -m live
            from alpaca.trading.client import TradingClient

            s = self._settings or load_settings()
            self._client = TradingClient(
                api_key=s.required["APCA_API_KEY_ID"],
                secret_key=s.required["APCA_API_SECRET_KEY"],
                paper=ALPACA_PAPER,  # hardcoded — never config/LIVE_MODE
            )
        return self._client

    def submit(self, intent: OrderIntent, client_order_id: str) -> BrokerOrderAck:
        """Submit an order to the paper broker. Any error → a non-accepted ack (fail closed)."""
        try:
            from alpaca.trading.enums import OrderSide, TimeInForce
            from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest

            side = OrderSide.BUY if intent.side is Side.BUY else OrderSide.SELL
            tif = TimeInForce(intent.time_in_force.value)
            if intent.order_type is OrderType.LIMIT:
                request: Any = LimitOrderRequest(
                    symbol=intent.symbol,
                    qty=intent.qty,
                    side=side,
                    time_in_force=tif,
                    limit_price=intent.limit_price,
                    client_order_id=client_order_id,
                )
            else:
                request = MarketOrderRequest(
                    symbol=intent.symbol,
                    qty=intent.qty,
                    side=side,
                    time_in_force=tif,
                    client_order_id=client_order_id,
                )
            order = self._get_client().submit_order(order_data=request)
            broker_id = getattr(order, "id", "?")
            logger.info("broker_submit_accepted coid=%s broker_id=%s", client_order_id, broker_id)
            return BrokerOrderAck(client_order_id, True, f"accepted (broker_id={broker_id})")
        except Exception as exc:
            # Re-wrap to the exception TYPE only — never surface a message that could embed a key.
            logger.warning(
                "broker_submit_failed coid=%s error=%s", client_order_id, type(exc).__name__
            )
            return BrokerOrderAck(client_order_id, False, f"broker error: {type(exc).__name__}")

    def flat_all(self) -> bool:
        """Cancel all open orders and close all positions (the RED auto-flat). Best-effort.

        Returns True if the broker confirmed the flatten; on any error logs the TYPE and returns
        False — the protective hard_stop is latched by the caller regardless of this result.
        """
        try:
            client = self._get_client()
            client.cancel_all_orders()
            client.close_all_positions(cancel_orders=True)
            logger.info("broker_flat_all_ok")
            return True
        except Exception as exc:
            logger.warning("broker_flat_all_failed error=%s", type(exc).__name__)
            return False

    def get_order_status(self, client_order_id: str) -> str:
        """Look up an order by client_order_id (startup orphan reconciliation). Never raises."""
        try:
            order = self._get_client().get_order_by_client_id(client_order_id)
            return str(getattr(order, "status", "unknown"))
        except Exception as exc:
            return f"lookup_failed:{type(exc).__name__}"
