# Developer entry points (Linux/macOS/CI). Windows: scripts/dev.ps1 has the
# same targets. docs/production-hardening-plan.md H0-D.
PY ?= .venv/bin/python

.PHONY: help install lock up down test test-backend test-agent test-legacy lint typecheck migrate cli

help:
	@echo "install   - install backend + agent runtime deps and dev tooling into .venv, npm ci"
	@echo "lock      - recompile backend/ and agent/ requirements.txt from requirements.in"
	@echo "up        - start the whole stack in Docker (migrate, backend, agent, frontend)"
	@echo "down      - stop it"
	@echo "test      - start postgres-test, run every pytest suite and the frontend tests"
	@echo "lint      - oxlint (frontend)"
	@echo "typecheck - tsc -b (frontend)"
	@echo "migrate   - alembic upgrade head against DATABASE_URL"
	@echo "cli       - python -m backend.cli $(ARGS)   e.g. make cli ARGS=\"finalize-stuck-sessions --dry-run\""

install:
	$(PY) -m pip install -r backend/requirements.txt -r agent/requirements.txt -r requirements-dev.txt
	cd frontend && npm ci

lock:
	$(PY) -m piptools compile --strip-extras --no-header -o backend/requirements.txt backend/requirements.in
	$(PY) -m piptools compile --strip-extras --no-header -o agent/requirements.txt agent/requirements.in

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

lint:
	cd frontend && npx oxlint src

typecheck:
	cd frontend && npm run typecheck

migrate:
	cd backend && ../$(PY) -m alembic upgrade head

cli:
	PYTHONPATH=backend $(PY) -m backend.cli $(ARGS)
