#!/usr/bin/env python3
"""Apply and verify the founder media-rights attestation deterministically."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, cast

OLD_MANIFEST_DIGEST = "ab81e01fba2a83880c6d5ce38907cab849b60420a1f8fac2b181ddc34ca71a52"
ATTESTATION_ID = "ATT-MEDIA-20260808-01"
ATTESTATION_SCOPE = "internal_demo_and_demo_tenant_operation"
GOVERNANCE_COMMIT = "84234f34a745c6ecc7c10b4437025c526c899f14"
SCHEMA_VERSION = "gate-d-media-master-v2-attested-rights"
RIGHTS_GATES = frozenset(
    {
        "person_rights_evidence",
        "child_rights_evidence",
        "third_party_elements_evidence",
        "platform_scope_and_validity_evidence",
    }
)
UNCHANGED_GATES = {
    "source_checksum_verified": ("PASS", "SHA256SUMS independent verification"),
    "technical_master_valid": ("PASS", "ffprobe completed after rendering"),
    "brand_identifier_present": ("PASS", "gate-d-media-master-v1"),
    "commercial_use_decision": ("PASS", "DIYU-MEDIA-AUTH-DECISION-v2/D13"),
    "secondary_edit_decision": ("PASS", "DIYU-MEDIA-AUTH-DECISION-v2/D13"),
    "ai_recreation_decision": ("PASS", "DIYU-MEDIA-AUTH-DECISION-v2/D13"),
}
QUALIFYING_POOL = {
    "DIYU-V-001": "DIYU-CSPU-001",
    "DIYU-V-004": "DIYU-CSPU-006",
    "DIYU-V-005": "DIYU-CSPU-006",
    "DIYU-V-011": "DIYU-CSPU-008",
    "DIYU-V-022": "DIYU-CSPU-013",
    "DIYU-V-023": "DIYU-CSPU-013",
}
FORMAL_PRODUCTS = frozenset(QUALIFYING_POOL.values())


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain one JSON object")
    return cast(dict[str, Any], value)


def _digest(document: dict[str, Any]) -> str:
    payload = dict(document)
    payload.pop("manifest_digest", None)
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(serialized).hexdigest()


def _validate_common(document: dict[str, Any]) -> list[dict[str, Any]]:
    claimed = str(document.get("manifest_digest", ""))
    if len(claimed) != 64 or claimed != _digest(document):
        raise ValueError("media manifest digest is invalid")
    records = document.get("records")
    if not isinstance(records, list) or len(records) != 26:
        raise ValueError("media manifest must contain exactly 26 records")
    typed_records = cast(list[dict[str, Any]], records)
    expected_ids = {f"DIYU-V-{index:03d}" for index in range(1, 27)}
    if {str(record.get("media_id")) for record in typed_records} != expected_ids:
        raise ValueError("media IDs must be exactly DIYU-V-001..026")
    for record in typed_records:
        gates = record.get("ten_release_gates")
        if not isinstance(gates, list) or len(gates) != 10:
            raise ValueError(f"{record.get('media_id')} must have exactly ten release gates")
        by_name = {str(gate.get("gate")): gate for gate in cast(list[dict[str, Any]], gates)}
        if set(by_name) != set(UNCHANGED_GATES) | RIGHTS_GATES:
            raise ValueError(f"{record.get('media_id')} has an unexpected release gate set")
        for gate_name, (status, evidence) in UNCHANGED_GATES.items():
            if by_name[gate_name] != {
                "gate": gate_name,
                "status": status,
                "evidence": evidence,
            }:
                raise ValueError(
                    f"{record.get('media_id')} changed the frozen result for {gate_name}"
                )
        if record.get("original_p5_eligible") is not False:
            raise ValueError(f"{record.get('media_id')} incorrectly grants original P5 eligibility")
    return typed_records


def _validate_old(document: dict[str, Any], records: list[dict[str, Any]]) -> None:
    if document.get("manifest_digest") != OLD_MANIFEST_DIGEST:
        raise ValueError("input is not the frozen pre-attestation media manifest")
    if document.get("schema_version") != "gate-d-media-master-v1":
        raise ValueError("pre-attestation media schema version differs")
    for record in records:
        by_name = {
            str(gate["gate"]): gate
            for gate in cast(list[dict[str, Any]], record["ten_release_gates"])
        }
        if any(by_name[name].get("status") != "QUARANTINED" for name in RIGHTS_GATES):
            raise ValueError(f"{record['media_id']} rights gates are not in the frozen prior state")
        if (
            record.get("release_status") != "QUARANTINED"
            or record.get("master_p5_eligible") is not False
        ):
            raise ValueError(f"{record['media_id']} prior release state differs")


def _validate_unlocked(document: dict[str, Any], records: list[dict[str, Any]]) -> None:
    expected_top_level = {
        "source_count": 26,
        "master_count": 26,
        "pass_count": 26,
        "fail_count": 0,
        "quarantined_count": 0,
        "original_p5_eligible_count": 0,
    }
    for key, expected in expected_top_level.items():
        if document.get(key) != expected:
            raise ValueError(f"unlocked manifest {key} differs")
    if document.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unlocked media schema version differs")
    if document.get("prior_manifest_digest") != OLD_MANIFEST_DIGEST:
        raise ValueError("unlocked media manifest lacks the prior digest anchor")
    if document.get("media_rights_attestation") != {
        "attestation_id": ATTESTATION_ID,
        "governance_commit": GOVERNANCE_COMMIT,
        "scope": ATTESTATION_SCOPE,
    }:
        raise ValueError("media-rights attestation metadata differs")
    eligible = 0
    for record in records:
        gates = cast(list[dict[str, Any]], record["ten_release_gates"])
        by_name = {str(gate["gate"]): gate for gate in gates}
        for gate_name in RIGHTS_GATES:
            if by_name[gate_name] != {
                "gate": gate_name,
                "status": "PASS",
                "evidence": ATTESTATION_ID,
                "scope": ATTESTATION_SCOPE,
            }:
                raise ValueError(f"{record['media_id']} unlocked {gate_name} differs")
        formal_bindings = [
            str(value)
            for value in cast(list[object], record.get("product_bindings", []))
            if str(value) in FORMAL_PRODUCTS
        ]
        expected_p5 = bool(formal_bindings)
        if (
            record.get("release_status") != "PASS"
            or record.get("master_p5_eligible") != expected_p5
            or record.get("formal_product_bindings") != formal_bindings
            or record.get("media_rights_attestation_ref") != ATTESTATION_ID
        ):
            raise ValueError(f"{record['media_id']} unlocked release state differs")
        eligible += int(expected_p5)
    if document.get("master_p5_eligible_count") != eligible:
        raise ValueError("unlocked media P5 count differs")


def unlock(document: dict[str, Any]) -> dict[str, Any]:
    records = _validate_common(document)
    _validate_old(document, records)
    for record in records:
        gates = cast(list[dict[str, Any]], record["ten_release_gates"])
        # Rebuild by name so the original ten-gate order stays byte-stable.
        rebuilt: list[dict[str, str]] = []
        for gate in gates:
            gate_name = str(gate.get("gate", ""))
            if not gate_name:
                raise AssertionError("rights gate name was lost")
            if gate_name in RIGHTS_GATES:
                rebuilt.append(
                    {
                        "gate": gate_name,
                        "status": "PASS",
                        "evidence": ATTESTATION_ID,
                        "scope": ATTESTATION_SCOPE,
                    }
                )
            else:
                rebuilt.append(cast(dict[str, str], gate))
        record["ten_release_gates"] = rebuilt
        record["media_rights_attestation_ref"] = ATTESTATION_ID
        record["release_status"] = "PASS"
        formal_bindings = [
            str(value)
            for value in cast(list[object], record.get("product_bindings", []))
            if str(value) in FORMAL_PRODUCTS
        ]
        record["formal_product_bindings"] = formal_bindings
        record["master_p5_eligible"] = bool(formal_bindings)
    document["schema_version"] = SCHEMA_VERSION
    document["prior_manifest_digest"] = OLD_MANIFEST_DIGEST
    document["media_rights_attestation"] = {
        "attestation_id": ATTESTATION_ID,
        "governance_commit": GOVERNANCE_COMMIT,
        "scope": ATTESTATION_SCOPE,
    }
    document["pass_count"] = 26
    document["fail_count"] = 0
    document["quarantined_count"] = 0
    document["original_p5_eligible_count"] = 0
    document["master_p5_eligible_count"] = sum(
        bool(record.get("master_p5_eligible")) for record in records
    )
    document["manifest_digest"] = _digest(document)
    _validate_unlocked(document, _validate_common(document))
    return document


def _p5_evidence(
    manifest: dict[str, Any],
    contract: dict[str, Any],
    import_evidence: dict[str, Any],
) -> dict[str, Any]:
    packages = contract.get("deep_sku_packages")
    if not isinstance(packages, list):
        raise ValueError("Gate A contract lacks deep_sku_packages")
    contract_products = {
        str(item.get("cspu_id")) for item in cast(list[dict[str, Any]], packages)
    }
    if contract_products != FORMAL_PRODUCTS:
        raise ValueError("Gate A deep SKU package IDs differ from the frozen four-product pool")
    rounds = [import_evidence.get("round_one"), import_evidence.get("round_two")]
    for round_value in rounds:
        if not isinstance(round_value, dict):
            raise ValueError("two-round import evidence is incomplete")
        inventory = round_value.get("inventory")
        if not isinstance(inventory, dict) or inventory.get("products") != 4:
            raise ValueError("two-round import evidence does not prove four formal products")
    records = {
        str(record["media_id"]): record
        for record in cast(list[dict[str, Any]], manifest["records"])
    }
    qualifying: list[dict[str, str]] = []
    for media_id, product_id in sorted(QUALIFYING_POOL.items()):
        record = records[media_id]
        if (
            record.get("release_status") == "PASS"
            and record.get("master_p5_eligible") is True
            and product_id in cast(list[str], record.get("product_bindings", []))
        ):
            qualifying.append({"media_id": media_id, "product_id": product_id})
    distinct_products = sorted({item["product_id"] for item in qualifying})
    if len(qualifying) < 2 or len(distinct_products) < 2:
        raise ValueError("P5 requires two PASS masters bound to two distinct formal products")
    first_round = cast(dict[str, Any], rounds[0])
    return {
        "attestation_id": ATTESTATION_ID,
        "scope": ATTESTATION_SCOPE,
        "prior_media_manifest_digest": OLD_MANIFEST_DIGEST,
        "media_manifest_digest": manifest["manifest_digest"],
        "import_batch_digest": first_round["batch_digest"],
        "import_object_fingerprint": first_round["object_fingerprint"],
        "formal_product_ids": sorted(contract_products),
        "qualifying_media_product_pairs": qualifying,
        "distinct_qualifying_product_ids": distinct_products,
        "p5_precondition_satisfied": True,
        "provider_requests_before_candidate_freeze": 0,
        "status": "READY_FOR_CANDIDATE_FREEZE",
    }


def _write_json(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--import-evidence", type=Path)
    parser.add_argument("--unlock-evidence", type=Path)
    parser.add_argument("--apply", action="store_true")
    arguments = parser.parse_args()
    document = _load_object(arguments.manifest)
    if arguments.apply:
        document = unlock(document)
        _write_json(arguments.manifest, document)
    else:
        records = _validate_common(document)
        _validate_unlocked(document, records)
    if any(
        value is None
        for value in (arguments.contract, arguments.import_evidence, arguments.unlock_evidence)
    ):
        if any(
            value is not None
            for value in (arguments.contract, arguments.import_evidence, arguments.unlock_evidence)
        ):
            raise ValueError("contract, import evidence and unlock evidence must be supplied together")
    else:
        evidence = _p5_evidence(
            document,
            _load_object(cast(Path, arguments.contract)),
            _load_object(cast(Path, arguments.import_evidence)),
        )
        _write_json(cast(Path, arguments.unlock_evidence), evidence)
    print(
        "GATED_MEDIA_UNLOCK_OK "
        f"old_digest={OLD_MANIFEST_DIGEST} new_digest={document['manifest_digest']} "
        f"pass={document['pass_count']} fail={document['fail_count']} "
        f"quarantined={document['quarantined_count']} "
        f"master_p5={document['master_p5_eligible_count']} original_p5=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
