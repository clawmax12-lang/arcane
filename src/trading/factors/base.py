"""The FINAL ``AlphaFactor`` — the structural look-ahead defense for the factor layer.

``compute()`` is ``@final``: authors implement only ``_raw(df) -> pd.Series``. After ``_raw``
returns the raw, bar-``t``-aligned signal, the base re-derives EVERY correctness property — input
assertion, finiteness, strictly-trailing rolling-z, zero-variance masking, ``clip[-3,3]``, and the
ONE mandatory ``shift(1)`` so a value at bar ``t`` uses only data ``<= t-1`` — so a buggy or
adversarial ``_raw`` cannot open a look-ahead leak or fabricate a saturated signal. Mirrors
``DataLoader.load()`` / ``PITUniverse.as_of_members()``: one untrusted hook, trusted re-derivation.

Why the explicit guards (the surfaces the registry-wide prefix-stability property MISSES):

* **inf laundering (GUARD B).** An ``inf``-producing ``_raw`` (an unguarded ``x/0`` — amihud on a
  zero-volume bar, a zero-range bar) is *perfectly prefix-stable* (``inf == inf`` compares equal),
  yet ``inf`` survives the rolling-z to finite-looking values and ``inf.clip(-3, 3)`` fabricates a
  saturated ``+/-3`` max-conviction signal. So finiteness is asserted on ``_raw`` BEFORE z-scoring;
  ``inf`` is the failure, ``NaN`` is the honest undefined/warmup marker (CLAUDE.md §4.3).
* **zero-variance fabrication (GUARD C).** A flat trailing window has ``std == 0``; the mask makes
  ``z`` ``NaN`` explicitly instead of relying on the ``0/0 == NaN`` coincidence (a non-zero
  numerator over ``std == 0`` would otherwise be ``+/-inf -> +/-3``).

Reliability is **DERIVED** (§4.3): a factor is advisory and may NEVER gate an order. It is a
read-only property (no settable field to forge); the registry rejects any factor whose reliability
is not DERIVED.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar, Final, final

import numpy as np
import numpy.typing as npt
import pandas as pd

from trading.data.reliability import Reliability
from trading.factors.errors import FactorContractError

_CLIP: Final[float] = 3.0
_REQUIRED_COLUMNS: Final[frozenset[str]] = frozenset({"open", "high", "low", "close", "volume"})


class AlphaFactor(ABC):
    """Abstract factor. Subclasses implement ONLY ``_raw``; ``compute`` is final and structural."""

    #: Unique registry id.
    id: ClassVar[str]
    #: Canonical economic rationale (non-empty).
    rationale: ClassVar[str]
    #: Strictly-trailing z-score lookback.
    z_window: ClassVar[int] = 21
    #: The longest trailing offset ``_raw`` reaches back (drives registry frame-adequacy).
    raw_lookback: ClassVar[int] = 0

    @property
    def reliability(self) -> Reliability:
        """Read-only: a factor is DERIVED (§4.3) — advisory, NEVER gates an order."""
        return Reliability.DERIVED

    def params(self) -> dict[str, int]:
        """The factor's parameterization — the trial-ledger combo key (with ``id`` as ref_id)."""
        return {"z_window": self.z_window, "raw_lookback": self.raw_lookback}

    @final
    def compute(self, df: pd.DataFrame) -> pd.Series:
        self._assert_bar_frame(df)  # STEP 0
        raw = self._raw(df)  # STEP 1 — the SOLE author hook
        values = self._assert_raw_contract(raw, df)  # GUARD A + GUARD B -> validated float64 array
        z = self._trailing_z(values, df.index)  # STEP 4-6 + GUARD C/D
        out = z.clip(-_CLIP, _CLIP).shift(1)  # STEP 8 (clip) + STEP 9 (the ONE mandatory shift)
        return self._finalize(out, df)  # GUARD E

    @abstractmethod
    def _raw(self, df: pd.DataFrame) -> pd.Series:
        """The ONLY author hook: the raw, bar-``t``-aligned signal from trailing/same-bar data.

        MAY use a positive ``.shift(n)`` as a trailing LOOKBACK offset (``close`` n bars ago) but
        MUST NOT add an output-alignment shift — the base owns the single ``shift(1)``. MUST map any
        non-finite division to ``NaN`` via ``.where(denom > 0)`` (never ``.fillna/.ffill/.bfill``,
        which are banned and fabricating). Returns a ``pd.Series`` aligned to ``df.index``.
        """

    # --- structural re-derivation (base-owned; a subclass has no override point) ---

    @staticmethod
    def _assert_bar_frame(df: pd.DataFrame) -> None:
        idx = df.index
        if not isinstance(idx, pd.DatetimeIndex) or idx.tz is None or str(idx.tz) != "UTC":
            tz = getattr(idx, "tz", None)
            raise FactorContractError(f"factor input index must be tz-aware UTC, got tz={tz!r}")
        if not idx.is_monotonic_increasing or not idx.is_unique:
            raise FactorContractError("factor input index must be monotonic-increasing and unique")
        missing = _REQUIRED_COLUMNS - set(df.columns)
        if missing:
            raise FactorContractError(f"factor input missing required columns: {sorted(missing)}")

    def _assert_raw_contract(self, raw: object, df: pd.DataFrame) -> npt.NDArray[np.float64]:
        # GUARD A — type / shape / INDEX EQUALITY (a reindexed correct-length Series is a silent
        # time-misalignment leak; length alone is not enough).
        if not isinstance(raw, pd.Series):
            raise FactorContractError(
                f"{self.id}._raw must return a pd.Series, got {type(raw).__name__}"
            )
        if len(raw) != len(df) or not raw.index.equals(df.index):
            raise FactorContractError(f"{self.id}._raw output is not aligned to the bar index")
        # GUARD B — finiteness BEFORE z-scoring. inf is the failure; NaN is allowed (honest hole).
        try:
            values: npt.NDArray[np.float64] = raw.to_numpy(dtype="float64", na_value=np.nan)
        except (ValueError, TypeError) as exc:
            raise FactorContractError(f"{self.id}._raw output is not numeric: {exc}") from exc
        if bool(np.isinf(values).any()):
            raise FactorContractError(
                f"{self.id}._raw produced non-finite (inf) values; map divisions to NaN via "
                ".where(denom > 0) — a PIT hole must stay a hole, never a fabricated extreme"
            )
        return values

    def _trailing_z(self, values: npt.NDArray[np.float64], index: pd.Index) -> pd.Series:
        w = self.z_window
        s = pd.Series(values, index=index, dtype="float64")
        # min_periods == window: a partial window is a DIFFERENT statistic on a prefix
        # (prefix-instability); NO center (a centered window straddles future bars).
        mean = s.rolling(w, min_periods=w).mean()
        std = s.rolling(w, min_periods=w).std(ddof=1)  # ddof pinned: a default change can't rescale
        with np.errstate(divide="ignore", invalid="ignore"):
            z = (s - mean) / std
        # GUARD C — zero-variance => NaN, never inf. std > 0 is False where std == 0 OR std is NaN
        # (warmup, already NaN), so the mask only ever turns a would-be inf/NaN into NaN.
        z = z.mask(~(std > 0))
        # GUARD D — belt-and-suspenders: no residual inf survives (NaN allowed).
        if bool(np.isinf(z.to_numpy(dtype="float64", na_value=np.nan)).any()):
            raise FactorContractError(f"{self.id} z-score produced inf after the zero-var mask")
        return z

    def _finalize(self, out: pd.Series, df: pd.DataFrame) -> pd.Series:
        # GUARD E — output contract: the (Series, .id, .compute) shape prefix_stability consumes.
        result = out.astype("float64")
        if len(result) != len(df) or not result.index.equals(df.index):
            raise FactorContractError(f"{self.id} output is not aligned to the input bar index")
        return result
