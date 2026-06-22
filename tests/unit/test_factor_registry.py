"""Tests for FactorRegistry + default_registry — Increment 3 cluster 4 (the hard look-ahead gate).

Proves: default_registry builds the lean 13 within the ADR §5 budget and seeds the ledger with 13
distinct trials (idempotently across restarts); register is forge-proof (dup id / non-DERIVED /
non-factor rejected); validate_all is non-vacuous (FrameAdequacyError on empty/too-short panels) and
has TEETH on BOTH surfaces — it catches an obvious future-shift leak AND, critically, a global-
rescale leak that the base's z-score MASKS on compute() but the _raw prefix-stability check exposes.
"""

from __future__ import annotations

from typing import ClassVar

import numpy as np
import pandas as pd
import pytest

from trading.data.errors import PrefixStabilityError
from trading.data.prefix_stability import first_violation
from trading.data.reliability import Reliability
from trading.factors.base import AlphaFactor
from trading.factors.errors import (
    DuplicateFactorError,
    FactorContractError,
    FrameAdequacyError,
)
from trading.factors.momentum import Mom21d
from trading.factors.registry import (
    MAX_FACTORS,
    MIN_FACTORS,
    FactorRegistry,
    default_factors,
    default_registry,
)
from trading.factors.trial_ledger import TrialLedger


