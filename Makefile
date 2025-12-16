# Makefile for Executive Assistant development
.PHONY: help install test lint format clean deploy

# Default target
help:
	@echo "Executive Assistant Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install          Install development dependencies"
	@echo "  make install-hooks    Install pre-commit hooks"
	@echo ""
	@echo "Development:"
	@echo "  make test             Run unit tests"
	@echo "  make test-cov         Run tests with coverage report"
	@echo "  make lint             Run linters (ruff, mypy)"
	@echo "  make format           Format code with ruff"
	@echo ""
	@echo "Infrastructure:"
	@echo "  make infra-init       Initialize Pulumi stack (first time)"
	@echo "  make infra-preview    Preview infrastructure changes"
	@echo "  make infra-deploy     Deploy infrastructure"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean            Clean build artifacts"

# Install dependencies
install:
	pip install -r requirements-dev.txt

# Install pre-commit hooks
install-hooks:
	pre-commit install

# Run tests
test:
	pytest tests/ -v

# Run tests with coverage
test-cov:
	pytest tests/ -v --cov=exec_assistant --cov-report=html --cov-report=term

# Run integration tests (requires AWS credentials)
test-integ:
	pytest tests_integ/ -v

# Lint code
lint:
	ruff check src/ tests/
	mypy src/

# Format code
format:
	ruff format src/ tests/
	ruff check --fix src/ tests/

# Preview infrastructure changes
infra-preview:
	@command -v pulumi >/dev/null 2>&1 || { echo "Error: pulumi not installed. See infrastructure/README.md"; exit 1; }
	cd infrastructure && pulumi preview

# Deploy infrastructure
infra-deploy:
	@command -v pulumi >/dev/null 2>&1 || { echo "Error: pulumi not installed. See infrastructure/README.md"; exit 1; }
	cd infrastructure && pulumi up

# Initialize Pulumi stack
infra-init:
	@command -v pulumi >/dev/null 2>&1 || { echo "Error: pulumi not installed. Install: curl -fsSL https://get.pulumi.com | sh"; exit 1; }
	cd infrastructure && pulumi stack init dev
	cd infrastructure && pulumi config set aws:region us-east-1
	@echo "✅ Pulumi stack initialized. Set secrets with:"
	@echo "   cd infrastructure && pulumi config set --secret exec-assistant:slack_signing_secret YOUR_SECRET"
	@echo "   cd infrastructure && pulumi config set --secret exec-assistant:slack_bot_token YOUR_TOKEN"

# Clean build artifacts
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name ".coverage" -delete 2>/dev/null || true
	rm -rf build/ dist/

# Run local DynamoDB (for development)
dynamodb-local:
	docker run -p 8000:8000 amazon/dynamodb-local

# Quick check before committing
pre-commit: format lint test
	@echo "✅ All checks passed!"
