from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest

from src.brain.content_service import ContentService
from src.shared.errors import DomainError
from src.shared.narrative import (
    FRAME_VERSION,
    NarrativeBlock,
    NarrativeBlockType,
    ObservationType,
    ReviewerObservation,
    frame_document,
    frame_from_document,
    legacy_frame,
    new_frame,
    reconcile_observations,
)
from src.shared.types import (
    ContentControlContext,
    CreativeDirection,
    DirectionSelection,
)

_CONSTRAINTS = frozenset(
    {
        "source:brand_baseline",
        "source:role_boundary",
        "source:organization",
    }
)
_SCENE_TEXT = "抽象色块沿阅读顺序展开。"


def _block(
    text: str,
    *,
    block_type: str = "general_observation",
    fact_refs: tuple[str, ...] = (),
) -> NarrativeBlock:
    return NarrativeBlock(
        block_id="b1",
        block_type=cast(NarrativeBlockType, block_type),
        slot="spoken",
        text=text,
        fact_refs=fact_refs,
        constraint_refs=("source:brand_baseline",),
        linked_scene_ids=("s1",),
    )


def _observation(
    block: NarrativeBlock,
    observation_type: ObservationType = "abstract_principle",
    *,
    actions: tuple[str, ...] = (),
    disclosure: tuple[str, ...] = (),
) -> ReviewerObservation:
    return ReviewerObservation(
        target_id=block.block_id,
        target_kind="block",
        text_spans=(block.text,),
        people=(),
        relationships=(),
        actions_or_events=actions,
        dialogue=(),
        motives=(),
        causes=(),
        results=(),
        times=(),
        locations=(),
        possessions=(),
        observation_type=observation_type,
        resource_refs=(),
        dramatization_disclosure_spans=disclosure,
        instruction_conflicts=(),
        uncertain=False,
    )


def _scene_observation(
    *,
    observation_type: ObservationType = "abstract_principle",
    resources: tuple[str, ...] = ("resource:original_composition",),
) -> ReviewerObservation:
    return ReviewerObservation(
        target_id="s1",
        target_kind="scene",
        text_spans=(_SCENE_TEXT,),
        people=(),
        relationships=(),
        actions_or_events=(),
        dialogue=(),
        motives=(),
        causes=(),
        results=(),
        times=(),
        locations=(),
        possessions=(),
        observation_type=observation_type,
        resource_refs=resources,
        dramatization_disclosure_spans=(),
        instruction_conflicts=(),
        uncertain=False,
    )


def _issues(
    frame: object,
    block: NarrativeBlock,
    observation: ReviewerObservation,
    *,
    scene_observation: ReviewerObservation | None = None,
    fact_text_by_id: dict[str, str] | None = None,
    brand_fact_ids: frozenset[str] = frozenset(),
) -> set[str]:
    assert not isinstance(frame, dict)
    issues = reconcile_observations(
        frame=frame,  # type: ignore[arg-type]
        blocks=(block,),
        scene_text={"s1": _SCENE_TEXT},
        scene_resource_refs={"s1": ("resource:original_composition",)},
        observations=(
            observation,
            scene_observation or _scene_observation(),
        ),
        allowed_resource_ids=frozenset(
            {
                "resource:creator_expression",
                "resource:original_composition",
            }
        ),
        fact_text_by_id=fact_text_by_id or {},
        brand_fact_ids=brand_fact_ids,
        allowed_constraint_ids=_CONSTRAINTS,
    )
    return {issue.reason for issue in issues}


def test_frame_v1_round_trips_and_legacy_tasks_are_conservative() -> None:
    frame = new_frame(
        "actuality_reflection",
        ("今天店里忙了一天，回家还因为谁洗碗拌了两句。",),
        ("fact:product:one",),
    )
    assert frame.frame_version == FRAME_VERSION
    assert frame_from_document(frame_document(frame)) == frame
    assert legacy_frame().narrative_mode == "general_observation"
    assert legacy_frame().user_facts == ()


def test_frame_rejects_actuality_without_exact_source_and_nonactual_with_source() -> None:
    actual = frame_document(
        new_frame("actuality_reflection", ("今天店里忙了一天。",), ())
    )
    actual["user_facts"] = []
    with pytest.raises(DomainError, match="缺少冻结原文"):
        frame_from_document(actual)
    nonactual = frame_document(new_frame("general_observation", (), ()))
    nonactual["user_facts"] = [
        {
            "source_id": "source:user_actuality:1",
            "exact_text": "不应存在",
        }
    ]
    with pytest.raises(DomainError, match="不能冻结真人事实"):
        frame_from_document(nonactual)


def test_only_an_explicit_registered_story_mechanism_forces_dramatization() -> None:
    selection = DirectionSelection(
        axis="mechanism",
        stable_id="CAT-GENRE-DRAMA-04",
        label="故事品牌",
        applied_label="故事品牌",
        translated=False,
        preserved_aspect="",
        origin="explicit",
    )
    direction = CreativeDirection(
        catalog_version="content-expression-catalog-v2",
        selections=(selection,),
        custom_text="",
        body_related_opt_in=False,
        translation_notice=None,
    )
    control = ContentControlContext(
        catalog_version=direction.catalog_version,
        direction=direction,
        account_expression=None,
        materials=(),
        preference_mode="absent",
        preference_version=None,
    )
    assert ContentService._explicit_narrative_mode(control) == "dramatization"
    defaulted = replace(
        control,
        direction=replace(
            direction,
            selections=(replace(selection, origin="default"),),
        ),
    )
    assert ContentService._explicit_narrative_mode(defaulted) is None


