from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from src.brain.platform_directions import direction_for
from src.shared.brand_publication import publication_projection_digest
from src.shared.errors import DomainError
from src.shared.publication_contract import INTAKE_ROLE_CONTRACT_VERSION
from src.shared.types import ContentTarget

CANDIDATE_FREEZE_SCHEMA = "tenant01-candidate-freeze-v2"
_MODEL_CONFIG = {
    "provider": "deepseek",
    "model": "deepseek-v4-flash",
    "temperature": 0,
    "max_retries": 0,
}
_BINDING_FIELDS = frozenset(
    {
        "tenant_id",
        "brand_id",
        "publishing_account_id",
        "platform_target_account_id",
        "platform_target_key",
        "platform",
        "media_format",
        "content_role_id",
        "account_expression_profile_id",
        "account_expression_profile_version",
        "publication_projection_id",
        "publication_projection_version",
        "publication_projection_digest",
        "publication_projection_item_count",
        "publication_projection_source_bound_item_count",
    }
)


def _head_sha() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _object(value: object, message: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise DomainError(message)
    return cast(dict[str, object], value)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_digest(document: dict[str, object]) -> str:
    return _sha256_bytes(
        json.dumps(
            document,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    )


def _read_private(path: Path, message: str) -> tuple[dict[str, object], str]:
    if path.stat().st_mode & 0o077:
        raise DomainError(f"{message}权限不是 0600")
    payload = path.read_bytes()
    return _object(json.loads(payload), f"{message}无效"), _sha256_bytes(payload)


def _projection_items(
    connection: psycopg.Connection[dict[str, object]],
    *,
    tenant_id: UUID,
    brand_id: UUID,
    projection_id: UUID,
) -> list[dict[str, object]]:
    rows = connection.execute(
        """
        SELECT position, publication_role, published_text, applicability,
               source_kind, source_ref, source_version, source_digest,
               source_segment_id
          FROM brand_publication_projection_items
         WHERE tenant_id=%s AND brand_id=%s AND projection_id=%s
         ORDER BY position
        """,
        (tenant_id, brand_id, projection_id),
    ).fetchall()
    return [dict(row) for row in rows]


def current_binding(
    database_url: str,
    *,
    tenant_id: UUID,
    brand_id: UUID,
    publishing_account_id: UUID,
    platform_target_key: str,
) -> dict[str, object]:
    try:
        direction = direction_for(cast(ContentTarget, platform_target_key))
    except (KeyError, RuntimeError, TypeError, ValueError) as exc:
        raise DomainError("候选冻结的平台目标无效") from exc
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        connection.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),))
        rows = connection.execute(
            """
            SELECT brand.current_publication_projection_id AS projection_id,
                   projection.version_number AS projection_version,
                   projection.digest AS projection_digest,
                   projection.status AS projection_status,
                   root.id AS publishing_account_id,
                   root.brand_id,
                   root.channel,
                   root.enabled,
                   root.platform_enabled,
                   root.current_expression_profile_id AS profile_id,
                   profile.version AS profile_version,
                   account_role.content_role_id
              FROM brands brand
              JOIN brand_publication_projections projection
                ON projection.tenant_id=brand.tenant_id
               AND projection.brand_id=brand.id
               AND projection.id=brand.current_publication_projection_id
              JOIN content_accounts root
                ON root.tenant_id=brand.tenant_id
               AND root.brand_id=brand.id
               AND root.id=%s
               AND root.carrier_of_account_id IS NULL
              JOIN account_content_roles account_role
                ON account_role.tenant_id=root.tenant_id
               AND account_role.account_id=root.id
              JOIN account_expression_profile_versions profile
                ON profile.tenant_id=root.tenant_id
               AND profile.account_id=root.id
               AND profile.id=root.current_expression_profile_id
             WHERE brand.tenant_id=%s AND brand.id=%s
            """,
            (publishing_account_id, tenant_id, brand_id),
        ).fetchall()
        if len(rows) != 1:
            raise DomainError("候选冻结无法唯一解析正式账号、角色和画像")
        row = rows[0]
        if (
            row["projection_status"] != "confirmed"
            or row["enabled"] is not True
            or row["platform_enabled"] is not True
            or str(row["channel"]) != direction.platform
            or str(row["brand_id"]) != str(brand_id)
        ):
            raise DomainError("候选冻结的投影或平台账号没有处于正式可用状态")
        projection_id = UUID(str(row["projection_id"]))
        items = _projection_items(
            connection,
            tenant_id=tenant_id,
            brand_id=brand_id,
            projection_id=projection_id,
        )
    digest_items = [
        {
            "position": int(str(item["position"])),
            "publication_role": str(item["publication_role"]),
            "published_text": str(item["published_text"]),
            "applicability": list(cast(list[str], item["applicability"])),
            "source_kind": str(item["source_kind"]),
            "source_ref": str(item["source_ref"]),
            "source_version": str(item["source_version"]),
            "source_digest": str(item["source_digest"]),
        }
        for item in items
    ]
    recomputed_digest = publication_projection_digest(digest_items)
    if not items or recomputed_digest != str(row["projection_digest"]):
        raise DomainError("候选冻结的正式发布投影 digest 无法复算")
    source_bound_count = sum(
        item["source_kind"] == "brand_source_segment"
        and item["source_segment_id"] is not None
        and bool(str(item["source_digest"]))
        for item in items
    )
    if source_bound_count < 1:
        raise DomainError("候选冻结不能只绑定兼容品牌基线")
    return {
        "tenant_id": str(tenant_id),
        "brand_id": str(brand_id),
        "publishing_account_id": str(row["publishing_account_id"]),
        "platform_target_account_id": str(row["publishing_account_id"]),
        "platform_target_key": platform_target_key,
        "platform": direction.platform,
        "media_format": direction.media_format,
        "content_role_id": str(row["content_role_id"]),
        "account_expression_profile_id": str(row["profile_id"]),
        "account_expression_profile_version": int(str(row["profile_version"])),
        "publication_projection_id": str(projection_id),
        "publication_projection_version": int(str(row["projection_version"])),
        "publication_projection_digest": recomputed_digest,
        "publication_projection_item_count": len(items),
        "publication_projection_source_bound_item_count": source_bound_count,
    }


