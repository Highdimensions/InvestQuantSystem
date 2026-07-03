VENV_PYTHON := $(if $(wildcard .venv/Scripts/python.exe),.venv/Scripts/python.exe,python)
PYTHON ?= $(VENV_PYTHON)
PYTEST ?= $(PYTHON) -m pytest
export PYTHONPATH := src

.PHONY: test test-contract test-replay-golden test-evaluation-recovery dashboard

test:
	$(PYTEST)

test-contract:
	$(PYTEST) tests/contract

test-replay-golden:
	$(PYTEST) tests/unit/test_market_data_repository_reconciliation.py tests/integration/test_research_pipeline.py

test-evaluation-recovery:
	$(PYTEST) tests/integration/test_research_pipeline.py

dashboard:
	$(PYTHON) -m quant_signal_system.dashboard --market-db reports/dashboard/market.db --signal-db reports/dashboard/signals.db --host 127.0.0.1 --port 8000
