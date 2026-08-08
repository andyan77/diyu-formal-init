from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import cast
from uuid import UUID

from src.shared.errors import DomainError

PUBLICATION_PROJECTION_V2_CONTRACT = "brand-publication-projection-v2"
PUBLICATION_ITEM_SCOPE_V2_CONTRACT = "publication-item-scope-v2"
AUTHORIZATION_CONTRACT_VERSION = "content-authorization-v1"
QUALIFICATION_CONTRACT_VERSION = "brand-relevance-qualification-v1"


@dataclass(frozen=True)
class AuthorizationContractV1:
    contract_version: str
    authorization_id: str
    authorization_version: str
    subject_ref: str
    tenant_id: str
    brand_id: str
    logical_account_id: str
    organization_id: str
    allowed_source_digest: str
    allowed_usage: tuple[str, ...]
    single_use: bool
    effective_at: str
    expires_at: str | None
    digest: str


_V2_DIGEST_FIELDS = (
    "position",
    "publication_role",
    "published_text",
    "applicability",
    "source_kind",
    "source_ref",
    "source_version",
    "source_digest",
    "visibility_scope",
    "scope_organization_ids",
    "effective_at",
    "expires_at",
    "authority_class",
    "semantic_subject_type",
    "semantic_subject_id",
    "claim_key",
    "scope_contract_version",
)


