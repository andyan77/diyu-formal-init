from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import psycopg

from src.shared.errors import DomainError

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_REGISTRY_PATH = _PROJECT_ROOT / "config/formal-capabilities-v1.json"
_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")
_CHECK_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{1,127}$")
_OBSERVATION_FIELDS = frozenset(
    {
        "capability_id",
        "verdict",
        "route",
        "ui_control",
        "api_consumer",
        "database_effect",
        "visible_result",
        "error_recovery",
        "evidence_refs",
    }
)
_EVIDENCE_SOURCE_FIELDS = frozenset(
    {"source_id", "path", "sha256", "schema_version"}
)


def _registry_ids() -> tuple[str, ...]:
    try:
        document = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DomainError("正式能力注册表无法读取") from exc
    capabilities = document.get("capabilities") if isinstance(document, dict) else None
    if not isinstance(capabilities, list):
        raise DomainError("正式能力注册表格式无效")
    identifiers = tuple(
        str(item.get("id"))
        for item in capabilities
        if isinstance(item, dict)
    )
    if len(identifiers) != 58 or len(set(identifiers)) != 58:
        raise DomainError("正式能力注册表必须恰好包含 58 个唯一能力")
    return identifiers


def _registry_records() -> dict[str, dict[str, str]]:
    try:
        document = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DomainError("正式能力注册表无法读取") from exc
    capabilities = document.get("capabilities") if isinstance(document, dict) else None
    if not isinstance(capabilities, list):
        raise DomainError("正式能力注册表格式无效")
    records: dict[str, dict[str, str]] = {}
    for raw in capabilities:
        if not isinstance(raw, dict) or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in raw.items()
        ):
            raise DomainError("正式能力注册表条目无效")
        record = cast(dict[str, str], raw)
        records[record["id"]] = record
    if tuple(records) != _registry_ids():
        raise DomainError("正式能力注册表顺序或 ID 漂移")
    return records


def _nonempty_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DomainError(f"正式能力实测字段 {field} 不能为空")
    return value.strip()


