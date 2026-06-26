"""The slow-loop LLM transport — a thin httpx Anthropic Messages client (Inc-8 PART A).

Lives OUTSIDE the PHI1 submit-path roots. The API key is read at the HTTP layer only, never passed
into prompt-assembly and never logged. Callers MUST hand it already-§4.2-sanitized text.
"""
