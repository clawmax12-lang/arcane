"""ARCANE regime classifier (Increment 7 PART B) — a lean, deterministic, ADVISORY label.

The regime label is §4.3 DERIVED: it may inform the allocator's POSTURE but can NEVER gate an order,
size a position, or override the bias gate or a cap. It is type-disjoint from every gate/sizing/cap
signature and imports NO LLM/agent module (PHI1 — this package is in the submit-path AST scan). An
LLM-advisory regime synthesis, if ever built, lives in a SEPARATE slow-loop package consumed via a
sanitized ``regime.json`` — never imported here.
"""
