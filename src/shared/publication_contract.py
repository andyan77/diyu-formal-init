from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, TypeAlias, cast

from src.shared.errors import DomainError

PUBLICATION_CONTRACT_VERSION = "publication-contract-v2"

IntakeSpanRole: TypeAlias = Literal[
    "observable_actuality",
    "creation_instruction",
    "style_or_revision_instruction",
]

NEGATIVE_SAFETY_RULES: dict[str, str] = {
    "no_user_actuality_rewrite": (
        "不新增、改写或补全用户现实事实，也不替现实人物、对象或事件判定"
        "未提供的原因、内部状态、变化或结果"
    ),
    "no_product_fact_or_effect": "不新增商品硬事实或具体商品效果",
    "no_method_as_fact": "不把品牌约束、方法或机构信息升级为现实事实",
    "no_unregistered_media": "不使用未登记的人物、场地、道具、商品或媒体资源",
    "advice_stays_conditional": "一般建议保持建议、条件或假设身份",
    "no_high_risk_reality_claim": "不新增健康、法律、交易或其他高风险现实结论",
}
NEGATIVE_SAFETY_RULE_IDS = tuple(NEGATIVE_SAFETY_RULES)


def negative_safety_contract_text() -> str:
    """Render the single shared negative contract for Writer consumers."""

    return "；".join(
        NEGATIVE_SAFETY_RULES[rule_id]
        for rule_id in NEGATIVE_SAFETY_RULE_IDS
    )


@dataclass(frozen=True)
class PublicationInputSpanV1:
    source_id: str
    role: IntakeSpanRole
    exact_text: str
    turn_index: int
    start_offset: int
    end_offset: int
    start_byte: int
    end_byte: int


@dataclass(frozen=True)
class PublicationContractV2:
    """One frozen boundary between trusted inputs and non-factual writing.

    This is deliberately a brief plus a negative safety boundary, not a
    sentence-shape language.  Unit ownership, facts and media resources remain
    in their existing contracts.
    """

    contract_version: str
    primary_product: str
    topic: str
    topic_origin: str
    central_job: str
    audience_payoff: str
    known_conditions: tuple[str, ...]
    allowed_general_advice_scope: tuple[str, ...]
    frozen_fact_refs: tuple[str, ...]
    prohibited_reality_or_product_claims: tuple[str, ...]
    intake_spans: tuple[PublicationInputSpanV1, ...]
    account_identity: str
    account_audience: str
    account_attention: str
    account_response_boundary: str
    account_refusals: str
    allowed_editorial_stance: str
    source_profile_id: str | None
    source_profile_version: int | None
    publication_projection_id: str | None
    publication_projection_version: int | None
    publication_projection_digest: str | None
    product_value_contract_digest: str | None


def publication_contract_document(
    contract: PublicationContractV2,
) -> dict[str, object]:
    """Return one JSON-native representation used by JSONB and evidence.

    Tuples are part of the immutable Python contract, but they must never leak
    into the persisted document.  PostgreSQL JSONB and a JSON round-trip both
    materialize arrays as lists; emitting lists here keeps the task snapshot
    byte-for-byte comparable with the completion patch.
    """

    return {
        "contract_version": contract.contract_version,
        "primary_product": contract.primary_product,
        "topic": contract.topic,
        "topic_origin": contract.topic_origin,
        "central_job": contract.central_job,
        "audience_payoff": contract.audience_payoff,
        "known_conditions": list(contract.known_conditions),
        "allowed_general_advice_scope": list(
            contract.allowed_general_advice_scope
        ),
        "frozen_fact_refs": list(contract.frozen_fact_refs),
        "prohibited_reality_or_product_claims": list(
            contract.prohibited_reality_or_product_claims
        ),
        "intake_spans": [
            {
                "source_id": span.source_id,
                "role": span.role,
                "exact_text": span.exact_text,
                "turn_index": span.turn_index,
                "start_offset": span.start_offset,
                "end_offset": span.end_offset,
                "start_byte": span.start_byte,
                "end_byte": span.end_byte,
            }
            for span in contract.intake_spans
        ],
        "account_identity": contract.account_identity,
        "account_audience": contract.account_audience,
        "account_attention": contract.account_attention,
        "account_response_boundary": contract.account_response_boundary,
        "account_refusals": contract.account_refusals,
        "allowed_editorial_stance": contract.allowed_editorial_stance,
        "source_profile_id": contract.source_profile_id,
        "source_profile_version": contract.source_profile_version,
        "publication_projection_id": contract.publication_projection_id,
        "publication_projection_version": (
            contract.publication_projection_version
        ),
        "publication_projection_digest": contract.publication_projection_digest,
        "product_value_contract_digest": contract.product_value_contract_digest,
    }


