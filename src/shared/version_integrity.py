from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from src.shared.content_presentation import project_content_body
from src.shared.errors import DomainError
from src.shared.narrative import visible_digest

AUDIT_VERSION_V1 = "content-version-audit-v1"
AUDIT_VERSION_V2 = "content-version-audit-v2"
AUDIT_VERSION_V3 = "content-version-audit-v3"
FINAL_VISIBLE_PROJECTION_V2 = "delivery-compiler-v2-final-visible-v1"
FINAL_VISIBLE_PROJECTION_V3 = "delivery-compiler-v3-final-visible-v1"


@dataclass(frozen=True)
class ValidatedVersionContent:
    outline: str
    body: str
    audit_version: str | None


def validate_version_content(row: Mapping[str, object]) -> ValidatedVersionContent:
    """Validate one version before any user-visible or source-content read.

    Legacy rows have no digest and keep their historical projection. Audit-v1
    rows retain that same projection after digest verification. Audit-v2/v3
    rows bind and return their compiler's final visible outline/body directly.
    """

    outline = row.get("outline")
    body = row.get("body")
    if not isinstance(outline, str) or not isinstance(body, str):
        raise DomainError("内容版本正文数据无效")

    digest = row.get("artifact_digest")
    snapshot = row.get("version_audit_snapshot")
    if digest is None and (snapshot is None or snapshot == {}):
        return ValidatedVersionContent(
            outline=outline,
            body=project_content_body(body),
            audit_version=None,
        )
    if not isinstance(digest, str) or not isinstance(snapshot, dict):
        raise DomainError("内容版本审计证据不完整")

    audit_version = snapshot.get("audit_version")
    snapshot_digest = snapshot.get("artifact_digest")
    if audit_version not in {
        AUDIT_VERSION_V1,
        AUDIT_VERSION_V2,
        AUDIT_VERSION_V3,
    }:
        raise DomainError("内容版本审计格式无效")
    if snapshot_digest != digest or visible_digest(outline, body) != digest:
        raise DomainError("内容版本完整性校验失败")

    if audit_version == AUDIT_VERSION_V1:
        visible_body = project_content_body(body)
    else:
        expected_projection = (
            FINAL_VISIBLE_PROJECTION_V3
            if audit_version == AUDIT_VERSION_V3
            else FINAL_VISIBLE_PROJECTION_V2
        )
        if snapshot.get("visible_projection") != expected_projection:
            raise DomainError("内容版本可见投影证据无效")
        visible_body = body
    return ValidatedVersionContent(
        outline=outline,
        body=visible_body,
        audit_version=str(audit_version),
    )
