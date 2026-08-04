from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest

from src.brain.formal_readiness import capability_matrix, guide_truth
from src.shared.errors import DomainError
from src.tool.record_formal_capability_observations import (
    _registry_ids,
    _registry_records,
    _verify_evidence_sources,
    validate_observation_document,
)
from src.tool.render_tenant01_usage_guide import render_usage_guide
from src.tool.run_tenant01_formal_browser import _provider_settings


def _inputs() -> dict[str, object]:
    return {
        "brand_name": "笛语服饰",
        "source_documents": 19,
        "all_source_documents": 21,
        "template_documents": 2,
        "source_segments": 5046,
        "publication_confirmed": True,
        "publication_version": 2,
        "publication_items": 8,
        "publication_source_bound_items": 8,
        "publication_brand_facts": 3,
        "publication_expression_constraints": 3,
        "publication_creative_methods": 2,
        "product_media_products": 0,
        "confirmed_stores": 0,
        "formal_users": 2,
        "content_users": 1,
        "root_accounts": 1,
        "platform_targets": 4,
        "profile_accounts": 1,
        "active_products": 14,
        "allowed_product_fact_fields": 26,
        "product_fact_readiness": [
            {
                "sku": f"DIYU-CSPU-{index:03d}",
                "display_name": f"正式候选商品 {index}",
                "current_facts": {
                    "品类": "童装",
                    **({"主色": "藏蓝"} if index < 13 else {}),
                },
                "missing_fields": ["价格带", "功效", "面料倾向"],
            }
            for index in range(1, 15)
        ],
        "organization_media": 0,
        "formal_inventory_snapshots": 0,
        "display_users": 0,
        "formal_content_tasks": 0,
        "formal_content_versions": 0,
        "formal_display_tasks": 0,
        "schema_revision": "20260817_44",
        "evaluated_at": "2026-08-04T12:00:00+00:00",
        "observed_capability_ids": ["FT-001", "FT-038"],
    }


def test_capability_registry_is_exactly_the_supported_58_and_excludes_not_built() -> None:
    matrix = capability_matrix(
        _inputs(),
        viewer_role="tenant_admin",
        can_content=False,
        can_display=False,
        runtime_sha="a" * 40,
    )

    items = matrix["items"]
    assert isinstance(items, list)
    assert len(items) == 58
    identifiers = {str(item["id"]) for item in items}
    assert identifiers.isdisjoint({"FT-033", "FT-053", "FT-059", "FT-061", "FT-062", "FT-063"})
    assert matrix["summary"] == {
        "implemented": 58,
        "not_built": 6,
        "data_satisfied": 54,
        "permission_granted": 32,
        "formally_tested": 2,
    }
    factory_generation = next(item for item in items if item["id"] == "FT-038")
    assert factory_generation == {
        "id": "FT-038",
        "role": "租户用户",
        "route": "/content",
        "title": "“生成内容”显式成稿",
        "consumer": "interaction_mode=generate",
        "software_implemented": True,
        "data_state": "satisfied",
        "permission_state": "not_granted",
        "formally_tested": True,
        "supplement_href": "/user",
    }


def test_readiness_truth_changes_with_database_inputs_instead_of_static_numbers() -> None:
    before = _inputs()
    after = deepcopy(before)
    after.update(
        {
            "formal_users": 4,
            "content_users": 3,
            "organization_media": 6,
            "product_media_products": 2,
            "confirmed_stores": 1,
            "formal_inventory_snapshots": 1,
            "display_users": 1,
        }
    )

    before_guide = guide_truth(before)
    after_guide = guide_truth(after)
    before_counts = cast(dict[str, int], before_guide["current_counts"])
    after_counts = cast(dict[str, int], after_guide["current_counts"])
    before_missing = cast(list[dict[str, object]], before_guide["data_missing"])
    after_missing = cast(list[dict[str, object]], after_guide["data_missing"])
    assert before_counts != after_counts
    assert before_counts["formal_users"] == 2
    assert after_counts["formal_users"] == 4
    assert {item["id"] for item in before_missing if item["missing"]} == {
        "P4",
        "P5",
        "DM01",
    }
    assert not any(item["missing"] for item in after_missing)


