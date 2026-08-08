from __future__ import annotations

from dataclasses import replace
from uuid import UUID

import pytest

from src.brain.content_expression import snapshot_document
from src.brain.content_service import ContentService
from src.brain.payoff_assembly import (
    RULESET_V1,
    assemble_task_value,
    brand_relevance_evidence,
    build_payoff_request,
)
from src.brain.platform_directions import direction_for
from src.shared.account_editorial_lens import (
    ACCOUNT_EDITORIAL_DEGRADED_REASONS,
    ACCOUNT_EDITORIAL_LENS_V4_VERSION,
    AccountEditorialDegradedReason,
    AccountEditorialResolutionV4,
    account_editorial_lens_digest,
    account_editorial_resolution_digest,
    account_editorial_resolution_document,
    resolve_account_editorial_context,
)
from src.shared.content_snapshot import visible_context_basis
from src.shared.creative_plan import ACCOUNT_BASELINE_TONE_ID, build_creative_plan
from src.shared.delivery_compiler import DELIVERY_COMPILER_V5_VERSION
from src.shared.errors import DomainError, GenerationFailed
from src.shared.media_program import (
    MediaCapabilityEnvelope,
    build_media_capability_envelope,
    select_media_program,
)
from src.shared.narrative import NarrativeFrame, new_frame
from src.shared.product_value import (
    P1ProductDecisionBasisV3,
    build_product_decision_basis_v2,
    product_value_contract_digest,
)
from src.shared.publication_contract import (
    PublicationContractV3,
    publication_contract_digest,
)
from src.shared.task_value_assembly import (
    BRAND_RELEVANCE_PATHS,
    BRAND_RELEVANCE_SOURCE_TYPES,
    BrandRelevancePath,
    TaskValueAssemblyV1,
)
from src.shared.types import (
    AccountExpression,
    BrandContext,
    BrandContextPacketV3,
    ContentControlContext,
    ContentProduct,
    GenerationInput,
    ProductFact,
)
from src.shared.writer_request import (
    build_writer_request_v3,
    writer_request_digest,
)
from src.tool.llm_gateway.stub import DeterministicContentGenerator

_PRODUCTS: tuple[ContentProduct, ...] = (
    "dressing_decision",
    "product_truth",
    "brand_life_narrative",
    "local_response",
    "visual_styling_story",
)


def _packet() -> BrandContextPacketV3:
    return BrandContextPacketV3(
        packet_version="brand-context-packet-v3",
        packet_digest="b" * 64,
        publication_projection_id="projection-gateb",
        publication_projection_version=3,
        publication_projection_digest="a" * 64,
        available_segment_refs=(),
        frozen_segment_refs=(),
        consumed_segment_refs=(),
        displayed_segment_refs=(),
        segments=(),
    )


def _profile(account: str = "H01") -> AccountExpression:
    values = {
        "H01": (
            "品牌官方定义者",
            "只表达品牌已确认判断，不代替个人或门店发言",
            "把受众当作能够独立判断的平等参与者",
            "先观察关系与品牌长期立场",
            "以完整图文为默认条件",
            "00000000-0000-0000-0000-000000000101",
        ),
        "H03": (
            "商品企划与取舍解释者",
            "只依据已确认商品事实说明取舍，不承诺效果",
            "帮助正在比较具体条件的受众做有限判断",
            "先核对商品依据与适用条件",
            "以事实卡与静物画面为默认条件",
            "00000000-0000-0000-0000-000000000103",
        ),
        "S02": (
            "门店搭配顾问",
            "只给条件化搭配建议，不虚构顾客与门店经历",
            "回应需要把建议带回自身场景检验的到店受众",
            "先看当日使用场景与搭配取舍",
            "以可复核搭配条件为默认条件",
            "00000000-0000-0000-0000-000000000202",
        ),
    }[account]
    return AccountExpression(
        profile_id=UUID(values[5]),
        version=2,
        identity_position=values[0],
        authority_boundary=values[1],
        audience_relationship=values[2],
        content_territories=values[3],
        default_production_conditions=values[4],
        is_draft=False,
    )


