"""Conservative, turnover-driven cost model (the M3 defense).

Every fill is charged: ``cost_t = total_bps * 1e-4 * |position_t - position_{t-1}|`` (a fraction of
gross capital), with the first bar entering from flat (prior position 0). ``total_bps`` is
``(commission + half_spread + slippage) * cost_scale``. Each component has a hardcoded conservative
FLOOR that config cannot lower (the ``constants.py`` EQUITY_FLOOR idiom: config may only make cost
MORE pessimistic), and ``cost_scale >= 1.0`` so the Inc-5 2x/3x stress handle can only RAISE cost,
never make a fill cheaper than the ~6 bps floor. Over-stating cost can only KILL a marginal edge,
never manufacture one (ADR §0). Market-impact and adverse-selection are EXCLUDED here (the Inc-5
conservative-live-cost veto), not part of the base model.

Turnover is computed with numpy (the prior is shifted explicitly, with the leading bar's prior 0),
so the from-flat entry is charged WITHOUT the leak-lint-banned ``.fillna``. The cost series reads
only the position (already a trailing, prefix-stable series), never a contemporaneous price/volume.
"""

from __future__ import annotations

from typing import Final

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from trading.backtest.errors import CostModelError

#: Conservative floors (bps, one-way) — config may exceed them, never go below (fail-closed).
COMMISSION_FLOOR_BPS: Final[float] = 1.0
HALF_SPREAD_FLOOR_BPS: Final[float] = 3.0
SLIPPAGE_FLOOR_BPS: Final[float] = 2.0
_BPS: Final[float] = 1e-4


class CostModel(BaseModel):
    """Frozen conservative cost model; ``per_bar_cost`` charges every fill on turnover."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: Folded into ``spec_hash`` so a cost change is a new trial (``run`` asserts a match).
    cost_model_id: str = Field(default="conservative_v1", min_length=1)
    commission_bps: float = Field(
        default=COMMISSION_FLOOR_BPS, ge=COMMISSION_FLOOR_BPS, allow_inf_nan=False
    )
    half_spread_bps: float = Field(
        default=HALF_SPREAD_FLOOR_BPS, ge=HALF_SPREAD_FLOOR_BPS, allow_inf_nan=False
    )
    slippage_bps: float = Field(
        default=SLIPPAGE_FLOOR_BPS, ge=SLIPPAGE_FLOOR_BPS, allow_inf_nan=False
    )
    #: >= 1.0 — the Inc-5 stress handle can only RAISE cost; Inc-4 never sets it above 1.0.
    cost_scale: float = Field(default=1.0, ge=1.0, allow_inf_nan=False)

    @property
    def total_bps(self) -> float:
        """Total one-way cost in bps after the (>= 1) stress scale."""
        return (self.commission_bps + self.half_spread_bps + self.slippage_bps) * self.cost_scale

    def per_bar_cost(self, position: pd.Series) -> pd.Series:
        """Per-bar cost (fraction of capital) from |Δposition|; fail-closed on a non-finite pos."""
        values = position.to_numpy(dtype="float64", na_value=np.nan)
        if values.size == 0:
            return pd.Series([], index=position.index, dtype="float64")
        if not bool(np.isfinite(values).all()):
            raise CostModelError(
                "position series must be finite (no NaN/inf) to cost; the engine flattens warmup "
                "NaNs to 0 before costing"
            )
        prior = np.empty_like(values)
        prior[0] = 0.0  # the first bar enters from flat -> its entry is charged
        prior[1:] = values[:-1]
        turnover = np.abs(values - prior)
        cost = self.total_bps * _BPS * turnover
        return pd.Series(cost, index=position.index, dtype="float64")
