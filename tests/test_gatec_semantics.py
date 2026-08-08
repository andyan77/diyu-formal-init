from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from src.brain.content_service import ContentService
from src.brain.payoff_assembly import brand_relevance_evidence
from src.shared.brand_publication import (
    BRAND_CONTEXT_PACKET_V3_VERSION,
    brand_context_packet_document,
    brand_context_packet_v3_digest,
)
from src.shared.errors import DomainError
from src.shared.publication_scope import (
    AUTHORIZATION_CONTRACT_VERSION,
    PUBLICATION_ITEM_SCOPE_V2_CONTRACT,
    AuthorizationContractV1,
    authorization_contract_digest,
    publication_item_is_effective,
    publication_projection_v2_digest,
    resolve_claim_authority,
)
from src.shared.task_value_assembly import (
    BRAND_RELEVANCE_CONTRACT_V2_VERSION,
    BRAND_RELEVANCE_CONTRACT_VERSION,
)
from src.shared.types import (
    BrandContext,
    BrandContextPacketV3,
    BrandContextSegment,
    ContentControlContext,
)


def _authorization(*, source_digest: str = "a" * 64) -> AuthorizationContractV1:
    unsigned = AuthorizationContractV1(
        contract_version=AUTHORIZATION_CONTRACT_VERSION,
        authorization_id="90000000-0000-0000-0000-000000000001",
        authorization_version="v1",
        subject_ref="person:gatec-001",
        tenant_id="90000000-0000-0000-0000-000000000002",
        brand_id="90000000-0000-0000-0000-000000000003",
        logical_account_id="90000000-0000-0000-0000-000000000004",
        organization_id="90000000-0000-0000-0000-000000000005",
        allowed_source_digest=source_digest,
        allowed_usage=("organization_people", "local_trust"),
        single_use=True,
        effective_at="2026-08-08T00:00:00+00:00",
        expires_at="2027-08-08T00:00:00+00:00",
        digest="",
    )
    return replace(unsigned, digest=authorization_contract_digest(unsigned))


def _claim(
    position: int,
    *,
    subject: str = "product",
    claim_key: str = "composition",
    authority: str = "headquarters_formal",
    text: str = "总部确认成分",
    source_digest: str = "a" * 64,
) -> dict[str, object]:
    return {
        "position": position,
        "semantic_subject_type": subject,
        "semantic_subject_id": "DIYU-CSPU-001",
        "claim_key": claim_key,
        "authority_class": authority,
        "published_text": text,
        "source_digest": source_digest,
    }


def _v2_item(*, text: str = "门店在雨天提供伞套") -> dict[str, object]:
    return {
        "position": 1,
        "publication_role": "public_brand_fact",
        "published_text": text,
        "applicability": ["local_response"],
        "source_kind": "brand_expression_baseline",
        "source_ref": "RK-EC-01",
        "source_version": "v2",
        "source_digest": "a" * 64,
        "visibility_scope": "organizations",
        "scope_organization_ids": [
            "90000000-0000-0000-0000-000000000005",
            "90000000-0000-0000-0000-000000000004",
        ],
        "effective_at": "2026-08-08T00:00:00+00:00",
        "expires_at": None,
        "authority_class": "local_formal",
        "semantic_subject_type": "local_context",
        "semantic_subject_id": "DIYU-STORE-001",
        "claim_key": "rain_service",
        "scope_contract_version": PUBLICATION_ITEM_SCOPE_V2_CONTRACT,
    }


def test_projection_v2_digest_is_deterministic_and_scope_sensitive() -> None:
    first = _v2_item()
    scope_ids = first["scope_organization_ids"]
    assert isinstance(scope_ids, list)
    reordered = {**first, "scope_organization_ids": list(reversed(scope_ids))}
    assert publication_projection_v2_digest([first]) == publication_projection_v2_digest([reordered])
    assert publication_projection_v2_digest([first]) != publication_projection_v2_digest(
        [{**first, "visibility_scope": "brand_all", "scope_organization_ids": []}]
    )
    assert publication_projection_v2_digest([first]) != publication_projection_v2_digest(
        [{**first, "expires_at": "2026-09-01T00:00:00+00:00"}]
    )


