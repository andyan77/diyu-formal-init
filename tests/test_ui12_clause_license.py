from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

from src.shared.clause_license import (
    CLAUSE_LICENSE_REVIEW_VERSION,
    ClauseLicenseReviewsV1,
    ClauseLicenseReviewV1,
    UnitClauseLicensePolicyV1,
    build_unit_clause_license_policies_v1,
    clause_license_review_json_schema,
    materialize_clause_licenses_v1,
    parse_clause_license_reviews_v1,
    reconcile_clause_license_reviews_v1,
)
from src.shared.narrative import FRAME_VERSION, FrozenUserFact, NarrativeFrame
from src.shared.review_evidence import ClauseContextV2, UnitContractV2

_FIXTURE = Path("tests/fixtures/ui12_clause_license_pairs_v1.json")
_FACT_ID = "source:user_actuality:pair"
_FACT_TEXT = "今天店里忙了一天，回家还因为谁洗碗拌了两句。"


def _samples() -> tuple[dict[str, Any], ...]:
    raw = json.loads(_FIXTURE.read_text())
    assert isinstance(raw, dict)
    assert raw["fixture_version"] == "ui12-clause-license-pairs-v1"
    return tuple(cast(list[dict[str, Any]], raw["samples"]))


def _frame() -> NarrativeFrame:
    return NarrativeFrame(
        frame_version=FRAME_VERSION,
        narrative_mode="actuality_reflection",
        user_facts=(FrozenUserFact(_FACT_ID, _FACT_TEXT),),
        allowed_brand_fact_ids=(),
        allowed_product_fact_ids=(),
    )


def _contexts(
    text: str,
    *,
    contract: UnitContractV2 = "actuality_reflection",
) -> tuple[ClauseContextV2, ...]:
    return (
        ClauseContextV2(
            clause_id="unit:frozen-fact:1:clause:1",
            unit_id="unit:frozen-fact:1",
            exact_text=_FACT_TEXT,
            visible_order=31001,
            text_source="frozen_user_fact",
            unit_contract="frozen_fact",
            speaker_kind="personal_ip_account",
            fact_ref=_FACT_ID,
        ),
        ClauseContextV2(
            clause_id="unit:body:clause:1",
            unit_id="unit:body",
            exact_text=text,
            visible_order=100001,
            text_source="writer_unit",
            unit_contract=contract,
            speaker_kind="personal_ip_account",
        ),
    )


def _policy(
    contract: UnitContractV2 = "actuality_reflection",
) -> tuple[UnitClauseLicensePolicyV1, ...]:
    return build_unit_clause_license_policies_v1(
        frame=_frame(),
        unit_contracts={"unit:body": contract},
    )


def _review(
    *,
    contexts: tuple[ClauseContextV2, ...],
    verdict: str,
    reason_code: str,
    quote: str,
    policies: tuple[UnitClauseLicensePolicyV1, ...] | None = None,
) -> tuple[
    tuple[UnitClauseLicensePolicyV1, ...],
    ClauseLicenseReviewsV1,
]:
    trusted_policies = policies or _policy(contexts[-1].unit_contract)
    licenses = materialize_clause_licenses_v1(
        contexts=contexts,
        policies=trusted_policies,
    )
    parsed = parse_clause_license_reviews_v1(
        {
            "review_version": CLAUSE_LICENSE_REVIEW_VERSION,
            "reviews": [
                {
                    "clause_id": licenses[0].clause_id,
                    "license_id": licenses[0].license_id,
                    "verdict": verdict,
                    "reason_code": reason_code,
                    "unsupported_quote": quote,
                }
            ],
        },
        licenses=licenses,
    )
    return trusted_policies, parsed


