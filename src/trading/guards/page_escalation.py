"""§5.2 operator paging-latency escalation ladder (Increment 6 PART B).

A disaster RED page is issued IMMEDIATELY by ``apply_guards`` (the protective hard_stop/auto-flat
already happened at t=0). This ladder is the NOTIFICATION escalation on top: if the operator
does not
acknowledge within 15 / 30 / 60 minutes it resends, and at 60 minutes it performs the terminal
auto-liquidate + hard_stop (§5.2). It runs on an INDEPENDENT watchdog cadence, NOT the trading
scheduler, so a wedged scheduler cannot prevent the terminal action.

State is disk-persisted (``opened_epoch``), so a crash at minute 40 still liquidates at minute 60.
ACK is an operator-written marker (a future Telegram callback writes the same marker without
changing
``tick``). The clock is injected so the ladder is deterministic in tests.
"""

from __future__ import annotations

import contextlib
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from trading.notify.telegram import Severity

_RESEND_15_S = 900.0
_RESEND_30_S = 1800.0
_TERMINAL_60_S = 3600.0


class EscalationAction(StrEnum):
    NONE = "NONE"
    RESEND_15 = "RESEND_15"
    RESEND_30 = "RESEND_30"
    TERMINAL_LIQUIDATE = "TERMINAL_LIQUIDATE"


class _Halter(Protocol):
    def hard_stop(self, reason: str) -> object: ...


class _Pager(Protocol):
    def page_operator(self, severity: Severity, text: str) -> None: ...


@dataclass(frozen=True, slots=True)
class PageState:
    page_id: str
    opened_epoch: float


class PageEscalation:
    """Disk-persisted, clock-injected escalation state machine for ONE open operator page."""

    def __init__(self, state_path: Path, *, ack_path: Path | None = None) -> None:
        self._path = state_path
        self._ack = ack_path or state_path.parent / "PAGE_ACK"

    def open_page(self, page_id: str, *, opened_epoch: float) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_write(
            self._path, json.dumps({"page_id": page_id, "opened_epoch": opened_epoch})
        )

    def acknowledge(self, page_id: str) -> None:
        self._ack.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_write(self._ack, page_id)

    def resolve(self) -> None:
        self._path.unlink(missing_ok=True)
        self._ack.unlink(missing_ok=True)

    def tick(self, now_epoch: float) -> EscalationAction:
        state = self._load()
        if state is None:
            return EscalationAction.NONE
        if self._is_acked(state.page_id):
            return EscalationAction.NONE
        elapsed = now_epoch - state.opened_epoch
        if elapsed >= _TERMINAL_60_S:
            return EscalationAction.TERMINAL_LIQUIDATE
        if elapsed >= _RESEND_30_S:
            return EscalationAction.RESEND_30
        if elapsed >= _RESEND_15_S:
            return EscalationAction.RESEND_15
        return EscalationAction.NONE

    # --- internals ---

    def _load(self) -> PageState | None:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            return PageState(page_id=str(raw["page_id"]), opened_epoch=float(raw["opened_epoch"]))
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def _is_acked(self, page_id: str) -> bool:
        try:
            return self._ack.read_text(encoding="utf-8").strip() == page_id
        except OSError:
            return False

    @staticmethod
    def _atomic_write(path: Path, text: str) -> None:
        tmp = path.parent / (path.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)


def apply_escalation(
    action: EscalationAction,
    kill_switch: _Halter,
    notifier: _Pager,
    *,
    broker_flat_fn: Callable[[], None],
) -> None:
    """Carry out an escalation action. TERMINAL does ALL THREE: flat-all + hard_stop + final
    RED page."""
    if action is EscalationAction.NONE:
        return
    if action is EscalationAction.RESEND_15:
        _try_page(notifier, Severity.ORANGE, "[NO ACK 15m] disaster page unacknowledged")
        return
    if action is EscalationAction.RESEND_30:
        _try_page(
            notifier, Severity.ORANGE, "[NO ACK 30m — would call] disaster page unacknowledged"
        )
        return
    # TERMINAL_LIQUIDATE — protective action FIRST, then the final page (best-effort).
    broker_flat_fn()
    kill_switch.hard_stop("§5.2 60-min no-ack auto-liquidate")
    _try_page(notifier, Severity.RED, "[60m NO ACK] auto-liquidated + HARD_STOPPED")


def _try_page(notifier: _Pager, severity: Severity, text: str) -> None:
    # escalation must never crash on a transport failure
    with contextlib.suppress(Exception):
        notifier.page_operator(severity, text)
