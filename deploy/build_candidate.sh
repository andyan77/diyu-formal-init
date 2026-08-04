#!/usr/bin/env bash
set -euo pipefail

if [[ $(id -u) -ne 0 ]]; then
  echo "This script must run as root on the controlled build host." >&2
  exit 1
fi

sha="${1:?Usage: build_candidate.sh <40-character-git-sha> <clean-source-repository>}"
source_repository="${2:?Usage: build_candidate.sh <40-character-git-sha> <clean-source-repository>}"
release_root="${DIYU_RELEASE_ROOT:-/opt/diyu-saas/releases}"
if [[ ! "$sha" =~ ^[0-9a-f]{40}$ ]]; then
  echo "A full lowercase Git SHA is required." >&2
  exit 1
fi
if [[ ! -d "$source_repository/.git" ]] \
  || [[ "$(git -C "$source_repository" rev-parse HEAD)" != "$sha" ]] \
  || [[ -n "$(git -C "$source_repository" status --porcelain)" ]]; then
  echo "Candidate build source is not the exact clean frozen commit." >&2
  exit 1
fi

exec 9>"${DIYU_BUILD_LOCK:-/run/diyu-candidate-build.lock}"
if ! flock -n 9; then
  echo "Another candidate image build is active." >&2
  exit 1
fi

image_tag="diyu-saas:$sha"
release_directory="$release_root/$sha"
binding_file="$release_directory/image-binding.json"
if docker image inspect "$image_tag" >/dev/null 2>&1 || [[ -e "$binding_file" ]]; then
  echo "Candidate image or release binding already exists; refusing a second build." >&2
  exit 1
fi

export DOCKER_BUILDKIT=1
docker build \
  --build-arg "DIYU_RUNTIME_SHA=$sha" \
  --label "cc.diyu.tenant01.implementation_sha=$sha" \
  --tag "$image_tag" \
  "$source_repository"

image_digest="$(docker image inspect -f '{{.Id}}' "$image_tag")"
image_revision="$(docker image inspect -f '{{index .Config.Labels "cc.diyu.tenant01.implementation_sha"}}' "$image_tag")"
if [[ ! "$image_digest" =~ ^sha256:[0-9a-f]{64}$ || "$image_revision" != "$sha" ]]; then
  echo "Built image is not bound to the frozen candidate." >&2
  exit 1
fi

install -d -m 700 "$release_directory"
umask 077
python3 - "$binding_file" "$sha" "$image_digest" <<'PY'
import datetime
import json
import os
import sys

path, sha, digest = sys.argv[1:]
payload = {
    "binding_version": "tenant01-build-once-v1",
    "implementation_sha": sha,
    "image_digest": digest,
    "built_at": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
    "build_count": 1,
}
descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    handle.write("\n")
    handle.flush()
    os.fsync(handle.fileno())
PY
(
  cd "$release_directory"
  sha256sum image-binding.json >SHA256SUMS
  chmod 600 SHA256SUMS
)
printf '%s\n' "$image_digest"