@pytest.mark.parametrize(
    "sample",
    tuple(sample for sample in _samples() if sample["unit_contract"] != "frozen_fact"),
    ids=lambda sample: cast(dict[str, Any], sample)["sample_id"],
)
def test_paired_clause_license_rulings(sample: dict[str, Any]) -> None:
    contract = cast(UnitContractV2, sample["unit_contract"])
    contexts = _contexts(cast(str, sample["exact_text"]), contract=contract)
    policies = _policy(contract)
    licenses = materialize_clause_licenses_v1(
        contexts=contexts,
        policies=policies,
    )
    _, reviews = _review(
        contexts=contexts,
        verdict=cast(str, sample["license_verdict"]),
        reason_code=cast(str, sample["reason_code"]),
        quote=cast(str, sample["unsupported_quote"]),
        policies=policies,
    )
    result = reconcile_clause_license_reviews_v1(
        contexts=contexts,
        policies=policies,
        licenses=licenses,
        reviews=reviews,
        fact_text_by_id={_FACT_ID: _FACT_TEXT},
    )
    if sample["license_verdict"] == "supported":
        assert result.issues == ()
    else:
        assert result.issues


def test_frozen_fact_is_structurally_valid_only_with_exact_text_and_ref() -> None:
    contexts = _contexts("换位思考不等于没有边界。")
    policies = _policy()
    licenses = materialize_clause_licenses_v1(
        contexts=contexts,
        policies=policies,
    )
    _, reviews = _review(
        contexts=contexts,
        verdict="supported",
        reason_code="supported_by_license",
        quote="",
        policies=policies,
    )
    assert (
        reconcile_clause_license_reviews_v1(
            contexts=contexts,
            policies=policies,
            licenses=licenses,
            reviews=reviews,
            fact_text_by_id={_FACT_ID: _FACT_TEXT},
        ).issues
        == ()
    )
    changed = (replace(contexts[0], exact_text="今天店里不忙。"), *contexts[1:])
    assert {
        issue.reason
        for issue in reconcile_clause_license_reviews_v1(
            contexts=changed,
            policies=policies,
            licenses=licenses,
            reviews=reviews,
            fact_text_by_id={_FACT_ID: _FACT_TEXT},
        ).issues
    } == {"frozen_fact_changed"}
    wrong_ref = (replace(contexts[0], fact_ref="source:user_actuality:other"), *contexts[1:])
    assert {
        issue.reason
        for issue in reconcile_clause_license_reviews_v1(
            contexts=wrong_ref,
            policies=policies,
            licenses=licenses,
            reviews=reviews,
            fact_text_by_id={_FACT_ID: _FACT_TEXT},
        ).issues
    } == {"frozen_fact_changed"}


def test_clause_and_license_coverage_and_quote_binding_fail_closed() -> None:
    contexts = _contexts("一对伴侣都很疲惫。")
    policies = _policy()
    licenses = materialize_clause_licenses_v1(contexts=contexts, policies=policies)
    _, reviews = _review(
        contexts=contexts,
        verdict="unsupported",
        reason_code="specific_social_relation",
        quote="一对伴侣",
        policies=policies,
    )
    assert reconcile_clause_license_reviews_v1(
        contexts=contexts,
        policies=policies,
        licenses=licenses,
        reviews=reviews,
        fact_text_by_id={_FACT_ID: _FACT_TEXT},
    ).issues
    forged_quote = replace(reviews.reviews[0], unsupported_quote="不存在")
    assert {
        issue.reason
        for issue in reconcile_clause_license_reviews_v1(
            contexts=contexts,
            policies=policies,
            licenses=licenses,
            reviews=replace(reviews, reviews=(forged_quote,)),
            fact_text_by_id={_FACT_ID: _FACT_TEXT},
        ).issues
    } == {"license_review_quote"}
    duplicated_contexts = _contexts("一对伴侣和一对伴侣都很疲惫。")
    duplicated_licenses = materialize_clause_licenses_v1(
        contexts=duplicated_contexts,
        policies=policies,
    )
    duplicated_review = ClauseLicenseReviewsV1(
        review_version=CLAUSE_LICENSE_REVIEW_VERSION,
        reviews=(
            ClauseLicenseReviewV1(
                clause_id=duplicated_licenses[0].clause_id,
                license_id=duplicated_licenses[0].license_id,
                verdict="unsupported",
                reason_code="specific_social_relation",
                unsupported_quote="一对伴侣",
            ),
        ),
    )
    assert {
        issue.reason
        for issue in reconcile_clause_license_reviews_v1(
            contexts=duplicated_contexts,
            policies=policies,
            licenses=duplicated_licenses,
            reviews=duplicated_review,
            fact_text_by_id={_FACT_ID: _FACT_TEXT},
        ).issues
    } == {"license_review_quote"}


