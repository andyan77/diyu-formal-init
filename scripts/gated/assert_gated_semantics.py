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
        "pass_count": 0,
        "fail_count": 0,
        "quarantined_count": 26,
        "original_p5_eligible_count": 0,
        "master_p5_eligible_count": 0,
    }
    for key, value in expected.items():
        if document.get(key) != value:
            raise SystemExit(f"Gate D semantics FAIL: media {key} differs")
    records = cast(list[dict[str, Any]], document.get("records"))
    if len(records) != 26 or len({record.get("media_id") for record in records}) != 26:
        raise SystemExit("Gate D semantics FAIL: media rows are not 26 unique records")
    for record in records:
        gates = cast(list[dict[str, Any]], record.get("ten_release_gates"))
        if (
            len(gates) != 10
            or record.get("release_status") != "QUARANTINED"
            or record.get("original_p5_eligible") is not False
            or record.get("master_p5_eligible") is not False
            or len(str(record.get("source_sha256", ""))) != 64
            or len(str(record.get("master_sha256", ""))) != 64
        ):
            raise SystemExit("Gate D semantics FAIL: a media row violates the quarantine contract")
    frozen = dict(document)
    claimed = str(frozen.pop("manifest_digest", ""))
    canonical = json.dumps(frozen, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    if claimed != hashlib.sha256(canonical).hexdigest():
        raise SystemExit("Gate D semantics FAIL: media manifest digest differs")
    return claimed


def main() -> None:
    _assert_d0()
    batch_digest, fingerprint = _assert_import()
    _assert_consumers()
    media_digest = _assert_media()
    print(
        "GATED_SEMANTICS_OK "
        f"batch_digest={batch_digest} object_fingerprint={fingerprint} "
        f"media_digest={media_digest} roots=10 carriers=20 accounts=30 targets=40 "
        "local_entries=31 J=4 authorizations=2 masters=26 quarantined=26 p5_eligible=0 "
        "provider_requests=0 terminal=MEDIA_QUALIFICATION_INSUFFICIENT"
    )


if __name__ == "__main__":
    main()
