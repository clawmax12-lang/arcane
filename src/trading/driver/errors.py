"""Driver errors — rooted at the shared ``ArcaneError`` (Increment 7 PART C)."""

from __future__ import annotations

from trading.risk.errors import ArcaneError


class DriverError(ArcaneError):
    """A driver-assembly failure (oversized family, etc.) — fail-closed to ZERO candidates."""
