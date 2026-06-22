# ARCANE — developer command surface (GNU make). Default target: check.
.DEFAULT_GOAL := check
PY := uv run

.PHONY: setup format lint typecheck test test-cov check inc1 inc2 inc3 leak-lint clean clean-cache

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

# Structural look-ahead guard: AST ban-list over the data AND factor layers (fails loud, exit 1).
# The complementary registry-wide prefix-stability property runs inside the pytest suite below.
leak-lint:
	$(PY) python -m trading.data.leak_lint src/trading/data src/trading/factors

# Increment 2 gate: the data spine must clear ALL of these.
inc2:
	$(PY) ruff check src tests
	$(PY) black --check src tests
	$(PY) python -m trading.data.leak_lint src/trading/data
	$(PY) mypy
	$(PY) pytest --cov=trading --cov-report=term-missing --cov-fail-under=85 -q
	@echo "Increment 2 gate: PASS"

# Increment 3 gate: the alpha-factor layer must clear ALL of these. leak-lint now scans the data
# AND factor layers; the registry-wide prefix-stability (on _raw AND compute) + frame-adequacy run
# inside the pytest suite (tests/unit/test_factor_registry.py).
inc3:
	$(PY) ruff check src tests
	$(PY) black --check src tests
	$(PY) python -m trading.data.leak_lint src/trading/data src/trading/factors
	$(PY) mypy
	$(PY) pytest --cov=trading --cov-report=term-missing --cov-fail-under=85 -q
	@echo "Increment 3 gate: PASS"
