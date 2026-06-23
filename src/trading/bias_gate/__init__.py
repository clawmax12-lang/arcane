"""ARCANE Increment 5 — the ALL-of bias/kill gate.

This is the FIRST place in ARCANE that emits an accept/kill VERDICT, built on the sealed Inc-4
verdict-free ``BacktestResult``. The bias-gate symbols (deflated / dsr / pbo / psr / reality_check /
allocated / accept / approve / kill / verdict / passed) are banned in ``src/trading/backtest`` by an
AST name-ban and become LEGAL **only** here. The gate consumes ONLY public Inc-4 surfaces — it adds
no field to ``BacktestResult`` and touches no Inc-4 source.

THE GATE'S JOB IS TO SAY NO (ADR §0): ARCANE is an edge-falsification harness; accepting ZERO
survivors is a SUCCESS. Every estimator fails CLOSED — any NaN/ruin/degenerate/under-sample input is
a KILL, never a pass. See ``docs/INCREMENT-5-DESIGN.md``.
"""

from __future__ import annotations
