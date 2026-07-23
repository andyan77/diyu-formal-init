#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
data_dir="$project_root/var/postgres/data"
socket_dir="$project_root/var/postgres/socket"
port="${DIYU_LOCAL_PG_PORT:-55432}"
if [[ -n "${DIYU_PG_BIN:-}" ]]; then
  pg_bin="$DIYU_PG_BIN"
elif command -v pg_config >/dev/null 2>&1; then
  pg_bin="$(pg_config --bindir)"
elif command -v initdb >/dev/null 2>&1; then
  pg_bin="$(dirname "$(command -v initdb)")"
else
  echo "未找到 PostgreSQL 服务端工具；请设置 DIYU_PG_BIN 或安装 pg_config/initdb。" >&2
  exit 1
fi

if [[ ! -x "$pg_bin/initdb" || ! -x "$pg_bin/pg_ctl" || ! -x "$pg_bin/pg_isready" ]]; then
  echo "DIYU_PG_BIN 不包含 initdb、pg_ctl 和 pg_isready。" >&2
  exit 1
fi

mkdir -p "$socket_dir" "$data_dir"
if [[ ! -f "$data_dir/PG_VERSION" ]]; then
  "$pg_bin/initdb" -D "$data_dir" --auth-local=trust --auth-host=reject --username=diyu_migrator
  sed -i "s/^#listen_addresses = 'localhost'/listen_addresses = ''/" "$data_dir/postgresql.conf"
fi
if ! "$pg_bin/pg_isready" -h "$socket_dir" -p "$port" >/dev/null 2>&1; then
  "$pg_bin/pg_ctl" -D "$data_dir" -l "$project_root/var/postgres/postgres.log" -o "-k '$socket_dir' -p $port" start
fi
if ! psql -h "$socket_dir" -p "$port" -U diyu_migrator -d postgres -tAc "SELECT 1 FROM pg_roles WHERE rolname = 'diyu_app'" | grep -qx 1; then
  psql -h "$socket_dir" -p "$port" -U diyu_migrator -d postgres -v ON_ERROR_STOP=1 -c "CREATE ROLE diyu_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS"
fi
if ! psql -h "$socket_dir" -p "$port" -U diyu_migrator -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = 'diyu_m3'" | grep -qx 1; then
  psql -h "$socket_dir" -p "$port" -U diyu_migrator -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE diyu_m3 OWNER diyu_migrator"
fi
export DIYU_MIGRATOR_DATABASE_URL="postgresql://diyu_migrator@/diyu_m3?host=$socket_dir&port=$port"
export DIYU_APP_DATABASE_URL="postgresql://diyu_app@/diyu_m3?host=$socket_dir&port=$port"
