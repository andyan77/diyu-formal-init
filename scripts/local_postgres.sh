#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
data_dir="$project_root/var/postgres/data"
socket_dir="$project_root/var/postgres/socket"
port="${DIYU_LOCAL_PG_PORT:-55432}"
pg_bin="/usr/lib/postgresql/14/bin"

mkdir -p "$socket_dir" "$data_dir"
if [[ ! -f "$data_dir/PG_VERSION" ]]; then
  "$pg_bin/initdb" -D "$data_dir" --auth-local=trust --auth-host=reject --username=diyu_migrator
  sed -i "s/^#listen_addresses = 'localhost'/listen_addresses = ''/" "$data_dir/postgresql.conf"
fi
if ! "$pg_bin/pg_isready" -h "$socket_dir" -p "$port" >/dev/null 2>&1; then
  "$pg_bin/pg_ctl" -D "$data_dir" -l "$project_root/var/postgres/postgres.log" -o "-k '$socket_dir' -p $port" start
fi
if ! psql -h "$socket_dir" -p "$port" -U diyu_migrator -d postgres -tAc "SELECT 1 FROM pg_roles WHERE rolname = 'diyu_app'" | rg -q 1; then
  psql -h "$socket_dir" -p "$port" -U diyu_migrator -d postgres -v ON_ERROR_STOP=1 -c "CREATE ROLE diyu_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS"
fi
if ! psql -h "$socket_dir" -p "$port" -U diyu_migrator -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = 'diyu_m3'" | rg -q 1; then
  psql -h "$socket_dir" -p "$port" -U diyu_migrator -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE diyu_m3 OWNER diyu_migrator"
fi
export DIYU_MIGRATOR_DATABASE_URL="postgresql://diyu_migrator@/diyu_m3?host=$socket_dir&port=$port"
export DIYU_APP_DATABASE_URL="postgresql://diyu_app@/diyu_m3?host=$socket_dir&port=$port"
