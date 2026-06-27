"""The slow-loop RUNNER — ``python -m trading.slowloop.run`` / ``make slowloop`` (Inc-8.6 PART B).

This is what finally RUNS the dormant orchestrator on a cadence so the keys earn their keep: every
~20 min it fetches real Tavily/Apify news → the NewsAgent (which sanitizes each headline BEFORE the
Haiku call) → an atomically-written, schema-validated ``state/slowloop/news_state.json``; every
~60 min it builds a real FRED macro summary → the RegimeSynthAgent → ``regime_advisory.json``. The
console then answers "läs dagens nyheter" with REAL, current headlines.

It is a PURE SCHEDULER over ``run_agent`` — the single fail-closed choke (discard on agent error,
keep last-known-good byte-identical, ORANGE-page the operator at 3 failures). It writes ONLY the
agents' own ``state/slowloop/`` outputs + ``_health.json``; it NEVER touches a submit-path marker
(SCHEDULER_ENABLE / SUBMIT_GO / kill_switch). It lives INSIDE ``trading.slowloop`` so the PHI1
boundary holds (it imports NO broker/order/driver/scheduler symbol). It is STRICTLY distinct from
the console chat listener AND from the dormant trading scheduler. ``run_forever`` is sleep-/clock-
injected and predicate-bounded so the loop runs offline against fakes; one ``live`` smoke hits the
real APIs. A real infra error (unwritable ``state/``) propagates LOUDLY — not retried.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import structlog

from trading.notify.telegram import build_notifier
from trading.settings import load_model_settings, load_notify_settings, load_settings
from trading.slowloop.agents.news import NewsAgent
from trading.slowloop.agents.regime_synth import RegimeSynthAgent
from trading.slowloop.llm.anthropic_client import Responder, build_responder
from trading.slowloop.orchestrator import Agent, Pager, run_agent
from trading.slowloop.sources.factory import build_market_summary_source, build_news_source

_log = structlog.get_logger(__name__)

#: The producer side of the contract with console/state_reader (which reads these exact paths).
NEWS_PATH = Path("state/slowloop/news_state.json")
REGIME_ADVISORY_PATH = Path("state/slowloop/regime_advisory.json")

NEWS_INTERVAL = timedelta(minutes=20)  # ~72 calls/day, well under Tavily free 1000/mo
REGIME_INTERVAL = timedelta(minutes=60)
_DEFAULT_TICK_S = 60.0


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class ScheduledAgent:
    """An orchestrator ``Agent`` paired with how often the runner should run it."""

    agent: Agent
    interval: timedelta


def run_forever(
    schedule: Sequence[ScheduledAgent],
    responder: Responder,
    *,
    notifier: Pager | None,
    sleep: Callable[[float], None],
    should_continue: Callable[[], bool],
    now: Callable[[], datetime],
    tick_seconds: float = _DEFAULT_TICK_S,
    health_path: Path | None = None,
    log: structlog.BoundLogger | None = None,
) -> None:
    """Drive each due agent through ``run_agent`` on its cadence; sleep a tick between sweeps.

    Each agent is run when ``now() >= next_due``; ``run_agent`` is the fail-closed choke (it never
    raises on an agent/transport error — it discards, counts, and ORANGE-pages at 3). The ONLY thing
    that can propagate out of this loop is a genuine infra error (e.g. unwritable ``state/``), and
    that SHOULD surface loudly rather than be retried into a silent wedge. ``KeyboardInterrupt`` is
    handled by ``main`` so this stays a pure, sleep-injected, predicate-bounded function.
    """
    out = log if log is not None else _log
    next_due = {sa.agent.name: now() for sa in schedule}  # every agent is due immediately on start
    while should_continue():
        current = now()
        for sa in schedule:
            if current >= next_due[sa.agent.name]:
                if health_path is None:
                    result = run_agent(sa.agent, responder, notifier=notifier)
                else:
                    result = run_agent(
                        sa.agent, responder, notifier=notifier, health_path=health_path
                    )
                out.info(
                    "slowloop_agent_ran",
                    agent=sa.agent.name,
                    written=result.written,
                    reason=result.reason,
                )
                next_due[sa.agent.name] = current + sa.interval
        sleep(tick_seconds)


def assemble_schedule(
    *,
    tavily_token: str | None,
    apify_token: str | None,
    fred_token: str | None,
    agent_model: str,
    now_provider: Callable[[], datetime] = _utc_now,
) -> list[ScheduledAgent]:
    """Build the live ScheduledAgents from available tokens (pure — no settings/network read).

    News is scheduled iff a Tavily/Apify token exists; the FRED regime advisory iff a FRED key
    exists. A missing optional key simply leaves that agent UNSCHEDULED (degrade, never crash).
    """
    schedule: list[ScheduledAgent] = []
    news_source = build_news_source(tavily_token=tavily_token, apify_token=apify_token)
    if news_source is not None:
        schedule.append(
            ScheduledAgent(
                NewsAgent(
                    news_source=news_source,
                    output_path=NEWS_PATH,
                    model_id=agent_model,
                    now_provider=now_provider,
                ),
                NEWS_INTERVAL,
            )
        )
    market_summary = build_market_summary_source(fred_token=fred_token)
    if market_summary is not None:
        schedule.append(
            ScheduledAgent(
                RegimeSynthAgent(
                    market_summary_source=market_summary,
                    output_path=REGIME_ADVISORY_PATH,
                    model_id=agent_model,
                    now_provider=now_provider,
                ),
                REGIME_INTERVAL,
            )
        )
    return schedule


def build_slowloop_deps() -> tuple[list[ScheduledAgent], Responder, Pager | None]:
    """Wire the live schedule + responder + notifier from settings/.env (fail-closed if keys gone).

    The agents run on the cheap STRUCTURED model (Haiku via ``AGENT_MODEL_ID``). A missing Telegram
    token leaves the notifier ``None`` (the orchestrator's ORANGE page is then a no-op; artifacts
    still write).
    """
    settings = load_settings()  # fail-fast: ANTHROPIC_API_KEY required
    key = settings.get("ANTHROPIC_API_KEY")
    _conversation_model, agent_model = load_model_settings()
    responder = build_responder(key, agent_model)

    token, chat_id = load_notify_settings()
    notifier: Pager | None = build_notifier(token, chat_id) if (token and chat_id) else None

    schedule = assemble_schedule(
        tavily_token=settings.get("TAVILY_API_KEY"),
        apify_token=settings.get("APIFY_TOKEN"),
        fred_token=settings.get("FRED_API_KEY"),
        agent_model=agent_model,
    )
    return schedule, responder, notifier


def main() -> int:
    """Build the slow loop from the environment and run it until Ctrl-C."""
    schedule, responder, notifier = build_slowloop_deps()
    _log.info(
        "slowloop_runner_starting",
        agents=[sa.agent.name for sa in schedule],
        news_interval_min=int(NEWS_INTERVAL.total_seconds() // 60),
    )
    if not schedule:
        _log.warning("slowloop_no_agents_configured")  # no optional keys -> nothing to run
        return 0
    try:
        run_forever(
            schedule,
            responder,
            notifier=notifier,
            sleep=time.sleep,
            should_continue=lambda: True,
            now=_utc_now,
        )
    except KeyboardInterrupt:
        _log.info("slowloop_runner_stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
