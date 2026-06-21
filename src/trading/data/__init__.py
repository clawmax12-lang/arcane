"""Data ingestion layer.

All external text MUST pass through ``sanitize`` (§4.2) before any agent or LLM sees it.
"""

from __future__ import annotations
