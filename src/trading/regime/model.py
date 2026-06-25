"""The deterministic regime classifier — tercile-by-trend over bar data (Inc-7 PART B).

A lean, dependency-light, STRICTLY CAUSAL regime label (ADR §5: "deterministic + Markov/HMM only";
hmmlearn/torch are deferred). The label at bar ``t`` is computed from a trailing realized-volatility
tercile × a trailing trend sign, then ``shift(1)``-published so it uses ONLY bars ``<= t-1`` (the
``AlphaFactor`` one-shift idiom) — leak-free by construction (proven by the registry prefix
property). Window params are FROZEN module constants (no YAML, no per-run tuning — §7 forbids tuning
during a live day; not a parameter-drift vector). It is a PURE function of past bars: no wall-clock,
no RNG, no fit/seed surface, so it is exactly reproducible.

The label is §4.3 DERIVED — carried in a ``RegimeAssessment`` whose ``reliability`` is a read-only
property (no settable field). It can NEVER reach a gate/sizing/cap input (no such parameter exists
on those signatures — a mypy error — and an AST import-ban keeps the regime package out of
``bias_gate``/``executor``(sizing/grant)/``risk``). PHI1: no LLM/agent import (in the submit-path
scan). The ``RegimeModel`` Protocol lets an HMM register as a drop-in later (ADR §4).
"""

from __future__ import annotations

from typing import Final, Protocol, runtime_checkable

import numpy as np
import pandas as pd

from trading.data.reliability import Reliability
from trading.regime.labels import RegimeLabel

#: Frozen window constants (law, NOT operator-tunable — mirrors ``AlphaFactor`` z-window).
VOL_LOOKBACK: Final[int] = 63  # trailing realized-vol window (≈ one quarter of sessions)
VOL_MIN_POINTS: Final[int] = 63  # min non-NaN vol observations before tercile edges are confident
SMA_LEN: Final[int] = 50  # trailing trend SMA length


@runtime_checkable
class RegimeModel(Protocol):
    """A named, deterministic regime classifier (an HMM can register as a drop-in later, ADR §4)."""

    model_id: str

    def label_series(self, bars: pd.DataFrame) -> pd.Series: ...


class RegimeAssessment:
    """The advisory regime read — a label + confidence. ``reliability`` is DERIVED, read-only.

    There is NO settable ``reliability`` field (mirrors ``AlphaFactor`` reliability and
    ``UniverseMeta.survivorship_unverified``): a caller can never forge it to HARD/STRUCTURED to
    smuggle a DERIVED label past a §4.3 gate. The allocator consumes ``label`` for POSTURE only
    (subtractive eligibility) — it is never a gate/sizing/cap input.
    """

    __slots__ = ("label", "confidence", "model_id")

    label: RegimeLabel
    confidence: float
    model_id: str

    def __init__(self, label: RegimeLabel, confidence: float, model_id: str) -> None:
        object.__setattr__(self, "label", label)
        object.__setattr__(self, "confidence", float(confidence))
        object.__setattr__(self, "model_id", model_id)

    def __setattr__(self, name: str, value: object) -> None:  # frozen
        raise AttributeError("RegimeAssessment is immutable")

    @property
    def reliability(self) -> Reliability:
        """Always DERIVED (§4.3) — advisory only, never gates/sizes/overrides; no field to forge."""
        return Reliability.DERIVED

    def __repr__(self) -> str:
        return f"RegimeAssessment(label={self.label.value!r}, confidence={self.confidence:.3f})"


class DeterministicRegimeModel:
    """Tercile-by-trend regime over a market-proxy OHLCV frame (the default ``RegimeModel``)."""

    model_id: str = "deterministic_tercile_trend_v1"

    def label_series(self, bars: pd.DataFrame) -> pd.Series:
        """A ``shift(1)``-published, strictly-causal ``RegimeLabel`` value per bar (object Series).

        Warmup rows (insufficient history) and the leading shift are ``UNKNOWN``. NEVER raises on a
        valid OHLCV frame and NEVER realigns (length == input length) — so it plugs into the
        registry prefix-stability property with zero rework.
        """
        close = bars["close"].astype("float64")
        n = len(close)
        unknown = RegimeLabel.UNKNOWN.value
        if n == 0:
            return pd.Series([], index=close.index, dtype=object)

        log_ret = np.log(close).diff()
        vol = log_ret.rolling(VOL_LOOKBACK).std()
        # Causal tercile edges: EXPANDING quantiles use only past+present vol (never the full-sample
        # future distribution); the final shift(1) makes the published label use only bars <= t-1.
        q_lo = vol.expanding(min_periods=VOL_MIN_POINTS).quantile(1.0 / 3.0)
        q_hi = vol.expanding(min_periods=VOL_MIN_POINTS).quantile(2.0 / 3.0)
        sma = close.rolling(SMA_LEN).mean()

        finite = vol.notna() & q_lo.notna() & q_hi.notna() & sma.notna()
        low = vol <= q_lo
        high = vol > q_hi
        trend = np.where(close.to_numpy() > sma.to_numpy(), "up", "down")
        vb = np.where(low.to_numpy(), "low", np.where(high.to_numpy(), "high", "mid"))
        built = pd.Series(
            [f"{v}_vol_{t}" for v, t in zip(vb, trend, strict=True)], index=close.index
        )

        label = pd.Series(unknown, index=close.index, dtype=object)
        label[finite] = built[finite]
        # The ONE mandatory shift: the label PUBLISHED at bar t uses only bars <= t-1 (leak-free).
        published = label.shift(1)
        return published.where(published.notna(), unknown).astype(object)


def assess(model: RegimeModel, bars: pd.DataFrame) -> RegimeAssessment:
    """The current advisory regime read (the LAST published label). DERIVED — advisory only.

    Confidence is 0.0 while UNKNOWN (warmup), else 1.0 (a deterministic classifier is categorical;
    a probabilistic HMM drop-in would return a real posterior here).
    """
    series = model.label_series(bars)
    if len(series) == 0:
        return RegimeAssessment(RegimeLabel.UNKNOWN, 0.0, model.model_id)
    label = RegimeLabel(str(series.iloc[-1]))
    confidence = 0.0 if label is RegimeLabel.UNKNOWN else 1.0
    return RegimeAssessment(label, confidence, model.model_id)
