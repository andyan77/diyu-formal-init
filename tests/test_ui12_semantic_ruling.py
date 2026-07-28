from __future__ import annotations

from dataclasses import replace
from typing import Literal

import pytest

from src.shared.creative_kernel import (
    DRAMATIZATION_DISCLOSURE,
    HYPOTHESIS_DISCLOSURE,
    OBSERVATION_ONLY_PROGRAM,
    CreativeKernelV1,
    build_kernel_skeleton,
    parse_writer_kernel,
)
from src.shared.errors import GenerationFailed
from src.shared.factual_basis import FrozenFactRecord
from src.shared.narrative import NarrativeFrame, NarrativeIssue, new_frame
from src.shared.review_evidence import (
    REVIEW_EVIDENCE_V2_VERSION,
    ClauseContextV2,
    ClauseEvidenceV2,
    GrammaticalMarkerSpans,
    ProtectedSubjectScopeV2,
    ReviewEvidenceV2,
    SpanOccurrence,
    UnitContractV2,
    build_clause_contexts_v2,
    parse_review_evidence_v2,
    reconcile_review_evidence_v2,
)
from src.shared.types import SpeakerKind
from src.tool.llm_gateway.deepseek import DeepSeekGenerator

_CONSTRAINTS = frozenset({"source:brand_baseline"})
_ALL_SDR_IDS = frozenset(f"SDR-{index:03d}" for index in range(1, 43))


def _frame_and_kernel(
    *,
    mode: Literal[
        "actuality_reflection",
        "general_observation",
        "hypothesis",
        "dramatization",
    ] = "general_observation",
    program_id: Literal[
        "observation_only_v1",
        "observation_with_hypothetical_example_v1",
    ] = OBSERVATION_ONLY_PROGRAM,
    body: str = "换位思考不等于没有边界。",
    facts: tuple[FrozenFactRecord, ...] = (),
    speaker_kind: SpeakerKind = "institutional_account",
) -> tuple[NarrativeFrame, CreativeKernelV1, tuple[ClauseContextV2, ...]]:
    user_facts = tuple(
        record.exact_text
        for record in facts
        if record.fact_kind == "user_actuality"
    )
    brand_ids = tuple(
        record.fact_id for record in facts if record.fact_kind == "brand"
    )
    product_ids = tuple(
        record.fact_id for record in facts if record.fact_kind == "product"
    )
    frame = new_frame(mode, user_facts, product_ids, brand_ids)
    skeleton = build_kernel_skeleton(
        frame=frame,
        fact_registry=facts,
        constraint_refs=tuple(_CONSTRAINTS),
        program_id=program_id,
    )
    raw_units: list[dict[str, str]] = []
    for unit in skeleton.writable_units:
        text = {
            "unit:title": "边界不是一道判决题",
            "unit:natural-guide": "这篇从理解与边界说起。",
            "unit:body": body,
            "unit:body-opening": body,
            "unit:hypothetical-example": body,
            "unit:body-closing": "彼此可以先停一下。",
            "unit:release-caption": "理解彼此，也保留自己。",
        }[unit.unit_id]
        raw_units.append({"unit_id": unit.unit_id, "text": text})
    kernel = parse_writer_kernel({"units": raw_units}, skeleton)
    contexts = build_clause_contexts_v2(
        kernel=kernel,
        frame=frame,
        fact_registry=facts,
        allowed_constraint_ids=_CONSTRAINTS,
        speaker_kind=speaker_kind,
    )
    return frame, kernel, contexts


def _occurrence(
    text: str,
    fragment: str,
    *,
    occurrence: int = 1,
) -> SpanOccurrence:
    start = -1
    cursor = 0
    for _ in range(occurrence):
        start = text.index(fragment, cursor)
        cursor = start + len(fragment)
    return SpanOccurrence(fragment, start, start + len(fragment))


