"""A thin httpx Anthropic Messages client — the slow-loop LLM transport (Inc-8 PART A).

A ``Responder`` is ``(system_prompt, sanitized_user_text) -> reply_text``. It is built with an
injectable HTTP ``post`` seam (mirroring ``telegram.py``'s injectable Sender) so the whole gate runs
offline against fakes; exactly one ``@pytest.mark.live`` smoke hits the real API. NO new heavy
dependency — httpx is already used by the pager.

Token discipline (the ``telegram.py`` pattern): the API key is captured as a closure local and put
ONLY in the request headers; it is never logged. ANY exception from the ``post`` call is re-wrapped
to ``LLMTransportError(type(exc).__name__)`` so a key-bearing error string can never escape.

The caller MUST pass already-§4.2-sanitized text — this module is pure transport, not a sanitizer.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Final

import httpx

from trading.slowloop.errors import LLMTransportError

_API_URL: Final[str] = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_VERSION: Final[str] = "2023-06-01"
_HTTP_TIMEOUT_S: Final[float] = 30.0
_DEFAULT_MAX_TOKENS: Final[int] = 1024

#: ``(system_prompt, sanitized_user_text) -> reply_text``. RAISES ``LLMTransportError`` on failure.
Responder = Callable[[str, str], str]
#: ``(url, headers, json_body) -> parsed_json``. RAISES on transport/protocol failure.
HttpPost = Callable[[str, dict[str, str], dict[str, object]], dict[str, Any]]


def _httpx_post(url: str, headers: dict[str, str], body: dict[str, object]) -> dict[str, Any]:
    """Default HttpPost: POST the payload; re-wrap ALL errors to avoid leaking the header key."""
    try:
        resp = httpx.post(url, headers=headers, json=body, timeout=_HTTP_TIMEOUT_S)
    except Exception as exc:
        raise LLMTransportError(f"anthropic transport failed: {type(exc).__name__}") from None
    if resp.status_code // 100 != 2:
        raise LLMTransportError(f"anthropic returned HTTP {resp.status_code}")
    parsed: dict[str, Any] = resp.json()
    return parsed


def _extract_text(payload: dict[str, Any]) -> str:
    """Concatenate the text blocks from an Anthropic Messages response (fail closed if none)."""
    content = payload.get("content")
    if not isinstance(content, list):
        raise LLMTransportError("anthropic response missing a content list")
    texts = [
        block["text"]
        for block in content
        if isinstance(block, dict) and block.get("type") == "text" and "text" in block
    ]
    if not texts:
        raise LLMTransportError("anthropic response had no text block")
    return "".join(str(t) for t in texts)


def build_responder(
    api_key: str | None,
    model_id: str,
    *,
    post: HttpPost = _httpx_post,
    max_tokens: int = _DEFAULT_MAX_TOKENS,
) -> Responder:
    """Build a ``Responder`` bound to ``api_key`` (fail closed if missing).

    The key lives ONLY inside the returned closure's request headers — it is never logged and never
    interpolated into a prompt. Any ``post`` exception is re-wrapped to expose only the exception
    TYPE, so even an injected ``post`` that raises a key-bearing message cannot leak it.
    """
    if not api_key:
        raise LLMTransportError(
            "ANTHROPIC_API_KEY missing — slow-loop agents are DOWN (fail closed)"
        )
    key = api_key

    def _respond(system_prompt: str, user_text: str) -> str:
        headers = {
            "x-api-key": key,
            "anthropic-version": _ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        body: dict[str, object] = {
            "model": model_id,
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_text}],
        }
        try:
            payload = post(_API_URL, headers, body)
        except LLMTransportError:
            raise
        except Exception as exc:
            # Defense in depth: re-wrap ANY transport error TYPE-only, so a key-bearing exception
            # string from a custom/real post can never escape.
            raise LLMTransportError(f"anthropic call failed: {type(exc).__name__}") from None
        return _extract_text(payload)

    return _respond
