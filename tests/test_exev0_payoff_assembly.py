from __future__ import annotations

from dataclasses import replace

import pytest

from src.brain.payoff_assembly import (
    CONTENT_PRODUCTS,
    PAYOFF_RULESET_VERSION,
    RULESET_V0,
    TOPIC_ORIGINS,
    PayoffAssemblyRequest,
    assemble_task_value,
    build_payoff_request,
    payoff_ruleset_digest,
    product_contract_job,
    profile_signals,
    static_payoff_defaults,
)
from src.shared.errors import DomainError
from src.shared.publication_contract import (
    ProductDecisionBasisRefV2,
    SeriesDeltaV1,
    product_brief,
)
from src.shared.task_value_assembly import (
    PAYOFF_DEGRADATION_REASONS,
    PAYOFF_MAX_LENGTH,
    PAYOFF_MIN_LENGTH,
    PRE_PROPOSAL_CONFIRMATION_STATE,
    PROFILE_SIGNAL_FIELDS,
    V0_PRODUCIBLE_PATHS,
    V0_RESERVED_PATHS,
    assert_task_value_assembly,
    normalized_payoff,
    task_value_assembly_digest,
    task_value_assembly_document,
    task_value_assembly_from_document,
)
from src.shared.types import AccountExpression

# The six 题材 the pre-V0 static table distinguishes: five content products, with
# the life narrative splitting on topic origin.
SIX_TOPIC_KINDS: tuple[tuple[str, str], ...] = (
    ("dressing_decision", "explicit_user"),
    ("product_truth", "explicit_user"),
    ("local_response", "explicit_user"),
    ("visual_styling_story", "explicit_user"),
    ("brand_life_narrative", "explicit_user"),
    ("brand_life_narrative", "system_selected"),
)


def _expression(**overrides: str) -> AccountExpression:
    segments = {
        "identity_position": "总部岗位型表达身份，代表品牌说清当前确认的立场",
        "authority_boundary": "只使用已经确认的品牌基线与当前版本商品事实",
        "audience_relationship": "与受众平等协作，帮助判断适合谁、解决什么、有什么取舍",
        "content_territories": "持续讨论真实穿衣问题、商品事实与专业取舍",
        "default_production_conditions": "默认按一人、一部手机、普通室内完成",
    }
    segments.update(overrides)
    return AccountExpression(
        profile_id=None,
        version=1,
        is_draft=False,
        **segments,
    )


_EMPTY_EXPRESSION = _expression(
    identity_position="",
    authority_boundary="",
    audience_relationship="",
    content_territories="",
    default_production_conditions="",
)


def _product_basis(*, supporting: tuple[str, ...] = ("source:product:1",)) -> ProductDecisionBasisRefV2:
    return ProductDecisionBasisRefV2(
        contract_version="product-decision-basis-v2",
        digest="a" * 64,
        supporting_fact_refs=supporting,
    )


def _series_delta(position: int = 2) -> SeriesDeltaV1:
    return SeriesDeltaV1(
        contract_version="series-episode-contract-v1",
        prior_episode_facts=(),
        prior_judgments=("上一篇已经给出的判断",),
        current_episode_job="完成系列第 2 篇并推进冻结主线",
        required_new_judgment="必须给出一条尚未出现过的判断",
        series_position=position,
        topic_origin="explicit_user",
    )


def _request(
    content_product: str,
    topic_origin: str = "explicit_user",
    *,
    expression: AccountExpression | None = None,
    product_basis: ProductDecisionBasisRefV2 | None = None,
    series_delta: SeriesDeltaV1 | None = None,
) -> PayoffAssemblyRequest:
    return build_payoff_request(
        content_product=content_product,
        topic_origin=topic_origin,
        account_expression=_expression() if expression is None else expression,
        product_basis=product_basis,
        series_delta=series_delta,
        static_payoff=product_brief(content_product, topic_origin)[1],
    )


def test_assembly_is_deterministic_for_the_same_input() -> None:
    first = assemble_task_value(_request("product_truth", product_basis=_product_basis()))
    second = assemble_task_value(_request("product_truth", product_basis=_product_basis()))

    assert first == second
    assert task_value_assembly_digest(first) == task_value_assembly_digest(second)
    assert first.payoff_origin == "server_assembled"
    assert first.payoff_confirmation_state == PRE_PROPOSAL_CONFIRMATION_STATE


def test_six_topic_kinds_produce_six_distinct_payoffs() -> None:
    payoffs = [
        assemble_task_value(_request(content_product, topic_origin)).audience_payoff
        for content_product, topic_origin in SIX_TOPIC_KINDS
    ]

    assert len({normalized_payoff(payoff) for payoff in payoffs}) == len(SIX_TOPIC_KINDS)


