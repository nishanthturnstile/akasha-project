# Akasha monorepo — developer convenience targets (Slice 0).
# Docker targets require a local Docker engine (not available inside the
# Emergent sandbox); the validate/smoke/format targets run anywhere.

COMPOSE := docker compose -f infra/docker/docker-compose.yml
COMPOSE_DEV := docker compose -f infra/docker/docker-compose.yml -f infra/docker/docker-compose.dev.yml

.PHONY: help dev backend frontend backend-rebuild backend-logs up down logs build validate smoke fmt lint test reset db-upgrade db-current db-heads db-check db-revision db-merge-heads

help:
	@echo "Akasha monorepo — make targets"
	@echo "  make dev      - start Docker backend + hot-reload Vite frontend"
	@echo "  make backend  - start Docker backend/gateway with FastAPI hot reload"
	@echo "  make frontend - start only the hot-reload Vite frontend (backend must be running)"
	@echo "  make up       - start/prepare Docker backend + gateway only"
	@echo "  make down     - stop the local stack"
	@echo "  make reset    - stop the stack and delete local volumes"
	@echo "  make logs     - tail logs for all services"
	@echo "  make backend-logs - tail only API backend logs"
	@echo "  make backend-rebuild - rebuild API image after dependency/Dockerfile changes"
	@echo "  make build    - build all service images"
	@echo "  make validate - run the Slice 0 artifact validator (no Docker needed)"
	@echo "  make smoke    - run the smoke test against BASE_URL (default :8080)"
	@echo "  make fmt      - format Python (black+isort) and JS/TS (prettier)"
	@echo "  make lint     - lint Python (ruff)"
	@echo "  make test     - run api unit tests"
	@echo "  make db-revision MSG='add thing' - create an Alembic revision in the API container"
	@echo "  make db-upgrade/db-current/db-heads/db-check - app-schema migration helpers"

dev:
	bash scripts/dev-local.sh

backend:
	bash scripts/dev-local.sh --backend-only

frontend:
	bash scripts/dev-local.sh --frontend-only

up:
	bash scripts/dev-local.sh --backend-only

down:
	$(COMPOSE_DEV) down

reset:
	$(COMPOSE_DEV) down -v

logs:
	$(COMPOSE_DEV) logs -f

backend-logs:
	$(COMPOSE_DEV) logs -f api

backend-rebuild:
	$(COMPOSE_DEV) build api
	$(COMPOSE_DEV) up -d api web

build:
	$(COMPOSE_DEV) build

db-upgrade:
	$(COMPOSE_DEV) exec -T api python -m app.cli db upgrade

db-current:
	$(COMPOSE_DEV) exec -T api python -m app.cli db current

db-heads:
	$(COMPOSE_DEV) exec -T api python -m app.cli db heads

db-check:
	$(COMPOSE_DEV) exec -T api python -m app.cli db verify-current

db-revision:
	@test -n "$(MSG)" || (echo "Usage: make db-revision MSG='add thing'" && exit 1)
	$(COMPOSE_DEV) exec -T api alembic revision --autogenerate -m "$(MSG)"

db-merge-heads:
	@test -n "$(MSG)" || (echo "Usage: make db-merge-heads MSG='merge heads'" && exit 1)
	$(COMPOSE_DEV) exec -T api alembic merge heads -m "$(MSG)"

validate:
	python scripts/validate_slice0.py

smoke:
	python scripts/smoke-test.py $(BASE_URL)

fmt:
	- black apps/api services/ingestion
	- isort apps/api services/ingestion
	- cd apps/frontend && yarn prettier --write "src/**/*.{ts,tsx,css}" || true

lint:
	- ruff check apps/api services/ingestion

test:
	cd apps/api && python -m pytest -q
