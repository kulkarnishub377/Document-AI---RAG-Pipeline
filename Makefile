# ─────────────────────────────────────────────────────────────────────────────
# Makefile — Document AI + RAG Pipeline
# Common shortcuts for development, testing, and deployment
# ─────────────────────────────────────────────────────────────────────────────

.PHONY: help dev test lint format clean docker docker-down install install-dev

# Default target
help: ## Show this help message
	@echo.
	@echo   Document AI + RAG Pipeline v2.0
	@echo   ================================
	@echo.
	@echo   Available commands:
	@echo.
	@echo     make install       Install production dependencies
	@echo     make install-dev   Install production + development dependencies
	@echo     make dev           Start the development server (with reload)
	@echo     make run           Start the production server
	@echo     make test          Run the full test suite
	@echo     make test-cov      Run tests with coverage report
	@echo     make lint          Run Ruff linter
	@echo     make format        Format code with Black
	@echo     make format-check  Check formatting without changes
	@echo     make docker        Build and start with Docker Compose
	@echo     make docker-down   Stop Docker Compose services
	@echo     make clean         Remove caches, build artifacts, temp files
	@echo.

# ── Setup ────────────────────────────────────────────────────────────────────

install: ## Install production dependencies
	pip install --upgrade pip
	pip install -r requirements.txt

install-dev: install ## Install production + dev dependencies
	pip install -e ".[dev]"

# ── Run ──────────────────────────────────────────────────────────────────────

dev: ## Start dev server with auto-reload
	python -m uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload

run: ## Start production server
	python run.py

# ── Testing ──────────────────────────────────────────────────────────────────

test: ## Run all tests
	python -m pytest tests/ -v --tb=short

test-cov: ## Run tests with coverage
	python -m pytest tests/ -v --cov=. --cov-report=term-missing --cov-report=html

# ── Code Quality ─────────────────────────────────────────────────────────────

lint: ## Run Ruff linter
	ruff check .

format: ## Format code with Black
	black .

format-check: ## Check code formatting
	black --check --diff .

# ── Docker ───────────────────────────────────────────────────────────────────

docker: ## Build and start with Docker Compose
	docker-compose up -d --build

docker-down: ## Stop Docker Compose services
	docker-compose down

# ── Cleanup ──────────────────────────────────────────────────────────────────

clean: ## Remove caches, build artifacts, temp files
	if exist __pycache__ rd /s /q __pycache__
	if exist .pytest_cache rd /s /q .pytest_cache
	if exist htmlcov rd /s /q htmlcov
	if exist .coverage del /f .coverage
	if exist build rd /s /q build
	if exist dist rd /s /q dist
	if exist *.egg-info rd /s /q *.egg-info
	for /d /r . %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d"
	@echo Cleaned!
