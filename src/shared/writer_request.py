from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass

from src.shared.account_editorial_lens import (
    account_editorial_lens_digest,
    account_editorial_resolution_digest,
)
from src.shared.errors import DomainError, GenerationFailed
from src.shared.product_value import (
    P1ProductDecisionBasisV3,
    P2ProductDecisionBasisV2,
    P5ProductDecisionBasisV2,
    ProductDecisionBasisV2,
    product_value_contract_digest,
)
from src.shared.publication_contract import (
    INTAKE_ROLE_CONTRACT_VERSION,
    LEGACY_INTAKE_ROLE_CONTRACT_VERSION,
    LEGACY_USER_ACTUALITY_EXPRESSION_POLICY,
    USER_ACTUALITY_EXPRESSION_POLICY,
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
    actuality_fact_refs: tuple[str, ...]
    read_only_actuality_context: tuple[dict[str, str], ...]
    explicit_user_controls: tuple[str, ...]
    account_editorial_permission: dict[str, str]
    product_decision_basis: dict[str, object] | None
    series_delta: dict[str, object] | None
    platform_direction: dict[str, str]
    prohibited_bindings: tuple[str, ...]
    prior_output: dict[str, str] | None
    revision_instruction: str | None
    expression_policy_version: str
    intake_role_contract_version: str
    account_editorial_context: dict[str, object] | None = None
    brand_relevance: dict[str, object] | None = None


@dataclass(frozen=True)
class WriterOutputV3:
    output_version: str
    title: str
    natural_guide: str
    creative_body: str
    publication_caption: str


def _product_basis_document(
    basis: ProductDecisionBasisV2 | None,
) -> dict[str, object] | None:
    if isinstance(basis, P1ProductDecisionBasisV3):
        return {
            "contract_version": basis.contract_version,
            "decision_axis": basis.decision_axis,
            "product_specific_understanding": basis.product_specific_understanding,
            "tradeoff": basis.tradeoff,
            "condition_of_validity": basis.condition_of_validity,
            "supporting_fact_refs": list(basis.supporting_fact_refs),
            "source_packet_digest": basis.source_packet_digest,
            "judgment_ref": basis.judgment_ref,
            "judgment_version": basis.judgment_version,
            "applicability_conditions": list(basis.applicability_conditions),
        }
    if isinstance(basis, P2ProductDecisionBasisV2):
        return {
            "decision_axis": basis.decision_axis,
            "product_specific_understanding": basis.product_specific_understanding,
            "tradeoff": basis.tradeoff,
            "condition_of_validity": basis.condition_of_validity,
            "supporting_fact_refs": list(basis.supporting_fact_refs),
        }
    if isinstance(basis, P5ProductDecisionBasisV2):
        return {
            "product_specific_understanding": basis.product_specific_understanding,
            "tradeoff": basis.tradeoff,
            "condition_of_validity": basis.condition_of_validity,
            "relation_kind": basis.relation_kind,
            "supporting_fact_refs": list(basis.supporting_fact_refs),
        }
    return None


def build_writer_request_v3(
    contract: PublicationContractV3,
    *,
    product_decision_basis: ProductDecisionBasisV2 | None,
    platform_expression_responsibility: str,
    prior_output: WriterOutputV3 | None,
    revision_instruction: str | None,
) -> WriterRequestV3:
    basis_document = _product_basis_document(product_decision_basis)
    _assert_product_basis_binding(contract, product_decision_basis)
    permission = contract.account_editorial_permission
    series = contract.series_delta
    platform = contract.platform_direction
    actuality_fact_refs = tuple(span.source_id for span in contract.input_roles if span.role == "observable_actuality")
    read_only_actuality_context = tuple(
        {
            "fact_ref": span.source_id,
            "exact_text": span.exact_text,
        }
        for span in contract.input_roles
        if span.role == "observable_actuality"
    )
    request = WriterRequestV3(
        request_version=WRITER_REQUEST_VERSION,
        publication_contract_digest=publication_contract_digest(contract),
        topic_origin=contract.topic_origin,
        topic=contract.topic,
        content_product=contract.content_product,
        central_job=contract.central_job,
        audience_payoff=contract.audience_payoff,
        actuality_fact_refs=actuality_fact_refs,
        read_only_actuality_context=read_only_actuality_context,
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
            "expression_responsibility": (platform_expression_responsibility.strip()),
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
        expression_policy_version=contract.expression_policy_version,
        intake_role_contract_version=contract.intake_role_contract_version,
        account_editorial_context=_writer_account_editorial_context(contract),
        brand_relevance=_writer_brand_relevance(contract),
    )
    assert_writer_request_v3(request)
    return request


def writer_request_document(request: WriterRequestV3) -> dict[str, object]:
    document: dict[str, object] = {
        "request_version": request.request_version,
        "publication_contract_digest": request.publication_contract_digest,
        "topic_origin": request.topic_origin,
        "topic": request.topic,
        "content_product": request.content_product,
        "central_job": request.central_job,
        "audience_payoff": request.audience_payoff,
        "actuality_fact_refs": list(request.actuality_fact_refs),
        "read_only_actuality_context": [dict(item) for item in request.read_only_actuality_context],
        "explicit_user_controls": list(request.explicit_user_controls),
        "account_editorial_permission": dict(request.account_editorial_permission),
        "product_decision_basis": request.product_decision_basis,
        "series_delta": request.series_delta,
        "platform_direction": dict(request.platform_direction),
        "prohibited_bindings": list(request.prohibited_bindings),
        "prior_output": request.prior_output,
        "revision_instruction": request.revision_instruction,
    }
    if request.expression_policy_version != LEGACY_USER_ACTUALITY_EXPRESSION_POLICY:
        document["expression_policy_version"] = request.expression_policy_version
    if request.intake_role_contract_version != LEGACY_INTAKE_ROLE_CONTRACT_VERSION:
        document["intake_role_contract_version"] = request.intake_role_contract_version
    if request.account_editorial_context is not None:
        document["account_editorial_context"] = request.account_editorial_context
    if request.brand_relevance is not None:
        document["brand_relevance"] = request.brand_relevance
    return document


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
        or tuple(item.get("fact_ref") for item in request.read_only_actuality_context) != request.actuality_fact_refs
        or any(
            set(item) != {"fact_ref", "exact_text"} or not item["exact_text"]
            for item in request.read_only_actuality_context
        )
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
        or set(request.platform_direction)
        != {
            "target",
            "media_format",
            "direction_version",
            "expression_responsibility",
        }
        or any(not value for value in request.platform_direction.values())
        or request.expression_policy_version
        not in {
            LEGACY_USER_ACTUALITY_EXPRESSION_POLICY,
            USER_ACTUALITY_EXPRESSION_POLICY,
        }
        or request.intake_role_contract_version
        not in {
            LEGACY_INTAKE_ROLE_CONTRACT_VERSION,
            INTAKE_ROLE_CONTRACT_VERSION,
        }
        or not _valid_account_editorial_context(request.account_editorial_context)
        or not _valid_brand_relevance(request.brand_relevance)
    ):
        raise DomainError("Writer 请求没有绑定唯一发布合同")


