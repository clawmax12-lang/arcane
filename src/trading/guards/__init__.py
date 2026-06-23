"""Murphy guards (CLAUDE.md §5) — deterministic defenses against the UNKNOWN (Increment 6 PART B).

The mistake ledger handles KNOWN failure categories; the guards here handle the rest — data
staleness,
fill delay, reconciliation drift, broker/LLM heartbeat loss, time drift, equity-velocity
spikes, order
bursts, correlation spikes, prompt-injection floods — plus the §8 abandonment evaluator and the §5.2
operator paging-latency escalation. Every guard is a PURE deterministic function over injected
HARD/STRUCTURED state; the kill-switch + notifier are mutated in ONE place (``panel.apply_guards`` /
``abandonment.engage_abandonment``). No LLM is imported anywhere in this package (PHI1).
"""
