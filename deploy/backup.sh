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

sha256sum "$snapshot/database.dump" >"$snapshot/SHA256SUMS"
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
