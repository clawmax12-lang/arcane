# ARCANE — developer command surface (GNU make). Default target: check.
.DEFAULT_GOAL := check
PY := uv run

.PHONY: setup format lint typecheck test test-cov check inc1 inc2 clean clean-cache

setup:
	uv sync

format:
	$(PY) ruff check --fix src tests
	$(PY) black src tests

lint:
	$(PY) ruff check src tests
	$(PY) black --check src tests

typecheck:
	$(PY) mypy

test:
	$(PY) pytest -q

test-cov:
	$(PY) pytest --cov=trading --cov-report=term-missing

check: lint typecheck test

# Increment 1 gate: the safety spine must clear ALL of these.
inc1:
	$(PY) ruff check src tests
	$(PY) black --check src tests
	$(PY) mypy
	$(PY) pytest --cov=trading --cov-report=term-missing --cov-fail-under=85 -q
	@echo "Increment 1 gate: PASS"

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
	find . -type d -name __pycache__ -prune -exec rm -rf {} +

clean-cache:
	uv cache prune

# Increment 2 gate: the data spine must clear ALL of these.
inc2:
	$(PY) ruff check src tests
	$(PY) black --check src tests
	$(PY) mypy
	$(PY) pytest --cov=trading --cov-report=term-missing --cov-fail-under=85 -q
	@echo "Increment 2 gate: PASS"
