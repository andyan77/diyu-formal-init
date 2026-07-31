from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import cast

from src.shared.dm01_rules import canonical_json_digest
from src.shared.errors import DomainError

DISPLAY_ARTIFACT_AUDIT_VERSION = "dm01-artifact-audit-v1"


def attach_display_artifact_audit(body: str, plan: dict[str, object]) -> dict[str, object]:
    visible_plan = deepcopy(plan)
    visible_plan.pop("artifact_audit", None)
    body_sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
    plan_digest = canonical_json_digest(visible_plan)
    audit = {
        "audit_version": DISPLAY_ARTIFACT_AUDIT_VERSION,
        "body_sha256": body_sha,
        "plan_digest": plan_digest,
        "artifact_digest": canonical_json_digest({"body": body, "plan": visible_plan}),
    }
    return {**visible_plan, "artifact_audit": audit}


def assert_display_artifact_integrity(body: object, plan: object) -> dict[str, object]:
    if not isinstance(body, str) or not isinstance(plan, dict):
        raise DomainError("陈列版本内容不完整。")
    stored = cast(dict[str, object], plan)
    raw_audit = stored.get("artifact_audit")
    if not isinstance(raw_audit, dict):
        # Honest legacy compatibility: old versions had no digest contract.
        return stored
    audit = cast(dict[str, object], raw_audit)
    visible_plan = {key: value for key, value in stored.items() if key != "artifact_audit"}
    expected = {
        "audit_version": DISPLAY_ARTIFACT_AUDIT_VERSION,
        "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "plan_digest": canonical_json_digest(visible_plan),
        "artifact_digest": canonical_json_digest({"body": body, "plan": visible_plan}),
    }
    if audit != expected:
        raise DomainError("陈列版本完整性校验失败，暂不返回正文。")
    return stored