def test_uncertain_is_nonrepairable_insufficient_evidence() -> None:
    contexts = _contexts("她说这样也许更好。")
    policies = _policy()
    licenses = materialize_clause_licenses_v1(contexts=contexts, policies=policies)
    _, reviews = _review(
        contexts=contexts,
        verdict="uncertain",
        reason_code="insufficient_evidence",
        quote="",
        policies=policies,
    )
    assert {
        issue.reason
        for issue in reconcile_clause_license_reviews_v1(
            contexts=contexts,
            policies=policies,
            licenses=licenses,
            reviews=reviews,
            fact_text_by_id={_FACT_ID: _FACT_TEXT},
        ).issues
    } == {"insufficient_evidence"}


def test_license_policy_mutations_change_rulings() -> None:
    contexts = _contexts("一对伴侣都很疲惫。")
    policies = _policy()
    licenses = materialize_clause_licenses_v1(contexts=contexts, policies=policies)
    _, supported = _review(
        contexts=contexts,
        verdict="supported",
        reason_code="supported_by_license",
        quote="",
        policies=policies,
    )
    mutated_policy = (
        replace(
            policies[0],
            prohibited_bindings=tuple(
                binding
                for binding in policies[0].prohibited_bindings
                if binding != "specific_social_relation_to_actuality"
            ),
        ),
    )
    assert {
        issue.reason
        for issue in reconcile_clause_license_reviews_v1(
            contexts=contexts,
            policies=mutated_policy,
            licenses=licenses,
            reviews=supported,
            fact_text_by_id={_FACT_ID: _FACT_TEXT},
        ).issues
    } == {"license_review_coverage"}

    current_contexts = _contexts("我们两个人其实都渴望被看见。")
    current_licenses = materialize_clause_licenses_v1(
        contexts=current_contexts,
        policies=policies,
    )
    _, rejected = _review(
        contexts=current_contexts,
        verdict="unsupported",
        reason_code="current_person_binding",
        quote="我们两个人其实都渴望被看见",
        policies=policies,
    )
    assert reconcile_clause_license_reviews_v1(
        contexts=current_contexts,
        policies=policies,
        licenses=current_licenses,
        reviews=rejected,
        fact_text_by_id={_FACT_ID: _FACT_TEXT},
    ).issues


def test_paired_oracle_rejects_people_count_partner_and_subject_drift() -> None:
    samples = {cast(str, sample["sample_id"]): sample for sample in _samples()}
    generic = cast(
        dict[str, list[str]],
        samples["generic-people-motive"]["closed_evidence"],
    )
    partner = cast(
        dict[str, list[str]],
        samples["specific-partner"]["closed_evidence"],
    )
    current = cast(
        dict[str, list[str]],
        samples["current-user-motive"]["closed_evidence"],
    )

    assert generic["relationship_claim"] == []
    assert partner["relationship_claim"] == ["partner"]
    assert current["subject_binding"] == ["current_user"]

    people_count_as_relationship = {
        **generic,
        "relationship_claim": ["other_social_relation"],
    }
    partner_allowed = {
        **partner,
        "relationship_claim": [],
    }
    current_as_generic = {
        **current,
        "subject_binding": ["generic"],
    }
    assert people_count_as_relationship != generic
    assert partner_allowed != partner
    assert current_as_generic != current


def test_strict_schema_is_closed_and_requires_every_field() -> None:
    contexts = _contexts("换位思考不等于没有边界。")
    licenses = materialize_clause_licenses_v1(
        contexts=contexts,
        policies=_policy(),
    )
    schema = clause_license_review_json_schema(licenses)
    assert schema["additionalProperties"] is False
    properties = cast(dict[str, Any], schema["properties"])
    review = cast(dict[str, Any], properties["reviews"])
    item = cast(dict[str, Any], review["items"])
    assert item["additionalProperties"] is False
    item_properties = cast(dict[str, Any], item["properties"])
    assert set(item["required"]) == set(item_properties)
