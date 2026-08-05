from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from src.shared.errors import DomainError
from src.shared.publication_contract import INTAKE_ROLE_CONTRACT_VERSION
from src.tool import run_tenant01_formal_browser as browser_tool
from src.tool.tenant01_candidate_freeze import (
    CANDIDATE_FREEZE_SCHEMA,
    assert_candidate_freeze_document,
)

_SHA = "a" * 40
_TENANT_ID = "11111111-1111-4111-8111-111111111111"
_BRAND_ID = "22222222-2222-4222-8222-222222222222"
_ACCOUNT_ID = "33333333-3333-4333-8333-333333333333"
_ROLE_ID = "44444444-4444-4444-8444-444444444444"
_PROFILE_ID = "55555555-5555-4555-8555-555555555555"
_PROJECTION_ID = "66666666-6666-4666-8666-666666666666"
_PROJECTION_DIGEST = "b" * 64
_CONTEXT_SHA = "c" * 64


def _digest(document: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(document, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()


def _binding() -> dict[str, object]:
    return {
        "tenant_id": _TENANT_ID,
        "brand_id": _BRAND_ID,
        "publishing_account_id": _ACCOUNT_ID,
        "platform_target_account_id": _ACCOUNT_ID,
        "platform_target_key": "douyin_video",
        "platform": "抖音",
        "media_format": "video",
        "content_role_id": _ROLE_ID,
        "account_expression_profile_id": _PROFILE_ID,
        "account_expression_profile_version": 1,
        "publication_projection_id": _PROJECTION_ID,
        "publication_projection_version": 3,
        "publication_projection_digest": _PROJECTION_DIGEST,
        "publication_projection_item_count": 8,
        "publication_projection_source_bound_item_count": 8,
    }


def _context() -> dict[str, object]:
    return {
        "candidate_sha": _SHA,
        "tenant_id": _TENANT_ID,
        "verdict": "PASS",
        "projection_isolation": {
            "new_projection_id": _PROJECTION_ID,
            "new_projection_version": 3,
            "new_projection_digest": _PROJECTION_DIGEST,
        },
    }


def _document(binding: dict[str, object] | None = None) -> dict[str, object]:
    frozen = dict(binding or _binding())
    return {
        "schema_version": CANDIDATE_FREEZE_SCHEMA,
        "candidate_sha": _SHA,
        "created_at": "2026-08-04T00:00:00+00:00",
        "model_config": {
            "provider": "deepseek",
            "model": "deepseek-v4-flash",
            "temperature": 0,
            "max_retries": 0,
        },
        "intake_contract_version": INTAKE_ROLE_CONTRACT_VERSION,
        "context_evidence_sha256": _CONTEXT_SHA,
        "binding": frozen,
        "binding_digest": _digest(frozen),
    }


def test_candidate_freeze_accepts_one_exact_source_bound_context() -> None:
    binding = _binding()

    assert (
        assert_candidate_freeze_document(
            _document(binding),
            candidate_sha=_SHA,
            context_evidence_sha256=_CONTEXT_SHA,
            current=binding,
            context_evidence=_context(),
        )
        == binding
    )


@pytest.mark.parametrize(
    ("field", "mutated"),
    (
        ("publication_projection_id", "77777777-7777-4777-8777-777777777777"),
        ("publication_projection_version", 4),
        ("publication_projection_digest", "d" * 64),
        ("publishing_account_id", "77777777-7777-4777-8777-777777777777"),
        ("content_role_id", "77777777-7777-4777-8777-777777777777"),
        ("account_expression_profile_id", "77777777-7777-4777-8777-777777777777"),
        ("account_expression_profile_version", 2),
        ("platform_target_key", "xiaohongshu_graphic"),
    ),
)
def test_candidate_freeze_rejects_every_context_drift(field: str, mutated: object) -> None:
    current = _binding()
    frozen = dict(current)
    frozen[field] = mutated

    with pytest.raises(DomainError, match="候选冻结与当前正式上下文不一致"):
        assert_candidate_freeze_document(
            _document(frozen),
            candidate_sha=_SHA,
            context_evidence_sha256=_CONTEXT_SHA,
            current=current,
            context_evidence=_context(),
        )


def test_candidate_freeze_rejects_compatibility_baseline_only() -> None:
    binding = _binding()
    binding["publication_projection_source_bound_item_count"] = 0

    with pytest.raises(DomainError, match="候选冻结与当前正式上下文不一致"):
        assert_candidate_freeze_document(
            _document(binding),
            candidate_sha=_SHA,
            context_evidence_sha256=_CONTEXT_SHA,
            current=binding,
            context_evidence=_context(),
        )


def test_provider_preflight_drift_fails_before_provider_construction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credentials_path = tmp_path / "credentials.json"
    context_path = tmp_path / "context.json"
    freeze_path = tmp_path / "freeze.json"
    output_path = tmp_path / "browser.json"
    credentials_path.write_text(
        json.dumps(
            {
                "candidate_sha": _SHA,
                "tenant_id": _TENANT_ID,
                "brand_id": _BRAND_ID,
                "account_id": _ACCOUNT_ID,
            }
        ),
        encoding="utf-8",
    )
    context_path.write_text(json.dumps(_context()), encoding="utf-8")
    freeze_path.write_text("{}", encoding="utf-8")
    for path in (credentials_path, context_path, freeze_path):
        path.chmod(0o600)
    provider_constructions = 0

    def reject_freeze(**_: object) -> tuple[dict[str, object], str]:
        raise DomainError("projection freeze drift")

    def provider_settings(*_: object) -> object:
        nonlocal provider_constructions
        provider_constructions += 1
        return object()

    monkeypatch.setattr(browser_tool, "_head_sha", lambda: _SHA)
    monkeypatch.setattr(browser_tool, "validate_candidate_freeze", reject_freeze)
    monkeypatch.setattr(browser_tool, "_provider_settings", provider_settings)

    with pytest.raises(DomainError, match="projection freeze drift"):
        browser_tool.run(
            database_url="postgresql://must-not-connect.invalid/db",
            credentials_path=credentials_path,
            context_evidence_path=context_path,
            output_path=output_path,
            candidate_sha=_SHA,
            candidate_freeze_path=freeze_path,
            provider_model=True,
        )

    assert provider_constructions == 0
    assert not output_path.exists()
