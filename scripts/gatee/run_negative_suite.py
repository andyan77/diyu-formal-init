#!/usr/bin/env python3
"""Run Gate E pre-provider negative cases against one isolated imported database."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from unittest.mock import Mock

import psycopg

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from scripts.gated.brand_matrix_importer import (  # noqa: E402
    BRAND_ID,
    OPERATOR_IDS,
    TENANT_ID,
    matrix_id,
)
from src.brain.content_service import ContentService  # noqa: E402
from src.infrastructure.postgres_repository import PostgresContentRepository  # noqa: E402
from src.shared.types import ProductFact, RequestedControls, TrustedScope  # noqa: E402


class OutsideQualityFixtureRepository(PostgresContentRepository):
    """Supply a synthetic product outside the four imported quality-record subjects."""

    def load_product_facts(self, scope: TrustedScope, weak_seed: str) -> tuple[ProductFact, ...]:
        del scope, weak_seed
        return (
            ProductFact(
                "DEMO-TEST-CSPU-NO-QC",
                {"category": "演示测试外套"},
                display_name="演示测试外套",
            ),
        )


def _scope(account_code: str) -> TrustedScope:
    organization = "DIYU-HQ-001"
    return TrustedScope(
        TENANT_ID,
        OPERATOR_IDS[organization],
        BRAND_ID,
        matrix_id(f"account:{account_code}"),
    )


def _object_counts(database_url: str) -> dict[str, int]:
    queries = {
        "tasks": "SELECT count(*) FROM business_tasks WHERE tenant_id=%s AND brand_id=%s",
        "runs": (
            "SELECT count(*) FROM generation_runs run JOIN business_tasks task "
            "ON task.tenant_id=run.tenant_id AND task.id=run.task_id "
            "WHERE task.tenant_id=%s AND task.brand_id=%s"
        ),
        "versions": (
            "SELECT count(*) FROM content_versions version JOIN business_tasks task "
            "ON task.tenant_id=version.tenant_id AND task.id=version.task_id "
            "WHERE task.tenant_id=%s AND task.brand_id=%s"
        ),
    }
    counts: dict[str, int] = {}
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
        for key, query in queries.items():
            cursor.execute(query, (TENANT_ID, BRAND_ID))
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError(f"negative suite count query returned no row: {key}")
            counts[key] = int(row[0])
    return counts


def run(database_url: str) -> dict[str, object]:
    before = _object_counts(database_url)
    generator = Mock()
    h04 = ContentService(OutsideQualityFixtureRepository(database_url), generator)
    missing_quality = h04.create_from_weak_seed(
        _scope("H04"),
        "出厂之前你们都检查什么？以本次操作员绑定的商品为例。",
        primary_product_override="product_truth",
    )
    h01 = ContentService(PostgresContentRepository(database_url), generator)
    missing_p5 = h01.create_from_weak_seed(
        _scope("H01"),
        "请做一条商品视觉内容。",
        controls=RequestedControls(product_media_intent=True),
        primary_product_override="visual_styling_story",
    )
    after = _object_counts(database_url)
    if (
        missing_quality.get("kind") != "question"
        or "缺少可消费的检查环节或品控记录" not in str(missing_quality.get("message", ""))
        or "不会把它自动改写成商品介绍" not in str(missing_quality.get("message", ""))
        or missing_p5.get("kind") != "question"
        or "至少两件不同商品" not in str(missing_p5.get("message", ""))
        or generator.method_calls
        or before != after
    ):
        raise RuntimeError("Gate E negative suite failed closed incorrectly or polluted the database")
    return {
        "suite_version": "brand-matrix-gatee-negative-v1",
        "database_kind": "local_isolated_import",
        "cases": [
            {
                "case_id": "NEG-H04-P2-MISSING-QUALITY",
                "result": "PASS",
                "provider_requests": 0,
                "task_run_version_delta": [0, 0, 0],
                "observed_kind": missing_quality["kind"],
            },
            {
                "case_id": "NEG-P5-MISSING-BINDINGS",
                "result": "PASS",
                "provider_requests": 0,
                "task_run_version_delta": [0, 0, 0],
                "observed_kind": missing_p5["kind"],
            },
        ],
        "counts_before": before,
        "counts_after": after,
        "provider_requests": 0,
        "pollution_delta": {key: after[key] - before[key] for key in before},
        "status": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    result = run(str(arguments.database_url))
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"cases": 2, "provider_requests": 0, "status": "PASS"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