def test_lifecycle_uses_closed_open_server_time_interval() -> None:
    effective = datetime(2026, 8, 8, tzinfo=timezone.utc)
    expires = effective + timedelta(days=1)
    assert not publication_item_is_effective(
        effective_at=effective,
        expires_at=expires,
        task_context_as_of=effective - timedelta(microseconds=1),
    )
    assert publication_item_is_effective(
        effective_at=effective,
        expires_at=expires,
        task_context_as_of=effective,
    )
    assert not publication_item_is_effective(
        effective_at=effective,
        expires_at=expires,
        task_context_as_of=expires,
    )
    assert publication_item_is_effective(
        effective_at=effective,
        expires_at=None,
        task_context_as_of=expires + timedelta(days=365),
    )


def test_headquarters_product_fact_wins_without_local_pollution() -> None:
    headquarters = _claim(1)
    local_error = _claim(
        2,
        authority="local_ordinary",
        text="门店文件中的错误成分",
        source_digest="b" * 64,
    )
    assert resolve_claim_authority([local_error, headquarters]) == (headquarters,)


def test_local_fact_is_not_overridden_by_headquarters_for_local_claim() -> None:
    headquarters = _claim(
        1,
        subject="local_context",
        authority="headquarters_formal",
        text="总部推测营业时间",
    )
    local = _claim(
        2,
        subject="local_context",
        authority="local_formal",
        text="门店确认营业时间",
        source_digest="b" * 64,
    )
    assert resolve_claim_authority([headquarters, local]) == (local,)


def test_same_level_same_claim_conflict_fails_only_when_consumed() -> None:
    with pytest.raises(DomainError, match="needs_review"):
        resolve_claim_authority(
            [
                _claim(1),
                _claim(2, text="另一条正式成分", source_digest="b" * 64),
            ]
        )
    assert len(resolve_claim_authority([_claim(1), _claim(2, claim_key="care")])) == 2


def test_institutional_local_trust_does_not_require_person_authorization() -> None:
    evidence = brand_relevance_evidence(
        path_family="local_trust",
        source_object_type="local_trust_qualification",
        source_id="qualification:local-institutional",
        source_version="v1",
        source_digest="a" * 64,
        actual_consumed_refs=("RK-EC-01",),
        organization_ref="90000000-0000-0000-0000-000000000005",
        contract_version=BRAND_RELEVANCE_CONTRACT_V2_VERSION,
        involves_person=False,
    )
    assert evidence.authorization is None


@pytest.mark.parametrize("family", ("local_trust", "organization_people"))
def test_people_paths_require_a_matching_full_authorization_contract(family: str) -> None:
    with pytest.raises(DomainError):
        brand_relevance_evidence(
            path_family=family,  # type: ignore[arg-type]
            source_object_type=f"{family}_qualification",
            source_id="qualification:person",
            source_version="v1",
            source_digest="a" * 64,
            actual_consumed_refs=("person:ref",),
            organization_ref="90000000-0000-0000-0000-000000000005",
            authorization_ref="90000000-0000-0000-0000-000000000001",
            contract_version=BRAND_RELEVANCE_CONTRACT_V2_VERSION,
            involves_person=True,
        )
    authorization = _authorization()
    evidence = brand_relevance_evidence(
        path_family=family,  # type: ignore[arg-type]
        source_object_type=f"{family}_qualification",
        source_id="qualification:person",
        source_version="v1",
        source_digest="a" * 64,
        actual_consumed_refs=("person:ref",),
        organization_ref=authorization.organization_id,
        authorization_ref=authorization.authorization_id,
        contract_version=BRAND_RELEVANCE_CONTRACT_V2_VERSION,
        involves_person=True,
        authorization=authorization,
    )
    assert evidence.authorization == authorization


def test_legacy_relevance_contract_cannot_acquire_v2_authorization() -> None:
    with pytest.raises(DomainError, match="历史品牌关联合同"):
        brand_relevance_evidence(
            path_family="organization_people",
            source_object_type="organization_people_qualification",
            source_id="qualification:legacy",
            source_version="v1",
            source_digest="a" * 64,
            actual_consumed_refs=("person:legacy",),
            organization_ref="90000000-0000-0000-0000-000000000005",
            authorization_ref="90000000-0000-0000-0000-000000000001",
            contract_version=BRAND_RELEVANCE_CONTRACT_VERSION,
            authorization=_authorization(),
        )


