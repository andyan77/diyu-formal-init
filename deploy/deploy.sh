#!/usr/bin/env bash
set -euo pipefail

if [[ $(id -u) -ne 0 ]]; then
  echo "This script must run as root on the ECS host." >&2
  exit 1
fi

sha="${1:?Usage: deploy.sh <40-character-git-sha>}"
if [[ ! "$sha" =~ ^[0-9a-f]{40}$ ]]; then
  echo "A full lowercase Git SHA is required." >&2
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
git -C "$repository" checkout --detach --quiet "$sha"

export DIYU_IMAGE_TAG="$sha"
export COMPOSE_PROJECT_NAME="diyu-m5-4"
export DOCKER_BUILDKIT=1

"$repository/deploy/backup.sh" predeploy
docker compose -f "$repository/$compose_file" build app
docker compose -f "$repository/$compose_file" run --rm migrate </dev/null
docker compose -f "$repository/$compose_file" run --rm seed </dev/null
if [[ ! -e /etc/diyu/bootstrap-output ]]; then
  docker compose -f "$repository/$compose_file" run --rm bootstrap </dev/null
fi
docker compose -f "$repository/$compose_file" up -d --no-build app

for _ in $(seq 1 30); do
  if curl --fail --silent --show-error http://127.0.0.1:18000/health/ready >/dev/null; then
    install -m 644 "$repository/deploy/systemd/diyu-m5-4-backup.service" /etc/systemd/system/
    install -m 644 "$repository/deploy/systemd/diyu-m5-4-backup.timer" /etc/systemd/system/
    systemctl daemon-reload
    systemctl enable --now diyu-m5-4-backup.timer
    printf 'Candidate %s is ready on the loopback port.\n' "$sha"
    exit 0
  fi
  sleep 1
done

echo "Candidate health check failed; public Nginx routing was not changed." >&2
exit 1
