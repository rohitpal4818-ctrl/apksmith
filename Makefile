# Common tasks. `make` alone lists them.

PYTHON ?= python
VENV   ?= .venv
BIN     = $(VENV)/Scripts/python
POSIX  ?= 0

ifeq ($(OS),Windows_NT)
BIN     = $(VENV)/Scripts/python
else
BIN     = $(VENV)/bin/python
endif

SAMPLE := samples/F-Droid.apk

.DEFAULT_GOAL := help
.PHONY: help setup fetch test lint format check scan generate evaluate mcp clean all

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

setup:  ## Create the venv and install everything
	$(PYTHON) -m venv $(VENV)
	$(BIN) -m pip install --upgrade pip
	$(BIN) -m pip install -e ".[dev]"

fetch: $(SAMPLE)  ## Download the sample APK

$(SAMPLE):
	@echo "downloading F-Droid.apk ..."
	curl -L --fail --progress-bar https://f-droid.org/F-Droid.apk -o $(SAMPLE)

test:  ## Run the test suite
	$(BIN) -m pytest

lint:  ## Check formatting, lint rules, docs and docstrings
	$(BIN) -m ruff check src tests scripts
	$(BIN) -m ruff format --check src tests scripts
	$(BIN) scripts/check_docs.py
	$(BIN) scripts/check_docstrings.py

format:  ## Apply formatting and safe fixes
	$(BIN) -m ruff check src tests scripts --fix
	$(BIN) -m ruff format src tests scripts

check: lint test  ## Everything CI runs

scan:  ## Static analysis of the sample APK
	$(BIN) -m apksmith scan $(SAMPLE)

generate:  ## Generate a project from the bundled example spec
	$(BIN) -m apksmith generate run evaluation/example_spec.json --out build/recon

evaluate:  ## Run the evaluation suite
	$(BIN) -m apksmith evaluate run evaluation/suite.json

understand:  ## Full pipeline on the sample APK. Needs OPENROUTER_API_KEY.
	$(BIN) -m apksmith understand run $(SAMPLE) --json reports/fdroid.json

mcp:  ## Run the MCP server on stdio. Needs the mcp package.
	$(BIN) -m apksmith.mcp_server

clean:  ## Remove caches and build output
	rm -rf build dist .pytest_cache .ruff_cache .apksmith-cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +

all: check  ## Everything that must pass before pushing