#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$project_root/scripts/test.sh"
"$project_root/.venv/bin/python" -m src.gateway.api.export_openapi --check
# The frontend types are generated from that same document, so they drift the
# moment it changes without a regeneration (EXE-01 FE-02).
node "$project_root/frontend/tools/generate-contracts.mjs" --check