def _evidence(
    contexts: tuple[ClauseContextV2, ...],
    *,
    target_fragment: str | None = None,
    subject: tuple[str, ...] = (),
    predicate: tuple[str, ...] = (),
    action: tuple[str, ...] = (),
    dialogue: tuple[str, ...] = (),
    motive: tuple[str, ...] = (),
    cause: tuple[str, ...] = (),
    result: tuple[str, ...] = (),
    time: tuple[str, ...] = (),
    location: tuple[str, ...] = (),
    modality: tuple[str, ...] = (),
    aspect: tuple[str, ...] = (),
    implicit_subject: Literal[
        "none",
        "current_speaker",
        "generic",
        "uncertain",
    ] = "none",
    uncertain: bool = False,
) -> ReviewEvidenceV2:
    items: list[ClauseEvidenceV2] = []
    for context in contexts:
        if context.text_source != "writer_unit":
            continue
        selected = (
            target_fragment is not None
            and target_fragment in context.exact_text
        )

        def spans(
            values: tuple[str, ...],
            exact_text: str = context.exact_text,
            selected_clause: bool = selected,
        ) -> tuple[SpanOccurrence, ...]:
            return (
                tuple(_occurrence(exact_text, value) for value in values)
                if selected_clause
                else ()
            )

        items.append(
            ClauseEvidenceV2(
                clause_id=context.clause_id,
                exact_text=context.exact_text,
                subject_spans=spans(subject),
                predicate_spans=spans(predicate),
                action_or_event_spans=spans(action),
                dialogue_spans=spans(dialogue),
                motive_spans=spans(motive),
                cause_spans=spans(cause),
                result_spans=spans(result),
                time_spans=spans(time),
                location_spans=spans(location),
                grammatical_marker_spans=GrammaticalMarkerSpans(
                    modality=spans(modality),
                    aspect=spans(aspect),
                ),
                implicit_subject=implicit_subject if selected else "none",
                uncertain=uncertain if selected else False,
            )
        )
    return ReviewEvidenceV2(REVIEW_EVIDENCE_V2_VERSION, tuple(items))


def _reasons(
    contexts: tuple[ClauseContextV2, ...],
    evidence: ReviewEvidenceV2,
    *,
    facts: tuple[FrozenFactRecord, ...] = (),
    speaker_kind: SpeakerKind = "institutional_account",
) -> tuple[str, ...]:
    return tuple(
        issue.reason
        for issue in reconcile_review_evidence_v2(
            contexts=contexts,
            evidence=evidence,
            fact_text_by_id={
                record.fact_id: record.exact_text for record in facts
            },
            protected_subjects=ProtectedSubjectScopeV2(
                exact_names=("笛语", "笛语服饰", "品牌官方账号"),
                speaker_kind=speaker_kind,
            ),
        )
    )


def _manual_context(
    text: str,
    contract: UnitContractV2,
    *,
    speaker_kind: SpeakerKind = "institutional_account",
) -> tuple[ClauseContextV2, ...]:
    return (
        ClauseContextV2(
            clause_id="unit:test:clause:1",
            unit_id="unit:test",
            exact_text=text,
            visible_order=1,
            text_source="writer_unit",
            unit_contract=contract,
            speaker_kind=speaker_kind,
        ),
    )


@pytest.mark.parametrize(
    ("sdr_id", "mode", "expected_wrapper"),
    (
        ("SDR-001", "hypothesis", HYPOTHESIS_DISCLOSURE),
        ("SDR-004", "dramatization", DRAMATIZATION_DISCLOSURE),
    ),
)
def test_server_wrapper_source_precedes_model_semantics(
    sdr_id: str,
    mode: Literal["hypothesis", "dramatization"],
    expected_wrapper: str,
) -> None:
    _, _, contexts = _frame_and_kernel(mode=mode)
    wrapper = next(
        context
        for context in contexts
        if context.text_source == "server_wrapper"
    )
    evidence = _evidence(
        contexts,
        target_fragment=expected_wrapper,
        subject=(expected_wrapper,),
        predicate=(expected_wrapper,),
        implicit_subject="current_speaker",
    )

    assert wrapper.exact_text == f"{expected_wrapper}\n"
    assert _reasons(contexts, evidence) == ()
    assert sdr_id in _ALL_SDR_IDS


