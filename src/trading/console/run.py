"""The ALWAYS-ON console listener — ``python -m trading.console.run`` / ``make console`` (Inc-8.5).

This wakes the dormant poller so a typed Telegram message is answered within seconds. It is the CHAT
listener ONLY — strictly orthogonal to the trading scheduler (which stays ``SCHEDULER_ENABLE``-
dormant) and to the per-order ``SUBMIT_GO``: this module imports, reads, and writes NEITHER. It
lives INSIDE ``trading.console`` so the PHI1 boundary holds — from ``trading.executor`` it imports
ONLY
``kill_switch`` (escalate-only), and no broker/order-placement symbol. The conversation runs on the
operator-selected model (``CONSOLE_MODEL_ID``; default Sonnet). Logging is token-free; the loop is
fail-closed (a transient transport error backs off with a cap, never a crash-loop) and the durable
offset (in ``poller.poll_once``) prevents double-answers and cold-start backlog replay.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import structlog

from trading.console.app import build_console_deps, build_poller
from trading.console.errors import ConsoleError
from trading.console.poller import ConsolePoller
from trading.executor.kill_switch import DEFAULT_KILL_SWITCH_PATH, KillSwitch
from trading.notify.telegram import build_notifier
from trading.settings import load_model_settings, load_notify_settings, load_settings
from trading.slowloop.llm.anthropic_client import build_responder
from trading.slowloop.sources.factory import build_news_source

_log = structlog.get_logger(__name__)

_DEFAULT_IDLE_S = 1.0
_DEFAULT_BASE_BACKOFF_S = 1.0
_DEFAULT_MAX_BACKOFF_S = 60.0


def run_forever(
    poller: ConsolePoller,
    *,
    sleep: Callable[[float], None],
    should_continue: Callable[[], bool],
    idle_interval: float = _DEFAULT_IDLE_S,
    base_backoff: float = _DEFAULT_BASE_BACKOFF_S,
    max_backoff: float = _DEFAULT_MAX_BACKOFF_S,
    log: structlog.BoundLogger | None = None,
) -> None:
    """Drive ``poller.poll_once()`` repeatedly with capped exponential backoff on transport errors.

    ``poll_once`` already (a) long-polls ~25s server-side and (b) wraps EACH update in try/except +
    always advances the durable offset, so the only exception that can reach here is the fetch-level
    ``ConsoleError``. We back off on that (never crash-loop), reset on a clean cycle, and sleep a
    short breather between clean cycles. A non-``ConsoleError`` is deliberately NOT caught (a real
    bug / unwritable-state ``OSError`` should surface loudly, not be retried forever).
    ``KeyboardInterrupt`` is not caught here — ``main`` handles it — so this stays a pure, sleep-
    injected, predicate-bounded function.
    """
    out = log if log is not None else _log
    backoff = base_backoff
    while should_continue():
        try:
            poller.poll_once()
        except ConsoleError as exc:
            out.warning("console_poll_transport_error", error=type(exc).__name__, backoff=backoff)
            sleep(backoff)
            backoff = min(backoff * 2, max_backoff)
            continue
        backoff = base_backoff
        sleep(idle_interval)


def _build_console_poller() -> tuple[ConsolePoller, str]:
    """Build the real console poller from settings/.env; return ``(poller, conversation_model_id)``.

    Fail-closed: a missing ``TELEGRAM_BOT_TOKEN`` or ``TELEGRAM_CHAT_ID`` raises ``ConsoleError``
    (the inbound auth MUST be pinned to a KNOWN operator chat_id — never auto-resolved from "whoever
    messaged last", which would be an auth hole). The same ``chat_id`` pins both the outbound
    notifier and the inbound poller auth. The kill switch must be writable or the console refuses.
    """
    settings = load_settings()  # fail-fast: ANTHROPIC_API_KEY required
    key = settings.get("ANTHROPIC_API_KEY")
    token, chat_id = load_notify_settings()
    conversation_model, agent_model = load_model_settings()
    if not token:
        raise ConsoleError(
            "TELEGRAM_BOT_TOKEN missing — console listener cannot start (fail closed)"
        )
    if not chat_id:
        raise ConsoleError(
            "TELEGRAM_CHAT_ID missing — the listener needs the operator chat_id to authenticate "
            "inbound messages (never auto-resolved); set it in .env (fail closed)"
        )
    kill_switch = KillSwitch(DEFAULT_KILL_SWITCH_PATH)
    kill_switch.verify_writable()  # refuse to start a console that cannot escalate
    notifier = build_notifier(token, chat_id)
    responder = build_responder(key, conversation_model)  # the warm conversation runs on Sonnet
    # Inc-8.6 PART C: a live news source + a cheap Haiku responder power the on-demand refresh so a
    # market/news question (or /nyheter) freshens real news before grounding (rate-limited, hushed).
    news_source = build_news_source(
        tavily_token=settings.get("TAVILY_API_KEY"),
        apify_token=settings.get("APIFY_TOKEN"),
    )
    agent_responder = build_responder(key, agent_model)
    deps = build_console_deps(
        notifier=notifier,
        kill_switch=kill_switch,
        responder=responder,
        news_source=news_source,
        agent_responder=agent_responder,
        agent_model=agent_model,
    )
    poller = build_poller(token=token, operator_chat_id=chat_id, deps=deps)
    return poller, conversation_model


def main() -> int:
    """Build the console from the environment and run the chat listener until Ctrl-C."""
    poller, conversation_model = _build_console_poller()
    _log.info(
        "console_listener_starting",
        model_id=conversation_model,
        idle_interval=_DEFAULT_IDLE_S,
        max_backoff=_DEFAULT_MAX_BACKOFF_S,
    )
    try:
        run_forever(poller, sleep=time.sleep, should_continue=lambda: True)
    except KeyboardInterrupt:
        _log.info("console_listener_stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
