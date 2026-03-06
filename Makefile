.PHONY: install run-all stop clean lint test test-cov help precommit-install precommit-run git-stage git-commit

help:
	@echo "Available commands:"
	@echo "  install   : Install dependencies locally"
	@echo "  run-all   : Start all services using Docker Compose"
	@echo "  stop      : Stop all services"
	@echo "  clean     : Remove temporary files and containers"
	@echo "  lint              : Run ruff lint + format check"
	@echo "  precommit-install : Install pre-commit hooks"
	@echo "  precommit-run     : Run pre-commit on all files"
	@echo "  test      : Run tests"
	@echo "  test-cov  : Run tests with coverage report"
	@echo "  demo      : Run E2E demo (requires Docker)"
	@echo "  dashboard : Run dashboard locally (port 8005)"
	@echo "  release-check : Run all pre-release validations"
	@echo "  git-stage : Stage all modified files (prevents 'unstaged' issues)"
	@echo "  git-commit MSG=<msg> : Stage all changes and commit with message"

release-check:
	@echo "Running Release Validation..."
	$(MAKE) test
	@echo "Checking Database Migrations..."
	alembic check
	@echo "Running Smoke Test..."
	python scripts/smoke_test.py
	@echo "Verifying Artifacts..."
	@if [ ! -d logs ]; then mkdir logs; fi
	@if [ ! -d backups ]; then mkdir backups; fi
	@echo "Release check PASSED."

install:
	pip install -r requirements.txt
	pre-commit install

run-all:
	docker-compose up --build -d

stop:
	docker-compose down

clean:
	docker-compose down -v --remove-orphans
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

lint:
	ruff check .
	ruff format --check .

precommit-install:
	pip install pre-commit
	pre-commit install

precommit-run:
	pre-commit run --all-files

git-stage:
	@echo "Staging all modified files..."
	git add .
	@echo "All changes staged. Status:"
	git status

git-commit:
	@if [ -z "$(MSG)" ]; then echo "Error: MSG required. Usage: make git-commit MSG='your message'"; exit 1; fi
	@echo "Staging all changes..."
	git add .
	@echo "Committing with message: $(MSG)"
	git commit -m "$(MSG)"

test:
	pytest

test-cov:
	pytest --cov=shared --cov=services --cov-report=term-missing --cov-report=html

db-init:
	alembic revision --autogenerate -m "Initial migration"

migrate:
	alembic upgrade head

cli-packets:
	python infra/cli.py list-packets

cli-runs:
	python infra/cli.py list-runs

tech-scan:
	python services/technical/replay.py scan

demo: run-all
	@echo "Waiting for services to start..."
	@sleep 10
	python scripts/v1_demo/demo.py
	@echo "Demo complete. Open dashboard: http://localhost:8005/dashboard"

dashboard:
	python services/dashboard/main.py

orchestrate:
	python services/orchestration/main.py


precommit-install:
	pre-commit install

precommit-run:
	pre-commit run --all-files