def test_product_fact_guide_exposes_only_trusted_fields_and_names_missing_fields() -> None:
    guide = guide_truth(_inputs())
    products = cast(list[dict[str, object]], guide["product_fact_readiness"])

    assert len(products) == 14
    first = products[0]
    assert first["sku"] == "DIYU-CSPU-001"
    assert first["current_facts"] == [
        {"field": "主色", "value": "藏蓝"},
        {"field": "品类", "value": "童装"},
    ]
    assert first["missing_fields"] == ["价格带", "功效", "面料倾向"]
    assert "每次任务只加载该 SKU" in str(first["can_do"])
    assert "未列入当前可用事实" in str(first["cannot_promise"])
    status_meanings = cast(
        list[dict[str, object]], guide["service_status_meanings"]
    )
    assert {item["state"] for item in status_meanings} == {
        "unknown",
        "degraded",
        "unavailable",
    }


def test_user_matrix_keeps_software_data_permission_and_formal_test_separate() -> None:
    inputs = _inputs()
    inputs["allowed_product_fact_fields"] = 0
    matrix = capability_matrix(
        inputs,
        viewer_role="tenant_user",
        can_content=True,
        can_display=False,
        runtime_sha="b" * 40,
    )
    items = cast(list[dict[str, object]], matrix["items"])
    product_admin = next(item for item in items if item["id"] == "FT-029")
    content = next(item for item in items if item["id"] == "FT-038")
    display = next(item for item in items if item["id"] == "FT-050")
    assert product_admin["software_implemented"] is True
    assert product_admin["data_state"] == "partial"
    assert product_admin["permission_state"] == "not_granted"
    assert product_admin["formally_tested"] is False
    assert content["permission_state"] == "granted"
    assert content["formally_tested"] is True
    assert display["data_state"] == "missing"
    assert display["permission_state"] == "not_granted"


def test_authoritative_usage_guide_is_rendered_from_shared_dynamic_truth() -> None:
    inputs = _inputs()
    matrix = capability_matrix(
        inputs,
        viewer_role="tenant_admin",
        can_content=False,
        can_display=False,
        runtime_sha="a" * 40,
    )
    rendered = render_usage_guide(
        {
            "capability_matrix": matrix,
            "usage_guide": guide_truth(inputs),
        },
        candidate_sha="a" * 40,
        schema_revision="20260817_44",
        readiness_sha256="b" * 64,
    )

    assert "# 笛语服饰使用说明与能力就绪清单" in rendered
    assert "注册表共 58 项；这里的 58 只表示软件支持面" in rendered
    assert rendered.count("### DIYU-CSPU-") == 14
    assert "P4 `data_missing`" in rendered
    assert "P5 `data_missing`" in rendered
    assert "DM01 `data_missing`" in rendered
    assert "Readiness JSON SHA-256：`" + "b" * 64 + "`" in rendered


def test_formal_provider_browser_is_fixed_to_deepseek_and_zero_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_BASE_URL", "https://provider.example")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-never-logged")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    settings = _provider_settings("postgresql://test", "a" * 40)
    assert settings.generator_mode == "deepseek"
    assert settings.deepseek_model == "deepseek-v4-flash"
    assert settings.model_max_retries == 0
    assert settings.runtime_sha == "a" * 40

    monkeypatch.setenv("DEEPSEEK_MODEL", "unapproved-model")
    with pytest.raises(DomainError, match="deepseek-v4-flash"):
        _provider_settings("postgresql://test", "a" * 40)


