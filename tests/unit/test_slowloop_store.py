"""C1 — the atomic, fail-closed artifact STORE (Inc-8 PART A).

Mirrors ``kill_switch._write`` exactly (temp -> fsync -> os.replace) so a half-written artifact is
never observable. ``read_artifact`` fails CLOSED: a missing / torn / corrupt / schema-invalid file
returns ``None`` ("unavailable") and NEVER raises into a reader — a corrupt file is the same as
"no data yet", and "no data" is always safe (the acting path already fails closed to zero
candidates). Each agent owns exactly ONE output path (one output domain).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from trading.slowloop.contract import AgentArtifact, NewsPayload, Source
from trading.slowloop.store import read_artifact, write_artifact

_TS = datetime(2026, 6, 26, 9, 30, tzinfo=UTC)


def _artifact() -> AgentArtifact:
    return AgentArtifact(
        schema_version=1,
        agent_name="news",
        reliability="textual",
        confidence=0.6,
        as_of=_TS,
        produced_at=_TS,
        model_id="claude-test",
        sources=[Source(kind="news", ref="reuters", as_of=_TS)],
        status="ok",
        payload=NewsPayload(headline_count=2, summary="calm", tone="mixed"),
    )


def test_write_then_read_roundtrips(tmp_path: Path) -> None:
    p = tmp_path / "news_state.json"
    art = _artifact()
    write_artifact(p, art)
    got = read_artifact(p)
    assert got == art


def test_read_missing_file_returns_none(tmp_path: Path) -> None:
    assert read_artifact(tmp_path / "nope.json") is None


def test_read_corrupt_json_returns_none_not_raises(tmp_path: Path) -> None:
    p = tmp_path / "news_state.json"
    p.write_text("{ this is not json", encoding="utf-8")
    assert read_artifact(p) is None  # fail closed, never raises


def test_read_schema_invalid_json_returns_none(tmp_path: Path) -> None:
    p = tmp_path / "news_state.json"
    # well-formed JSON, but reliability forged to a gateable tier -> schema rejects -> None.
    p.write_text('{"reliability": "hard", "agent_name": "news"}', encoding="utf-8")
    assert read_artifact(p) is None


def test_write_is_atomic_no_tmp_left_behind(tmp_path: Path) -> None:
    p = tmp_path / "news_state.json"
    write_artifact(p, _artifact())
    leftovers = [q.name for q in tmp_path.iterdir() if q.name != "news_state.json"]
    assert leftovers == [], f"non-atomic write left scratch files: {leftovers}"


def test_a_stale_tmp_file_does_not_corrupt_a_read(tmp_path: Path) -> None:
    # Simulate a crash mid-write (a .tmp exists but os.replace never ran): the reader must see the
    # PRIOR valid artifact, never a torn parse from the partial temp file.
    p = tmp_path / "news_state.json"
    write_artifact(p, _artifact())
    (tmp_path / "news_state.json.tmp").write_text("{ half written", encoding="utf-8")
    assert read_artifact(p) == _artifact()


def test_overwrite_replaces_in_place(tmp_path: Path) -> None:
    p = tmp_path / "news_state.json"
    write_artifact(p, _artifact())
    updated = _artifact().model_copy(update={"confidence": 0.9})
    write_artifact(p, updated)
    got = read_artifact(p)
    assert got is not None and got.confidence == 0.9