def _context(profile: AccountExpression, packet: BrandContextPacketV3 | None = None) -> BrandContext:
    return BrandContext(
        brand_name="笛语服饰",
        positioning="尊重独立判断",
        decision_order="先核对条件，再形成有限判断",
        tone="真实、克制、有依据",
        account_name="测试逻辑账号",
        operator_name="当前运营者",
        organization_name="笛语总部",
        content_role_name=profile.identity_position,
        content_role_boundary=profile.authority_boundary,
        audience_description=profile.audience_relationship,
        strategy_version="brand-expression-v2",
        platform="小红书",
        media_format="图文",
        production_conditions=profile.default_production_conditions,
        expression_constraint_context=("不把候选信息写成事实",),
        creative_method_context=("先呈现可见取舍，再给成立条件",),
        context_packet=packet or _packet(),
    )


def _control(profile: AccountExpression) -> ContentControlContext:
    return ContentControlContext(
        catalog_version=None,
        direction=None,
        account_expression=profile,
        materials=(),
        preference_mode="account_default",
        preference_version=None,
        content_role=profile.identity_position,
        content_role_boundary=profile.authority_boundary,
    )


def _product() -> ProductFact:
    return ProductFact(
        sku="DIYU-CSPU-001",
        display_name="双面外套",
        facts={
            "colors": ["深灰", "米白"],
            "both_sides_complete": True,
            # Candidate price/effect/performance fields are deliberately absent.
        },
        source_kind="confirmed_product_version",
        source_note="Gate A V-level facts",
        fact_version=2,
        applicability="只在需要两种完整可见外观之间切换时成立",
        product_id=UUID("00000000-0000-0000-0000-000000001001"),
        product_version_id=UUID("00000000-0000-0000-0000-000000001002"),
    )


def _formal_contract(
    product: ContentProduct,
    profile: AccountExpression,
    *,
    product_basis: P1ProductDecisionBasisV3 | None = None,
) -> tuple[
    PublicationContractV3,
    TaskValueAssemblyV1,
    NarrativeFrame,
    MediaCapabilityEnvelope,
]:
    topic = "同一天先开会，再接孩子，怎样保留调整余地"
    plan = build_creative_plan(
        topic_spans=(topic,),
        primary_value=product,
        tone_ids=(ACCOUNT_BASELINE_TONE_ID,),
        mechanism_id=None,
        target_shape="xiaohongshu_graphic:graphic",
    )
    product_refs = product_basis.supporting_fact_refs if product_basis is not None else ()
    frame = new_frame("general_observation", (), product_refs)
    direction = direction_for("xiaohongshu_graphic")
    envelope = build_media_capability_envelope(
        platform_shape=plan.platform_shape,
        media_format="graphic",
    )
    contract, assembly = ContentService._new_publication_contract(
        primary_product=product,
        plan=plan,
        frame=frame,
        control=_control(profile),
        context=_context(profile),
        product_value_contract=product_basis,
        intake_spans=ContentService._default_publication_spans(
            topic,
            frame,
            non_fact_role="creation_instruction",
        ),
        target="xiaohongshu_graphic",
        direction=direction,
        series_context=None,
        media_envelope=envelope,
    )
    return contract, assembly, frame, envelope


def test_lens_has_exact_five_product_keys_and_v4_is_used_for_new_tasks() -> None:
    for product in _PRODUCTS:
        resolution = resolve_account_editorial_context(
            primary_product=product,
            account_expression=_profile(),
            brand_context_packet=_packet(),
        )
        assert resolution.applied is True
        assert resolution.degraded_reasons == ()
        assert resolution.lens is not None
        assert resolution.lens.contract_version == ACCOUNT_EDITORIAL_LENS_V4_VERSION
        assert resolution.lens.primary_product == product