@pytest.mark.parametrize(
    ("sdr_id", "mode", "wrapper"),
    (
        ("SDR-002", "general_observation", HYPOTHESIS_DISCLOSURE),
        ("SDR-005", "general_observation", DRAMATIZATION_DISCLOSURE),
    ),
)
def test_writer_cannot_forge_server_wrapper(
    sdr_id: str,
    mode: Literal["general_observation"],
    wrapper: str,
) -> None:
    with pytest.raises(ValueError, match="forged a server wrapper"):
        _frame_and_kernel(mode=mode, body=wrapper)
    assert sdr_id in _ALL_SDR_IDS


@pytest.mark.parametrize(
    ("sdr_id", "mode"),
    (
        ("SDR-003", "hypothesis"),
        ("SDR-006", "dramatization"),
    ),
)
def test_missing_server_wrapper_fails_closed(
    sdr_id: str,
    mode: Literal["hypothesis", "dramatization"],
) -> None:
    frame, kernel, _ = _frame_and_kernel(mode=mode)
    mutated = replace(
        kernel,
        units=tuple(
            replace(unit, text=unit.text.split("\n", 1)[-1])
            if unit.unit_id == "unit:body"
            else unit
            for unit in kernel.units
        ),
    )
    with pytest.raises(ValueError, match="server wrapper structure drifted"):
        build_clause_contexts_v2(
            kernel=mutated,
            frame=frame,
            fact_registry=(),
            allowed_constraint_ids=_CONSTRAINTS,
            speaker_kind="institutional_account",
        )
    assert sdr_id in _ALL_SDR_IDS


@pytest.mark.parametrize(
    ("sdr_id", "fact"),
    (
        (
            "SDR-007",
            FrozenFactRecord(
                "source:user_actuality:1",
                "今天店里忙了一天。",
                "user_actuality",
            ),
        ),
        (
            "SDR-008",
            FrozenFactRecord(
                "fact:brand:confirmed",
                "笛语确认本账号只发布人工终审后的草稿。",
                "brand",
            ),
        ),
        (
            "SDR-009",
            FrozenFactRecord(
                "fact:product:confirmed",
                "商品编号是 ZX-C218。",
                "product",
            ),
        ),
    ),
)
def test_frozen_fact_source_is_structural_not_model_semantic(
    sdr_id: str,
    fact: FrozenFactRecord,
) -> None:
    mode: Literal["actuality_reflection", "general_observation"] = (
        "actuality_reflection"
        if fact.fact_kind == "user_actuality"
        else "general_observation"
    )
    _, _, contexts = _frame_and_kernel(mode=mode, facts=(fact,))
    evidence = _evidence(
        contexts,
        target_fragment=fact.exact_text,
        subject=(fact.exact_text,),
        predicate=(fact.exact_text,),
        action=(fact.exact_text,),
        aspect=(fact.exact_text,),
    )

    assert _reasons(contexts, evidence, facts=(fact,)) == ()
    assert sdr_id in _ALL_SDR_IDS


def test_frozen_fact_and_writer_fact_bindings_fail_closed() -> None:
    fact = FrozenFactRecord(
        "source:user_actuality:1",
        "今天店里忙了一天。",
        "user_actuality",
    )
    frame, kernel, _ = _frame_and_kernel(
        mode="actuality_reflection",
        facts=(fact,),
    )
    fact_changed = replace(
        kernel,
        units=tuple(
            replace(unit, text="今天店里特别忙。")
            if unit.purpose == "frozen_fact"
            else unit
            for unit in kernel.units
        ),
    )
    with pytest.raises(ValueError, match="fact unit source drifted"):
        build_clause_contexts_v2(
            kernel=fact_changed,
            frame=frame,
            fact_registry=(fact,),
            allowed_constraint_ids=_CONSTRAINTS,
            speaker_kind="institutional_account",
        )

    writer_bound = replace(
        kernel,
        units=tuple(
            replace(unit, fact_refs=(fact.fact_id,))
            if unit.unit_id == "unit:body"
            else unit
            for unit in kernel.units
        ),
    )
    with pytest.raises(ValueError, match="writer-owned unit"):
        build_clause_contexts_v2(
            kernel=writer_bound,
            frame=frame,
            fact_registry=(fact,),
            allowed_constraint_ids=_CONSTRAINTS,
            speaker_kind="institutional_account",
        )
    assert {"SDR-010", "SDR-011"} <= _ALL_SDR_IDS