def assert_candidate_freeze_document(
    document: dict[str, object],
    *,
    candidate_sha: str,
    context_evidence_sha256: str,
    current: dict[str, object],
    context_evidence: dict[str, object],
) -> dict[str, object]:
    if set(document) != {
        "schema_version",
        "candidate_sha",
        "created_at",
        "model_config",
        "intake_contract_version",
        "context_evidence_sha256",
        "binding",
        "binding_digest",
    }:
        raise DomainError("候选冻结字段发生漂移")
    binding = _object(document.get("binding"), "候选冻结绑定无效")
    model_config = _object(document.get("model_config"), "候选冻结模型配置无效")
    if (
        document.get("schema_version") != CANDIDATE_FREEZE_SCHEMA
        or document.get("candidate_sha") != candidate_sha
        or document.get("intake_contract_version") != INTAKE_ROLE_CONTRACT_VERSION
        or document.get("context_evidence_sha256") != context_evidence_sha256
        or model_config != _MODEL_CONFIG
        or set(binding) != _BINDING_FIELDS
        or document.get("binding_digest") != _canonical_digest(binding)
        or binding != current
        or type(binding["publication_projection_item_count"]) is not int
        or type(binding["publication_projection_source_bound_item_count"]) is not int
        or binding["publication_projection_source_bound_item_count"] < 1
        or binding["publication_projection_item_count"]
        < binding["publication_projection_source_bound_item_count"]
    ):
        raise DomainError("候选冻结与当前正式上下文不一致")
    isolation = _object(
        context_evidence.get("projection_isolation"),
        "候选冻结缺少投影隔离证据",
    )
    if (
        context_evidence.get("candidate_sha") != candidate_sha
        or context_evidence.get("tenant_id") != binding["tenant_id"]
        or context_evidence.get("verdict") != "PASS"
        or isolation.get("new_projection_id") != binding["publication_projection_id"]
        or isolation.get("new_projection_version") != binding["publication_projection_version"]
        or isolation.get("new_projection_digest") != binding["publication_projection_digest"]
    ):
        raise DomainError("候选冻结与正式投影隔离证据不一致")
    return binding


