#!/usr/bin/env bash
set -euo pipefail

target_host="${DIYU_ECS_HOST:-diyuai.cc}"
target_user="${DIYU_ECS_USER:-root}"
ssh_key="${DIYU_ECS_SSH_KEY:-/home/faye/.ssh/diyu-hk.pem}"
secret_file="${DIYU_DEEPSEEK_ENV_FILE:-/home/diyu/worktrees/gate1-longrun-001/controlled_content_generator_v2_001/gate1_v1_1_001/p7_successor_longrun_001/.env.deepseek}"

if [[ ! -r "$secret_file" ]]; then
  echo "Authorized DeepSeek environment file is unavailable." >&2
  exit 1
fi

# shellcheck disable=SC1090
source "$secret_file"
: "${DEEPSEEK_API_KEY:?Authorized DeepSeek key is missing}"

known_hosts="$(mktemp)"
{
  printf 'DEEPSEEK_API_KEY=%s\n' "$DEEPSEEK_API_KEY"
} | ssh -i "$ssh_key" -o UserKnownHostsFile="$known_hosts" -o StrictHostKeyChecking=accept-new \
  -o BatchMode=yes "$target_user@$target_host" \
  "umask 077; test -f /etc/diyu/app.env; grep -q '^DEEPSEEK_API_KEY=' /etc/diyu/app.env && exit 1; cat >> /etc/diyu/app.env; chmod 600 /etc/diyu/app.env"

printf 'DeepSeek connection material was installed into the ECS root-only application configuration.\n'
