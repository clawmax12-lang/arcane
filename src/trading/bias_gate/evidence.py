"""Evidence helpers — tripwire A3 (re-derived purge floor) + (C5) the OOS-series assembler.

A3: a leak-sensitive consumer must purge ``>= max_total_window + label_horizon``, re-derived from
the strategy's OWN bound factors (never an author-declared constant — the registry-2 lesson).
``required_purge_bars`` reuses the public Inc-4 ``strategy_warmup`` (deepest factor pipeline) and
``assert_purge_adequate`` fails closed if a ``WalkForwardConfig`` under-purges. The impure OOS
assembler + the T1 consistency guard are added in cluster C5 (this module is extended, not forked).
"""

from __future__ import annotations

from trading.backtest.engine import strategy_warmup
from trading.backtest.resolve import ResolvedStrategy
from trading.backtest.walk_forward import WalkForwardConfig
from trading.bias_gate.errors import PurgeUnderspecifiedError


def required_purge_bars(strategy: ResolvedStrategy, *, label_horizon: int = 1) -> int:
    """The purge floor = deepest factor pipeline (``strategy_warmup``) + the label/holding horizon.

    ``label_horizon`` is an EXPLICIT gate parameter (close-to-close ⇒ 1), never read from the spec.
    A horizon below 1 is degenerate and fails closed.
    """
    if label_horizon < 1:
        raise PurgeUnderspecifiedError(
            f"label_horizon must be >= 1 (a holding horizon), got {label_horizon}"
        )
    return strategy_warmup(strategy) + label_horizon


def assert_purge_adequate(
    folds: WalkForwardConfig, strategy: ResolvedStrategy, *, label_horizon: int = 1
) -> int:
    """Return the required purge if ``folds.purge_bars`` meets it; else raise (fail closed).

    ``<`` (not ``!=``) so a deliberately LARGER purge (more conservative) is allowed; only an
    UNDER-purge fails closed.
    """
    need = required_purge_bars(strategy, label_horizon=label_horizon)
    if folds.purge_bars < need:
        raise PurgeUnderspecifiedError(
            f"WalkForwardConfig.purge_bars={folds.purge_bars} < required {need} = "
            f"warmup({strategy_warmup(strategy)}) + label_horizon({label_horizon}); a "
            "leak-sensitive consumer must purge >= the deepest factor pipeline + holding horizon"
        )
    return need
