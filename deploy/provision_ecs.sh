#!/usr/bin/env bash
set -euo pipefail

if [[ $(id -u) -ne 0 ]]; then
  echo "This script must run as root on the ECS host." >&2
  exit 1
fi

postgres_container="${DIYU_POSTGRES_CONTAINER:-diyu-infra-postgres-1}"
minio_container="${DIYU_MINIO_CONTAINER:-diyu-infra-minio-1}"
config_dir="/etc/diyu"
app_env="$config_dir/app.env"
migrator_env="$config_dir/migrator.env"
bootstrap_env="$config_dir/bootstrap.env"
database_name="diyu_m5_4"
bucket_name="diyu-m5-4-materials"

if [[ -e "$app_env" || -e "$migrator_env" || -e "$bootstrap_env" ]]; then
  echo "Refusing to overwrite existing current-project secrets in $config_dir." >&2
  exit 1
fi

docker inspect "$postgres_container" >/dev/null
docker inspect "$minio_container" >/dev/null
install -d -m 700 "$config_dir" /opt/diyu-saas /var/backups/diyu-m5-4

app_database_password="$(openssl rand -hex 32)"
migrator_database_password="$(openssl rand -hex 32)"
session_secret="$(openssl rand -hex 48)"
s3_access_key="diyu-m54-$(openssl rand -hex 8)"
s3_secret_key="$(openssl rand -base64 36 | tr -d '\n')"
ops_password="$(openssl rand -base64 30 | tr -d '\n')"

existing_roles="$(docker exec "$postgres_container" sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "SELECT string_agg(rolname, chr(44) ORDER BY rolname) FROM pg_roles WHERE rolname IN (chr(100)||chr(105)||chr(121)||chr(117)||chr(95)||chr(97)||chr(112)||chr(112), chr(100)||chr(105)||chr(121)||chr(117)||chr(95)||chr(109)||chr(105)||chr(103)||chr(114)||chr(97)||chr(116)||chr(111)||chr(114))"')"
if [[ "$existing_roles" == "diyu_app,diyu_migrator" ]]; then
  database_is_empty="$(docker exec "$postgres_container" sh -lc 'psql -U "$POSTGRES_USER" -d diyu_m5_4 -Atc "SELECT to_regclass(chr(112)||chr(117)||chr(98)||chr(108)||chr(105)||chr(99)||chr(46)||chr(97)||chr(108)||chr(101)||chr(109)||chr(98)||chr(105)||chr(99)||chr(95)||chr(118)||chr(101)||chr(114)||chr(115)||chr(105)||chr(111)||chr(110)) IS NULL"')"
  if [[ "$database_is_empty" != "t" ]]; then
    echo "Existing current-project database is not an empty failed provision; refusing recovery." >&2
    exit 1
  fi
  docker exec -i "$postgres_container" sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1' <<SQL >/dev/null
ALTER ROLE diyu_migrator PASSWORD '${migrator_database_password}';
ALTER ROLE diyu_app PASSWORD '${app_database_password}';
SQL
elif [[ -n "$existing_roles" ]]; then
  echo "A partial non-isolated role set already exists; refusing to reuse it." >&2
  exit 1
else
  docker exec -i "$postgres_container" sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1' <<SQL >/dev/null
DO \$\$
BEGIN
    CREATE ROLE diyu_migrator LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD '${migrator_database_password}';
    CREATE ROLE diyu_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOINHERIT PASSWORD '${app_database_password}';
END
\$\$;
SELECT format('CREATE DATABASE %I OWNER %I', '${database_name}', 'diyu_migrator')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = '${database_name}')\gexec
GRANT CONNECT ON DATABASE ${database_name} TO diyu_app;
SQL
fi

docker exec -i "$minio_container" sh -ec '
  IFS= read -r access_key
  IFS= read -r secret_key
  if [ -n "${MINIO_ROOT_USER_FILE:-}" ] && [ -r "$MINIO_ROOT_USER_FILE" ]; then MINIO_ROOT_USER=$(cat "$MINIO_ROOT_USER_FILE"); fi
  if [ -n "${MINIO_ROOT_PASSWORD_FILE:-}" ] && [ -r "$MINIO_ROOT_PASSWORD_FILE" ]; then MINIO_ROOT_PASSWORD=$(cat "$MINIO_ROOT_PASSWORD_FILE"); fi
  mc alias set current-project http://127.0.0.1:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null
  mc mb --ignore-existing "current-project/diyu-m5-4-materials" >/dev/null
  cat >/tmp/diyu-m5-4-materials-policy.json <<"JSON"
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["s3:ListBucket"],"Resource":["arn:aws:s3:::diyu-m5-4-materials"]},{"Effect":"Allow","Action":["s3:GetObject","s3:PutObject","s3:DeleteObject"],"Resource":["arn:aws:s3:::diyu-m5-4-materials/*"]}]}
JSON
  mc admin policy create current-project diyu-m5-4-materials /tmp/diyu-m5-4-materials-policy.json >/dev/null
  mc admin user add current-project "$access_key" "$secret_key" >/dev/null
  mc admin policy attach current-project diyu-m5-4-materials --user "$access_key" >/dev/null
' <<EOF
${s3_access_key}
${s3_secret_key}
EOF

umask 077
cat >"$app_env" <<EOF
DIYU_RUNTIME_MODE=production
DIYU_APP_DATABASE_URL=postgresql://diyu_app:${app_database_password}@127.0.0.1:5432/${database_name}
DIYU_SESSION_SECRET=${session_secret}
DIYU_GENERATOR_MODE=deepseek
DEEPSEEK_API_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
DIYU_S3_ENDPOINT_URL=http://127.0.0.1:9000
DIYU_S3_BUCKET=${bucket_name}
DIYU_S3_ACCESS_KEY_ID=${s3_access_key}
DIYU_S3_SECRET_ACCESS_KEY=${s3_secret_key}
DIYU_S3_REGION=us-east-1
DIYU_LOGIN_RATE_LIMIT_PER_MINUTE=10
DIYU_MODEL_GLOBAL_CONCURRENCY=4
DIYU_MODEL_TENANT_CONCURRENCY=2
DIYU_MODEL_TENANT_RATE_PER_MINUTE=12
DIYU_MODEL_TIMEOUT_SECONDS=45
DIYU_MODEL_MAX_RETRIES=2
DIYU_PUBLIC_URL=https://diyuai.cc
EOF
cat >"$migrator_env" <<EOF
DIYU_MIGRATOR_DATABASE_URL=postgresql://diyu_migrator:${migrator_database_password}@127.0.0.1:5432/${database_name}
EOF
cat >"$bootstrap_env" <<EOF
DIYU_BOOTSTRAP_OUTPUT_PATH=/run/diyu-ops/bootstrap-output
DIYU_INITIAL_OPS_USERNAME=diyu-ops
DIYU_INITIAL_OPS_PASSWORD=${ops_password}
DIYU_INITIAL_DEMO_ADMIN_USERNAME=folding-admin
EOF
chmod 600 "$app_env" "$migrator_env" "$bootstrap_env"
printf 'M5-4 isolated database roles, bucket and root-only configuration were created.\n'
