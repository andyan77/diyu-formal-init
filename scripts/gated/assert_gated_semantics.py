#!/usr/bin/env python3
"""Fail-closed structural and evidence assertions for Gate D."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

_ROOT = Path(__file__).resolve().parents[2]
_EVIDENCE = _ROOT / "docs/BRAND-MATRIX-01/GateD-记录"
_EXPECTED_INVENTORY = {
    "logical_roots": 10,
    "carrier_rows": 20,
    "matrix_content_accounts": 30,
    "platform_format_targets": 40,
    "legacy_hidden_accounts": 9,
    "legacy_tasks_readable": 1,
    "organizations": 6,
    "regional_store_entries": 31,
    "judgments": 4,
    "products": 4,
    "series": 2,
    "authorizations": 2,
    "qualifications": 30,
    "projection_items": 34,
    "regional_store_projection_items": 28,
    "expired_rk_ec_08": 1,
}
_D0_TESTS = (
    "test_gated_d0_v2_preview_confirm_task_snapshot_and_feedback",
    "test_gated_d0_api_contract_forbids_client_owned_governance_fields",
)
_MEDIA_DIGEST = "587d821315d896c414b382a1f277a07e1f7290f95cb8e0d829334cc53efc335b"
_PRIOR_MEDIA_DIGEST = "ab81e01fba2a83880c6d5ce38907cab849b60420a1f8fac2b181ddc34ca71a52"
_MEDIA_ATTESTATION = "ATT-MEDIA-20260808-01"
_MEDIA_SCOPE = "internal_demo_and_demo_tenant_operation"
_RIGHTS_GATES = {
    "person_rights_evidence",
    "child_rights_evidence",
    "third_party_elements_evidence",
    "platform_scope_and_validity_evidence",
}


def _document(name: str) -> dict[str, Any]:
    value = json.loads((_EVIDENCE / name).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"Gate D semantics FAIL: {name} must contain an object")
    return cast(dict[str, Any], value)


def _source(path: str) -> str:
    return (_ROOT / path).read_text(encoding="utf-8")


def _require(source: str, markers: tuple[str, ...], label: str) -> None:
    missing = [marker for marker in markers if marker not in source]
    if missing:
        raise SystemExit(f"Gate D semantics FAIL ({label}): missing {missing}")


def _assert_d0() -> None:
    contracts = _source("src/gateway/api/contracts.py")
    app = _source("src/gateway/api/app.py") + _source("src/gateway/api/gated_routes.py")
    service = _source("src/brain/workbench_service.py")
    repository = _source("src/infrastructure/workbench_repository.py")
    importer = _source("scripts/gated/brand_matrix_importer.py")
    tests = _source("tests/test_gated_d0.py")
    frontend = _source("frontend/src/app/TenantAdminApp.tsx")
    _require(
        contracts,
        ("source_segment_id: UUID", "visibility_scope:", "organization_ids:", "fact_subject:"),
        "business-owned request",
    )
    _require(
        app,
        (
            '"/api/v1/tenant-management/brand-publication/preview"',
            '"/api/v1/tenant-management/brand-feedback-observations"',
            '"/api/v1/tenant-management/brand-relevance-governance"',
        ),
        "formal API",
    )
    _require(
        service + repository,
        (
            "brand-publication-projection-v2",
            "scope_organization_ids",
            "authority_class",
            "semantic_subject_type",
            "claim_key",
            "scope_contract_version",
            "source_digest",
            "brand_feedback_observations",
            "brand_relevance_qualifications",
        ),
        "server-owned V2 derivation",
    )
    _require(frontend, ("预览 V2 合同", "fact_subject", "organization_ids"), "React D0 surface")
    _require(importer, ("class BrandMatrixImporter", "logical_root_accounts"), "isolated importer")
    _require(tests, _D0_TESTS, "formal D0 vertical tests")


def _assert_import() -> tuple[str, str]:
    evidence = _document("import-rehearsal-evidence.json")
    first = cast(dict[str, Any], evidence.get("round_one"))
    second = cast(dict[str, Any], evidence.get("round_two"))
    if not evidence.get("byte_identical_batch_digest") or not evidence.get(
        "byte_identical_object_fingerprint"
    ):
        raise SystemExit("Gate D semantics FAIL: two-round equality flags are false")
    for key in ("batch_digest", "object_fingerprint"):
        if first.get(key) != second.get(key) or len(str(first.get(key, ""))) != 64:
            raise SystemExit(f"Gate D semantics FAIL: two-round {key} differs")
    for round_value in (first, second):
        inventory = cast(dict[str, Any], round_value.get("inventory"))
        for key, expected in _EXPECTED_INVENTORY.items():
            if inventory.get(key) != expected:
                raise SystemExit(
                    f"Gate D semantics FAIL: inventory {key}={inventory.get(key)} expected={expected}"
                )
        readback = cast(dict[str, Any], round_value.get("formal_readback"))
        if readback != {
            "authorizations": 2,
            "logical_root_accounts": 10,
            "platform_targets": 40,
            "projection_contract_version": "brand-publication-projection-v2",
            "projection_items": 34,
            "qualifications": 30,
        }:
            raise SystemExit("Gate D semantics FAIL: formal importer readback differs")
    return str(first["batch_digest"]), str(first["object_fingerprint"])


def _assert_consumers() -> None:
    evidence = _document("formal-consumer-evidence.json")
    if evidence.get("provider_requests") != 0:
        raise SystemExit("Gate D semantics FAIL: a provider request occurred before freeze")
    scope = cast(dict[str, Any], evidence.get("scope_consumption"))
    required_positive = (
        "headquarters_global_positive",
        "east_positive",
        "sichuan_positive",
        "hangzhou_positive",
        "huzhou_positive",
        "chengdu_positive",
    )
    if not all(scope.get(key) is True for key in required_positive):
        raise SystemExit("Gate D semantics FAIL: an organization positive consumer is missing")
    if scope.get("sibling_scope_leaks") != 0 or scope.get("expired_rk_ec_08_consumptions") != 0:
        raise SystemExit("Gate D semantics FAIL: organization or lifecycle isolation failed")
    task_snapshots = cast(list[dict[str, Any]], scope.get("formal_task_snapshots"))
    if (
        len(task_snapshots) != 7
        or {item.get("account_code") for item in task_snapshots}
        != {"H01", "R01", "R02", "S01", "S02", "S03", "S04"}
        or any(not item.get("projection_item_ids") for item in task_snapshots)
        or any(item.get("provider_requests") != 0 for item in task_snapshots)
    ):
        raise SystemExit("Gate D semantics FAIL: formal organization task snapshots differ")
    judgments = cast(dict[str, Any], evidence.get("judgment_consumption"))
    if judgments.get("p1_consumers") != 4 or judgments.get("p2_consumers") != 4:
        raise SystemExit("Gate D semantics FAIL: four J decisions did not reach P1 and P2")
    if len(cast(list[object], judgments.get("judgments"))) != 4:
        raise SystemExit("Gate D semantics FAIL: J evidence count differs")
    authorization = cast(dict[str, Any], evidence.get("authorization_consumption"))
    fixtures = cast(list[dict[str, Any]], authorization.get("authorization_fixtures"))
    if {fixture.get("subject_ref") for fixture in fixtures} != {"PS-S02-05", "PS-S04-03"}:
        raise SystemExit("Gate D semantics FAIL: authorization fixtures differ")
    for fixture in fixtures:
        if not all(
            fixture.get(key) is True
            for key in (
                "failed_run_released",
                "independent_task_rejected",
                "same_lineage_v2_without_second_consumption",
                "v1_consumed_once",
            )
        ):
            raise SystemExit("Gate D semantics FAIL: authorization state-machine evidence failed")


def _assert_media() -> str:
    document = _document("media-master-manifest.json")
    expected = {
        "source_count": 26,
        "master_count": 26,
        "pass_count": 26,
        "fail_count": 0,
        "quarantined_count": 0,
        "original_p5_eligible_count": 0,
        "master_p5_eligible_count": 6,
    }
    for key, value in expected.items():
        if document.get(key) != value:
            raise SystemExit(f"Gate D semantics FAIL: media {key} differs")
    records = cast(list[dict[str, Any]], document.get("records"))
    if len(records) != 26 or len({record.get("media_id") for record in records}) != 26:
        raise SystemExit("Gate D semantics FAIL: media rows are not 26 unique records")
    eligible_pairs: set[tuple[str, str]] = set()
    for record in records:
        gates = cast(list[dict[str, Any]], record.get("ten_release_gates"))
        by_name = {str(gate.get("gate")): gate for gate in gates}
        formal_bindings = cast(list[str], record.get("formal_product_bindings"))
        if (
            len(gates) != 10
            or record.get("release_status") != "PASS"
            or record.get("original_p5_eligible") is not False
            or record.get("master_p5_eligible") != bool(formal_bindings)
            or record.get("media_rights_attestation_ref") != _MEDIA_ATTESTATION
            or len(str(record.get("source_sha256", ""))) != 64
            or len(str(record.get("master_sha256", ""))) != 64
        ):
            raise SystemExit("Gate D semantics FAIL: a media row violates the unlocked contract")
        for gate_name in _RIGHTS_GATES:
            if by_name.get(gate_name) != {
                "gate": gate_name,
                "status": "PASS",
                "evidence": _MEDIA_ATTESTATION,
                "scope": _MEDIA_SCOPE,
            }:
                raise SystemExit("Gate D semantics FAIL: a media rights gate differs")
        for sku in formal_bindings:
            eligible_pairs.add((str(record["media_id"]), sku))
    frozen = dict(document)
    claimed = str(frozen.pop("manifest_digest", ""))
    canonical = json.dumps(frozen, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    if (
        claimed != _MEDIA_DIGEST
        or claimed != hashlib.sha256(canonical).hexdigest()
        or document.get("prior_manifest_digest") != _PRIOR_MEDIA_DIGEST
        or document.get("media_rights_attestation")
        != {
            "attestation_id": _MEDIA_ATTESTATION,
            "governance_commit": "84234f34a745c6ecc7c10b4437025c526c899f14",
            "scope": _MEDIA_SCOPE,
        }
    ):
        raise SystemExit("Gate D semantics FAIL: media manifest digest differs")
    required_pairs = {
        ("DIYU-V-001", "DIYU-CSPU-001"),
        ("DIYU-V-004", "DIYU-CSPU-006"),
        ("DIYU-V-005", "DIYU-CSPU-006"),
        ("DIYU-V-011", "DIYU-CSPU-008"),
        ("DIYU-V-022", "DIYU-CSPU-013"),
        ("DIYU-V-023", "DIYU-CSPU-013"),
    }
    if eligible_pairs != required_pairs:
        raise SystemExit("Gate D semantics FAIL: formal P5 media pool differs")
    attestation = (_EVIDENCE / "媒体权利授权-ATT-MEDIA-20260808-01.md").read_text(
        encoding="utf-8"
    )
    if (
        "「裁决：A；覆盖26条，确认授权；" not in attestation
        or _MEDIA_SCOPE not in attestation
        or "真实对外公开发布" not in attestation
    ):
        raise SystemExit("Gate D semantics FAIL: media attestation record is incomplete")
    unlock = _document("media-unlock-evidence.json")
    if (
        unlock.get("prior_media_manifest_digest") != _PRIOR_MEDIA_DIGEST
        or unlock.get("media_manifest_digest") != claimed
        or unlock.get("p5_precondition_satisfied") is not True
        or len(cast(list[object], unlock.get("distinct_qualifying_product_ids"))) != 4
    ):
        raise SystemExit("Gate D semantics FAIL: P5 unlock evidence differs")
    readback = _document("media-database-readback.json")
    readback_unsigned = dict(readback)
    readback_digest = str(readback_unsigned.pop("readback_digest", ""))
    if (
        readback.get("media_manifest_digest") != claimed
        or readback.get("asset_count") != 26
        or readback.get("formal_binding_count") != 6
        or readback.get("p5_eligible_master_count") != 6
        or readback_digest
        != hashlib.sha256(
            json.dumps(
                readback_unsigned,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
        ).hexdigest()
    ):
        raise SystemExit("Gate D semantics FAIL: isolated media database readback differs")
    return claimed


def _assert_formal_suite_contract() -> None:
    contract = _document("formal-suite-contract.json")
    if (
        contract.get("suite_version") != "brand-matrix-gate-d-formal-suite-v5"
        or contract.get("expected_counts")
        != {"anomalies": 8, "cards": 15, "content_products": 5, "scenarios": 8}
    ):
        raise SystemExit("Gate D semantics FAIL: formal suite counts differ")
    constraints = cast(dict[str, Any], contract.get("constraints"))
    if (
        constraints.get("maximum_provider_requests") != 80
        or constraints.get("maximum_transport_retries") != 0
        or constraints.get("prior_provider_requests") != 10
        or constraints.get("temperature") != 0
        or constraints.get("writer_assertion_policy")
        != "ADJ-WRITER-BOUNDARY-04-EXACT-ABSOLUTE"
    ):
        raise SystemExit("Gate D semantics FAIL: formal provider discipline differs")
    cards = cast(list[dict[str, Any]], contract.get("cards"))
    anomalies = cast(list[dict[str, Any]], contract.get("anomalies"))
    if (
        len(cards) != 15
        or len({str(item.get("id")) for item in cards}) != 15
        or len(anomalies) != 8
        or len({str(item.get("id")) for item in anomalies}) != 8
        or {str(item.get("content_product")) for item in cards}
        != {
            "dressing_decision",
            "product_truth",
            "brand_life_narrative",
            "local_response",
            "visual_styling_story",
        }
    ):
        raise SystemExit("Gate D semantics FAIL: formal suite coverage differs")
    internal_prompt_terms = (
        "门店普通文件",
        "已登记母版",
        "当前有效区域资料",
        "当前有效资料",
        "登记一条门店反馈观察",
        "不得使用未确认反馈",
    )
    if any(
        term in str(card.get("seed", ""))
        for card in cards
        for term in internal_prompt_terms
    ):
        raise SystemExit("Gate D semantics FAIL: formal cards expose internal governance language")
    runner = _source("scripts/gated/run_formal_acceptance.py")
    _require(
        runner,
        (
            '"temperature": 0.0',
            "max_retries=0",
            "each formal card must receive exactly one Writer response",
            "GATED_FORMAL_SUITE_FAILED_SAFE",
        ),
        "formal frozen runner",
    )
    factual_boundary = _source("src/shared/factual_basis.py")
    _require(
        factual_boundary,
        (
            "def product_fact_value_conflicts(",
            "def unconfirmed_product_specificity_spans(",
            '"composition_percentage"',
            '"price_amount"',
            '"exact_process"',
            '"age_range"',
            '"guaranteed_performance_assertion"',
            '"absolute_claim"',
            "(?:永不|绝不)",
        ),
        "Writer factual boundary",
    )
    if "(?:全网|行业|同类|史上|市面上)?最" in factual_boundary:
        raise SystemExit("Gate D semantics FAIL: ambiguous superlatives remain machine-blocked")
    writer = _source("src/tool/llm_gateway/deepseek.py")
    _require(
        writer,
        (
            "confirmed_product_facts=confirmed_product_facts",
            "product_fact_value_conflicts(context.product_fact_packet, visible)",
            "unconfirmed_product_specificity_spans(visible)",
            "used_persona_quote_ids",
            "ADJ-WRITER-BOUNDARY-04 三层制",
            "最舒适／业内第一／全网最好",
            "最好不要／最好先／第一眼",
            "L2 是不取得事实资格的软性体验表达",
            "不得写入 ProductFact",
            "如果你需要／如果你的条件是",
            "账号画像只提供观察角度，不提供自传",
        ),
        "Writer truth and persona prompt boundary",
    )
    if "product_fact_literal_spans(context.product_fact_packet, visible)" in writer:
        raise SystemExit("Gate D semantics FAIL: confirmed product literals remain forbidden")
    tests = _source("tests/test_deepseek_adapter.py")
    _require(
        tests,
        (
            "test_publication_v3_allows_l2_soft_experience_words",
            "test_publication_v3_allows_prior_s01_p1_l2_boundary_excerpt",
            "test_publication_v3_allows_ambiguous_daily_suggestion_words",
            "test_publication_v3_allows_prior_s01_p2_absolute_claim_false_positive",
            "整套搭配里最好不要再出现第二个强色",
            "先看这一眼",
            "这件商品保证不起球",
            "这件商品100%纯棉",
            "这件商品永不变形",
            "这件商品绝不掉色",
        ),
        "Writer assertion-layer regression",
    )
    repository = _source("src/infrastructure/postgres_repository.py")
    _require(
        repository,
        (
            '"writer_confirmed_product_fact_refs"',
            '"used_persona_quote_ids"',
            "_PUBLICATION_V3_LEGACY_COMPLETION_KEYS",
            "_validate_publication_v3_grounding",
            "Writer 确认商品事实引用超出冻结事实包",
            "Writer 单次人设原句与冻结核销授权不一致",
        ),
        "publication-v3 completion grounding",
    )
    snapshot_tests = _source("tests/test_gated_d0.py")
    _require(
        snapshot_tests,
        (
            "test_gated_rerun03_completion_snapshot_commits_the_failed_shape",
            "test_gated_rerun03_completion_snapshot_stays_fail_closed_and_legacy_safe",
            "test_gated_rerun03_completion_grounding_rejects_invalid_shapes",
            "test_gated_rerun03_single_use_quote_matches_frozen_authorization",
            "3bafbf45-fb92-45ae-b832-984ef425a5f8",
            "27b810b8-f219-4d72-aaf8-b2b1aee1f80e",
        ),
        "publication-v3 completion snapshot regression",
    )


def main() -> None:
    _assert_d0()
    batch_digest, fingerprint = _assert_import()
    _assert_consumers()
    media_digest = _assert_media()
    _assert_formal_suite_contract()
    print(
        "GATED_SEMANTICS_OK "
        f"batch_digest={batch_digest} object_fingerprint={fingerprint} "
        f"media_digest={media_digest} roots=10 carriers=20 accounts=30 targets=40 "
        "local_entries=31 J=4 authorizations=2 masters=26 pass=26 quarantined=0 "
        "p5_eligible=6 distinct_p5_products=4 provider_requests_before_freeze=0 "
        "terminal=READY_FOR_RUNTIME_FREEZE"
    )


if __name__ == "__main__":
    main()
