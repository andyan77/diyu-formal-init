#!/usr/bin/env bash
set -euo pipefail

if [[ $(id -u) -ne 0 ]]; then
  echo "This script must run as root on the ECS host." >&2
  exit 1
fi

target="${1:?Usage: rollback.sh <40-character-git-sha|maintenance> [sha256-image-digest]}"
repository="/opt/diyu-saas/repo"
compose_file="$repository/docker-compose.production.yml"

if [[ "$target" == "maintenance" ]]; then
  "$repository/deploy/switch_public_route.sh" maintenance
  app_id="$(docker ps -q \
    --filter label=com.docker.compose.project=diyu-m5-4 \
    --filter label=com.docker.compose.service=app)"
  if [[ -n "$app_id" ]]; then
    docker stop "$app_id" >/dev/null
  fi
  printf 'diyuai.cc is in explicit maintenance mode; project data and images were retained.\n'
  exit 0
fi
if [[ ! "$target" =~ ^[0-9a-f]{40}$ ]]; then
  echo "A full lowercase Git SHA or maintenance is required." >&2
  exit 1
fi
image_digest="${2:?Usage: rollback.sh <40-character-git-sha> <sha256-image-digest>}"
if [[ ! "$image_digest" =~ ^sha256:[0-9a-f]{64}$ ]]; then
  echo "A full sha256 image digest is required." >&2
  exit 1
fi
if [[ -n "$(git -C "$repository" status --porcelain)" ]]; then
  echo "Refusing to overwrite local deployment repository changes." >&2
  exit 1
fi

git -C "$repository" fetch --quiet origin "$target"
git -C "$repository" cat-file -e "${target}^{commit}"
target_tag="diyu-saas:$target"
resolved_digest="$(docker image inspect -f '{{.Id}}' "$target_tag")"
image_revision="$(docker image inspect -f '{{if .Config.Labels}}{{index .Config.Labels "cc.diyu.tenant01.implementation_sha"}}{{end}}' "$target_tag")"
if [[ "$resolved_digest" != "$image_digest" ]]; then
  echo "Rollback image does not match the requested digest." >&2
  exit 1
fi
if [[ -n "$image_revision" && "$image_revision" != "$target" ]]; then
  echo "Rollback image revision label differs from the requested SHA." >&2
  exit 1
fi

export DIYU_IMAGE_REF="$image_digest"
export COMPOSE_PROJECT_NAME="diyu-m5-4"
docker compose -f "$compose_file" up -d --no-build app
for _ in $(seq 1 30); do
  if curl --fail --silent http://127.0.0.1:18000/health/ready >/dev/null; then
    app_id="$(docker compose -f "$compose_file" ps -q app)"
    if [[ -z "$app_id" ]]; then
      echo "Rollback application container is unavailable." >&2
      exit 1
    fi
    running_digest="$(docker inspect -f '{{.Image}}' "$app_id")"
    if [[ "$running_digest" != "$image_digest" ]]; then
      echo "Running rollback digest differs from the requested image." >&2
      exit 1
    fi
    "$repository/deploy/switch_public_route.sh" application
    printf 'Application rollback candidate %s (%s) is healthy and public.\n' "$target" "$image_digest"
    exit 0
  fi
  sleep 1
done

echo "Rollback candidate failed health checks; public route was left unchanged." >&2
exit 1
