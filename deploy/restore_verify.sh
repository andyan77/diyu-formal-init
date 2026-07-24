#!/usr/bin/env bash
set -euo pipefail

snapshot="${1:?Usage: restore_verify.sh /var/backups/diyu-m5-4/<snapshot>}"
if [[ $(id -u) -ne 0 || ! -f "$snapshot/database.dump" || ! -f "$snapshot/manifest.json" ]]; then
  echo "Run as root with a current-project backup snapshot." >&2
  exit 1
fi

postgres_image="$(docker inspect -f '{{.Config.Image}}' "${DIYU_POSTGRES_CONTAINER:-diyu-infra-postgres-1}")"
minio_image="$(docker inspect -f '{{.Config.Image}}' "${DIYU_MINIO_CONTAINER:-diyu-infra-minio-1}")"
app_image="diyu-saas:${DIYU_IMAGE_TAG:?DIYU_IMAGE_TAG is required}"
suffix="$(openssl rand -hex 6)"
postgres_name="diyu-m5-4-restore-${suffix}"
app_name="diyu-m5-4-restore-app-${suffix}"
postgres_port="55440"
temporary_directory="/run/diyu-restore-${suffix}"
postgres_env="$temporary_directory/postgres.env"
app_env="$temporary_directory/app.env"
verify_password="$(openssl rand -hex 32)"
restore_admin="diyu_restore_admin"

cleanup() {
  docker rm -f "$app_name" "$postgres_name" >/dev/null 2>&1 || true
  if [[ -d "$temporary_directory" ]]; then
    shred -u "$postgres_env" "$app_env" >/dev/null 2>&1 || true
    rmdir "$temporary_directory" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

sha256sum -c "$snapshot/SHA256SUMS" >/dev/null
install -d -m 700 "$temporary_directory"
umask 077
cat >"$postgres_env" <<EOF
POSTGRES_USER=${restore_admin}
POSTGRES_PASSWORD=${verify_password}
POSTGRES_DB=diyu_m5_4
EOF

docker run -d --name "$postgres_name" --env-file "$postgres_env" -p "127.0.0.1:${postgres_port}:5432" \
  "$postgres_image" >/dev/null
for _ in $(seq 1 30); do
  if docker exec "$postgres_name" pg_isready -U "$restore_admin" -d diyu_m5_4 >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
docker exec "$postgres_name" pg_isready -U "$restore_admin" -d diyu_m5_4 >/dev/null
docker exec -i "$postgres_name" pg_restore -U "$restore_admin" -d diyu_m5_4 --no-owner --no-acl \
  <"$snapshot/database.dump"
docker exec "$postgres_name" psql -U "$restore_admin" -d diyu_m5_4 -v ON_ERROR_STOP=1 -c \
  "CREATE ROLE diyu_app LOGIN PASSWORD '${verify_password}' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
   GRANT CONNECT ON DATABASE diyu_m5_4 TO diyu_app;
   GRANT USAGE ON SCHEMA public TO diyu_app;
   GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO diyu_app;
   GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO diyu_app;
   GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO diyu_app;" >/dev/null

if docker exec -e PGPASSWORD="$verify_password" "$postgres_name" \
  psql -U diyu_app -d diyu_m5_4 -c 'SELECT count(*) FROM users' >/dev/null 2>&1; then
  echo "Restored RLS unexpectedly allowed an unscoped tenant read." >&2
  exit 1
fi
docker exec -e PGPASSWORD="$verify_password" "$postgres_name" \
  psql -U diyu_app -d diyu_m5_4 -v ON_ERROR_STOP=1 -c \
  "SELECT set_config('app.tenant_id', '00000000-0000-0000-0000-000000000001', true); SELECT count(*) FROM users;" \
  >/dev/null

expected_manifest="$(
  python3 - "$snapshot/manifest.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as manifest_file:
    manifest = json.load(manifest_file)
counts = manifest["counts"]
values = (
    manifest["schema_version"],
    counts["tenants"],
    counts["brands"],
    counts["enabled_users"],
    counts["publishing_accounts"],
    counts["content_roles"],
    counts["active_grants"],
    counts["confirmed_brand_versions"],
    counts["successful_content_versions"],
    counts["active_assets"],
    counts["complete_content_chains"],
    counts["objects"],
)
print("|".join(str(value) for value in values))
PY
)"
restored_database_manifest="$(
  docker exec "$postgres_name" psql -U "$restore_admin" -d diyu_m5_4 -At -F "|" -v ON_ERROR_STOP=1 -c "
    SELECT
      (SELECT version_num FROM alembic_version LIMIT 1),
      (SELECT count(*) FROM tenants),
      (SELECT count(*) FROM brands),
      (SELECT count(*) FROM users WHERE enabled = true),
      (SELECT count(*) FROM content_accounts WHERE enabled = true),
      (SELECT count(*) FROM content_roles),
      (SELECT count(*) FROM auth_grants WHERE enabled = true),
      (SELECT count(*) FROM brand_expression_baselines WHERE status = 'confirmed'),
      (
        SELECT count(*)
        FROM content_versions version_record
        JOIN generation_runs run_record
          ON run_record.tenant_id = version_record.tenant_id
         AND run_record.id = version_record.run_id
        WHERE run_record.status = 'succeeded'
      ),
      (SELECT count(*) FROM system_asset_activations),
      (
        SELECT count(DISTINCT version_record.id)
        FROM brand_expression_baselines baseline
        JOIN content_accounts account_record
          ON account_record.tenant_id = baseline.tenant_id
         AND account_record.brand_id = baseline.brand_id
         AND account_record.enabled = true
        JOIN account_content_roles account_role
          ON account_role.tenant_id = account_record.tenant_id
         AND account_role.account_id = account_record.id
        JOIN content_roles role_record
          ON role_record.tenant_id = account_role.tenant_id
         AND role_record.id = account_role.content_role_id
         AND role_record.brand_id = baseline.brand_id
        JOIN auth_grants grant_record
          ON grant_record.tenant_id = account_record.tenant_id
         AND grant_record.account_id = account_record.id
         AND grant_record.enabled = true
        JOIN business_tasks task_record
          ON task_record.tenant_id = account_record.tenant_id
         AND task_record.brand_id = baseline.brand_id
         AND task_record.account_id = account_record.id
         AND task_record.created_by = grant_record.user_id
        JOIN generation_runs run_record
          ON run_record.tenant_id = task_record.tenant_id
         AND run_record.task_id = task_record.id
         AND run_record.status = 'succeeded'
        JOIN content_versions version_record
          ON version_record.tenant_id = run_record.tenant_id
         AND version_record.run_id = run_record.id
        WHERE baseline.status = 'confirmed'
      );
  "
)"
restored_object_count="$(find "$snapshot/objects" -type f | wc -l | tr -d ' ')"
if [[ "${restored_database_manifest}|${restored_object_count}" != "$expected_manifest" ]]; then
  echo "Restored database or object counts do not match the snapshot manifest." >&2
  exit 1
