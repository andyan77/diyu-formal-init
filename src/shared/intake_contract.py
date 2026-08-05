from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from src.shared.errors import DomainError
from src.shared.narrative import UserFactCandidate
from src.shared.publication_contract import (
    INTAKE_ROLE_CONTRACT_VERSION,
    LEGACY_INTAKE_ROLE_CONTRACT_VERSION,
    IntakeSpanRole,
)

_ALLOWED_ROLES = frozenset(
    {
        "observable_actuality",
        "creation_instruction",
        "style_or_revision_instruction",
    }
)
_DELETED_LIVE_FIELDS = frozenset(
    {
        "user_fact_sentence_ids",
        "user_instruction_sentence_ids",
    }
)


@dataclass(frozen=True)
class IntakeRoleProjectionV2:
    """One ordered role projection over server-owned source candidates."""

    contract_version: str
    source_contract_version: str
    roles: tuple[tuple[str, IntakeSpanRole], ...]
    legacy_replay: bool = False

    @property
    def actuality_source_ids(self) -> tuple[str, ...]:
        return tuple(source_id for source_id, role in self.roles if role == "observable_actuality")

    @property
    def instruction_source_ids(self) -> tuple[str, ...]:
        return tuple(source_id for source_id, role in self.roles if role != "observable_actuality")


def parse_live_intake_role_projection(
    document: Mapping[str, object],
    candidates: Sequence[UserFactCandidate],
) -> IntakeRoleProjectionV2:
    """Parse the v2 live contract and reject every deleted duplicate authority."""

    deleted = sorted(_DELETED_LIVE_FIELDS & set(document))
    if deleted:
        raise DomainError("新 Intake 合同包含已删除的事实选择字段")
    return _parse_roles(
        document.get("user_sentence_roles"),
        candidates,
        source_contract_version=INTAKE_ROLE_CONTRACT_VERSION,
        legacy_replay=False,
    )


def replay_legacy_intake_role_projection(
    document: Mapping[str, object],
    candidates: Sequence[UserFactCandidate],
) -> IntakeRoleProjectionV2:
    """Replay old raw without granting its duplicate fact list any authority."""

    return _parse_roles(
        document.get("user_sentence_roles"),
        candidates,
        source_contract_version=LEGACY_INTAKE_ROLE_CONTRACT_VERSION,
        legacy_replay=True,
    )


def _parse_roles(
    raw_roles: object,
    candidates: Sequence[UserFactCandidate],
    *,
    source_contract_version: str,
    legacy_replay: bool,
) -> IntakeRoleProjectionV2:
    candidate_ids = tuple(candidate.source_id for candidate in candidates)
    if len(candidate_ids) != len(set(candidate_ids)):
        raise DomainError("服务端冻结的 Intake 候选标识重复")
    if not isinstance(raw_roles, list):
        raise DomainError("Intake 角色表缺失")

    parsed: list[tuple[str, IntakeSpanRole]] = []
    seen: set[str] = set()
    for item in raw_roles:
        if not isinstance(item, Mapping) or set(item) != {"sentence_id", "role"}:
            raise DomainError("Intake 角色项结构无效")
        sentence_id = item.get("sentence_id")
        role = item.get("role")
        if not isinstance(sentence_id, str) or sentence_id not in candidate_ids:
            raise DomainError("Intake 角色表包含未知候选")
        if sentence_id in seen:
            raise DomainError("Intake 角色表包含重复候选")
        if role not in _ALLOWED_ROLES:
            raise DomainError("Intake 角色表包含非法角色")
        seen.add(sentence_id)
        parsed.append((sentence_id, cast(IntakeSpanRole, role)))

    parsed_ids = tuple(source_id for source_id, _ in parsed)
    if set(parsed_ids) != set(candidate_ids):
        raise DomainError("Intake 角色表未完整覆盖冻结候选")
    if parsed_ids != candidate_ids:
        raise DomainError("Intake 角色表改变了冻结候选顺序")
    return IntakeRoleProjectionV2(
        contract_version=INTAKE_ROLE_CONTRACT_VERSION,
        source_contract_version=source_contract_version,
        roles=tuple(parsed),
        legacy_replay=legacy_replay,
    )