def test_mutation_removing_dramatization_disclosure_fails() -> None:
    frame = new_frame("dramatization", (), ())
    block = _block(
        "婆婆把桌上的两张牌翻了过来。",
        block_type="dramatization",
    )
    assert "dramatization_not_visible" in _issues(
        frame,
        block,
        _observation(block, "dramatization"),
    )


def test_implicit_micro_event_fails_in_general_observation() -> None:
    frame = new_frame("general_observation", (), ())
    block = _block("饭桌上一句话让两个人都沉默。")
    assert "situated_event_in_observation" in _issues(
        frame,
        block,
        _observation(
            block,
            "situated_event",
            actions=("饭桌上一句话让两个人都沉默",),
        ),
    )


def test_unsupported_institutional_assertion_cannot_use_constraint_as_fact() -> None:
    frame = new_frame("general_observation", (), ())
    block = _block("笛语相信婆媳关系需要换位思考。")
    assert "unsupported_institutional_assertion" in _issues(
        frame,
        block,
        _observation(block, "institutional_assertion"),
    )


def test_exact_brand_fact_can_support_institutional_assertion() -> None:
    text = "笛语相信婆媳关系需要换位思考。"
    fact_id = "fact:brand:one"
    frame = new_frame(
        "general_observation",
        (),
        (),
        (fact_id,),
    )
    block = _block(text, fact_refs=(fact_id,))
    assert not _issues(
        frame,
        block,
        _observation(block, "institutional_assertion"),
        fact_text_by_id={fact_id: text},
        brand_fact_ids=frozenset({fact_id}),
    )


def test_abstract_principle_is_not_misclassified_as_event() -> None:
    frame = new_frame("general_observation", (), ())
    block = _block("换位思考不等于没有边界。")
    assert not _issues(frame, block, _observation(block))


def test_mutation_using_user_actuality_as_a_filming_resource_fails() -> None:
    frame = new_frame(
        "actuality_reflection",
        ("今天店里忙了一天。",),
        (),
    )
    block = NarrativeBlock(
        block_id="actuality:1",
        block_type="actuality_source",
        slot="spoken",
        text="今天店里忙了一天。",
        fact_refs=("source:user_actuality:1",),
        constraint_refs=(),
        linked_scene_ids=("s1",),
    )
    assert "unsupported_resource" in _issues(
        frame,
        block,
        _observation(block, "user_actuality"),
        scene_observation=_scene_observation(
            resources=("source:user_actuality:1",)
        ),
    )


def test_scene_situated_event_is_not_hidden_by_missing_explicit_people() -> None:
    frame = new_frame("general_observation", (), ())
    block = _block("换位思考不等于没有边界。")
    assert "scene_mode_drift" in _issues(
        frame,
        block,
        _observation(block),
        scene_observation=_scene_observation(
            observation_type="situated_event"
        ),
    )


def test_mutation_changing_actuality_block_fails_against_frozen_frame() -> None:
    frame = new_frame(
        "actuality_reflection",
        ("今天店里忙了一天，回家还因为谁洗碗拌了两句。",),
        (),
    )
    block = NarrativeBlock(
        block_id="actuality:1",
        block_type="actuality_source",
        slot="spoken",
        text="今天店里忙了一天，丈夫最后把碗洗了。",
        fact_refs=("source:user_actuality:1",),
        constraint_refs=(),
        linked_scene_ids=("s1",),
    )
    assert "actuality_changed" in _issues(
        frame,
        block,
        _observation(block, "user_actuality"),
    )
    changed_frame = replace(
        frame,
        user_facts=(
            replace(frame.user_facts[0], exact_text="今天店里不忙。"),
        ),
    )
    assert frame_document(changed_frame) != frame_document(frame)


@pytest.mark.parametrize("mutation", ("missing", "partial_span", "unknown_span"))
def test_mutation_sparse_or_nonexistent_reviewer_span_fails(
    mutation: str,
) -> None:
    frame = new_frame("general_observation", (), ())
    block = _block("边界像标点，停顿不等于敌意。")
    observation = _observation(block)
    observations: tuple[ReviewerObservation, ...]
    if mutation == "missing":
        observations = (_scene_observation(),)
    elif mutation == "partial_span":
        observations = (
            replace(observation, text_spans=("边界像标点",)),
            _scene_observation(),
        )
    else:
        observations = (
            replace(observation, text_spans=("不存在的跨度",)),
            _scene_observation(),
        )
    issues = reconcile_observations(
        frame=frame,
        blocks=(block,),
        scene_text={"s1": _SCENE_TEXT},
        scene_resource_refs={"s1": ("resource:original_composition",)},
        observations=observations,
        allowed_resource_ids=frozenset({"resource:original_composition"}),
        fact_text_by_id={},
        brand_fact_ids=frozenset(),
        allowed_constraint_ids=_CONSTRAINTS,
    )
    assert {"review_coverage", "missing_exact_span"} & {
        issue.reason for issue in issues
    }
