"""ARCANE backtest layer — frozen StrategySpec + the @final walk-forward BacktestEngine.

Increment 4. A sibling layer to the data spine and the factor layer: it JOINS Inc-3 factor signals
to realized returns under a point-in-time, purged + embargoed walk-forward, applies a conservative
cost model, and emits COMPUTE-AND-REPORT-ONLY statistics for the Increment-5 bias gate. It NEVER
gates, approves, or kills a strategy (that is Increment 5). Look-ahead is a test failure (the engine
causality property), not a code-review call.
"""

from __future__ import annotations
