from __future__ import annotations

from dataclasses import replace

import pytest

from src.brain.content_service import ContentService
from src.shared.errors import DomainError
from src.shared.narrative import (
    FRAME_VERSION,
    NarrativeBlock,
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


def _block_observation(
    block: NarrativeBlock,
    *,
    binding: str = "general_observation",
    people: tuple[str, ...] = (),
    relationships: tuple[str, ...] = (),
    actions: tuple[str, ...] = (),
    disclosure: tuple[str, ...] = (),
) -> ReviewerObservation:
    return ReviewerObservation(
        target_id=block.block_id,
        target_kind="block",
        text_spans=(block.text,),
        people=people,
        relationships=relationships,
        actions_or_events=actions,
        dialogue=(),
        motives=(),
        causes=(),
        results=(),
        times=(),
        locations=(),
        possessions=(),
        reality_binding=binding,  # type: ignore[arg-type]
        resource_refs=(),
        dramatization_disclosure_spans=disclosure,
        instruction_conflicts=(),
        uncertain=False,
    )


def _scene_observation(
    text: str,
    *,
    resources: tuple[str, ...] = ("resource:original_composition",),
) -> ReviewerObservation:
    return ReviewerObservation(
        target_id="s1",
        target_kind="scene",
        text_spans=(text,),
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
        reality_binding="general_observation",
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
) -> set[str]:
    assert not isinstance(frame, dict)
    scene_text = "抽象色块沿阅读顺序展开。"
    issues = reconcile_observations(
        frame=frame,  # type: ignore[arg-type]
        blocks=(block,),
        scene_text={"s1": scene_text},
        scene_resource_refs={"s1": ("resource:original_composition",)},
        observations=(
            observation,
            scene_observation or _scene_observation(scene_text),
        ),
        allowed_resource_ids=frozenset(
            {
                "resource:creator_expression",
                "resource:original_composition",
            }
        ),
        exact_product_facts={},
    )
    return {issue.reason for issue in issues}


def test_frame_v1_round_trips_and_legacy_tasks_are_conservative() -> None:
    frame = new_frame(
        "actuality_reflection",
        ("今天店里忙了一天，回家还因为谁洗碗拌了两句。",),
        ("source:product:ZX-C218",),
    )
    assert frame.frame_version == FRAME_VERSION
    assert frame_from_document(frame_document(frame)) == frame
    assert legacy_frame().narrative_mode == "general_observation"
    assert legacy_frame().user_facts == ()


def test_frame_rejects_actuality_without_exact_source_and_nonactual_with_source() -> None:
    actual = frame_document(
        new_frame(
            "actuality_reflection",
            ("今天店里忙了一天。",),
            (),
        )
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
    block = NarrativeBlock(
        "b1",
        "dramatization",
        "spoken",
        "婆婆把桌上的两张牌翻了过来。",
        ("source:brand_baseline",),
        ("s1",),
    )
    assert "dramatization_not_visible" in _issues(
        frame,
        block,
        _block_observation(block, binding="dramatization"),
    )


def test_mutation_turning_general_observation_into_user_event_fails() -> None:
    frame = new_frame("general_observation", (), ())
    block = NarrativeBlock(
        "b1",
        "general_observation",
        "spoken",
        "我婆婆每天替我带孩子。",
        ("source:brand_baseline",),
        ("s1",),
    )
    assert "concrete_event_in_observation" in _issues(
        frame,
        block,
        _block_observation(
            block,
            people=("我婆婆",),
            relationships=("婆媳",),
            actions=("每天替我带孩子",),
        ),
    )


def test_mutation_using_user_actuality_as_a_filming_resource_fails() -> None:
    frame = new_frame(
        "actuality_reflection",
        ("今天店里忙了一天。",),
        (),
    )
    block = NarrativeBlock(
        "actuality:1",
        "actuality_source",
        "spoken",
        "今天店里忙了一天。",
        ("source:user_actuality:1",),
        ("s1",),
    )
    assert "unsupported_resource" in _issues(
        frame,
        block,
        _block_observation(block, binding="user_actuality"),
        scene_observation=_scene_observation(
            "抽象色块沿阅读顺序展开。",
            resources=("source:user_actuality:1",),
        ),
    )


def test_scene_observation_cannot_smuggle_a_real_person_or_relationship() -> None:
    frame = new_frame(
        "actuality_reflection",
        ("今天店里忙了一天。",),
        (),
    )
    block = NarrativeBlock(
        "actuality:1",
        "actuality_source",
        "spoken",
        "今天店里忙了一天。",
        ("source:user_actuality:1",),
        ("s1",),
    )
    observed_scene = replace(
        _scene_observation("抽象色块沿阅读顺序展开。"),
        people=("丈夫",),
        relationships=("夫妻",),
        actions_or_events=("在厨房洗碗",),
        resource_refs=("resource:original_composition",),
    )
    assert "unregistered_scene_actuality" in _issues(
        frame,
        block,
        _block_observation(block, binding="user_actuality"),
        scene_observation=observed_scene,
    )


def test_mutation_changing_actuality_block_fails_against_frozen_frame() -> None:
    frame = new_frame(
        "actuality_reflection",
        ("今天店里忙了一天，回家还因为谁洗碗拌了两句。",),
        (),
    )
    block = NarrativeBlock(
        "actuality:1",
        "actuality_source",
        "spoken",
        "今天店里忙了一天，丈夫最后把碗洗了。",
        ("source:user_actuality:1",),
        ("s1",),
    )
    assert "actuality_changed" in _issues(
        frame,
        block,
        _block_observation(block, binding="user_actuality"),
    )
    changed_frame = replace(
        frame,
        user_facts=(
            replace(
                frame.user_facts[0],
                exact_text="今天店里不忙。",
            ),
        ),
    )
    assert frame_document(changed_frame) != frame_document(frame)


@pytest.mark.parametrize(
    "mutation",
    ("missing", "partial_span", "unknown_span"),
)
def test_mutation_sparse_or_nonexistent_reviewer_span_fails(
    mutation: str,
) -> None:
    frame = new_frame("general_observation", (), ())
    block = NarrativeBlock(
        "b1",
        "general_observation",
        "spoken",
        "边界像标点，停顿不等于敌意。",
        ("source:brand_baseline",),
        ("s1",),
    )
    observation = _block_observation(block)
    observations: tuple[ReviewerObservation, ...]
    if mutation == "missing":
        observations = (_scene_observation("抽象色块沿阅读顺序展开。"),)
    elif mutation == "partial_span":
        observations = (
            replace(observation, text_spans=("边界像标点",)),
            _scene_observation("抽象色块沿阅读顺序展开。"),
        )
    else:
        observations = (
            replace(observation, text_spans=("不存在的跨度",)),
            _scene_observation("抽象色块沿阅读顺序展开。"),
        )
    issues = reconcile_observations(
        frame=frame,
        blocks=(block,),
        scene_text={"s1": "抽象色块沿阅读顺序展开。"},
        scene_resource_refs={"s1": ("resource:original_composition",)},
        observations=observations,
        allowed_resource_ids=frozenset({"resource:original_composition"}),
        exact_product_facts={},
    )
    assert {"review_coverage", "missing_exact_span"} & {
        issue.reason for issue in issues
    }
