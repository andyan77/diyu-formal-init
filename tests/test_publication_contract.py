from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from typing import cast

import pytest

from src.brain.input_role_resolver import resolve_input_roles
from src.infrastructure.postgres_repository import PostgresContentRepository
from src.shared.content_snapshot import frozen_publication_contract
from src.shared.delivery_compiler import (
    DELIVERY_COMPILER_VERSION,
    DUAL_TRACK_DELIVERY_COMPILER_VERSION,
    MEDIA_NATIVE_DELIVERY_COMPILER_VERSION,
)
from src.shared.errors import DomainError
from src.shared.narrative import UserFactCandidate, user_fact_candidates
from src.shared.publication_contract import (
    AccountEditorialPermissionV3,
    BrandContextUseV3,
    IntakeSpanRole,
    PlatformDirectionV3,
    PublicationContractV2,
    PublicationContractV3,
    PublicationInputSpanV1,
    build_publication_contract,
    build_publication_contract_v3,
    publication_contract_digest,
    publication_contract_document,
    publication_contract_from_document,
)
from src.shared.writer_request import (
    build_writer_request_v3,
    writer_request_document,
)


def _publication_span(
    candidate: UserFactCandidate,
    role: IntakeSpanRole,
) -> PublicationInputSpanV1:
    return PublicationInputSpanV1(
        source_id=candidate.source_id,
        role=role,
        exact_text=candidate.exact_text,
        turn_index=candidate.turn_index,
        start_offset=candidate.start_offset,
        end_offset=candidate.end_offset,
        start_byte=candidate.start_byte,
        end_byte=candidate.end_byte,
    )


def _exact_span_fixture() -> tuple[
    tuple[str, ...],
    tuple[PublicationInputSpanV1, ...],
]:
    turns = (
        "  今天穿了红裙🙂，  请写成小红书。  ",
        "\t今天穿了红裙🙂，  改成更短一些。 \n",
    )
    candidates = user_fact_candidates(turns)
    roles: tuple[IntakeSpanRole, ...] = (
        "observable_actuality",
        "creation_instruction",
        "observable_actuality",
        "style_or_revision_instruction",
    )
    assert len(candidates) == len(roles)
    spans = tuple(_publication_span(candidate, role) for candidate, role in zip(candidates, roles, strict=True))
    return turns, spans


def _contract(
    spans: tuple[PublicationInputSpanV1, ...] | None = None,
) -> PublicationContractV2:
    if spans is None:
        _, spans = _exact_span_fixture()
    observable_spans = tuple(span for span in spans if span.role == "observable_actuality")
    return build_publication_contract(
        primary_product="dressing_decision",
        topic_spans=(observable_spans[0].exact_text,),
        topic_origin="explicit_user",
        known_conditions=tuple(span.exact_text for span in observable_spans),
        frozen_fact_refs=tuple(span.source_id for span in observable_spans),
        intake_spans=spans,
        account_identity="帮助普通人按眼前条件做选择",
        account_audience="需要清楚穿衣判断的人",
        account_attention="先看具体条件，再说明真实取舍",
        account_response_boundary="不补造现实经历或商品效果",
        source_profile_id="profile-publication-tests",
        source_profile_version=2,
        publication_projection_id="projection-publication-tests",
        publication_projection_version=3,
        publication_projection_digest="1" * 64,
        product_value_contract_digest="2" * 64,
    )


