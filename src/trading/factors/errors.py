"""Typed, fail-closed error taxonomy for the factor layer (all ``ArcaneError`` subclasses).

Factors are a SIBLING layer to the data spine (they CONSUME bar frames), so ``FactorError`` roots
at ``trading.risk.errors.ArcaneError`` — the SAME root as ``data.errors.DataError`` — and NOT under
``DataError``, so a factor fault is never mis-bucketed by an ``except DataError`` handler. Mirrors
the data-layer idiom: every failure is a specific, catchable exception; the default on any
uncertainty is to RAISE (fail closed) rather than return a partial/fabricated signal.
"""

from __future__ import annotations

from trading.risk.errors import ArcaneError


class FactorError(ArcaneError):
    """Base class for all factor-layer errors."""


class FactorContractError(FactorError):
    """A factor violated the ``AlphaFactor`` contract (bad input frame, a ``_raw`` output that is
    not a row-aligned finite-or-NaN Series, or a broken output shape)."""


class DuplicateFactorError(FactorError):
    """Two factors share an ``id`` in one registry (ids must be unique)."""


class FrameAdequacyError(FactorError):
    """A prefix-stability sample panel is empty or too short to exercise the look-ahead property
    non-vacuously (a too-short frame is a false-green; fail closed)."""


class TrialLedgerError(FactorError):
    """The append-only trial ledger is missing/unreadable/corrupt, or an un-encodable trial was
    recorded — never silently report a lower count (under-counting is the M18 overfit vector)."""
