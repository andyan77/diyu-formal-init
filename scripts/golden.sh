#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$project_root/scripts/test.sh"
"$project_root/.venv/bin/python" -m src.gateway.api.export_openapi --check
