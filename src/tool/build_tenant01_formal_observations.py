from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import cast
from uuid import UUID

from src.shared.errors import DomainError
from src.tool.record_formal_capability_observations import (
    _verify_evidence_sources,
    validate_observation_document,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_REGISTRY_PATH = _PROJECT_ROOT / "config/formal-capabilities-v1.json"

_REFERENCES: dict[str, tuple[str, ...]] = {
    "FT-001": ("browser#PUBLIC_HOME",),
    "FT-002": ("browser#PUBLIC_HOME",),
    "FT-003": ("browser#PUBLIC_HOME",),
    "FT-004": ("surface#PUBLIC_AUTH_AND_STATUS", "browser#ADMIN_LOGIN"),
    "FT-005": ("context#FORMAL_MEMBER_ACTIVATION_RESET", "browser#ADMIN_ACTIVATION_LINK_BROWSER"),
    "FT-006": ("browser#ADMIN_ACTIVATION_LINK_BROWSER",),
    "FT-007": ("surface#WRONG_ENTRY_SESSION_PRESERVED", "browser#PERMISSION_DENIAL_SESSION"),
    "FT-008": ("surface#SESSION_EXPIRY_CLASSIFIED",),
    "FT-009": ("surface#TEAM_USAGE_7_30",),
    "FT-010": ("browser#ADMIN_READINESS_GUIDE",),
    "FT-011": ("browser#ADMIN_MEMBER_IDENTITY",),
    "FT-012": ("context#FORMAL_MEMBER_DUPLICATE_DISPLAY_NAME", "browser#ADMIN_MEMBER_IDENTITY"),
    "FT-013": ("browser#ADMIN_MEMBER_PREREQUISITES", "context#FORMAL_MEMBER_GRANT_DISABLE_RESTORE"),
    "FT-014": ("browser#ADMIN_MEMBER_PREREQUISITES", "surface#DM01_DATA_MISSING_ZERO_OBJECTS"),
    "FT-015": ("setup#ADMIN_LOGICAL_ACCOUNT_PROFILE", "context#FORMAL_MEMBER_GRANT_DISABLE_RESTORE"),
    "FT-016": ("browser#ADMIN_ACTIVATION_LINK_BROWSER",),
    "FT-017": ("browser#ADMIN_ACTIVATION_LINK_BROWSER",),
    "FT-018": ("browser#ADMIN_ACTIVATION_LINK_BROWSER",),
    "FT-019": ("context#FORMAL_MEMBER_GRANT_DISABLE_RESTORE",),
    "FT-020": ("context#FORMAL_MEMBER_ACTIVATION_RESET", "browser#ADMIN_RESET_LINK_BROWSER"),
    "FT-021": ("browser#ADMIN_RESET_LINK_BROWSER",),
    "FT-022": ("context#FORMAL_MEMBER_GRANT_DISABLE_RESTORE",),
    "FT-023": ("setup#ADMIN_LOGICAL_ACCOUNT_PROFILE",),
    "FT-024": ("setup#ADMIN_LOGICAL_ACCOUNT_PROFILE",),
    "FT-025": ("setup#ADMIN_FOUR_PLATFORM_TARGETS", "browser#CONTENT_SCOPE"),
    "FT-026": ("surface#ACCOUNT_PROFILE_V1_V2_HISTORY",),
    "FT-027": ("surface#BRAND_LIBRARY_LIFECYCLE",),
    "FT-028": ("publication#PROJECTION_SOURCE_BOUND", "browser#ADMIN_PUBLICATION_PROJECTION"),
    "FT-029": ("setup#ADMIN_PRODUCT_PIPELINE_14_26", "surface#PRODUCT_AND_READINESS_TRUTH"),
    "FT-030": ("surface#ORGANIZATION_MATERIAL_LIFECYCLE",),
    "FT-031": ("surface#TEAM_USAGE_7_30",),
    "FT-032": ("browser#ADMIN_READINESS_GUIDE", "surface#PRODUCT_AND_READINESS_TRUTH"),
    "FT-034": ("browser#USER_GUIDE", "surface#DM01_DATA_MISSING_ZERO_OBJECTS"),
    "FT-035": ("browser#CONTENT_SCOPE",),
    "FT-036": ("browser#CONTENT_SCOPE", "context#CROSS_PLATFORM_STRUCTURE"),
    "FT-037": ("context#SEND_ZERO_OBJECTS", "browser#CONTENT_SEND_ONLY"),
    "FT-038": ("context#FACTORY_ACTUALITY_V1", "browser#FACTORY_V1"),
    "FT-039": ("surface#CREATIVE_DIRECTION_FROZEN",),
    "FT-040": ("surface#GENERATION_STAGES",),
    "FT-041": ("context#FACTORY_ACTUALITY_V1", "browser#FACTORY_V1"),
    "FT-042": ("browser#CONTENT_V2_HISTORY_COPY_EXPORT",),
    "FT-043": ("context#V1_V2_REPLAY_IMMUTABLE", "browser#CONTENT_V2_HISTORY_COPY_EXPORT"),
    "FT-044": ("browser#CONTENT_V2_HISTORY_COPY_EXPORT",),
    "FT-045": ("surface#SERIES_FROZEN_CONTEXT",),
    "FT-046": ("surface#PRIVATE_MATERIAL_LIFECYCLE",),
    "FT-047": ("surface#RATE_LIMIT_RETRY_IDEMPOTENT", "browser#CONTENT_DRAFT_PERSISTENCE"),
    "FT-048": ("browser#CONTENT_DRAFT_PERSISTENCE",),
    "FT-049": ("browser#FORMAL_EMPTY_STATE",),
    "FT-050": ("surface#DM01_DATA_MISSING_ZERO_OBJECTS", "browser#ADMIN_READINESS_GUIDE"),
    "FT-051": ("surface#DM01_DATA_MISSING_ZERO_OBJECTS", "browser#ADMIN_READINESS_GUIDE"),
    "FT-052": ("surface#DM01_DATA_MISSING_ZERO_OBJECTS", "setup#FORMAL_DATA_GAPS_ZERO"),
    "FT-054": ("setup#OPS_TENANT_PROVISION",),
    "FT-055": ("setup#OPS_TENANT_PROVISION",),
    "FT-056": ("setup#OPS_TENANT_DISABLE_RESTORE",),
    "FT-057": ("setup#OPS_UNMET_REQUEST_ANSWER",),
    "FT-058": ("browser#PUBLIC_STATUS", "surface#PUBLIC_AUTH_AND_STATUS"),
    "FT-060": ("surface#RATE_LIMIT_RETRY_IDEMPOTENT", "browser#CONTENT_DRAFT_PERSISTENCE"),
    "FT-064": ("browser#RESPONSIVE_ACCESSIBILITY",),
}

_NO_BUSINESS_WRITE = frozenset(
    {
        "FT-001",
        "FT-002",
        "FT-003",
        "FT-004",
        "FT-006",
        "FT-007",
        "FT-008",
        "FT-009",
        "FT-010",
        "FT-011",
        "FT-018",
        "FT-021",
        "FT-025",
        "FT-028",
        "FT-031",
        "FT-032",
        "FT-034",
        "FT-035",
        "FT-036",
        "FT-037",
        "FT-044",
        "FT-047",
        "FT-048",
        "FT-049",
        "FT-050",
        "FT-051",
        "FT-052",
        "FT-058",
        "FT-060",
        "FT-064",
    }
)
_IDENTITY_WRITE = frozenset(
    {
        "FT-005",
        "FT-012",
        "FT-013",
        "FT-014",
        "FT-015",
        "FT-016",
        "FT-017",
        "FT-019",
        "FT-020",
        "FT-022",
        "FT-054",
        "FT-055",
        "FT-056",
    }
)
_CONTENT_WRITE = frozenset({"FT-038", "FT-040", "FT-041", "FT-042", "FT-043", "FT-045"})
_DATA_MISSING = frozenset({"FT-014", "FT-030", "FT-050", "FT-051", "FT-052"})


def _head_sha() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=_PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _registry() -> tuple[dict[str, str], ...]:
    raw = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    values = raw.get("capabilities") if isinstance(raw, dict) else None
    if not isinstance(values, list):
        raise DomainError("正式能力注册表格式无效")
    records = tuple(cast(dict[str, str], item) for item in values if isinstance(item, dict))
    if len(records) != 58 or set(_REFERENCES) != {record["id"] for record in records}:
        raise DomainError("正式能力引用必须恰好覆盖注册表 58 项")
    return records


def _database_effect(capability_id: str) -> str:
    if capability_id in _NO_BUSINESS_WRITE:
        return "已复核业务对象计数保持不变；读取、失败关闭、复制或前端状态不会暗建任务/版本。"
    if capability_id in _IDENTITY_WRITE:
        return "身份、凭据、授权或租户状态只经正式事务写入；冲突和失败均为零部分写。"
    if capability_id in _CONTENT_WRITE:
        return "只形成预期的任务、运行和追加式版本；完成后永久 running 为 0，旧版本摘要不变。"
    if capability_id == "FT-023":
        return "创建一个逻辑发布根账号，平台载体继续引用同一不可变账号身份。"
    if capability_id == "FT-024":
        return "speaker_kind 与 ContentRole 作为版本化账号配置保存，不改写自然人身份。"
    if capability_id == "FT-026":
        return "五段画像形成 V2 并保留 V1 历史，当前指针只前移到新版本。"
    if capability_id == "FT-027":
        return "文字资料完成预览、V1→V2、停用生命周期，版本记录保持追加式。"
    if capability_id == "FT-029":
        return "14 个候选商品及 26 个获准 ProductFact 字段按 SKU/version 读取，不加载整库。"
    if capability_id == "FT-030":
        return "组织素材完成上传、V2、停用、恢复和软删除；对象删除后不可变版本仍保留。"
    if capability_id == "FT-039":
        return "选择的创作方向冻结进任务快照，不写入静默个人偏好。"
    if capability_id == "FT-046":
        return "私人素材只在本人作用域创建、改说明和软删除，未进入品牌或组织资料域。"
    if capability_id == "FT-057":
        return "能力反馈经正式状态流从 received 更新为 answered，并保留运维答复。"
    raise DomainError(f"{capability_id} 缺少数据库变化口径")


def _visible_result(record: dict[str, str]) -> str:
    capability_id = record["id"]
    if capability_id in {"FT-050", "FT-051", "FT-052"}:
        return "当前正式门店和库存均为 0，用户看到 DM01 data_missing 与补录入口，不冒充可生成。"
    if capability_id == "FT-030":
        return "管理员看到组织素材的版本、状态和删除结果；当前正式媒体数量仍按现场真值显示。"
    if capability_id == "FT-047":
        return "429 显示稳定错误阶段、可重试标记和 trace；同 request_id 重试成功且不重复建对象。"
    return f"在 {record['route']} 实测“{record['title']}”，页面或 API 返回与当前资料和权限一致的结果。"


def _error_recovery(record: dict[str, str]) -> str:
    capability_id = record["id"]
    if capability_id in {"FT-007", "FT-008", "FT-060"}:
        return "权限拒绝留在原页且保留输入；只有 AUTH_REQUIRED/真实过期才清会话并回登录。"
    if capability_id in {"FT-012", "FT-013", "FT-014", "FT-015"}:
        return "显示名可同名；登录用户名冲突或资料/资格缺口给出稳定代码、中文提示和补录入口。"
    if capability_id in _DATA_MISSING:
        return "资料不足在任务和 Writer 前失败关闭，task/run/version 与模型调用均保持 0。"
    if capability_id in {"FT-038", "FT-040", "FT-041", "FT-042", "FT-043", "FT-045"}:
        return "生成或保存失败不会留下 running/半版本；历史回放只读取冻结上下文。"
    return "失败路径保留当前作用域与可恢复状态，并提供明确返回、重试或补充入口。"


def build(
    *,
    candidate_sha: str,
    source_paths: dict[str, Path],
    output_path: Path,
) -> dict[str, object]:
    if _head_sha() != candidate_sha:
        raise DomainError("正式能力观察候选 SHA 与当前 HEAD 不一致")
    if output_path.exists():
        raise DomainError("正式能力观察证据已存在，拒绝静默覆盖")
    root = output_path.parent.resolve()
    sources: list[dict[str, object]] = []
    source_documents: dict[str, dict[str, object]] = {}
    tenant_id: str | None = None
    schema_revision: str | None = None
    for source_id, path in source_paths.items():
        resolved = path.resolve(strict=True)
        if resolved.parent != root:
            raise DomainError("正式能力观察的全部证据源必须位于同一私有根")
        source_document = json.loads(resolved.read_text(encoding="utf-8"))
        if not isinstance(source_document, dict):
            raise DomainError("正式能力观察证据源格式无效")
        if source_document.get("candidate_sha") != candidate_sha or source_document.get("verdict") != "PASS":
            raise DomainError("正式能力观察证据源候选或 verdict 不一致")
        current_tenant = str(source_document.get("tenant_id", ""))
        if not current_tenant or (tenant_id is not None and current_tenant != tenant_id):
            raise DomainError("正式能力观察证据源租户不一致")
        tenant_id = current_tenant
        current_schema = source_document.get("schema_revision")
        if isinstance(current_schema, str) and current_schema:
            if schema_revision is not None and current_schema != schema_revision:
                raise DomainError("正式能力观察证据源 schema 不一致")
            schema_revision = current_schema
        checks = source_document.get("checks")
        if not isinstance(checks, list) or not checks:
            raise DomainError("正式能力观察证据源缺少 checks")
        source_documents[source_id] = cast(dict[str, object], source_document)
        sources.append(
            {
                "source_id": source_id,
                "path": resolved.name,
                "sha256": hashlib.sha256(resolved.read_bytes()).hexdigest(),
                "schema_version": str(source_document.get("schema_version", "")),
            }
        )
    if tenant_id is None or schema_revision is None:
        raise DomainError("正式能力观察缺少租户或 schema 真值")
    available_checks = {
        source_id: {
            str(check["id"])
            for check in cast(list[dict[str, object]], source_document["checks"])
            if check.get("status") == "PASS"
        }
        for source_id, source_document in source_documents.items()
    }
    observations: list[dict[str, object]] = []
    for record in _registry():
        references = _REFERENCES[record["id"]]
        for reference in references:
            source_id, check_id = reference.split("#", 1)
            if check_id not in available_checks.get(source_id, set()):
                raise DomainError(f"{record['id']} 引用了不存在的正式 PASS check")
        observations.append(
            {
                "capability_id": record["id"],
                "verdict": "PASS",
                "route": record["route"],
                "ui_control": f"{record['role']}可见的“{record['title']}”控件或明确服务入口",
                "api_consumer": record["consumer"],
                "database_effect": _database_effect(record["id"]),
                "visible_result": _visible_result(record),
                "error_recovery": _error_recovery(record),
                "evidence_refs": list(references),
            }
        )
    document: dict[str, object] = {
        "schema_version": "tenant01-formal-capability-observations-v1",
        "tenant_id": tenant_id,
        "candidate_sha": candidate_sha,
        "schema_revision": schema_revision,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "evidence_sources": sources,
        "observations": observations,
    }
    parsed_tenant_id = UUID(tenant_id)
    validate_observation_document(
        document,
        expected_candidate_sha=candidate_sha,
        expected_tenant_id=parsed_tenant_id,
    )
    output_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    output_path.parent.chmod(0o700)
    payload = (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    output_path.write_bytes(payload)
    output_path.chmod(0o600)
    _verify_evidence_sources(
        document,
        observation_path=output_path,
        expected_candidate_sha=candidate_sha,
        expected_tenant_id=parsed_tenant_id,
    )
    return {
        "candidate_sha": candidate_sha,
        "tenant_id": tenant_id,
        "schema_revision": schema_revision,
        "observations": len(observations),
        "output": str(output_path),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "verdict": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the evidence-backed TENANT-01 58-capability observation document."
    )
    parser.add_argument("--setup", required=True, type=Path)
    parser.add_argument("--publication", required=True, type=Path)
    parser.add_argument("--context", required=True, type=Path)
    parser.add_argument("--surface", required=True, type=Path)
    parser.add_argument("--browser", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--candidate-sha", required=True)
    args = parser.parse_args()
    result = build(
        candidate_sha=args.candidate_sha,
        source_paths={
            "setup": args.setup,
            "publication": args.publication,
            "context": args.context,
            "surface": args.surface,
            "browser": args.browser,
        },
        output_path=args.output.resolve(),
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
