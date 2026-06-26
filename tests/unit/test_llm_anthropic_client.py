"""C2 — the thin httpx Anthropic Messages client (Inc-8 PART A).

A ``Responder = (system_prompt, sanitized_user_text) -> reply_text`` with an injectable ``post``
seam (mirroring ``telegram.py``'s injectable Sender) so the whole gate is offline and faked; exactly
one ``@pytest.mark.live`` smoke hits the real API. NO new heavy dependency (httpx already present).
Token discipline: the API key is a closure local, NEVER logged, and ANY transport exception is
re-wrapped to expose only the exception TYPE so a key-bearing error string can never escape.
"""

from __future__ import annotations

from typing import Any

import pytest

from trading.slowloop.errors import LLMTransportError
from trading.slowloop.llm.anthropic_client import build_responder


def test_responder_extracts_text_and_builds_the_request() -> None:
    captured: dict[str, Any] = {}

    def fake_post(url: str, headers: dict[str, str], body: dict[str, object]) -> dict[str, Any]:
        captured["url"] = url
        captured["headers"] = headers
        captured["body"] = body
        return {"content": [{"type": "text", "text": "hello "}, {"type": "text", "text": "world"}]}

    respond = build_responder("sk-ant-secret", "claude-x", post=fake_post)
    out = respond("be brief", "hur går det?")

    assert out == "hello world"
    assert captured["url"] == "https://api.anthropic.com/v1/messages"
    assert captured["body"]["system"] == "be brief"
    assert captured["body"]["model"] == "claude-x"
    assert captured["body"]["messages"][0]["content"] == "hur går det?"
    assert captured["headers"]["x-api-key"] == "sk-ant-secret"


def test_missing_key_fails_closed() -> None:
    with pytest.raises(LLMTransportError):
        build_responder("", "claude-x")


def test_transport_exception_is_rewrapped_and_never_leaks_the_key() -> None:
    def boom_post(url: str, headers: dict[str, str], body: dict[str, object]) -> dict[str, Any]:
        raise RuntimeError("connection to host carrying sk-ant-supersecret refused")

    respond = build_responder("sk-ant-supersecret", "claude-x", post=boom_post)
    with pytest.raises(LLMTransportError) as ei:
        respond("sys", "hi")
    msg = str(ei.value)
    assert "sk-ant" not in msg and "supersecret" not in msg
    assert "RuntimeError" in msg  # only the exception TYPE is surfaced


def test_malformed_response_fails_closed() -> None:
    for bad in ({}, {"content": "nope"}, {"content": []}, {"content": [{"type": "image"}]}):

        def fake_post(
            url: str, headers: dict[str, str], body: dict[str, object], _b: dict[str, Any] = bad
        ) -> dict[str, Any]:
            return _b

        respond = build_responder("sk-ant-secret", "claude-x", post=fake_post)
        with pytest.raises(LLMTransportError):
            respond("sys", "hi")
