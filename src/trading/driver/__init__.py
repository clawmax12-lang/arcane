"""ARCANE driver (Increment 7 PART C) — the FIRST real caller of the acting path, record-only.

Assembles ``FamilyMember``s from real strategies + a proof-bearing ``UniverseSnapshot``, runs the
backtest, the bias gate, the allocator, and ``run_loop_pass`` — RECORD_ONLY (it never writes the
operator GO marker). With the 4 edgeless toys the gate kills all -> zero grants -> zero submits.
PHI1: no LLM/agent import (this package is in the submit-path AST scan).
"""
