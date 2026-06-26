"""Inc-8 LIVE smokes — excluded from every gate via ``-m 'not live'`` (no trading, no state change).

Run explicitly with ``uv run pytest -m live tests/unit/test_inc8_live_smoke.py``. These prove real
transports work end-to-end against the actual APIs; the gate uses fakes for everything. The Telegram
two-way round-trip smoke is added in the console clusters (C3/C4).
"""

from __future__ import annotations

import pytest

from trading.settings import load_settings
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
