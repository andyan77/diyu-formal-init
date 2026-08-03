from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass

from src.shared.errors import DomainError, GenerationFailed
from src.shared.product_value import (
    P2ProductDecisionBasisV2,
    P5ProductDecisionBasisV2,
    ProductDecisionBasisV2,
)
from src.shared.publication_contract import (
    PublicationContractV3,
    publication_contract_digest,
)
from src.shared.visible_structure import assert_writer_visible_text_safe

WRITER_REQUEST_VERSION = "writer-request-v3"
WRITER_OUTPUT_VERSION = "writer-output-v3"


@dataclass(frozen=True)
class WriterRequestV3:
    request_version: str
    publication_contract_digest: str
    topic_origin: str
    topic: str
    content_product: str
    central_job: str
    audience_payoff: str
    actuality_context: tuple[tuple[str, str], ...]
    explicit_user_controls: tuple[str, ...]
    account_editorial_permission: dict[str, str]
    product_decision_basis: dict[str, object] | None
    series_delta: dict[str, object] | None
    platform_direction: dict[str, str]
    prohibited_bindings: tuple[str, ...]
    prior_output: dict[str, str] | None
    revision_instruction: str | None


@dataclass(frozen=True)
class WriterOutputV3:
    output_version: str
    title: str
    natural_guide: str
    creative_body: str
    publication_caption: str


def build_writer_request_v3(
    contract: PublicationContractV3,
    *,
    product_decision_basis: ProductDecisionBasisV2 | None,
    prior_output: WriterOutputV3 | None,
    revision_instruction: str | None,
) -> WriterRequestV3:
    basis_document: dict[str, object] | None = None
    if isinstance(product_decision_basis, P2ProductDecisionBasisV2):
        basis_document = {
            "product_specific_understanding": (product_decision_basis.product_specific_understanding),
            "tradeoff": product_decision_basis.tradeoff,
            "condition_of_validity": (product_decision_basis.condition_of_validity),
            "supporting_fact_refs": list(product_decision_basis.supporting_fact_refs),
        }
    elif isinstance(product_decision_basis, P5ProductDecisionBasisV2):
        basis_document = {
            "product_specific_understanding": (product_decision_basis.product_specific_understanding),
            "tradeoff": product_decision_basis.tradeoff,
            "condition_of_validity": (product_decision_basis.condition_of_validity),
            "relation_kind": product_decision_basis.relation_kind,
            "supporting_fact_refs": list(product_decision_basis.supporting_fact_refs),
        }
    permission = contract.account_editorial_permission
    series = contract.series_delta
    platform = contract.platform_direction
    actuality_context = tuple(
        (span.source_id, span.exact_text)
        for span in contract.input_roles
        if span.role == "observable_actuality"
    )
    request = WriterRequestV3(
        request_version=WRITER_REQUEST_VERSION,
        publication_contract_digest=publication_contract_digest(contract),
        topic_origin=contract.topic_origin,
        topic=(
            "现实片段已由服务端冻结并会另行展示；请从事实之后直接形成中心判断"
            if actuality_context
            else contract.topic
        ),
        content_product=contract.content_product,
        central_job=contract.central_job,
        audience_payoff=contract.audience_payoff,
        actuality_context=actuality_context,
        explicit_user_controls=contract.explicit_user_controls,
        account_editorial_permission={
            "identity": permission.identity,
            "audience": permission.audience,
            "attention_order": permission.attention_order,
            "response_posture": permission.response_posture,
            "refusals": permission.refusals,
            "allowed_stance": permission.allowed_stance,
        },
        product_decision_basis=basis_document,
        series_delta=(
            {
                "prior_episode_facts": list(series.prior_episode_facts),
                "prior_judgments": list(series.prior_judgments),
                "current_episode_job": series.current_episode_job,
                "required_new_judgment": series.required_new_judgment,
                "series_position": series.series_position,
                "topic_origin": series.topic_origin,
            }
            if series is not None
            else None
        ),
        platform_direction={
            "target": platform.target,
            "media_format": platform.media_format,
            "direction_version": platform.direction_version,
        },
        prohibited_bindings=contract.prohibited_bindings,
        prior_output=(
            {
                "title": prior_output.title,
                "natural_guide": prior_output.natural_guide,
                "creative_body": prior_output.creative_body,
                "publication_caption": prior_output.publication_caption,
            }
            if prior_output is not None
            else None
        ),
        revision_instruction=(revision_instruction.strip() if revision_instruction else None),
    )
    assert_writer_request_v3(request)
    return request


