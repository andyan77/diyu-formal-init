from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, TypeAlias, cast

from src.shared.errors import DomainError

CreationDisposition: TypeAlias = Literal["not_committed", "committed"]
CreationSource: TypeAlias = Literal["explicit_text", "explicit_ui", "active_revision"]
CreationKind: TypeAlias = Literal["new_content", "revision", "continuation", "recompile"]

GATE_VERSION = "creation-intent-gate-v1"

_DELIVERABLE = (
    r"(?:小红书(?:文案|图文|视频)?|文案|文章|帖子|脚本|口播|图文|视频稿|"
    r"短视频|发布草稿|内容成品|成品|内容|短剧|情境演绎|故事|"
    r"(?:这|那|一)条(?:内容)?)"
)
_DIRECTIVE = re.compile(
    rf"^(?:(?:请|麻烦|直接|帮我|给我|替我|可以帮我|能不能帮我)\s*)+"
    rf"(?:生成|写|做|创作|产出|制作|发|整理|改写)"
    rf"[^。！？!?\n]{{0,56}}?{_DELIVERABLE}"
)
_BARE_IMPERATIVE = re.compile(
    rf"^(?:生成|写|做|创作|产出|制作|发)"
    rf"[^。！？!?\n]{{0,56}}?{_DELIVERABLE}"
)
_BA_CONSTRUCTION = re.compile(
    rf"^把[^。！？!?\n]{{1,64}}?(?:写出来|写成[^。！？!?\n]{{0,24}}?{_DELIVERABLE}|"
    rf"整理成[^。！？!?\n]{{0,24}}?{_DELIVERABLE}|改写成[^。！？!?\n]{{0,24}}?{_DELIVERABLE})"
)
_MISSING_ACTUALITY_BA = re.compile(
    r"^把\s*(?:我(?:们)?(?:的)?|这段(?:经历|日子|过程)|那段(?:经历|日子|过程)|"
    r"这件事|那件事|刚才(?:说|提)的|上面(?:说|提)的)"
)
_CLAUSE = re.compile(r"[^，,。！？!?\n]+")


@dataclass(frozen=True)
class CreationCommitment:
    gate_version: str
    disposition: CreationDisposition
    source: CreationSource
    creation_kind: CreationKind
    source_turn: int
    intent_span: str

    @property
    def committed(self) -> bool:
        return self.disposition == "committed"


def evaluate_creation_intent(
    user_turns: Sequence[str],
    *,
    explicit_ui: bool = False,
    active_revision: bool = False,
    creation_kind: CreationKind = "new_content",
) -> CreationCommitment:
    """Authorize only a user-observable creation commitment.

    The gate is deliberately a tiny positive grammar. It knows creation actions and deliverable
    forms, not topics, people, emotions, life situations, test cards, or model classifications.
    It performs no I/O and has no access to a repository or provider.
    """
    turns = tuple(user_turns)
    source_turn = max(0, len(turns) - 1)
    current = turns[-1] if turns else ""
    if active_revision and current.strip():
        return CreationCommitment(
            GATE_VERSION,
            "committed",
            "active_revision",
            creation_kind,
            source_turn,
            current,
        )
    if explicit_ui and current.strip():
        return CreationCommitment(
            GATE_VERSION,
            "committed",
            "explicit_ui",
            creation_kind,
            source_turn,
            current,
        )
    for index in range(len(turns) - 1, -1, -1):
        span = explicit_intent_span(turns[index])
        if span is not None:
            return CreationCommitment(
                GATE_VERSION,
                "committed",
                "explicit_text",
                creation_kind,
                index,
                span,
            )
    return CreationCommitment(
        GATE_VERSION,
        "not_committed",
        "explicit_text",
        creation_kind,
        source_turn,
        "",
    )


def explicit_intent_span(text: str) -> str | None:
    """Return one exact user substring containing both creation action and deliverable."""
    for clause_match in _CLAUSE.finditer(text):
        raw_clause = clause_match.group(0)
        leading = len(raw_clause) - len(raw_clause.lstrip())
        clause = raw_clause.lstrip()
        for pattern in (_DIRECTIVE, _BARE_IMPERATIVE, _BA_CONSTRUCTION):
            match = pattern.match(clause)
            if match is None:
                continue
            start = clause_match.start() + leading + match.start()
            end = clause_match.start() + leading + match.end()
            span = text[start:end]
            if span and span in text:
                return span
    return None


def requires_indispensable_user_fact(intent_span: str) -> bool:
    """Recognize an unresolved first-person or anaphoric actuality directive.

    This small grammatical guard contains no topic, relationship, emotion, or
    historical failure vocabulary.  The directive identifies what the user
    wants produced, but does not prove what happened.
    """
    return _MISSING_ACTUALITY_BA.match(intent_span.strip()) is not None


def commitment_document(commitment: CreationCommitment) -> dict[str, object]:
    return {
        "gate_version": commitment.gate_version,
        "disposition": commitment.disposition,
        "source": commitment.source,
        "creation_kind": commitment.creation_kind,
        "source_turn": commitment.source_turn,
        "intent_span": commitment.intent_span,
    }


def commitment_from_document(value: object) -> CreationCommitment:
    if not isinstance(value, Mapping):
        raise DomainError("内容任务冻结的创作提交无效")
    gate_version = value.get("gate_version")
    disposition = value.get("disposition")
    source = value.get("source")
    creation_kind = value.get("creation_kind")
    source_turn = value.get("source_turn")
    intent_span = value.get("intent_span")
    if (
        gate_version != GATE_VERSION
        or disposition not in {"not_committed", "committed"}
        or source not in {"explicit_text", "explicit_ui", "active_revision"}
        or creation_kind not in {"new_content", "revision", "continuation", "recompile"}
        or not isinstance(source_turn, int)
        or source_turn < 0
        or not isinstance(intent_span, str)
        or (disposition == "committed") != bool(intent_span)
    ):
        raise DomainError("内容任务冻结的创作提交无效")
    return CreationCommitment(
        GATE_VERSION,
        cast(CreationDisposition, disposition),
        cast(CreationSource, source),
        cast(CreationKind, creation_kind),
        source_turn,
        intent_span,
    )
