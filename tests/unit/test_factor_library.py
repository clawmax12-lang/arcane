"""Tests for the 13 standard alpha factors — Increment 3 cluster 3.

Proves each factor: (1) is prefix-stable (no look-ahead) on an adequately-long frame; (2) yields a
finite-or-NaN float64 Series aligned to the bar index — NEVER inf, even on adversarial bars
(zero-volume, zero-range, zero-change) that exercise every NaN-guarded division; (3) is DERIVED
(§4.3); (4) has the expected raw sign / bounded shape. The zero-volume / zero-range cases are the
highest-priority guard tests (an unguarded x/0 would make _raw inf -> base GUARD B raises ->
prefix-stability reports a FALSE leak and the gate goes red).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trading.data.prefix_stability import first_violation
from trading.data.reliability import Reliability
from trading.factors.base import AlphaFactor
from trading.factors.meanrev import Reversal5d
from trading.factors.momentum import Mom21d, Mom63d, Mom126Skip21
from trading.factors.range_factors import (
    CloseLocInRange,
    DistFromSma50,
    HlRange21d,
    SmaRatio2050,
)
from trading.factors.volatility import Atr14, Vol21d
from trading.factors.volume import AmihudIlliq21d, DollarVol21d, RelVolume21d

FACTORS: list[AlphaFactor] = [
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
]


def _panel(n: int, *, seed: int = 7) -> pd.DataFrame:
    """A deterministic, schema-shaped OHLCV daily frame (high>=open/close>=low, volume>0)."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-02", periods=n, freq="D", tz="UTC")
    idx.name = "ts"
    close = 100.0 * np.exp(np.cumsum(rng.normal(0.0003, 0.012, n)))
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


def test_there_are_thirteen_factors_with_unique_ids() -> None:
    assert len(FACTORS) == 13
    ids = [f.id for f in FACTORS]
    assert len(set(ids)) == 13


@pytest.mark.parametrize("factor", FACTORS, ids=lambda f: f.id)
def test_factor_output_shape_dtype_and_finiteness(factor: AlphaFactor) -> None:
    df = _panel(400)
    out = factor.compute(df)
    assert isinstance(out, pd.Series)
    assert out.index.equals(df.index)
    assert str(out.dtype) == "float64"
    assert not np.isinf(out.to_numpy("float64", na_value=np.nan)).any()
    assert out.notna().sum() > 0, "a factor must produce some real signal after warmup"


@pytest.mark.parametrize("factor", FACTORS, ids=lambda f: f.id)
def test_factor_is_prefix_stable(factor: AlphaFactor) -> None:
    # frame sized to this factor's full pipeline depth so prefix-stability is non-vacuous.
    n = 2 * (factor.raw_lookback + factor.z_window + 1) + 5
    assert first_violation(factor, _panel(n)) is None, f"{factor.id} has a look-ahead leak"


@pytest.mark.parametrize("factor", FACTORS, ids=lambda f: f.id)
def test_factor_is_finite_or_nan_on_adversarial_bars(factor: AlphaFactor) -> None:
    df = _panel(360).copy()
    df.loc[df.index[120], "volume"] = 0  # zero-volume bar (amihud/rel_volume div-by-zero)
    px = float(df.loc[df.index[180], "close"])
    df.loc[df.index[180], ["open", "high", "low"]] = px  # zero-range bar (close_loc/hl_range)
    df.loc[df.index[240], "close"] = df.loc[df.index[239], "close"]  # zero-change bar
    out = factor.compute(df)  # must NOT raise — every division is .where(denom>0)-guarded to NaN
    assert not np.isinf(out.to_numpy("float64", na_value=np.nan)).any()


@pytest.mark.parametrize("factor", FACTORS, ids=lambda f: f.id)
def test_every_factor_is_derived_with_metadata(factor: AlphaFactor) -> None:
    assert factor.reliability is Reliability.DERIVED
    assert factor.id and factor.rationale and factor.family


# --- formula sanity (the raw sign/shape, bypassing the z-score) ---


def _rising_frame(n: int = 80) -> pd.DataFrame:
    idx = pd.date_range("2021-01-04", periods=n, freq="D", tz="UTC")
    idx.name = "ts"
    close = pd.Series(np.linspace(100.0, 200.0, n), index=idx, dtype="Float64")
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": pd.Series([1_000_000] * n, index=idx, dtype="Int64"),
        }
    )


def test_momentum_raw_is_positive_on_a_rising_series() -> None:
    assert Mom21d()._raw(_rising_frame()).iloc[-1] > 0


def test_reversal_raw_is_negative_on_a_rising_series() -> None:
    # negated trailing return -> a rising series is "overbought" -> negative reversal signal.
    assert Reversal5d()._raw(_rising_frame()).iloc[-1] < 0


def test_close_loc_raw_is_within_the_unit_range() -> None:
    raw = CloseLocInRange()._raw(_panel(60)).dropna()
    assert (raw >= 0).all() and (raw <= 1).all()
