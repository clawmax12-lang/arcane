"""Kill switch — persisted, atomic, monotonic-toward-safety state machine.

States escalate ``ARMED -> TRIPPED -> HARD_STOPPED`` and never de-escalate automatically.
Only an explicit operator action (``arm(operator_authority=True)``, wired to an
interactive CLI) may lower severity; agents/LLMs cannot re-arm (§7).

Persistence is crash-safe: writes go to a temp file, are ``fsync``'d, then atomically
``os.replace``d into place. Two fail-safe properties (hardened after red-team findings):
  * A genuinely missing file is a fresh ``ARMED`` start, but a dangling symlink or any
    other unreadable/corrupt state fails SAFE to ``TRIPPED`` (finding #5).
  * Each instance keeps an in-memory severity LATCH set *before* the disk write, so if a
    write fails (read-only dir, disk full) the escalation still takes effect in-process
    and ``read()`` reports the escalated state rather than the stale permissive file (#6).
"""

from __future__ import annotations

import contextlib
import json
import os
from enum import StrEnum
from pathlib import Path

from trading.risk.errors import ArcaneError


class KillSwitchState(StrEnum):
    ARMED = "ARMED"
    TRIPPED = "TRIPPED"
    HARD_STOPPED = "HARD_STOPPED"


_SEVERITY: dict[KillSwitchState, int] = {
    KillSwitchState.ARMED: 0,
    KillSwitchState.TRIPPED: 1,
    KillSwitchState.HARD_STOPPED: 2,
}

DEFAULT_KILL_SWITCH_PATH = Path("state/kill_switch.json")
_TOMBSTONE_NAME = "HARD_STOP.tombstone"


class KillSwitchAuthorityError(ArcaneError):
    """Raised when a non-operator caller attempts to re-arm the kill switch."""


class KillSwitchUnwritableError(ArcaneError):
    """Raised at startup when the kill-switch state store is not writable."""


