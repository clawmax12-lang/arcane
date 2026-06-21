"""Increment 2 STEP 0 — the data stack imports and resolves on Python 3.13."""

from __future__ import annotations


def test_data_stack_imports() -> None:
    import alpaca
    import duckdb
    import exchange_calendars
    import pandas as pd
    import pandera
    import pyarrow

    for module in (alpaca, duckdb, exchange_calendars, pandera, pyarrow):
        assert module is not None
    assert pd.__version__.startswith("3"), f"expected pandas 3.x, got {pd.__version__}"
