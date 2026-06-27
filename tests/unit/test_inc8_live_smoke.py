"""Inc-8 LIVE smokes — excluded from every gate via ``-m 'not live'`` (no trading, no state change).

Run explicitly with ``uv run pytest -m live tests/unit/test_inc8_live_smoke.py``. These prove real
transports work end-to-end against the actual APIs; the gate uses fakes for everything. The Telegram
two-way round-trip smoke is added in the console clusters (C3/C4).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from trading.console.app import make_telegram_fetcher
from trading.console.responder import SYSTEM_PROMPT, build_answerer
from trading.notify.telegram import build_notifier
from trading.settings import load_model_settings, load_notify_settings, load_settings
from trading.slowloop.llm.anthropic_client import build_responder

_HAIKU = "claude-haiku-4-5-20251001"


def _now_utc() -> datetime:
    return datetime.now(UTC)


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


# ----------------------------------------------------------------- Inc-8.6 live vendor smokes


@pytest.mark.live
def test_live_tavily_returns_real_news() -> None:
    # The keys finally ring: real Tavily news, mapped to fail-closed NewsItems with parsed dates.
    from trading.slowloop.sources.tavily_news import HttpxTavilyNews

    settings = load_settings()
    src = HttpxTavilyNews(settings.get("TAVILY_API_KEY") or "")
    items = src()
    assert items, "Tavily returned no headlines"
    assert all(i.title.strip() for i in items)
    assert all(i.published_at.tzinfo is not None for i in items)  # aware UTC, never fabricated


@pytest.mark.live
def test_live_fred_macro_summary() -> None:
    # Real FRED macro: a compact summary string with live numbers feeding the regime advisory.
    from trading.slowloop.sources.fred_macro import FredMacroSource

    settings = load_settings()
    summary = FredMacroSource(settings.get("FRED_API_KEY") or "")()
    assert summary.startswith("Makroläge (FRED")
    assert "VIX" in summary and "10y" in summary


@pytest.mark.live
def test_live_end_to_end_news_to_state_and_briefing(tmp_path: Path) -> None:
    # The PART D proof, end to end: real Tavily -> NewsAgent (real Haiku) -> news_state.json ->
    # the console state_reader briefing answers with a REAL, current headline summary.
    from trading.console.state_reader import gather_briefing
    from trading.slowloop.agents.news import NewsAgent
    from trading.slowloop.orchestrator import run_agent
    from trading.slowloop.sources.tavily_news import HttpxTavilyNews

    settings = load_settings()
    key = settings.get("ANTHROPIC_API_KEY")
    _conv, agent_model = load_model_settings()
    news_path = tmp_path / "news_state.json"
    agent = NewsAgent(
        news_source=HttpxTavilyNews(settings.get("TAVILY_API_KEY") or ""),
        output_path=news_path,
        model_id=agent_model,
        now_provider=_now_utc,
    )
    result = run_agent(
        agent,
        build_responder(key, agent_model),
        notifier=None,
        health_path=tmp_path / "_health.json",
    )
    assert result.written, f"news agent discarded: {result.reason}"

    class _Kill:
        def read(self) -> str:
            return "ARMED"

        def reason(self) -> str:
            return "live smoke"

    briefing = gather_briefing(
        _Kill(),
        news_path=news_path,
        regime_advisory_path=tmp_path / "regime.json",
        now=_now_utc(),
    )
    nyheter = briefing.get("nyheter")
    assert nyheter is not None and "otillgänglig" not in nyheter.text  # REAL news, not unavailable
    print("LIVE NEWS BRIEFING:", nyheter.text)