def validate_observation_document(
    document: object,
    *,
    expected_candidate_sha: str,
    expected_tenant_id: UUID,
) -> tuple[dict[str, object], ...]:
    if not isinstance(document, dict):
        raise DomainError("正式能力实测证据必须是 JSON 对象")
    if set(document) != {
        "schema_version",
        "tenant_id",
        "candidate_sha",
        "schema_revision",
        "observed_at",
        "evidence_sources",
        "observations",
    }:
        raise DomainError("正式能力实测证据顶层字段不完整或含未授权字段")
    if document.get("schema_version") != "tenant01-formal-capability-observations-v1":
        raise DomainError("正式能力实测证据版本无效")
    if str(document.get("tenant_id")) != str(expected_tenant_id):
        raise DomainError("正式能力实测证据租户不一致")
    candidate_sha = str(document.get("candidate_sha"))
    if candidate_sha != expected_candidate_sha or not _SHA_PATTERN.fullmatch(candidate_sha):
        raise DomainError("正式能力实测证据候选 SHA 不一致")
    _nonempty_text(document.get("schema_revision"), "schema_revision")
    observed_at = _nonempty_text(document.get("observed_at"), "observed_at")
    try:
        datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DomainError("正式能力实测时间格式无效") from exc
    raw_observations = document.get("observations")
    raw_sources = document.get("evidence_sources")
    if not isinstance(raw_sources, list) or not raw_sources:
        raise DomainError("正式能力实测缺少受摘要绑定的证据源")
    source_ids: list[str] = []
    for raw_source in raw_sources:
        if not isinstance(raw_source, dict) or set(raw_source) != _EVIDENCE_SOURCE_FIELDS:
            raise DomainError("正式能力实测证据源字段无效")
        source_id = _nonempty_text(raw_source.get("source_id"), "source_id")
        if not _SOURCE_ID_PATTERN.fullmatch(source_id):
            raise DomainError("正式能力实测 source_id 无效")
        source_ids.append(source_id)
        _nonempty_text(raw_source.get("path"), "path")
        digest = _nonempty_text(raw_source.get("sha256"), "sha256")
        if not _DIGEST_PATTERN.fullmatch(digest):
            raise DomainError("正式能力实测证据源摘要无效")
        _nonempty_text(raw_source.get("schema_version"), "schema_version")
    if len(source_ids) != len(set(source_ids)):
        raise DomainError("正式能力实测含重复证据源")
    if not isinstance(raw_observations, list):
        raise DomainError("正式能力实测 observations 无效")
    registry = _registry_records()
    referenced_source_ids: set[str] = set()
    observations: list[dict[str, object]] = []
    for raw in raw_observations:
        if not isinstance(raw, dict) or set(raw) != _OBSERVATION_FIELDS:
            raise DomainError("正式能力单项观察字段不完整或含未授权字段")
        capability_id = _nonempty_text(raw.get("capability_id"), "capability_id")
        registered = registry.get(capability_id)
        if registered is None:
            raise DomainError(f"{capability_id} 不在正式能力注册表")
        if raw.get("verdict") != "PASS":
            raise DomainError(f"{capability_id} 未通过，禁止写入正式实测 PASS")
        route = _nonempty_text(raw.get("route"), "route")
        api_consumer = _nonempty_text(raw.get("api_consumer"), "api_consumer")
        if route != registered["route"] or api_consumer != registered["consumer"]:
            raise DomainError(f"{capability_id} 的路由或消费者与正式注册表不一致")
        for field in ("ui_control", "database_effect", "visible_result", "error_recovery"):
            _nonempty_text(raw.get(field), field)
        evidence_refs = raw.get("evidence_refs")
        if (
            not isinstance(evidence_refs, list)
            or not evidence_refs
            or any(not isinstance(item, str) or not item.strip() for item in evidence_refs)
        ):
            raise DomainError(f"{capability_id} 缺少逐项证据引用")
        for evidence_ref in cast(list[str], evidence_refs):
            source_id, separator, check_id = evidence_ref.partition("#")
            if (
                separator != "#"
                or source_id not in source_ids
                or not _CHECK_ID_PATTERN.fullmatch(check_id)
            ):
                raise DomainError(f"{capability_id} 的逐项证据引用无效")
            referenced_source_ids.add(source_id)
        observations.append(cast(dict[str, object], raw))
    observed_ids = tuple(str(item["capability_id"]) for item in observations)
    registry_ids = _registry_ids()
    if len(observed_ids) != len(set(observed_ids)):
        raise DomainError("正式能力实测含重复能力")
    if set(observed_ids) != set(registry_ids):
        missing = sorted(set(registry_ids) - set(observed_ids))
        extra = sorted(set(observed_ids) - set(registry_ids))
        raise DomainError(
            "正式能力实测必须逐项覆盖注册表；"
            f"缺失={','.join(missing) or '无'}；越界={','.join(extra) or '无'}"
        )
    if referenced_source_ids != set(source_ids):
        raise DomainError("正式能力实测含未被逐项消费的证据源")
    return tuple(observations)


def _verify_evidence_sources(
    document: dict[str, object],
    *,
    observation_path: Path,
    expected_candidate_sha: str,
    expected_tenant_id: UUID,
) -> None:
    root = observation_path.parent.resolve()
    sources = cast(list[dict[str, object]], document["evidence_sources"])
    passed_checks: dict[str, set[str]] = {}
    for source in sources:
        source_id = str(source["source_id"])
        source_path = Path(str(source["path"]))
        if not source_path.is_absolute():
            source_path = root / source_path
        resolved = source_path.resolve(strict=True)
        if resolved == observation_path.resolve() or (
            resolved != root and root not in resolved.parents
        ):
            raise DomainError("正式能力实测证据源必须位于同一私有证据根")
        raw = resolved.read_bytes()
        if hashlib.sha256(raw).hexdigest() != source["sha256"]:
            raise DomainError("正式能力实测证据源摘要漂移")
        try:
            source_document = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise DomainError("正式能力实测证据源不是有效 JSON") from exc
        if not isinstance(source_document, dict):
            raise DomainError("正式能力实测证据源必须是 JSON 对象")
        if (
            source_document.get("schema_version") != source["schema_version"]
            or source_document.get("candidate_sha") != expected_candidate_sha
            or source_document.get("tenant_id") != str(expected_tenant_id)
            or source_document.get("verdict") != "PASS"
        ):
            raise DomainError("正式能力实测证据源身份、版本或 verdict 不一致")
        raw_checks = source_document.get("checks")
        if not isinstance(raw_checks, list) or not raw_checks:
            raise DomainError("正式能力实测证据源缺少标准 PASS checks")
        check_ids: list[str] = []
        for raw_check in raw_checks:
            if (
                not isinstance(raw_check, dict)
                or raw_check.get("status") != "PASS"
                or not isinstance(raw_check.get("id"), str)
                or not _CHECK_ID_PATTERN.fullmatch(str(raw_check["id"]))
            ):
                raise DomainError("正式能力实测证据源含无效或非 PASS check")
            check_ids.append(str(raw_check["id"]))
        if len(check_ids) != len(set(check_ids)):
            raise DomainError("正式能力实测证据源含重复 check")
        passed_checks[source_id] = set(check_ids)
    observations = cast(list[dict[str, object]], document["observations"])
    for observation in observations:
        for evidence_ref in cast(list[str], observation["evidence_refs"]):
            source_id, check_id = evidence_ref.split("#", 1)
            if check_id not in passed_checks[source_id]:
                raise DomainError(
                    f"{observation['capability_id']} 引用了证据源中不存在的 PASS check"
                )


