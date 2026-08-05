from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from src.shared.errors import DomainError
from src.shared.narrative import UserFactCandidate
from src.shared.publication_contract import (
    INTAKE_ROLE_CONTRACT_VERSION,
    IntakeSpanRole,
    PublicationInputSpanV1,
)


@dataclass(frozen=True)
class InputRoleResolution:
    """One complete, source-bound interpretation of the current user turns."""

    contract_version: str
    spans: tuple[PublicationInputSpanV1, ...]

    @property
    def actuality_source_ids(self) -> tuple[str, ...]:
        return tuple(span.source_id for span in self.spans if span.role == "observable_actuality")

    @property
    def actuality_texts(self) -> tuple[str, ...]:
        return tuple(span.exact_text for span in self.spans if span.role == "observable_actuality")

    @property
    def instruction_source_ids(self) -> tuple[str, ...]:
        return tuple(span.source_id for span in self.spans if span.role != "observable_actuality")


def resolve_input_roles(
    *,
    user_turns: Sequence[str],
    candidates: Sequence[UserFactCandidate],
    roles: Mapping[str, IntakeSpanRole],
    contract_version: str = INTAKE_ROLE_CONTRACT_VERSION,
) -> InputRoleResolution:
    """Validate model-selected roles against server-owned exact candidates.

    The caller may classify candidates, but it cannot create, crop, reorder or
    rewrite them.  This function is the final authority shared by both content
    API entrypoints before any business task is created.
    """

    candidate_tuple = tuple(candidates)
    candidate_ids = tuple(candidate.source_id for candidate in candidate_tuple)
    if len(candidate_ids) != len(set(candidate_ids)):
        raise DomainError("用户输入跨度标识重复")
    if tuple(roles) != candidate_ids:
        raise DomainError("用户输入角色没有完整覆盖冻结跨度")
    if contract_version != INTAKE_ROLE_CONTRACT_VERSION:
        raise DomainError("新内容任务的 Intake 角色合同版本无效")

    spans: list[PublicationInputSpanV1] = []
    turn_tuple = tuple(user_turns)
    for candidate in candidate_tuple:
        if candidate.turn_index < 1 or candidate.turn_index > len(turn_tuple):
            raise DomainError("用户输入跨度不属于本次会话")
        source = turn_tuple[candidate.turn_index - 1]
        source_bytes = source.encode("utf-8")
        if (
            source[candidate.start_offset : candidate.end_offset] != candidate.exact_text
            or source_bytes[candidate.start_byte : candidate.end_byte].decode("utf-8") != candidate.exact_text
        ):
            raise DomainError("用户输入跨度地址与原文不一致")
        spans.append(
            PublicationInputSpanV1(
                source_id=candidate.source_id,
                role=roles[candidate.source_id],
                exact_text=candidate.exact_text,
                turn_index=candidate.turn_index,
                start_offset=candidate.start_offset,
                end_offset=candidate.end_offset,
                start_byte=candidate.start_byte,
                end_byte=candidate.end_byte,
            )
        )
    return InputRoleResolution(contract_version, tuple(spans))
