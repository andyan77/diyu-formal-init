from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, TypeAlias, cast

from src.shared.creative_kernel import (
    DRAMATIZATION_DISCLOSURE,
    HYPOTHESIS_DISCLOSURE,
    CreativeKernelV1,
)
from src.shared.narrative import NarrativeIssue

ImplicitSubject: TypeAlias = Literal[
    "none",
    "current_speaker",
    "generic",
    "uncertain",
]

REVIEW_EVIDENCE_VERSION = "review-evidence-v1"
_IMPLICIT_SUBJECTS = frozenset(
    {"none", "current_speaker", "generic", "uncertain"}
)
_CLAUSE_ENDINGS = frozenset("。！？；.!?;\n")
_INSTITUTIONAL_SELF_REFERENCES = frozenset(
    {"我们", "本品牌", "本公司", "本店", "本账号", "当前表达方"}
)
_INSTITUTIONAL_DESIGNATORS = frozenset(
    {"品牌", "公司", "门店", "账号", "组织", "企业", "集团"}
)


@dataclass(frozen=True)
class ReviewClause:
    unit_id: str
    clause_id: str
    exact_text: str
    visible_order: int


@dataclass(frozen=True)
class ClauseEvidence:
    clause_id: str
    exact_text: str
    subject_spans: tuple[str, ...]
    predicate_spans: tuple[str, ...]
    action_or_event_spans: tuple[str, ...]
    dialogue_spans: tuple[str, ...]
    motive_spans: tuple[str, ...]
    cause_spans: tuple[str, ...]
    result_spans: tuple[str, ...]
    time_spans: tuple[str, ...]
    location_spans: tuple[str, ...]
    implicit_subject: ImplicitSubject
    uncertain: bool

    @property
    def all_spans(self) -> tuple[str, ...]:
        return (
            *self.subject_spans,
            *self.predicate_spans,
            *self.action_or_event_spans,
            *self.dialogue_spans,
            *self.motive_spans,
            *self.cause_spans,
            *self.result_spans,
            *self.time_spans,
            *self.location_spans,
        )

    @property
    def event_spans(self) -> tuple[str, ...]:
        return (
            *self.action_or_event_spans,
            *self.dialogue_spans,
            *self.motive_spans,
            *self.cause_spans,
            *self.result_spans,
        )


@dataclass(frozen=True)
class ReviewEvidenceV1:
    evidence_version: str
    clauses: tuple[ClauseEvidence, ...]


@dataclass(frozen=True)
class ProtectedSubjectScope:
    exact_names: tuple[str, ...]
    current_speaker_is_institutional: bool


def build_review_clauses(kernel: CreativeKernelV1) -> tuple[ReviewClause, ...]:
    clauses: list[ReviewClause] = []
    for unit in kernel.units:
        parts = _split_visible_text(unit.text)
        for index, exact_text in enumerate(parts, start=1):
            clauses.append(
                ReviewClause(
                    unit_id=unit.unit_id,
                    clause_id=f"{unit.unit_id}:clause:{index}",
                    exact_text=exact_text,
                    visible_order=unit.visible_order * 1000 + index,
                )
            )
    return tuple(clauses)


def parse_review_evidence(value: object) -> ReviewEvidenceV1:
    if not isinstance(value, Mapping) or frozenset(value) != {
        "evidence_version",
        "clauses",
    }:
        raise TypeError("review evidence root is invalid")
    raw_clauses = value.get("clauses")
    if (
        value.get("evidence_version") != REVIEW_EVIDENCE_VERSION
        or not isinstance(raw_clauses, list)
    ):
        raise TypeError("review evidence version is invalid")
    clauses: list[ClauseEvidence] = []
    required = frozenset(
        {
            "clause_id",
            "exact_text",
            "subject_spans",
            "predicate_spans",
            "action_or_event_spans",
            "dialogue_spans",
            "motive_spans",
            "cause_spans",
            "result_spans",
            "time_spans",
            "location_spans",
            "implicit_subject",
            "uncertain",
        }
    )
    for raw in raw_clauses:
        if not isinstance(raw, Mapping) or frozenset(raw) != required:
            raise TypeError("review evidence clause is invalid")
        implicit_subject = raw.get("implicit_subject")
        uncertain = raw.get("uncertain")
        if (
            not isinstance(implicit_subject, str)
            or implicit_subject not in _IMPLICIT_SUBJECTS
            or not isinstance(uncertain, bool)
        ):
            raise TypeError("review evidence clause fields are invalid")
        clauses.append(
            ClauseEvidence(
                clause_id=_required_string(raw.get("clause_id")),
                exact_text=_required_string(raw.get("exact_text")),
                subject_spans=_string_tuple(raw.get("subject_spans")),
                predicate_spans=_string_tuple(raw.get("predicate_spans")),
                action_or_event_spans=_string_tuple(
                    raw.get("action_or_event_spans")
                ),
                dialogue_spans=_string_tuple(raw.get("dialogue_spans")),
                motive_spans=_string_tuple(raw.get("motive_spans")),
                cause_spans=_string_tuple(raw.get("cause_spans")),
                result_spans=_string_tuple(raw.get("result_spans")),
                time_spans=_string_tuple(raw.get("time_spans")),
                location_spans=_string_tuple(raw.get("location_spans")),
                implicit_subject=cast(ImplicitSubject, implicit_subject),
                uncertain=uncertain,
            )
        )
    return ReviewEvidenceV1(
        evidence_version=REVIEW_EVIDENCE_VERSION,
        clauses=tuple(clauses),
    )