@pytest.mark.parametrize(
    (
        "sdr_id",
        "text",
        "contract",
        "speaker_kind",
        "subject",
        "predicate",
        "action",
        "dialogue",
        "motive",
        "cause",
        "result",
        "time",
        "location",
        "modality",
        "aspect",
        "implicit",
        "expected",
    ),
    (
        (
            "SDR-012",
            "换位思考不等于没有边界。",
            "abstract_observation",
            "institutional_account",
            (),
            ("不等于",),
            (),
            (),
            (),
            (),
            (),
            (),
            (),
            (),
            (),
            "none",
            (),
        ),
        (
            "SDR-013",
            "关系变僵，不一定是不理解，也可能是一开始期待太高。",
            "abstract_observation",
            "institutional_account",
            (),
            (),
            (),
            (),
            (),
            ("不理解",),
            ("期待太高",),
            (),
            (),
            ("可能",),
            (),
            "generic",
            (),
        ),
        (
            "SDR-014",
            "婆婆尊重儿媳。",
            "abstract_observation",
            "institutional_account",
            (),
            (),
            ("尊重",),
            (),
            (),
            (),
            (),
            (),
            (),
            (),
            (),
            "generic",
            ("insufficient_evidence",),
        ),
        (
            "SDR-015",
            "饭桌上一句话让两个人都沉默。",
            "abstract_observation",
            "institutional_account",
            (),
            (),
            ("一句话",),
            (),
            (),
            (),
            ("两个人都沉默",),
            (),
            ("饭桌上",),
            (),
            (),
            "generic",
            ("situated_event_in_observation",),
        ),
        (
            "SDR-016",
            "婆婆来帮忙带孩子，儿媳是孩子的妈妈。",
            "abstract_observation",
            "institutional_account",
            ("婆婆",),
            ("来帮忙带孩子",),
            ("来帮忙带孩子",),
            (),
            (),
            (),
            (),
            (),
            (),
            (),
            (),
            "none",
            ("situated_event_in_observation",),
        ),
        (
            "SDR-017",
            "我昨天停下来了。",
            "abstract_observation",
            "personal_ip_account",
            ("我",),
            ("停下来",),
            ("停下来",),
            (),
            (),
            (),
            (),
            ("昨天",),
            (),
            (),
            ("了",),
            "none",
            ("unsupported_actuality_binding",),
        ),
        (
            "SDR-018",
            "婆婆要尊重儿媳。",
            "recommendation",
            "institutional_account",
            ("婆婆",),
            ("尊重",),
            ("尊重",),
            (),
            (),
            (),
            (),
            (),
            (),
            ("要",),
            (),
            "none",
            (),
        ),
        (
            "SDR-019",
            "婆婆尊重儿媳。",
            "recommendation",
            "institutional_account",
            ("婆婆",),
            ("尊重",),
            ("尊重",),
            (),
            (),
            (),
            (),
            (),
            (),
            (),
            (),
            "none",
            ("insufficient_evidence",),
        ),
        (
            "SDR-020",
            "婆婆尊重了儿媳。",
            "recommendation",
            "institutional_account",
            ("婆婆",),
            ("尊重",),
            ("尊重",),
            (),
            (),
            (),
            (),
            (),
            (),
            (),
            ("了",),
            "none",
            ("situated_event_in_recommendation",),
        ),
        (
            "SDR-021",
            "昨天婆婆说“先停一下”。",
            "recommendation",
            "institutional_account",
            ("婆婆",),
            ("说",),
            ("说",),
            ("先停一下",),
            (),
            (),
            (),
            ("昨天",),
            (),
            (),
            (),
            "none",
            ("situated_event_in_recommendation",),
        ),
        (
            "SDR-022",
            "如果婆婆愿意先停一下。",
            "hypothetical_example",
            "institutional_account",
            ("婆婆",),
            ("停",),
            ("停",),
            (),
            (),
            (),
            (),
            (),
            (),
            ("如果", "愿意"),
            (),
            "none",
            (),
        ),
        (
            "SDR-023",
            "如果我家先停一下。",
            "hypothetical_example",
            "personal_ip_account",
            ("我家",),
            ("停",),
            ("停",),
            (),
            (),
            (),
            (),
            (),
            (),
            ("如果",),
            (),
            "none",
            ("unsupported_actuality_binding",),
        ),
        (
            "SDR-024",
            "如果笛语先停一下。",
            "hypothetical_example",
            "institutional_account",
            ("笛语",),
            ("停",),
            ("停",),
            (),
            (),
            (),
            (),
            (),
            (),
            ("如果",),
            (),
            "none",
            ("unsupported_institutional_assertion",),
        ),
        (
            "SDR-025",
            "婆婆说“我先停一下”。",
            "disclosed_dramatization",
            "institutional_account",
            ("婆婆",),
            ("说",),
            ("说",),
            ("我先停一下",),
            (),
            (),
            (),
            (),
            (),
            (),
            (),
            "none",
            (),
        ),
        (
            "SDR-026",
            "我说“我先停一下”。",
            "disclosed_dramatization",
            "personal_ip_account",
            ("我",),
            ("说",),
            ("说",),
            ("我先停一下",),
            (),
            (),
            (),
            (),
            (),
            (),
            (),
            "none",
            ("unsupported_actuality_binding",),
        ),
        (
            "SDR-027",
            "笛语说“我先停一下”。",
            "disclosed_dramatization",
            "institutional_account",
            ("笛语",),
            ("说",),
            ("说",),
            ("我先停一下",),
            (),
            (),
            (),
            (),
            (),
            (),
            (),
            "none",
            ("unsupported_institutional_assertion",),
        ),
        (
            "SDR-028",
            "忙乱之后，边界依然值得被看见。",
            "actuality_reflection",
            "institutional_account",
            (),
            ("值得",),
            (),
            (),
            (),
            (),
            (),
            (),
            (),
            (),
            (),
            "none",
            (),
        ),
        (
            "SDR-029",
            "人可以先停一下再回应。",
            "actuality_reflection",
            "institutional_account",
            (),
            ("停",),
            ("停",),
            (),
            (),
            (),
            (),
            (),
            (),
            ("可以",),
            (),
            "generic",
            (),
        ),
        (
            "SDR-030",
            "我因为委屈最后离开了。",
            "actuality_reflection",
            "personal_ip_account",
            ("我",),
            ("离开",),
            ("离开",),
            (),
            ("委屈",),
            ("因为",),
            ("最后离开",),
            (),
            (),
            (),
            ("了",),
            "none",
            ("unsupported_actuality_expansion",),
        ),
        (
            "SDR-031",
            "笛语相信关系需要边界。",
            "abstract_observation",
            "institutional_account",
            ("笛语",),
            ("相信",),
            (),
            (),
            (),
            (),
            (),
            (),
            (),
            (),
            (),
            "none",
            ("unsupported_institutional_assertion",),
        ),
        (
            "SDR-032",
            "我们应该尊重边界。",
            "recommendation",
            "institutional_account",
            (),
            ("尊重",),
            ("尊重",),
            (),
            (),
            (),
            (),
            (),
            (),
            ("应该",),
            (),
            "current_speaker",
            ("unsupported_institutional_assertion",),
        ),
        (
            "SDR-033",
            "我更想聊换位思考和边界。",
            "abstract_observation",
            "personal_ip_account",
            (),
            ("想聊",),
            (),
            (),
            (),
            (),
            (),
            (),
            (),
            ("想",),
            (),
            "current_speaker",
            (),
        ),
        (
            "SDR-034",
            "我建议先停一下再回应。",
            "recommendation",
            "personal_ip_account",
            (),
            ("建议",),
            ("停",),
            (),
            (),
            (),
            (),
            (),
            (),
            ("建议",),
            (),
            "current_speaker",
            (),
        ),
        (
            "SDR-035",
            "我昨天已经这样做了。",
            "abstract_observation",
            "personal_ip_account",
            (),
            ("做",),
            ("做",),
            (),
            (),
            (),
            (),
            ("昨天",),
            (),
            (),
            ("已经", "了"),
            "current_speaker",
            ("unsupported_actuality_binding",),
        ),
        (
            "SDR-036",
            "我更想聊边界。",
            "abstract_observation",
            "unknown",
            (),
            ("想聊",),
            (),
            (),
            (),
            (),
            (),
            (),
            (),
            ("想",),
            (),
            "current_speaker",
            ("insufficient_evidence",),
        ),
    ),
)
def test_sdr_writer_semantic_matrix(
    sdr_id: str,
    text: str,
    contract: UnitContractV2,
    speaker_kind: SpeakerKind,
    subject: tuple[str, ...],
    predicate: tuple[str, ...],
    action: tuple[str, ...],
    dialogue: tuple[str, ...],
    motive: tuple[str, ...],
    cause: tuple[str, ...],
    result: tuple[str, ...],
    time: tuple[str, ...],
    location: tuple[str, ...],
    modality: tuple[str, ...],
    aspect: tuple[str, ...],
    implicit: Literal[
        "none",
        "current_speaker",
        "generic",
        "uncertain",
    ],
    expected: tuple[str, ...],
) -> None:
    contexts = _manual_context(text, contract, speaker_kind=speaker_kind)
    evidence = _evidence(
        contexts,
        target_fragment=text,
        subject=subject,
        predicate=predicate,
        action=action,
        dialogue=dialogue,
        motive=motive,
        cause=cause,
        result=result,
        time=time,
        location=location,
        modality=modality,
        aspect=aspect,
        implicit_subject=implicit,
    )

    assert _reasons(
        contexts,
        evidence,
        speaker_kind=speaker_kind,
    ) == expected
    assert sdr_id in _ALL_SDR_IDS