def test_every_producible_payoff_stays_inside_the_length_gate() -> None:
    for content_product in CONTENT_PRODUCTS:
        for topic_origin in TOPIC_ORIGINS:
            for basis in (None, _product_basis()):
                for series in (None, _series_delta(1), _series_delta(3)):
                    assembly = assemble_task_value(
                        _request(
                            content_product,
                            topic_origin,
                            product_basis=basis,
                            series_delta=series,
                        )
                    )
                    assert PAYOFF_MIN_LENGTH <= len(assembly.audience_payoff) <= PAYOFF_MAX_LENGTH


def test_no_assembled_payoff_repeats_a_static_default() -> None:
    defaults = {normalized_payoff(default) for default in static_payoff_defaults()}

    for content_product, topic_origin in SIX_TOPIC_KINDS:
        assembly = assemble_task_value(_request(content_product, topic_origin))

        assert assembly.payoff_origin == "server_assembled"
        assert normalized_payoff(assembly.audience_payoff) not in defaults


def test_static_defaults_are_derived_from_the_product_table_not_copied() -> None:
    assert static_payoff_defaults() == tuple(
        dict.fromkeys(
            product_brief(content_product, topic_origin)[1]
            for content_product in CONTENT_PRODUCTS
            for topic_origin in TOPIC_ORIGINS
        )
    )
    assert len(static_payoff_defaults()) == len(SIX_TOPIC_KINDS)


def test_frozen_product_basis_wins_the_path_over_the_account_profile() -> None:
    assembly = assemble_task_value(_request("product_truth", product_basis=_product_basis()))

    assert assembly.brand_relevance_path == "product_expertise"
    assert assembly.assembly_trace.product_basis_present is True
    assert assembly.assembly_trace.used_profile_fields == ()


def test_an_empty_supporting_fact_list_does_not_count_as_a_product_basis() -> None:
    assembly = assemble_task_value(
        _request("product_truth", product_basis=_product_basis(supporting=()))
    )

    assert assembly.brand_relevance_path == "audience_relationship"
    assert assembly.assembly_trace.product_basis_present is False


def test_a_valid_series_delta_takes_the_series_path_and_marks_continuity() -> None:
    second = assemble_task_value(_request("brand_life_narrative", series_delta=_series_delta(2)))
    first = assemble_task_value(_request("brand_life_narrative", series_delta=_series_delta(1)))

    assert second.brand_relevance_path == "existing_series"
    assert second.assembly_trace.template_id.endswith("+series")
    assert RULESET_V0.series_continuity_tail in second.audience_payoff
    assert first.brand_relevance_path == "existing_series"
    assert RULESET_V0.series_continuity_tail not in first.audience_payoff


def test_audience_relationship_falls_back_to_brand_stance_when_that_segment_is_blank() -> None:
    assembly = assemble_task_value(
        _request("brand_life_narrative", expression=_expression(audience_relationship=""))
    )

    assert assembly.brand_relevance_path == "brand_stance"
    assert assembly.assembly_trace.used_profile_fields == (
        "identity_position",
        "authority_boundary",
        "content_territories",
    )


def test_the_trace_points_back_at_the_profile_field_that_justified_the_path() -> None:
    assembly = assemble_task_value(_request("brand_life_narrative"))

    assert assembly.brand_relevance_path == "audience_relationship"
    assert assembly.assembly_trace.used_profile_fields == ("audience_relationship",)
    assert set(assembly.assembly_trace.used_profile_fields) <= set(PROFILE_SIGNAL_FIELDS)


def test_v0_never_produces_a_reserved_relevance_path() -> None:
    for content_product in CONTENT_PRODUCTS:
        for topic_origin in TOPIC_ORIGINS:
            assembly = assemble_task_value(
                _request(content_product, topic_origin, product_basis=_product_basis())
            )

            assert assembly.brand_relevance_path not in V0_RESERVED_PATHS
            assert assembly.brand_relevance_path in V0_PRODUCIBLE_PATHS


def test_a_product_basis_may_not_repoint_a_life_narrative_at_goods() -> None:
    assembly = assemble_task_value(
        _request(
            "brand_life_narrative",
            expression=_EMPTY_EXPRESSION,
            product_basis=_product_basis(),
        )
    )

    assert assembly.payoff_origin == "static_fallback"
    assert assembly.payoff_degraded is True
    assert assembly.payoff_degradation_reason == "safety_gate_rejected"
    assert assembly.brand_relevance_path is None


def test_a_missing_profile_degrades_visibly_instead_of_inventing_a_path() -> None:
    assembly = assemble_task_value(_request("brand_life_narrative", expression=_EMPTY_EXPRESSION))

    assert assembly.payoff_origin == "static_fallback"
    assert assembly.payoff_degraded is True
    assert assembly.payoff_degradation_reason == "missing_profile_signal"
    assert assembly.brand_relevance_path is None
    assert assembly.audience_payoff == product_brief("brand_life_narrative", "explicit_user")[1]


