"""Tests for the FINAL ``AlphaFactor`` base — Increment 3 cluster 1.

The base owns every correctness property after ``_raw`` returns: STEP-0 input assertion, GUARD A
(type/shape/index-equality), GUARD B (finiteness on ``_raw`` BEFORE z-scoring — inf is the failure,
NaN is the honest hole), strictly-trailing rolling-z (min_periods==window, ddof=1, no center),
GUARD C (zero-variance => NaN, never a fabricated +/-3), clip[-3,3], and the ONE mandatory shift(1).
These tests prove a clean trailing factor passes end-to-end (with a hand-computed numeric check) and
that every contract breach FAILS CLOSED.
"""

from __future__ import annotations

from typing import Final

import numpy as np
import pandas as pd
import pytest

from trading.data.prefix_stability import first_violation
from trading.data.reliability import Reliability
from trading.factors.base import AlphaFactor
from trading.factors.errors import FactorContractError


def _frame(closes: list[float], *, volume: int = 100) -> pd.DataFrame:
    n = len(closes)
    idx = pd.date_range("2024-01-02", periods=n, freq="D", tz="UTC")
    idx.name = "ts"
    c = pd.Series(closes, index=idx, dtype="Float64")
    return pd.DataFrame(
        {
            "open": c,
            "high": c + 1,
            "low": c - 1,
            "close": c,
            "volume": pd.Series([volume] * n, index=idx, dtype="Int64"),
        }
    )


class _IdentityClose(AlphaFactor):
    """Minimal trailing/same-bar factor: _raw is close itself (z_window small for hand-checks)."""

    id: Final[str] = "identity_close"
    rationale: Final[str] = "test fixture — same-bar close, z-scored by the base"
    z_window: Final[int] = 2
    raw_lookback: Final[int] = 0

    def _raw(self, df: pd.DataFrame) -> pd.Series:
        return df["close"]


class _RawWithNaN(AlphaFactor):
    id: Final[str] = "raw_with_nan"
    rationale: Final[str] = "test fixture — trailing return whose warmup row is NaN (allowed)"
    z_window: Final[int] = 2
    raw_lookback: Final[int] = 1

    def _raw(self, df: pd.DataFrame) -> pd.Series:
        return df["close"].pct_change()


# --- contract: reliability is DERIVED and read-only; compute is @final ---


def test_reliability_is_derived() -> None:
    assert _IdentityClose().reliability is Reliability.DERIVED


def test_compute_is_marked_final() -> None:
    # typing.final stamps __final__ = True; mirrors DataLoader.load / PITUniverse.as_of_members.
    assert getattr(AlphaFactor.compute, "__final__", False) is True


# --- the happy path: a clean trailing factor, hand-computed end-to-end ---


def test_identity_close_pipeline_is_hand_correct() -> None:
    out = _IdentityClose().compute(_frame([10.0, 12.0, 11.0, 13.0]))
    # mean(2)=[NA,11,11.5,12]; std(2,ddof=1)=[NA,1.41421,0.70711,1.41421]
    # z=[NA, 0.70711, -0.70711, 0.70711]; clip keeps; shift(1)=>[NA,NA,0.70711,-0.70711]
    vals = out.to_numpy(dtype="float64", na_value=np.nan)
    assert np.isnan(vals[0]) and np.isnan(vals[1])
    assert vals[2] == pytest.approx(0.70710678, abs=1e-6)
    assert vals[3] == pytest.approx(-0.70710678, abs=1e-6)
    assert out.index.equals(_frame([10.0, 12.0, 11.0, 13.0]).index)


def test_output_first_row_is_nan_from_the_mandatory_shift() -> None:
    out = _IdentityClose().compute(_frame([10.0, 12.0, 11.0, 13.0, 14.0]))
    assert pd.isna(out.iloc[0])


def test_nan_in_raw_is_allowed_not_rejected() -> None:
    # pct_change's first row is NaN — the honest warmup marker, must NOT raise.
    out = _RawWithNaN().compute(_frame([10.0, 11.0, 12.0, 13.0, 14.0]))
    assert isinstance(out, pd.Series)
    assert not np.isinf(out.to_numpy(dtype="float64", na_value=np.nan)).any()


def test_good_factor_is_prefix_stable() -> None:
    frame = _frame([10.0, 11.5, 12.0, 11.0, 13.0, 14.0, 13.0])
    assert first_violation(_RawWithNaN(), frame) is None


# --- GUARD C: zero-variance window => NaN, never inf, never a fabricated +/-3 ---


def test_constant_input_yields_nan_not_a_fabricated_extreme() -> None:
    out = _IdentityClose().compute(_frame([5.0, 5.0, 5.0, 5.0, 5.0, 5.0]))
    arr = out.to_numpy(dtype="float64", na_value=np.nan)
    assert not np.isinf(arr).any(), "zero-variance std==0 must NOT fabricate +/-inf -> +/-3"
    assert np.isnan(arr).all(), "a flat series has no signal -> all NaN"


# --- GUARD B: inf in _raw is rejected (the laundering surface prefix-stability misses) ---


