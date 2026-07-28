from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, TypeAlias, cast

from src.shared.creative_kernel import (
    DRAMATIZATION_DISCLOSURE,
    HYPOTHESIS_DISCLOSURE,
    OBSERVATION_ONLY_PROGRAM,
    OBSERVATION_WITH_HYPOTHETICAL_EXAMPLE_PROGRAM,
    CreativeKernelV1,
)
from src.shared.factual_basis import FrozenFactRecord
from src.shared.narrative import NarrativeFrame, NarrativeIssue
from src.shared.types import SpeakerKind

ImplicitSubject: TypeAlias = Literal[
    "none",
    "current_speaker",
    "generic",
    "uncertain",
]

REVIEW_EVIDENCE_VERSION = "review-evidence-v1"
REVIEW_EVIDENCE_V2_VERSION = "review-evidence-v2"
REVIEW_EVIDENCE_V2_TOOL_NAME = "submit_review_evidence_v2"
_IMPLICIT_SUBJECTS = frozenset(
    {"none", "current_speaker", "generic", "uncertain"}
)
_CLAUSE_ENDINGS = frozenset("。！？；.!?;\n")
_QUOTE_CANDIDATE_BOUNDARIES = frozenset("，,、：:；;。！？.!?\n")
_INSTITUTIONAL_SELF_REFERENCES = frozenset(
    {"我们", "本品牌", "本公司", "本店", "本账号", "当前表达方"}
)
_INSTITUTIONAL_DESIGNATORS = frozenset(
    {"品牌", "公司", "门店", "账号", "组织", "企业", "集团"}
)
_CURRENT_REALITY_PREFIXES = (
    "我家",
    "我们家",
    "本店",
    "我们店",
    "店里",
    "真实员工",
    "真实顾客",
    "门店历史",
    "现实中",
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


TextSourceV2: TypeAlias = Literal[
    "server_wrapper",
    "frozen_user_fact",
    "frozen_brand_fact",
    "frozen_product_fact",
    "writer_unit",
]
UnitContractV2: TypeAlias = Literal[
    "abstract_observation",
    "recommendation",
    "hypothetical_example",
    "disclosed_dramatization",
    "actuality_reflection",
    "frozen_fact",
]
SubjectBindingV2: TypeAlias = Literal[
    "none",
    "generic",
    "fictional_role",
    "current_person",
    "current_institution",
    "protected_exact_subject",
    "uncertain",
]


@dataclass(frozen=True)
class ClauseContextV2:
    clause_id: str
    unit_id: str
    exact_text: str
    visible_order: int
    text_source: TextSourceV2
    unit_contract: UnitContractV2
    speaker_kind: SpeakerKind
    fact_ref: str | None = None


@dataclass(frozen=True)
class SpanOccurrence:
    text: str
    start: int
    end: int


@dataclass(frozen=True)
class GrammaticalMarkerSpans:
    modality: tuple[SpanOccurrence, ...]
    aspect: tuple[SpanOccurrence, ...]


@dataclass(frozen=True)
class ClauseEvidenceV2:
    clause_id: str
    exact_text: str
    subject_spans: tuple[SpanOccurrence, ...]
    predicate_spans: tuple[SpanOccurrence, ...]
    action_or_event_spans: tuple[SpanOccurrence, ...]
    dialogue_spans: tuple[SpanOccurrence, ...]
    motive_spans: tuple[SpanOccurrence, ...]
    cause_spans: tuple[SpanOccurrence, ...]
    result_spans: tuple[SpanOccurrence, ...]
    time_spans: tuple[SpanOccurrence, ...]
    location_spans: tuple[SpanOccurrence, ...]
    grammatical_marker_spans: GrammaticalMarkerSpans
    implicit_subject: ImplicitSubject
    uncertain: bool

    @property
    def all_spans(self) -> tuple[SpanOccurrence, ...]:
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
            *self.grammatical_marker_spans.modality,
            *self.grammatical_marker_spans.aspect,
        )

    @property
    def event_spans(self) -> tuple[SpanOccurrence, ...]:
        return (
            *self.action_or_event_spans,
            *self.dialogue_spans,
            *self.motive_spans,
            *self.cause_spans,
            *self.result_spans,
        )


