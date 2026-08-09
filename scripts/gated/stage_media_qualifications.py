#!/usr/bin/env python3
"""Stage attested Gate D masters in the isolated database through formal repositories."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from scripts.gated.brand_matrix_importer import (  # noqa: E402
    ADMIN_USER_ID,
    BRAND_ID,
    TENANT_ID,
    matrix_id,
)
from scripts.gated.unlock_media_manifest import (  # noqa: E402
    ATTESTATION_ID,
    ATTESTATION_SCOPE,
)
from src.infrastructure.workbench_repository import (  # noqa: E402
    PostgresWorkbenchRepository,
)
from src.shared.types import TenantManagementScope  # noqa: E402

EXPECTED_MEDIA_MANIFEST_DIGEST = "587d821315d896c414b382a1f277a07e1f7290f95cb8e0d829334cc53efc335b"
HQ_ORGANIZATION_ID = matrix_id("organization:DIYU-HQ-001")


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain one JSON object")
    return cast(dict[str, Any], value)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _asset_row(database_url: str, asset_id: UUID) -> dict[str, Any] | None:
    with psycopg.connect(database_url, row_factory=dict_row) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
        cursor.execute(
            """
            SELECT asset.id, asset.status, asset.media_type, asset.object_key,
                   asset.byte_size, asset.original_filename, asset.checksum_sha256,
                   asset.reference_note, asset.visibility_scope,
                   asset.owner_organization_id, asset.current_version_id,
                   version.version_number, version.source_checksum_sha256
              FROM material_assets asset
              JOIN material_asset_versions version
                ON version.tenant_id=asset.tenant_id
               AND version.brand_id=asset.brand_id
               AND version.asset_id=asset.id
               AND version.id=asset.current_version_id
             WHERE asset.tenant_id=%s AND asset.brand_id=%s AND asset.id=%s
            """,
            (TENANT_ID, BRAND_ID, asset_id),
        )
        row = cursor.fetchone()
    return cast(dict[str, Any] | None, dict(row) if row is not None else None)


def _product_binding_rows(database_url: str, asset_id: UUID) -> list[dict[str, Any]]:
    with psycopg.connect(database_url, row_factory=dict_row) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
        cursor.execute(
            """
            SELECT binding.id, binding.status, product.sku,
                   product.current_version_id AS product_version_id
              FROM product_media_bindings binding
              JOIN brand_products product
                ON product.tenant_id=binding.tenant_id
               AND product.brand_id=binding.brand_id
               AND product.id=binding.product_id
             WHERE binding.tenant_id=%s AND binding.brand_id=%s
               AND binding.asset_id=%s
             ORDER BY product.sku, binding.id
            """,
            (TENANT_ID, BRAND_ID, asset_id),
        )
        rows = cursor.fetchall()
    return [cast(dict[str, Any], dict(row)) for row in rows]


def _validate_asset(
    row: dict[str, Any],
    *,
    asset_id: UUID,
    filename: str,
    checksum: str,
    byte_size: int,
) -> None:
    expected = {
        "id": asset_id,
        "status": "active",
        "media_type": "video",
        "object_key": f"gated-media-masters/{filename}",
        "byte_size": byte_size,
        "original_filename": filename,
        "checksum_sha256": checksum,
        "reference_note": (
            f"{ATTESTATION_ID}; scope={ATTESTATION_SCOPE}; Gate D isolated master"
        ),
        "visibility_scope": "brand_all",
        "owner_organization_id": HQ_ORGANIZATION_ID,
        "version_number": 1,
        "source_checksum_sha256": checksum,
    }
    for key, value in expected.items():
        if row.get(key) != value:
            raise ValueError(f"media asset {asset_id} field {key} differs")
    if row.get("current_version_id") is None:
        raise ValueError(f"media asset {asset_id} has no frozen current version")


def stage(
    database_url: str,
    master_root: Path,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    if manifest.get("manifest_digest") != EXPECTED_MEDIA_MANIFEST_DIGEST:
        raise ValueError("media manifest is not the unlocked frozen input")
    records = manifest.get("records")
    if not isinstance(records, list) or len(records) != 26:
        raise ValueError("media manifest must contain 26 records")
    repository = PostgresWorkbenchRepository(database_url)
    management_scope = TenantManagementScope(TENANT_ID, ADMIN_USER_ID, BRAND_ID)
    readback: list[dict[str, Any]] = []
    for raw in cast(list[dict[str, Any]], records):
        media_id = str(raw["media_id"])
        filename = str(raw["master_filename"])
        checksum = str(raw["master_sha256"])
        path = master_root / filename
        if not path.is_file() or _sha256(path) != checksum:
            raise ValueError(f"master checksum differs: {media_id}")
        if raw.get("release_status") != "PASS":
            raise ValueError(f"non-PASS media cannot enter isolated master registry: {media_id}")
        asset_id = matrix_id(f"media-master:{media_id}")
        row = _asset_row(database_url, asset_id)
        if row is None:
            repository.create_management_organization_material(
                management_scope,
                HQ_ORGANIZATION_ID,
                asset_id,
                f"{media_id} 笛语标识母版",
                "video",
                f"gated-media-masters/{filename}",
                path.stat().st_size,
                filename,
                checksum,
                f"{ATTESTATION_ID}; scope={ATTESTATION_SCOPE}; Gate D isolated master",
                "brand_all",
                (),
            )
            row = _asset_row(database_url, asset_id)
        if row is None:
            raise ValueError(f"media asset was not persisted: {media_id}")
        _validate_asset(
            row,
            asset_id=asset_id,
            filename=filename,
            checksum=checksum,
            byte_size=path.stat().st_size,
        )
        formal_bindings = tuple(str(value) for value in raw.get("formal_product_bindings", []))
        existing = _product_binding_rows(database_url, asset_id)
        existing_skus = {str(item["sku"]) for item in existing}
        unexpected = existing_skus - set(formal_bindings)
        if unexpected:
            raise ValueError(f"media {media_id} has unexpected formal bindings: {sorted(unexpected)}")
        for sku in formal_bindings:
            if sku not in existing_skus:
                repository.create_management_product_media_binding(
                    management_scope,
                    asset_id,
                    matrix_id(f"product:{sku}"),
                )
        bindings = _product_binding_rows(database_url, asset_id)
        if (
            {str(item["sku"]) for item in bindings} != set(formal_bindings)
            or any(item["status"] != "active" for item in bindings)
        ):
            raise ValueError(f"media {media_id} formal binding readback differs")
        readback.append(
            {
                "media_id": media_id,
                "asset_id": str(asset_id),
                "asset_version_id": str(row["current_version_id"]),
                "asset_version": int(row["version_number"]),
                "master_filename": filename,
                "master_sha256": checksum,
                "release_status": "PASS",
                "attestation_id": ATTESTATION_ID,
                "scope": ATTESTATION_SCOPE,
                "formal_product_bindings": [
                    {
                        "binding_id": str(item["id"]),
                        "product_id": str(matrix_id(f"product:{item['sku']}")),
                        "product_version_id": str(item["product_version_id"]),
                        "sku": str(item["sku"]),
                    }
                    for item in bindings
                ],
            }
        )
    if len(readback) != 26:
        raise AssertionError("media readback count drifted")
    binding_count = sum(len(item["formal_product_bindings"]) for item in readback)
    eligible = [item for item in readback if item["formal_product_bindings"]]
    distinct_products = sorted(
        {
            str(binding["sku"])
            for item in readback
            for binding in cast(list[dict[str, Any]], item["formal_product_bindings"])
        }
    )
    if binding_count != 6 or len(eligible) != 6 or len(distinct_products) != 4:
        raise ValueError("formal P5 media qualification inventory differs")
    result: dict[str, Any] = {
        "contract_version": "gate-d-media-database-readback-v1",
        "media_manifest_digest": manifest["manifest_digest"],
        "attestation_id": ATTESTATION_ID,
        "scope": ATTESTATION_SCOPE,
        "asset_count": 26,
        "formal_binding_count": binding_count,
        "p5_eligible_master_count": len(eligible),
        "distinct_formal_product_ids": distinct_products,
        "records": readback,
    }
    result["readback_digest"] = hashlib.sha256(
        json.dumps(result, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-database-url", required=True)
    parser.add_argument("--master-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--evidence-output", type=Path, required=True)
    arguments = parser.parse_args()
    result = stage(
        arguments.app_database_url,
        arguments.master_root,
        _load_object(arguments.manifest),
    )
    arguments.evidence_output.parent.mkdir(parents=True, exist_ok=True)
    arguments.evidence_output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        "GATED_MEDIA_DATABASE_OK "
        f"assets={result['asset_count']} bindings={result['formal_binding_count']} "
        f"p5_eligible={result['p5_eligible_master_count']} "
        f"readback_digest={result['readback_digest']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
