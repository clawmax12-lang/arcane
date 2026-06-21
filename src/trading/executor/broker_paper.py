"""Paper broker adapter — ``paper=True`` is HARDCODED and cannot become live.

Defense in depth behind the LIVE_MODE triple-lock gate: even if every other guard
failed, the broker client is constructed with ``paper=True`` regardless of any config
or LIVE_MODE state. ``paper`` is a read-only property derived from the module constant
``ALPACA_PAPER`` — it cannot be reassigned on an instance, and the Increment-2 submit
path will pass ``paper=ALPACA_PAPER`` (the constant) to the Alpaca client, never a
mutable attribute. In Increment 1 submission is a stub. A source-grep test forbids a
``paper=False`` literal.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

#: Hardcoded, grep-able. Never wired to config or LIVE_MODE. Always paper.
ALPACA_PAPER: Final[bool] = True


@dataclass(frozen=True, slots=True)
class BrokerOrderAck:
    client_order_id: str
    accepted: bool
    detail: str


class PaperBroker:
    """Broker adapter pinned to paper trading; ``paper`` is read-only and always True."""

    @property
    def paper(self) -> bool:
        return ALPACA_PAPER

    def submit(self, client_order_id: str) -> BrokerOrderAck:
        # Increment 2 constructs the alpaca-py client with paper=ALPACA_PAPER (constant).
        raise NotImplementedError("paper submission is wired in Increment 2 (Alpaca data spine)")