@dataclass(frozen=True)
class ReviewEvidenceV2:
    evidence_version: str
    clauses: tuple[ClauseEvidenceV2, ...]


@dataclass(frozen=True)
class ProtectedSubjectScopeV2:
    exact_names: tuple[str, ...]
    speaker_kind: SpeakerKind


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


def build_clause_contexts_v2(
    *,
    kernel: CreativeKernelV1,
    frame: NarrativeFrame,
    fact_registry: Sequence[FrozenFactRecord],
    allowed_constraint_ids: frozenset[str],
    speaker_kind: SpeakerKind,
) -> tuple[ClauseContextV2, ...]:
    """Build the only trusted source/contract sidecar for a new kernel review."""
    contracts = unit_contracts_v2(kernel, frame)
    fact_by_id = {record.fact_id: record for record in fact_registry}
    contexts: list[ClauseContextV2] = []
    for unit in kernel.units:
        contract = contracts[unit.unit_id]
        if any(
            ref not in allowed_constraint_ids for ref in unit.constraint_refs
        ):
            raise ValueError("kernel unit constraint source drifted")
        parts = _split_visible_text(unit.text)
        fact_ref: str | None = None
        fact_source: TextSourceV2 | None = None
        if contract == "frozen_fact":
            if len(unit.fact_refs) != 1 or unit.constraint_refs:
                raise ValueError("frozen fact unit structure drifted")
            fact_ref = unit.fact_refs[0]
            record = fact_by_id.get(fact_ref)
            if record is None or unit.text != record.exact_text:
                raise ValueError("frozen fact unit source drifted")
            if record.fact_kind == "user_actuality":
                fact_source = "frozen_user_fact"
            elif record.fact_kind == "brand":
                fact_source = "frozen_brand_fact"
            else:
                fact_source = "frozen_product_fact"
        elif unit.fact_refs:
            raise ValueError("writer-owned unit cannot carry fact refs")

        wrapper: str | None = None
        if contract == "hypothetical_example":
            wrapper = f"{HYPOTHESIS_DISCLOSURE}\n"
        elif contract == "disclosed_dramatization":
            wrapper = f"{DRAMATIZATION_DISCLOSURE}\n"
        if wrapper is not None and (not parts or parts[0] != wrapper):
            raise ValueError("server wrapper structure drifted")

        for index, exact_text in enumerate(parts, start=1):
            if fact_source is not None:
                source = fact_source
            elif wrapper is not None and index == 1:
                source = "server_wrapper"
            else:
                source = "writer_unit"
            if (
                source == "writer_unit"
                and exact_text.strip()
                in {HYPOTHESIS_DISCLOSURE, DRAMATIZATION_DISCLOSURE}
            ):
                raise ValueError("writer forged a server wrapper")
            contexts.append(
                ClauseContextV2(
                    clause_id=f"{unit.unit_id}:clause:{index}",
                    unit_id=unit.unit_id,
                    exact_text=exact_text,
                    visible_order=unit.visible_order * 1000 + index,
                    text_source=source,
                    unit_contract=contract,
                    speaker_kind=speaker_kind,
                    fact_ref=fact_ref,
                )
            )
    identifiers = [context.clause_id for context in contexts]
    orders = [context.visible_order for context in contexts]
    if (
        len(identifiers) != len(set(identifiers))
        or len(orders) != len(set(orders))
        or orders != sorted(orders)
    ):
        raise ValueError("clause context coverage or order drifted")
    return tuple(contexts)


def review_clauses_from_contexts(
    contexts: Sequence[ClauseContextV2],
) -> tuple[ReviewClause, ...]:
    return tuple(
        ReviewClause(
            unit_id=context.unit_id,
            clause_id=context.clause_id,
            exact_text=context.exact_text,
            visible_order=context.visible_order,
        )
        for context in contexts
    )


