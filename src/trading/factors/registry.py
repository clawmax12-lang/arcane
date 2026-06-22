"""The shared factor registry — unique ids, frame-adequacy, registry-wide prefix-stability, ledger.

``validate_all`` is the HARD look-ahead gate (run in pytest): for every factor it asserts
prefix-stability on BOTH the UNGUARDED ``_raw`` (so a leaky ``_raw`` cannot hide behind the base's
``z`` / ``clip`` / ``shift`` — e.g. a global rescale that per-row z-scoring cancels is invisible on
``compute()`` yet caught on ``_raw``) AND the full ``compute()``. It mirrors the Inc-2 ``@final``
base + ``check_registry`` idiom and reuses ``data/prefix_stability`` with zero rework.

``default_registry`` builds the FROZEN lean 13, asserts the ADR §5 budget (10–15), and records each
as a trial in the ``TrialLedger`` (the M18 search-breadth count). Frame-adequacy: a panel shorter
than the deepest factor's pipeline yields all-NaN prefixes that pass vacuously (a false-green
look-ahead check) — so a too-short or empty panel fails closed with ``FrameAdequacyError``. Each
factor is then checked on a slice of the panel sized to its OWN pipeline depth (the floor guarantees
the slice is adequate), so the gate is non-vacuous AND fast.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Final

import pandas as pd

from trading.data.prefix_stability import assert_prefix_stable
from trading.data.reliability import Reliability
from trading.factors.base import AlphaFactor
from trading.factors.errors import (
    DuplicateFactorError,
    FactorContractError,
    FrameAdequacyError,
)
from trading.factors.meanrev import Reversal5d
from trading.factors.momentum import Mom21d, Mom63d, Mom126Skip21
from trading.factors.range_factors import (
    CloseLocInRange,
    DistFromSma50,
    HlRange21d,
    SmaRatio2050,
)
from trading.factors.trial_ledger import TrialLedger
from trading.factors.volatility import Atr14, Vol21d
from trading.factors.volume import AmihudIlliq21d, DollarVol21d, RelVolume21d

MIN_FACTORS: Final[int] = 10
MAX_FACTORS: Final[int] = 15  # ADR §5 lean budget — never exceed


def default_factors() -> tuple[AlphaFactor, ...]:
    """The FROZEN lean 13 (order is the canonical registry/ledger order)."""
    return (
        Mom21d(),
        Mom63d(),
        Mom126Skip21(),
        Reversal5d(),
        Vol21d(),
        Atr14(),
        DollarVol21d(),
        RelVolume21d(),
        AmihudIlliq21d(),
        HlRange21d(),
        CloseLocInRange(),
        DistFromSma50(),
        SmaRatio2050(),
    )


class _PrefixView:
    """A ``PrefixComputation`` adapter over a factor's ``_raw`` or full ``compute()``.

    ``id`` is a settable instance attribute (not a ``ClassVar``/read-only property), so the adapter
    satisfies the ``PrefixComputation`` Protocol that a factor's ``ClassVar`` ``id`` does not.
    """

    __slots__ = ("id", "fn")

    def __init__(self, name: str, fn: Callable[[pd.DataFrame], pd.Series]) -> None:
        self.id = name
        self.fn = fn

    def compute(self, df: pd.DataFrame) -> pd.Series:
        return self.fn(df)


class FactorRegistry:
    """Holds factors by unique id; ``validate_all`` is the registry-wide look-ahead gate."""

    def __init__(self) -> None:
        self._factors: dict[str, AlphaFactor] = {}

    def register(self, factor: AlphaFactor) -> None:
        if not isinstance(factor, AlphaFactor):
            raise FactorContractError(f"not an AlphaFactor: {type(factor).__name__}")
        # forge-proof §4.3: a factor whose reliability is not DERIVED could be threaded into a gate.
        if factor.reliability is not Reliability.DERIVED:
            raise FactorContractError(
                f"factor {factor.id!r} reliability is {factor.reliability} — must be DERIVED (§4.3)"
            )
        if factor.id in self._factors:
            raise DuplicateFactorError(f"duplicate factor id {factor.id!r}")
        self._factors[factor.id] = factor

    def factors(self) -> tuple[AlphaFactor, ...]:
        return tuple(self._factors.values())

    def __len__(self) -> int:
        return len(self._factors)

    def max_total_window(self) -> int:
        """Deepest factor pipeline: max over factors of ``raw_lookback + z_window + 1[shift]``."""
        return max(f.raw_lookback + f.z_window + 1 for f in self._factors.values())

    def validate_all(self, frames: Sequence[pd.DataFrame]) -> None:
        if not self._factors:
            return  # honest vacuous pass — no factors registered
        if not frames:
            raise FrameAdequacyError("validate_all requires at least one sample frame")
        floor = 2 * self.max_total_window() + 5
        for df in frames:
            if len(df) < floor:
                raise FrameAdequacyError(
                    f"sample frame len {len(df)} < required {floor} "
                    "(too short => a vacuous false-green look-ahead check)"
                )
        for factor in self._factors.values():
            depth = 2 * (factor.raw_lookback + factor.z_window + 1) + 5
            for df in frames:
                sub = df.iloc[:depth]  # frame >= floor >= depth, so the slice is adequate
                assert_prefix_stable(_PrefixView(f"{factor.id}__raw", factor._raw), sub)  # raw
                assert_prefix_stable(_PrefixView(factor.id, factor.compute), sub)  # full compute()


def default_registry(ledger: TrialLedger) -> FactorRegistry:
    """Build the lean 13, assert the ADR §5 budget, and record each as a trial in ``ledger``."""
    registry = FactorRegistry()
    for factor in default_factors():
        registry.register(factor)
        ledger.record("factor", factor.id, dict(factor.params()))
    count = len(registry)
    if not (MIN_FACTORS <= count <= MAX_FACTORS):
        raise FactorContractError(
            f"factor count {count} outside the ADR §5 lean budget [{MIN_FACTORS}, {MAX_FACTORS}]"
        )
    return registry
