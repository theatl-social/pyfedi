# PieFed Development Makefile

.PHONY: help venv install install-dev test openapi clean dev db-init db-migrate db-upgrade lint lint-python lint-templates

# Default target
help:
	@echo "PieFed Development Commands:"
	@echo "  make venv          - Create virtual environment"
	@echo "  make install       - Install dependencies"
	@echo "  make install-dev   - Install development dependencies"
	@echo "  make dev           - Run development server"
	@echo "  make test          - Run tests"
	@echo "  make openapi       - Generate OpenAPI/Swagger JSON schema"
	@echo "  make db-init       - Initialize database"
	@echo "  make db-migrate    - Create database migration"
	@echo "  make db-upgrade    - Apply database migrations"
	@echo "  make lint          - Run all linting (Python + templates)"
	@echo "  make lint-python   - Run Python code linting only"
	@echo "  make lint-templates - Run template linting only"
	@echo "  make clean         - Clean temporary files"

# Virtual environment setup
venv:
	uv venv
	@echo "✅ Virtual environment created. Activate with: source .venv/bin/activate"

# Install dependencies
install: venv
	source .venv/bin/activate && uv pip install -r requirements.txt
	@echo "✅ Dependencies installed"

# Install development dependencies
install-dev: install
	source .venv/bin/activate && uv pip install -r requirements-dev.txt
	@echo "✅ Development dependencies installed"

# Development server
dev:
	@echo "🚀 Starting development server..."
	source .venv/bin/activate && \
	export SERVER_NAME=localhost && \
	export DATABASE_URL=postgresql://pyfedi:pyfedi@localhost/pyfedi && \
	flask run

# Run tests
test:
	@echo "🧪 Running tests..."
	source .venv/bin/activate && \
	SERVER_NAME=localhost python -m pytest tests/test_field_consistency_simple.py -v

# Generate OpenAPI/Swagger schema
openapi:
	@echo "📋 Generating OpenAPI schema..."
	source .venv/bin/activate && python generate_openapi.py
	@if [ -f openapi.json ]; then \
		echo "📁 Schema saved to: openapi.json"; \
		echo "🌐 View online at: https://editor.swagger.io/ (paste the JSON)"; \
	fi

# Database commands
db-init:
	@echo "🗄️  Initializing database..."
	source .venv/bin/activate && flask init-db

db-migrate:
	@read -p "Migration description: " desc && \
	source .venv/bin/activate && flask db migrate -m "$$desc"

db-upgrade:
	@echo "⬆️  Applying database migrations..."
	source .venv/bin/activate && flask db upgrade

# Linting - run both Python and template linting
lint: lint-python lint-templates
	@echo "✅ All linting completed"

# Python linting
lint-python:
	@echo "🔍 Running Python code linting..."
	source .venv/bin/activate && ruff check .

# Template linting
lint-templates:
	@echo "🔍 Running template linting..."
	@if [ ! -f .venv/bin/djlint ]; then \
		echo "⚠️  djlint not found. Installing development dependencies..."; \
		make install-dev; \
	fi
	source .venv/bin/activate && djlint app/templates --check --lint

# Clean temporary files
clean:
	@echo "🧹 Cleaning temporary files..."
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	rm -f openapi.json
	rm -f temp.db
	@echo "✅ Cleanup completed"