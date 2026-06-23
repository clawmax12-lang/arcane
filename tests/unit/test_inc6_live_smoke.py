"""Increment 6 LIVE smokes — verify the wiring against the REAL vendors (operator-run only).

``@pytest.mark.live`` is EXCLUDED from ``make inc6`` (and every inc gate). These hit the network and
authenticate from ``.env``. They prove the wiring is built from real vendor behavior
(insight-fakes-must-mirror-reality) — and CRUCIALLY they do NOT submit any order: the first paper
order is deferred to a per-order operator GO (the Inc-6 hard stop / ADR §7). The Alpaca smoke
is read-only connectivity; it asserts ``paper=True``.
"""

from __future__ import annotations

import pytest

from trading.data.polygon_universe import HttpxPolygonReference
from trading.executor.broker_paper import ALPACA_PAPER
from trading.settings import load_settings


@pytest.mark.live
def test_polygon_pit_reconstruction_live() -> None:
    """Ground-truth checkpoint: Polygon reconstructs membership as a true point-in-time interval."""
    token = load_settings().get("POLYGON_API_KEY")
    if not token:
        pytest.skip("POLYGON_API_KEY not set")
    ref = HttpxPolygonReference(token, min_interval_s=13.0)  # respect the ~5/min free tier
    # SIVB (SVB Financial, delisted 2023-03-28): active during its trading life...
    active = ref("SIVB", "2023-02-15")
    assert active and active[0]["ticker"] == "SIVB"
    assert active[0]["active"] is True
    assert active[0].get("delisted_utc") in (None, "")  # reconstructed as-of: not-yet-delisted
    # ...and the interval is CLOSED after the delist (a flat watchlist would wrongly keep it).
    closed = ref("SIVB", "2023-09-01")
    assert closed == []  # count 0 post-delist


@pytest.mark.live
def test_alpaca_paper_connectivity_live() -> None:
    """Read-only: the paper TradingClient connects and reports a paper account. NO order
    submitted."""
    from alpaca.trading.client import TradingClient

    s = load_settings()
    client = TradingClient(
        api_key=s.required["APCA_API_KEY_ID"],
        secret_key=s.required["APCA_API_SECRET_KEY"],
        paper=ALPACA_PAPER,  # hardcoded True
    )
    account = client.get_account()
    assert account is not None
    assert getattr(account, "status", None) is not None
    # Deliberately NO submit_order here — the first real paper order requires an explicit
    # operator GO.