def _contract_v3() -> PublicationContractV3:
    turns = ("回家才发现忘记喝水，帮我发一条。",)
    candidates = user_fact_candidates(turns)
    assert len(candidates) == 2
    resolution = resolve_input_roles(
        user_turns=turns,
        candidates=candidates,
        roles={
            candidates[0].source_id: "observable_actuality",
            candidates[1].source_id: "creation_instruction",
        },
        selected_actuality_source_ids=(candidates[0].source_id,),
    )
    return build_publication_contract_v3(
        input_roles=resolution.spans,
        topic_origin="explicit_user",
        topic="围绕忙碌中遗漏日常步骤的张力形成一条生活观察",
        content_product="brand_life_narrative",
        central_job="围绕用户提供的具体张力形成一条独立判断",
        audience_payoff="让受众从这个生活片段里看到一个值得停留的观察",
        explicit_user_controls=(candidates[1].exact_text,),
        account_editorial_permission=AccountEditorialPermissionV3(
            identity="品牌生活观察账号",
            audience="愿意认真看日常的人",
            attention_order="先看具体处境，再形成判断",
            response_posture="平等、具体、不替用户补原因",
            refusals="不新增用户身体、心理、原因或后续结果",
            allowed_stance="可以形成一般观察与低风险比喻",
            source_profile_id="profile-v3-tests",
            source_profile_version=3,
        ),
        frozen_fact_refs=(candidates[0].source_id,),
        product_decision_basis=None,
        series_delta=None,
        platform_direction=PlatformDirectionV3(
            target="xiaohongshu_graphic",
            media_format="graphic",
            direction_version="platform-direction-v3-test",
            direction_digest="3" * 64,
        ),
        media_capability_ref="4" * 64,
        brand_context_use=BrandContextUseV3(
            available_refs=("brand-1", "method-1"),
            frozen_refs=("brand-1", "method-1"),
            consumed_refs=("method-1",),
            displayed_refs=(),
        ),
        publication_projection_id="projection-v3-tests",
        publication_projection_version=4,
        publication_projection_digest="5" * 64,
    )


