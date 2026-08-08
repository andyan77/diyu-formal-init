from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from scripts.gated.brand_matrix_importer import (  # noqa: E402
    BRAND_ID,
    TENANT_ID,
    BrandMatrixImporter,
    seed_matrix_prestate,
)

_DATABASE_NAME = re.compile(r"diyu_gated_rehearsal_(one|two)\Z")
_TABLE_QUERIES = {
    "organizations": (
        "SELECT id,parent_organization_id,name,business_data_kind,organization_level,enabled "
        "FROM organizations WHERE tenant_id=%s ORDER BY id"
    ),
    "users": (
        "SELECT id,organization_id,display_name,enabled,entry_kind,business_data_kind "
        "FROM users WHERE tenant_id=%s ORDER BY id"
    ),
    "accounts": (
        "SELECT id,name,channel,enabled,control_organization_id,current_expression_profile_id,"
        "control_organization_source,carrier_of_account_id,business_data_kind,platform_enabled "
        "FROM content_accounts WHERE tenant_id=%s AND brand_id=%s ORDER BY id"
    ),
    "roles": (
        "SELECT id,name,voice_boundary,speaker_kind FROM content_roles "
        "WHERE tenant_id=%s AND brand_id=%s ORDER BY id"
    ),
    "account_roles": (
        "SELECT id,account_id,content_role_id FROM account_content_roles "
        "WHERE tenant_id=%s ORDER BY id"
    ),
    "profiles": (
        "SELECT id,account_id,content_role_id,version,identity_position,authority_boundary,"
        "audience_relationship,content_territories,default_production_conditions,created_by "
        "FROM account_expression_profile_versions WHERE tenant_id=%s ORDER BY id"
    ),
    "auth_grants": (
        "SELECT id,user_id,account_id,role_name,enabled,can_maintain_expression_profile "
        "FROM auth_grants WHERE tenant_id=%s ORDER BY id"
    ),
    "source_documents": (
        "SELECT id,source_id,embedded_title,provenance_filename,source_version,original_status,"
        "activation_status,authorization_source,visibility_scope,status,current_version_id "
        "FROM brand_source_documents WHERE tenant_id=%s AND brand_id=%s ORDER BY id"
    ),
    "source_versions": (
        "SELECT id,document_id,source_version,raw_sha256,normalized_sha256,source_size,content "
        "FROM brand_source_document_versions WHERE tenant_id=%s AND brand_id=%s ORDER BY id"
    ),
    "source_segments": (
        "SELECT id,document_id,document_version_id,segment_key,heading_path,source_locator,exact_text,"
        "semantic_kind,evidence_level,applicability,visibility_scope,digest "
        "FROM brand_source_segments WHERE tenant_id=%s AND brand_id=%s ORDER BY id"
    ),
    "products": (
        "SELECT id,sku,facts,display_name,source_kind,source_note,fact_version,applicability,status,"
        "visibility_scope,current_version_id,business_data_kind,record_kind "
        "FROM brand_products WHERE tenant_id=%s AND brand_id=%s ORDER BY id"
    ),
    "product_versions": (
        "SELECT id,product_id,version_number,display_name,facts,source_kind,source_note,applicability,"
        "visibility_scope,scope_organization_ids,created_by FROM brand_product_versions "
        "WHERE tenant_id=%s AND brand_id=%s ORDER BY id"
    ),
    "library_entries": (
        "SELECT id,category,title,source_note,content,version,status,visibility_scope,current_version_id,"
        "business_data_kind FROM brand_library_entries WHERE tenant_id=%s AND brand_id=%s ORDER BY id"
    ),
    "library_versions": (
        "SELECT id,entry_id,version_number,version_label,category,title,source_note,content,visibility_scope,"
        "scope_organization_ids,created_by FROM brand_library_entry_versions "
        "WHERE tenant_id=%s AND brand_id=%s ORDER BY id"
    ),
    "series": (
        "SELECT id,title,premise,account_id,logical_account_id,revision,business_data_kind FROM content_series "
        "WHERE tenant_id=%s AND brand_id=%s ORDER BY id"
    ),
    "authorizations": (
        "SELECT id,logical_account_id,organization_id,subject_ref,authorization_version,allowed_source_digest,"
        "allowed_usage,single_use,effective_at,expires_at,authorization_state,digest,recorded_by "
        "FROM content_authorizations WHERE tenant_id=%s AND brand_id=%s ORDER BY id"
    ),
    "projections": (
        "SELECT id,version_number,status,digest,contract_version,created_by,confirmed_by "
        "FROM brand_publication_projections WHERE tenant_id=%s AND brand_id=%s ORDER BY id"
    ),
    "projection_items": (
        "SELECT id,projection_id,position,publication_role,published_text,applicability,source_kind,source_ref,"
        "source_version,source_digest,visibility_scope,scope_organization_ids,effective_at,expires_at,"
        "authority_class,semantic_subject_type,semantic_subject_id,claim_key,scope_contract_version "
        "FROM brand_publication_projection_items WHERE tenant_id=%s AND brand_id=%s ORDER BY id"
    ),
    "qualifications": (
        "SELECT id,projection_id,projection_item_id,path_family,organization_id,involves_person,authorization_id,"
        "qualification_version,source_digest,digest FROM brand_relevance_qualifications "
        "WHERE tenant_id=%s AND brand_id=%s ORDER BY id"
    ),
    "import_audits": (
        "SELECT id,actor_id,event_type,entity_type,entity_id,metadata FROM activity_events "
        "WHERE tenant_id=%s AND entity_id=%s AND event_type='brand_matrix.imported' ORDER BY id"
    ),
    "legacy_tasks": (
        "SELECT id,account_id,created_by,weak_seed,primary_content_product,product_refs,media_format,"
        "production_conditions,content_context_snapshot,logical_account_id,business_data_kind "
        "FROM business_tasks WHERE tenant_id=%s AND brand_id=%s AND business_data_kind='legacy_hidden' ORDER BY id"
    ),
}


