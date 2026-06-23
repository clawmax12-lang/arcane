"""Pure-stdlib standard-normal CDF and inverse-CDF — NO scipy (it is absent by design).

``norm_cdf`` is exact-to-machine-precision via ``math.erf``. ``norm_ppf`` is Acklam's rational
approximation (max rel. error ~1.15e-9) followed by ONE Halley refinement step against the exact
``norm_cdf`` (driving the error to ~machine epsilon). The PPF is FAIL-CLOSED on its domain: a
probability outside the OPEN interval (0, 1), or NaN, RAISES ``BiasGateError`` — it NEVER returns
``±inf``/``nan`` silently (that would fail OPEN into a passing gate, e.g. a DSR deflation hurdle of
``-inf``). These two functions are the statistical backbone of PSR/DSR/SPA.
"""

from __future__ import annotations

import math
from typing import Final

from trading.bias_gate.errors import BiasGateError

_SQRT2: Final[float] = math.sqrt(2.0)

# Acklam (2003) inverse-normal-CDF rational-approximation coefficients.
_A: Final[tuple[float, ...]] = (
    -3.969683028665376e01,
    2.209460984245205e02,
    -2.759285104469687e02,
    1.383577518672690e02,
    -3.066479806614716e01,
    2.506628277459239e00,
)
_B: Final[tuple[float, ...]] = (
    -5.447609879822406e01,
    1.615858368580409e02,
    -1.556989798598866e02,
    6.680131188771972e01,
    -1.328068155288572e01,
)
_C: Final[tuple[float, ...]] = (
    -7.784894002430293e-03,
    -3.223964580411365e-01,
    -2.400758277161838e00,
    -2.549732539343734e00,
    4.374664141464968e00,
    2.938163982698783e00,
)
_D: Final[tuple[float, ...]] = (
    7.784695709041462e-03,
    3.224671290700398e-01,
    2.445134137142996e00,
    3.754408661907416e00,
)
_P_LOW: Final[float] = 0.02425
_P_HIGH: Final[float] = 1.0 - _P_LOW


def norm_cdf(x: float) -> float:
    """Standard-normal CDF Φ(x), exact to machine precision via ``math.erf``."""
    return 0.5 * (1.0 + math.erf(x / _SQRT2))


def _acklam(p: float) -> float:
    """Acklam's rational approximation of Φ⁻¹(p) for p in (0, 1)."""
    if p < _P_LOW:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((_C[0] * q + _C[1]) * q + _C[2]) * q + _C[3]) * q + _C[4]) * q + _C[5]) / (
            (((_D[0] * q + _D[1]) * q + _D[2]) * q + _D[3]) * q + 1.0
        )
    if p <= _P_HIGH:
        q = p - 0.5
        r = q * q
        return (
            (((((_A[0] * r + _A[1]) * r + _A[2]) * r + _A[3]) * r + _A[4]) * r + _A[5])
            * q
            / (((((_B[0] * r + _B[1]) * r + _B[2]) * r + _B[3]) * r + _B[4]) * r + 1.0)
        )
    q = math.sqrt(-2.0 * math.log(1.0 - p))
    return -(((((_C[0] * q + _C[1]) * q + _C[2]) * q + _C[3]) * q + _C[4]) * q + _C[5]) / (
        (((_D[0] * q + _D[1]) * q + _D[2]) * q + _D[3]) * q + 1.0
    )


def norm_ppf(p: float) -> float:
    """Inverse standard-normal CDF Φ⁻¹(p) for p in the OPEN interval (0, 1) — fail-closed.

    A probability of exactly 0 or 1, outside [0, 1], or NaN RAISES ``BiasGateError`` (not ``inf``).
    """
    # NaN-safe domain check: ``not (0 < p < 1)`` is True for NaN (all comparisons are False).
    if not (0.0 < p < 1.0):
        raise BiasGateError(f"norm_ppf domain is the open interval (0, 1); got {p!r}")
    x = _acklam(p)
    # One Halley step against the exact CDF -> ~machine-precision (defends the 1e-9 tail accuracy).
    e = norm_cdf(x) - p
    u = e * math.sqrt(2.0 * math.pi) * math.exp(x * x / 2.0)
    return x - u / (1.0 + x * u / 2.0)