@pytest.mark.parametrize(
    ("sdr_id", "mutation", "expected_reason"),
    (
        ("SDR-037", "missing", "review_evidence_coverage"),
        ("SDR-038", "offset", "review_evidence_span"),
        ("SDR-039", "uncertain", "insufficient_evidence"),
    ),
)
def test_sdr_evidence_qualification_failures(
    sdr_id: str,
    mutation: str,
    expected_reason: str,
) -> None:
    contexts = _manual_context(
        "换位思考不等于没有边界。",
        "abstract_observation",
    )
    evidence = _evidence(contexts)
    if mutation == "missing":
        evidence = replace(evidence, clauses=())
    elif mutation == "offset":
        item = replace(
            evidence.clauses[0],
            predicate_spans=(SpanOccurrence("换位思考", 1, 5),),
        )
        evidence = replace(evidence, clauses=(item,))
    else:
        evidence = replace(
            evidence,
            clauses=(replace(evidence.clauses[0], uncertain=True),),
        )

    assert expected_reason in _reasons(contexts, evidence)
    assert sdr_id in _ALL_SDR_IDS


def test_occurrence_aware_parser_distinguishes_repeated_text() -> None:
    text = "先停一下，再停一下。"
    second_start = text.rindex("停")
    evidence = parse_review_evidence_v2(
        {
            "evidence_version": REVIEW_EVIDENCE_V2_VERSION,
            "clauses": [
                {
                    "clause_id": "unit:test:clause:1",
                    "exact_text": text,
                    "subject_spans": [],
                    "predicate_spans": [],
                    "action_or_event_spans": [
                        {"text": "停", "start": 1, "end": 2},
                        {
                            "text": "停",
                            "start": second_start,
                            "end": second_start + 1,
                        },
                    ],
                    "dialogue_spans": [],
                    "motive_spans": [],
                    "cause_spans": [],
                    "result_spans": [],
                    "time_spans": [],
                    "location_spans": [],
                    "grammatical_marker_spans": {
                        "modality": [],
                        "aspect": [],
                    },
                    "implicit_subject": "generic",
                    "uncertain": False,
                }
            ],
        }
    )

    assert tuple(
        span.start for span in evidence.clauses[0].action_or_event_spans
    ) == (1, second_start)


