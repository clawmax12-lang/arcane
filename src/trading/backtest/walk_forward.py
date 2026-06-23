"""Purged + embargoed walk-forward splitter (ADR §8 walk-forward 12/3/3).

A pure function over a sorted, unique session ``DatetimeIndex``. It tiles the timeline into folds
with a 12-calendar-month TRAIN, a 3-month OOS TEST, and a 3-month STEP, anchored/expanding (train
always starts at the first session). Between train-end and test-start sits a clean GAP of
``purge_bars`` (the label/holding horizon) plus an EMBARGO of ``ceil(embargo_frac * len(test))``
bars, so no train bar falls within the gap of a test window. Calendar windows map to sessions via
``DateOffset`` comparisons (never raw row counts, never the banned ``resample``).

For Inc-4's NON-fitted deterministic strategies nothing is trained, so purge/embargo prevent no leak
here; they are the standard de-Prado scaffolding for the ADR §8 OOS-fold statistics AND are drop-in
for a future fitted/Inc-5 consumer. The splitter is PREFIX-STABLE: a fold depends only on the first
session and the offsets, so a later session never retroactively changes an earlier fold. The engine
(not the splitter) enforces the registry-derived warmup-adequacy floor.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator

from trading.backtest.errors import WalkForwardError


class WalkForwardConfig(BaseModel):
    """Frozen 12/3/3 walk-forward geometry; purge/embargo explicit (no author-trust constant)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    train_months: int = Field(default=12, ge=1)
    test_months: int = Field(default=3, ge=1)
    step_months: int = Field(default=3, ge=1)
    #: label/holding horizon in bars removed from train-end (H = 1 for Inc-4 close-to-close hold).
    purge_bars: int = Field(default=1, ge=0)
    #: de-Prado embargo as a fraction of the test span (bars), applied on top of the purge.
    embargo_frac: float = Field(default=0.01, ge=0.0, allow_inf_nan=False)

    @model_validator(mode="after")
    def _no_overlapping_test_windows(self) -> WalkForwardConfig:
        """Reject ``step_months < test_months`` — it OVERLAPS consecutive OOS test windows.

        The engine concatenates each ``fold.test`` into the OOS index, so an overlapped session is
        DOUBLE-COUNTED and the OOS edge magnitude is silently inflated (red-team WF-1). Requiring
        ``step >= test`` keeps the OOS test windows disjoint; ``step == test`` (the 12/3/3 default)
        is full, gap-free coverage. (``step > test`` deliberately sub-samples — honest.)
        """
        if self.step_months < self.test_months:
            raise ValueError(
                f"step_months ({self.step_months}) < test_months ({self.test_months}) overlaps "
                "OOS test windows (double-counts sessions); require step_months >= test_months"
            )
        return self


@dataclass(frozen=True, slots=True, eq=False)
class Fold:
    """One walk-forward fold: the train and OOS-test session labels (disjoint, gap-separated)."""

    index: int
    train: pd.DatetimeIndex
    test: pd.DatetimeIndex


def walk_forward_folds(sessions: pd.DatetimeIndex, config: WalkForwardConfig) -> tuple[Fold, ...]:
    """Return the anchored, purged + embargoed walk-forward folds over sessions (fail-closed)."""
    if not isinstance(sessions, pd.DatetimeIndex):
        raise WalkForwardError(f"sessions must be a DatetimeIndex, got {type(sessions).__name__}")
    if len(sessions) == 0:
        raise WalkForwardError("sessions is empty")
    if not sessions.is_monotonic_increasing or not sessions.is_unique:
        raise WalkForwardError("sessions must be monotonic-increasing and unique")

    start = sessions[0]
    last = sessions[-1]
    folds: list[Fold] = []
    i = 0
    while True:
        test_start = start + pd.DateOffset(months=config.train_months + i * config.step_months)
        if test_start > last:
            break
        test_end = test_start + pd.DateOffset(months=config.test_months)
        test_idx = sessions[(sessions >= test_start) & (sessions < test_end)]
        i += 1
        if len(test_idx) == 0:
            continue  # a calendar window with no sessions (e.g. a long market gap) — skip
        embargo_bars = math.ceil(config.embargo_frac * len(test_idx))
        gap = config.purge_bars + embargo_bars
        train_full = sessions[(sessions >= start) & (sessions < test_start)]
        train_idx = train_full[:-gap] if gap > 0 else train_full
        if len(train_idx) == 0:
            continue  # train fully purged away (too little history before this test) — skip
        folds.append(Fold(index=len(folds), train=train_idx, test=test_idx))
    return tuple(folds)
