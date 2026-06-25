"""C4 — the deterministic regime model: leak-free (prefix-stable), pure-deterministic, UNKNOWN warm.

The regime label is ADVISORY DERIVED posture (it can never gate/size/override — that boundary is
proven in test_regime_boundary). Here we prove it is computed with the SAME causal discipline as the
13 factors: ``compute(df[:k]) == compute(df[:k+1])[:k]`` (a look-ahead leak is a mechanical test
failure, ADR §7) — with a must-FAIL canary (full-sample tercile edges) proving the property bites
— plus pure determinism and an UNKNOWN warmup that never fabricates a confident regime.
"""

from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pandas as pd

from trading.data.prefix_stability import check_registry, first_violation
from trading.regime.labels import PRODUCT_LABELS, RegimeLabel
from trading.regime.model import (
    SMA_LEN,
    VOL_LOOKBACK,
    DeterministicRegimeModel,
    assess,
)

_REGIME_PKG = Path(__file__).resolve().parents[2] / "src" / "trading" / "regime"


def _bars(n: int, *, seed: int, drift: float = 0.0003) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.DatetimeIndex(pd.bdate_range("2014-01-02", periods=n, tz="UTC"), name="ts")
    close = 100.0 * np.exp(np.cumsum(rng.normal(drift, 0.015, n)))
    return pd.DataFrame({"close": pd.Series(close, index=idx, dtype="float64")}, index=idx)


def _flat_bars(n: int) -> pd.DataFrame:
    idx = pd.DatetimeIndex(pd.bdate_range("2014-01-02", periods=n, tz="UTC"), name="ts")
    return pd.DataFrame({"close": pd.Series([100.0] * n, index=idx, dtype="float64")}, index=idx)


class _Comp:
    """Adapt a RegimeModel to the prefix_stability PrefixComputation protocol (.id + .compute)."""

    def __init__(self, model: object) -> None:
        self.id = getattr(model, "model_id", "regime")
        self._model = model

    def compute(self, df: pd.DataFrame) -> pd.Series:
        return self._model.label_series(df)  # type: ignore[attr-defined,no-any-return]


class _LeakyRegimeModel:
    """A deliberately LEAKY variant: full-sample tercile edges peek at the FUTURE vol distrib."""

    model_id = "leaky_full_sample_edges"

    def label_series(self, bars: pd.DataFrame) -> pd.Series:
        close = bars["close"].astype("float64")
        log_ret = np.log(close).diff()
        vol = log_ret.rolling(VOL_LOOKBACK).std()
        q_lo = vol.quantile(1.0 / 3.0)  # LEAK: a scalar over the WHOLE series (future included)
        q_hi = vol.quantile(2.0 / 3.0)
        sma = close.rolling(SMA_LEN).mean()
        finite = vol.notna() & sma.notna() & pd.notna(q_lo) & pd.notna(q_hi)
        trend = np.where(close.to_numpy() > sma.to_numpy(), "up", "down")
        vb = np.where(vol.to_numpy() <= q_lo, "low", np.where(vol.to_numpy() > q_hi, "high", "mid"))
        built = pd.Series(
            [f"{v}_vol_{t}" for v, t in zip(vb, trend, strict=True)], index=close.index
        )
        label = pd.Series(RegimeLabel.UNKNOWN.value, index=close.index, dtype=object)
        label[finite] = built[finite]
        published = label.shift(1)
        return published.where(published.notna(), RegimeLabel.UNKNOWN.value).astype(object)


# --- label set ---


def test_label_space_is_six_products_plus_unknown() -> None:
    assert len(PRODUCT_LABELS) == 6
    assert set(RegimeLabel) == set(PRODUCT_LABELS) | {RegimeLabel.UNKNOWN}


# --- leak-freedom (the load-bearing causal proof) ---


def test_regime_is_prefix_stable_on_normal_and_degenerate_frames() -> None:
    model = DeterministicRegimeModel()
    frames = [_bars(300, seed=1), _bars(300, seed=2, drift=-0.0004), _flat_bars(200)]
    check_registry([_Comp(model)], frames)  # raises PrefixStabilityError on any look-ahead


def test_prefix_stability_canary_catches_a_full_sample_tercile_leak() -> None:
    # The must-FAIL teeth: a leaky full-sample-edge variant MUST be caught (else the property above
    # would be vacuous — memory: optimizing/relying-on a gate without proving it still CATCHES).
    violation = first_violation(_Comp(_LeakyRegimeModel()), _bars(300, seed=7))
    assert violation is not None and "future" in violation.reason


# --- determinism ---


def test_regime_is_a_pure_deterministic_function_of_past_bars() -> None:
    model = DeterministicRegimeModel()
    bars = _bars(300, seed=3)
    assert model.label_series(bars).equals(model.label_series(bars))  # same input -> bit-identical
    assert (
        DeterministicRegimeModel().label_series(bars).equals(model.label_series(bars))
    )  # any inst


def test_appending_future_bars_never_changes_a_past_label() -> None:
    model = DeterministicRegimeModel()
    full = _bars(300, seed=4)
    k = 220
    assert model.label_series(full).iloc[:k].equals(model.label_series(full.iloc[:k]))


def test_no_wall_clock_or_rng_import_in_the_regime_package() -> None:
    banned = {"random", "secrets", "time"}
    offenders: list[str] = []
    for py in _REGIME_PKG.rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                offenders += [f"{py.name}: {a.name}" for a in node.names if a.name in banned]
            elif isinstance(node, ast.ImportFrom) and node.module in banned:
                offenders.append(f"{py.name}: from {node.module}")
    assert not offenders, f"non-deterministic import in regime/: {offenders}"


# --- UNKNOWN warmup (never a fabricated confident regime) ---


def test_warmup_is_unknown_then_a_confident_label_emerges() -> None:
    model = DeterministicRegimeModel()
    series = model.label_series(_bars(400, seed=5))
    assert all(v == RegimeLabel.UNKNOWN.value for v in series.iloc[:60])  # warmup is UNKNOWN
    assert RegimeLabel(str(series.iloc[-1])) in PRODUCT_LABELS  # a confident label by the end


def test_short_frame_is_all_unknown_and_does_not_raise() -> None:
    series = DeterministicRegimeModel().label_series(_bars(10, seed=6))
    assert len(series) == 10
    assert all(v == RegimeLabel.UNKNOWN.value for v in series)


def test_empty_frame_returns_empty_series() -> None:
    empty = pd.DataFrame({"close": pd.Series([], dtype="float64")})
    assert len(DeterministicRegimeModel().label_series(empty)) == 0


# --- assess() returns the current advisory read ---


def test_assess_returns_a_label_and_confidence() -> None:
    a = assess(DeterministicRegimeModel(), _bars(400, seed=8))
    assert a.label in set(RegimeLabel)
    assert 0.0 <= a.confidence <= 1.0
    assert a.model_id == "deterministic_tercile_trend_v1"
