.PHONY: help setup test clean lint run

help:
	@echo "Access Manager Lambda - Available commands:"
	@echo "  make setup       - Create virtual environment and install dependencies"
	@echo "  make test        - Run tests with coverage"
	@echo "  make lint        - Run code style checks"
	@echo "  make clean       - Remove virtual environment and cache files"
	@echo "  make run         - Run the Lambda handler locally with sample event"

setup:
	python3 -m venv .venv
	. .venv/bin/activate && pip install --upgrade pip
	. .venv/bin/activate && pip install -r requirements-dev.txt

test:
	. .venv/bin/activate && pytest tests/ -v --cov=src

lint:
	. .venv/bin/activate && pytest tests/ -v --tb=short

clean:
	rm -rf .venv/
	rm -rf .pytest_cache/
	rm -rf .coverage
	rm -rf htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

run:
	. .venv/bin/activate && python3 -c "from src.lambda_function import lambda_handler; import json; event = {'test': 'data'}; context = type('obj', (object,), {'aws_request_id': 'local-test'})(); print(json.dumps(lambda_handler(event, context), indent=2))"
