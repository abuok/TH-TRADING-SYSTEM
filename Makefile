.PHONY: install run-all stop clean lint test help

help:
	@echo "Available commands:"
	@echo "  install   : Install dependencies locally"
	@echo "  run-all   : Start all services using Docker Compose"
	@echo "  stop      : Stop all services"
	@echo "  clean     : Remove temporary files and containers"
	@echo "  lint      : Run linters (black, isort, flake8)"
	@echo "  test      : Run tests"
	@echo "  demo      : Run E2E demo (requires Docker)"
	@echo "  dashboard : Run dashboard locally (port 8005)"

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
	black .
	isort .
	flake8 .

test:
	pytest

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
	python services/orchestration/demo.py
	@echo "Demo complete. Open dashboard: http://localhost:8005/dashboard"

dashboard:
	python services/dashboard/main.py

orchestrate:
	python services/orchestration/main.py