class KillSwitch:
    """File-backed kill switch. Construct with a path; safe across process restarts.

    An in-memory latch keeps a single instance fail-closed even if the disk write fails;
    the latch is reset only by an operator re-arm.
    """

    def __init__(self, path: Path = DEFAULT_KILL_SWITCH_PATH) -> None:
        self._path = path
        self._latch: KillSwitchState = KillSwitchState.ARMED

    def read(self) -> KillSwitchState:
        persisted, _ = self._load()
        # Effective state = the MOST severe of the persisted file and the in-memory latch.
        return persisted if _SEVERITY[persisted] >= _SEVERITY[self._latch] else self._latch

    def reason(self) -> str:
        return self._load()[1]

    def allows_new_orders(self) -> bool:
        """New orders are permitted only in the ARMED state."""
        return self.read() is KillSwitchState.ARMED

    def trip(self, reason: str) -> KillSwitchState:
        """Escalate to TRIPPED (no new orders; existing positions may be managed)."""
        return self._escalate(KillSwitchState.TRIPPED, reason)

    def hard_stop(self, reason: str) -> KillSwitchState:
        """Escalate to HARD_STOPPED (terminal) AND lay down a durable tombstone (GRD-4).

        The tombstone makes a latched HARD_STOP survive deletion of the json state file alone (the
        realistic single-file attack: an editor, a partial cleanup script, a targeted ``unlink``):
        on a fresh process a MISSING json + a PRESENT tombstone reads HARD_STOPPED. The json is
        written FIRST (existing ``_escalate``) so a crash before the tombstone still reads
        HARD_STOPPED off the json; the tombstone is written second and idempotently (re-written on
        every call so it exists whenever the effective state is HARD_STOPPED). A whole-dir
        ``rm -rf state/`` wipe is OUT of scope (operator/Murphy territory — indistinguishable from a
        first-ever boot; same class as the ledger-deletion residual).
        """
        result = self._escalate(KillSwitchState.HARD_STOPPED, reason)
        self._write_tombstone(reason)  # durable terminal marker (json was written first)
        return result

    def arm(self, *, operator_authority: bool, reason: str = "operator re-arm") -> KillSwitchState:
        """Re-arm — operator-only. Raises if called without explicit operator authority.

        Writes the ARMED json FIRST, THEN clears the tombstone: a present, validly-ARMED json WINS
        over a stale tombstone (``_load`` never consults the tombstone when the json is readable),
        so a crash between the two non-atomic ops cannot let a stale tombstone silently override the
        re-arm. The tombstone removal is best-effort (a residual stale tombstone is benign — it only
        matters if the json is LATER deleted, where HARD_STOPPED is the conservative-safe answer).
        """
        if not operator_authority:
            raise KillSwitchAuthorityError(
                "kill switch can only be re-armed by explicit operator authority (§7)"
            )
        self._write(KillSwitchState.ARMED, reason)  # may raise -> operator retries
        self._remove_tombstone()  # clear the terminal tombstone AFTER the durable ARMED write
        self._latch = KillSwitchState.ARMED  # clear the latch only after a durable write
        return KillSwitchState.ARMED

    def verify_writable(self) -> None:
        """Raise ``KillSwitchUnwritableError`` if the state store can't be written.

        Call at startup and refuse to trade if it raises — a kill switch we cannot
        escalate to disk is not a kill switch.
        """
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            probe = self._path.parent / (self._path.name + ".probe")
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
        except OSError as exc:
            raise KillSwitchUnwritableError(
                f"kill-switch state store not writable at {self._path}: {exc}"
            ) from exc

    # --- internals ---

    def _escalate(self, target: KillSwitchState, reason: str) -> KillSwitchState:
        current = self.read()
        if _SEVERITY[current] >= _SEVERITY[target]:
            return current  # monotonic: never de-escalate automatically
        # Latch in memory BEFORE the write so a write failure still escalates this process.
        if _SEVERITY[target] > _SEVERITY[self._latch]:
            self._latch = target
        self._write(target, reason)  # may raise; the latch already protects us
        return target

    def _write(self, state: KillSwitchState, reason: str) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.parent / (self._path.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"state": state.value, "reason": reason}, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self._path)

    def _tombstone_path(self) -> Path:
        return self._path.parent / _TOMBSTONE_NAME

    def _write_tombstone(self, reason: str) -> None:
        """Atomically lay down the durable HARD_STOP tombstone (temp -> fsync -> os.replace)."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tomb = self._tombstone_path()
        tmp = tomb.parent / (tomb.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"state": KillSwitchState.HARD_STOPPED.value, "reason": reason}, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, tomb)

    def _remove_tombstone(self) -> None:
        """Best-effort tombstone removal (a residual stale tombstone fails safe to HARD_STOPPED)."""
        with contextlib.suppress(OSError):
            self._tombstone_path().unlink(missing_ok=True)

    def _load(self) -> tuple[KillSwitchState, str]:
        try:
            text = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            # A latched HARD_STOP is durable across deletion of the json ALONE: a present tombstone
            # with a missing json fails SAFE to HARD_STOPPED (GRD-4 single-file close). A present,
            # valid ARMED json never reaches here (it short-circuits above), so a re-arm WINS over a
            # stale tombstone. Whole-dir ``rm -rf state/`` removes the tombstone too -> fresh ARMED
            # (the documented operator/Murphy residual).
            if self._tombstone_path().exists():
                return KillSwitchState.HARD_STOPPED, "hard-stop-tombstone-failsafe"
            # A genuine fresh start requires the path itself NOT to be a (dangling) symlink
            # AND the parent to resolve to a real directory. is_symlink() only inspects the
            # final component, so a dangling PARENT-component symlink is caught by
            # parent.is_dir() (which follows links) returning False -> fail safe to TRIPPED.
            if self._path.is_symlink() or not self._path.parent.is_dir():
                return KillSwitchState.TRIPPED, "unresolvable-path-failsafe"
            return KillSwitchState.ARMED, "initial"
        except OSError:
            return KillSwitchState.TRIPPED, "unreadable-state-failsafe"
        try:
            raw = json.loads(text)
            state = KillSwitchState(raw["state"])
            return state, str(raw.get("reason", ""))
        except (ValueError, KeyError, TypeError):
            return KillSwitchState.TRIPPED, "corrupt-state-failsafe"