@pytest.mark.parametrize(
    ("product", "profile", "packet", "expected"),
    (
        (
            "unsupported-product",
            _profile(),
            _packet(),
            AccountEditorialDegradedReason.UNSUPPORTED_CONTENT_PRODUCT,
        ),
        (
            "brand_life_narrative",
            None,
            _packet(),
            AccountEditorialDegradedReason.ACCOUNT_PROFILE_MISSING,
        ),
        (
            "brand_life_narrative",
            replace(_profile(), identity_position=""),
            _packet(),
            AccountEditorialDegradedReason.ACCOUNT_PROFILE_IDENTITY_INCOMPLETE,
        ),
        (
            "brand_life_narrative",
            replace(_profile(), is_draft=True),
            _packet(),
            AccountEditorialDegradedReason.ACCOUNT_PROFILE_NOT_CONFIRMED,
        ),
        (
            "brand_life_narrative",
            _profile(),
            None,
            AccountEditorialDegradedReason.BRAND_CONTEXT_INCOMPATIBLE,
        ),
    ),
)
def test_each_account_gate_degrades_with_named_snapshot_reason(
    product: str,
    profile: AccountExpression | None,
    packet: BrandContextPacketV3 | None,
    expected: AccountEditorialDegradedReason,
) -> None:
    resolution = resolve_account_editorial_context(
        primary_product=product,
        account_expression=profile,
        brand_context_packet=packet,
    )
    assert resolution.applied is False
    assert resolution.lens is None
    assert expected in resolution.degraded_reasons
    projection = visible_context_basis(
        {"account_editorial_resolution": account_editorial_resolution_document(resolution)},
        account_name="逻辑账号",
        channel="小红书",
        media_format="graphic",
    )
    assert projection["account_editorial_state"] == "degraded"
    reasons = projection["account_editorial_degraded_reasons"]
    assert isinstance(reasons, list)
    assert expected.value in reasons
    assert "identity_position" not in projection


def test_reason_enum_is_exact_and_applied_case_has_no_failure_reason() -> None:
    assert tuple(reason.value for reason in ACCOUNT_EDITORIAL_DEGRADED_REASONS) == (
        "unsupported_content_product",
        "account_profile_missing",
        "account_profile_identity_incomplete",
        "account_profile_not_confirmed",
        "brand_context_incompatible",
    )
    applied = resolve_account_editorial_context(
        primary_product="brand_life_narrative",
        account_expression=_profile(),
        brand_context_packet=_packet(),
    )
    assert applied.applied is True
    assert applied.degraded_reasons == ()


def test_same_seed_cross_account_changes_semantics_not_facts_or_product_job() -> None:
    contracts: dict[tuple[ContentProduct, str], PublicationContractV3] = {}
    for product in _PRODUCTS:
        for account in ("H01", "H03", "S02"):
            contract, _, _, _ = _formal_contract(product, _profile(account))
            contracts[(product, account)] = contract
            writer = build_writer_request_v3(
                contract,
                product_decision_basis=None,
                platform_expression_responsibility=direction_for("xiaohongshu_graphic").direction,
                prior_output=None,
                revision_instruction=None,
            )
            assert writer.account_editorial_context is not None
            assert writer.account_editorial_context["applied"] is True
            assert writer.account_editorial_context["source_digest"] == (
                contract.account_editorial_resolution.source_digest
                if contract.account_editorial_resolution is not None
                else None
            )
            assert contract.account_editorial_permission.identity not in contract.topic

        base = contracts[(product, "H01")]
        for account in ("H03", "S02"):
            candidate = contracts[(product, account)]
            assert candidate.topic == base.topic
            assert candidate.frozen_fact_refs == base.frozen_fact_refs
            assert candidate.central_job == base.central_job
            assert candidate.platform_direction == base.platform_direction
            changed = sum(
                left != right
                for left, right in (
                    (
                        base.account_editorial_permission.attention_order,
                        candidate.account_editorial_permission.attention_order,
                    ),
                    (
                        base.account_editorial_permission.response_posture,
                        candidate.account_editorial_permission.response_posture,
                    ),
                    (
                        base.account_editorial_permission.audience,
                        candidate.account_editorial_permission.audience,
                    ),
                    (
                        base.account_editorial_permission.allowed_stance,
                        candidate.account_editorial_permission.allowed_stance,
                    ),
                )
            )
            assert changed >= 2
            assert candidate.account_editorial_permission.source_profile_id != (
                base.account_editorial_permission.source_profile_id
            )
            assert candidate.account_editorial_resolution is not None
            assert base.account_editorial_resolution is not None
            assert candidate.account_editorial_resolution.source_digest != (
                base.account_editorial_resolution.source_digest
            )