def _database_url(admin_url: str, database_name: str) -> str:
    parsed = urlsplit(admin_url)
    if parsed.scheme not in {"postgres", "postgresql"} or not parsed.path.startswith("/"):
        raise ValueError("admin URL must be a PostgreSQL URI")
    return urlunsplit(parsed._replace(path=f"/{database_name}"))


def _recreate_database(admin_url: str, database_name: str) -> str:
    if _DATABASE_NAME.fullmatch(database_name) is None:
        raise ValueError("refusing to recreate a database outside the Gate D rehearsal names")
    with psycopg.connect(admin_url, autocommit=True) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname=%s AND pid<>pg_backend_pid()",
            (database_name,),
        )
        cursor.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(database_name)))
        cursor.execute(
            sql.SQL("CREATE DATABASE {} OWNER diyu_migrator").format(sql.Identifier(database_name))
        )
    return _database_url(admin_url, database_name)


def _upgrade(repository_root: Path, database_url: str) -> None:
    environment = os.environ.copy()
    environment["DIYU_MIGRATOR_DATABASE_URL"] = database_url
    subprocess.run(
        (os.fspath(repository_root / ".venv/bin/python"), "-m", "alembic", "upgrade", "head"),
        cwd=repository_root,
        env=environment,
        check=True,
        stdout=subprocess.DEVNULL,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stable(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _stable(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple)):
        return [_stable(item) for item in value]
    if isinstance(value, (UUID, datetime)):
        return value.isoformat() if isinstance(value, datetime) else str(value)
    return value


def _fingerprint(database_url: str) -> tuple[str, dict[str, int]]:
    document: dict[str, object] = {}
    counts: dict[str, int] = {}
    with psycopg.connect(database_url, row_factory=dict_row) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
        for name, query in _TABLE_QUERIES.items():
            parameters = (TENANT_ID, BRAND_ID) if query.count("%s") == 2 else (TENANT_ID,)
            cursor.execute(query, parameters)
            rows = [_stable(dict(row)) for row in cursor.fetchall()]
            document[name] = rows
            counts[name] = len(rows)
    serialized = json.dumps(document, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(serialized).hexdigest(), counts


def _importer(repository_root: Path, database_url: str, source_root: Path) -> BrandMatrixImporter:
    contract_root = repository_root / "docs/BRAND-MATRIX-01/GateA-素材合同"
    return BrandMatrixImporter(
        database_url,
        contract_path=contract_root / "import-contract.json",
        manifest_path=contract_root / "import-manifest.json",
        windows_source_root=source_root,
        repository_root=repository_root,
    )


def rehearse(
    *,
    repository_root: Path,
    admin_url: str,
    source_root: Path,
    snapshot_path: Path,
) -> dict[str, object]:
    first_url = _recreate_database(admin_url, "diyu_gated_rehearsal_one")
    _upgrade(repository_root, first_url)
    prestate = seed_matrix_prestate(first_url)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ("pg_dump", "--format=custom", "--no-owner", "--file", os.fspath(snapshot_path), first_url),
        check=True,
    )
    first_importer = _importer(repository_root, first_url, source_root)
    first_plan = first_importer.dry_run()
    first_result = first_importer.apply(first_plan)
    first_fingerprint, first_counts = _fingerprint(first_url)

    second_url = _recreate_database(admin_url, "diyu_gated_rehearsal_two")
    subprocess.run(("pg_restore", "--no-owner", "--dbname", second_url, os.fspath(snapshot_path)), check=True)
    second_importer = _importer(repository_root, second_url, source_root)
    second_plan = second_importer.dry_run()
    second_result = second_importer.apply(second_plan)
    second_fingerprint, second_counts = _fingerprint(second_url)

    if first_plan.batch_digest != second_plan.batch_digest:
        raise AssertionError("the two import batch digests differ")
    if first_fingerprint != second_fingerprint or first_counts != second_counts:
        raise AssertionError("the two imported object fingerprints differ")
    return {
        "schema_revision": "20260818_45",
        "prestate": prestate,
        "prestate_snapshot_sha256": _sha256(snapshot_path),
        "round_one": {
            "batch_digest": first_plan.batch_digest,
            "object_fingerprint": first_fingerprint,
            "counts": first_counts,
            "inventory": first_result["inventory"],
            "formal_readback": first_result["formal_readback"],
        },
        "round_two": {
            "batch_digest": second_plan.batch_digest,
            "object_fingerprint": second_fingerprint,
            "counts": second_counts,
            "inventory": second_result["inventory"],
            "formal_readback": second_result["formal_readback"],
        },
        "byte_identical_batch_digest": True,
        "byte_identical_object_fingerprint": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--admin-url", required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--evidence-output", type=Path, required=True)
    arguments = parser.parse_args()
    result = rehearse(
        repository_root=arguments.repository_root.resolve(),
        admin_url=arguments.admin_url,
        source_root=arguments.source_root,
        snapshot_path=arguments.snapshot,
    )
    arguments.evidence_output.parent.mkdir(parents=True, exist_ok=True)
    arguments.evidence_output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    round_one = result["round_one"]
    if not isinstance(round_one, dict):
        raise AssertionError("round one evidence is invalid")
    print(
        json.dumps(
            {
                "batch_digest": round_one["batch_digest"],
                "object_fingerprint": round_one["object_fingerprint"],
                "rounds": 2,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
