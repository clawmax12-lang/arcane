"""C3 — the console getUpdates long-poll + DURABLE OFFSET + cold-start backlog discard (Inc-8).

The poll loop acknowledges updates by advancing a durably-persisted offset (atomic temp->fsync->
os.replace). On a COLD start (no offset file) it seeds the offset to the current max ``update_id``
and DISCARDS the backlog — so a stale ``/flatta`` cannot replay out of context after the operator
re-armed. Per-update handling is wrapped so one malformed/exploding update advances the offset and
cannot wedge the loop.
"""

from __future__ import annotations

import json
from pathlib import Path

from trading.console.authz import InboundMessage
from trading.console.poller import ConsolePoller

_OP = "123456789"


def _msg_update(uid: int, text: str) -> dict[str, object]:
    return {
        "update_id": uid,
        "message": {"chat": {"id": int(_OP), "type": "private"}, "text": text},
    }


def _poller(
    batches: list[list[dict[str, object]]], offset_path: Path
) -> tuple[ConsolePoller, list[str], list[int | None]]:
    handled: list[str] = []
    seen_offsets: list[int | None] = []
    calls = {"i": 0}

    def fetch(offset: int | None) -> list[dict[str, object]]:
        seen_offsets.append(offset)
        i = calls["i"]
        calls["i"] += 1
        return batches[i] if i < len(batches) else []

    def handle(msg: InboundMessage) -> None:
        handled.append(msg.text)

    poller = ConsolePoller(
        fetch_updates=fetch, handle=handle, offset_path=offset_path, operator_chat_id=_OP
    )
    return poller, handled, seen_offsets


def test_cold_start_seeds_offset_to_max_and_discards_backlog(tmp_path: Path) -> None:
    offset_path = tmp_path / "console_offset.json"
    backlog = [_msg_update(40, "/flatta"), _msg_update(41, "/pausa"), _msg_update(42, "hej")]
    poller, handled, _ = _poller([backlog], offset_path)

    n = poller.poll_once()
    assert n == 0  # NOTHING processed on cold start
    assert handled == []  # the stale /flatta and /pausa were discarded
    assert json.loads(offset_path.read_text())["offset"] == 43  # max(42)+1


def test_warm_start_processes_new_updates_and_advances_offset(tmp_path: Path) -> None:
    offset_path = tmp_path / "console_offset.json"
    offset_path.write_text(json.dumps({"offset": 100}), encoding="utf-8")
    poller, handled, seen = _poller(
        [[_msg_update(100, "hur går det?"), _msg_update(101, "/status")]], offset_path
    )

    n = poller.poll_once()
    assert n == 2
    assert handled == ["hur går det?", "/status"]
    assert seen == [100]  # fetched with the persisted offset
    assert json.loads(offset_path.read_text())["offset"] == 102  # advanced past the last update


def test_dropped_updates_still_advance_the_offset(tmp_path: Path) -> None:
    offset_path = tmp_path / "console_offset.json"
    offset_path.write_text(json.dumps({"offset": 200}), encoding="utf-8")
    # a foreign chat_id update (dropped by authz) must still be acknowledged (offset advances).
    foreign = {"update_id": 200, "message": {"chat": {"id": 999, "type": "private"}, "text": "x"}}
    poller, handled, _ = _poller([[foreign, _msg_update(201, "hej")]], offset_path)

    poller.poll_once()
    assert handled == ["hej"]  # only the operator message handled
    assert json.loads(offset_path.read_text())["offset"] == 202


def test_a_handler_exception_advances_offset_and_does_not_wedge(tmp_path: Path) -> None:
    offset_path = tmp_path / "console_offset.json"
    offset_path.write_text(json.dumps({"offset": 300}), encoding="utf-8")

    def fetch(offset: int | None) -> list[dict[str, object]]:
        return [_msg_update(300, "boom"), _msg_update(301, "ok")]

    def handle(msg: InboundMessage) -> None:
        if msg.text == "boom":
            raise RuntimeError("handler blew up")

    poller = ConsolePoller(
        fetch_updates=fetch, handle=handle, offset_path=offset_path, operator_chat_id=_OP
    )
    poller.poll_once()  # must not raise
    assert json.loads(offset_path.read_text())["offset"] == 302  # advanced past BOTH


def test_corrupt_offset_file_is_treated_as_cold_start(tmp_path: Path) -> None:
    # A well-formed-but-non-dict offset file must fail closed to a cold start (seed + discard).
    offset_path = tmp_path / "console_offset.json"
    offset_path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")  # valid JSON, but a list
    poller, handled, seen = _poller([[_msg_update(500, "/flatta")]], offset_path)
    n = poller.poll_once()
    assert n == 0 and handled == []  # cold start: nothing handled
    assert seen == [None]  # fetched with offset=None (cold start)
    assert json.loads(offset_path.read_text())["offset"] == 501  # seeded past the backlog


def test_cold_start_with_no_pending_updates_does_not_seed(tmp_path: Path) -> None:
    # Cold start with an empty backlog leaves the offset unseeded (re-checks next cycle); no crash.
    offset_path = tmp_path / "console_offset.json"
    poller, handled, seen = _poller([[]], offset_path)
    assert poller.poll_once() == 0
    assert handled == [] and seen == [None]
    assert not offset_path.exists()  # nothing to seed from yet


def test_malformed_update_without_id_is_skipped(tmp_path: Path) -> None:
    offset_path = tmp_path / "console_offset.json"
    offset_path.write_text(json.dumps({"offset": 400}), encoding="utf-8")
    poller, handled, _ = _poller([[{"message": {}}, _msg_update(400, "hej")]], offset_path)
    poller.poll_once()
    assert handled == ["hej"]
    assert json.loads(offset_path.read_text())["offset"] == 401
