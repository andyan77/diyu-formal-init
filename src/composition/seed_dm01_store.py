from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import cast

from src.infrastructure.dm01_store_seed import DM01StoreSeedWriter

_DEFAULT_RECORD = Path("config/task_inputs/diyu_clothing_keqiao_dm01_v1.json")


def main() -> None:
    """Idempotently configure one wall structure and the default seed for its next task.

    This command is configuration only. It creates no task, run or version: a real reference plan is
    always started by an authenticated display user through the ordinary API.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    migrator_database_url = os.environ.get("DIYU_MIGRATOR_DATABASE_URL")
    if not migrator_database_url:
        raise RuntimeError("the migrator database URL is required")
    raw = json.loads(_DEFAULT_RECORD.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise RuntimeError("task input record must be an object")
    record = cast(dict[str, object], raw)
    seed = DM01StoreSeedWriter(migrator_database_url).seed(record)
    logging.info(
        json.dumps(
            {
                "seeded": True,
                "store_id": str(seed.store_id),
                "store_name": seed.store_name,
                "structure_version": seed.structure_version,
                "task_input_version": seed.task_input_version,
                "seed_products": seed.product_count,
                "tasks_created": 0,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