def writer_request_document(request: WriterRequestV3) -> dict[str, object]:
    return {
        "request_version": request.request_version,
        "publication_contract_digest": request.publication_contract_digest,
        "topic_origin": request.topic_origin,
        "topic": request.topic,
        "content_product": request.content_product,
        "central_job": request.central_job,
        "audience_payoff": request.audience_payoff,
        "actuality_context": [
            {"source_id": source_id, "exact_text": exact_text} for source_id, exact_text in request.actuality_context
        ],
        "explicit_user_controls": list(request.explicit_user_controls),
        "account_editorial_permission": dict(request.account_editorial_permission),
        "product_decision_basis": request.product_decision_basis,
        "series_delta": request.series_delta,
        "platform_direction": dict(request.platform_direction),
        "prohibited_bindings": list(request.prohibited_bindings),
        "prior_output": request.prior_output,
        "revision_instruction": request.revision_instruction,
    }


def writer_request_digest(request: WriterRequestV3) -> str:
    return hashlib.sha256(
        json.dumps(
            writer_request_document(request),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    ).hexdigest()


def assert_writer_request_v3(request: WriterRequestV3) -> None:
    if (
        request.request_version != WRITER_REQUEST_VERSION
        or len(request.publication_contract_digest) != 64
        or request.topic_origin not in {"explicit_user", "system_selected"}
        or not request.topic
        or not request.content_product
        or not request.central_job
        or not request.audience_payoff
        or set(request.account_editorial_permission)
        != {
            "identity",
            "audience",
            "attention_order",
            "response_posture",
            "refusals",
            "allowed_stance",
        }
        or any(not value for value in request.account_editorial_permission.values())
        or set(request.platform_direction) != {"target", "media_format", "direction_version"}
    ):
        raise DomainError("Writer 请求没有绑定唯一发布合同")


def writer_output_from_response(value: object) -> WriterOutputV3:
    if not isinstance(value, Mapping) or set(value) != {
        "title",
        "natural_guide",
        "creative_body",
        "publication_caption",
    }:
        raise GenerationFailed("Writer 返回结构不完整")
    output = WriterOutputV3(
        output_version=WRITER_OUTPUT_VERSION,
        title=_required_visible_text(value.get("title"), "标题"),
        natural_guide=_required_visible_text(value.get("natural_guide"), "导读"),
        creative_body=_required_visible_text(value.get("creative_body"), "正文"),
        publication_caption=_required_visible_text(value.get("publication_caption"), "发布配文"),
    )
    return output


def writer_output_document(output: WriterOutputV3) -> dict[str, object]:
    return {
        "output_version": output.output_version,
        "title": output.title,
        "natural_guide": output.natural_guide,
        "creative_body": output.creative_body,
        "publication_caption": output.publication_caption,
    }


def writer_output_from_document(value: object) -> WriterOutputV3:
    if not isinstance(value, Mapping) or value.get("output_version") != WRITER_OUTPUT_VERSION:
        raise DomainError("内容任务冻结的 Writer 成稿无效")
    output = WriterOutputV3(
        output_version=WRITER_OUTPUT_VERSION,
        title=_required_visible_text(value.get("title"), "标题"),
        natural_guide=_required_visible_text(value.get("natural_guide"), "导读"),
        creative_body=_required_visible_text(value.get("creative_body"), "正文"),
        publication_caption=_required_visible_text(value.get("publication_caption"), "发布配文"),
    )
    return output


def writer_output_digest(output: WriterOutputV3) -> str:
    return hashlib.sha256(
        json.dumps(
            writer_output_document(output),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    ).hexdigest()


def _required_visible_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GenerationFailed(f"Writer 缺少{label}")
    text = value.strip()
    try:
        assert_writer_visible_text_safe(text)
    except ValueError as exc:
        raise GenerationFailed(f"Writer {label}包含保留结构") from exc
    return text
