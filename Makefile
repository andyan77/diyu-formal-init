.PHONY: format lint typecheck test golden openapi

format:
	.venv/bin/python -m ruff format src tests alembic

lint:
	.venv/bin/python -m ruff check src tests alembic

typecheck:
	.venv/bin/python -m mypy src tests

test:
	scripts/test.sh

golden:
	scripts/golden.sh

openapi:
	bash -c 'source scripts/test.sh && .venv/bin/python -m src.gateway.api.export_openapi'