def _panel(n: int, *, seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2019-06-03", periods=n, freq="D", tz="UTC")
    idx.name = "ts"
    close = 100.0 * np.exp(np.cumsum(rng.normal(0.0002, 0.013, n)))
    intraday = rng.uniform(0.002, 0.02, n)
    open_ = close * (1.0 + rng.normal(0.0, 0.004, n))
    high = np.maximum.reduce([close * (1.0 + intraday), open_, close])
    low = np.minimum.reduce([close * (1.0 - intraday), open_, close])
    vol = rng.integers(50_000, 5_000_000, n)
    return pd.DataFrame(
        {
            "open": pd.Series(open_, index=idx, dtype="Float64"),
            "high": pd.Series(high, index=idx, dtype="Float64"),
            "low": pd.Series(low, index=idx, dtype="Float64"),
            "close": pd.Series(close, index=idx, dtype="Float64"),
            "volume": pd.Series(vol, index=idx, dtype="Int64"),
        }
    )


def _ledger(tmp_path: object) -> TrialLedger:
    return TrialLedger(tmp_path / "trials.sqlite", clock=lambda: 1.0)  # type: ignore[operator]


# --- default_registry: lean budget + ledger seeding ---


def test_default_registry_builds_the_lean_thirteen(tmp_path: object) -> None:
    reg = default_registry(_ledger(tmp_path))
    assert len(reg) == 13
    assert MIN_FACTORS <= len(reg) <= MAX_FACTORS
    assert len(default_factors()) == 13


def test_default_registry_seeds_ledger_with_thirteen_distinct_trials(tmp_path: object) -> None:
    led = _ledger(tmp_path)
    default_registry(led)
    assert led.n_trials() == 13
    # a fresh process re-builds the SAME 13 (idempotent) — n_trials stays 13, not 26.
    default_registry(led)
    assert led.n_trials() == 13


def test_default_factors_have_unique_ids() -> None:
    ids = [f.id for f in default_factors()]
    assert len(set(ids)) == len(ids) == 13


def test_factors_accessor_returns_registered_in_order(tmp_path: object) -> None:
    reg = default_registry(_ledger(tmp_path))
    assert tuple(f.id for f in reg.factors()) == tuple(f.id for f in default_factors())


def test_empty_registry_validates_vacuously() -> None:
    FactorRegistry().validate_all([_panel(343)])  # no factors registered -> honest no-op


# --- register: forge-proof ---


def test_register_rejects_duplicate_id() -> None:
    reg = FactorRegistry()
    reg.register(Mom21d())
    with pytest.raises(DuplicateFactorError):
        reg.register(Mom21d())


def test_register_rejects_non_alpha_factor() -> None:
    with pytest.raises(FactorContractError):
        FactorRegistry().register("not a factor")  # type: ignore[arg-type]


class _GateableFactor(AlphaFactor):
    """Adversarial: tries to relabel itself gateable (a §4.3 forge)."""

    id: ClassVar[str] = "gateable_forge"
    family: ClassVar[str] = "test"
    rationale: ClassVar[str] = "adversarial: claims HARD reliability"
    raw_lookback: ClassVar[int] = 0

    @property
    def reliability(self) -> Reliability:
        return Reliability.HARD  # forge attempt — must be rejected at registration

    def _raw(self, df: pd.DataFrame) -> pd.Series:
        return df["close"].astype("float64")


def test_register_rejects_non_derived_reliability() -> None:
    with pytest.raises(FactorContractError, match="DERIVED"):
        FactorRegistry().register(_GateableFactor())


# --- validate_all: frame-adequacy (fail-closed, non-vacuous) ---


def test_validate_all_rejects_empty_panel(tmp_path: object) -> None:
    with pytest.raises(FrameAdequacyError):
        default_registry(_ledger(tmp_path)).validate_all([])


def test_validate_all_rejects_too_short_frame(tmp_path: object) -> None:
    # MAX_TOTAL_WINDOW = 147 + 21 + 1 = 169 -> floor = 343; 100 rows is a vacuous false-green.
    with pytest.raises(FrameAdequacyError):
        default_registry(_ledger(tmp_path)).validate_all([_panel(100)])


# --- validate_all: TEETH on adequate panels ---


def test_default_registry_validates_clean(tmp_path: object) -> None:
    default_registry(_ledger(tmp_path)).validate_all([_panel(343, seed=1)])  # no raise


class _FutureShiftLeak(AlphaFactor):
    """Adversarial: pulls the next bar into the present (an OBVIOUS look-ahead)."""

    id: ClassVar[str] = "future_shift_leak"
    family: ClassVar[str] = "test"
    rationale: ClassVar[str] = "adversarial: negative shift"
    raw_lookback: ClassVar[int] = 0

    def _raw(self, df: pd.DataFrame) -> pd.Series:
        return df["close"].astype("float64").shift(-1)


class _MaskedRescaleLeak(AlphaFactor):
    """Adversarial: scales close by a FUTURE-dependent power of 2 (``2 ** (total_bars % 2)``).

    The base's trailing z-score is EXACTLY invariant to multiplication by a power of 2 (IEEE-754:
    ``*2^k`` only shifts the exponent, so mean/std/division cancel it bit-for-bit) — so this
    look-ahead (the scale depends on how many FUTURE bars exist) is BIT-IDENTICAL on compute() and
    thus perfectly MASKED there. Only the _raw prefix-stability check exposes it. This is the
    surgical proof that validate_all MUST check _raw, not only compute().
    """

    id: ClassVar[str] = "masked_rescale_leak"
    family: ClassVar[str] = "test"
    rationale: ClassVar[str] = "adversarial: scale by a future-length-dependent power of 2"
    raw_lookback: ClassVar[int] = 0

    def _raw(self, df: pd.DataFrame) -> pd.Series:
        close = df["close"].astype("float64")
        scale = 2.0 ** (len(df) % 2)  # depends on the TOTAL bar count = a look-ahead
        return close * scale


def _registry_with(*factors: AlphaFactor) -> FactorRegistry:
    reg = FactorRegistry()
    for f in factors:
        reg.register(f)
    return reg


def test_validate_all_catches_an_obvious_future_shift_leak() -> None:
    with pytest.raises(PrefixStabilityError):
        _registry_with(_FutureShiftLeak()).validate_all([_panel(300)])


def test_validate_all_catches_a_rescale_leak_that_compute_masks() -> None:
    leak = _MaskedRescaleLeak()
    # 1) demonstrate the MASK: the full compute() of this factor is prefix-stable (leak hidden,
    #    because the trailing z-score is bit-exactly invariant to the power-of-2 scale) ...
    assert first_violation(leak, _panel(120)) is None
    # 2) ... yet validate_all RAISES, because it ALSO checks the UNGUARDED _raw.
    with pytest.raises(PrefixStabilityError):
        _registry_with(leak).validate_all([_panel(300)])


class _LengthDependentLeak(AlphaFactor):
    """Adversarial: peeks at the future ONLY when the frame is long (a length-dependent leak).

    A per-factor depth-SLICE (the old validate_all) would check only short prefixes and MISS this;
    the red-team (registry-1) showed it passed a sliced gate but first_violation on the FULL frame
    catches it. validate_all now checks the full frame.
    """

    id: ClassVar[str] = "length_dependent_leak"
    family: ClassVar[str] = "test"
    rationale: ClassVar[str] = "adversarial: leaks only at len(df) >= 70"
    raw_lookback: ClassVar[int] = 5  # honestly small => old slice depth was ~59

    def _raw(self, df: pd.DataFrame) -> pd.Series:
        close = df["close"].astype("float64").copy()
        if len(df) >= 70:
            close.iloc[0] = df["close"].astype("float64").iloc[-1]  # poison row 0 with the future
        return close


def test_validate_all_catches_a_length_dependent_leak_on_the_full_frame() -> None:
    # red-team registry-1: a depth-slice (~59 rows) never reaches the len>=70 leaky region.
    with pytest.raises(PrefixStabilityError):
        _registry_with(_LengthDependentLeak()).validate_all([_panel(300)])


class _ConstantRaw(AlphaFactor):
    """A factor whose _raw is constant => trailing std==0 => GUARD C masks every z to NaN."""

    id: ClassVar[str] = "constant_raw"
    family: ClassVar[str] = "test"
    rationale: ClassVar[str] = "value-degenerate: a constant signal"
    raw_lookback: ClassVar[int] = 0

    def _raw(self, df: pd.DataFrame) -> pd.Series:
        return pd.Series(1.0, index=df.index, dtype="float64")


def test_validate_all_rejects_a_value_degenerate_panel() -> None:
    # red-team failopen-1: an all-NaN output makes the prefix check vacuously true (a false-green);
    # the gate must exercise REAL signal, else FrameAdequacyError.
    with pytest.raises(FrameAdequacyError, match="no non-NaN"):
        _registry_with(_ConstantRaw()).validate_all([_panel(300)])
