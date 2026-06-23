"""C1 — the bias_gate error taxonomy roots at ArcaneError (fail-closed family)."""

from __future__ import annotations

import pytest

from trading.bias_gate.errors import (
    BiasGateError,
    EvidenceConsistencyError,
    HighWaterMarkError,
    PurgeUnderspecifiedError,
)
from trading.risk.errors import ArcaneError


def test_bias_gate_error_is_arcane_error() -> None:
    assert issubclass(BiasGateError, ArcaneError)


@pytest.mark.parametrize(
    "exc",
    [HighWaterMarkError, PurgeUnderspecifiedError, EvidenceConsistencyError],
)
def test_every_bias_gate_error_is_a_bias_gate_error(exc: type[BiasGateError]) -> None:
    assert issubclass(exc, BiasGateError)
    assert issubclass(exc, ArcaneError)
    # constructable + carries its message
    instance = exc("boom")
    assert str(instance) == "boom"
    assert isinstance(instance, ArcaneError)
