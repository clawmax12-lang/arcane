"""Tripwire A2 — the n_trials high-water-mark (a monotonic floor DB deletion cannot reset).

``TrialLedger`` fails closed on a CORRUPT db but NOT a MISSING one: raw deletion of the ``.db``
recreates a fresh 0-trial ledger, silently resetting the DSR deflation input to 0 — the M18 vector.
This persistent high-water-mark records ``max(n_trials ever seen)`` and RAISES if a live count ever
falls below it. The store write is crash-safe (temp, ``fsync``, ``os.replace`` — the ``kill_switch``
idiom) and the mark only RISES (no fsync churn on a flat/repeated read).

RESIDUAL (documented, NOT silently dropped): the mark lives in the gitignored ``state/`` zone, so
deleting BOTH the ledger ``.db`` AND this json resets to a believable fresh start. For a paper-only
experiment that simultaneous-deletion case is escalated to Murphy-guard/operator territory, not
defended with a committed floor.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Final

from trading.bias_gate.errors import HighWaterMarkError

DEFAULT_HWM_PATH: Final[Path] = Path("state/n_trials_high_water_mark.json")
_KEY: Final[str] = "n_trials_high_water_mark"


class NTrialsHighWaterMark:
    """A persistent, monotonic n_trials floor; ``checked_n_trials`` fails closed on a regression."""

    def __init__(self, path: Path = DEFAULT_HWM_PATH) -> None:
        self._path = path

    def verify_writable(self) -> None:
        """Raise ``HighWaterMarkError`` if the mark store cannot be written (call at startup)."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            probe = self._path.parent / (self._path.name + ".probe")
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
        except OSError as exc:
            raise HighWaterMarkError(
                f"n_trials high-water-mark store not writable at {self._path}: {exc}"
            ) from exc

    def checked_n_trials(self, live_count: int) -> int:
        """Return ``live_count`` if >= the persisted mark; else RAISE (a deflation regression).

        Rejects a non-``int`` / ``bool`` / negative ``live_count`` (fail closed — a bad count must
        never deflate the gate). On a strictly greater count the mark RISES (atomic write).
        """
        if isinstance(live_count, bool) or not isinstance(live_count, int) or live_count < 0:
            raise HighWaterMarkError(f"live_count must be a non-negative int, got {live_count!r}")
        mark = self._read_mark()
        if live_count < mark:
            raise HighWaterMarkError(
                f"n_trials regressed: live count {live_count} < high-water-mark {mark} "
                "(ledger deleted/tampered/rolled back) — fail closed (M18)"
            )
        if live_count > mark:
            self._write_mark(live_count)
        return live_count

    def _read_mark(self) -> int:
        """Read the persisted mark; a missing file is 0, anything unreadable/malformed RAISES."""
        try:
            text = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            # A genuine fresh start requires the path NOT to be a (dangling) symlink AND the parent
            # to resolve to a real dir (mirrors kill_switch._load) — else fail closed.
            if self._path.is_symlink() or not self._path.parent.is_dir():
                raise HighWaterMarkError(
                    f"high-water-mark path unresolvable: {self._path}"
                ) from None
            return 0
        except OSError as exc:
            raise HighWaterMarkError(
                f"high-water-mark store unreadable at {self._path}: {exc}"
            ) from exc
        try:
            raw = json.loads(text)
            mark = raw[_KEY]
        except (ValueError, KeyError, TypeError) as exc:
            raise HighWaterMarkError(
                f"high-water-mark store corrupt at {self._path}: {exc!r}"
            ) from exc
        if isinstance(mark, bool) or not isinstance(mark, int) or mark < 0:
            raise HighWaterMarkError(f"high-water-mark must be a non-negative int, got {mark!r}")
        return mark

    def _write_mark(self, value: int) -> None:
        """Atomically persist the mark (temp → fsync → os.replace; the kill_switch idiom)."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.parent / (self._path.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({_KEY: value}, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self._path)
