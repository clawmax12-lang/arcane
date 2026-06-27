"""C4 — the slow-loop runner (Increment 8.6 PART B).

``run_forever`` is a PURE SCHEDULER over the orchestrator's fail-closed ``run_agent`` choke. It is
sleep-/clock-injected and predicate-bounded so it runs fully offline. The runner writes ONLY the
agents' ``state/slowloop/`` outputs — never a submit-path marker. ``assemble_schedule`` is
pure (token-driven), so the wiring is tested without reading ``.env`` or the network.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from trading.console.app import DEFAULT_NEWS_PATH, DEFAULT_REGIME_ADVISORY_PATH
from trading.slowloop.contract import AgentArtifact, NewsPayload, Source
from trading.slowloop.llm.anthropic_client import Responder
from trading.slowloop.run import (
    NEWS_PATH,
    REGIME_ADVISORY_PATH,
    ScheduledAgent,
    assemble_schedule,
    run_forever,
)

_T0 = datetime(2026, 6, 27, 12, 0, tzinfo=UTC)


def _artifact(now: datetime) -> AgentArtifact:
    return AgentArtifact(
        agent_name="news",
        reliability="textual",
        confidence=0.8,
        as_of=now,
        produced_at=now,
        model_id="claude-test",
        sources=[Source(kind="news", ref="reuters.com", as_of=now)],
        status="ok",
        payload=NewsPayload(headline_count=1, summary="lugnt", tone="mixed"),
    )


class _FakeAgent:
    """A minimal orchestrator Agent: writes a valid artifact, counts produce calls."""

    def __init__(self, name: str, output_path: Path) -> None:
        self.name = name
        self.output_path = output_path
        self.calls = 0

    def produce(self, responder: Responder) -> AgentArtifact:
        self.calls += 1
        return _artifact(_T0)


def _responder(system: str, user: str) -> str:  # never actually called by the fake agent
    return "{}"


def _clock(times: list[datetime]) -> object:
    it = iter(times)

    def now() -> datetime:
        return next(it)

    return now


def test_runs_each_due_agent_once_per_tick(tmp_path: Path) -> None:
    agent = _FakeAgent("news", tmp_path / "news.json")
    sched = [ScheduledAgent(agent, timedelta(minutes=20))]
    # three sweeps spaced 20 min apart -> the agent is due each sweep
    times = [_T0, _T0, _T0 + timedelta(minutes=20), _T0 + timedelta(minutes=40)]
    calls = {"n": 0}

    def should_continue() -> bool:
        calls["n"] += 1
        return calls["n"] <= 3

    run_forever(
        sched,
        _responder,
        notifier=None,
        sleep=lambda _s: None,
        should_continue=should_continue,
        now=_clock(times),
        health_path=tmp_path / "_health.json",
    )
    assert agent.calls == 3
    assert (tmp_path / "news.json").exists()  # the artifact was written


def test_respects_the_interval_between_sweeps(tmp_path: Path) -> None:
    agent = _FakeAgent("news", tmp_path / "news.json")
    sched = [ScheduledAgent(agent, timedelta(minutes=20))]
    # sweeps only 1 min apart -> due once, then not again until 20 min elapse
    times = [_T0, _T0, _T0 + timedelta(minutes=1), _T0 + timedelta(minutes=2)]
    calls = {"n": 0}

    def should_continue() -> bool:
        calls["n"] += 1
        return calls["n"] <= 3

    run_forever(
        sched,
        _responder,
        notifier=None,
        sleep=lambda _s: None,
        should_continue=should_continue,
        now=_clock(times),
        health_path=tmp_path / "_health.json",
    )
    assert agent.calls == 1  # ran once; not due again within 20 min


def test_runner_writes_only_its_own_state_never_a_submit_marker(tmp_path: Path) -> None:
    agent = _FakeAgent("news", tmp_path / "slowloop" / "news.json")
    sched = [ScheduledAgent(agent, timedelta(minutes=20))]
    calls = {"n": 0}

    def should_continue() -> bool:
        calls["n"] += 1
        return calls["n"] <= 1

    run_forever(
        sched,
        _responder,
        notifier=None,
        sleep=lambda _s: None,
        should_continue=should_continue,
        now=_clock([_T0, _T0]),
        health_path=tmp_path / "slowloop" / "_health.json",
    )
    written = {p.name for p in (tmp_path / "slowloop").iterdir()}
    assert written == {"news.json", "_health.json"}  # ONLY the agent's own outputs
    for marker in ("SUBMIT_GO", "SCHEDULER_ENABLE", "LIVE_MODE_CONFIRMED", "kill_switch.json"):
        assert not (tmp_path / marker).exists()
        assert not (tmp_path / "slowloop" / marker).exists()


# ---------------------------------------------------------------- schedule assembly


def test_assemble_news_only_when_only_tavily() -> None:
    sched = assemble_schedule(
        tavily_token="tv", apify_token=None, fred_token=None, agent_model="haiku"
    )
    assert [s.agent.name for s in sched] == ["news"]


def test_assemble_regime_only_when_only_fred() -> None:
    sched = assemble_schedule(
        tavily_token=None, apify_token=None, fred_token="fr", agent_model="haiku"
    )
    assert [s.agent.name for s in sched] == ["regime_synth"]


def test_assemble_both_when_keys_present() -> None:
    sched = assemble_schedule(
        tavily_token="tv", apify_token="ap", fred_token="fr", agent_model="haiku"
    )
    assert [s.agent.name for s in sched] == ["news", "regime_synth"]


def test_assemble_empty_when_no_optional_keys() -> None:
    sched = assemble_schedule(
        tavily_token=None, apify_token=None, fred_token=None, agent_model="haiku"
    )
    assert sched == []


# ---------------------------------------------------------- the producer/consumer path contract


def test_runner_paths_match_the_console_reader_paths() -> None:
    # The runner is the PRODUCER; console/state_reader is the CONSUMER. If these drift, the console
    # silently reads an empty path forever — pin them equal.
    assert NEWS_PATH == DEFAULT_NEWS_PATH
    assert REGIME_ADVISORY_PATH == DEFAULT_REGIME_ADVISORY_PATH
