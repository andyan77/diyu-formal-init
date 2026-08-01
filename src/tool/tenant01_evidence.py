from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast
from uuid import UUID

from src.shared.narrative import visible_digest

TENANT01_CARD_IDS: Final[frozenset[str]] = frozenset(
    {
        "coffee",
        "zero_topic",
        "family_relationship",
        "daily_complaint",
        "P1",
        "P2",
        "P4_series1",
        "cross_platform_xhs",
        "cross_platform_douyin",
        "series2",
        "series3",
    }
)
TENANT01_REVIEW_DIMENSIONS: Final[tuple[str, ...]] = (
    "brand_relation",
    "account_voice",
    "viewer_value",
    "platform_fit",
    "completeness",
    "natural_language",
    "local_revision_consistency",
)
TENANT01_HARD_BOUNDARIES: Final[tuple[str, ...]] = (
    "tenant_scope",
    "product_facts",
    "person_facts",
    "media_resources",
)


class Tenant01EvidenceError(ValueError):
    """Raised when a first-tenant evidence set is incomplete or unbound."""


@dataclass(frozen=True)
class Tenant01ArtifactInput:
    card_id: str
    artifact_file: str
    raw_response_file: str


@dataclass(frozen=True)
class Tenant01HumanReview:
    card_id: str
    artifact_file: str
    scores: dict[str, int]
    excerpts: dict[str, str]
    hard_boundaries: dict[str, bool]
    notes: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _private_child(root: Path, filename: str) -> Path:
    path = (root / filename).resolve()
    if path.parent != root.resolve() or path.name != filename:
        raise Tenant01EvidenceError("证据文件必须直接位于私有证据目录。")
    if not path.is_file() or path.stat().st_mode & 0o077:
        raise Tenant01EvidenceError(f"{filename} 不存在或权限不是 0600。")
    return path


def _json_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Tenant01EvidenceError(f"{path.name} 必须是 JSON 对象。")
    return cast(dict[str, object], value)


def _uuid_text(value: object, *, label: str) -> str:
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError) as exc:
        raise Tenant01EvidenceError(f"{label} 缺少真实 UUID。") from exc


def _artifact_binding(
    path: Path,
    *,
    card_id: str,
) -> tuple[dict[str, object], dict[str, str]]:
    document = _json_object(path)
    if document.get("card_id") != card_id:
        raise Tenant01EvidenceError(f"{card_id} 成品文件绑定到了另一张卡。")
    outline = document.get("outline")
    body = document.get("body")
    if not isinstance(outline, str) or not outline.strip():
        raise Tenant01EvidenceError(f"{card_id} 缺少可见标题。")
    if not isinstance(body, str) or not body.strip():
        raise Tenant01EvidenceError(f"{card_id} 缺少完整成品。")
    expected_visible = visible_digest(outline, body)
    if document.get("visible_digest") != expected_visible:
        raise Tenant01EvidenceError(f"{card_id} visible_digest 无法复算。")
    persistence = {
        field: _uuid_text(document.get(field), label=f"{card_id} {field}")
        for field in ("task_id", "run_id", "version_id")
    }
    return document, persistence


def _validate_review(
    review: Tenant01HumanReview,
    *,
    artifact: dict[str, object],
) -> dict[str, object]:
    if set(review.scores) != set(TENANT01_REVIEW_DIMENSIONS):
        raise Tenant01EvidenceError(f"{review.card_id} 人工评分维度不完整。")
    if any(not isinstance(score, int) or not 1 <= score <= 5 for score in review.scores.values()):
        raise Tenant01EvidenceError(f"{review.card_id} 人工评分必须为 1—5。")
    for dimension in ("brand_relation", "account_voice", "platform_fit", "completeness"):
        if review.scores[dimension] < 4:
            raise Tenant01EvidenceError(f"{review.card_id} 未通过 {dimension} 硬门。")
    if set(review.hard_boundaries) != set(TENANT01_HARD_BOUNDARIES) or not all(
        review.hard_boundaries.values()
    ):
        raise Tenant01EvidenceError(f"{review.card_id} 事实或资源硬边界未通过。")
    if set(review.excerpts) != {"title", "body", "media", "caption"}:
        raise Tenant01EvidenceError(f"{review.card_id} 人工审阅引用不完整。")
    outline = str(artifact["outline"])
    body = str(artifact["body"])
    for field, excerpt in review.excerpts.items():
        if not excerpt.strip():
            raise Tenant01EvidenceError(f"{review.card_id} {field} 引用为空。")
        haystack = outline if field == "title" else body
        if excerpt not in haystack:
            raise Tenant01EvidenceError(
                f"{review.card_id} {field} 引用不在最终 artifact 中。"
            )
    if not review.notes.strip():
        raise Tenant01EvidenceError(f"{review.card_id} 人工审阅结论为空。")
    return {
        "card_id": review.card_id,
        "artifact_file": review.artifact_file,
        "scores": review.scores,
        "average_score": round(
            sum(review.scores.values()) / len(review.scores),
            3,
        ),
        "excerpts": review.excerpts,
        "hard_boundaries": review.hard_boundaries,
        "notes": review.notes,
    }


def _assert_preflight(path: Path) -> dict[str, object]:
    document = _json_object(path)
    if (
        document.get("card_id") != "P5_no_media"
        or document.get("provider_calls") != 0
        or document.get("persistence_delta") != [0, 0, 0]
        or document.get("result_kind") != "question"
    ):
        raise Tenant01EvidenceError("P5 无图反证未保持 0/0/0 与零模型调用。")
    return document


