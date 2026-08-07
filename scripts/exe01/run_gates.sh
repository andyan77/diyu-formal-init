#!/usr/bin/env bash
#
# Run the nine EXE-01 / EXE-01R determinism gates, in order, and report each.
#
# The gates existed before this runner did — they simply were not wired to
# anything, so nobody found out when one went red. This is the wiring: one
# command, locally and in CI, that either goes green or names the gate that
# did not.
#
# Self-contained on purpose. It starts (or reuses) the project's own
# PostgreSQL — a unix socket under var/postgres with `listen_addresses = ''`,
# so it has no TCP port and cannot be reached from off the machine — migrates
# it, seeds it deterministically, and exports the same demo identifiers
# scripts/test.sh uses. It never reads .env, never resolves a remote host, and
# never touches production, Qdrant, ECS or Dify.
set -uo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$project_root"
python_bin="$project_root/.venv/bin/python"

if [[ ! -x "$python_bin" ]]; then
  echo "缺少 .venv：先跑 uv sync --all-groups --no-install-project --locked" >&2
  exit 2
fi

# --- the sandbox the gates run against -------------------------------------
set -e
source "$project_root/scripts/local_postgres.sh"
export DIYU_SESSION_SECRET="local-test-session-secret"
export DIYU_DEMO_TENANT_ID="00000000-0000-0000-0000-000000000001"
export DIYU_DEMO_USER_ID="00000000-0000-0000-0000-000000000011"
export DIYU_DEMO_BRAND_ID="00000000-0000-0000-0000-000000000021"
export DIYU_DEMO_ACCOUNT_ID="00000000-0000-0000-0000-000000000031"
export DIYU_DEMO_DISPLAY_ORGANIZATION_ID="00000000-0000-0000-0000-000000000012"
export DIYU_DEMO_DISPLAY_USER_ID="00000000-0000-0000-0000-000000000013"
export DIYU_GENERATOR_MODE="stub"
export TMPDIR="$project_root/var/tmp"
export TEMP="$TMPDIR"
export TMP="$TMPDIR"
mkdir -p "$TMPDIR"

"$python_bin" -m alembic upgrade head >/dev/null
"$python_bin" -m src.infrastructure.seed_demo >/dev/null
"$python_bin" -m src.infrastructure.system_asset_catalog >/dev/null

# Two gates read build output rather than source, so it has to exist. In CI
# `make frontend-build` has already run; locally it may not have.
if [[ ! -f "$project_root/frontend/dist/.vite/manifest.json" ]]; then
  echo "→ frontend/dist 不存在，先构建一次"
  npm --prefix frontend run build >/dev/null
fi
set +e

# --- the nine --------------------------------------------------------------
GATES=(
  assert_scope
  assert_baseline_frozen
  assert_test_reconciliation
  assert_codegen_drift
  assert_dead_css
  assert_bundle_budget
  assert_function_budget
  assert_visual_evidence
  assert_route_compatibility
)

failed=()
for gate in "${GATES[@]}"; do
  echo
  echo "════════ ${gate} ════════"
  if "$python_bin" "scripts/exe01/${gate}.py"; then
    echo "✔ ${gate}"
  else
    echo "✘ ${gate}"
    failed+=("$gate")
  fi
done

echo
echo "──────── 九门汇总 ────────"
printf '通过 %d / %d\n' "$(( ${#GATES[@]} - ${#failed[@]} ))" "${#GATES[@]}"
if (( ${#failed[@]} )); then
  printf '未通过：%s\n' "${failed[*]}" >&2
  exit 1
fi
echo "九门全绿"
