.PHONY: help setup up up-llm down restart logs migrate test lint format cluster health precommit-install precommit llm-up llm-pull llm-check

help:
	@echo "Available targets:"
	@echo "  make setup    - Copy .env.example to .env if missing"
	@echo "  make up       - Build and start docker services"
	@echo "  make up-llm   - Build/start backend + local ollama service"
	@echo "  make down     - Stop docker services"
	@echo "  make restart  - Restart docker services"
	@echo "  make logs     - Tail API logs"
	@echo "  make migrate  - Apply Alembic migrations"
	@echo "  make test     - Run pytest"
	@echo "  make lint     - Run ruff"
	@echo "  make format   - Run black"
	@echo "  make precommit-install - Install git pre-commit hooks"
	@echo "  make precommit - Run all pre-commit hooks"
	@echo "  make cluster  - Run clustering worker"
	@echo "  make health   - Check API health endpoint"
	@echo "  make llm-up   - Start only local ollama service (docker profile)"
	@echo "  make llm-pull MODEL=<name> - Pull a model inside ollama service"
	@echo "  make llm-check MODEL=<name> - Validate local LLM endpoint and model"

setup:
	@test -f .env || cp .env.example .env
	@echo ".env ready"

up:
	docker compose up --build -d

up-llm:
	docker compose --profile local-llm up --build -d

down:
	docker compose down

restart: down up

logs:
	docker compose logs -f api

migrate:
	alembic upgrade head

test:
	pytest

lint:
	ruff check app tests

format:
	black app tests

precommit-install:
	PRE_COMMIT_HOME=/tmp/pre-commit-cache pre-commit install

precommit:
	PRE_COMMIT_HOME=/tmp/pre-commit-cache pre-commit run --all-files

cluster:
	python -m app.workers.cluster_messages

health:
	curl -fsS http://localhost:8000/health

llm-up:
	docker compose --profile local-llm up -d ollama

llm-pull:
	docker compose --profile local-llm exec ollama ollama pull $(or $(MODEL),llama3.1:8b-instruct)

llm-check:
	LOCAL_LLM_MODEL_EXTRACT=$(or $(MODEL),llama3.1:8b-instruct) ./scripts/check_local_llm.sh
