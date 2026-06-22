"""The monotonic, append-only TRIAL LEDGER — the ADR §5 / M18 overfit defense.

``n_trials`` is the cumulative count of every DISTINCT ``(kind, ref_id, params)`` factor/param combo
EVER evaluated across the project lifetime — the Deflated-Sharpe / Reality-Check search-breadth
deflation input (ADR-001 §5). **Under-counting deflates the overfit penalty and is the exact M18
fail-open vector the ledger exists to defend**, so the read path is fail-CLOSED: a corrupt or
unreadable DB RAISES — it never silently reports ``0`` or a lower count.

Store = **SQLite**, mirroring ``executor/idempotency.py`` ``SqliteIdempotencyStore`` (ADR-001 §3
names the ledger under the SQLite stdlib fail-closed restart-safe store): a ``PRIMARY KEY`` +
``INSERT OR IGNORE`` makes ``record`` idempotent at-most-once and the count structurally
monotonic-toward-more. There is **no** delete/update/clear/remove API on the type — the count can
only grow or no-op. ``combo_hash`` is a SHA-256 over canonical JSON (the same idiom as
``data.cache.cache_key`` / ``executor.idempotency.client_order_id``) with **no** ``default=str``
coercion: an un-encodable param is rejected rather than collided into an existing combo.

Documented residual (DEFER to the Inc-4/5 param-sweep increment): a factor *formula rewrite* that
keeps the same ``id``+params is not counted as a new trial (a ``inspect.getsource`` fingerprint was
rejected — it makes ``n_trials`` fragile to cosmetic/formatter edits); and raw deletion of the DB
file recreates a fresh 0-trial ledger (filesystem tampering, the same posture as
``kill_switch.json`` — a persisted high-water-mark is deferred, not built).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

from trading.factors.errors import TrialLedgerError

_T = TypeVar("_T")

_PRAGMA_DURABLE = "PRAGMA synchronous=FULL"
_CREATE = (
    "CREATE TABLE IF NOT EXISTS trials ("
    "combo_hash TEXT PRIMARY KEY, kind TEXT NOT NULL, ref_id TEXT NOT NULL, "
    "params_json TEXT NOT NULL, created REAL NOT NULL)"
)


@dataclass(frozen=True, slots=True)
class TrialRecord:
    """One recorded trial (a factor/param hypothesis that has entered the search)."""

    combo_hash: str
    kind: str
    ref_id: str
    params: Mapping[str, Any]
    created: float


def _canonical(kind: str, ref_id: str, params: Mapping[str, Any]) -> tuple[str, str]:
    """Return ``(combo_hash, params_json)``; un-encodable params raise (no ``default=str``)."""
    try:
        params_json = json.dumps(params, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise TrialLedgerError(f"trial params are not JSON-encodable: {exc!r}") from exc
    payload = json.dumps(
        {"kind": kind, "ref_id": ref_id, "params": params},
        sort_keys=True,
        separators=(",", ":"),
    )
    combo_hash = "arcane-trial-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:40]
    return combo_hash, params_json


class TrialLedger:
    """Append-only, monotonic, fail-closed SQLite ledger of evaluated factor/param combos."""

    def __init__(self, path: Path | str, *, clock: Callable[[], float] = time.time) -> None:
        self._path = Path(path)
        self._clock = clock
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._exec(lambda conn: conn.execute(_CREATE))

    def _exec(self, body: Callable[[sqlite3.Connection], _T]) -> _T:
        """Run ``body`` in one durable txn; a DB fault is a fail-closed TrialLedgerError."""
        try:
            conn = sqlite3.connect(self._path)
        except sqlite3.Error as exc:  # pragma: no cover - connect rarely fails after mkdir
            raise TrialLedgerError(f"cannot open trial ledger {self._path}: {exc!r}") from exc
        try:
            conn.execute(_PRAGMA_DURABLE)
            with conn:
                return body(conn)
        except sqlite3.DatabaseError as exc:
            # A corrupt/clobbered DB MUST fail closed — never let a read report 0 / a lower count.
            raise TrialLedgerError(
                f"trial ledger {self._path} is unreadable/corrupt: {exc!r}"
            ) from exc
        finally:
            conn.close()

    def record(self, kind: str, ref_id: str, params: Mapping[str, Any]) -> TrialRecord:
        """Idempotently record one (kind, ref_id, params) combo; re-recording is a no-op."""
        combo_hash, params_json = _canonical(kind, ref_id, params)
        created = float(self._clock())

        def _body(conn: sqlite3.Connection) -> TrialRecord:
            conn.execute(
                "INSERT OR IGNORE INTO trials (combo_hash, kind, ref_id, params_json, created) "
                "VALUES (?, ?, ?, ?, ?)",
                (combo_hash, kind, ref_id, params_json, created),
            )
            row = conn.execute(
                "SELECT combo_hash, kind, ref_id, params_json, created FROM trials "
                "WHERE combo_hash = ?",
                (combo_hash,),
            ).fetchone()
            if row is None:  # pragma: no cover - defensive (record() always passes non-null values)
                # INSERT OR IGNORE swallows a NOT-NULL violation as well as a PK conflict; if the
                # row is then absent the combo was NOT counted -> fail closed (an under-count is the
                # M18 vector), not a bare TypeError from the missing row (red-team ledger-1).
                raise TrialLedgerError(
                    f"trial {combo_hash} absent after INSERT OR IGNORE (a swallowed constraint?)"
                )
            return _row_to_record(row)

        return self._exec(_body)

    def n_trials(self) -> int:
        """Count of DISTINCT recorded combos — the DSR/M18 deflation input (fail-closed)."""
        row = self._exec(lambda conn: conn.execute("SELECT COUNT(*) FROM trials").fetchone())
        return int(row[0])

    def trials(self) -> tuple[TrialRecord, ...]:
        """Every recorded trial, oldest first (read-only)."""

        def _body(conn: sqlite3.Connection) -> tuple[TrialRecord, ...]:
            rows = conn.execute(
                "SELECT combo_hash, kind, ref_id, params_json, created FROM trials "
                "ORDER BY created, combo_hash"
            ).fetchall()
            return tuple(_row_to_record(r) for r in rows)

        return self._exec(_body)


def _row_to_record(row: tuple[str, str, str, str, float]) -> TrialRecord:
    combo_hash, kind, ref_id, params_json, created = row
    try:
        params = json.loads(params_json)
    except json.JSONDecodeError as exc:  # a tampered params_json is a fail-closed corruption
        raise TrialLedgerError(f"trial {combo_hash} has corrupt params_json: {exc!r}") from exc
    return TrialRecord(
        combo_hash=combo_hash, kind=kind, ref_id=ref_id, params=params, created=float(created)
    )
