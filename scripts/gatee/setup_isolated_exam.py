#!/usr/bin/env python3
"""Rebuild one local-only Gate E exam database without touching production."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import psycopg

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from scripts.gated.brand_matrix_importer import (  # noqa: E402
    BRAND_ID,
    TENANT_ID,
    BrandMatrixImporter,
    seed_matrix_prestate,
)
from scripts.gated.rehearse_import import (  # noqa: E402
    _fingerprint,
    _recreate_database,
    _upgrade,
)

_DATABASE_NAME = "diyu_gated_rehearsal_one"


def rebuild(*, admin_url: str, source_root: Path) -> tuple[str, dict[str, object]]:
    """Create, migrate, seed, and import the one isolated database used by E-1'."""
    if not source_root.is_dir():
        raise RuntimeError("the read-only brand source root is unavailable")
    database_url = _recreate_database(admin_url, _DATABASE_NAME)
    _upgrade(_ROOT, database_url)
    prestate = seed_matrix_prestate(database_url)
    contract_root = _ROOT / "docs/BRAND-MATRIX-01/GateA-素材合同"
    importer = BrandMatrixImporter(
        database_url,
        contract_path=contract_root / "import-contract.json",
        manifest_path=contract_root / "import-manifest.json",
        windows_source_root=source_root,
        repository_root=_ROOT,
    )
    plan = importer.dry_run()
    applied = importer.apply(plan)
    fingerprint, counts = _fingerprint(database_url)
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
        cursor.execute(
            "SELECT digest FROM brand_publication_projections "
            "WHERE tenant_id=%s AND brand_id=%s AND status='confirmed'",
            (TENANT_ID, BRAND_ID),
        )
        row = cursor.fetchone()
    if row is None:
        raise RuntimeError("the isolated import has no confirmed publication projection")
    return database_url, {
        "setup_version": "brand-matrix-gatee-isolated-setup-v1",
        "database_kind": "local_isolated_import",
        "schema_revision": "20260818_45",
        "prestate": prestate,
        "batch_digest": plan.batch_digest,
        "object_fingerprint": fingerprint,
        "publication_projection_digest": str(row[0]),
        "counts": counts,
        "inventory": applied["inventory"],
        "formal_readback": applied["formal_readback"],
        "provider_requests": 0,
        "status": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--admin-url", required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    _, evidence = rebuild(
        admin_url=str(arguments.admin_url),
        source_root=arguments.source_root.resolve(),
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "batch_digest": evidence["batch_digest"],
                "provider_requests": 0,
                "status": "PASS",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
