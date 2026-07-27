#!/usr/bin/env python3
"""Export deterministic, human-readable projections of existing source files.

This script never edits the JSON/JSONL sources.  It only writes the two CSV
projections beside itself when ``--write`` is supplied; otherwise it validates
that the checked-in projections are current.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import logging
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PROJECTION_DIR = Path(__file__).resolve().parent

ASSET_SOURCE = REPOSITORY_ROOT / (
    "首批领域数据库知识数据/第六批-G零售经营陈列知识与墙面挂杆闭环包-v0.1/15-双应用全库机器导入候选-v0.2.jsonl"
)
GOVERNANCE_SOURCE = REPOSITORY_ROOT / ("首批领域数据库知识数据/第五批：评测与导入包/12-系统资产运行治理-v1.json")
CAPABILITY_SOURCE = REPOSITORY_ROOT / "config/content_expression/capability-inventory-v1.jsonl"
FIXTURE_SOURCE = REPOSITORY_ROOT / (
    "首批领域数据库知识数据/第六批-G零售经营陈列知识与墙面挂杆闭环包-v0.1/12-双应用验证夹具注册表-v0.2.jsonl"
)

ASSET_OUTPUT = PROJECTION_DIR / "系统领域资产明细_V1.csv"
CAPABILITY_OUTPUT = PROJECTION_DIR / "内容表达能力明细_V1.csv"

EXPECTED_ASSET_SHA256 = "f0aa764a4e78198eb141f39a7ac7af33c3fc5b9d364fa07a58f066f0741eec11"
EXPECTED_GOVERNANCE_SHA256 = "c8cdf923d1933a5aaef51d1eda325b672d77899960c8041913fcf1a12ba6e507"
EXPECTED_CAPABILITY_SHA256 = "876290faeb93a123716d51c7534e2ad02f5ca871e9a0e0c9798b613292f37aaf"
EXPECTED_FIXTURE_SHA256 = "733cbece915acd42ef1a2f0280e7823f2fb6dd69a30f7afd39a41275cd7a4bf4"

LOGGER = logging.getLogger(__name__)

ASSET_FIELDS = [
    "asset_id",
    "名称",
    "asset_type",
    "category",
    "source_batch",
    "candidate_status",
    "runtime_lifecycle",
    "consumer",
    "applicability",
    "runtime_applicability",
    "supported_products",
    "supported_display_contracts",
    "required_inputs",
    "use_when",
    "avoid_when",
    "not_when",
    "gold_fixture_refs",
    "valid_until",
    "superseded_by",
    "能力边界摘要",
    "真源路径",
    "source_sha256",
]

CAPABILITY_FIELDS = [
    "stable_id",
    "来源分类",
    "原始标签",
    "内部五轴",
    "标准名称",
    "capability_state",
    "是否进入精简V1",
    "是否体型相关",
    "依赖条件",
    "gap_type",
    "缺口去向",
    "evidence_refs",
    "supporting_asset_ids",
    "代表性成品或测试",
    "能力边界",
    "真源路径",
    "source_sha256",
]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def _compact(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, list):
        return "；".join(_compact(item) for item in value)
    if isinstance(value, dict):
        if not value:
            return ""
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _first(record: dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        value = record.get(key)
        if value not in (None, "", [], {}):
            return value
    return ""


def _join_present(record: dict[str, Any], keys: Iterable[str]) -> str:
    values: list[str] = []
    for key in keys:
        rendered = _compact(record.get(key))
        if rendered and rendered not in values:
            values.append(rendered)
    return "；".join(values)


def _asset_rows() -> list[dict[str, str]]:
    records = _read_jsonl(ASSET_SOURCE)
    governance = json.loads(GOVERNANCE_SOURCE.read_text(encoding="utf-8"))
    active_by_id = {item["asset_id"]: item for item in governance["assets"]}

    rows: list[dict[str, str]] = []
    for record in records:
        asset_id = record["asset_id"]
        runtime = active_by_id.get(asset_id)
        rows.append(
            {
                "asset_id": asset_id,
                "名称": _compact(_first(record, ("title", "display_name", "name", "topic"))),
                "asset_type": _compact(record.get("asset_type")),
                "category": _compact(record.get("category")),
                "source_batch": _compact(record.get("source_batch")),
                "candidate_status": _compact(record.get("status")),
                "runtime_lifecycle": ("active" if runtime else _compact(record.get("status"))),
                "consumer": _compact(runtime.get("consumer")) if runtime else "",
                "applicability": _compact(record.get("applicability")),
                "runtime_applicability": (_compact(runtime.get("applicability")) if runtime else ""),
                "supported_products": _compact(record.get("supported_products")),
                "supported_display_contracts": _compact(record.get("supported_display_contracts")),
                "required_inputs": _compact(record.get("required_inputs")),
                "use_when": _compact(_first(record, ("use_when", "when"))),
                "avoid_when": _compact(record.get("avoid_when")),
                "not_when": _compact(record.get("not_when")),
                "gold_fixture_refs": _compact(record.get("gold_fixture_refs")),
                "valid_until": _compact(record.get("valid_until")),
                "superseded_by": _compact(record.get("superseded_by")),
                "能力边界摘要": _join_present(
                    record,
                    (
                        "anti_misuse",
                        "avoid_when",
                        "not_when",
                        "must_not_impersonate",
                        "unsuitable_topics",
                        "failure_pattern",
                    ),
                ),
                "真源路径": ASSET_SOURCE.relative_to(REPOSITORY_ROOT).as_posix(),
                "source_sha256": EXPECTED_ASSET_SHA256,
            }
        )
    return rows


def _capability_rows() -> list[dict[str, str]]:
    records = _read_jsonl(CAPABILITY_SOURCE)
    rows: list[dict[str, str]] = []
    for record in records:
        evidence_refs = record.get("evidence_refs", [])
        supporting_asset_ids = [
            ref.removeprefix("system_domain_assets:")
            for ref in evidence_refs
            if ref.startswith("system_domain_assets:")
        ]
        representative_refs = [
            ref
            for ref in evidence_refs
            if ref.startswith("tests/") or ref.startswith("docs/") or "artifact" in ref.lower()
        ]
        rows.append(
            {
                "stable_id": _compact(record.get("stable_id")),
                "来源分类": _compact(record.get("source_group")),
                "原始标签": _compact(record.get("source_label")),
                "内部五轴": _compact(record.get("mapped_axis")),
                "标准名称": _compact(record.get("normalized_label")),
                "capability_state": _compact(record.get("capability_state")),
                "是否进入精简V1": _compact(record.get("visible_in_compact_v1", False)),
                "是否体型相关": _compact(record.get("body_related", False)),
                "依赖条件": _compact(record.get("dependencies")),
                "gap_type": _compact(record.get("gap_type")),
                "缺口去向": _compact(record.get("destination")),
                "evidence_refs": _compact(evidence_refs),
                "supporting_asset_ids": _compact(supporting_asset_ids),
                "代表性成品或测试": _compact(representative_refs),
                "能力边界": _join_present(
                    record,
                    ("boundary_note", "preserved_aspect", "restrained_variant"),
                ),
                "真源路径": CAPABILITY_SOURCE.relative_to(REPOSITORY_ROOT).as_posix(),
                "source_sha256": EXPECTED_CAPABILITY_SHA256,
            }
        )
    return rows


def _render_csv(rows: list[dict[str, str]], fields: list[str]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def _assert_projection_contracts(
    asset_rows: list[dict[str, str]],
    capability_rows: list[dict[str, str]],
) -> None:
    actual_hashes = {
        "asset": _sha256(ASSET_SOURCE),
        "governance": _sha256(GOVERNANCE_SOURCE),
        "capability": _sha256(CAPABILITY_SOURCE),
        "fixture": _sha256(FIXTURE_SOURCE),
    }
    expected_hashes = {
        "asset": EXPECTED_ASSET_SHA256,
        "governance": EXPECTED_GOVERNANCE_SHA256,
        "capability": EXPECTED_CAPABILITY_SHA256,
        "fixture": EXPECTED_FIXTURE_SHA256,
    }
    if actual_hashes != expected_hashes:
        raise SystemExit(f"source SHA drifted; review the source change before refreshing projections: {actual_hashes}")
    if len(asset_rows) != 243:
        raise SystemExit(f"asset projection must contain 243 rows, got {len(asset_rows)}")
    if len({row["asset_id"] for row in asset_rows}) != 243:
        raise SystemExit("asset_id values are not unique")
    asset_type_counts = Counter(row["asset_type"] for row in asset_rows)
    expected_asset_type_counts = {
        "domain_knowledge": 99,
        "generation_method": 58,
        "industry_role_template": 8,
        "evaluation_rule": 78,
    }
    if asset_type_counts != expected_asset_type_counts:
        raise SystemExit(f"asset type counts drifted: {dict(asset_type_counts)}")
    if len(capability_rows) != 119:
        raise SystemExit(f"capability projection must contain 119 rows, got {len(capability_rows)}")
    if len({row["stable_id"] for row in capability_rows}) != 119:
        raise SystemExit("stable_id values are not unique")
    active_rows = [row for row in asset_rows if row["runtime_lifecycle"] == "active"]
    if len(active_rows) != 41:
        raise SystemExit(f"runtime active projection must contain 41 rows, got {len(active_rows)}")
    active_type_counts = Counter(row["asset_type"] for row in active_rows)
    if active_type_counts != {"domain_knowledge": 20, "generation_method": 21}:
        raise SystemExit(f"runtime active type counts drifted: {dict(active_type_counts)}")
    capability_state_counts = Counter(row["capability_state"] for row in capability_rows)
    expected_capability_state_counts = {
        "verified": 10,
        "composable": 64,
        "experimental": 6,
        "unsupported": 38,
        "explicitly_out_of_scope": 1,
    }
    if capability_state_counts != expected_capability_state_counts:
        raise SystemExit(f"capability state counts drifted: {dict(capability_state_counts)}")
    compact_rows = [row for row in capability_rows if row["是否进入精简V1"] == "是"]
    compact_body_counts = Counter(row["是否体型相关"] for row in compact_rows)
    if compact_body_counts != {"否": 21, "是": 4}:
        raise SystemExit(f"compact V1 visibility/body counts drifted: {dict(compact_body_counts)}")
    prefix_counts = Counter(
        "source_gap" if row["stable_id"].startswith("CAT-SOURCE-GAP-") else row["stable_id"].split("-")[1].lower()
        for row in capability_rows
    )
    if prefix_counts != {"style": 20, "topic": 55, "genre": 41, "source_gap": 3}:
        raise SystemExit(f"catalog axis counts drifted: {dict(prefix_counts)}")
    linked_capabilities = [row for row in capability_rows if row["supporting_asset_ids"]]
    if len(linked_capabilities) != 6:
        raise SystemExit(
            "only the six directly evidenced capabilities may contain "
            f"supporting_asset_ids, got {len(linked_capabilities)}"
        )
    fixture_rows = _read_jsonl(FIXTURE_SOURCE)
    if len(fixture_rows) != 123:
        raise SystemExit(f"fixture registry must contain 123 rows, got {len(fixture_rows)}")
    governance = json.loads(GOVERNANCE_SOURCE.read_text(encoding="utf-8"))
    if len(governance.get("fixture_bindings", [])) != 4:
        raise SystemExit("runtime governance must contain exactly 4 fixture bindings")


def _check_or_write(path: Path, content: str, write: bool) -> None:
    if write:
        path.write_text(content, encoding="utf-8", newline="")
        return
    if not path.exists() or path.read_text(encoding="utf-8") != content:
        raise SystemExit(f"projection is stale: {path.relative_to(REPOSITORY_ROOT)}")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--write",
        action="store_true",
        help="write the two checked-in CSV projections; JSON/JSONL sources stay untouched",
    )
    args = parser.parse_args()

    asset_rows = _asset_rows()
    capability_rows = _capability_rows()
    _assert_projection_contracts(asset_rows, capability_rows)
    _check_or_write(
        ASSET_OUTPUT,
        _render_csv(asset_rows, ASSET_FIELDS),
        args.write,
    )
    _check_or_write(
        CAPABILITY_OUTPUT,
        _render_csv(capability_rows, CAPABILITY_FIELDS),
        args.write,
    )
    mode = "written" if args.write else "current"
    LOGGER.info(f"projections {mode}: assets={len(asset_rows)}, capabilities={len(capability_rows)}")


if __name__ == "__main__":
    main()