def test_a_product_whose_only_natural_path_is_reserved_reports_that_reason() -> None:
    assembly = assemble_task_value(_request("local_response", expression=_EMPTY_EXPRESSION))

    assert assembly.payoff_degradation_reason == "unsupported_relevance_path"
    assert RULESET_V0.natural_reserved_path["local_response"] in V0_RESERVED_PATHS


def test_a_ruleset_that_cannot_form_a_legal_sentence_reports_invalid_assembly() -> None:
    empty = replace(RULESET_V0, path_lead={}, product_focus={}, topic_tail={})

    assembly = assemble_task_value(_request("brand_life_narrative"), ruleset=empty)

    assert assembly.payoff_degradation_reason == "invalid_assembly"
    assert assembly.payoff_origin == "static_fallback"
    assert assembly.brand_relevance_path is None


def test_a_ruleset_that_reproduces_a_static_default_is_refused_at_the_hard_gate() -> None:
    static_default = product_brief("brand_life_narrative", "explicit_user")[1]
    echoes_static = replace(
        RULESET_V0,
        path_lead={path: "" for path in V0_PRODUCIBLE_PATHS},
        product_focus={"brand_life_narrative": static_default},
        topic_tail={"explicit_user": ""},
    )

    assembly = assemble_task_value(_request("brand_life_narrative"), ruleset=echoes_static)

    assert assembly.payoff_degradation_reason == "invalid_assembly"
    assert assembly.payoff_origin == "static_fallback"


def test_every_degradation_reason_is_a_declared_enum_member() -> None:
    reasons = {
        assemble_task_value(_request(content_product, expression=_EMPTY_EXPRESSION)).payoff_degradation_reason
        for content_product in CONTENT_PRODUCTS
    }

    assert reasons <= set(PAYOFF_DEGRADATION_REASONS)
    assert None not in reasons


def test_no_payoff_carries_profile_seed_or_product_text() -> None:
    expression = _expression()
    forbidden = (
        expression.identity_position,
        expression.authority_boundary,
        expression.audience_relationship,
        expression.content_territories,
        expression.default_production_conditions,
    )

    for content_product, topic_origin in SIX_TOPIC_KINDS:
        payoff = assemble_task_value(
            _request(content_product, topic_origin, product_basis=_product_basis())
        ).audience_payoff

        for segment in forbidden:
            assert segment not in payoff
        assert "笛语" not in payoff
        assert "ZX-C218" not in payoff


def test_profile_signals_report_field_names_only() -> None:
    signals = profile_signals(_expression(content_territories="   "))

    assert signals == (
        "identity_position",
        "authority_boundary",
        "audience_relationship",
        "default_production_conditions",
    )
    assert profile_signals(None) == ()


def test_product_contract_job_stays_the_five_product_invariant() -> None:
    for content_product in CONTENT_PRODUCTS:
        for topic_origin in TOPIC_ORIGINS:
            assert product_contract_job(content_product, topic_origin) == product_brief(
                content_product, topic_origin
            )[0]


def test_the_ruleset_digest_moves_only_when_the_ruleset_moves() -> None:
    unchanged = replace(RULESET_V0)
    reworded = replace(RULESET_V0, series_continuity_tail="，并且换一个说法")

    assert payoff_ruleset_digest(unchanged) == payoff_ruleset_digest(RULESET_V0)
    assert payoff_ruleset_digest(reworded) != payoff_ruleset_digest(RULESET_V0)
    assert RULESET_V0.version == PAYOFF_RULESET_VERSION


def test_the_assembly_document_round_trips_without_drift() -> None:
    assembly = assemble_task_value(_request("product_truth", product_basis=_product_basis()))
    document = task_value_assembly_document(assembly)

    restored = task_value_assembly_from_document(document)

    assert restored == assembly
    assert task_value_assembly_document(restored) == document
    assert task_value_assembly_digest(restored) == task_value_assembly_digest(assembly)


def test_a_self_contradictory_assembly_is_refused() -> None:
    degraded = assemble_task_value(_request("brand_life_narrative", expression=_EMPTY_EXPRESSION))
    assembled = assemble_task_value(_request("brand_life_narrative"))

    with pytest.raises(DomainError, match="自相矛盾"):
        assert_task_value_assembly(replace(degraded, payoff_degraded=False))
    with pytest.raises(DomainError, match="自相矛盾"):
        assert_task_value_assembly(replace(assembled, payoff_degradation_reason="invalid_assembly"))
    with pytest.raises(DomainError, match="自相矛盾"):
        assert_task_value_assembly(replace(assembled, brand_relevance_path="local_trust"))


def test_a_trace_may_not_carry_an_unknown_profile_field() -> None:
    assembly = assemble_task_value(_request("brand_life_narrative"))
    trace = replace(
        assembly.assembly_trace,
        used_profile_fields=("audience_relationship", "private_notes"),
    )

    with pytest.raises(DomainError, match="价值组装无效"):
        assert_task_value_assembly(replace(assembly, assembly_trace=trace))
