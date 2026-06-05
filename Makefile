.PHONY: venv install test lint format run status clean

PYTHON := python3.12
VENV := .venv
BIN := $(VENV)/bin

venv:
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install -e ".[dev]"

install:
	$(BIN)/pip install -e ".[dev]"

test:
	$(BIN)/pytest tests/ -v

lint:
	$(BIN)/ruff check argus/

format:
	$(BIN)/ruff format argus/

run:
	$(BIN)/argus run

status:
	$(BIN)/argus status

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	rm -rf build/ dist/
