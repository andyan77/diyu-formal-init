#!/usr/bin/env bash
set -euo pipefail

if [[ $(id -u) -ne 0 ]]; then
  echo "This script must run as root on the ECS host." >&2
  exit 1
fi

sha="${1:?Usage: deploy.sh <40-character-git-sha> <sha256-image-digest>}"
image_digest="${2:?Usage: deploy.sh <40-character-git-sha> <sha256-image-digest>}"
if [[ ! "$sha" =~ ^[0-9a-f]{40}$ ]]; then
  echo "A full lowercase Git SHA is required." >&2
  exit 1
fi
if [[ ! "$image_digest" =~ ^sha256:[0-9a-f]{64}$ ]]; then
  echo "A full sha256 image digest is required." >&2
  exit 1
fi

release_root="/opt/diyu-saas"
repository="$release_root/repo"
compose_file="docker-compose.production.yml"
repository_url="https://github.com/andyan77/diyu-formal-init.git"

test -f /etc/diyu/app.env
test -f /etc/diyu/migrator.env
grep -q '^DEEPSEEK_API_KEY=.' /etc/diyu/app.env

if [[ ! -d "$repository/.git" ]]; then
  git clone --quiet "$repository_url" "$repository"
fi
if [[ -n "$(git -C "$repository" status --porcelain)" ]]; then
  echo "Refusing to overwrite local deployment repository changes." >&2
  exit 1
fi
git -C "$repository" fetch --quiet origin "$sha"
git -C "$repository" cat-file -e "${sha}^{commit}"
# Root-only backup or evidence shells may deliberately run with umask 077.
# Set the runtime-safe mask before checkout creates any worktree file, then
# re-materialize the index before Docker COPY.
umask 022
git -C "$repository" checkout --detach --quiet "$sha"
git -C "$repository" checkout-index --all --force

candidate_tag="diyu-saas:$sha"
resolved_digest="$(docker image inspect -f '{{.Id}}' "$candidate_tag")"
image_revision="$(docker image inspect -f '{{index .Config.Labels "cc.diyu.tenant01.implementation_sha"}}' "$candidate_tag")"
if [[ "$resolved_digest" != "$image_digest" || "$image_revision" != "$sha" ]]; then
  echo "Candidate image does not match the frozen SHA and digest." >&2
  exit 1
fi

export DIYU_IMAGE_REF="$image_digest"
export COMPOSE_PROJECT_NAME="diyu-m5-4"

"$repository/deploy/backup.sh" predeploy
docker compose -f "$repository/$compose_file" run --rm migrate </dev/null
docker compose -f "$repository/$compose_file" run --rm seed </dev/null
if [[ ! -e /etc/diyu/bootstrap-output ]]; then
  docker compose -f "$repository/$compose_file" run --rm bootstrap </dev/null
fi
docker compose -f "$repository/$compose_file" up -d --no-build app

for _ in $(seq 1 30); do
  if curl --fail --silent --show-error http://127.0.0.1:18000/health/ready >/dev/null; then
    app_id="$(docker compose -f "$repository/$compose_file" ps -q app)"
    if [[ -z "$app_id" ]]; then
      echo "Candidate application container is unavailable." >&2
      exit 1
    fi
    running_digest="$(docker inspect -f '{{.Image}}' "$app_id")"
    if [[ "$running_digest" != "$image_digest" ]]; then
      echo "Running application digest differs from the frozen release binding." >&2
      exit 1
    fi
    install -m 644 "$repository/deploy/systemd/diyu-m5-4-backup.service" /etc/systemd/system/
    install -m 644 "$repository/deploy/systemd/diyu-m5-4-backup.timer" /etc/systemd/system/
    systemctl daemon-reload
    systemctl enable --now diyu-m5-4-backup.timer
    printf 'Candidate %s (%s) is ready on the loopback port.\n' "$sha" "$image_digest"
    exit 0
  fi
  sleep 1
done

echo "Candidate health check failed; public Nginx routing was not changed." >&2
exit 1
