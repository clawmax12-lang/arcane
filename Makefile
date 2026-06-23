# ARCANE — developer command surface (GNU make). Default target: check.
.DEFAULT_GOAL := check
PY := uv run

.PHONY: setup format lint typecheck test test-cov check inc1 inc2 inc3 inc4 inc5 leak-lint clean clean-cache

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

# Increment 4 gate: the strategy + walk-forward-backtest layer must clear ALL of these. leak-lint now
# scans the data AND factor AND backtest layers; the engine causality property (PositionView +
# RealizedView prefix-stability), frame/value-adequacy, and the perfect-foresight off-by-one
# must-fail canary run inside the pytest suite (tests/unit/test_backtest_engine.py).
inc4:
	$(PY) ruff check src tests
	$(PY) black --check src tests
	$(PY) python -m trading.data.leak_lint src/trading/data src/trading/factors src/trading/backtest
	$(PY) mypy
	$(PY) pytest --cov=trading --cov-report=term-missing --cov-fail-under=85 -q
	@echo "Increment 4 gate: PASS"

# Increment 5 gate: the ALL-of bias/kill gate + Telegram notifier must clear ALL of these. leak-lint
# now also scans the bias_gate + notify packages; the ADR-§8 ALL-of composer (DSR/PSR/PBO/SPA + WF),
# the T1 consistency guard, the high-water-mark, and the seal-boundary teeth run inside the pytest
# suite. The Inc-4 backtest AST name-ban still scans ONLY backtest (a teeth test pins that).
inc5:
	$(PY) ruff check src tests
	$(PY) black --check src tests
	$(PY) python -m trading.data.leak_lint src/trading/data src/trading/factors src/trading/backtest src/trading/bias_gate src/trading/notify
	$(PY) mypy
	$(PY) pytest --cov=trading --cov-report=term-missing --cov-fail-under=85 -q
	@echo "Increment 5 gate: PASS"
