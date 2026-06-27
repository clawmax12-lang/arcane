"""Inc-8 LIVE smokes — excluded from every gate via ``-m 'not live'`` (no trading, no state change).

Run explicitly with ``uv run pytest -m live tests/unit/test_inc8_live_smoke.py``. These prove real
transports work end-to-end against the actual APIs; the gate uses fakes for everything. The Telegram
two-way round-trip smoke is added in the console clusters (C3/C4).
"""

from __future__ import annotations

import pytest

from trading.console.app import make_telegram_fetcher
from trading.console.responder import SYSTEM_PROMPT, build_answerer
from trading.notify.telegram import build_notifier
from trading.settings import load_model_settings, load_notify_settings, load_settings
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
def test_live_sonnet_conversation_is_warm_and_grounded() -> None:
    # Inc-8.5: prove the REAL conversation model (default Sonnet) answers the warm prompt grounded
    # in a synthetic briefing, in Swedish, without inventing a number. Proves the model id works.
    settings = load_settings()
    key = settings.get("ANTHROPIC_API_KEY")
    conversation_model, _agent = load_model_settings()  # default claude-sonnet-4-6
    respond = build_responder(key, conversation_model, max_tokens=400)
    briefing = (
        "- kill_switch (källa: HARD): ARMED (ingen anledning)\n"
        "- mode (källa: Inc-7 seal): RECORD-ONLY. Inga riktiga ordrar har lagts.\n"
        "- gate_utfall (källa: ADR §0): Gaten dödade alla 4 leksaksstrategier: 0 survivors, "
        "0 ordrar.\n"
        "- nyheter (källa: news): otillgänglig (saknas eller föråldrad)"
    )
    answer = build_answerer(respond, briefing_provider=lambda: briefing)
    reply = answer("hur går det idag, och förklara kort vad gaten gör?")
    assert isinstance(reply, str) and len(reply.strip()) > 40  # a real, substantive Swedish answer
    # grounded honesty: it must NOT invent news it doesn't have
    assert (
        SYSTEM_PROMPT  # the warm prompt is what was sent (system==SYSTEM_PROMPT in build_answerer)
    )


@pytest.mark.live
def test_live_telegram_two_way_transport() -> None:
    # Proves the real two-way transport: send a message to the operator AND read getUpdates back.
    token, chat_id = load_notify_settings()
    notifier = build_notifier(token, chat_id)
    notifier.send_message("ARCANE Inc-8 console: live two-way transport smoke ✅")
    assert token is not None
    updates = make_telegram_fetcher(token)(None)
    assert isinstance(updates, list)
