from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

_SOURCE = (
    Path(__file__).resolve().parents[2]
    / "首批领域数据库知识数据"
    / "第六批-G零售经营陈列知识与墙面挂杆闭环包-v0.1"
    / "15-双应用全库机器导入候选-v0.2.jsonl"
)
_ACTIVE: dict[str, tuple[str, str]] = {
    "B-TPO-001": ("p1_context", "正式场合或关系期待会影响当前穿衣选择时"),
    "C-COMMUTE-001": ("p1_context", "同一弱种子明确出现两个以上连续生活或工作阶段时"),
    "D-DIRECT-001": ("p1_method", "当前 P1 任务需要先给出可执行选择结论时"),
    "D-CRAFT-001": ("p1_method", "当前 P1 成品需要去除重复并推进选择、边界或行动时"),
}


def import_system_asset_catalog(source: Path = _SOURCE) -> int:
    database_url = os.environ.get("DIYU_MIGRATOR_DATABASE_URL")
    if not database_url:
        raise RuntimeError("DIYU_MIGRATOR_DATABASE_URL is required to import system assets")
    records = _load_records(source)
    if len(records) != 243 or len({record["asset_id"] for record in records}) != 243:
        raise RuntimeError("C1 source must contain exactly 243 unique candidate assets")
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        for record in records:
            asset_id = str(record["asset_id"])
            status = "active" if asset_id in _ACTIVE else "review_candidate"
            cursor.execute(
                """
                INSERT INTO system_domain_assets
                    (asset_id, asset_type, schema_version, source_batch, display_name, structured_body,
                     supported_products, applicability, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (asset_id) DO NOTHING
                """,
                (
                    asset_id,
                    str(record["asset_type"]),
                    str(record["schema_version"]),
                    str(record["source_batch"]),
                    str(record.get("title") or record.get("name") or asset_id),
                    Jsonb(record),
                    Jsonb(record.get("supported_products") or record.get("applies_to") or []),
                    Jsonb(_boundaries(record)),
                    status,
                ),
            )
        for asset_id, (consumer, applicability) in _ACTIVE.items():
            cursor.execute(
                """
                INSERT INTO system_asset_activations (asset_id, consumer, applicability)
                VALUES (%s, %s, %s)
                ON CONFLICT (asset_id) DO NOTHING
                """,
                (asset_id, consumer, applicability),
            )
    return len(records)


def _load_records(source: Path) -> list[dict[str, Any]]:
    with source.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def _boundaries(record: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "when",
        "not_when",
        "tradeoffs",
        "anti_misuse",
        "applicability",
        "use_when",
        "avoid_when",
    )
    return {key: record[key] for key in keys if key in record}


if __name__ == "__main__":
    import_system_asset_catalog()