def create_candidate_freeze(
    *,
    database_url: str,
    credentials_path: Path,
    context_evidence_path: Path,
    output_path: Path,
    candidate_sha: str,
    platform_target_key: str,
) -> dict[str, object]:
    if _head_sha() != candidate_sha:
        raise DomainError("候选冻结 SHA 与当前 HEAD 不一致")
    if output_path.exists():
        raise DomainError("候选冻结文件已存在，拒绝静默覆盖")
    credentials, _ = _read_private(credentials_path, "正式纵向凭据")
    context_evidence, context_evidence_sha256 = _read_private(context_evidence_path, "正式上下文证据")
    if (
        credentials.get("candidate_sha") != candidate_sha
        or context_evidence.get("candidate_sha") != candidate_sha
        or credentials.get("tenant_id") != context_evidence.get("tenant_id")
    ):
        raise DomainError("候选冻结输入不属于同一候选和租户")
    current = current_binding(
        database_url,
        tenant_id=UUID(str(credentials["tenant_id"])),
        brand_id=UUID(str(credentials["brand_id"])),
        publishing_account_id=UUID(str(credentials["account_id"])),
        platform_target_key=platform_target_key,
    )
    document: dict[str, object] = {
        "schema_version": CANDIDATE_FREEZE_SCHEMA,
        "candidate_sha": candidate_sha,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model_config": dict(_MODEL_CONFIG),
        "intake_contract_version": INTAKE_ROLE_CONTRACT_VERSION,
        "context_evidence_sha256": context_evidence_sha256,
        "binding": current,
        "binding_digest": _canonical_digest(current),
    }
    assert_candidate_freeze_document(
        document,
        candidate_sha=candidate_sha,
        context_evidence_sha256=context_evidence_sha256,
        current=current,
        context_evidence=context_evidence,
    )
    output_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    output_path.parent.chmod(0o700)
    payload = (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    output_path.write_bytes(payload)
    output_path.chmod(0o600)
    return {
        "candidate_sha": candidate_sha,
        "output": str(output_path),
        "sha256": _sha256_bytes(payload),
        "verdict": "PASS",
    }


def validate_candidate_freeze(
    *,
    database_url: str,
    candidate_freeze_path: Path,
    context_evidence_path: Path,
    candidate_sha: str,
) -> tuple[dict[str, object], str]:
    document, candidate_freeze_sha256 = _read_private(candidate_freeze_path, "候选冻结文件")
    context_evidence, context_evidence_sha256 = _read_private(context_evidence_path, "正式上下文证据")
    raw_binding = _object(document.get("binding"), "候选冻结绑定无效")
    current = current_binding(
        database_url,
        tenant_id=UUID(str(raw_binding.get("tenant_id"))),
        brand_id=UUID(str(raw_binding.get("brand_id"))),
        publishing_account_id=UUID(str(raw_binding.get("publishing_account_id"))),
        platform_target_key=str(raw_binding.get("platform_target_key")),
    )
    binding = assert_candidate_freeze_document(
        document,
        candidate_sha=candidate_sha,
        context_evidence_sha256=context_evidence_sha256,
        current=current,
        context_evidence=context_evidence,
    )
    return binding, candidate_freeze_sha256


def main() -> int:
    parser = argparse.ArgumentParser(description="Freeze one provider-safe TENANT-01 candidate binding.")
    parser.add_argument("--credentials", required=True, type=Path)
    parser.add_argument("--context-evidence", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--platform-target", default="douyin_video")
    args = parser.parse_args()
    database_url = os.environ.get("DIYU_APP_DATABASE_URL", "")
    if not database_url:
        raise DomainError("缺少本地正式应用数据库连接")
    result = create_candidate_freeze(
        database_url=database_url,
        credentials_path=args.credentials.resolve(strict=True),
        context_evidence_path=args.context_evidence.resolve(strict=True),
        output_path=args.output.resolve(),
        candidate_sha=args.candidate_sha,
        platform_target_key=args.platform_target,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