def _assert_dm01(path: Path) -> dict[str, object]:
    document = _json_object(path)
    required = {
        "task_id",
        "v1_run_id",
        "v1_version_id",
        "v2_run_id",
        "v2_version_id",
    }
    identifiers = document.get("identifiers")
    if not isinstance(identifiers, dict) or set(identifiers) != required:
        raise Tenant01EvidenceError("DM01 证据缺少 V1/V2 正式标识。")
    for field in required:
        _uuid_text(identifiers[field], label=f"DM01 {field}")
    if (
        document.get("model") != "dm01-rule-compiler-v1"
        or document.get("provider_calls") != 0
        or document.get("provider_usage") not in ({}, None)
        or document.get("rules_total") != 13
        or document.get("generation_rules") != 11
        or document.get("v1_v2_v1") is not True
        or document.get("inventory_conservation") is not True
        or document.get("ai_generated") is not False
    ):
        raise Tenant01EvidenceError("DM01 隔离卡没有满足纯文字、零模型和库存守恒合同。")
    return document


def write_tenant01_evidence(
    root: Path,
    *,
    implementation_sha: str,
    schema_revision: str,
    image_digest: str,
    artifacts: tuple[Tenant01ArtifactInput, ...],
    reviews: tuple[Tenant01HumanReview, ...],
    p5_preflight_file: str,
    dm01_file: str,
) -> None:
    if len(implementation_sha) != 40 or any(character not in "0123456789abcdef" for character in implementation_sha):
        raise Tenant01EvidenceError("实现 SHA 无效。")
    if not schema_revision or not image_digest.startswith("sha256:"):
        raise Tenant01EvidenceError("schema 或镜像 digest 未冻结。")
    if root.stat().st_mode & 0o077:
        raise Tenant01EvidenceError("证据目录权限必须为 0700。")
    if {item.card_id for item in artifacts} != TENANT01_CARD_IDS:
        raise Tenant01EvidenceError("黄金卡覆盖不完整。")
    if len({item.card_id for item in artifacts}) != len(artifacts):
        raise Tenant01EvidenceError("黄金卡重复。")
    review_by_card = {review.card_id: review for review in reviews}
    if set(review_by_card) != TENANT01_CARD_IDS or len(review_by_card) != len(reviews):
        raise Tenant01EvidenceError("人工审阅覆盖不完整或重复。")

    artifact_records: list[dict[str, object]] = []
    review_records: list[dict[str, object]] = []
    review_averages: list[float] = []
    for item in artifacts:
        artifact_path = _private_child(root, item.artifact_file)
        raw_path = _private_child(root, item.raw_response_file)
        artifact, persistence = _artifact_binding(
            artifact_path,
            card_id=item.card_id,
        )
        review = review_by_card[item.card_id]
        if review.artifact_file != item.artifact_file:
            raise Tenant01EvidenceError(f"{item.card_id} 人工审阅引用了另一文件。")
        validated_review = _validate_review(review, artifact=artifact)
        average_score = validated_review["average_score"]
        if not isinstance(average_score, float):
            raise Tenant01EvidenceError(f"{item.card_id} 人工评分摘要无效。")
        review_averages.append(average_score)
        artifact_records.append(
            {
                "card_id": item.card_id,
                "artifact_file": item.artifact_file,
                "artifact_sha256": sha256_file(artifact_path),
                "raw_response_file": item.raw_response_file,
                "raw_response_sha256": sha256_file(raw_path),
                "visible_digest": artifact["visible_digest"],
                **persistence,
            }
        )
        validated_review["artifact_sha256"] = sha256_file(artifact_path)
        validated_review["visible_digest"] = artifact["visible_digest"]
        review_records.append(validated_review)

    p5_path = _private_child(root, p5_preflight_file)
    dm01_path = _private_child(root, dm01_file)
    _assert_preflight(p5_path)
    _assert_dm01(dm01_path)
    _write_private_json(
        root / "human-review.json",
        {
            "review_contract": "TENANT-01-HUMAN-REVIEW-V1",
            "reviews": review_records,
            "overall_average": round(
                sum(review_averages) / len(review_averages),
                3,
            ),
            "hard_boundary_violations": 0,
        },
    )
    _write_private_json(
        root / "manifest.json",
        {
            "manifest_version": "TENANT-01-EVIDENCE-V1",
            "implementation_sha": implementation_sha,
            "schema_revision": schema_revision,
            "image_digest": image_digest,
            "provider_config": {
                "model": "deepseek-v4-flash",
                "temperature": 0,
                "max_retries": 0,
            },
            "artifacts": artifact_records,
            "p5_preflight": {
                "file": p5_preflight_file,
                "sha256": sha256_file(p5_path),
            },
            "dm01": {"file": dm01_file, "sha256": sha256_file(dm01_path)},
        },
    )
    files = sorted(
        path
        for path in root.iterdir()
        if path.is_file() and path.name != "SHA256SUMS"
    )
    checksum = "".join(f"{sha256_file(path)}  {path.name}\n" for path in files)
    _write_private_bytes(root / "SHA256SUMS", checksum.encode())


def _write_private_json(path: Path, value: object) -> None:
    payload = (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode()
    _write_private_bytes(path, payload)


def _write_private_bytes(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        remaining = memoryview(payload)
        while remaining:
            written = os.write(descriptor, remaining)
            remaining = remaining[written:]
    finally:
        os.close(descriptor)
    path.chmod(0o600)
