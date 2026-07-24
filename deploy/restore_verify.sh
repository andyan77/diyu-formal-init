#!/usr/bin/env bash
set -euo pipefail

snapshot="${1:?Usage: restore_verify.sh /var/backups/diyu-m5-4/<snapshot>}"
if [[ $(id -u) -ne 0 || ! -f "$snapshot/database.dump" ]]; then
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
POSTGRES_USER=diyu_app
POSTGRES_PASSWORD=${verify_password}
POSTGRES_DB=diyu_m5_4
EOF

docker run -d --name "$postgres_name" --env-file "$postgres_env" -p "127.0.0.1:${postgres_port}:5432" \
  "$postgres_image" >/dev/null
for _ in $(seq 1 30); do
  if docker exec "$postgres_name" pg_isready -U diyu_app -d diyu_m5_4 >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
docker exec "$postgres_name" pg_isready -U diyu_app -d diyu_m5_4 >/dev/null
docker exec -i "$postgres_name" pg_restore -U diyu_app -d diyu_m5_4 --no-owner --no-acl <"$snapshot/database.dump"

if docker exec "$postgres_name" psql -U diyu_app -d diyu_m5_4 -c 'SELECT count(*) FROM users' >/dev/null 2>&1; then
  echo "Restored RLS unexpectedly allowed an unscoped tenant read." >&2
  exit 1
fi
activation_count="$(docker exec "$postgres_name" psql -U diyu_app -d diyu_m5_4 -Atc 'SELECT count(*) FROM system_asset_activations')"
if [[ "$activation_count" != "41" ]]; then
  echo "Restored active-system-asset count is not the expected 41." >&2
  exit 1
fi
docker exec "$postgres_name" psql -U diyu_app -d diyu_m5_4 -v ON_ERROR_STOP=1 -c \
  "SELECT set_config('app.tenant_id', '00000000-0000-0000-0000-000000000001', true); SELECT count(*) FROM users;" \
  >/dev/null

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
if ! docker run --rm -i --network host -v "$test_object:/restore-object:ro" "$minio_image" sh -ec '
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
