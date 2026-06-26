"""ARCANE two-way Telegram operator console (Increment 8 PART B).

The headline feature: the operator talks to his trader from his phone. He asks GENERAL questions
("hur går det?", "har du läst nyheterna inatt?", "vad dödade gaten idag?") and occasionally issues
an operator-authority STOP ("/pausa", "/flatta"). He never gives buy/sell orders — and the system
can never accept one.

This package is OUTSIDE the PHI1 submit-path roots (proven static AND dynamic by
``tests/unit/test_inc8_boundary.py``). The HARD boundary:
  * input is accepted ONLY from the operator's ``TELEGRAM_CHAT_ID`` (auth + update-shape whitelist);
  * every inbound message is §4.2-sanitized before any LLM sees it;
  * command dispatch is DETERMINISTIC string matching on a frozen allow-list — never the LLM
    deciding to act. The LLM reply is TEXT ONLY: there is no parser turning it into an action;
  * acting commands map ONLY to the EXISTING deterministic ``kill_switch`` escalate methods
    (trip/hard_stop) — NEVER re-arm (§7), NEVER a broker write;
  * a trade order ("köp AAPL") is refused deterministically, naming the gate->GO path.
"""
