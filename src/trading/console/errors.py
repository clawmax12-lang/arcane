"""Typed, fail-closed exceptions for the operator console (root: ``ArcaneError``)."""

from __future__ import annotations

from trading.risk.errors import ArcaneError


class ConsoleError(ArcaneError):
    """A console transport/protocol failure (e.g. a getUpdates call failed) — token-free message."""
