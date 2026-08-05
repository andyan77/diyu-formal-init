#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

if [[ "$#" -eq 0 ]]; then
  echo "usage: scripts/tenant01_deploy_entry.sh [--action production_readonly|backup|deploy|rollback|cleanup] <command> [args...]" >&2
  exit 2
fi

action="deploy"
if [[ "${1:-}" == "--action" ]]; then
  if [[ "$#" -lt 3 ]]; then
    echo "--action requires an execution-control action and a command." >&2
    exit 2
  fi
  action="$2"
  shift 2
fi

.venv/bin/python -m src.tool.execution_control verify --action "$action" >/dev/null
exec "$@"
