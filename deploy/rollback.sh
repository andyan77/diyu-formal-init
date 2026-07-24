#!/usr/bin/env bash
set -euo pipefail

if [[ $(id -u) -ne 0 ]]; then
  echo "This script must run as root on the ECS host." >&2
  exit 1
fi

target="${1:?Usage: rollback.sh <40-character-git-sha|maintenance>}"
repository="/opt/diyu-saas/repo"
compose_file="$repository/docker-compose.production.yml"

if [[ "$target" == "maintenance" ]]; then
  "$repository/deploy/switch_public_route.sh" maintenance
  export COMPOSE_PROJECT_NAME="diyu-m5-4"
  docker compose -f "$compose_file" stop app
  printf 'diyuai.cc is in explicit maintenance mode; project data and images were retained.\n'
  exit 0
fi
if [[ ! "$target" =~ ^[0-9a-f]{40}$ ]]; then
  echo "A full lowercase Git SHA or maintenance is required." >&2
  exit 1
fi
if [[ -n "$(git -C "$repository" status --porcelain)" ]]; then
  echo "Refusing to overwrite local deployment repository changes." >&2
  exit 1
fi

git -C "$repository" fetch --quiet origin "$target"
git -C "$repository" cat-file -e "${target}^{commit}"
git -C "$repository" checkout --detach --quiet "$target"
export DIYU_IMAGE_TAG="$target"
export COMPOSE_PROJECT_NAME="diyu-m5-4"
export DOCKER_BUILDKIT=1
docker compose -f "$compose_file" build app
docker compose -f "$compose_file" up -d --no-build app
for _ in $(seq 1 30); do
  if curl --fail --silent http://127.0.0.1:18000/health/ready >/dev/null; then
    "$repository/deploy/switch_public_route.sh" application
    printf 'Application rollback candidate %s is healthy and public.\n' "$target"
    exit 0
  fi
  sleep 1
done

echo "Rollback candidate failed health checks; public route was left unchanged." >&2
exit 1