def test_p1_selected_product_freezes_v_facts_judgment_and_writer_basis() -> None:
    selected = _product()
    basis = build_product_decision_basis_v2(
        primary_product="dressing_decision",
        products=(selected,),
    )
    assert isinstance(basis, P1ProductDecisionBasisV3)
    assert basis.supporting_fact_refs
    assert basis.judgment_ref == f"product-version:{selected.product_version_id}:judgment"
    assert basis.applicability_conditions == (selected.applicability,)
    contract, _, _, _ = _formal_contract("dressing_decision", _profile("H03"), product_basis=basis)
    assert contract.product_decision_basis is not None
    assert contract.product_decision_basis.digest == product_value_contract_digest(basis)
    assert contract.product_decision_basis.judgment_ref == basis.judgment_ref
    writer = build_writer_request_v3(
        contract,
        product_decision_basis=basis,
        platform_expression_responsibility=direction_for("xiaohongshu_graphic").direction,
        prior_output=None,
        revision_instruction=None,
    )
    assert writer.product_decision_basis is not None
    assert writer.product_decision_basis["source_packet_digest"] == basis.source_packet_digest
    assert writer.product_decision_basis["supporting_fact_refs"] == list(basis.supporting_fact_refs)
    assert writer.product_decision_basis["judgment_ref"] == basis.judgment_ref
    assert "price" not in writer.product_decision_basis
    assert "effect" not in writer.product_decision_basis


def test_p1_without_product_is_valid_and_product_path_is_only_unavailable() -> None:
    assert (
        build_product_decision_basis_v2(
            primary_product="dressing_decision",
            products=(),
        )
        is None
    )
    contract, assembly, _, _ = _formal_contract("dressing_decision", _profile("S02"))
    assert contract.product_decision_basis is None
    assert assembly.brand_relevance_state == "applied"
    assert assembly.brand_relevance_path in {"audience_relationship", "brand_stance"}
    assert assembly.brand_relevance_path != "product_expertise"
    assert assembly.payoff_degraded is False


def test_p1_explicit_product_with_missing_or_ambiguous_basis_fails_closed() -> None:
    insufficient = replace(_product(), facts={"colors": ["深灰"]})
    with pytest.raises(GenerationFailed, match="不足"):
        build_product_decision_basis_v2(
            primary_product="dressing_decision",
            products=(insufficient,),
        )
    with pytest.raises(GenerationFailed, match="明确选择一件"):
        build_product_decision_basis_v2(
            primary_product="dressing_decision",
            products=(_product(), replace(_product(), sku="DIYU-CSPU-006")),
        )


@pytest.mark.parametrize("family", BRAND_RELEVANCE_PATHS)
def test_each_brand_relevance_family_has_typed_consumed_evidence(
    family: BrandRelevancePath,
) -> None:
    source_type = next(iter(BRAND_RELEVANCE_SOURCE_TYPES[family]))
    evidence = brand_relevance_evidence(
        path_family=family,
        source_object_type=source_type,
        source_id=f"{source_type}:gateb",
        source_version="v1",
        source_digest="c" * 64,
        actual_consumed_refs=(f"{source_type}:gateb:ref",),
        organization_ref=(
            "organization:DIYU-STORE-001:v1" if family in {"local_trust", "organization_people"} else None
        ),
        authorization_ref=("authorization:person-001:v1" if family == "organization_people" else None),
        media_ref=("media:DIYU-V-001:v1" if family == "brand_visual" else None),
    )
    assembly = assemble_task_value(
        build_payoff_request(
            content_product=(
                "dressing_decision"
                if family == "product_expertise"
                else (
                    "visual_styling_story"
                    if family == "brand_visual"
                    else ("local_response" if family == "local_trust" else "brand_life_narrative")
                )
            ),
            topic_origin="explicit_user",
            account_expression=None,
            product_basis=None,
            series_delta=None,
            static_payoff="让受众从一件具体生活题材中获得可执行的观察角度。",
            relevance_evidence=(evidence,),
        ),
        ruleset=RULESET_V1,
    )
    assert assembly.brand_relevance_state == "applied"
    assert assembly.brand_relevance_path == family
    assert assembly.brand_relevance_evidence == evidence
    assert assembly.brand_relevance_evidence.actual_consumed_refs == (f"{source_type}:gateb:ref",)
    assert assembly.demonstration_eligible is True


