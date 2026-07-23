#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$project_root/scripts/local_postgres.sh"

: "${DIYU_SESSION_SECRET:?请先设置本机 DIYU_SESSION_SECRET；不要把它提交到仓库}"
export DIYU_DEMO_TENANT_ID="00000000-0000-0000-0000-000000000001"
export DIYU_DEMO_USER_ID="00000000-0000-0000-0000-000000000011"
export DIYU_DEMO_BRAND_ID="00000000-0000-0000-0000-000000000021"
export DIYU_DEMO_ACCOUNT_ID="00000000-0000-0000-0000-000000000031"
export DIYU_DEMO_DISPLAY_ORGANIZATION_ID="00000000-0000-0000-0000-000000000012"
export DIYU_DEMO_DISPLAY_USER_ID="00000000-0000-0000-0000-000000000013"
export DIYU_GENERATOR_MODE="${DIYU_GENERATOR_MODE:-stub}"

"$project_root/.venv/bin/python" -m alembic upgrade head
"$project_root/.venv/bin/python" -m src.infrastructure.seed_demo
"$project_root/.venv/bin/python" -m src.infrastructure.system_asset_catalog
exec "$project_root/.venv/bin/python" -m uvicorn src.gateway.api.app:create_app --factory --host 127.0.0.1 --port "${DIYU_APP_PORT:-8000}"
