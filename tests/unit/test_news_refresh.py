"""C5 — on-demand news refresh: agentic, rate-limited, fail-closed (Increment 8.6 PART C).

``maybe_refresh_news`` freshens ``news_state.json`` ONLY when stale AND off-cooldown, runs the news
agent through the fail-closed ``run_agent`` choke, and is FULLY SWALLOWED so it can never break a
console reply. The cooldown is persisted + stamped ON ATTEMPT + FAILS CLOSED on a corrupt file, so a
hard-down vendor cannot be re-hit per message. It writes ONLY ``news_state.json`` + its own
cooldown/health files — never a broker/kill-switch/SUBMIT_GO surface.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from trading.console.news_refresh import (
    RefreshContext,
    RefreshOutcome,
    build_news_refresher,
    maybe_refresh_news,
)
from trading.slowloop.agents.news import NewsItem
from trading.slowloop.contract import (
    AgentArtifact,
    NewsPayload,
    Source,
)
from trading.slowloop.sources.errors import NewsSourceError
from trading.slowloop.store import read_artifact, write_artifact

_NOW = datetime(2026, 6, 27, 12, 0, tzinfo=UTC)


def _now() -> datetime:
    return _NOW


def _good_source() -> list[NewsItem]:
    return [NewsItem(title="Fed holds rates", source="reuters.com", published_at=_NOW)]


def _ok_responder(system: str, user: str) -> str:
    return '{"summary": "lugnt övernattsläge", "tone": "mixed", "confidence": 0.7}'


def _ctx(tmp_path: Path, **kw: object) -> RefreshContext:
    base = dict(
        news_source=_good_source,
        responder=_ok_responder,
        model_id="claude-haiku",
        news_path=tmp_path / "news_state.json",
        cooldown_path=tmp_path / "_cooldown.json",
        health_path=tmp_path / "_health.json",
        now=_now,
    )
    base.update(kw)
    return RefreshContext(**base)  # type: ignore[arg-type]


def _fresh_news(path: Path, as_of: datetime) -> None:
    art = AgentArtifact(
        agent_name="news",
        reliability="textual",
        confidence=0.8,
        as_of=as_of,
        produced_at=as_of,
        model_id="x",
        sources=[Source(kind="news", ref="reuters.com", as_of=as_of)],
        status="ok",
        payload=NewsPayload(headline_count=1, summary="gammalt", tone="mixed"),
    )
    write_artifact(path, art)


# ---------------------------------------------------------------- the gates


def test_no_source_is_noop(tmp_path: Path) -> None:
    assert maybe_refresh_news(_ctx(tmp_path, news_source=None)) is RefreshOutcome.NO_SOURCE


def test_fresh_news_skips_the_fetch(tmp_path: Path) -> None:
    calls = {"n": 0}

    def counting_source() -> list[NewsItem]:
        calls["n"] += 1
        return _good_source()

    ctx = _ctx(tmp_path, news_source=counting_source)
    _fresh_news(ctx.news_path, _NOW - timedelta(minutes=5))  # younger than the 30-min guard
    assert maybe_refresh_news(ctx) is RefreshOutcome.FRESH_NOOP
    assert calls["n"] == 0  # no fetch when news is fresh


def test_stale_news_refreshes_and_writes(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)  # no news file -> stale
    assert maybe_refresh_news(ctx) is RefreshOutcome.REFRESHED
    art = read_artifact(ctx.news_path)
    assert art is not None and isinstance(art.payload, NewsPayload)
    assert ctx.cooldown_path.exists()  # cooldown stamped


def test_cooldown_blocks_a_second_fetch(tmp_path: Path) -> None:
    calls = {"n": 0}

    def counting_source() -> list[NewsItem]:
        calls["n"] += 1
        return _good_source()

    ctx = _ctx(tmp_path, news_source=counting_source)
    assert maybe_refresh_news(ctx) is RefreshOutcome.REFRESHED
    # a stale file again, same now -> the cooldown must block (only ~5 min would have passed)
    ctx.news_path.unlink()
    assert maybe_refresh_news(ctx) is RefreshOutcome.COOLDOWN_NOOP
    assert calls["n"] == 1  # exactly ONE fetch despite two stale requests


def test_corrupt_cooldown_fails_closed(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    ctx.cooldown_path.write_text("{ this is not valid json", encoding="utf-8")
    assert maybe_refresh_news(ctx) is RefreshOutcome.COOLDOWN_NOOP  # corrupt -> block (fail closed)


def test_always_raising_vendor_attempts_exactly_once(tmp_path: Path) -> None:
    calls = {"n": 0}

    def boom() -> list[NewsItem]:
        calls["n"] += 1
        raise NewsSourceError("vendor down")

    ctx = _ctx(tmp_path, news_source=boom)
    first = maybe_refresh_news(ctx)
    second = maybe_refresh_news(ctx)
    third = maybe_refresh_news(ctx)
    assert first is RefreshOutcome.DISCARDED  # run_agent caught the source error, kept last-good
    assert second is RefreshOutcome.COOLDOWN_NOOP and third is RefreshOutcome.COOLDOWN_NOOP
    assert calls["n"] == 1  # cooldown stamped on the first attempt blocks the flood


def test_refresh_never_raises(tmp_path: Path) -> None:
    # An exception anywhere returns an outcome, never propagates (the reply must always proceed).
    def explode() -> list[NewsItem]:
        raise RuntimeError("unexpected non-NewsSourceError")

    out = maybe_refresh_news(_ctx(tmp_path, news_source=explode))
    assert out in (RefreshOutcome.DISCARDED, RefreshOutcome.ERROR_SWALLOWED)


def test_refresh_writes_only_its_own_state_no_markers(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    maybe_refresh_news(ctx)
    names = {p.name for p in tmp_path.iterdir()}
    assert names <= {"news_state.json", "_cooldown.json", "_health.json"}
    for marker in ("SUBMIT_GO", "SCHEDULER_ENABLE", "LIVE_MODE_CONFIRMED", "kill_switch.json"):
        assert not (tmp_path / marker).exists()


def test_build_news_refresher_is_callable(tmp_path: Path) -> None:
    refresh = build_news_refresher(_ctx(tmp_path))
    assert refresh() is RefreshOutcome.REFRESHED


def test_cooldown_stamp_is_iso_parseable(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    maybe_refresh_news(ctx)
    raw = json.loads(ctx.cooldown_path.read_text(encoding="utf-8"))
    assert datetime.fromisoformat(raw["last_attempt"]) == _NOW
