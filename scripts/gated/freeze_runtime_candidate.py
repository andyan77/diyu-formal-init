#!/usr/bin/env python3
"""Freeze the unique Gate D runtime candidate and its non-task input fingerprints."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from scripts.gated.brand_matrix_importer import BRAND_ID, TENANT_ID  # noqa: E402
from scripts.gated.provider_env import parse_authorized_deepseek_env  # noqa: E402

REGISTRATION_VERSION = "brand-matrix-gate-d-runtime-freeze-v1"
EXPECTED_MEDIA_DIGEST = "587d821315d896c414b382a1f277a07e1f7290f95cb8e0d829334cc53efc335b"
EXPECTED_GATE_A_MANIFEST_DIGEST = "14fed12141dc3b277c09c878a2a30ef71b445ce8ea31457c0122b403aeb48a06"

_FROZEN_QUERIES = {
    "brand": (
        "SELECT id,public_name,strategy_version,current_publication_projection_id "
        "FROM brands WHERE tenant_id=%s AND id=%s"
    ),
    "organizations": (
        "SELECT id,parent_organization_id,name,organization_level,enabled,business_data_kind "
        "FROM organizations WHERE tenant_id=%s ORDER BY id"
    ),
    "accounts": (
        "SELECT id,name,channel,enabled,control_organization_id,current_expression_profile_id,"
        "carrier_of_account_id,business_data_kind,platform_enabled FROM content_accounts "
        "WHERE tenant_id=%s AND brand_id=%s ORDER BY id"
    ),
    "profiles": (
        "SELECT id,account_id,content_role_id,version,identity_position,authority_boundary,"
        "audience_relationship,content_territories,default_production_conditions FROM "
        "account_expression_profile_versions WHERE tenant_id=%s ORDER BY id"
    ),
    "products": (
        "SELECT id,sku,facts,status,current_version_id,business_data_kind,record_kind "
        "FROM brand_products WHERE tenant_id=%s AND brand_id=%s ORDER BY id"
    ),
    "product_versions": (
        "SELECT id,product_id,version_number,facts,visibility_scope,scope_organization_ids "
        "FROM brand_product_versions WHERE tenant_id=%s AND brand_id=%s ORDER BY id"
    ),
    "library": (
        "SELECT id,category,title,version,status,visibility_scope,current_version_id "
        "FROM brand_library_entries WHERE tenant_id=%s AND brand_id=%s ORDER BY id"
    ),
    "library_versions": (
        "SELECT id,entry_id,version_number,version_label,visibility_scope,scope_organization_ids "
        "FROM brand_library_entry_versions WHERE tenant_id=%s AND brand_id=%s ORDER BY id"
    ),
    "projection": (
        "SELECT id,version_number,status,digest,contract_version FROM brand_publication_projections "
        "WHERE tenant_id=%s AND brand_id=%s ORDER BY id"
    ),
    "projection_items": (
        "SELECT id,projection_id,position,publication_role,published_text,source_ref,source_version,"
        "source_digest,visibility_scope,scope_organization_ids,effective_at,expires_at,authority_class,"
        "semantic_subject_type,semantic_subject_id,claim_key,scope_contract_version "
        "FROM brand_publication_projection_items WHERE tenant_id=%s AND brand_id=%s ORDER BY id"
    ),
    "qualifications": (
        "SELECT id,projection_id,projection_item_id,path_family,organization_id,involves_person,"
        "authorization_id,qualification_version,source_digest,digest FROM brand_relevance_qualifications "
        "WHERE tenant_id=%s AND brand_id=%s ORDER BY id"
    ),
    "authorizations": (
        "SELECT id,logical_account_id,organization_id,subject_ref,authorization_version,"
        "allowed_source_digest,allowed_usage,single_use,effective_at,expires_at,authorization_state,digest "
        "FROM content_authorizations WHERE tenant_id=%s AND brand_id=%s ORDER BY id"
    ),
    "authorization_reservations": (
        "SELECT authorization_id,task_id,run_id,task_lineage_id,status,actor_id,reservation_digest "
        "FROM content_authorization_reservations WHERE tenant_id=%s AND brand_id=%s ORDER BY authorization_id"
    ),
    "authorization_events": (
        "SELECT authorization_id,task_id,run_id,task_lineage_id,event_type,actor_id,event_digest "
        "FROM content_authorization_events WHERE tenant_id=%s AND brand_id=%s "
        "ORDER BY authorization_id,event_type,event_at"
    ),
    "media_assets": (
        "SELECT id,owner_organization_id,status,media_type,object_key,byte_size,original_filename,"
        "checksum_sha256,reference_note,visibility_scope,current_version_id FROM material_assets "
        "WHERE tenant_id=%s AND brand_id=%s AND object_key LIKE 'gated-media-masters/%%' ORDER BY id"
    ),
    "media_versions": (
        "SELECT version.id,version.asset_id,version.version_number,version.visibility_scope,"
        "version.scope_organization_ids,version.source_filename,version.source_checksum_sha256 "
        "FROM material_asset_versions version JOIN material_assets asset ON asset.tenant_id=version.tenant_id "
        "AND asset.brand_id=version.brand_id AND asset.id=version.asset_id WHERE version.tenant_id=%s "
        "AND version.brand_id=%s AND asset.object_key LIKE 'gated-media-masters/%%' ORDER BY version.id"
    ),
    "media_bindings": (
        "SELECT binding.id,binding.product_id,binding.asset_id,binding.usage_kind,binding.status "
        "FROM product_media_bindings binding JOIN material_assets asset ON asset.tenant_id=binding.tenant_id "
        "AND asset.brand_id=binding.brand_id AND asset.id=binding.asset_id WHERE binding.tenant_id=%s "
        "AND binding.brand_id=%s AND asset.object_key LIKE 'gated-media-masters/%%' ORDER BY binding.id"
    ),
}


def _stable(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _stable(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple)):
        return [_stable(item) for item in value]
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _canonical_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain one JSON object")
    return cast(dict[str, Any], value)


def database_input_fingerprint(database_url: str) -> tuple[str, dict[str, int], str]:
    document: dict[str, object] = {}
    counts: dict[str, int] = {}
    with psycopg.connect(database_url, row_factory=dict_row) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
        for name, query in _FROZEN_QUERIES.items():
            parameters = (TENANT_ID, BRAND_ID) if query.count("%s") == 2 else (TENANT_ID,)
            cursor.execute(query, parameters)
            rows = [_stable(dict(row)) for row in cursor.fetchall()]
            document[name] = rows
            counts[name] = len(rows)
    projection_rows = cast(list[dict[str, object]], document["projection"])
    confirmed = [row for row in projection_rows if row.get("status") == "confirmed"]
    if len(confirmed) != 1:
        raise ValueError("runtime freeze requires exactly one confirmed publication projection")
    expected_counts = {
        "accounts": 39,
        "authorization_events": 8,
        "authorization_reservations": 2,
        "authorizations": 6,
        "media_assets": 26,
        "media_bindings": 6,
        "media_versions": 26,
        "organizations": 7,
        "products": 4,
        "projection_items": 34,
        "qualifications": 30,
    }
    for key, expected in expected_counts.items():
        if counts.get(key) != expected:
            raise ValueError(f"runtime frozen database {key} count differs")
    return _canonical_digest(document), counts, str(confirmed[0]["digest"])


def build_registration(
    *,
    candidate_sha: str,
    database_url: str,
    env_path: Path,
) -> dict[str, Any]:
    if subprocess.run(
        ("git", "cat-file", "-e", f"{candidate_sha}^{{commit}}"),
        cwd=_ROOT,
        check=False,
        capture_output=True,
    ).returncode:
        raise ValueError("runtime candidate SHA is not a commit")
    changed_since_candidate = subprocess.run(
        ("git", "diff", "--name-only", candidate_sha, "HEAD"),
        cwd=_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    if any(not path.startswith("docs/BRAND-MATRIX-01/GateD-记录/") for path in changed_since_candidate):
        raise ValueError("runtime candidate differs from HEAD outside Gate D records")
    environment = parse_authorized_deepseek_env(env_path)
    model = environment["DEEPSEEK_MODEL"]
    media = _load_object(_ROOT / "docs/BRAND-MATRIX-01/GateD-记录/media-master-manifest.json")
    if media.get("manifest_digest") != EXPECTED_MEDIA_DIGEST:
        raise ValueError("runtime freeze media manifest digest differs")
    import_evidence = _load_object(_ROOT / "docs/BRAND-MATRIX-01/GateD-记录/import-rehearsal-evidence.json")
    first_round = import_evidence.get("round_one")
    if not isinstance(first_round, dict):
        raise ValueError("runtime freeze import evidence is incomplete")
    database_digest, database_counts, projection_digest = database_input_fingerprint(database_url)
    registration: dict[str, Any] = {
        "registration_version": REGISTRATION_VERSION,
        "runtime_candidate_sha": candidate_sha,
        "provider_requests_at_freeze": 0,
        "model": model,
        "temperature": 0,
        "max_retries": 0,
        "content_max_retries": 0,
        "transport_max_retries": 2,
        "retry_policy_version": "provider-transport-v1",
        "same_candidate_resume_policy": ("interrupted_card_only_after_explicit_user_continue"),
        "prompt_contracts": {
            "prompt_5_rev3_sha256": _file_sha256(_ROOT / "docs/BRAND-MATRIX-01/GateD-记录/Prompt-5-rev3.md"),
            "formal_suite_contract_sha256": _file_sha256(
                _ROOT / "docs/BRAND-MATRIX-01/GateD-记录/formal-suite-contract.json"
            ),
        },
        "gate_a_manifest_digest": _file_sha256(_ROOT / "docs/BRAND-MATRIX-01/GateA-素材合同/import-manifest.json"),
        "import_batch_digest": first_round.get("batch_digest"),
        "import_object_fingerprint": first_round.get("object_fingerprint"),
        "media_manifest_digest": media["manifest_digest"],
        "media_database_readback_digest": _load_object(
            _ROOT / "docs/BRAND-MATRIX-01/GateD-记录/media-database-readback.json"
        ).get("readback_digest"),
        "publication_projection_digest": projection_digest,
        "local_isolated_database_input_fingerprint": database_digest,
        "local_isolated_database_counts": database_counts,
        "status": "FROZEN_NO_PROVIDER_REQUESTS",
    }
    if registration["gate_a_manifest_digest"] != EXPECTED_GATE_A_MANIFEST_DIGEST:
        raise ValueError("Gate A manifest byte digest differs")
    registration["registration_digest"] = _canonical_digest(registration)
    return registration


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--app-database-url", required=True)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    registration = build_registration(
        candidate_sha=arguments.candidate_sha,
        database_url=arguments.app_database_url,
        env_path=arguments.env_file,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(registration, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        "GATED_RUNTIME_FROZEN "
        f"candidate={registration['runtime_candidate_sha']} "
        f"registration_digest={registration['registration_digest']} provider_requests=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