def clause_context_document(
    contexts: Sequence[ClauseContextV2],
) -> list[dict[str, object]]:
    return [
        {
            "clause_id": context.clause_id,
            "unit_id": context.unit_id,
            "exact_text": context.exact_text,
            "visible_order": context.visible_order,
            "text_source": context.text_source,
            "unit_contract": context.unit_contract,
            "speaker_kind": context.speaker_kind,
            "fact_ref": context.fact_ref,
        }
        for context in contexts
    ]


def writer_clause_contexts_v2(
    contexts: Sequence[ClauseContextV2],
) -> tuple[ClauseContextV2, ...]:
    """Return the only clauses whose semantics require model evidence."""
    return tuple(
        context
        for context in contexts
        if context.text_source == "writer_unit"
    )


def validate_server_owned_contexts_v2(
    *,
    contexts: Sequence[ClauseContextV2],
    fact_text_by_id: Mapping[str, str],
) -> tuple[NarrativeIssue, ...]:
    """Validate wrappers and facts without delegating their authority."""
    issues: list[NarrativeIssue] = []
    fact_contexts: dict[str, list[ClauseContextV2]] = {}
    for context in contexts:
        if context.text_source == "writer_unit":
            if context.fact_ref is not None:
                issues.append(
                    NarrativeIssue(
                        context.unit_id,
                        "frozen_fact_changed",
                        context.exact_text,
                    )
                )
            continue
        if context.text_source == "server_wrapper":
            if (
                context.fact_ref is not None
                or not _valid_server_wrapper(context)
            ):
                issues.append(
                    NarrativeIssue(
                        context.unit_id,
                        "server_wrapper_drift",
                        context.exact_text,
                    )
                )
            continue
        if (
            context.text_source
            not in {
                "frozen_user_fact",
                "frozen_brand_fact",
                "frozen_product_fact",
            }
            or context.unit_contract != "frozen_fact"
            or context.fact_ref is None
        ):
            issues.append(
                NarrativeIssue(
                    context.unit_id,
                    "frozen_fact_changed",
                    context.exact_text,
                )
            )
            continue
        fact_contexts.setdefault(context.unit_id, []).append(context)

    for unit_id, unit_contexts in fact_contexts.items():
        fact_refs = {context.fact_ref for context in unit_contexts}
        fact_ref = next(iter(fact_refs)) if len(fact_refs) == 1 else None
        exact_text = "".join(
            context.exact_text
            for context in sorted(
                unit_contexts,
                key=lambda item: item.visible_order,
            )
        )
        if (
            fact_ref is None
            or fact_text_by_id.get(fact_ref) != exact_text
        ):
            issues.append(
                NarrativeIssue(
                    unit_id,
                    "frozen_fact_changed",
                    exact_text,
                )
            )
    return tuple(dict.fromkeys(issues))


def unique_review_quote_candidates(
    exact_texts: Sequence[str],
) -> tuple[str, ...]:
    """Build a small server-owned vocabulary of uniquely bindable quotes."""
    candidates: list[str] = []
    for exact_text in exact_texts:
        chunks: list[str] = []
        start = 0
        for index, character in enumerate(exact_text):
            if character in _QUOTE_CANDIDATE_BOUNDARIES:
                chunk = exact_text[start : index + 1]
                if chunk.strip():
                    chunks.append(chunk)
                start = index + 1
        tail = exact_text[start:]
        if tail.strip():
            chunks.append(tail)
        if not chunks:
            chunks.append(exact_text)
        for index, chunk in enumerate(chunks):
            if len(_exact_match_starts(exact_text, chunk)) == 1:
                candidates.append(chunk)
                continue
            resolved: str | None = None
            for width in range(2, len(chunks) + 1):
                windows = (
                    "".join(chunks[window_start : window_start + width])
                    for window_start in range(
                        max(0, index - width + 1),
                        min(index, len(chunks) - width) + 1,
                    )
                )
                resolved = next(
                    (
                        window
                        for window in windows
                        if len(_exact_match_starts(exact_text, window)) == 1
                    ),
                    None,
                )
                if resolved is not None:
                    break
            candidates.append(resolved or exact_text)
    return tuple(dict.fromkeys(candidates))