def _head_sha() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=_PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def record_observations(
    *,
    evidence_path: Path,
    candidate_sha: str,
    tenant_id: UUID,
    database_url: str,
) -> dict[str, object]:
    raw = evidence_path.read_bytes()
    evidence_digest = hashlib.sha256(raw).hexdigest()
    if not _DIGEST_PATTERN.fullmatch(evidence_digest):
        raise DomainError("正式能力实测证据摘要无效")
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DomainError("正式能力实测证据不是有效 JSON") from exc
    observations = validate_observation_document(
        document,
        expected_candidate_sha=candidate_sha,
        expected_tenant_id=tenant_id,
    )
    _verify_evidence_sources(
        cast(dict[str, object], document),
        observation_path=evidence_path,
        expected_candidate_sha=candidate_sha,
        expected_tenant_id=tenant_id,
    )
    schema_revision = str(cast(dict[str, object], document)["schema_revision"])
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT version_num::text FROM alembic_version LIMIT 1")
        row = cursor.fetchone()
        if row is None or str(row[0]) != schema_revision:
            raise DomainError("正式能力实测证据 schema 与目标数据库不一致")
        cursor.execute("SELECT 1 FROM tenants WHERE id = %s", (tenant_id,))
        if cursor.fetchone() is None:
            raise DomainError("正式能力实测目标租户不存在")
        for item in observations:
            cursor.execute(
                "INSERT INTO formal_capability_observations "
                "(id, tenant_id, capability_id, candidate_sha, evidence_sha256, verdict) "
                "VALUES (%s, %s, %s, %s, %s, 'PASS') "
                "ON CONFLICT (tenant_id, capability_id, candidate_sha, evidence_sha256) "
                "DO NOTHING",
                (
                    uuid4(),
                    tenant_id,
                    item["capability_id"],
                    candidate_sha,
                    evidence_digest,
                ),
            )
        cursor.execute(
            "SELECT array_agg(capability_id ORDER BY capability_id) "
            "FROM formal_capability_observations "
            "WHERE tenant_id = %s AND candidate_sha = %s AND evidence_sha256 = %s",
            (tenant_id, candidate_sha, evidence_digest),
        )
        recorded = cursor.fetchone()
    recorded_ids = tuple(recorded[0] or ()) if recorded is not None else ()
    if set(recorded_ids) != set(_registry_ids()):
        raise DomainError("正式能力实测观察写入后复核不完整")
    return {
        "candidate_sha": candidate_sha,
        "tenant_id": str(tenant_id),
        "schema_revision": schema_revision,
        "evidence_sha256": evidence_digest,
        "recorded": len(recorded_ids),
        "verdict": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Record all 58 evidence-backed formal capability observations."
    )
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--tenant-id", required=True, type=UUID)
    args = parser.parse_args()
    if _head_sha() != args.candidate_sha:
        raise DomainError("当前 Git HEAD 与正式能力实测候选 SHA 不一致")
    database_url = os.environ.get("DIYU_MIGRATOR_DATABASE_URL", "")
    if not database_url:
        raise DomainError("缺少受控 migrator 数据库连接")
    result = record_observations(
        evidence_path=args.evidence.resolve(strict=True),
        candidate_sha=args.candidate_sha,
        tenant_id=args.tenant_id,
        database_url=database_url,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
