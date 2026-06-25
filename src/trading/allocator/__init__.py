"""ARCANE allocator (Increment 7 PART C) — survivors-only, within caps, record-only.

Allocates capital ACROSS bias-gate-ACCEPTED survivors by minting ``AllocationGrant`` tokens via the
existing ``AllocationGrant.from_decision`` chokepoint (a killed/forged decision raises). It never
builds an ``OrderIntent``, touches a cap, or calls the broker; zero survivors -> zero allocation ->
zero orders by construction (ADR §0). The regime label may only SUBTRACT consideration, never add a
killed strategy or enlarge a size. PHI1: no LLM/agent import (in the submit-path AST scan).
"""
