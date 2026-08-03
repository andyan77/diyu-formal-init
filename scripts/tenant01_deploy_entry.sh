#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

if [[ "$#" -eq 0 ]]; then
  echo "usage: scripts/tenant01_deploy_entry.sh <deploy-command> [args...]" >&2
  exit 2
fi

.venv/bin/python -m src.tool.execution_control verify --action deploy >/dev/null
exec "$@"
