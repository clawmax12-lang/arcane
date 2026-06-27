"""C4 — the grounded, REPORT-ONLY Q&A responder (Inc-8 PART B).

The responder answers the operator's question grounded ONLY in the sanitized briefing. Its system
prompt makes it report-only: it cannot place trades, must answer from the briefing (or say "I don't
have that"), and must be honest about the boring 0-trade days (§9 / R2 / R3). It returns ``str``
— there is no structured action surface, so a jailbroken reply can never become an action.
"""

from __future__ import annotations

from trading.console.responder import SYSTEM_PROMPT, build_answerer


def test_answerer_grounds_the_question_in_the_briefing_and_returns_text() -> None:
    captured: dict[str, str] = {}

    def fake_responder(system: str, user: str) -> str:
        captured["system"] = system
        captured["user"] = user
        return "Det går bra — record-only, 0 trades, gaten dödade alla 4 toys."

    answer = build_answerer(fake_responder, briefing_provider=lambda: "BRIEFING: ARMED; 0 trades")
    out = answer("hur går det?")

    assert out.startswith("Det går bra")
    assert captured["system"] == SYSTEM_PROMPT
    # the briefing AND the question are both handed to the model (grounding)
    assert "BRIEFING: ARMED; 0 trades" in captured["user"]
    assert "hur går det?" in captured["user"]


def test_system_prompt_grounds_facts_and_forbids_trading() -> None:
    low = SYSTEM_PROMPT.lower()
    # facts are grounded in the briefing / cannot trade / honest about missing data
    assert "gate" in low  # only the gate->GO path can produce an order
    assert "order" in low or "ordrar" in low
    assert "briefing" in low
    # it is told NOT to invent data it does not have
    assert "hitta aldrig på" in low or "inte har den datan" in low


def test_system_prompt_is_warm_and_conversational_not_a_straitjacket() -> None:
    # Inc-8.5: the prompt must NOT re-impose the old report-only/short straitjacket, and must
    # explicitly invite a real conversation (so a regression to the stiff prompt is caught).
    low = SYSTEM_PROMPT.lower()
    assert "enbart rapporterande" not in low
    assert "svara kort" not in low
    assert "samtal" in low  # it is told to hold a real conversation
    assert "förklara" in low  # it is free to explain/teach


def test_answerer_passes_the_briefing_fresh_each_call() -> None:
    state = {"n": 0}

    def provider() -> str:
        state["n"] += 1
        return f"BRIEFING call #{state['n']}"

    seen: list[str] = []

    def fake_responder(system: str, user: str) -> str:
        seen.append(user)
        return "ok"

    answer = build_answerer(fake_responder, briefing_provider=provider)
    answer("fråga 1")
    answer("fråga 2")
    assert "BRIEFING call #1" in seen[0]
    assert "BRIEFING call #2" in seen[1]  # the briefing is re-gathered per question, never stale
