"""Console WIRING — assemble the two-way operator console from real components (Inc-8 PART B).

This is the integration point: it ties the deterministic ``kill_switch`` (escalate-only), the
``TelegramNotifier`` (outbound, sanitizes), the grounded report-only Q&A responder, and the durable
poller into one ``ConsolePoller``. ``console`` is OUTSIDE the PHI1 submit-path roots, so it MAY
import ``executor.kill_switch`` / ``notify`` / ``slowloop`` — the reverse is forbidden (proven by
the boundary test). The Telegram token lives only in the getUpdates URL (a non-logged local); a
transport error is re-wrapped to a token-free ``ConsoleError``.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, Protocol

import httpx

from trading.console.commands import ConsoleDeps, _no_op_refresh, handle_message
from trading.console.errors import ConsoleError
from trading.console.news_refresh import (
    RefreshContext,
    build_news_refresher,
)
from trading.console.poller import DEFAULT_OFFSET_PATH, ConsolePoller, UpdatesFetcher
from trading.console.responder import build_answerer
from trading.console.state_reader import gather_briefing, read_command_map
from trading.notify.telegram import TelegramNotifier
from trading.slowloop.agents.news import NewsSource
from trading.slowloop.llm.anthropic_client import Responder


class ConsoleKillSwitch(Protocol):
    """The kill-switch surface the console needs: ESCALATE (trip/hard_stop) + READ (read/reason).

    The real ``KillSwitch`` satisfies this. There is deliberately NO ``arm`` — re-arm stays CLI-only
    (§7), so the console can never re-arm even by accident.
    """

    def trip(self, reason: str) -> object: ...

    def hard_stop(self, reason: str) -> object: ...

    def read(self) -> object: ...

    def reason(self) -> str: ...


_API_BASE: Final[str] = "https://api.telegram.org"
_LONG_POLL_TIMEOUT_S: Final[int] = 25
DEFAULT_NEWS_PATH = Path("state/slowloop/news_state.json")
DEFAULT_REGIME_ADVISORY_PATH = Path("state/slowloop/regime_advisory.json")

#: ``(url, params) -> parsed_json``. RAISES ``ConsoleError`` (token-free) on transport failure.
HttpGet = Callable[[str, dict[str, int]], dict[str, Any]]


def _httpx_get(url: str, params: dict[str, int]) -> dict[str, Any]:
    try:
        resp = httpx.get(url, params=params, timeout=_LONG_POLL_TIMEOUT_S + 5)
    except Exception as exc:
        raise ConsoleError(f"telegram getUpdates failed: {type(exc).__name__}") from None
    if resp.status_code // 100 != 2:
        raise ConsoleError(f"telegram getUpdates returned HTTP {resp.status_code}")
    parsed: dict[str, Any] = resp.json()
    return parsed


def make_telegram_fetcher(
    token: str, *, timeout_s: int = _LONG_POLL_TIMEOUT_S, http_get: HttpGet = _httpx_get
) -> UpdatesFetcher:
    """Build a getUpdates fetcher: ``offset -> updates``. The token stays in a non-logged URL."""

    def fetch(offset: int | None) -> list[dict[str, object]]:
        url = f"{_API_BASE}/bot{token}/getUpdates"
        params: dict[str, int] = {"timeout": timeout_s}
        if offset is not None:
            params["offset"] = offset
        payload = http_get(url, params)
        result = payload.get("result", []) if isinstance(payload, dict) else []
        return [u for u in result if isinstance(u, dict)]

    return fetch


def _utc_now() -> datetime:
    return datetime.now(UTC)


def build_console_deps(
    *,
    notifier: TelegramNotifier,
    kill_switch: ConsoleKillSwitch,
    responder: Responder,
    news_source: NewsSource | None = None,
    agent_responder: Responder | None = None,
    agent_model: str = "claude-haiku-4-5-20251001",
    news_path: Path = DEFAULT_NEWS_PATH,
    regime_advisory_path: Path = DEFAULT_REGIME_ADVISORY_PATH,
    now_provider: Callable[[], datetime] = _utc_now,
) -> ConsoleDeps:
    """Assemble the console actuators + grounded Q&A responder + the on-demand news refresh.

    When a live ``news_source`` + an ``agent_responder`` (Haiku) are supplied, the console gains the
    Inc-8.6 PART C on-demand refresh: a market/news/status question (or ``/nyheter``) freshens real
    news before grounding (rate-limited, fail-closed, swallowed). Absent them, ``refresh_news`` is
    the default no-op and the console answers from whatever the slow-loop runner last wrote.
    """

    def briefing_provider() -> str:
        return gather_briefing(
            kill_switch,
            news_path=news_path,
            regime_advisory_path=regime_advisory_path,
            now=now_provider(),
        ).to_prompt_text()

    refresh_news: Callable[[], object]
    if news_source is not None and agent_responder is not None:
        refresh_news = build_news_refresher(
            RefreshContext(
                news_source=news_source,
                responder=agent_responder,
                model_id=agent_model,
                news_path=news_path,
                now=now_provider,
            )
        )
    else:
        refresh_news = _no_op_refresh

    return ConsoleDeps(
        kill_switch=kill_switch,
        reply=notifier.send_message,  # outbound is re-sanitized by the notifier
        answer=build_answerer(responder, briefing_provider=briefing_provider),
        reads=read_command_map(
            kill_switch,
            news_path=news_path,
            regime_advisory_path=regime_advisory_path,
            now_provider=now_provider,
        ),
        refresh_news=refresh_news,
    )


def build_poller(
    *,
    token: str,
    operator_chat_id: str,
    deps: ConsoleDeps,
    offset_path: Path = DEFAULT_OFFSET_PATH,
    fetch_updates: UpdatesFetcher | None = None,
) -> ConsolePoller:
    """Wire the durable-offset poller: getUpdates -> auth -> sanitize -> deterministic dispatch."""
    fetch = fetch_updates if fetch_updates is not None else make_telegram_fetcher(token)
    return ConsolePoller(
        fetch_updates=fetch,
        handle=lambda message: handle_message(message.text, deps),
        offset_path=offset_path,
        operator_chat_id=operator_chat_id,
    )
