# ─────────────────────────────────────────────────────────────────────────────
# OSS RAG Stack — Developer Makefile
# Usage: make <target>   |   make help
# ─────────────────────────────────────────────────────────────────────────────

.DEFAULT_GOAL := help
BACKEND_DIR   := app/backend
BACKEND_PORT  ?= 8001

.PHONY: help up down build restart restart-full logs logs-be logs-fe shell \
        test test-unit test-int eval eval-llm lint format type-check \
        reindex reset-qdrant clean infra-up infra-down

# ── Help ──────────────────────────────────────────────────────────────────────
help: ## Show available commands
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / \
	  {printf "\033[36m%-22s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# ── Stack lifecycle ───────────────────────────────────────────────────────────
up: ## Start all services (detached)
	docker compose up -d

down: ## Stop and remove containers (keeps volumes)
	docker compose down

build: ## Build all Docker images
	docker compose build

restart: ## Rebuild + restart backend only (fastest after code changes)
	docker compose build backend
	docker compose up -d --force-recreate backend

restart-full: ## Rebuild + restart entire stack
	docker compose build
	docker compose up -d --force-recreate

# ── Infra only (useful for local dev outside Docker) ─────────────────────────
infra-up: ## Start infrastructure services only (postgres, qdrant, minio)
	docker compose up -d postgres qdrant minio minio-init

infra-down: ## Stop infrastructure services only
	docker compose stop postgres qdrant minio

# ── Logs ──────────────────────────────────────────────────────────────────────
logs: ## Tail all service logs
	docker compose logs -f

logs-be: ## Tail backend logs
	docker compose logs -f backend

logs-fe: ## Tail frontend logs
	docker compose logs -f frontend

# ── Shell access ──────────────────────────────────────────────────────────────
shell: ## Open a shell in the running backend container
	docker exec -it oss-rag-backend bash

shell-db: ## Open psql inside the postgres container
	docker exec -it oss-rag-postgres psql -U raguser -d ragdb

# ── Tests ─────────────────────────────────────────────────────────────────────
test: ## Run all tests (unit + integration); requires running stack
	cd $(BACKEND_DIR) && pytest tests/ -v --tb=short

test-unit: ## Run unit tests only — no running services needed
	cd $(BACKEND_DIR) && pytest tests/unit/ -v --tb=short -m "not integration"

test-int: ## Run integration tests — requires postgres + qdrant running
	cd $(BACKEND_DIR) && pytest tests/integration/ -v --tb=short -m integration

test-cov: ## Run unit tests with coverage report
	cd $(BACKEND_DIR) && pytest tests/unit/ -v --tb=short \
	  --cov=. --cov-omit="tests/*" --cov-report=term-missing

eval: ## Run retrieval eval (requires qdrant; downloads embedder model ~90MB on first run)
	cd $(BACKEND_DIR) && pytest tests/eval/ -v --tb=short -m eval -k "not answer_quality"

eval-llm: ## Run full eval including LLM-as-judge (requires ANTHROPIC_API_KEY + RUN_EVAL=true)
	cd $(BACKEND_DIR) && RUN_EVAL=true pytest tests/eval/ -v --tb=short -m eval

# ── Code quality ──────────────────────────────────────────────────────────────
lint: ## Run ruff linter
	cd $(BACKEND_DIR) && ruff check .

format: ## Auto-format code with ruff
	cd $(BACKEND_DIR) && ruff format .

lint-check: ## Check formatting without modifying files (used in CI)
	cd $(BACKEND_DIR) && ruff check . && ruff format --check .

# ── Document operations ───────────────────────────────────────────────────────
reindex: ## Re-index a document: make reindex DOC_ID=<uuid>
	@test -n "$(DOC_ID)" || (echo "Usage: make reindex DOC_ID=<document-uuid>" && exit 1)
	curl -sf -X POST http://localhost:$(BACKEND_PORT)/documents/$(DOC_ID)/reindex \
	  | python3 -m json.tool

docs-list: ## List all indexed documents
	curl -sf http://localhost:$(BACKEND_PORT)/documents | python3 -m json.tool

# ── Qdrant operations ─────────────────────────────────────────────────────────
reset-qdrant: ## WARNING: delete Qdrant data volume and restart (requires re-index)
	@echo "⚠️  This will delete ALL vectors. Press Ctrl-C to cancel, Enter to continue."; read _
	docker compose stop qdrant
	docker volume rm open-source-rag_qdrant_data || true
	docker compose up -d qdrant

# ── Cleanup ───────────────────────────────────────────────────────────────────
clean: ## Remove Python cache files and build artifacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	find . -name ".pytest_cache" -type d -exec rm -rf {} + 2>/dev/null || true
	find . -name ".ruff_cache" -type d -exec rm -rf {} + 2>/dev/null || true
	@echo "Clean complete."