def _json_round_trip_document(
    value: dict[str, object],
) -> dict[str, object]:
    decoded = json.loads(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
    if not isinstance(decoded, dict):
        raise AssertionError("JSON document must remain an object")
    return cast(dict[str, object], decoded)


def _span_documents(
    document: dict[str, object],
) -> list[dict[str, object]]:
    raw_spans = document.get("intake_spans")
    if not isinstance(raw_spans, list) or any(not isinstance(item, dict) for item in raw_spans):
        raise AssertionError("publication intake spans must be JSON objects")
    return cast(list[dict[str, object]], raw_spans)


def _current_completion_patch(
    contract: PublicationContractV2,
) -> dict[str, object]:
    return {
        "creative_kernel_v2": {
            "kernel_version": "creative-kernel-v4",
            "units": [],
        },
        "expression_plan_version": "expression-plan-v1",
        "expression_plan_digest": "3" * 64,
        "delivery_compiler_version": DELIVERY_COMPILER_VERSION,
        "writer_model": "deterministic-test-writer",
        "version_authorization": "deterministic-dual-track-v1",
        "claim_inventory_v1": [],
        "reviewed_kernel_digest": "4" * 64,
        "reviewed_creative_digest": "5" * 64,
        "product_fact_packet": {
            "packet_version": "product-fact-packet-v1",
            "facts": [],
        },
        "immutable_product_fact_blocks": [],
        "used_product_fact_ids": [],
        "used_product_fact_block_ids": [],
        "product_fact_renderer_version": None,
        "visible_provenance": {"body": ["unit:body"]},
        "delivery_resource_refs": ["resource:original_composition"],
        "media_capability_envelope": None,
        "media_capability_envelope_digest": None,
        "media_program": None,
        "media_program_digest": None,
        "product_value_contract": None,
        "product_value_contract_digest": None,
        "publication_contract": publication_contract_document(contract),
        "publication_contract_digest": publication_contract_digest(contract),
    }


def _legacy_completion_patch(
    contract: PublicationContractV2,
    compiler_version: str,
) -> dict[str, object]:
    patch = _current_completion_patch(contract)
    patch.pop("publication_contract")
    patch.pop("publication_contract_digest")
    if compiler_version != DELIVERY_COMPILER_VERSION:
        patch.pop("product_value_contract")
        patch.pop("product_value_contract_digest")
    if compiler_version == DUAL_TRACK_DELIVERY_COMPILER_VERSION:
        patch.pop("media_capability_envelope")
        patch.pop("media_capability_envelope_digest")
        patch.pop("media_program")
        patch.pop("media_program_digest")
    patch["delivery_compiler_version"] = compiler_version
    return patch


def test_exact_spans_preserve_trimmed_char_and_utf8_byte_addresses() -> None:
    turns, spans = _exact_span_fixture()

    for span in spans:
        turn = turns[span.turn_index - 1]
        assert turn[span.start_offset : span.end_offset] == span.exact_text
        assert turn.encode("utf-8")[span.start_byte : span.end_byte].decode("utf-8") == span.exact_text
        assert turn[span.start_offset - 1].isspace()
        assert turn[span.end_offset].isspace()

    assert spans[0].exact_text == spans[2].exact_text == "今天穿了红裙🙂，"
    assert spans[0].source_id != spans[2].source_id
    assert spans[0].turn_index == 1
    assert spans[2].turn_index == 2
    assert spans[0].end_byte - spans[0].start_byte > (spans[0].end_offset - spans[0].start_offset)


@pytest.mark.parametrize(
    ("turn", "role"),
    (
        ("  请帮我发一条。  ", "creation_instruction"),
        ("\t写成小红书图文。 ", "creation_instruction"),
        ("  语气再克制些。\n", "style_or_revision_instruction"),
    ),
)
def test_three_distinct_creation_instructions_keep_exact_char_and_byte_spans(
    turn: str,
    role: IntakeSpanRole,
) -> None:
    candidates = user_fact_candidates((turn,))
    assert len(candidates) == 1
    span = _publication_span(candidates[0], role)

    assert turn[span.start_offset : span.end_offset] == span.exact_text
    assert turn.encode("utf-8")[span.start_byte : span.end_byte].decode("utf-8") == span.exact_text
    assert span.role != "observable_actuality"


@pytest.mark.parametrize(
    "instruction",
    (
        "帮我发一条。",
        "写成小红书图文。",
        "语气荒诞一点。",
    ),
)
def test_creation_instruction_cannot_be_frozen_as_part_of_the_actuality_turn(
    instruction: str,
) -> None:
    candidates = user_fact_candidates((f"回家才发现忘记喝水，{instruction}",))
    assert len(candidates) == 2
    spans = (
        _publication_span(candidates[0], "observable_actuality"),
        _publication_span(candidates[1], "creation_instruction"),
    )

    with pytest.raises(DomainError, match="现实事实跨度没有绑定冻结事实"):
        build_publication_contract(
            primary_product="brand_life_narrative",
            topic_spans=(spans[0].exact_text,),
            topic_origin="explicit_user",
            known_conditions=(spans[0].exact_text,),
            frozen_fact_refs=tuple(span.source_id for span in spans),
            intake_spans=spans,
            account_identity="生活观察账号",
            account_audience="正在重新看日常的人",
            account_attention="先看具体变化",
            account_response_boundary="不补造原因",
            source_profile_id="profile-publication-tests",
            source_profile_version=2,
            publication_projection_id=None,
            publication_projection_version=None,
            publication_projection_digest=None,
            product_value_contract_digest=None,
        )


def test_publication_contract_has_stable_direct_and_json_round_trips() -> None:
    contract = _contract()
    document = publication_contract_document(contract)
    json_document = _json_round_trip_document(document)

    assert isinstance(document["known_conditions"], list)
    assert isinstance(document["frozen_fact_refs"], list)
    assert isinstance(document["intake_spans"], list)
    assert json_document == document
    assert publication_contract_from_document(document) == contract
    assert publication_contract_from_document(json_document) == contract
    assert publication_contract_digest(
        publication_contract_from_document(json_document)
    ) == publication_contract_digest(contract)


def test_publication_contract_v3_is_the_only_writer_semantic_projection() -> None:
    contract = _contract_v3()
    document = publication_contract_document(contract)
    restored = publication_contract_from_document(_json_round_trip_document(document))
    request = build_writer_request_v3(
        contract,
        product_decision_basis=None,
        platform_expression_responsibility="以图文页面形成完整阅读结构",
        prior_output=None,
        revision_instruction=None,
    )
    request_document = writer_request_document(request)

    assert restored == contract
    assert publication_contract_digest(restored) == publication_contract_digest(contract)
    assert request.actuality_fact_refs == (contract.input_roles[0].source_id,)
    assert request.read_only_actuality_context == (
        {
            "fact_ref": contract.input_roles[0].source_id,
            "exact_text": contract.input_roles[0].exact_text,
        },
    )
    assert contract.input_roles[1].exact_text in request.explicit_user_controls
    assert contract.input_roles[0].exact_text not in request.topic
    assert "known_conditions" not in request_document
    assert "visible_text" not in json.dumps(
        request_document,
        ensure_ascii=False,
    )


def test_publication_contract_v3_rejects_actuality_text_in_writer_topic() -> None:
    contract = _contract_v3()
    actuality = next(span for span in contract.input_roles if span.role == "observable_actuality")

    with pytest.raises(DomainError, match="Writer 主题不得包含服务端冻结的现实原文"):
        build_publication_contract_v3(
            input_roles=contract.input_roles,
            topic_origin=contract.topic_origin,
            topic=actuality.exact_text,
            content_product=contract.content_product,
            central_job=contract.central_job,
            audience_payoff=contract.audience_payoff,
            explicit_user_controls=contract.explicit_user_controls,
            account_editorial_permission=contract.account_editorial_permission,
            frozen_fact_refs=contract.frozen_fact_refs,
            product_decision_basis=contract.product_decision_basis,
            series_delta=contract.series_delta,
            platform_direction=contract.platform_direction,
            media_capability_ref=contract.media_capability_ref,
            brand_context_use=contract.brand_context_use,
            publication_projection_id=contract.publication_projection_id,
            publication_projection_version=contract.publication_projection_version,
            publication_projection_digest=contract.publication_projection_digest,
        )


def test_publication_contract_v3_projects_two_brands_without_a_diyu_branch() -> None:
    first = _contract_v3()
    second = replace(
        first,
        account_editorial_permission=replace(
            first.account_editorial_permission,
            identity="另一品牌的生活编辑",
            audience="希望把日常说清楚的人",
            allowed_stance="从具体处境形成克制但明确的判断",
        ),
        publication_projection_id="55555555-5555-4555-8555-555555555555",
        publication_projection_digest="5" * 64,
    )

    first_request = writer_request_document(
        build_writer_request_v3(
            first,
            product_decision_basis=None,
            platform_expression_responsibility="以图文页面形成完整阅读结构",
            prior_output=None,
            revision_instruction=None,
        )
    )
    second_request = writer_request_document(
        build_writer_request_v3(
            second,
            product_decision_basis=None,
            platform_expression_responsibility="以图文页面形成完整阅读结构",
            prior_output=None,
            revision_instruction=None,
        )
    )

    assert first_request["account_editorial_permission"] != second_request["account_editorial_permission"]
    assert first_request["publication_contract_digest"] != second_request["publication_contract_digest"]
    assert "笛语" not in json.dumps(first_request, ensure_ascii=False)
    assert "笛语" not in json.dumps(second_request, ensure_ascii=False)


def test_publication_contract_v3_fails_closed_on_brand_use_and_span_drift() -> None:
    document = publication_contract_document(_contract_v3())
    raw_use = document["brand_context_use"]
    assert isinstance(raw_use, dict)
    raw_use["displayed_refs"] = ["brand-1"]
    raw_use["consumed_refs"] = ["method-1"]
    with pytest.raises(DomainError, match="品牌资料消费状态越界"):
        publication_contract_from_document(document)

    span_document = publication_contract_document(_contract_v3())
    raw_roles = span_document["input_roles"]
    assert isinstance(raw_roles, list)
    assert isinstance(raw_roles[0], dict)
    raw_roles[0]["end_byte"] = int(raw_roles[0]["end_byte"]) + 1
    with pytest.raises(DomainError, match="输入跨度无效"):
        publication_contract_from_document(span_document)


@pytest.mark.parametrize(
    ("field", "delta"),
    (
        ("end_offset", 1),
        ("end_byte", -1),
    ),
)
def test_publication_contract_rejects_invalid_exact_span_lengths(
    field: str,
    delta: int,
) -> None:
    document = publication_contract_document(_contract())
    first_span = _span_documents(document)[0]
    current_value = first_span[field]
    assert isinstance(current_value, int)
    first_span[field] = current_value + delta

    with pytest.raises(DomainError, match="输入跨度无效"):
        publication_contract_from_document(document)


def test_publication_contract_rejects_unknown_span_role() -> None:
    document = publication_contract_document(_contract())
    _span_documents(document)[0]["role"] = "invented_reality_role"

    with pytest.raises(DomainError, match="输入跨度无效"):
        publication_contract_from_document(document)


def test_publication_contract_rejects_duplicate_span_source_ids() -> None:
    document = publication_contract_document(_contract())
    spans = _span_documents(document)
    spans[1]["source_id"] = spans[0]["source_id"]

    with pytest.raises(DomainError, match="输入跨度无效"):
        publication_contract_from_document(document)


def test_publication_contract_rejects_unbound_actuality_span() -> None:
    document = publication_contract_document(_contract())
    document["frozen_fact_refs"] = []

    with pytest.raises(DomainError, match="现实事实跨度没有绑定冻结事实"):
        publication_contract_from_document(document)


def test_frozen_publication_contract_validates_document_and_digest() -> None:
    contract = _contract()
    snapshot: dict[str, object] = {
        "publication_contract": publication_contract_document(contract),
        "publication_contract_digest": publication_contract_digest(contract),
    }
    persisted_snapshot = _json_round_trip_document(snapshot)

    assert frozen_publication_contract(persisted_snapshot) == contract

    tampered_document = deepcopy(persisted_snapshot)
    raw_contract = tampered_document["publication_contract"]
    assert isinstance(raw_contract, dict)
    raw_contract["topic"] = "被静默替换的题材"
    with pytest.raises(DomainError, match="摘要不一致"):
        frozen_publication_contract(tampered_document)

    tampered_digest = dict(persisted_snapshot)
    tampered_digest["publication_contract_digest"] = "f" * 64
    with pytest.raises(DomainError, match="摘要不一致"):
        frozen_publication_contract(tampered_digest)


def test_repository_accepts_current_complete_publication_keyset() -> None:
    contract = _contract()
    task_snapshot = _json_round_trip_document(
        {
            "publication_contract": publication_contract_document(contract),
            "publication_contract_digest": publication_contract_digest(contract),
        }
    )
    patch = _current_completion_patch(contract)

    assert frozenset(patch) == PostgresContentRepository._DUAL_TRACK_COMPLETION_KEYS
    merged = PostgresContentRepository._validated_completion_snapshot(
        task_snapshot,
        patch,
    )

    assert merged["publication_contract"] == task_snapshot["publication_contract"]
    assert merged["publication_contract_digest"] == task_snapshot["publication_contract_digest"]


@pytest.mark.parametrize(
    "missing_key",
    ("publication_contract", "publication_contract_digest"),
)
def test_repository_rejects_half_publication_completion_pair(
    missing_key: str,
) -> None:
    contract = _contract()
    patch = _current_completion_patch(contract)
    patch.pop(missing_key)

    with pytest.raises(DomainError, match="字段不完整或越界"):
        PostgresContentRepository._validated_completion_snapshot({}, patch)


@pytest.mark.parametrize(
    "compiler_version",
    (
        DUAL_TRACK_DELIVERY_COMPILER_VERSION,
        MEDIA_NATIVE_DELIVERY_COMPILER_VERSION,
        DELIVERY_COMPILER_VERSION,
    ),
)
def test_repository_accepts_prepublication_v2_v3_v4_completion_shapes(
    compiler_version: str,
) -> None:
    patch = _legacy_completion_patch(_contract(), compiler_version)

    merged = PostgresContentRepository._validated_completion_snapshot({}, patch)

    assert merged["delivery_compiler_version"] == compiler_version
    assert "publication_contract" not in merged
    assert "publication_contract_digest" not in merged


@pytest.mark.parametrize(
    "legacy_snapshot",
    (
        {},
        {
            "publication_contract": None,
            "publication_contract_digest": None,
        },
    ),
)
def test_prepublication_snapshot_reads_without_inventing_a_contract(
    legacy_snapshot: dict[str, object],
) -> None:
    assert frozen_publication_contract(legacy_snapshot) is None


def test_repository_v1_to_v2_revision_keeps_publication_contract_frozen() -> None:
    contract = _contract()
    persisted_task_snapshot = _json_round_trip_document(
        {
            "publication_contract": publication_contract_document(contract),
            "publication_contract_digest": publication_contract_digest(contract),
        }
    )
    version_one = PostgresContentRepository._validated_completion_snapshot(
        persisted_task_snapshot,
        _current_completion_patch(contract),
    )
    revision_patch = _json_round_trip_document(_current_completion_patch(contract))

    version_two = PostgresContentRepository._validated_completion_snapshot(
        version_one,
        revision_patch,
    )

    assert version_two["publication_contract"] == version_one["publication_contract"]
    assert version_two["publication_contract_digest"] == version_one["publication_contract_digest"]

    changed_revision = deepcopy(revision_patch)
    changed_contract = changed_revision["publication_contract"]
    assert isinstance(changed_contract, dict)
    changed_contract["topic"] = "修订时偷换的新题材"
    with pytest.raises(DomainError, match="publication_contract"):
        PostgresContentRepository._validated_completion_snapshot(
            version_one,
            changed_revision,
        )
