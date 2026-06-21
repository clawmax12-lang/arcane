"""Typed exceptions for the ARCANE safety core."""

from __future__ import annotations


class ArcaneError(Exception):
    """Base class for all ARCANE errors."""


class RiskConfigError(ArcaneError):
    """Raised when risk configuration cannot be loaded or is invalid (fail-closed)."""
