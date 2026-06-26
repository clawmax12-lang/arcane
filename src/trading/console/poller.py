"""The console getUpdates long-poll + DURABLE OFFSET + cold-start backlog discard (Inc-8 PART B).

``poll_once`` runs ONE poll cycle (so it is deterministically testable; a live loop calls it
repeatedly). It acknowledges updates by advancing a durably-persisted offset (atomic
temp->fsync->os.replace, mirroring ``kill_switch._write``). On a COLD start (no offset file) it
seeds the offset to the current max ``update_id`` and DISCARDS the backlog — so a stale ``/flatta``
cannot replay out of context after the operator re-armed. Each update is handled under try/except +
always advances the offset, so one malformed or exploding update cannot wedge the loop; a re-run of
a kill_switch escalation is a harmless no-op (monotonic), so advancing the offset after handling
never double-fires or loses a control.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import structlog

from trading.console.authz import InboundMessage, extract_authorized

_log = structlog.get_logger(__name__)

DEFAULT_OFFSET_PATH = Path("state/console_offset.json")

#: ``offset -> raw updates`` (None offset = cold-start fetch of everything pending).
UpdatesFetcher = Callable[[int | None], list[dict[str, object]]]
MessageHandler = Callable[[InboundMessage], None]


def _update_id_key(update: dict[str, object]) -> int:
    uid = update.get("update_id")
    return uid if isinstance(uid, int) else -1


@dataclass(frozen=True, slots=True)
class ConsolePoller:
    fetch_updates: UpdatesFetcher
    handle: MessageHandler
    offset_path: Path
    operator_chat_id: str

    def _load_offset(self) -> int | None:
        try:
            raw = json.loads(self.offset_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, ValueError):
            return None
        if not isinstance(raw, dict):
            return None
        offset = raw.get("offset")
        return offset if isinstance(offset, int) else None

    def _save_offset(self, offset: int) -> None:
        self.offset_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.offset_path.parent / (self.offset_path.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"offset": offset}, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.offset_path)

    def poll_once(self) -> int:
        """Run one poll cycle; return the number of operator messages handled."""
        offset = self._load_offset()
        if offset is None:
            # COLD start: seed past the current max and DISCARD the backlog (no stale replay).
            updates = self.fetch_updates(None)
            uids = [u for u in (_update_id_key(u) for u in updates) if u >= 0]
            if uids:
                self._save_offset(max(uids) + 1)
                _log.info("console_cold_start_backlog_skipped", discarded=len(uids))
            return 0

        updates = self.fetch_updates(offset)
        handled = 0
        for update in sorted(updates, key=_update_id_key):
            uid = update.get("update_id")
            if not isinstance(uid, int):
                continue
            try:
                message = extract_authorized(update, self.operator_chat_id)
                if message is not None:
                    self.handle(message)
                    handled += 1
            except Exception:  # one bad update must never wedge the loop
                _log.warning("console_update_handler_failed", update_id=uid)
            self._save_offset(uid + 1)  # acknowledge regardless (idempotent controls)
        return handled