def review_evidence_v2_json_schema(
    allowed_quotes: Sequence[str] = (),
) -> dict[str, object]:
    """Return the strict function schema for ReviewEvidenceV2."""
    text_schema: dict[str, object] = {
        "type": "string",
        "description": (
            "Exact evidence text copied from the selected context_quote; "
            "never return an address or index."
        ),
    }
    context_schema: dict[str, object] = {
        "type": "string",
        "description": (
            "Server-provided exact context quote that occurs once in the "
            "source clause and contains this evidence text exactly once."
        ),
    }
    unique_quotes = tuple(dict.fromkeys(allowed_quotes))
    if unique_quotes:
        context_schema["enum"] = list(unique_quotes)
    span_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "text": text_schema,
            "context_quote": context_schema,
        },
        "required": ["text", "context_quote"],
        "additionalProperties": False,
    }

    def span_array() -> dict[str, object]:
        return {"type": "array", "items": span_schema}

    marker_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "modality": span_array(),
            "aspect": span_array(),
        },
        "required": ["modality", "aspect"],
        "additionalProperties": False,
    }
    clause_properties: dict[str, object] = {
        "clause_id": {"type": "string"},
        "exact_text": {"type": "string"},
        "subject_spans": span_array(),
        "predicate_spans": span_array(),
        "action_or_event_spans": span_array(),
        "dialogue_spans": span_array(),
        "motive_spans": span_array(),
        "cause_spans": span_array(),
        "result_spans": span_array(),
        "time_spans": span_array(),
        "location_spans": span_array(),
        "grammatical_marker_spans": marker_schema,
        "implicit_subject": {
            "type": "string",
            "enum": [
                "none",
                "current_speaker",
                "generic",
                "uncertain",
            ],
        },
        "uncertain": {"type": "boolean"},
    }
    clause_schema: dict[str, object] = {
        "type": "object",
        "properties": clause_properties,
        "required": list(clause_properties),
        "additionalProperties": False,
    }
    root_properties: dict[str, object] = {
        "evidence_version": {
            "type": "string",
            "enum": [REVIEW_EVIDENCE_V2_VERSION],
        },
        "clauses": {
            "type": "array",
            "items": clause_schema,
        },
    }
    return {
        "type": "object",
        "properties": root_properties,
        "required": list(root_properties),
        "additionalProperties": False,
    }


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