def test_program_contract_sidecar_ignores_kernel_self_reported_type() -> None:
    frame, kernel, contexts = _frame_and_kernel(mode="hypothesis")
    body = kernel.unit("unit:body")
    mutated = replace(
        kernel,
        units=tuple(
            replace(unit, allowed_observation_types=("abstract_principle",))
            if unit.unit_id == body.unit_id
            else unit
            for unit in kernel.units
        ),
    )
    rebuilt = build_clause_contexts_v2(
        kernel=mutated,
        frame=frame,
        fact_registry=(),
        allowed_constraint_ids=_CONSTRAINTS,
        speaker_kind="institutional_account",
    )

    assert {
        context.unit_contract
        for context in contexts
        if context.unit_id == "unit:body"
    } == {"hypothetical_example"}
    assert {
        context.unit_contract
        for context in rebuilt
        if context.unit_id == "unit:body"
    } == {"hypothetical_example"}


def test_every_reachable_program_unit_has_one_trusted_contract() -> None:
    _, _, general = _frame_and_kernel(
        program_id="observation_with_hypothetical_example_v1",
    )
    contracts = {
        context.unit_id: context.unit_contract for context in general
    }
    assert contracts["unit:body-opening"] == "abstract_observation"
    assert contracts["unit:hypothetical-example"] == "hypothetical_example"
    assert contracts["unit:body-closing"] == "recommendation"

    for mode, expected in (
        ("general_observation", "abstract_observation"),
        ("hypothesis", "hypothetical_example"),
        ("dramatization", "disclosed_dramatization"),
    ):
        _, _, contexts = _frame_and_kernel(mode=mode)  # type: ignore[arg-type]
        assert {
            context.unit_contract
            for context in contexts
            if context.unit_id == "unit:body"
        } == {expected}


