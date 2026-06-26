"""C2 — the slow-loop ORCHESTRATOR (Inc-8 PART A).

``run_agent`` runs one agent, validates its output, and FAILS CLOSED: an exception during produce,
an ``uncertain`` status, or a below-floor confidence DISCARDS the output (the last-good artifact
on disk is left byte-identical), increments a persisted consecutive-failure counter, and pages the
operator ORANGE once the count reaches N (default 3 — one step before §8's 5-error abandonment). A
healthy run atomically writes the artifact and resets the counter. §1.2: one bad agent never stops
the others; the failure is local, the alert is global.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from trading.notify.telegram import Severity
from trading.slowloop.contract import AgentArtifact, NewsPayload, Source
from trading.slowloop.llm.anthropic_client import Responder
from trading.slowloop.orchestrator import run_agent
from trading.slowloop.store import read_artifact

_TS = datetime(2026, 6, 26, 9, 30, tzinfo=UTC)


def _artifact(**over: object) -> AgentArtifact:
    base: dict[str, object] = dict(
        schema_version=1,
        agent_name="news",
        reliability="textual",
        confidence=0.6,
        as_of=_TS,
        produced_at=_TS,
        model_id="claude-test",
        sources=[Source(kind="news", ref="reuters", as_of=_TS)],
        status="ok",
        payload=NewsPayload(headline_count=1, summary="calm", tone="mixed"),
    )
    base.update(over)
    return AgentArtifact(**base)  # type: ignore[arg-type]


class _FakeAgent:
    def __init__(
        self,
        output_path: Path,
        *,
        artifact: AgentArtifact | None = None,
        raises: Exception | None = None,
        name: str = "news",
    ) -> None:
        self.name = name
        self.output_path = output_path
        self._artifact = artifact
        self._raises = raises

    def produce(self, responder: Responder) -> AgentArtifact:
        if self._raises is not None:
            raise self._raises
        assert self._artifact is not None
        return self._artifact


class _SpyPager:
    def __init__(self) -> None:
        self.pages: list[tuple[Severity, str]] = []

    def page_operator(self, severity: Severity, text: str) -> None:
        self.pages.append((severity, text))


def _noop_responder(system: str, user: str) -> str:  # never actually called by a fake agent
    return ""


def test_healthy_run_writes_artifact_and_resets_counter(tmp_path: Path) -> None:
    out = tmp_path / "news_state.json"
    health = tmp_path / "_health.json"
    agent = _FakeAgent(out, artifact=_artifact())
    result = run_agent(agent, _noop_responder, health_path=health)
    assert result.written is True
    assert read_artifact(out) == _artifact()
    assert result.consecutive_failures == 0


def test_invalid_produce_discards_and_keeps_last_known_good(tmp_path: Path) -> None:
    out = tmp_path / "news_state.json"
    health = tmp_path / "_health.json"
    # seed a last-known-good artifact
    good = _artifact(confidence=0.9)
    run_agent(_FakeAgent(out, artifact=good), _noop_responder, health_path=health)
    before = out.read_bytes()

    # now an agent whose produce explodes
    failing = _FakeAgent(out, raises=ValueError("LLM emitted garbage"))
    result = run_agent(failing, _noop_responder, health_path=health)
    assert result.written is False
    assert out.read_bytes() == before  # last-known-good untouched, never a torn file
    assert read_artifact(out) == good


def test_uncertain_status_is_discarded(tmp_path: Path) -> None:
    out = tmp_path / "news_state.json"
    health = tmp_path / "_health.json"
    uncertain = _artifact(status="uncertain", sources=[])
    result = run_agent(_FakeAgent(out, artifact=uncertain), _noop_responder, health_path=health)
    assert result.written is False
    assert read_artifact(out) is None  # nothing written


def test_below_floor_confidence_is_discarded(tmp_path: Path) -> None:
    out = tmp_path / "news_state.json"
    health = tmp_path / "_health.json"
    timid = _artifact(confidence=0.3)
    result = run_agent(
        _FakeAgent(out, artifact=timid), _noop_responder, health_path=health, confidence_floor=0.4
    )
    assert result.written is False
    assert read_artifact(out) is None


def test_confidence_exactly_at_floor_is_kept(tmp_path: Path) -> None:
    out = tmp_path / "news_state.json"
    health = tmp_path / "_health.json"
    result = run_agent(
        _FakeAgent(out, artifact=_artifact(confidence=0.4)),
        _noop_responder,
        health_path=health,
        confidence_floor=0.4,
    )
    assert result.written is True


def test_orange_page_fires_exactly_once_at_N_consecutive_failures(tmp_path: Path) -> None:
    out = tmp_path / "news_state.json"
    health = tmp_path / "_health.json"
    pager = _SpyPager()
    failing = _FakeAgent(out, raises=ValueError("boom"))

    for _ in range(3):
        run_agent(failing, _noop_responder, notifier=pager, health_path=health, alert_after=3)

    assert len(pager.pages) == 1, f"expected one ORANGE page at the 3rd failure, got {pager.pages}"
    severity, text = pager.pages[0]
    assert severity is Severity.ORANGE
    assert "news" in text


def test_corrupt_health_file_fails_closed_to_a_fresh_counter(tmp_path: Path) -> None:
    # A corrupt / non-dict health file must not crash the orchestrator — it resets to a fresh count.
    out = tmp_path / "news_state.json"
    health = tmp_path / "_health.json"
    health.write_text("[1, 2, 3]", encoding="utf-8")  # well-formed JSON, but not a dict
    result = run_agent(
        _FakeAgent(out, raises=ValueError("boom")), _noop_responder, health_path=health
    )
    assert result.written is False
    assert result.consecutive_failures == 1  # treated as a fresh count, not a crash


def test_a_success_resets_the_failure_counter(tmp_path: Path) -> None:
    out = tmp_path / "news_state.json"
    health = tmp_path / "_health.json"
    pager = _SpyPager()
    fail = _FakeAgent(out, raises=ValueError("boom"))
    ok = _FakeAgent(out, artifact=_artifact())

    run_agent(fail, _noop_responder, notifier=pager, health_path=health, alert_after=3)
    run_agent(fail, _noop_responder, notifier=pager, health_path=health, alert_after=3)
    run_agent(ok, _noop_responder, notifier=pager, health_path=health, alert_after=3)  # reset
    # two more failures should NOT page (counter was reset to 0, now only 2)
    run_agent(fail, _noop_responder, notifier=pager, health_path=health, alert_after=3)
    run_agent(fail, _noop_responder, notifier=pager, health_path=health, alert_after=3)
    assert pager.pages == []
