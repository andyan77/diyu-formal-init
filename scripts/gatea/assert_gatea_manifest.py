"""Fail-closed structural and semantic assertions for the Gate A manifest."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from build_import_manifest import load_contract, render_manifest

LOGGER = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "docs/BRAND-MATRIX-01/GateA-素材合同/import-contract.json"
MANIFEST_PATH = ROOT / "docs/BRAND-MATRIX-01/GateA-素材合同/import-manifest.json"
DIGEST_PATH = ROOT / "docs/BRAND-MATRIX-01/GateA-素材合同/import-manifest.sha256"
EXPECTED_COUNTS = {
    "accounts": 10,
    "organizations": 6,
    "deep_sku_packages": 4,
    "series": 2,
    "regional_store_entries": 31,
    "media_registry": 26,
    "judgments": 4,
    "amendments": 1,
    "anomaly_samples": 8,
    "source_documents": 25,
}
PROFILE_SEGMENTS = {
    "identity_position",
    "authority_boundary",
    "audience_relationship",
    "content_territory",
    "default_production_conditions",
}
ITEM_FIELDS = {
    "item_id",
    "source_document_id",
    "source_anchor",
    "content_class",
    "primary_channel",
    "consumer_products",
    "consumer_component",
    "applicable_account_ids",
    "organization_scope",
    "publishability",
    "version",
    "effective_at",
    "expires_at",
    "selection_priority",
    "exclusion_reason",
}
JUDGMENT_FIELDS = {
    "judgment_owner",
    "approved_by",
    "approved_at",
    "applicability_conditions",
    "evidence_refs",
    "version",
    "organization_scope",
    "effective_at",
    "expires_at",
}
ALLOWED_CHANNELS = {
    "profile_content_role",
    "product_fact_candidate",
    "expression_constraint",
    "creative_method",
    "regional_store_data",
    "media",
    "internal_template_not_publishable",
}


def load_json(path: Path) -> dict[str, Any]:
    """Load a JSON object from a UTF-8 file."""
    with path.open(encoding="utf-8") as handle:
        value: Any = json.load(handle)
    if not isinstance(value, dict):
        raise AssertionError(f"expected JSON object: {path}")
    return value


def assert_unique(rows: list[dict[str, Any]], field: str) -> None:
    """Require one unique non-empty value for a field in every row."""
    values = [row.get(field) for row in rows]
    if any(not value for value in values) or len(values) != len(set(values)):
        raise AssertionError(f"field must be non-empty and unique: {field}")


def assert_counts(manifest: dict[str, Any]) -> None:
    """Assert exact declared and actual counts."""
    if manifest.get("counts") != EXPECTED_COUNTS:
        raise AssertionError(f"declared counts mismatch: {manifest.get('counts')}")
    for section, expected in EXPECTED_COUNTS.items():
        rows = manifest.get(section)
        if not isinstance(rows, list) or len(rows) != expected:
            raise AssertionError(f"{section} must contain exactly {expected} rows")


def assert_source_classification(manifest: dict[str, Any]) -> None:
    """Assert 25 unique primary channels and atomic-item boundaries."""
    documents: list[dict[str, Any]] = manifest["source_documents"]
    assert_unique(documents, "document_id")
    for document in documents:
        if document.get("primary_channel") not in ALLOWED_CHANNELS:
            raise AssertionError(f"invalid primary channel: {document}")
        if not document.get("consumer") and not document.get("exclusion_reason"):
            raise AssertionError(f"document lacks consumer or exclusion reason: {document}")
    by_ordinal = {document["ordinal"]: document for document in documents}
    for ordinal in (2, 5, 7):
        if by_ordinal[ordinal]["primary_channel"] != "profile_content_role":
            raise AssertionError(f"document {ordinal} must be profile/ContentRole driven")

    items: list[dict[str, Any]] = manifest["consumption_items"]
    assert_unique(items, "item_id")
    source_ids = {document["document_id"] for document in documents}
    covered_sources = {item.get("source_document_id") for item in items}
    if covered_sources != source_ids:
        raise AssertionError(f"atomic item coverage mismatch: {source_ids ^ covered_sources}")
    for item in items:
        missing = ITEM_FIELDS - item.keys()
        if missing:
            raise AssertionError(f"atomic item {item.get('item_id')} missing fields: {missing}")
        if item["primary_channel"] not in ALLOWED_CHANNELS:
            raise AssertionError(f"atomic item has invalid channel: {item['item_id']}")
        if item.get("raw_markdown") is not False:
            raise AssertionError(f"raw Markdown cannot enter a consumer: {item['item_id']}")
        if item["primary_channel"] == "internal_template_not_publishable" and (
            item.get("writer_eligible") is not False or not item.get("exclusion_reason")
        ):
            raise AssertionError(f"internal item cannot enter Writer: {item['item_id']}")


def assert_accounts(manifest: dict[str, Any]) -> None:
    """Assert ten complete logical accounts, 50 profile segments, roles and organizations."""
    accounts: list[dict[str, Any]] = manifest["accounts"]
    assert_unique(accounts, "account_code")
    assert_unique(accounts, "logical_account_id")
    organizations = {row["organization_id"] for row in manifest["organizations"]}
    profile_count = 0
    for account in accounts:
        for field in (
            "display_name",
            "organization_id",
            "content_role_id",
            "content_role_version",
            "platform_format_targets",
            "planned_operation_qualifications",
            "historical_compatibility",
        ):
            if not account.get(field):
                raise AssertionError(f"account {account['account_code']} lacks {field}")
        if account["organization_id"] not in organizations:
            raise AssertionError(f"unknown organization on {account['account_code']}")
        segments = account.get("profile_segments")
        if not isinstance(segments, dict) or set(segments) != PROFILE_SEGMENTS:
            raise AssertionError(f"account {account['account_code']} profile is incomplete")
        for segment in segments.values():
            if not segment.get("summary") or not segment.get("source_anchor"):
                raise AssertionError(f"account {account['account_code']} has an empty profile segment")
        profile_count += len(segments)
    if profile_count != 50:
        raise AssertionError(f"expected 50 profile segments, found {profile_count}")


def assert_product_grades(manifest: dict[str, Any]) -> None:
    """Require V/P/C/R preservation and ProductFact admission from V only."""
    for package in manifest["deep_sku_packages"]:
        tiers = package.get("field_tiers")
        if not isinstance(tiers, dict) or set(tiers) != {"V", "P", "C", "R"}:
            raise AssertionError(f"SKU package lacks V/P/C/R: {package.get('cspu_id')}")
        product_facts = set(package.get("product_fact_fields", []))
        if not product_facts or not product_facts <= set(tiers["V"]):
            raise AssertionError(f"ProductFact contains non-V fields: {package.get('cspu_id')}")
        if product_facts & set(tiers["R"]):
            raise AssertionError(f"R field entered ProductFact: {package.get('cspu_id')}")


def assert_judgments(manifest: dict[str, Any]) -> None:
    """Assert four complete J records with ownership separated from founder approval."""
    judgments: list[dict[str, Any]] = manifest["judgments"]
    assert_unique(judgments, "judgment_id")
    for judgment in judgments:
        missing = JUDGMENT_FIELDS - judgment.keys()
        if missing:
            raise AssertionError(f"judgment {judgment['judgment_id']} missing fields: {missing}")
        owner = judgment["judgment_owner"]
        if owner.get("role") == "founder" or owner.get("account_id") != "H03":
            raise AssertionError(f"judgment owner must be product owner/H03: {judgment['judgment_id']}")
        if judgment["approved_by"] != "founder" or judgment["approved_at"] is not None:
            raise AssertionError(f"founder approval must remain unsigned: {judgment['judgment_id']}")
        if not judgment["applicability_conditions"] or not judgment["evidence_refs"]:
            raise AssertionError(f"judgment lacks conditions or evidence: {judgment['judgment_id']}")


def assert_media(manifest: dict[str, Any]) -> None:
    """Assert 26 complete pending media records without fabricated hashes or P5 eligibility."""
    media: list[dict[str, Any]] = manifest["media_registry"]
    assert_unique(media, "media_id")
    assert_unique(media, "target_master_name")
    for row in media:
        media_id = row["media_id"]
        required = {
            "source_filename_raw",
            "declared_identifier",
            "source_sha256",
            "sha_verification",
            "brand_identity_placement",
            "edit_plan",
            "founder_decision_ref",
            "rights_decisions",
            "third_party_verification",
            "person_child_authorization_evidence",
            "product_bindings",
            "target_account_ids",
            "target_platforms",
            "effective_at",
            "expires_at",
            "completion_status",
            "master_status",
            "master_sha256",
            "publication_gates",
            "p5_eligibility",
        }
        missing = required - row.keys()
        if missing:
            raise AssertionError(f"media {media_id} missing fields: {missing}")
        if row["source_sha256"] is not None or row["master_sha256"] is not None:
            raise AssertionError(f"media {media_id} contains an unverified SHA")
        if row["sha_verification"] != "pending_gate_d":
            raise AssertionError(f"media {media_id} SHA status must be pending_gate_d")
        if row["completion_status"] != "pending_gate_d" or row["master_status"] != "pending_gate_d":
            raise AssertionError(f"media {media_id} falsely claims completion")
        if row["p5_eligibility"] is not False:
            raise AssertionError(f"media {media_id} cannot be P5 eligible")
        if len(row["rights_decisions"]) != 4 or len(row["publication_gates"]) != 10:
            raise AssertionError(f"media {media_id} has incomplete rights or publication gates")


def assert_selection_contract(manifest: dict[str, Any]) -> None:
    """Assert explicit budgets and selected/excluded/overflow fields."""
    selection = manifest["selection_contract"]
    required = {
        "selection_policy_version",
        "selection_priority",
        "applicable_products",
        "applicable_accounts",
        "organization_scope",
        "max_items",
        "max_characters",
        "selected_item_ids",
        "excluded_item_ids",
        "overflow_reason",
    }
    if required - selection.keys():
        raise AssertionError("selection contract is incomplete")
    if "title_order_forbidden" not in selection["selection_priority"]:
        raise AssertionError("title-order selection must be explicitly forbidden")
    if not isinstance(selection["selected_item_ids"], list) or not isinstance(selection["excluded_item_ids"], list):
        raise AssertionError("selection IDs must be explicit lists")
    if not selection["overflow_reason"]:
        raise AssertionError("overflow reason contract cannot be empty")


def assert_human_contract(digest: str) -> None:
    """Require the human contract and blank attestation to bind the exact digest."""
    directory = ROOT / "docs/BRAND-MATRIX-01/GateA-素材合同"
    for name in ("README.md", "02-确定性导入合同.md", "08-founder素材定稿签署页.md"):
        text = (directory / name).read_text(encoding="utf-8")
        if digest not in text:
            raise AssertionError(f"{name} does not bind the manifest digest")
    signoff = (directory / "08-founder素材定稿签署页.md").read_text(encoding="utf-8")
    blanks_intact = (
        "签名：____________________" in signoff
        and "签署时间：____________________" in signoff
    )
    awaiting = "- 状态：`AWAITING_FOUNDER_SIGNOFF`" in signoff
    signed = (
        "## 签署记录（监理经手登记）" in signoff
        and "- 状态：`SIGNED · ATT-" in signoff
        and signoff.count(digest) >= 2
    )
    if awaiting and blanks_intact and not signed:
        return
    if signed and not blanks_intact and not awaiting:
        return
    raise AssertionError(
        "founder signoff page must be exactly blank-awaiting or signed-with-attestation"
    )


def main() -> None:
    """Run all deterministic Gate A manifest assertions."""
    contract = load_contract(CONTRACT_PATH)
    manifest_bytes = MANIFEST_PATH.read_bytes()
    expected_bytes = render_manifest(contract)
    if manifest_bytes != expected_bytes:
        raise AssertionError("manifest bytes do not match the deterministic contract render")
    digest = hashlib.sha256(manifest_bytes).hexdigest()
    sidecar = DIGEST_PATH.read_text(encoding="utf-8").strip()
    if sidecar != f"{digest}  {MANIFEST_PATH.name}":
        raise AssertionError("manifest digest sidecar mismatch")

    manifest = load_json(MANIFEST_PATH)
    assert_counts(manifest)
    assert_source_classification(manifest)
    assert_accounts(manifest)
    assert_product_grades(manifest)
    assert_judgments(manifest)
    assert_media(manifest)
    assert_selection_contract(manifest)
    if manifest["account_transition_plan"].get("observed_existing_count") != 9:
        raise AssertionError("account transition plan must start from nine observed accounts")
    if len(manifest["account_transition_plan"].get("existing_account_slots", [])) != 9:
        raise AssertionError("account transition plan must contain nine inventory slots")
    if not any(row.get("exclusion_id") == "D-07-KQ" for row in manifest["exclusions"]):
        raise AssertionError("D-07 exclusion is missing")
    assert_human_contract(digest)
    LOGGER.info("Gate A manifest PASS: sha256=%s", digest)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()