@pytest.mark.parametrize(
    ("family", "source_type", "organization_ref", "authorization_ref", "media_ref"),
    (
        ("brand_visual", "product_decision_basis", None, None, "media:1"),
        ("brand_visual", "brand_visual_qualification", None, None, None),
        ("local_trust", "account_profile", "organization:1", None, None),
        ("local_trust", "local_trust_qualification", None, None, None),
        ("organization_people", "account_profile", "organization:1", "authorization:1", None),
        ("organization_people", "organization_people_qualification", "organization:1", None, None),
    ),
)
def test_reserved_families_cannot_be_inferred_or_lose_qualification_refs(
    family: BrandRelevancePath,
    source_type: str,
    organization_ref: str | None,
    authorization_ref: str | None,
    media_ref: str | None,
) -> None:
    with pytest.raises(DomainError):
        brand_relevance_evidence(
            path_family=family,
            source_object_type=source_type,
            source_id="unqualified:1",
            source_version="v1",
            source_digest="d" * 64,
            actual_consumed_refs=("unqualified:1",),
            organization_ref=organization_ref,
            authorization_ref=authorization_ref,
            media_ref=media_ref,
        )


def test_no_natural_path_is_visible_and_does_not_change_life_topic_to_product() -> None:
    static_payoff = "让受众从一件具体生活题材中获得可执行的观察角度。"
    assembly = assemble_task_value(
        build_payoff_request(
            content_product="brand_life_narrative",
            topic_origin="explicit_user",
            account_expression=None,
            product_basis=None,
            series_delta=None,
            static_payoff=static_payoff,
            relevance_evidence=(),
        ),
        ruleset=RULESET_V1,
    )
    assert assembly.audience_payoff == static_payoff
    assert assembly.brand_relevance_state == "degraded"
    assert assembly.brand_relevance_path is None
    assert assembly.brand_relevance_evidence is None
    assert assembly.brand_relevance_degraded_reason == "no_natural_brand_relevance_path"
    assert assembly.demonstration_eligible is False
    assert "商品" not in assembly.audience_payoff


