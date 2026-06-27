"""Console ON-DEMAND news refresh — agentic, rate-limited, fail-closed (Inc-8.6 PART C).

The operator's ask (verbatim): "if I ask casual questions or about the market it should search for
info so it doesn't talk nonsense … be like YOU, do things when you notice I need them … it should
just HAPPEN." So before the console answers a market/news/status question, it PROACTIVELY freshens
the real news — no command needed — bounded so it can never become a cost amplifier:

  1. FRESHNESS skip — if ``news_state.json`` is younger than ``ON_DEMAND_MAX_AGE`` (30 min; the
     ~20-min runner usually keeps it fresh) → no fetch (``FRESH_NOOP``).
  2. COOLDOWN gate — a PERSISTED, attempt-stamped cooldown caps on-demand fetches to <=6/hr. It is
     stamped ON ATTEMPT (before the fetch) and FAILS CLOSED on a corrupt file (present-but-bad →
     treated as "recently attempted" → blocked), so a hard-down vendor is not re-hit per message.
  3. else — run the news agent through the fail-closed ``run_agent`` choke (sanitize → Haiku →
     validate → atomic write of ``news_state.json``), ``notifier=None`` (a refresh failure degrades
     silently; only the RUNNER pages).

The WHOLE body is wrapped so any error degrades to ``ERROR_SWALLOWED`` — the dispatcher ignores the
return and always answers, so a refresh failure leaves the existing honest "otillgänglig". This is
NOT an acting surface: it writes ONLY ``news_state.json`` + its own cooldown file; it makes ZERO
broker / kill-switch / SUBMIT_GO calls. It lives in ``console`` (which may import ``slowloop``);
PHI1 is unchanged (the submit path imports neither).
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path

import structlog

from trading.slowloop.agents.news import NewsAgent, NewsSource
from trading.slowloop.llm.anthropic_client import Responder
from trading.slowloop.orchestrator import run_agent
from trading.slowloop.store import read_artifact

_log = structlog.get_logger(__name__)

DEFAULT_NEWS_PATH = Path("state/slowloop/news_state.json")
DEFAULT_COOLDOWN_PATH = Path("state/slowloop/_news_refresh_cooldown.json")
DEFAULT_ONDEMAND_HEALTH_PATH = Path("state/slowloop/_ondemand_health.json")
ON_DEMAND_MAX_AGE = timedelta(minutes=30)
COOLDOWN = timedelta(minutes=10)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class RefreshOutcome(StrEnum):
    """What an on-demand refresh did (returned for logging/tests; the dispatcher ignores it)."""

    NO_SOURCE = "no_source"
    FRESH_NOOP = "fresh_noop"
    COOLDOWN_NOOP = "cooldown_noop"
    REFRESHED = "refreshed"
    DISCARDED = "discarded"
    ERROR_SWALLOWED = "error_swallowed"


@dataclass(frozen=True, slots=True)
class RefreshContext:
    """Everything ``maybe_refresh_news`` needs (injectable for fully offline tests)."""

    news_source: NewsSource | None
    responder: Responder
    model_id: str
    news_path: Path = DEFAULT_NEWS_PATH
    cooldown_path: Path = DEFAULT_COOLDOWN_PATH
    health_path: Path = DEFAULT_ONDEMAND_HEALTH_PATH
    max_age: timedelta = ON_DEMAND_MAX_AGE
    cooldown: timedelta = COOLDOWN
    now: Callable[[], datetime] = _utc_now


def _is_fresh(path: Path, now: datetime, max_age: timedelta) -> bool:
    art = read_artifact(path)  # fails closed to None on missing/torn/corrupt
    if art is None:
        return False
    return (now - art.as_of) <= max_age


def _cooldown_active(path: Path, now: datetime, cooldown: timedelta) -> bool:
    """True if an attempt happened within ``cooldown``; FAIL CLOSED (block) on a corrupt file."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return False  # never attempted -> allow the first fetch
    except (OSError, ValueError):
        return True  # corrupt/unreadable -> fail CLOSED (treat as recently attempted -> block)
    ts = raw.get("last_attempt") if isinstance(raw, dict) else None
    if not isinstance(ts, str):
        return True  # malformed -> fail closed
    try:
        last = datetime.fromisoformat(ts)
    except ValueError:
        return True  # unparseable -> fail closed
    return (now - last) < cooldown


def _stamp_cooldown(path: Path, now: datetime) -> None:
    """Atomically record the attempt time (temp -> fsync -> os.replace), like the kill switch."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / (path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"last_attempt": now.isoformat()}, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def maybe_refresh_news(ctx: RefreshContext) -> RefreshOutcome:
    """Refresh ``news_state.json`` iff stale AND off-cooldown; swallowed (never breaks a reply).

    Returns an outcome for logging/tests; the dispatcher ignores it and always answers.
    """
    try:
        if ctx.news_source is None:
            return RefreshOutcome.NO_SOURCE
        now = ctx.now()
        if _is_fresh(ctx.news_path, now, ctx.max_age):
            return RefreshOutcome.FRESH_NOOP
        if _cooldown_active(ctx.cooldown_path, now, ctx.cooldown):
            return RefreshOutcome.COOLDOWN_NOOP
        _stamp_cooldown(ctx.cooldown_path, now)  # stamp ON ATTEMPT, before the fetch returns
        agent = NewsAgent(
            news_source=ctx.news_source,
            output_path=ctx.news_path,
            model_id=ctx.model_id,
            now_provider=ctx.now,
        )
        result = run_agent(agent, ctx.responder, notifier=None, health_path=ctx.health_path)
        return RefreshOutcome.REFRESHED if result.written else RefreshOutcome.DISCARDED
    except Exception:  # an on-demand refresh must NEVER break the console reply
        _log.warning("news_refresh_swallowed")
        return RefreshOutcome.ERROR_SWALLOWED


def build_news_refresher(ctx: RefreshContext) -> Callable[[], object]:
    """Bind ``maybe_refresh_news`` to a context as the ``ConsoleDeps.refresh_news`` callable."""

    def refresh() -> object:
        return maybe_refresh_news(ctx)

    return refresh
