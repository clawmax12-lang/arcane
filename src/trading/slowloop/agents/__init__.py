"""The starter slow-loop agents (Inc-8 PART C): news, regime-synth, daily-report.

Each agent is least-privilege (no broker, no acting-path import), §4.2-sanitizes ALL external text
before the LLM sees it, and emits a schema-validated §4.3-tagged ``AgentArtifact`` (TEXTUAL/DERIVED)
The orchestrator (``slowloop.orchestrator``) runs them and fails closed on any malformed output. The
rest of the §1.1 roster is FUTURE.
"""