def test_formal_zero_model_vertical_uses_one_frozen_resolution_and_p1_basis() -> None:
    profile = _profile("H03")
    selected = _product()
    basis = build_product_decision_basis_v2(
        primary_product="dressing_decision",
        products=(selected,),
    )
    assert isinstance(basis, P1ProductDecisionBasisV3)
    contract, assembly, frame, envelope = _formal_contract(
        "dressing_decision",
        profile,
        product_basis=basis,
    )
    plan = build_creative_plan(
        topic_spans=(contract.topic,),
        primary_value="dressing_decision",
        tone_ids=(ACCOUNT_BASELINE_TONE_ID,),
        mechanism_id=None,
        target_shape="xiaohongshu_graphic:graphic",
    )
    program = select_media_program(
        primary_product="dressing_decision",
        envelope=envelope,
        mechanism_id=plan.mechanism_id,
        series_position=None,
        fact_count=len(basis.supporting_fact_refs),
        topic_origin=plan.topic_origin,
        publication_contract=True,
    )
    initial_snapshot = snapshot_document(
        _control(profile),
        profile.identity_position,
        products=(selected,),
        narrative_frame=frame,
        user_premise=contract.topic,
        creative_plan=plan,
        delivery_compiler_version=DELIVERY_COMPILER_V5_VERSION,
        media_capability_envelope=envelope,
        media_program=program,
        product_value_contract=basis,
        brand_context_packet=_packet(),
        publication_contract=contract,
    )
    request = GenerationInput(
        run_id=UUID("00000000-0000-0000-0000-000000009001"),
        task_id=UUID("00000000-0000-0000-0000-000000009002"),
        weak_seed=contract.topic,
        primary_product="dressing_decision",
        revision_instruction=None,
        brand=_context(profile),
        target="xiaohongshu_graphic",
        media_format="graphic",
        platform_direction=direction_for("xiaohongshu_graphic"),
        products=(selected,),
        account_expression=profile,
        narrative_frame=frame,
        creative_plan=plan,
        delivery_compiler_version=DELIVERY_COMPILER_V5_VERSION,
        media_capability_envelope=envelope,
        media_program=program,
        product_value_contract=basis,
        publication_contract=contract,
    )
    artifact = DeterministicContentGenerator().generate(request)
    visible_artifact = f"{artifact.outline}\n{artifact.body}"
    for source_span in (
        profile.identity_position,
        profile.authority_boundary,
        profile.audience_relationship,
        profile.content_territories,
    ):
        assert source_span not in visible_artifact
    assert artifact.completion_snapshot_patch is not None
    completed_snapshot = {**initial_snapshot, **artifact.completion_snapshot_patch}
    raw_writer = completed_snapshot["writer_request_v3"]
    assert isinstance(raw_writer, dict)
    raw_editorial = raw_writer["account_editorial_context"]
    assert isinstance(raw_editorial, dict)
    resolution = contract.account_editorial_resolution
    assert resolution is not None
    assert raw_editorial["contract_version"] == resolution.contract_version
    assert resolution.lens is not None
    assert raw_editorial["lens_digest"] == account_editorial_lens_digest(resolution.lens)
    assert raw_editorial["source_digest"] == resolution.source_digest
    assert raw_editorial["resolution_digest"] == account_editorial_resolution_digest(resolution)
    assert initial_snapshot["account_editorial_resolution_digest"] == (account_editorial_resolution_digest(resolution))
    assert completed_snapshot["publication_contract_digest"] == publication_contract_digest(contract)
    assert raw_writer["product_decision_basis"]["judgment_ref"] == basis.judgment_ref
    assert raw_writer["brand_relevance"]["family"] == "product_expertise"
    assert assembly.brand_relevance_path == "product_expertise"
    visible = visible_context_basis(
        completed_snapshot,
        account_name="商品企划账号",
        channel="小红书",
        media_format="graphic",
    )
    assert visible["account_editorial_state"] == "applied"
    assert visible["account_editorial_degraded_reasons"] == []
    assert visible["brand_relevance_state"] == "applied"
    assert visible["brand_relevance_family"] == "product_expertise"

    changed_profile = replace(profile, identity_position="后来修改但不得污染旧任务", version=3)
    changed_resolution = resolve_account_editorial_context(
        primary_product="dressing_decision",
        account_expression=changed_profile,
        brand_context_packet=_packet(),
    )
    assert changed_resolution.source_digest != resolution.source_digest
    video_direction = direction_for("douyin_video")
    video_envelope = build_media_capability_envelope(
        platform_shape="douyin_video:video",
        media_format="video",
    )
    recarried = ContentService._recarried_publication_contract(
        contract,
        video_envelope,
        "douyin_video",
        video_direction,
        "改成抖音视频，但不改变原判断。",
    )
    assert recarried.account_editorial_resolution == resolution
    recarried_resolution = recarried.account_editorial_resolution
    assert isinstance(recarried_resolution, AccountEditorialResolutionV4)
    assert account_editorial_resolution_digest(recarried_resolution) == account_editorial_resolution_digest(resolution)
    replay_writer = build_writer_request_v3(
        recarried,
        product_decision_basis=basis,
        platform_expression_responsibility=video_direction.direction,
        prior_output=None,
        revision_instruction="改成抖音视频，但不改变原判断。",
    )
    assert replay_writer.account_editorial_context is not None
    assert replay_writer.account_editorial_context["source_digest"] == resolution.source_digest
    assert writer_request_digest(replay_writer) != str(completed_snapshot["writer_request_v3_digest"])
