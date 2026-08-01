from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from uuid import UUID

from src.infrastructure.tenant_source_importer import TenantSourceImporter
from src.shared.types import TenantManagementScope


def main() -> None:
    parser = argparse.ArgumentParser(description="Freeze or atomically activate one TENANT-01 source batch.")
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--tenant-id", type=UUID, required=True)
    parser.add_argument("--brand-id", type=UUID, required=True)
    parser.add_argument("--manager-user-id", type=UUID, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    database_url = os.environ["DIYU_APP_DATABASE_URL"]
    importer = TenantSourceImporter(database_url)
    scope = TenantManagementScope(args.tenant_id, args.manager_user_id, args.brand_id)
    plan = importer.dry_run(scope, args.source_root)
    result: dict[str, object] = {"plan": plan.public_manifest()}
    if args.apply:
        result["result"] = importer.apply(plan)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
