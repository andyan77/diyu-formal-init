.PHONY: format lint typecheck test golden openapi frontend-lint frontend-typecheck frontend-build frontend-test exe01-gates exev0-gates

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

frontend-lint:
	npm --prefix frontend run lint

frontend-typecheck:
	npm --prefix frontend run typecheck

frontend-build:
	npm --prefix frontend run build

frontend-test:
	npm --prefix frontend run test

# The nine EXE-01 / EXE-01R determinism gates. Self-contained: brings up the
# project's own local PostgreSQL, migrates and seeds it, then runs all nine.
exe01-gates:
	bash scripts/exe01/run_gates.sh

# The three EXE-V0 gates: change surface, the function-budget ratchet and the
# fixed-sample manifest. Pure git, AST and stdlib — no database, no network, so
# unlike exe01-gates there is nothing to bring up first. Each recipe line is its
# own shell, so the first gate to fail stops the target.
exev0-gates:
	.venv/bin/python scripts/exev0/assert_scope.py
	.venv/bin/python scripts/exev0/assert_function_budget.py
	.venv/bin/python scripts/exev0/build_fixed_samples.py --check
