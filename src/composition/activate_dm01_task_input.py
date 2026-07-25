from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import cast

from src.brain.display_service import DisplayService
from src.brain.dm01_display_compiler import DM01DisplayCompiler
from src.infrastructure.display_repository import PostgresDisplayRepository
from src.infrastructure.dm01_task_input import DM01TaskInputProvisioner

_DEFAULT_RECORD = Path("config/task_inputs/diyu_clothing_keqiao_dm01_v1.json")


def main() -> None:
    """Load one task snapshot and produce the current reference plan for it."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    app_database_url = os.environ.get("DIYU_APP_DATABASE_URL")
    migrator_database_url = os.environ.get("DIYU_MIGRATOR_DATABASE_URL")
    if not app_database_url or not migrator_database_url:
        raise RuntimeError("both app and migrator database URLs are required")
    raw = json.loads(_DEFAULT_RECORD.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise RuntimeError("task input record must be an object")
    record = cast(dict[str, object], raw)
    activation = DM01TaskInputProvisioner(migrator_database_url).activate(record)
    result = DisplayService(
        PostgresDisplayRepository(app_database_url),
        DM01DisplayCompiler(),
    ).create(activation.scope, activation.inventory_text)
    logging.info(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
