# Akasha monorepo — developer convenience targets (Slice 0).
# Docker targets require a local Docker engine (not available inside the
# Emergent sandbox); the validate/smoke/format targets run anywhere.

COMPOSE := docker compose -f infra/docker/docker-compose.yml

.PHONY: help up down logs build validate smoke fmt lint test reset

help:
	@echo "Akasha monorepo — make targets"
	@echo "  make up       - build & start the local stack (Docker Compose)"
	@echo "  make down     - stop the local stack"
	@echo "  make reset    - stop the stack and delete local volumes"
	@echo "  make logs     - tail logs for all services"
	@echo "  make build    - build all service images"
	@echo "  make validate - run the Slice 0 artifact validator (no Docker needed)"
	@echo "  make smoke    - run the smoke test against BASE_URL (default :8080)"
	@echo "  make fmt      - format Python (black+isort) and JS/TS (prettier)"
	@echo "  make lint     - lint Python (ruff)"
	@echo "  make test     - run api unit tests"

up:
	cd infra/docker && cp -n .env.example .env || true
	$(COMPOSE) up --build -d

down:
	$(COMPOSE) down

reset:
	$(COMPOSE) down -v

logs:
	$(COMPOSE) logs -f

build:
	$(COMPOSE) build

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
