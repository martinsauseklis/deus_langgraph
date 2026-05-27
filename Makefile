DEV_LOG=/tmp/langgraph_dev.log

.PHONY: all format lint test tests test_watch integration_tests docker_tests help extended_tests \
        e2e e2e-infra e2e-routing e2e-tools e2e-nodes e2e-flow logs dev dev-logs

# Default target executed when no arguments are given to make.
all: help

# Define a variable for the test file path.
TEST_FILE ?= tests/unit_tests/

test:
	python -m pytest $(TEST_FILE)

integration_tests:
	python -m pytest tests/integration_tests 

test_watch:
	python -m ptw --snapshot-update --now . -- -vv tests/unit_tests

test_profile:
	python -m pytest -vv tests/unit_tests/ --profile-svg

extended_tests:
	python -m pytest --only-extended $(TEST_FILE)


######################
# DEV SERVER
######################

dev:
	langgraph dev --config langgraph_dev.json 2>&1 | tee $(DEV_LOG)

dev-logs:
	tail -100 $(DEV_LOG)

######################
# E2E TESTS
######################

# Tier 1: infrastructure checks — no LLM, no server invocation (~seconds)
e2e-infra:
	python -m pytest tests/e2e/tier1_infra/ -v -s

# Tier 1+2: routing logic — pure Python, no LLM (~seconds)
e2e-routing:
	python -m pytest tests/e2e/tier1_infra/ tests/e2e/tier2_routing/ -v -s

# Tier 1-3: tool execution — no LLM, just tool calls (~10s)
e2e-tools:
	python -m pytest tests/e2e/tier1_infra/ tests/e2e/tier2_routing/ tests/e2e/tier3_tools/ -v -s

# Tier 4: node-level tests — real LLM calls, server must be running (~minutes)
e2e-nodes:
	python -m pytest tests/e2e/tier4_nodes/ -v -s -m e2e_nodes

# Tier 5: full end-to-end flow — real LLM, all services (~minutes)
e2e-flow:
	python -m pytest tests/e2e/tier5_flow/ -v -s -m e2e_flow

# Everything
e2e:
	python -m pytest tests/e2e/ -v -s

# Fetch event log for a thread: make logs T=<thread-id>
logs:
	@python scripts/logs.py $(T)

# List recent threads
logs-recent:
	@python scripts/logs.py --recent

# List recent threads that errored
logs-errors:
	@python scripts/logs.py --recent --errors

######################
# LINTING AND FORMATTING
######################

# Define a variable for Python and notebook files.
PYTHON_FILES=src/
MYPY_CACHE=.mypy_cache
lint format: PYTHON_FILES=.
lint_diff format_diff: PYTHON_FILES=$(shell git diff --name-only --diff-filter=d main | grep -E '\.py$$|\.ipynb$$')
lint_package: PYTHON_FILES=src
lint_tests: PYTHON_FILES=tests
lint_tests: MYPY_CACHE=.mypy_cache_test

lint lint_diff lint_package lint_tests:
	python -m ruff check .
	[ "$(PYTHON_FILES)" = "" ] || python -m ruff format $(PYTHON_FILES) --diff
	[ "$(PYTHON_FILES)" = "" ] || python -m ruff check --select I $(PYTHON_FILES)
	[ "$(PYTHON_FILES)" = "" ] || python -m mypy --strict $(PYTHON_FILES)
	[ "$(PYTHON_FILES)" = "" ] || mkdir -p $(MYPY_CACHE) && python -m mypy --strict $(PYTHON_FILES) --cache-dir $(MYPY_CACHE)

format format_diff:
	ruff format $(PYTHON_FILES)
	ruff check --select I --fix $(PYTHON_FILES)

spell_check:
	codespell --toml pyproject.toml

spell_fix:
	codespell --toml pyproject.toml -w

######################
# HELP
######################

help:
	@echo '----'
	@echo 'format                       - run code formatters'
	@echo 'lint                         - run linters'
	@echo 'test                         - run unit tests'
	@echo 'tests                        - run unit tests'
	@echo 'test TEST_FILE=<test_file>   - run all tests in file'
	@echo 'test_watch                   - run unit tests in watch mode'

