"""Paper broker adapter — ``paper=True`` is HARDCODED and cannot become live.

Defense in depth behind the LIVE_MODE triple-lock gate: even if every other guard
failed, the broker client is constructed with ``paper=True`` regardless of any config
or LIVE_MODE state. In Increment 1 submission is a stub (no alpaca-py dependency yet);
Increment 2 wires the real paper client. A source-grep test forbids ``paper=False``.
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
    """Broker adapter pinned to paper trading. Instances cannot change ``paper``."""

    paper: Final[bool] = ALPACA_PAPER

    def __init__(self) -> None:
        if not self.paper:
            raise RuntimeError("PaperBroker must be paper=True (hardcoded invariant)")

    def submit(self, client_order_id: str) -> BrokerOrderAck:
        # Real paper submission (alpaca-py, paper=ALPACA_PAPER) is wired in Increment 2.
        raise NotImplementedError("paper submission is wired in Increment 2 (Alpaca data spine)")
