#!/usr/bin/env bash
set -euo pipefail

if [[ $(id -u) -ne 0 ]]; then
  echo "This script must run as root on the ECS host." >&2
  exit 1
fi

mode="${1:-application}"
if [[ "$mode" != "application" && "$mode" != "maintenance" ]]; then
  echo "Usage: switch_public_route.sh [application|maintenance]" >&2
  exit 1
fi

repository="/opt/diyu-saas/repo"
nginx_available="/etc/nginx/sites-available"
nginx_enabled="/etc/nginx/sites-enabled"
target="$nginx_available/diyuai.cc"
kb_config="$nginx_available/kb.diyuai.cc"
source_file="$repository/deploy/nginx/diyuai.cc.conf"
if [[ "$mode" == "maintenance" ]]; then
  source_file="$repository/deploy/nginx/diyuai.cc-maintenance.conf"
fi

test -r "$source_file"
test -r "$kb_config"
test -r /etc/letsencrypt/live/kb.diyuai.cc/fullchain.pem
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_dir="/etc/nginx/diyu-m5-4-backups/$stamp"
install -d -m 700 "$backup_dir"
cp -a "$kb_config" "$backup_dir/kb.diyuai.cc"
had_target=false
if [[ -e "$target" ]]; then
  had_target=true
  cp -a "$target" "$backup_dir/diyuai.cc"
fi

install -m 644 "$source_file" "$target"
sed -i 's/server_name kb\.diyuai\.cc diyuai\.cc;/server_name kb.diyuai.cc;/g' "$kb_config"
ln -sfn "$target" "$nginx_enabled/diyuai.cc"

if ! nginx -t; then
  cp -a "$backup_dir/kb.diyuai.cc" "$kb_config"
  if [[ -e "$backup_dir/diyuai.cc" ]]; then
    cp -a "$backup_dir/diyuai.cc" "$target"
  elif [[ "$had_target" == "false" ]]; then
    unlink "$nginx_enabled/diyuai.cc"
    mv "$target" "$backup_dir/diyuai.cc.failed"
  fi
  nginx -t >/dev/null
  echo "Nginx validation failed; prior KB route was restored." >&2
  exit 1
fi
systemctl reload nginx
printf 'diyuai.cc now serves the %s route; historical subdomain routes were preserved.\n' "$mode"