def _assert_product_basis_binding(
    contract: PublicationContractV3,
    basis: ProductDecisionBasisV2 | None,
) -> None:
    frozen = contract.product_decision_basis
    if frozen is None and basis is None:
        return
    if (
        frozen is None
        or basis is None
        or (
            frozen.contract_version != basis.contract_version
            or frozen.digest != product_value_contract_digest(basis)
            or frozen.supporting_fact_refs != basis.supporting_fact_refs
        )
    ):
        raise DomainError("Writer 商品决策依据与冻结发布合同不一致")


def _writer_account_editorial_context(
    contract: PublicationContractV3,
) -> dict[str, object] | None:
    resolution = contract.account_editorial_resolution
    if resolution is None:
        return None
    return {
        "applied": resolution.applied,
        "contract_version": resolution.contract_version,
        "lens_contract_version": (resolution.lens.contract_version if resolution.lens is not None else None),
        "lens_digest": (
            account_editorial_lens_digest(resolution.lens) if resolution.lens is not None else None
        ),
        "degraded_reasons": [reason.value for reason in resolution.degraded_reasons],
        "source_refs": list(resolution.source_refs),
        "source_digest": resolution.source_digest,
        "resolution_digest": account_editorial_resolution_digest(resolution),
    }


def _writer_brand_relevance(contract: PublicationContractV3) -> dict[str, object] | None:
    if contract.brand_relevance_state is None:
        return None
    evidence = contract.brand_relevance_evidence
    return {
        "state": contract.brand_relevance_state,
        "family": evidence.path_family if evidence is not None else None,
        "source_object_type": evidence.source_object_type if evidence is not None else None,
        "source_id": evidence.source_id if evidence is not None else None,
        "source_version": evidence.source_version if evidence is not None else None,
        "source_digest": evidence.source_digest if evidence is not None else None,
        "organization_ref": evidence.organization_ref if evidence is not None else None,
        "authorization_ref": evidence.authorization_ref if evidence is not None else None,
        "media_ref": evidence.media_ref if evidence is not None else None,
        "actual_consumed_refs": list(evidence.actual_consumed_refs) if evidence is not None else [],
        "degraded_reason": contract.brand_relevance_degraded_reason,
        "demonstration_eligible": contract.demonstration_eligible,
    }


