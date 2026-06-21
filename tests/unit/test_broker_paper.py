"""Tests for the paper broker adapter (Increment 1 safety spine)."""

from __future__ import annotations

import ast
import inspect

import pytest

from trading.executor import broker_paper
from trading.executor.broker_paper import ALPACA_PAPER, PaperBroker


def test_alpaca_paper_constant_is_true() -> None:
    assert ALPACA_PAPER is True


def test_broker_is_paper() -> None:
    assert PaperBroker().paper is True


def test_submit_is_stub_until_increment_2() -> None:
    with pytest.raises(NotImplementedError):
        PaperBroker().submit("arcane-abc")


def test_alpaca_paper_literal_is_true_in_source() -> None:
    # AST check (ignores docstrings/comments): the constant must literally be True.
    tree = ast.parse(inspect.getsource(broker_paper))
    found = False
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "ALPACA_PAPER"
        ):
            assert isinstance(node.value, ast.Constant) and node.value.value is True
            found = True
    assert found, "ALPACA_PAPER constant assignment not found in source"