def _formal_observation_document() -> dict[str, object]:
    registry = _registry_records()
    return {
        "schema_version": "tenant01-formal-capability-observations-v1",
        "tenant_id": str(uuid4()),
        "candidate_sha": "a" * 40,
        "schema_revision": "20260817_44",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "evidence_sources": [
            {
                "source_id": "formal-browser",
                "path": "formal-browser.json",
                "sha256": "c" * 64,
                "schema_version": "tenant01-formal-browser-evidence-v1",
            }
        ],
        "observations": [
            {
                "capability_id": capability_id,
                "verdict": "PASS",
                "route": registry[capability_id]["route"],
                "ui_control": "正式可见控件或明确服务入口",
                "api_consumer": registry[capability_id]["consumer"],
                "database_effect": "已核对无写入或精确业务对象变化",
                "visible_result": "正式用户可见结果符合合同",
                "error_recovery": "错误状态可行动且不丢输入",
                "evidence_refs": [f"formal-browser#{capability_id}"],
            }
            for capability_id in _registry_ids()
        ],
    }


def test_formal_observation_finalizer_requires_all_58_real_pass_references() -> None:
    document = _formal_observation_document()
    observations = validate_observation_document(
        document,
        expected_candidate_sha="a" * 40,
        expected_tenant_id=UUID(str(document["tenant_id"])),
    )
    assert len(observations) == 58
    assert {str(item["capability_id"]) for item in observations} == set(
        _registry_ids()
    )


@pytest.mark.parametrize(
    "mutation",
    (
        "missing",
        "duplicate",
        "prefilled_fail",
        "candidate_drift",
        "extra_field",
        "missing_reference",
        "consumer_drift",
        "unknown_check_source",
    ),
)
def test_formal_observation_finalizer_rejects_fake_green_mutations(
    mutation: str,
) -> None:
    document = _formal_observation_document()
    mutated = deepcopy(document)
    observations = mutated["observations"]
    assert isinstance(observations, list)
    assert all(isinstance(item, dict) for item in observations)
    if mutation == "missing":
        observations.pop()
    elif mutation == "duplicate":
        observations[-1] = deepcopy(observations[0])
    elif mutation == "prefilled_fail":
        observations[0]["verdict"] = "FAIL"
    elif mutation == "candidate_drift":
        mutated["candidate_sha"] = "b" * 40
    elif mutation == "extra_field":
        observations[0]["average_score"] = 100
    elif mutation == "missing_reference":
        observations[0]["evidence_refs"] = []
    elif mutation == "consumer_drift":
        observations[0]["api_consumer"] = "不存在的消费者"
    elif mutation == "unknown_check_source":
        observations[0]["evidence_refs"] = ["unknown-source#FT-001"]
    with pytest.raises(DomainError):
        validate_observation_document(
            mutated,
            expected_candidate_sha="a" * 40,
            expected_tenant_id=UUID(str(document["tenant_id"])),
        )


def test_formal_observation_finalizer_recomputes_source_digest_and_check_ids(
    tmp_path: Path,
) -> None:
    document = _formal_observation_document()
    tenant_id = UUID(str(document["tenant_id"]))
    source = {
        "schema_version": "tenant01-formal-browser-evidence-v1",
        "candidate_sha": "a" * 40,
        "tenant_id": str(tenant_id),
        "checks": [
            {"id": capability_id, "status": "PASS"}
            for capability_id in _registry_ids()
        ],
        "verdict": "PASS",
    }
    source_path = tmp_path / "formal-browser.json"
    source_path.write_text(json.dumps(source), encoding="utf-8")
    evidence_sources = document["evidence_sources"]
    assert isinstance(evidence_sources, list)
    assert isinstance(evidence_sources[0], dict)
    evidence_sources[0]["sha256"] = hashlib.sha256(source_path.read_bytes()).hexdigest()

    _verify_evidence_sources(
        document,
        observation_path=tmp_path / "observations.json",
        expected_candidate_sha="a" * 40,
        expected_tenant_id=tenant_id,
    )

    observations = document["observations"]
    assert isinstance(observations, list) and isinstance(observations[0], dict)
    observations[0]["evidence_refs"] = ["formal-browser#NOT-A-REAL-CHECK"]
    with pytest.raises(DomainError, match="不存在的 PASS check"):
        _verify_evidence_sources(
            document,
            observation_path=tmp_path / "observations.json",
            expected_candidate_sha="a" * 40,
            expected_tenant_id=tenant_id,
        )
