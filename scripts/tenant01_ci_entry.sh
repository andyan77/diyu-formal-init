#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

if [[ "$#" -eq 0 ]]; then
  echo "usage: scripts/tenant01_ci_entry.sh <ci-trigger-command> [args...]" >&2
  exit 2
fi

.venv/bin/python -m src.tool.execution_control verify --action ci >/dev/null
exec "$@"
