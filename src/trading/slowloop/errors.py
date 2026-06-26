"""Typed, fail-closed exceptions for the slow-loop agent framework (root: ``ArcaneError``)."""

from __future__ import annotations

from trading.risk.errors import ArcaneError


class SlowLoopError(ArcaneError):
    """Base for any slow-loop agent / orchestrator / store failure."""


class AgentValidationError(SlowLoopError):
    """An agent produced output failing the artifact schema (discarded; last-known-good kept)."""


class LLMTransportError(SlowLoopError):
    """The LLM call could not be completed (transport/protocol failure) — token-free message."""
