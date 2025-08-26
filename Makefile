# SoC Validation Test Infrastructure - Makefile

.PHONY: help
help: ## Show this help message
	@echo "SoC Validation Test Infrastructure - Commands"
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'

.PHONY: setup
setup: ## Initial project setup
	@echo "Setting up soc-validation project..."
	cp .env.example .env
	docker-compose build
	@echo "Setup complete! Edit .env file and run 'make up'"

.PHONY: up
up: ## Start all services
	docker-compose up -d
	@echo "Services started. Access Prefect UI at http://localhost:4200"

.PHONY: down
down: ## Stop all services
	docker-compose down

.PHONY: restart
restart: down up ## Restart all services

.PHONY: logs
logs: ## View logs from all services
	docker-compose logs -f

.PHONY: logs-prefect
logs-prefect: ## View Prefect server logs
	docker-compose logs -f prefect

.PHONY: logs-redis
logs-redis: ## View Redis logs
	docker-compose logs -f redis

.PHONY: build
build: ## Build Docker images
	docker-compose build

.PHONY: rebuild
rebuild: ## Rebuild Docker images (no cache)
	docker-compose build --no-cache

.PHONY: shell
shell: ## Open shell in Prefect container
	docker-compose exec prefect /bin/bash

.PHONY: redis-cli
redis-cli: ## Open Redis CLI
	docker-compose exec redis redis-cli

.PHONY: test
test: ## Run all tests
	pytest tests/

.PHONY: test-unit
test-unit: ## Run unit tests
	pytest tests/unit/ -v

.PHONY: test-integration
test-integration: ## Run integration tests
	pytest tests/integration/ -v

.PHONY: test-e2e
test-e2e: ## Run end-to-end tests
	pytest tests/e2e/ -v

.PHONY: test-coverage
test-coverage: ## Run tests with coverage report
	pytest --cov=src --cov-report=html --cov-report=term

.PHONY: lint
lint: ## Run linting checks
	ruff check src/
	black --check src/

.PHONY: format
format: ## Format code
	black src/
	ruff check --fix src/

.PHONY: type-check
type-check: ## Run type checking
	mypy src/

.PHONY: clean
clean: ## Clean up generated files
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name ".coverage" -delete
	rm -rf htmlcov/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .ruff_cache/
	rm -rf dist/
	rm -rf build/
	rm -rf *.egg-info

.PHONY: clean-data
clean-data: ## Clean runtime data (careful!)
	rm -rf data/artifacts/*
	rm -rf data/logs/*
	@echo "Runtime data cleaned. Database files preserved."

.PHONY: install
install: ## Install Python dependencies
	pip install -r requirements.txt
	pre-commit install

.PHONY: install-docker-compose
install-docker-compose: ## Install Docker Compose v1.29.2
	@echo "Installing Docker Compose v1.29.2..."
	@# Remove any older/other Compose installs to avoid confusion
	@sudo apt-get remove -y docker-compose 2>/dev/null || true
	@sudo rm -f /usr/local/bin/docker-compose 2>/dev/null || true
	@# Download the exact v1.29.2 binary
	@sudo curl -L "https://github.com/docker/compose/releases/download/1.29.2/docker-compose-$$(uname -s)-$$(uname -m)" \
		-o /usr/local/bin/docker-compose
	@# Make it executable
	@sudo chmod +x /usr/local/bin/docker-compose
	@# Verify installation
	@echo "Docker Compose installed successfully:"
	@docker-compose version

.PHONY: prefect-ui
prefect-ui: ## Open Prefect UI in browser
	open http://localhost:4200 || xdg-open http://localhost:4200

.PHONY: api-docs
api-docs: ## Open API documentation
	open http://localhost:8000/docs || xdg-open http://localhost:8000/docs

.PHONY: health-check
health-check: ## Check service health
	@echo "Checking Prefect Server..."
	@curl -s http://localhost:4200/api/health | jq '.' || echo "Prefect Server not responding"
	@echo ""
	@echo "Checking Device Manager API..."
	@curl -s http://localhost:8000/api/health | jq '.' || echo "Device Manager not responding"
	@echo ""
	@echo "Checking Redis..."
	@docker-compose exec redis redis-cli ping || echo "Redis not responding"

.PHONY: create-work-pool
create-work-pool: ## Create default Prefect work pool
	docker-compose exec prefect python scripts/setup_queue.py

.PHONY: submit-test
submit-test: ## Submit a test job (example)
	curl -X POST http://localhost:8000/api/v1/tests \
		-H "Content-Type: application/json" \
		-d '{"test_binary": "/path/to/test", "board_family": "socA", "priority": 2}'

.PHONY: dev
dev: up logs ## Start services and tail logs

.PHONY: backup
backup: ## Backup data directories
	tar -czf backup-$(shell date +%Y%m%d-%H%M%S).tar.gz data/

.PHONY: docs
docs: ## Generate documentation
	@echo "Generating documentation..."
	# Add documentation generation commands here

.PHONY: version
version: ## Show version information
	@echo "SoC Validation Test Infrastructure v0.1.0"
	@echo "Python: 3.12+"
	@echo "Prefect: 3.0.0"
	@echo "FastAPI: 0.109.0"
	@echo "Redis: 7.4"