fi
IFS="|" read -r _ _ _ _ _ _ _ _ _ _ complete_content_chain_count _ <<<"$expected_manifest"
if (( complete_content_chain_count < 1 )); then
  echo "Snapshot does not contain a complete confirmed-brand content relationship chain." >&2
  exit 1
fi

grep -v '^DIYU_APP_DATABASE_URL=' /etc/diyu/app.env >"$app_env"
printf 'DIYU_APP_DATABASE_URL=postgresql://diyu_app:%s@127.0.0.1:%s/diyu_m5_4\n' \
  "$verify_password" "$postgres_port" >>"$app_env"
docker run -d --name "$app_name" --network host --env-file "$app_env" "$app_image" \
  uv run --no-sync uvicorn src.gateway.api.app:create_app --factory --host 127.0.0.1 --port 18001 \
  --proxy-headers --forwarded-allow-ips 127.0.0.1 >/dev/null
for _ in $(seq 1 30); do
  if curl --fail --silent http://127.0.0.1:18001/health/ready >/dev/null; then
    break
  fi
  sleep 1
done
curl --fail --silent http://127.0.0.1:18001/health/ready >/dev/null

test_object="$(find "$snapshot/objects" -type f -print -quit)"
if [[ -z "$test_object" ]]; then
  echo "A recovery verification requires the expected non-sensitive test object in the backup." >&2
  exit 1
fi
set -a
# shellcheck disable=SC1091
source /etc/diyu/app.env
set +a
restore_key="recovery-verify/${suffix}-$(basename "$test_object")"
if ! docker run --rm -i --network host -v "$test_object:/restore-object:ro" --entrypoint /bin/sh "$minio_image" -ec '
  IFS= read -r endpoint
  IFS= read -r access_key
  IFS= read -r secret_key
  IFS= read -r bucket
  IFS= read -r object_key
  mc alias set current-project "$endpoint" "$access_key" "$secret_key" >/dev/null
  mc cp /restore-object "current-project/$bucket/$object_key" >/dev/null
  mc stat "current-project/$bucket/$object_key" >/dev/null
  mc rm "current-project/$bucket/$object_key" >/dev/null
' <<EOF
${DIYU_S3_ENDPOINT_URL}
${DIYU_S3_ACCESS_KEY_ID}
${DIYU_S3_SECRET_ACCESS_KEY}
${DIYU_S3_BUCKET}
${restore_key}
EOF
then
  echo "Object-storage recovery verification failed without exposing object details." >&2
  exit 1
fi

printf 'Isolated database restore, RLS check, application readiness and object recovery verification passed.\n'
