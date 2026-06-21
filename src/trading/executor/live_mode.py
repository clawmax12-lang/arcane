"""LIVE_MODE triple-lock gate (PHI1 / CLAUDE.md §7).

Live trading requires THREE independent locks to ALL be open:

  1. code lock   — ``LIVE_MODE_CODE_DEFAULT`` must be flipped to ``True`` in source
                   (grep-able; a deliberate code change, not a config toggle).
  2. config lock — ``risk.yaml`` ``live_mode: true``.
  3. CLI lock    — an operator-created confirmation marker file written by a two-step
                   CLI (``scripts/toggle_live_mode.py``), containing an exact phrase.

``is_live()`` returns True ONLY for (True, True, True). All 7 other combinations resolve
to paper. The posture is fail-safe: any error reading the marker resolves to paper. The
Alpaca client additionally hardcodes ``paper=True`` in the submit path regardless of this
gate — so even a bug here cannot place a real order.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from trading.risk import constants as C

#: Default location of the operator confirmation marker (under gitignored ``state/``).
LIVE_MARKER_PATH = Path("state/LIVE_MODE_CONFIRMED")

#: The exact phrase the marker must contain for the CLI lock to count as open.
LIVE_CONFIRM_PHRASE = "I_UNDERSTAND_THIS_IS_REAL_MONEY"


@dataclass(frozen=True, slots=True)
class LiveModeStatus:
    """Snapshot of the three locks. Live only when all three are open."""

    code_lock: bool
    config_lock: bool
    cli_lock: bool

    @property
    def is_live(self) -> bool:
        return self.code_lock and self.config_lock and self.cli_lock


def code_lock_open() -> bool:
    """True only if the source-level default has been deliberately flipped to True."""
    return C.LIVE_MODE_CODE_DEFAULT is True


def cli_lock_open(marker_path: Path = LIVE_MARKER_PATH) -> bool:
    """True only if the operator marker exists and contains the exact confirm phrase."""
    try:
        if not marker_path.is_file():
            return False
        return marker_path.read_text(encoding="utf-8").strip() == LIVE_CONFIRM_PHRASE
    except OSError:
        return False


def evaluate_live_mode(
    config_live_mode: bool, marker_path: Path = LIVE_MARKER_PATH
) -> LiveModeStatus:
    return LiveModeStatus(
        code_lock=code_lock_open(),
        config_lock=bool(config_live_mode),
        cli_lock=cli_lock_open(marker_path),
    )


def is_live(config_live_mode: bool, marker_path: Path = LIVE_MARKER_PATH) -> bool:
    return evaluate_live_mode(config_live_mode, marker_path).is_live


def assert_paper_for_handoff(config_live_mode: bool) -> None:
    """Handoff/CI invariant: BOTH the code default and config must be paper.

    Raises ``AssertionError`` if either flag is flipped — this is wired into the
    Increment-1 gate so CI fails if a future edit arms live trading.
    """
    if C.LIVE_MODE_CODE_DEFAULT is not False:
        raise AssertionError("LIVE_MODE_CODE_DEFAULT must be False at handoff")
    if config_live_mode is not False:
        raise AssertionError("config live_mode must be false at handoff")