def _digest(document: Mapping[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(
            dict(document),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    ).hexdigest()


def publication_projection_v2_digest(
    items: Sequence[Mapping[str, object]],
) -> str:
    normalized: list[dict[str, object]] = []
    for item in items:
        if any(field not in item for field in _V2_DIGEST_FIELDS):
            raise DomainError("作用域发布条目缺少 V2 digest 字段")
        raw_applicability = item["applicability"]
        raw_scope_ids = item["scope_organization_ids"]
        if not isinstance(raw_applicability, Sequence) or isinstance(raw_applicability, str):
            raise DomainError("作用域发布条目适用产品无效")
        if not isinstance(raw_scope_ids, Sequence) or isinstance(raw_scope_ids, str):
            raise DomainError("作用域发布条目组织范围无效")
        normalized.append(
            {
                "position": _required_int(item["position"]),
                "publication_role": str(item["publication_role"]),
                "published_text": str(item["published_text"]),
                "applicability": sorted(str(value) for value in raw_applicability),
                "source_kind": str(item["source_kind"]),
                "source_ref": str(item["source_ref"]),
                "source_version": str(item["source_version"]),
                "source_digest": str(item["source_digest"]),
                "visibility_scope": str(item["visibility_scope"]),
                "scope_organization_ids": sorted(str(value) for value in raw_scope_ids),
                "effective_at": _iso_time(item["effective_at"]),
                "expires_at": _iso_time(item["expires_at"]),
                "authority_class": str(item["authority_class"]),
                "semantic_subject_type": _optional_string(item["semantic_subject_type"]),
                "semantic_subject_id": _optional_string(item["semantic_subject_id"]),
                "claim_key": _optional_string(item["claim_key"]),
                "scope_contract_version": str(item["scope_contract_version"]),
            }
        )
    normalized.sort(key=lambda item: cast(int, item["position"]))
    return _digest(
        {
            "contract_version": PUBLICATION_PROJECTION_V2_CONTRACT,
            "items": normalized,
        }
    )


def publication_item_is_effective(
    *,
    effective_at: datetime,
    expires_at: datetime | None,
    task_context_as_of: datetime,
) -> bool:
    """Apply the server-time interval used by the formal task query."""

    if (
        effective_at.tzinfo is None
        or task_context_as_of.tzinfo is None
        or (expires_at is not None and expires_at.tzinfo is None)
    ):
        raise DomainError("发布条目生命周期必须使用带时区的服务端时间")
    return effective_at <= task_context_as_of and (expires_at is None or task_context_as_of < expires_at)


def _iso_time(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise DomainError("作用域发布条目生命周期无效")
        return value.astimezone(timezone.utc).isoformat()
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError as exc:
        raise DomainError("作用域发布条目生命周期无效") from exc
    if parsed.tzinfo is None:
        raise DomainError("作用域发布条目生命周期无效")
    return parsed.astimezone(timezone.utc).isoformat()


def _optional_string(value: object) -> str | None:
    return str(value) if value is not None else None


def _required_int(value: object) -> int:
    if isinstance(value, bool):
        raise DomainError("作用域发布条目顺序无效")
    try:
        return int(str(value))
    except ValueError as exc:
        raise DomainError("作用域发布条目顺序无效") from exc


def authorization_contract_document(
    contract: AuthorizationContractV1,
    *,
    include_digest: bool = True,
) -> dict[str, object]:
    document: dict[str, object] = {
        "contract_version": contract.contract_version,
        "authorization_id": contract.authorization_id,
        "authorization_version": contract.authorization_version,
        "subject_ref": contract.subject_ref,
        "tenant_id": contract.tenant_id,
        "brand_id": contract.brand_id,
        "logical_account_id": contract.logical_account_id,
        "organization_id": contract.organization_id,
        "allowed_source_digest": contract.allowed_source_digest,
        "allowed_usage": list(contract.allowed_usage),
        "single_use": contract.single_use,
        "effective_at": _iso_time(contract.effective_at),
        "expires_at": _iso_time(contract.expires_at),
    }
    if include_digest:
        document["digest"] = contract.digest
    return document


def authorization_contract_digest(contract: AuthorizationContractV1) -> str:
    return _digest(authorization_contract_document(contract, include_digest=False))


def assert_authorization_contract(contract: AuthorizationContractV1) -> None:
    try:
        for value in (
            contract.authorization_id,
            contract.tenant_id,
            contract.brand_id,
            contract.logical_account_id,
            contract.organization_id,
        ):
            UUID(value)
    except ValueError as exc:
        raise DomainError("人物授权合同作用域无效") from exc
    if (
        contract.contract_version != AUTHORIZATION_CONTRACT_VERSION
        or not contract.authorization_version
        or not contract.subject_ref
        or len(contract.allowed_source_digest) != 64
        or not contract.allowed_usage
        or len(set(contract.allowed_usage)) != len(contract.allowed_usage)
        or authorization_contract_digest(contract) != contract.digest
    ):
        raise DomainError("人物授权合同无效")
    try:
        effective = datetime.fromisoformat(contract.effective_at)
        expires = datetime.fromisoformat(contract.expires_at) if contract.expires_at is not None else None
    except ValueError as exc:
        raise DomainError("人物授权合同生命周期无效") from exc
    if effective.tzinfo is None or (expires is not None and (expires.tzinfo is None or expires <= effective)):
        raise DomainError("人物授权合同生命周期无效")


def authorization_contract_from_document(value: object) -> AuthorizationContractV1:
    if not isinstance(value, Mapping):
        raise DomainError("人物授权合同无效")
    raw_usage = value.get("allowed_usage")
    if not isinstance(raw_usage, list) or any(not isinstance(item, str) for item in raw_usage):
        raise DomainError("人物授权合同用途无效")
    try:
        contract = AuthorizationContractV1(
            contract_version=str(value["contract_version"]),
            authorization_id=str(value["authorization_id"]),
            authorization_version=str(value["authorization_version"]),
            subject_ref=str(value["subject_ref"]),
            tenant_id=str(value["tenant_id"]),
            brand_id=str(value["brand_id"]),
            logical_account_id=str(value["logical_account_id"]),
            organization_id=str(value["organization_id"]),
            allowed_source_digest=str(value["allowed_source_digest"]),
            allowed_usage=tuple(cast(list[str], raw_usage)),
            single_use=_required_bool(value["single_use"]),
            effective_at=str(value["effective_at"]),
            expires_at=(str(value["expires_at"]) if value.get("expires_at") is not None else None),
            digest=str(value["digest"]),
        )
    except KeyError as exc:
        raise DomainError("人物授权合同不完整") from exc
    assert_authorization_contract(contract)
    return contract


def qualification_digest(document: Mapping[str, object]) -> str:
    return _digest(
        {
            "contract_version": QUALIFICATION_CONTRACT_VERSION,
            "path_family": document.get("path_family"),
            "source_id": document.get("source_id"),
            "source_version": document.get("source_version"),
            "source_digest": document.get("source_digest"),
            "organization_ref": document.get("organization_ref"),
            "involves_person": document.get("involves_person"),
            "authorization_digest": document.get("authorization_digest"),
        }
    )


def resolve_claim_authority(
    rows: Sequence[Mapping[str, object]],
) -> tuple[Mapping[str, object], ...]:
    """Resolve structured claim authority after SQL scope/lifecycle filtering."""

    selected: list[Mapping[str, object]] = []
    claims: dict[tuple[str, str | None, str], list[Mapping[str, object]]] = {}
    for row in rows:
        claim_key = row.get("claim_key")
        subject_type = row.get("semantic_subject_type")
        if not isinstance(claim_key, str) or not claim_key or not isinstance(subject_type, str):
            selected.append(row)
            continue
        key = (
            subject_type,
            str(row["semantic_subject_id"]) if row.get("semantic_subject_id") is not None else None,
            claim_key,
        )
        claims.setdefault(key, []).append(row)
    for (subject_type, _, _), candidates in claims.items():
        ranks = [_authority_rank(subject_type, str(item.get("authority_class"))) for item in candidates]
        winning_rank = max(ranks)
        winners = [item for item, rank in zip(candidates, ranks, strict=True) if rank == winning_rank]
        values = {(str(item.get("published_text")), str(item.get("source_digest"))) for item in winners}
        if len(values) != 1:
            raise DomainError("当前任务需要的同级正式事实存在冲突，状态为 needs_review")
        selected.extend(winners)
    return tuple(sorted(selected, key=lambda row: cast(int, row["position"])))


def _authority_rank(subject_type: str, authority_class: str) -> int:
    if subject_type == "local_context":
        return {
            "local_formal": 30,
            "local_ordinary": 20,
            "headquarters_formal": 10,
        }.get(authority_class, 0)
    if subject_type in {"brand", "product"}:
        return {
            "headquarters_formal": 30,
            "local_formal": 20,
            "local_ordinary": 10,
        }.get(authority_class, 0)
    return {
        "headquarters_formal": 20,
        "local_formal": 20,
        "local_ordinary": 10,
        "expression_governance": 0,
    }.get(authority_class, 0)


def _required_bool(value: object) -> bool:
    if not isinstance(value, bool):
        raise DomainError("人物授权合同无效")
    return value
