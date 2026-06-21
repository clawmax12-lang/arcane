"""Kill switch — persisted, atomic, monotonic-toward-safety state machine.

States escalate ``ARMED -> TRIPPED -> HARD_STOPPED`` and never de-escalate
automatically. Only an explicit operator action (``arm(operator_authority=True)``,
wired to an interactive CLI) may lower severity; agents/LLMs cannot re-arm (§7).

Persistence is crash-safe: writes go to a temp file, are ``fsync``'d, then atomically
``os.replace``d into place, so a crash mid-write can never leave a half-written state.
On read, a missing file is a fresh ``ARMED`` start; an unreadable/corrupt file fails
SAFE to ``TRIPPED``.
"""

from __future__ import annotations

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


class KillSwitchAuthorityError(ArcaneError):
    """Raised when a non-operator caller attempts to re-arm the kill switch."""


class KillSwitch:
    """File-backed kill switch. Construct with a path; safe across process restarts."""

    def __init__(self, path: Path = DEFAULT_KILL_SWITCH_PATH) -> None:
        self._path = path

    def read(self) -> KillSwitchState:
        return self._load()[0]

    def reason(self) -> str:
        return self._load()[1]

    def allows_new_orders(self) -> bool:
        """New orders are permitted only in the ARMED state."""
        return self.read() is KillSwitchState.ARMED

    def trip(self, reason: str) -> KillSwitchState:
        """Escalate to TRIPPED (no new orders; existing positions may be managed)."""
        return self._escalate(KillSwitchState.TRIPPED, reason)

    def hard_stop(self, reason: str) -> KillSwitchState:
        """Escalate to HARD_STOPPED (terminal; e.g. abandonment or red-guard auto-flat)."""
        return self._escalate(KillSwitchState.HARD_STOPPED, reason)

    def arm(self, *, operator_authority: bool, reason: str = "operator re-arm") -> KillSwitchState:
        """Re-arm — operator-only. Raises if called without explicit operator authority."""
        if not operator_authority:
            raise KillSwitchAuthorityError(
                "kill switch can only be re-armed by explicit operator authority (§7)"
            )
        self._write(KillSwitchState.ARMED, reason)
        return KillSwitchState.ARMED

    # --- internals ---

    def _escalate(self, target: KillSwitchState, reason: str) -> KillSwitchState:
        current = self.read()
        if _SEVERITY[current] >= _SEVERITY[target]:
            return current  # monotonic: never de-escalate automatically
        self._write(target, reason)
        return target

    def _write(self, state: KillSwitchState, reason: str) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.parent / (self._path.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"state": state.value, "reason": reason}, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self._path)

    def _load(self) -> tuple[KillSwitchState, str]:
        if not self._path.exists():
            return KillSwitchState.ARMED, "initial"
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            state = KillSwitchState(raw["state"])
            return state, str(raw.get("reason", ""))
        except (OSError, ValueError, KeyError, TypeError):
            return KillSwitchState.TRIPPED, "corrupt-or-unreadable-state-failsafe"
