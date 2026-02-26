#!/bin/bash
set -e

echo "Starting CI checks..."

echo "1. Running Linters..."
black --check .
isort --check-only .
flake8 .

echo "2. Running Tests..."
pytest

echo "CI checks passed!"
