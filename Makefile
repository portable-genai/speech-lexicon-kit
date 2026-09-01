PY ?= .venv/bin/python

.PHONY: help install lock lint format-check typecheck test eval gate clean regenerate-golden

help:
	@echo "install            locked install from requirements-dev.lock, then the project"
	@echo "lock               recompile requirements-dev.lock (needs uv + network)"
	@echo "lint               ruff check"
	@echo "format-check       ruff format --check (ruff pinned exactly in pyproject.toml)"
	@echo "typecheck          mypy --strict over src"
	@echo "test               pytest, excluding integration"
	@echo "eval               the golden replay (scripts/run_replay.py)"
	@echo "gate               the hard gate: all of the above, offline"
	@echo "regenerate-golden  rewrite tests/golden/replay.json (only when intended)"

# The LOCKED install, which is what CI performs, so `make install` and the hosted gate
# agree about versions. An unlocked resolve is an authoring step, not a gate step.
install:
	$(PY) -m pip install -r requirements-dev.lock
	$(PY) -m pip install --no-deps -e .

# Authoring only: needs uv and network. Run after any dependency change and commit it.
lock:
	uv pip compile --quiet --extra dev pyproject.toml -o requirements-dev.lock

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
