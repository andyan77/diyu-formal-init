#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$project_root/scripts/local_postgres.sh"
export DIYU_SESSION_SECRET="local-test-session-secret"
export DIYU_DEMO_TENANT_ID="00000000-0000-0000-0000-000000000001"
export DIYU_DEMO_USER_ID="00000000-0000-0000-0000-000000000011"
export DIYU_DEMO_BRAND_ID="00000000-0000-0000-0000-000000000021"
export DIYU_DEMO_ACCOUNT_ID="00000000-0000-0000-0000-000000000031"
export DIYU_GENERATOR_MODE="stub"
export TMPDIR="$project_root/var/tmp"
export TEMP="$TMPDIR"
export TMP="$TMPDIR"
mkdir -p "$TMPDIR"
"$project_root/.venv/bin/python" -m alembic upgrade head
"$project_root/.venv/bin/python" -m src.infrastructure.seed_demo
"$project_root/.venv/bin/python" -m src.infrastructure.system_asset_catalog
"$project_root/.venv/bin/python" -m pytest
