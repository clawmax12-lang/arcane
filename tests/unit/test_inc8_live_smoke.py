"""Inc-8 LIVE smokes — excluded from every gate via ``-m 'not live'`` (no trading, no state change).

Run explicitly with ``uv run pytest -m live tests/unit/test_inc8_live_smoke.py``. These prove real
transports work end-to-end against the actual APIs; the gate uses fakes for everything. The Telegram
two-way round-trip smoke is added in the console clusters (C3/C4).
"""

from __future__ import annotations

import pytest

from trading.console.app import make_telegram_fetcher
from trading.notify.telegram import build_notifier
from trading.settings import load_notify_settings, load_settings
from trading.slowloop.llm.anthropic_client import build_responder

_HAIKU = "claude-haiku-4-5-20251001"


@pytest.mark.live
def test_live_anthropic_responder_round_trip() -> None:
    settings = load_settings()
    key = settings.get("ANTHROPIC_API_KEY")
    respond = build_responder(key, _HAIKU, max_tokens=32)
    reply = respond(
        "You are a terse test probe. Reply with exactly one short word.",
        "Reply with the single word: ARCANE",
    )
    assert isinstance(reply, str) and reply.strip() != ""


@pytest.mark.live
def test_live_telegram_two_way_transport() -> None:
    # Proves the real two-way transport: send a message to the operator AND read getUpdates back.
    token, chat_id = load_notify_settings()
    notifier = build_notifier(token, chat_id)
    notifier.send_message("ARCANE Inc-8 console: live two-way transport smoke ✅")
    assert token is not None
    updates = make_telegram_fetcher(token)(None)
    assert isinstance(updates, list)
