"""ARCANE slow loop — the LLM-advisory agent framework (Increment 8 PART A).

This package is where LLMs ENTER the system. It is deliberately OUTSIDE the PHI1 submit-path roots
(``executor guards bias_gate data notify backtest factors risk regime allocator driver scheduler``):
no acting-path module may import ``trading.slowloop`` (proven static AND dynamic by
``tests/unit/test_inc8_boundary.py``). Agents are least-privilege — they have NO broker access, are
fed ONLY sanitized text (§4.2), and emit a SCHEMA-VALIDATED JSON artifact to ``state/slowloop/``
tagged §4.3 DERIVED/TEXTUAL with explicit confidence. The acting path only ever READS those files;
it never imports the producers. Agent output is ADVISORY/REPORT-ONLY — it can never gate an order,
size, override a cap or the bias gate, or place a trade (ADR §0 / §4.3).
"""
