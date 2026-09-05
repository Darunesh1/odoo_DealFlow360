# DealFlow360 - developer entry point.
#
# Docker runs the stateful services (Postgres, Redis). Everything containing
# project code - the API, the Celery worker, the frontend - runs natively so
# edits reload instantly.
#
# Typical first run:
#
#   make install
#   make api          # terminal 1 (starts the containers for you)
#   make worker       # terminal 2
#   make web          # terminal 3

BACKEND  := backend
FRONTEND := frontend
COMPOSE  := docker compose -f $(BACKEND)/docker-compose.yml
PROD     := docker compose -f $(BACKEND)/docker-compose.prod.yml

.DEFAULT_GOAL := help
.PHONY: help env install up wait down logs fresh api worker web test lint prod prod-down

help: ## Show the available commands
	@echo ""
	@echo "  DealFlow360"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'
	@echo ""

env: ## Create backend/.env and frontend/.env from their examples
	@for dir in $(BACKEND) $(FRONTEND); do \
		if [ -f "$$dir/.env" ]; then \
			echo "  kept    $$dir/.env (already exists)"; \
		else \
			cp "$$dir/.env.example" "$$dir/.env"; \
			echo "  created $$dir/.env"; \
		fi; \
	done

install: env ## Create the .env files and install all dependencies
	cd $(BACKEND) && uv sync
	cd $(FRONTEND) && npm install

up: ## Start the Postgres and Redis containers
	@$(COMPOSE) up -d
	@$(MAKE) --no-print-directory wait

wait: ## Block until the containers report healthy
	@printf "waiting for postgres and redis"
	@for i in $$(seq 1 60); do \
		if $(COMPOSE) exec -T db pg_isready -U "$${POSTGRES_USER:-postgres}" >/dev/null 2>&1 \
		&& $(COMPOSE) exec -T redis redis-cli ping >/dev/null 2>&1; then \
			echo " ready"; exit 0; \
		fi; \
		printf "."; sleep 1; \
	done; \
	echo " timed out"; exit 1

down: ## Stop the containers, keeping the data volumes
	$(COMPOSE) down

logs: ## Tail the container logs
	$(COMPOSE) logs -f

load-data: up ## Fill the database with bulk demo data (300 products, 300 customers)
	cd $(BACKEND) && uv run python scripts/generate_load_data.py $(ARGS)

fresh: ## Destroy the data volumes and start again from empty
	$(COMPOSE) down -v
	@$(MAKE) --no-print-directory up

api: up ## Run the FastAPI server on :8000
	cd $(BACKEND) && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

worker: up ## Run the Celery worker
	cd $(BACKEND) && uv run celery -A app.core.celery_app worker --loglevel=info

beat: up ## Run the Celery scheduler (backorders, recurring billing, deal health)
	cd $(BACKEND) && uv run celery -A app.core.celery_app beat --loglevel=info

web: ## Run the Vite dev server on :5173
	cd $(FRONTEND) && npm run dev

test: up ## Run the backend test suite (make test ARGS="-k auth")
	cd $(BACKEND) && uv run pytest $(ARGS)

lint: ## Lint and typecheck the frontend
	cd $(FRONTEND) && npm run lint && npm run typecheck

prod: ## Run the whole stack in Docker (requires JWT_SECRET_KEY)
	$(PROD) up -d --build

prod-down: ## Stop the full Docker stack
	$(PROD) down
