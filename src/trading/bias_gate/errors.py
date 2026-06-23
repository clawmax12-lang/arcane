"""Typed, fail-closed exceptions for the bias gate (root: ``ArcaneError``).

Mirrors the Inc-1..4 taxonomy idiom (``risk.errors.ArcaneError`` → package-local roots): every
gate fault is a *raise*, never a silent permissive default, so a degenerate/corrupt input can never
slip through as an implicit accept.
"""

from __future__ import annotations

from trading.risk.errors import ArcaneError


class BiasGateError(ArcaneError):
    """Base class for every bias-gate error (fail-closed)."""


class HighWaterMarkError(BiasGateError):
    """The n_trials high-water-mark regressed or its store is unreadable (M18 deflation tamper)."""


class PurgeUnderspecifiedError(BiasGateError):
    """A walk-forward purge is below the re-derived ``max_total_window + label_horizon`` floor."""


class EvidenceConsistencyError(BiasGateError):
    """The gate's recomputed OOS series diverged from the sealed ``BacktestResult`` (T1 guard)."""
