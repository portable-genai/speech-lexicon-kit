PY ?= .venv/bin/python

.PHONY: help install lint format-check typecheck test eval gate clean regenerate-golden

help:
	@echo "install            install the package with its dev extra (editable)"
	@echo "lint               ruff check"
	@echo "format-check       ruff format --check (ruff pinned exactly in pyproject.toml)"
	@echo "typecheck          mypy --strict over src"
	@echo "test               pytest, excluding integration"
	@echo "eval               the golden replay (scripts/run_replay.py)"
	@echo "gate               the hard gate: all of the above, offline"
	@echo "regenerate-golden  rewrite tests/golden/replay.json (only when intended)"

install:
	$(PY) -m pip install -e ".[dev]"

lint:
	$(PY) -m ruff check src tests scripts

format-check:
	$(PY) -m ruff format --check src tests scripts

typecheck:
	$(PY) -m mypy src

test:
	$(PY) -m pytest -m 'not integration'

eval:
	$(PY) scripts/run_replay.py

# The hard gate. Everything here runs offline: the package has no runtime dependency, no
# network call and no clock, so a green gate on a disconnected host means the same thing as
# a green gate anywhere else.
gate: lint format-check typecheck test eval
	@echo "GATE: PASS"

regenerate-golden:
	$(PY) scripts/run_replay.py --regenerate

clean:
	rm -rf .mypy_cache .pytest_cache .ruff_cache build dist