def publication_contract_digest(contract: PublicationContractV2) -> str:
    return hashlib.sha256(
        json.dumps(
            publication_contract_document(contract),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    ).hexdigest()


def publication_contract_from_document(value: object) -> PublicationContractV2:
    if not isinstance(value, Mapping) or value.get("contract_version") != PUBLICATION_CONTRACT_VERSION:
        raise DomainError("内容任务冻结的发布责任合同无效")
    raw_spans = value.get("intake_spans")
    if not isinstance(raw_spans, list):
        raise DomainError("内容任务冻结的输入跨度无效")
    spans: list[PublicationInputSpanV1] = []
    for raw in raw_spans:
        if not isinstance(raw, Mapping):
            raise DomainError("内容任务冻结的输入跨度无效")
        try:
            span = PublicationInputSpanV1(
                source_id=str(raw["source_id"]),
                role=cast(IntakeSpanRole, raw["role"]),
                exact_text=str(raw["exact_text"]),
                turn_index=int(raw["turn_index"]),
                start_offset=int(raw["start_offset"]),
                end_offset=int(raw["end_offset"]),
                start_byte=int(raw["start_byte"]),
                end_byte=int(raw["end_byte"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise DomainError("内容任务冻结的输入跨度无效") from exc
        _validate_input_span(span)
        spans.append(span)
    try:
        contract = PublicationContractV2(
            contract_version=PUBLICATION_CONTRACT_VERSION,
            primary_product=str(value["primary_product"]),
            topic=str(value["topic"]),
            topic_origin=str(value["topic_origin"]),
            central_job=str(value["central_job"]),
            audience_payoff=str(value["audience_payoff"]),
            known_conditions=_string_tuple(value.get("known_conditions")),
            allowed_general_advice_scope=_string_tuple(
                value.get("allowed_general_advice_scope")
            ),
            frozen_fact_refs=_string_tuple(value.get("frozen_fact_refs")),
            prohibited_reality_or_product_claims=_string_tuple(
                value.get("prohibited_reality_or_product_claims")
            ),
            intake_spans=tuple(spans),
            account_identity=str(value.get("account_identity") or ""),
            account_audience=str(value.get("account_audience") or ""),
            account_attention=str(value.get("account_attention") or ""),
            account_response_boundary=str(
                value.get("account_response_boundary") or ""
            ),
            account_refusals=str(value.get("account_refusals") or ""),
            allowed_editorial_stance=str(
                value.get("allowed_editorial_stance") or ""
            ),
            source_profile_id=_optional_string(value.get("source_profile_id")),
            source_profile_version=_optional_positive_int(
                value.get("source_profile_version")
            ),
            publication_projection_id=_optional_string(
                value.get("publication_projection_id")
            ),
            publication_projection_version=_optional_positive_int(
                value.get("publication_projection_version")
            ),
            publication_projection_digest=_optional_sha256(
                value.get("publication_projection_digest")
            ),
            product_value_contract_digest=_optional_sha256(
                value.get("product_value_contract_digest")
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise DomainError("内容任务冻结的发布责任合同无效") from exc
    assert_publication_contract(contract)
    return contract


def assert_publication_contract(contract: PublicationContractV2) -> None:
    if (
        contract.contract_version != PUBLICATION_CONTRACT_VERSION
        or not contract.primary_product
        or not contract.topic
        or contract.topic_origin not in {"explicit_user", "system_selected"}
        or not contract.central_job
        or not contract.audience_payoff
        or not contract.allowed_general_advice_scope
        or tuple(contract.prohibited_reality_or_product_claims)
        != NEGATIVE_SAFETY_RULE_IDS
        or len({span.source_id for span in contract.intake_spans})
        != len(contract.intake_spans)
    ):
        raise DomainError("内容任务冻结的发布责任合同无效")
    fact_span_ids = {
        span.source_id
        for span in contract.intake_spans
        if span.role == "observable_actuality"
    }
    frozen_user_fact_refs = {
        fact_ref
        for fact_ref in contract.frozen_fact_refs
        if fact_ref.startswith("source:user_actuality:")
    }
    if fact_span_ids != frozen_user_fact_refs:
        raise DomainError("现实事实跨度没有绑定冻结事实")
    for span in contract.intake_spans:
        _validate_input_span(span)


def build_publication_contract(
    *,
    primary_product: str,
    topic_spans: Sequence[str],
    topic_origin: str,
    known_conditions: Sequence[str],
    frozen_fact_refs: Sequence[str],
    intake_spans: Sequence[PublicationInputSpanV1],
    account_identity: str,
    account_audience: str,
    account_attention: str,
    account_response_boundary: str,
    source_profile_id: str | None,
    source_profile_version: int | None,
    publication_projection_id: str | None,
    publication_projection_version: int | None,
    publication_projection_digest: str | None,
    product_value_contract_digest: str | None,
) -> PublicationContractV2:
    central_job, payoff, advice_scope = _product_brief(primary_product, topic_origin)
    topic = (
        "由 Writer 从当前账号已确认内容领地自主选择一个具体题材"
        if topic_origin == "system_selected"
        else "\n".join(item.strip() for item in topic_spans if item.strip())
    )
    contract = PublicationContractV2(
        contract_version=PUBLICATION_CONTRACT_VERSION,
        primary_product=primary_product,
        topic=topic or "围绕本次明确输入完成一篇作品",
        topic_origin=topic_origin,
        central_job=central_job,
        audience_payoff=payoff,
        known_conditions=tuple(dict.fromkeys(item for item in known_conditions if item)),
        allowed_general_advice_scope=advice_scope,
        frozen_fact_refs=tuple(dict.fromkeys(frozen_fact_refs)),
        prohibited_reality_or_product_claims=NEGATIVE_SAFETY_RULE_IDS,
        intake_spans=tuple(intake_spans),
        account_identity=account_identity.strip(),
        account_audience=account_audience.strip(),
        account_attention=account_attention.strip(),
        account_response_boundary=account_response_boundary.strip(),
        account_refusals=account_response_boundary.strip(),
        allowed_editorial_stance=account_attention.strip(),
        source_profile_id=source_profile_id,
        source_profile_version=source_profile_version,
        publication_projection_id=publication_projection_id,
        publication_projection_version=publication_projection_version,
        publication_projection_digest=publication_projection_digest,
        product_value_contract_digest=product_value_contract_digest,
    )
    assert_publication_contract(contract)
    return contract


def _product_brief(
    primary_product: str,
    topic_origin: str,
) -> tuple[str, str, tuple[str, ...]]:
    if primary_product == "dressing_decision":
        return (
            "直接给出一条明确的一般穿衣建议、一个真实取舍和一个出门前检查动作；不要把主要决定退回用户",
            "让受众能按眼前条件做出一次可执行的穿衣选择",
            ("一般服装类别", "分层选择", "条件性建议", "真实取舍", "出门前可观察检查"),
        )
    if primary_product == "product_truth":
        return (
            "围绕逐字冻结的商品事实，解释它们对选择意味着什么，并自然写出商品专属理解、取舍与成立条件",
            "让受众知道这件商品的已确认信息何时值得纳入自己的选择",
            ("基于冻结事实的选择解释", "条件性消费者取舍", "一般判断方法"),
        )
    if primary_product == "local_response":
        return (
            "回应冻结的本地观察，给出符合账号服务姿态的具体价值；不补写人物身份、对白、原因或结果",
            "让处在相似情境的人感到被尊重，并知道可以怎样继续",
            ("条件性回应", "服务边界", "把选择留给对方"),
        )
    if primary_product == "visual_styling_story":
        return (
            "只在冻结商品事实与登记媒体资源内完成具体视觉关系",
            "让受众看清两件已登记商品的可见主辅关系",
            ("已登记资源内的视觉关系",),
        )
    if topic_origin == "system_selected":
        return (
            "自主选择一个具体生活题材，形成可陈述的中心判断并直接交付完整作品",
            "给受众一个能独立观看、能带走的具体观察",
            ("非事实创作观察", "条件性建议", "不绑定现实主体的假设"),
        )
    return (
        "围绕本次题材形成一条清楚中心判断，以当前账号的观察方式和回应姿态完成作品",
        "让受众从这一个具体片段获得可辨认、不可随意替换的观看价值",
        ("非事实创作观察", "条件性建议", "不绑定现实主体的假设"),
    )


def _validate_input_span(span: PublicationInputSpanV1) -> None:
    identity = (
        f"{span.turn_index}:{span.start_byte}:{span.end_byte}:".encode()
        + span.exact_text.encode("utf-8")
    )
    digest = hashlib.sha256(identity).hexdigest()[:12]
    source_match = re.fullmatch(
        r"source:user_actuality:turn-(\d+):clause-(\d+):(\d+)-(\d+):([0-9a-f]{12})",
        span.source_id,
    )
    if (
        source_match is None
        or int(source_match.group(1)) != span.turn_index
        or int(source_match.group(2)) < 1
        or int(source_match.group(3)) != span.start_byte
        or int(source_match.group(4)) != span.end_byte
        or source_match.group(5) != digest
        or span.role
        not in {
            "observable_actuality",
            "creation_instruction",
            "style_or_revision_instruction",
        }
        or not span.exact_text
        or span.turn_index < 1
        or span.start_offset < 0
        or span.end_offset <= span.start_offset
        or span.end_offset - span.start_offset != len(span.exact_text)
        or span.start_byte < 0
        or span.end_byte <= span.start_byte
        or span.end_byte - span.start_byte != len(span.exact_text.encode("utf-8"))
    ):
        raise DomainError("内容任务冻结的输入跨度无效")


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise DomainError("内容任务冻结的发布责任合同无效")
    return tuple(value)


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise DomainError("内容任务冻结的发布责任合同无效")
    return value


def _optional_positive_int(value: object) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or value < 1:
        raise DomainError("内容任务冻结的发布责任合同无效")
    return value


def _optional_sha256(value: object) -> str | None:
    result = _optional_string(value)
    if result is not None and (
        len(result) != 64
        or any(character not in "0123456789abcdef" for character in result)
    ):
        raise DomainError("内容任务冻结的发布责任合同摘要无效")
    return result