class _RawInf(AlphaFactor):
    id: Final[str] = "raw_inf"
    rationale: Final[str] = "adversarial: emits inf (e.g. an unguarded x/0)"
    z_window: Final[int] = 2
    raw_lookback: Final[int] = 0

    def _raw(self, df: pd.DataFrame) -> pd.Series:
        s = df["close"].astype("float64").copy()
        s.iloc[1] = np.inf
        return s


def test_inf_in_raw_fails_closed() -> None:
    with pytest.raises(FactorContractError, match="inf"):
        _RawInf().compute(_frame([10.0, 11.0, 12.0, 13.0]))


class _RawNonNumeric(AlphaFactor):
    id: Final[str] = "raw_non_numeric"
    rationale: Final[str] = "adversarial: returns a non-numeric (object) Series"
    z_window: Final[int] = 2
    raw_lookback: Final[int] = 0

    def _raw(self, df: pd.DataFrame) -> pd.Series:
        return pd.Series(["a", "b", "c", "d"], index=df.index, dtype="object")


def test_non_numeric_raw_fails_closed() -> None:
    with pytest.raises(FactorContractError, match="numeric"):
        _RawNonNumeric().compute(_frame([10.0, 11.0, 12.0, 13.0]))


class _RawNumericString(AlphaFactor):
    id: Final[str] = "raw_numeric_string"
    rationale: Final[str] = "adversarial: object Series of numeric STRINGS (silently coercible)"
    z_window: Final[int] = 2
    raw_lookback: Final[int] = 0

    def _raw(self, df: pd.DataFrame) -> pd.Series:
        return pd.Series([str(float(i)) for i in range(len(df))], index=df.index, dtype="object")


class _RawBool(AlphaFactor):
    id: Final[str] = "raw_bool"
    rationale: Final[str] = "adversarial: bool/object Series (silently coercible)"
    z_window: Final[int] = 2
    raw_lookback: Final[int] = 0

    def _raw(self, df: pd.DataFrame) -> pd.Series:
        return (df["close"].astype("float64") > 11.0).astype("object")


@pytest.mark.parametrize("factor", [_RawNumericString(), _RawBool()], ids=lambda f: f.id)
def test_silently_coercible_off_contract_dtype_fails_closed(factor: AlphaFactor) -> None:
    # red-team leak-1: to_numpy(dtype="float64") would SILENTLY coerce these; GUARD A rejects them.
    with pytest.raises(FactorContractError, match="real-numeric"):
        factor.compute(_frame([10.0, 11.0, 12.0, 13.0]))


def test_params_exposes_the_factor_windows() -> None:
    assert _IdentityClose().params() == {"z_window": 2, "raw_lookback": 0}


# --- GUARD A: shape / type / index-alignment breaches fail closed ---


class _RawWrongLength(AlphaFactor):
    id: Final[str] = "raw_wrong_length"
    rationale: Final[str] = "adversarial: drops a row (realignment)"
    z_window: Final[int] = 2
    raw_lookback: Final[int] = 0

    def _raw(self, df: pd.DataFrame) -> pd.Series:
        return df["close"].iloc[1:]


class _RawReindexed(AlphaFactor):
    id: Final[str] = "raw_reindexed"
    rationale: Final[str] = "adversarial: right length but a DIFFERENT index (misalignment)"
    z_window: Final[int] = 2
    raw_lookback: Final[int] = 0

    def _raw(self, df: pd.DataFrame) -> pd.Series:
        shifted = df["close"].copy()
        shifted.index = df.index + pd.Timedelta(days=1000)
        return shifted


class _RawNotSeries(AlphaFactor):
    id: Final[str] = "raw_not_series"
    rationale: Final[str] = "adversarial: returns an ndarray, not a Series"
    z_window: Final[int] = 2
    raw_lookback: Final[int] = 0

    def _raw(self, df: pd.DataFrame) -> pd.Series:
        return df["close"].to_numpy()  # type: ignore[return-value]


@pytest.mark.parametrize(
    "factor", [_RawWrongLength(), _RawReindexed(), _RawNotSeries()], ids=lambda f: f.id
)
def test_misaligned_raw_fails_closed(factor: AlphaFactor) -> None:
    with pytest.raises(FactorContractError):
        factor.compute(_frame([10.0, 11.0, 12.0, 13.0]))


# --- STEP 0: a bad input frame fails closed BEFORE _raw runs ---


def test_tz_naive_index_is_rejected() -> None:
    df = _frame([10.0, 11.0, 12.0])
    df.index = df.index.tz_localize(None)
    with pytest.raises(FactorContractError):
        _IdentityClose().compute(df)


def test_missing_column_is_rejected() -> None:
    df = _frame([10.0, 11.0, 12.0]).drop(columns=["volume"])
    with pytest.raises(FactorContractError):
        _IdentityClose().compute(df)


def test_non_monotonic_index_is_rejected() -> None:
    df = _frame([10.0, 11.0, 12.0]).iloc[::-1]
    with pytest.raises(FactorContractError):
        _IdentityClose().compute(df)