def _valid_account_editorial_context(value: dict[str, object] | None) -> bool:
    if value is None:
        return True
    reasons = value.get("degraded_reasons")
    return (
        isinstance(value.get("applied"), bool)
        and value.get("contract_version") == "account-editorial-resolution-v1"
        and isinstance(reasons, list)
        and all(isinstance(reason, str) and reason for reason in reasons)
        and _is_sha256(value.get("source_digest"))
        and _is_sha256(value.get("resolution_digest"))
        and ((value["applied"] is True and not reasons) or (value["applied"] is False and bool(reasons)))
    )


def _valid_brand_relevance(value: dict[str, object] | None) -> bool:
    if value is None:
        return True
    state = value.get("state")
    if state == "applied":
        return (
            value.get("family") is not None
            and _is_sha256(value.get("source_digest"))
            and isinstance(value.get("actual_consumed_refs"), list)
            and bool(value["actual_consumed_refs"])
            and value.get("demonstration_eligible") is True
        )
    return (
        state == "degraded"
        and value.get("family") is None
        and bool(value.get("degraded_reason"))
        and value.get("demonstration_eligible") is False
    )


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


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


def suppress_exact_fact_only_units(
    output: WriterOutputV3,
    *,
    user_actuality_texts: tuple[str, ...],
    exclusive_fact_texts: tuple[str, ...],
) -> WriterOutputV3:
    """Deduplicate only a standalone byte-exact user actuality paragraph.

    User actuality may be quoted, paraphrased or naturally continued in every
    Writer-owned field.  It never gains fact ownership by doing so.  Canonical
    product and brand facts remain exclusively server-owned and are rejected
    here if copied.  No normalization, approximation or semantic matching is
    performed.
    """

    exclusive_facts = tuple(text for text in exclusive_fact_texts if text)
    visible = "\n".join(
        (
            output.title,
            output.natural_guide,
            output.creative_body,
            output.publication_caption,
        )
    )
    if any(fact in visible for fact in exclusive_facts):
        raise GenerationFailed("Writer 不得复制或改写服务端事实块")

    actuality_facts = frozenset(text for text in user_actuality_texts if text)
    if not actuality_facts:
        return output
    body_paragraphs = tuple(part.strip() for part in output.creative_body.split("\n\n") if part.strip())
    creative_paragraphs = [paragraph for paragraph in body_paragraphs if paragraph not in actuality_facts]

    guide = output.natural_guide
    if guide in actuality_facts and len(creative_paragraphs) >= 2:
        guide = creative_paragraphs.pop(0)
    if not creative_paragraphs:
        raise GenerationFailed("Writer 正文不能只重复服务端事实块")
    return WriterOutputV3(
        output_version=output.output_version,
        title=output.title,
        natural_guide=guide,
        creative_body="\n\n".join(creative_paragraphs),
        publication_caption=output.publication_caption,
    )


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