def parse_review_evidence_v2(
    value: object,
    *,
    clause_text_by_id: Mapping[str, str],
) -> ReviewEvidenceV2:
    if not isinstance(value, Mapping) or frozenset(value) != {
        "evidence_version",
        "clauses",
    }:
        raise TypeError("review evidence v2 root is invalid")
    raw_clauses = value.get("clauses")
    if (
        value.get("evidence_version") != REVIEW_EVIDENCE_V2_VERSION
        or not isinstance(raw_clauses, list)
    ):
        raise TypeError("review evidence v2 version is invalid")
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
            "grammatical_marker_spans",
            "implicit_subject",
            "uncertain",
        }
    )
    clauses: list[ClauseEvidenceV2] = []
    for raw in raw_clauses:
        if not isinstance(raw, Mapping) or frozenset(raw) != required:
            raise TypeError("review evidence v2 clause is invalid")
        clause_id = _required_string(raw.get("clause_id"))
        exact_text = _required_string(raw.get("exact_text"))
        trusted_text = clause_text_by_id.get(clause_id)
        if trusted_text is None or exact_text != trusted_text:
            raise TypeError("review evidence v2 clause text is invalid")
        markers = raw.get("grammatical_marker_spans")
        if not isinstance(markers, Mapping) or frozenset(markers) != {
            "modality",
            "aspect",
        }:
            raise TypeError("review evidence v2 markers are invalid")
        implicit_subject = raw.get("implicit_subject")
        uncertain = raw.get("uncertain")
        if (
            not isinstance(implicit_subject, str)
            or implicit_subject not in _IMPLICIT_SUBJECTS
            or not isinstance(uncertain, bool)
        ):
            raise TypeError("review evidence v2 clause fields are invalid")
        clauses.append(
            ClauseEvidenceV2(
                clause_id=clause_id,
                exact_text=exact_text,
                subject_spans=_quote_tuple(
                    raw.get("subject_spans"),
                    exact_text=trusted_text,
                ),
                predicate_spans=_quote_tuple(
                    raw.get("predicate_spans"),
                    exact_text=trusted_text,
                ),
                action_or_event_spans=_quote_tuple(
                    raw.get("action_or_event_spans"),
                    exact_text=trusted_text,
                ),
                dialogue_spans=_quote_tuple(
                    raw.get("dialogue_spans"),
                    exact_text=trusted_text,
                ),
                motive_spans=_quote_tuple(
                    raw.get("motive_spans"),
                    exact_text=trusted_text,
                ),
                cause_spans=_quote_tuple(
                    raw.get("cause_spans"),
                    exact_text=trusted_text,
                ),
                result_spans=_quote_tuple(
                    raw.get("result_spans"),
                    exact_text=trusted_text,
                ),
                time_spans=_quote_tuple(
                    raw.get("time_spans"),
                    exact_text=trusted_text,
                ),
                location_spans=_quote_tuple(
                    raw.get("location_spans"),
                    exact_text=trusted_text,
                ),
                grammatical_marker_spans=GrammaticalMarkerSpans(
                    modality=_quote_tuple(
                        markers.get("modality"),
                        exact_text=trusted_text,
                    ),
                    aspect=_quote_tuple(
                        markers.get("aspect"),
                        exact_text=trusted_text,
                    ),
                ),
                implicit_subject=cast(ImplicitSubject, implicit_subject),
                uncertain=uncertain,
            )
        )
    return ReviewEvidenceV2(
        evidence_version=REVIEW_EVIDENCE_V2_VERSION,
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
    issues.extend(_kernel_program_issues(kernel))
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
                unit.allowed_observation_types == ("hypothesis",)
                and _has_unsupported_actuality_binding(item)
            ):
                issues.append(
                    NarrativeIssue(
                        unit.unit_id,
                        "unsupported_actuality_binding",
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


def reconcile_review_evidence_v2(
    *,
    contexts: Sequence[ClauseContextV2],
    evidence: ReviewEvidenceV2,
    fact_text_by_id: Mapping[str, str],
    protected_subjects: ProtectedSubjectScopeV2,
) -> tuple[NarrativeIssue, ...]:
    """Apply ADR-028 without trusting model-authored semantic labels."""
    issues = list(
        validate_server_owned_contexts_v2(
            contexts=contexts,
            fact_text_by_id=fact_text_by_id,
        )
    )
    if issues:
        return tuple(dict.fromkeys(issues))
    writer_contexts = writer_clause_contexts_v2(contexts)
    expected = {context.clause_id: context for context in writer_contexts}
    received: dict[str, ClauseEvidenceV2] = {}
    expected_order = tuple(
        context.clause_id for context in writer_contexts
    )
    received_order = tuple(item.clause_id for item in evidence.clauses)
    if received_order != expected_order:
        issues.append(
            NarrativeIssue(
                "review-evidence",
                "review_evidence_coverage",
                "clause_order_or_coverage",
            )
        )
    for item in evidence.clauses:
        context = expected.get(item.clause_id)
        if context is None or item.clause_id in received:
            issues.append(
                NarrativeIssue(
                    item.clause_id,
                    "review_evidence_coverage",
                    item.clause_id,
                )
            )
            continue
        received[item.clause_id] = item
        if item.exact_text != context.exact_text:
            issues.append(
                NarrativeIssue(
                    context.unit_id,
                    "review_evidence_coverage",
                    item.exact_text,
                )
            )
            continue
        invalid = next(
            (
                span
                for span in item.all_spans
                if span.start < 0
                or span.end <= span.start
                or span.end > len(context.exact_text)
                or context.exact_text[span.start : span.end] != span.text
            ),
            None,
        )
        if invalid is not None:
            issues.append(
                NarrativeIssue(
                    context.unit_id,
                    "review_evidence_span",
                    invalid.text,
                )
            )
        if item.uncertain or item.implicit_subject == "uncertain":
            issues.append(
                NarrativeIssue(
                    context.unit_id,
                    "insufficient_evidence",
                    context.exact_text,
                )
            )
    for missing_id in set(expected) - set(received):
        issues.append(
            NarrativeIssue(
                expected[missing_id].unit_id,
                "review_evidence_coverage",
                missing_id,
            )
        )
    if issues:
        return tuple(dict.fromkeys(issues))

    for context in writer_contexts:
        item = received[context.clause_id]
        binding = _subject_binding_v2(
            context,
            item,
            protected_subjects,
        )
        if binding == "uncertain":
            issues.append(
                NarrativeIssue(
                    context.unit_id,
                    "insufficient_evidence",
                    context.exact_text,
                )
            )
            continue
        issue = _writer_clause_issue(context, item, binding)
        if issue is not None:
            issues.append(issue)
    return tuple(dict.fromkeys(issues))


def unit_contracts_v2(
    kernel: CreativeKernelV1,
    frame: NarrativeFrame,
) -> dict[str, UnitContractV2]:
    contracts: dict[str, UnitContractV2] = {
        "unit:title": "abstract_observation",
        "unit:natural-guide": "abstract_observation",
        "unit:release-caption": "abstract_observation",
    }
    fact_units = tuple(
        unit for unit in kernel.units if unit.purpose == "frozen_fact"
    )
    for index, unit in enumerate(fact_units, start=1):
        if unit.unit_id != f"unit:frozen-fact:{index}":
            raise ValueError("frozen fact unit mapping is incomplete")
        contracts[unit.unit_id] = "frozen_fact"
    if {
        ref for unit in fact_units for ref in unit.fact_refs
    } != set(frame.allowed_fact_ids):
        raise ValueError("frozen fact unit mapping drifted from frame")

    if kernel.program_id == OBSERVATION_WITH_HYPOTHETICAL_EXAMPLE_PROGRAM:
        if frame.narrative_mode != "general_observation" or fact_units:
            raise ValueError("hypothetical example program drifted from frame")
        contracts.update(
            {
                "unit:body-opening": "abstract_observation",
                "unit:hypothetical-example": "hypothetical_example",
                "unit:body-closing": "recommendation",
            }
        )
    elif kernel.program_id == OBSERVATION_ONLY_PROGRAM:
        body_contract: UnitContractV2
        if frame.narrative_mode == "actuality_reflection":
            body_contract = "actuality_reflection"
        elif frame.narrative_mode == "hypothesis":
            body_contract = "hypothetical_example"
        elif frame.narrative_mode == "dramatization":
            body_contract = "disclosed_dramatization"
        else:
            body_contract = "abstract_observation"
        contracts["unit:body"] = body_contract
    else:
        raise ValueError("kernel program has no trusted contract mapping")

    units = {unit.unit_id: unit for unit in kernel.units}
    if set(units) != set(contracts):
        raise ValueError("kernel unit has no trusted contract mapping")
    expected_purpose = {
        "unit:title": "title",
        "unit:natural-guide": "natural_guide",
        "unit:release-caption": "release_caption",
    }
    for unit_id, unit in units.items():
        purpose = expected_purpose.get(
            unit_id,
            "frozen_fact" if unit_id.startswith("unit:frozen-fact:") else "body",
        )
        if unit.purpose != purpose:
            raise ValueError("kernel unit purpose drifted from trusted mapping")
    return contracts


def _valid_server_wrapper(context: ClauseContextV2) -> bool:
    expected = (
        f"{HYPOTHESIS_DISCLOSURE}\n"
        if context.unit_contract == "hypothetical_example"
        else f"{DRAMATIZATION_DISCLOSURE}\n"
        if context.unit_contract == "disclosed_dramatization"
        else ""
    )
    return bool(expected) and context.exact_text == expected


def _subject_binding_v2(
    context: ClauseContextV2,
    evidence: ClauseEvidenceV2,
    protected_subjects: ProtectedSubjectScopeV2,
) -> SubjectBindingV2:
    exact_names = tuple(name for name in protected_subjects.exact_names if name)
    if any(name in context.exact_text for name in exact_names):
        return "protected_exact_subject"
    subjects = tuple(span.text for span in evidence.subject_spans)
    locations = tuple(span.text for span in evidence.location_spans)
    if any(
        any(designator in subject for designator in _INSTITUTIONAL_DESIGNATORS)
        for subject in subjects
    ):
        return "current_institution"
    self_referenced = any(
        reference in subject
        for subject in subjects
        for reference in _INSTITUTIONAL_SELF_REFERENCES
    )
    if self_referenced:
        if protected_subjects.speaker_kind == "institutional_account":
            return "current_institution"
        if protected_subjects.speaker_kind == "personal_ip_account":
            return (
                "current_person"
                if any("我" in subject for subject in subjects)
                else "uncertain"
            )
        return "uncertain"
    if any(
        span == "我"
        or any(prefix in span for prefix in _CURRENT_REALITY_PREFIXES)
        for span in (*subjects, *locations)
    ):
        return "current_person"
    if evidence.implicit_subject == "current_speaker":
        if protected_subjects.speaker_kind == "institutional_account":
            return "current_institution"
        if protected_subjects.speaker_kind == "personal_ip_account":
            return "current_person"
        return "uncertain"
    if evidence.implicit_subject == "generic":
        return (
            "fictional_role"
            if context.unit_contract
            in {"hypothetical_example", "disclosed_dramatization"}
            else "generic"
        )
    if subjects:
        if evidence.action_or_event_spans:
            return "fictional_role"
        return (
            "fictional_role"
            if context.unit_contract
            in {"hypothetical_example", "disclosed_dramatization"}
            else "generic"
        )
    return "none"


def _writer_clause_issue(
    context: ClauseContextV2,
    evidence: ClauseEvidenceV2,
    binding: SubjectBindingV2,
) -> NarrativeIssue | None:
    if (
        binding in {"current_institution", "protected_exact_subject"}
        and evidence.predicate_spans
    ):
        return NarrativeIssue(
            context.unit_id,
            "unsupported_institutional_assertion",
            context.exact_text,
        )
    contract = context.unit_contract
    if contract in {"hypothetical_example", "disclosed_dramatization"}:
        if binding in {
            "current_person",
            "current_institution",
            "protected_exact_subject",
        }:
            return NarrativeIssue(
                context.unit_id,
                "unsupported_actuality_binding",
                context.exact_text,
            )
        return None

    has_action = bool(evidence.action_or_event_spans)
    has_dialogue = bool(evidence.dialogue_spans)
    has_time = bool(evidence.time_spans)
    has_location = bool(evidence.location_spans)
    has_aspect = bool(evidence.grammatical_marker_spans.aspect)
    has_modality = bool(evidence.grammatical_marker_spans.modality)
    has_result = bool(evidence.result_spans)
    has_reality_detail = any(
        (
            has_dialogue,
            bool(evidence.motive_spans),
            has_time,
            has_location,
            has_aspect,
        )
    )

    if contract == "abstract_observation":
        if (
            binding == "current_person"
            and (has_action or has_reality_detail or has_result)
        ):
            return NarrativeIssue(
                context.unit_id,
                "unsupported_actuality_binding",
                context.exact_text,
            )
        if binding == "fictional_role" and has_action:
            return NarrativeIssue(
                context.unit_id,
                "situated_event_in_observation",
                context.exact_text,
            )
        if has_dialogue or (
            has_action and (has_result or has_time or has_location or has_aspect)
        ) or ((has_time or has_location or has_aspect) and evidence.predicate_spans):
            return NarrativeIssue(
                context.unit_id,
                "situated_event_in_observation",
                context.exact_text,
            )
        if has_action:
            return NarrativeIssue(
                context.unit_id,
                "insufficient_evidence",
                context.exact_text,
            )
        return None

    if contract == "recommendation":
        if has_aspect or has_time or has_location or has_dialogue:
            return NarrativeIssue(
                context.unit_id,
                "situated_event_in_recommendation",
                context.exact_text,
            )
        if not has_modality:
            return NarrativeIssue(
                context.unit_id,
                "insufficient_evidence",
                context.exact_text,
            )
        return None

    if contract == "actuality_reflection":
        if (
            binding == "current_person"
            and (
                has_action
                or has_reality_detail
                or has_result
                or bool(evidence.cause_spans)
            )
        ):
            return NarrativeIssue(
                context.unit_id,
                "unsupported_actuality_expansion",
                context.exact_text,
            )
        if has_aspect or has_time or has_location or has_dialogue:
            return NarrativeIssue(
                context.unit_id,
                "situated_event_in_reflection",
                context.exact_text,
            )
        if has_action and not has_modality:
            return NarrativeIssue(
                context.unit_id,
                "insufficient_evidence",
                context.exact_text,
            )
        return None

    return NarrativeIssue(
        context.unit_id,
        "kernel_program_drift",
        context.exact_text,
    )


def _kernel_program_issues(
    kernel: CreativeKernelV1,
) -> tuple[NarrativeIssue, ...]:
    if (
        kernel.program_id
        == OBSERVATION_WITH_HYPOTHETICAL_EXAMPLE_PROGRAM
    ):
        expected = {
            "unit:body-opening": ("abstract_principle",),
            "unit:hypothetical-example": ("hypothesis",),
            "unit:body-closing": ("abstract_principle",),
        }
    else:
        expected = {"unit:body": ("abstract_principle",)}
    body_units = {
        unit.unit_id: unit
        for unit in kernel.units
        if unit.purpose == "body"
    }
    if set(body_units) != set(expected) or any(
        body_units[unit_id].allowed_observation_types != allowed
        for unit_id, allowed in expected.items()
        if unit_id in body_units
    ):
        return (
            NarrativeIssue(
                "creative-kernel",
                "kernel_program_drift",
                kernel.program_id,
            ),
        )
    return ()


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


def _has_unsupported_actuality_binding(
    evidence: ClauseEvidence,
) -> bool:
    """Reject deictic bindings while allowing generic fictional subjects.

    This is a small grammatical class, not a topic/person blacklist: first
    person possession, the current store, and explicitly real-world subjects
    bind a hypothetical clause to current actuality.
    """
    scoped_spans = (
        *evidence.subject_spans,
        *evidence.location_spans,
    )
    return any(
        span == "我"
        or span.startswith(_CURRENT_REALITY_PREFIXES)
        for span in scoped_spans
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


def _quote_tuple(
    value: object,
    *,
    exact_text: str,
) -> tuple[SpanOccurrence, ...]:
    if not isinstance(value, list):
        raise TypeError("review evidence quote spans are invalid")
    spans: list[SpanOccurrence] = []
    for raw in value:
        if not isinstance(raw, Mapping) or frozenset(raw) != {
            "text",
            "context_quote",
        }:
            raise TypeError("review evidence quote span is invalid")
        text = raw.get("text")
        context_quote = raw.get("context_quote")
        if (
            not isinstance(text, str)
            or not text
            or not isinstance(context_quote, str)
            or not context_quote
        ):
            raise TypeError("review evidence quote span fields are invalid")
        context_starts = _exact_match_starts(exact_text, context_quote)
        focus_starts = _exact_match_starts(context_quote, text)
        if len(context_starts) != 1 or len(focus_starts) != 1:
            raise TypeError("review evidence quote cannot be uniquely resolved")
        start = context_starts[0] + focus_starts[0]
        spans.append(
            SpanOccurrence(
                text=text,
                start=start,
                end=start + len(text),
            )
        )
    if len(spans) != len(set(spans)):
        raise TypeError("review evidence quote spans are duplicated")
    return tuple(spans)


def _exact_match_starts(exact_text: str, fragment: str) -> tuple[int, ...]:
    starts: list[int] = []
    cursor = 0
    while cursor <= len(exact_text) - len(fragment):
        start = exact_text.find(fragment, cursor)
        if start < 0:
            break
        starts.append(start)
        cursor = start + 1
    return tuple(starts)
