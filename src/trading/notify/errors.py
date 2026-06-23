"""Typed, fail-closed exceptions for the notifier (root: ``ArcaneError``)."""

from __future__ import annotations

from trading.risk.errors import ArcaneError


class NotifierError(ArcaneError):
    """A notification could not be delivered (transport/protocol failure)."""


class NotifierMisconfiguredError(NotifierError):
    """The notifier cannot be constructed — missing token or no resolvable chat_id (fail-closed)."""
