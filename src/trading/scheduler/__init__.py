"""ARCANE scheduler (Increment 7 PART C) — OFF by default, explicit-enable, RECORD_ONLY.

A thin deterministic RTH-cadence loop that runs the driver ONLY when an operator-written enable
marker is present, and even then stays RECORD_ONLY (never auto-runs unattended toward a real order;
the per-order SUBMIT_GO is a separate, orthogonal operator gate). It ships DORMANT (no cron).
PHI1: no LLM/agent import (in the submit-path AST scan).
"""
