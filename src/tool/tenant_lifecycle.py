from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from src.infrastructure.tenant_lifecycle import (
    TenantLifecycleClassifier,
    TenantLifecyclePlan,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply one reviewed TENANT-01 UUID lifecycle preimage.",
    )
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    plan = TenantLifecyclePlan.from_file(args.plan)
    result: dict[str, object] = {"plan": plan.public_manifest()}
    if args.apply:
        database_url = os.environ["DIYU_APP_DATABASE_URL"]
        result["result"] = TenantLifecycleClassifier(database_url).apply(plan)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
