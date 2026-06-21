"""Deterministic risk core.

Hard rule (CLAUDE.md PHI1 / §7): no LLM or agent code may be imported into this
package. The risk core is pure, deterministic, and fail-closed. An import-guard test
enforces this in later increments.
"""

from __future__ import annotations
