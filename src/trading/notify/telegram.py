"""Telegram notifier — the disaster-recovery pager + daily-report transport (httpx, fail-closed).

Design invariants (``docs/INCREMENT-5-DESIGN.md`` §C.1):
  * Every outbound body is §4.2-sanitized BEFORE the payload dict is built (the M13 defense). An
    empty sanitized body sends a fixed placeholder (Telegram rejects empty text).
  * A RED ``page_operator`` that fails to deliver RE-RAISES ``NotifierError`` — never swallowed (the
    worst fail-open is a dropped disaster page). YELLOW/ORANGE are best-effort (logged, not raised).
  * The bot token is NEVER logged: the API URL (which embeds ``/bot{token}/``) is a non-logged
    local, httpx exceptions are re-wrapped to expose only the exception TYPE + status, and structlog
    only ``{severity, ok}``. A grep test forbids a token-shaped literal anywhere in ``src/``.
  * Fail-closed construction: a missing token raises; a missing chat_id is resolved once via
    ``getUpdates`` (and raises with operator instructions if unresolvable).

The notifier is defense-in-depth, NOT a sanitization guarantee — the operator is a human reading
evidence, not an LLM acting on it (ADR §4.3).
"""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from typing import Any, Final

import httpx
import structlog

from trading.data.sanitize import sanitize
from trading.notify.errors import NotifierError, NotifierMisconfiguredError

_log = structlog.get_logger(__name__)

_API_BASE: Final[str] = "https://api.telegram.org"
_TELEGRAM_MAX_CHARS: Final[int] = 4096
_REDACTED_PLACEHOLDER: Final[str] = "[message redacted by sanitizer]"
_HTTP_TIMEOUT_S: Final[float] = 10.0

#: A Sender posts a Telegram payload; RAISES ``NotifierError`` on any failure, returns None on OK.
Sender = Callable[[str, dict[str, str]], None]
#: Fetches raw ``getUpdates`` result objects for chat_id resolution.
UpdatesFetcher = Callable[[str], list[dict[str, Any]]]


class Severity(StrEnum):
    """Graduated Murphy-guard response level (mirrors §5.1 Yellow/Orange/Red)."""

    YELLOW = "yellow"
    ORANGE = "orange"
    RED = "red"


def _httpx_sender(url: str, body: dict[str, str]) -> None:
    """Default Sender: POST the payload; re-wrap ALL httpx errors to avoid leaking the token URL."""
    try:
        resp = httpx.post(url, json=body, timeout=_HTTP_TIMEOUT_S)
    except httpx.HTTPError as exc:  # the exc embeds request.url (with the token) — never surface it
        raise NotifierError(f"telegram transport failed: {type(exc).__name__}") from None
    if resp.status_code // 100 != 2:
        raise NotifierError(f"telegram returned HTTP {resp.status_code}")


def _httpx_get_updates(token: str) -> list[dict[str, Any]]:
    """Default UpdatesFetcher: GET ``getUpdates``; re-wrap errors without leaking the token URL."""
    url = f"{_API_BASE}/bot{token}/getUpdates"
    try:
        resp = httpx.get(url, timeout=_HTTP_TIMEOUT_S)
    except httpx.HTTPError as exc:
        raise NotifierError(f"telegram getUpdates failed: {type(exc).__name__}") from None
    if resp.status_code // 100 != 2:
        raise NotifierError(f"telegram getUpdates returned HTTP {resp.status_code}")
    payload = resp.json()
    result = payload.get("result", []) if isinstance(payload, dict) else []
    return list(result)


def resolve_chat_id(token: str, *, fetch_updates: UpdatesFetcher = _httpx_get_updates) -> str:
    """Resolve a chat_id from the most recent ``getUpdates`` message; fail closed if none exists."""
    for update in reversed(fetch_updates(token)):
        chat = (update.get("message") or {}).get("chat") or {}
        if "id" in chat:
            return str(chat["id"])
    raise NotifierMisconfiguredError(
        "no chat_id resolvable from getUpdates — message @Traderexperimentbot once, then retry"
    )


def _chunks(text: str, size: int) -> list[str]:
    return [text[i : i + size] for i in range(0, max(len(text), 1), size)]


class TelegramNotifier:
    """Sends operator messages/pages/reports to one Telegram chat; sanitized + fail-closed."""

    def __init__(self, token: str, chat_id: str, *, sender: Sender = _httpx_sender) -> None:
        self._token = token
        self._chat_id = chat_id
        self._sender = sender

    def _post(self, text: str) -> None:
        """POST one already-sanitized chunk. The token-bearing URL is a non-logged local var."""
        url = f"{_API_BASE}/bot{self._token}/sendMessage"
        self._sender(url, {"chat_id": self._chat_id, "text": text})

    def send_message(self, text: str) -> None:
        """Sanitize and send a single message (placeholder if it sanitizes to empty)."""
        self._post(sanitize(text) or _REDACTED_PLACEHOLDER)

    def send_daily_report(self, report: str) -> None:
        """Sanitize, split into <=4096-char chunks, send sequentially (the §1.1 daily report)."""
        clean = sanitize(report) or _REDACTED_PLACEHOLDER
        for chunk in _chunks(clean, _TELEGRAM_MAX_CHARS):
            self._post(chunk)

    def page_operator(self, severity: Severity, text: str) -> None:
        """Page the operator. A failed RED page RE-RAISES; lower levels are best-effort."""
        tagged = f"[{severity.value.upper()}] " + (sanitize(text) or _REDACTED_PLACEHOLDER)
        try:
            self._post(tagged)
            _log.info("operator_paged", severity=severity.value, ok=True)
        except NotifierError as exc:
            _log.warning("operator_page_failed", severity=severity.value, error=type(exc).__name__)
            if severity is Severity.RED:
                raise  # a dropped disaster-recovery page must never be silent


def build_notifier(
    token: str | None,
    chat_id: str | None,
    *,
    sender: Sender = _httpx_sender,
    fetch_updates: UpdatesFetcher = _httpx_get_updates,
) -> TelegramNotifier:
    """Construct a notifier from credentials; fail closed on a missing token / no chat_id."""
    if not token:
        raise NotifierMisconfiguredError(
            "TELEGRAM_BOT_TOKEN missing — disaster-recovery paging is DOWN (fail closed)"
        )
    resolved = chat_id if chat_id else resolve_chat_id(token, fetch_updates=fetch_updates)
    return TelegramNotifier(token, resolved, sender=sender)
