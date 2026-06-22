"""Registry-wide prefix-stability (look-ahead) property — Increment 2 STEP 8.

A computation is *prefix-stable* iff truncating its input to the first ``k`` rows yields exactly
the first ``k`` rows of computing on the full input::

    compute(df[:k]) == compute(df[:k+1])[:k]        for every k

This *is* the definition of "uses no future data": every classic leak shape — full-series
normalization, centered windows, target/feature misalignment, normalize-by-last,
resample/dropna realignment — breaks it by construction. So a look-ahead leak becomes a *test
failure* found mechanically, not a code-review judgment call (ADR-001 §7).

The harness is generic over any iterable of computations, so the Increment-3 ``AlphaFactor`` base
and the shared registry plug in with zero rework: ``registry.validate_all()`` will simply call
:func:`check_registry` over its factors and a panel of sample frames. There are no factors yet
(Increment 2), so the production registry call is vacuous today — the *teeth* live in the tests,
which prove the property catches deliberately-leaky factors.

Fail-closed posture: anything that prevents a clean prefix-by-prefix comparison — a raised
exception, an output whose length differs from the input, a type/index/dtype mismatch — is a
VIOLATION, never a silent pass.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import pandas as pd

from trading.data.errors import PrefixStabilityError

# A factor maps a bar frame to one aligned value per input row (a Series, or a DataFrame of them).
type ComputeOutput = pd.Series | pd.DataFrame


@runtime_checkable
class PrefixComputation(Protocol):
    """A named, deterministic transform from a bar frame to a row-aligned output."""

    id: str

    def compute(self, df: pd.DataFrame) -> ComputeOutput: ...


@dataclass(frozen=True, slots=True)
class PrefixViolation:
    """The first prefix length ``k`` at which a computation revealed a look-ahead dependency."""

    computation_id: str
    k: int
    reason: str


def _aligned_equal(prefix: ComputeOutput, expected: ComputeOutput) -> bool:
    """True only if same container type, shape, index, dtype, and values (NaN==NaN per pandas)."""
    if type(prefix) is not type(expected):
        return False
    return bool(prefix.equals(expected))


def first_violation(comp: PrefixComputation, df: pd.DataFrame) -> PrefixViolation | None:
    """Return the first prefix-stability violation for ``comp`` on ``df``, or ``None`` if stable.

    Compares ``compute(df.iloc[:k])`` against ``compute(df).iloc[:k]`` for every ``k`` in
    ``1..len(df)-1``. Any exception, length mismatch, or value/index/dtype divergence is a
    violation (fail-closed) — a robust trailing factor returns NaN on a short window, it never
    raises and never realigns.
    """
    try:
        full = comp.compute(df)
    except Exception as exc:  # a registered computation must not raise on a valid frame
        return PrefixViolation(comp.id, len(df), f"compute raised on the full frame: {exc!r}")
    if len(full) != len(df):
        return PrefixViolation(
            comp.id, len(df), f"output length {len(full)} != input length {len(df)} (realignment)"
        )
    for k in range(1, len(df)):
        try:
            prefix = comp.compute(df.iloc[:k])
        except Exception as exc:
            return PrefixViolation(comp.id, k, f"compute raised on the prefix df[:{k}]: {exc!r}")
        if len(prefix) != k:
            return PrefixViolation(
                comp.id, k, f"prefix output length {len(prefix)} != {k} (realignment)"
            )
        if not _aligned_equal(prefix, full.iloc[:k]):
            return PrefixViolation(
                comp.id, k, "compute(df[:k]) != compute(df)[:k] — depends on future rows"
            )
    return None


def assert_prefix_stable(comp: PrefixComputation, df: pd.DataFrame) -> None:
    """Raise :class:`PrefixStabilityError` if ``comp`` has any look-ahead dependency on ``df``."""
    violation = first_violation(comp, df)
    if violation is not None:
        raise PrefixStabilityError(
            f"{violation.computation_id}: prefix-instability at k={violation.k}: {violation.reason}"
        )


def check_registry(comps: Iterable[PrefixComputation], frames: Sequence[pd.DataFrame]) -> None:
    """Assert every computation is prefix-stable on every sample frame (registry-wide entry point).

    This is what the Increment-3 shared-registry ``validate_all()`` calls. With no factors
    registered (Increment 2) it is a vacuous pass; the contract and the leak-catching teeth are
    proven by the STEP-8 tests.
    """
    for comp in comps:
        for df in frames:
            assert_prefix_stable(comp, df)
