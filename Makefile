.PHONY: run test lint

run:
	uvicorn booking_agent.main:create_app --factory --host 0.0.0.0 --port $${PORT:-8000}

test:
	pytest

lint:
	ruff check .
	ruff format --check .
	mypy
