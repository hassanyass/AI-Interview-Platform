# Developer entry points (Linux/macOS/CI). Windows: scripts/dev.ps1 has the
# same targets. docs/production-hardening-plan.md H0-D.
PY ?= .venv/bin/python

.PHONY: help install lock up down test test-backend test-agent test-legacy lint lint-py typecheck hooks ci migrate cli docs load-baseline

help:
	@echo "install   - install backend + agent runtime deps and dev tooling into .venv, npm ci"
	@echo "lock      - recompile backend/ and agent/ requirements.txt from requirements.in"
	@echo "up        - start the whole stack in Docker (migrate, backend, agent, frontend)"
	@echo "down      - stop it"
	@echo "test      - start postgres-test, run every pytest suite and the frontend tests"
	@echo "lint      - oxlint (frontend)"
	@echo "lint-py   - ruff check (backend + agent)"
	@echo "hooks     - install the pre-commit git hook"
	@echo "ci        - everything CI runs, locally: lint-py, lint, typecheck, tests"
	@echo "typecheck - tsc -b (frontend)"
	@echo "migrate   - alembic upgrade head against DATABASE_URL"
	@echo "cli       - python -m backend.cli $(ARGS)   e.g. make cli ARGS=\"finalize-stuck-sessions --dry-run\""
	@echo "docs      - regenerate the env matrix and the data model from the code"
	@echo "load-baseline - measure the HTTP layer against the disposable DB (docs/handover/capacity.md)"

install:
	$(PY) -m pip install -r backend/requirements.txt -r agent/requirements.txt -r requirements-dev.txt
	cd frontend && npm ci

# The two locks are installed into ONE environment -- the test suite imports
# both packages -- so their shared transitive dependencies must agree. They
# used to be compiled independently, which let 11 of them drift apart until
# `pip install -r backend -r agent` was impossible (found by CI's first real
# run, 2026-09-25). The agent is compiled first because livekit-agents
# carries the tighter bounds, then the backend is constrained by its result.
# `lock` RE-RESOLVES: pip-compile preserves versions already pinned in the
# output file, so this picks up changes to the .in files and nothing else.
# It will NOT pull newer releases -- that is `upgrade` below. Mistaking one
# for the other is how a lock sits still for months while advisories pile
# up against it.
lock:
	$(PY) -m piptools compile --strip-extras --no-header -o agent/requirements.txt agent/requirements.in
	$(PY) -m piptools compile --strip-extras --no-header -c agent/requirements.txt -o backend/requirements.txt backend/requirements.in
	$(PY) -m pytest -q backend/tests/test_requirements.py

# `upgrade` pulls the newest releases the .in files allow (pip-compile -U).
# Backend only by default: the agent lock carries livekit-agents and `av`,
# whose behaviour no test here can verify -- the agent suite runs against
# fakes with no LiveKit server -- so bumping them needs a real spoken
# interview afterwards. Do that deliberately, with:
#   make upgrade-agent
upgrade:
	$(PY) -m piptools compile --upgrade --strip-extras --no-header -c agent/requirements.txt -o backend/requirements.txt backend/requirements.in
	$(PY) -m pytest -q backend/tests/test_requirements.py

upgrade-agent:
	$(PY) -m piptools compile --upgrade --strip-extras --no-header -o agent/requirements.txt agent/requirements.in
	$(PY) -m piptools compile --strip-extras --no-header -c agent/requirements.txt -o backend/requirements.txt backend/requirements.in
	$(PY) -m pytest -q backend/tests/test_requirements.py

up:
	docker compose --profile app up --build

down:
	docker compose --profile app down

test: test-db
	$(PY) -m pytest -q
	cd frontend && npm test

test-db:
	docker compose up -d --wait postgres-test

test-backend: test-db
	$(PY) -m pytest -q backend/tests

test-agent:
	$(PY) -m pytest -q agent

test-legacy: test-db
	$(PY) -m pytest -q tests/legacy

lint-py:
	$(PY) -m ruff check .

hooks:
	$(PY) -m pre_commit install

# The same gates as .github/workflows/ci.yml, in the same order.
ci: lint-py test-db
	$(PY) -m pytest -q --cov=backend/backend --cov=agent/agent --cov-report=term-missing:skip-covered
	cd frontend && npm run typecheck && npm run lint && npm test && npm run build:only

lint:
	cd frontend && npx oxlint src

typecheck:
	cd frontend && npm run typecheck

migrate:
	cd backend && ../$(PY) -m alembic upgrade head

cli:
	PYTHONPATH=backend $(PY) -m backend.cli $(ARGS)

docs:
	$(PY) scripts/generate_docs.py

# Measures the HTTP layer only, against the disposable database, with
# recordings and rate limits off. docs/handover/capacity.md explains what
# the numbers are worth -- read it before quoting them.
load-baseline: test-db
	@echo ">> starting a backend on :8002 against the disposable database"
	@cd backend && DATABASE_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/himma_test \
		RATE_LIMIT_ENABLED=false R2_ENDPOINT= R2_ACCOUNT_ID= R2_ACCESS_KEY_ID= \
		R2_SECRET_ACCESS_KEY= R2_BUCKET_NAME= TASK_WORKER_ENABLED=false \
		../$(PY) -m uvicorn backend.main:app --host 127.0.0.1 --port 8002 --log-level warning & \
		echo $$! > /tmp/load-baseline.pid
	@sleep 12
	-$(PY) scripts/load_baseline.py --base-url http://127.0.0.1:8002
	@kill `cat /tmp/load-baseline.pid` 2>/dev/null || true
