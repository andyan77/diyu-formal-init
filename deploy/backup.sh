#!/usr/bin/env bash
set -euo pipefail

backup_root="/var/backups/diyu-m5-4"
postgres_container="${DIYU_POSTGRES_CONTAINER:-diyu-infra-postgres-1}"
minio_image="$(docker inspect -f '{{.Config.Image}}' "${DIYU_MINIO_CONTAINER:-diyu-infra-minio-1}")"
stamp="$(date -u +%Y%m%dT%H%M%SZ)-${1:-scheduled}"
snapshot="$backup_root/$stamp"

if [[ $(id -u) -ne 0 ]]; then
  echo "This script must run as root on the ECS host." >&2
  exit 1
fi
if [[ -e "$snapshot" ]]; then
  echo "Backup destination already exists." >&2
  exit 1
fi

install -d -m 700 "$snapshot/objects"
# shellcheck disable=SC1091
set -a
source /etc/diyu/app.env
set +a

docker exec "$postgres_container" sh -lc \
  'pg_dump -U "$POSTGRES_USER" -d diyu_m5_4 --format=custom --no-owner --no-acl' >"$snapshot/database.dump"

if ! docker run --rm -i --network host -v "$snapshot/objects:/backup" --entrypoint /bin/sh "$minio_image" -ec '
  IFS= read -r endpoint
  IFS= read -r access_key
  IFS= read -r secret_key
  IFS= read -r bucket
  mc alias set current-project "$endpoint" "$access_key" "$secret_key" >/dev/null
  mc mirror --overwrite "current-project/$bucket" /backup >/dev/null
' <<EOF
${DIYU_S3_ENDPOINT_URL}
${DIYU_S3_ACCESS_KEY_ID}
${DIYU_S3_SECRET_ACCESS_KEY}
${DIYU_S3_BUCKET}
EOF
then
  echo "Object-storage backup failed without exposing object names." >&2
  exit 1
fi

database_manifest="$(
  docker exec "$postgres_container" sh -lc '
    psql -U "$POSTGRES_USER" -d diyu_m5_4 -At -F "|" -v ON_ERROR_STOP=1 -c "
      SELECT
        (SELECT version_num FROM alembic_version LIMIT 1),
        (SELECT count(*) FROM tenants),
        (SELECT count(*) FROM brands),
        (SELECT count(*) FROM users WHERE enabled = true),
        (SELECT count(*) FROM content_accounts WHERE enabled = true),
        (SELECT count(*) FROM content_roles),
        (SELECT count(*) FROM auth_grants WHERE enabled = true),
        (SELECT count(*) FROM brand_expression_baselines WHERE status = '\''confirmed'\''),
        (
          SELECT count(*)
          FROM content_versions version_record
          JOIN generation_runs run_record
            ON run_record.tenant_id = version_record.tenant_id
           AND run_record.id = version_record.run_id
          WHERE run_record.status = '\''succeeded'\''
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
           AND run_record.status = '\''succeeded'\''
          JOIN content_versions version_record
            ON version_record.tenant_id = run_record.tenant_id
           AND version_record.run_id = run_record.id
          WHERE baseline.status = '\''confirmed'\''
        );
    "
  '
)"
IFS="|" read -r schema_version tenant_count brand_count enabled_user_count publishing_account_count \
  content_role_count active_grant_count confirmed_brand_version_count successful_content_version_count \
  active_asset_count complete_content_chain_count <<<"$database_manifest"
manifest_numbers=(
  "$tenant_count"
  "$brand_count"
  "$enabled_user_count"
  "$publishing_account_count"
  "$content_role_count"
  "$active_grant_count"
  "$confirmed_brand_version_count"
  "$successful_content_version_count"
  "$active_asset_count"
  "$complete_content_chain_count"
)
if [[ ! "$schema_version" =~ ^[0-9A-Za-z_]+$ ]]; then
  echo "Backup manifest schema version is invalid." >&2
  exit 1
fi
for value in "${manifest_numbers[@]}"; do
  if [[ ! "$value" =~ ^[0-9]+$ ]]; then
    echo "Backup manifest contains an invalid count." >&2
    exit 1
  fi
done
object_count="$(find "$snapshot/objects" -type f | wc -l | tr -d ' ')"
python3 - "$snapshot/manifest.json" \
  "$schema_version" "$tenant_count" "$brand_count" "$enabled_user_count" \
  "$publishing_account_count" "$content_role_count" "$active_grant_count" \
  "$confirmed_brand_version_count" "$successful_content_version_count" \
  "$active_asset_count" "$complete_content_chain_count" "$object_count" <<'PY'
import json
import sys

(
    destination,
    schema_version,
    tenant_count,
    brand_count,
    enabled_user_count,
    publishing_account_count,
    content_role_count,
    active_grant_count,
    confirmed_brand_version_count,
    successful_content_version_count,
    active_asset_count,
    complete_content_chain_count,
    object_count,
) = sys.argv[1:]
manifest = {
    "manifest_version": 1,
    "schema_version": schema_version,
    "counts": {
        "tenants": int(tenant_count),
        "brands": int(brand_count),
        "enabled_users": int(enabled_user_count),
        "publishing_accounts": int(publishing_account_count),
        "content_roles": int(content_role_count),
        "active_grants": int(active_grant_count),
        "confirmed_brand_versions": int(confirmed_brand_version_count),
        "successful_content_versions": int(successful_content_version_count),
        "active_assets": int(active_asset_count),
        "complete_content_chains": int(complete_content_chain_count),
        "objects": int(object_count),
    },
}
with open(destination, "w", encoding="utf-8") as manifest_file:
    json.dump(manifest, manifest_file, ensure_ascii=True, indent=2, sort_keys=True)
    manifest_file.write("\n")
PY

sha256sum "$snapshot/database.dump" >"$snapshot/SHA256SUMS"
sha256sum "$snapshot/manifest.json" >>"$snapshot/SHA256SUMS"
find "$snapshot/objects" -type f -print0 | sort -z | xargs -0 -r sha256sum >>"$snapshot/SHA256SUMS"

mapfile -t snapshots < <(find "$backup_root" -mindepth 1 -maxdepth 1 -type d -name '20*' -printf '%T@ %p\n' | sort -n | awk '{print $2}')
while (( ${#snapshots[@]} > 7 )); do
  oldest="${snapshots[0]}"
  case "$oldest" in
    "$backup_root"/20*) rm -rf -- "$oldest" ;;
    *) echo "Refusing unsafe backup retention target." >&2; exit 1 ;;
  esac
  snapshots=("${snapshots[@]:1}")
done

printf 'Database and independent object-storage backup completed: %s\n' "$stamp"