def reconcile_review_evidence(
    *,
    kernel: CreativeKernelV1,
    review_clauses: Sequence[ReviewClause],
    evidence: ReviewEvidenceV1,
    fact_text_by_id: Mapping[str, str],
    allowed_constraint_ids: frozenset[str],
    protected_subjects: ProtectedSubjectScope,
) -> tuple[NarrativeIssue, ...]:
    issues: list[NarrativeIssue] = []
    expected = {clause.clause_id: clause for clause in review_clauses}
    units = {unit.unit_id: unit for unit in kernel.units}
    received: dict[str, ClauseEvidence] = {}

    for item in evidence.clauses:
        clause = expected.get(item.clause_id)
        if clause is None or item.clause_id in received:
            issues.append(
                NarrativeIssue(
                    item.clause_id,
                    "review_evidence_coverage",
                    item.clause_id,
                )
            )
            continue
        received[item.clause_id] = item
        if item.exact_text != clause.exact_text:
            issues.append(
                NarrativeIssue(
                    clause.unit_id,
                    "review_evidence_coverage",
                    item.exact_text,
                )
            )
            continue
        invalid_span = next(
            (span for span in item.all_spans if span not in clause.exact_text),
            None,
        )
        if invalid_span is not None:
            issues.append(
                NarrativeIssue(
                    clause.unit_id,
                    "review_evidence_span",
                    invalid_span,
                )
            )
        if item.uncertain or item.implicit_subject == "uncertain":
            issues.append(
                NarrativeIssue(
                    clause.unit_id,
                    "review_evidence_uncertain",
                    clause.exact_text,
                )
            )

    for missing_id in set(expected) - set(received):
        clause = expected[missing_id]
        issues.append(
            NarrativeIssue(
                clause.unit_id,
                "review_evidence_coverage",
                clause.clause_id,
            )
        )
    if issues:
        return tuple(dict.fromkeys(issues))

    for unit in kernel.units:
        if unit.purpose == "frozen_fact":
            exact = {
                fact_text_by_id[ref]
                for ref in unit.fact_refs
                if ref in fact_text_by_id
            }
            if (
                len(unit.fact_refs) != 1
                or unit.text not in exact
                or unit.constraint_refs
            ):
                issues.append(
                    NarrativeIssue(
                        unit.unit_id,
                        "frozen_fact_changed",
                        unit.text,
                    )
                )
        elif unit.fact_refs:
            issues.append(
                NarrativeIssue(
                    unit.unit_id,
                    "writer_fact_binding",
                    unit.text,
                )
            )
        if any(
            ref not in allowed_constraint_ids for ref in unit.constraint_refs
        ):
            issues.append(
                NarrativeIssue(
                    unit.unit_id,
                    "unknown_constraint_ref",
                    unit.text,
                )
            )
        if unit.allowed_observation_types == ("dramatization",) and not (
            unit.text.startswith(DRAMATIZATION_DISCLOSURE)
        ):
            issues.append(
                NarrativeIssue(
                    unit.unit_id,
                    "dramatization_not_visible",
                    unit.text,
                )
            )
        if unit.allowed_observation_types == ("hypothesis",) and not (
            unit.text.startswith(HYPOTHESIS_DISCLOSURE)
        ):
            issues.append(
                NarrativeIssue(
                    unit.unit_id,
                    "hypothesis_not_visible",
                    unit.text,
                )
            )

    by_unit: dict[str, list[ClauseEvidence]] = {
        unit_id: [] for unit_id in units
    }
    for clause_id, item in received.items():
        by_unit[expected[clause_id].unit_id].append(item)
    for unit in kernel.units:
        if unit.purpose == "frozen_fact":
            continue
        for item in by_unit[unit.unit_id]:
            if _has_unsupported_institutional_assertion(
                item,
                protected_subjects,
            ):
                issues.append(
                    NarrativeIssue(
                        unit.unit_id,
                        "unsupported_institutional_assertion",
                        item.exact_text,
                    )
                )
                continue
            if (
                unit.allowed_observation_types == ("abstract_principle",)
                and item.event_spans
            ):
                issues.append(
                    NarrativeIssue(
                        unit.unit_id,
                        "situated_event_in_observation",
                        item.event_spans[0],
                    )
                )
    return tuple(dict.fromkeys(issues))


def _split_visible_text(text: str) -> tuple[str, ...]:
    if not text:
        raise ValueError("reviewed unit text cannot be empty")
    parts: list[str] = []
    start = 0
    for index, character in enumerate(text):
        if character in _CLAUSE_ENDINGS:
            part = text[start : index + 1]
            if any(
                value not in _CLAUSE_ENDINGS and not value.isspace()
                for value in part
            ):
                parts.append(part)
            elif parts:
                parts[-1] += part
            start = index + 1
    if start < len(text):
        tail = text[start:]
        if tail.strip() or not parts:
            parts.append(tail)
        else:
            parts[-1] += tail
    return tuple(part for part in parts if part)


def _has_unsupported_institutional_assertion(
    evidence: ClauseEvidence,
    protected_subjects: ProtectedSubjectScope,
) -> bool:
    if not evidence.predicate_spans:
        return False
    exact_subjects = {
        name for name in protected_subjects.exact_names if name
    }
    if any(name in evidence.exact_text for name in exact_subjects):
        return True
    if any(
        subject in exact_subjects
        or subject in _INSTITUTIONAL_SELF_REFERENCES
        or any(
            designator in subject
            for designator in _INSTITUTIONAL_DESIGNATORS
        )
        for subject in evidence.subject_spans
    ):
        return True
    return (
        protected_subjects.current_speaker_is_institutional
        and evidence.implicit_subject == "current_speaker"
    )


def _required_string(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise TypeError("review evidence string is invalid")
    return value


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise TypeError("review evidence spans are invalid")
    values = cast(list[str], value)
    if len(values) != len(set(values)):
        raise TypeError("review evidence spans are duplicated")
    return tuple(values)
