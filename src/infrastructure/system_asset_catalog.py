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
    "B-TPO-001": ("content-production / P1", "正式场合或关系期待会影响当前穿衣选择时"),
    "C-COMMUTE-001": ("content-production / P1", "同一弱种子明确出现两个以上连续生活或工作阶段时"),
    "D-DIRECT-001": ("content-production / P1", "当前 P1 任务需要先给出可执行选择结论时"),
    "D-CRAFT-001": ("content-production / P1", "当前 P1 成品需要去除重复并推进选择、边界或行动时"),
    "A-TRANSLATE-001": ("content-production / P2", "当前 P2 商品解释"),
    "A-MAT-005": ("content-production / P2", "当前 P2 商品事实边界"),
    "D-EXPLAIN-001": ("content-production / P2", "当前 P2 解释方法"),
    "D-PERSONA-001": ("content-production / P3", "当前 P3 账号人格观察"),
    "D-PERSONA-002": ("content-production / P3", "当前 P3 人格关系回报"),
    "D-CRAFT-002": ("content-production / P3", "当前 P3 叙事方法"),
    "C-LOCAL-001": ("content-production / P4", "当前 P4 南城店近场信号"),
    "C-LOCAL-002": ("content-production / P4", "当前 P4 可迁移关系回报"),
    "D-RESPONSE-002": ("content-production / P4", "当前 P4 合法账号回应"),
    "B-VIS-001": ("content-production / P5", "当前 P5 可见造型命题"),
    "B-VIS-003": ("content-production / P5", "当前 P5 真实商品画面关系"),
    "B-VIS-005": ("content-production / P5", "当前 P5 动作与构图"),
    "B-VIS-006": ("content-production / P5", "当前 P5 低条件制作"),
    "E-ADAPT-001": ("content-production / M5-2-media", "明确从已授权源版本改编到当前目标时"),
    "E-FORM-001": ("content-production / M5-2-media", "当前主要产品需要决定媒体表达关系时"),
    "E-FORM-006": ("content-production / M5-2-media", "当前目标为小红书图文时"),
    "E-RESOURCE-002": ("content-production / M5-2-media", "当前媒体条件与主要产品同时出现时"),
    "E-RESOURCE-003": ("content-production / M5-2-media", "当前条件下只需要一份可执行主版本时"),
    "E-SOUND-001": ("content-production / M5-2-media", "当前目标为视频且声音承担内容时"),
    "E-TEXT-001": ("content-production / M5-2-media", "文字不能替代图像或动作证据时"),
    "E-TIME-001": ("content-production / M5-2-media", "视频需要无冗余自然时长时"),
    "E-TIME-002": ("content-production / M5-2-media", "用户明确要求压短时"),
    "E-VISUAL-001": ("content-production / M5-2-media", "当前成品需要首图、封面或首帧时"),
    "E-VISUAL-003": ("content-production / M5-2-media", "当前成品需要图片或镜头顺序时"),
    "G-TASK-003": ("display-merchandising / DM01", "DM01 墙面挂杆任务"),
    "G-TASK-004": ("display-merchandising / DM01", "DM01 墙面挂杆任务"),
    "G-FIXTURE-001": ("display-merchandising / DM01", "双层挂杆条件"),
    "G-FIXTURE-002": ("display-merchandising / DM01", "固定正挂条件"),
    "G-GROUP-001": ("display-merchandising / DM01", "上下搭配分组"),
    "G-FOCUS-001": ("display-merchandising / DM01", "焦点与回应"),
    "G-DENSITY-002": ("display-merchandising / DM01", "可抽取密度"),
    "G-SUB-001": ("display-merchandising / DM01", "同款替代"),
    "G-SUB-003": ("display-merchandising / DM01", "局部减密度"),
    "G-REV-003": ("display-merchandising / DM01", "自然反馈局部修订"),
    "GM-LAYOUT-001": ("display-merchandising / DM01", "搭配布局方法"),
    "GM-EXEC-001": ("display-merchandising / DM01", "现场执行方法"),
    "GM-REVISE-001": ("display-merchandising / DM01", "局部修订方法"),
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
                ON CONFLICT (asset_id) DO UPDATE SET status = EXCLUDED.status
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
                ON CONFLICT (asset_id) DO UPDATE SET consumer = EXCLUDED.consumer, applicability = EXCLUDED.applicability
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