def test_unknown_program_or_unit_mapping_fails_closed() -> None:
    frame, kernel, _ = _frame_and_kernel()
    unknown_unit = replace(
        kernel,
        units=(
            *kernel.units,
            replace(
                kernel.unit("unit:body"),
                unit_id="unit:unmapped",
                visible_order=999,
            ),
        ),
    )
    with pytest.raises(ValueError, match="no trusted contract mapping"):
        build_clause_contexts_v2(
            kernel=unknown_unit,
            frame=frame,
            fact_registry=(),
            allowed_constraint_ids=_CONSTRAINTS,
            speaker_kind="institutional_account",
        )


def test_insufficient_evidence_is_not_writer_repairable() -> None:
    _, kernel, _ = _frame_and_kernel()
    with pytest.raises(
        GenerationFailed,
        match="Reviewer 证据不完整或事实单元不一致",
    ):
        DeepSeekGenerator._kernel_repair_scope(
            kernel,
            (
                NarrativeIssue(
                    "unit:body",
                    "insufficient_evidence",
                    "婆婆尊重儿媳。",
                ),
            ),
        )


def test_sdr_matrix_has_one_direct_consumer_for_every_stable_id() -> None:
    semantic_ids = {
        f"SDR-{index:03d}" for index in range(12, 37)
    }
    source_ids = {f"SDR-{index:03d}" for index in range(1, 12)}
    evidence_ids = {"SDR-037", "SDR-038", "SDR-039"}
    compiler_ids = {"SDR-040", "SDR-041", "SDR-042"}

    assert source_ids | semantic_ids | evidence_ids | compiler_ids == (
        _ALL_SDR_IDS
    )
