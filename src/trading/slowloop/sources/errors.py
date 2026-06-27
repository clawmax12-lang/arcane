"""Typed, fail-closed errors for the real vendor adapters (root: ``SlowLoopError``).

Mirrors ``data/errors.py``: every vendor failure is a specific, catchable exception, and the default
on ANY uncertainty is to RAISE (fail closed) rather than return a partial / fabricated set. The
message carries only the exception TYPE / status — never the token, never the vendor's raw body.
"""

from __future__ import annotations

from trading.slowloop.errors import SlowLoopError


class NewsSourceError(SlowLoopError):
    """A news vendor fetch failed (429/timeout/non-200/malformed) — abort, never a partial set."""


class MacroSourceError(SlowLoopError):
    """A macro vendor (FRED) fetch failed — fail closed; the agent discards, last-good is kept."""