def test_revision_replays_frozen_v2_scope_version_and_server_time() -> None:
    segment = BrandContextSegment(
        segment_id="item:scope-v2",
        source_document_id="document:gatec",
        source_document_version_id="document-version:v1",
        source_id="RK-EC-08",
        source_version="v1",
        semantic_kind="brand_fact",
        evidence_level="confirmed_publication",
        visibility_scope="organizations",
        digest="b" * 64,
        exact_text="旧任务冻结的区域活动",
        source_digest="a" * 64,
        applicability=("local_response",),
        scope_contract_version=PUBLICATION_ITEM_SCOPE_V2_CONTRACT,
        scope_organization_ids=("90000000-0000-0000-0000-000000000005",),
        effective_at="2026-08-08T00:00:00+00:00",
        expires_at="2026-08-09T00:00:00+00:00",
        authority_class="local_formal",
        semantic_subject_type="local_context",
        semantic_subject_id="DIYU-STORE-001",
        claim_key="local_event",
    )
    segment_document = {
        "segment_id": segment.segment_id,
        "source_document_id": segment.source_document_id,
        "source_document_version_id": segment.source_document_version_id,
        "source_id": segment.source_id,
        "source_version": segment.source_version,
        "semantic_kind": segment.semantic_kind,
        "evidence_level": segment.evidence_level,
        "visibility_scope": segment.visibility_scope,
        "digest": segment.digest,
        "exact_text": segment.exact_text,
        "source_digest": segment.source_digest,
        "applicability": list(segment.applicability),
        "scope_contract_version": segment.scope_contract_version,
        "scope_organization_ids": list(segment.scope_organization_ids),
        "effective_at": segment.effective_at,
        "expires_at": segment.expires_at,
        "authority_class": segment.authority_class,
        "semantic_subject_type": segment.semantic_subject_type,
        "semantic_subject_id": segment.semantic_subject_id,
        "claim_key": segment.claim_key,
    }
    packet_digest = brand_context_packet_v3_digest(
        projection_id="projection:v2",
        projection_version=2,
        projection_digest="c" * 64,
        available_segment_refs=(segment.segment_id,),
        frozen_segment_refs=(segment.segment_id,),
        consumed_segment_refs=(segment.segment_id,),
        displayed_segment_refs=(),
        segments=(segment_document,),
    )
    packet = BrandContextPacketV3(
        packet_version=BRAND_CONTEXT_PACKET_V3_VERSION,
        packet_digest=packet_digest,
        publication_projection_id="projection:v2",
        publication_projection_version=2,
        publication_projection_digest="c" * 64,
        available_segment_refs=(segment.segment_id,),
        frozen_segment_refs=(segment.segment_id,),
        consumed_segment_refs=(segment.segment_id,),
        displayed_segment_refs=(),
        segments=(segment,),
    )
    snapshot: dict[str, object] = {
        "task_context_as_of": "2026-08-08T12:00:00+00:00",
        "brand_reference_context": [segment.exact_text],
        "brand_context_packet": brand_context_packet_document(packet, include_text=True),
    }
    current = BrandContext(
        brand_name="笛语",
        positioning="当前定位",
        decision_order="当前顺序",
        tone="当前语气",
        account_name="账号",
        operator_name="操作人",
        organization_name="门店",
        content_role_name="角色",
        content_role_boundary="边界",
        audience_description="受众",
        strategy_version="v3",
        platform="小红书",
        media_format="图文",
        production_conditions="手机",
        task_context_as_of="2026-08-10T12:00:00+00:00",
    )
    control = ContentControlContext(
        catalog_version=None,
        direction=None,
        account_expression=None,
        materials=(),
        preference_mode="none",
        preference_version=None,
        content_role="",
        content_role_boundary="",
    )
    replayed = ContentService._replayed_context(current, control, snapshot)
    assert replayed.task_context_as_of == "2026-08-08T12:00:00+00:00"
    assert replayed.context_packet == packet
    assert replayed.brand_reference_context == (segment.exact_text,)
