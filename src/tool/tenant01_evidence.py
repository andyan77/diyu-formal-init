from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final, cast
from uuid import UUID

from src.shared.brand_publication import brand_context_packet_digest
from src.shared.content_snapshot import frozen_media_contract, frozen_product_facts
from src.shared.creative_kernel import (
    CreativeKernelV1,
    creative_units_digest,
    kernel_digest,
    kernel_from_document,
)
from src.shared.creative_plan import (
    ACCOUNT_BASELINE_TONE_ID,
    PLAN_VERSION,
    creative_plan_from_document,
    platform_shape,
    validate_creative_plan,
)
from src.shared.delivery_compiler import (
    DELIVERY_COMPILER_VERSION,
    CompiledDelivery,
    DeliveryCompileInput,
    compile_delivery,
)
from src.shared.errors import DomainError, GenerationFailed
from src.shared.factual_basis import ImmutableFactBlock
from src.shared.narrative import (
    frame_from_document,
    user_fact_candidates,
    visible_digest,
)
from src.shared.product_value import (
    ProductValueContract,
    product_value_contract_digest,
    product_value_contract_from_document,
)
from src.shared.publication_contract import (
    PUBLICATION_CONTRACT_VERSION,
    PublicationContractV2,
    build_publication_contract,
    publication_contract_digest,
    publication_contract_document,
    publication_contract_from_document,
)
from src.shared.types import ContentProduct, ContentTarget, MediaFormat

TENANT01_SUITE_VERSION: Final[str] = "TENANT-01-GOLDEN-V1"
TENANT01_RAW_BUNDLE_VERSION: Final[str] = "ux03-gate-c-provider-stages-v1"
TENANT01_GENERATION_LEDGER_VERSION: Final[str] = "tenant01-generation-ledger-v1"
TENANT01_GENERATION_LEDGER_FILE: Final[str] = "generation-ledger.json"
TENANT01_PROVIDER_MODEL: Final[str] = "deepseek-v4-flash"
TENANT01_CARD_IDS: Final[frozenset[str]] = frozenset(
    {
        "coffee",
        "zero_topic",
        "family_relationship",
        "daily_complaint",
        "P1",
        "P2",
        "P4_series1",
        "cross_platform_xhs",
        "cross_platform_douyin",
        "series2",
        "series3",
    }
)
TENANT01_REVIEW_DIMENSIONS: Final[tuple[str, ...]] = (
    "brand_relation",
    "account_voice",
    "viewer_value",
    "platform_fit",
    "completeness",
    "natural_language",
    "local_revision_consistency",
)
TENANT01_HARD_BOUNDARIES: Final[tuple[str, ...]] = (
    "tenant_scope",
    "product_facts",
    "person_facts",
    "media_resources",
)
TENANT01_DEMONSTRATION_CHECKS: Final[tuple[str, ...]] = (
    "scaffolding_free",
    "natural_brand_relation",
    "directly_publishable",
    "cross_card_distinct",
    "series_progression",
)
TENANT01_COMPARISON_FIELDS: Final[tuple[str, ...]] = (
    "title_angle",
    "central_judgment",
    "structure",
    "closure",
    "brand_relation",
)


class Tenant01EvidenceError(ValueError):
    """Raised when a first-tenant evidence set is incomplete or unbound."""


@dataclass(frozen=True)
class Tenant01ArtifactInput:
    card_id: str
    artifact_file: str
    raw_response_file: str


@dataclass(frozen=True)
class Tenant01HumanReview:
    card_id: str
    artifact_file: str
    artifact_sha256: str
    visible_digest: str
    scores: dict[str, int]
    excerpts: dict[str, str]
    hard_boundaries: dict[str, bool]
    demonstration_checks: dict[str, bool]
    comparison: dict[str, str]
    brand_basis: str
    verdict: str
    notes: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _private_child(root: Path, filename: str) -> Path:
    path = (root / filename).resolve()
    if path.parent != root.resolve() or path.name != filename:
        raise Tenant01EvidenceError("证据文件必须直接位于私有证据目录。")
    if not path.is_file() or path.stat().st_mode & 0o077:
        raise Tenant01EvidenceError(f"{filename} 不存在或不是私有文件。")
    return path


def _json_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Tenant01EvidenceError(f"{path.name} 必须是 JSON 对象。")
    return cast(dict[str, object], value)


def _uuid_text(value: object, *, label: str) -> str:
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError) as exc:
        raise Tenant01EvidenceError(f"{label} 缺少真实 UUID。") from exc


def _canonical_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    ).hexdigest()


def _raw_binding(path: Path, *, card_id: str) -> dict[str, object]:
    document = _json_object(path)
    if set(document) != {
        "raw_bundle_version",
        "card_id",
        "request_count",
        "responses",
    }:
        raise Tenant01EvidenceError(f"{card_id} 原始模型证据结构漂移。")
    if document.get("raw_bundle_version") != TENANT01_RAW_BUNDLE_VERSION or document.get("card_id") != card_id:
        raise Tenant01EvidenceError(f"{card_id} 原始模型证据绑定到了另一张卡或版本。")
    request_count = document.get("request_count")
    responses = document.get("responses")
    if (
        type(request_count) is not int
        or request_count != 2
        or not isinstance(responses, list)
        or len(responses) != request_count
    ):
        raise Tenant01EvidenceError(f"{card_id} 原始模型调用阶段不完整。")
    expected_stages = ("intake", "writer")
    request_hashes: list[str] = []
    response_hashes: list[str] = []
    for request_index, raw_response in enumerate(responses, start=1):
        if (
            not isinstance(raw_response, dict)
            or set(raw_response)
            != {
                "request_index",
                "transport_retries",
                "stage",
                "model",
                "request_sha256",
                "response_sha256",
                "response",
            }
            or type(raw_response.get("request_index")) is not int
            or raw_response.get("request_index") != request_index
            or type(raw_response.get("transport_retries")) is not int
            or raw_response.get("transport_retries") != 0
            or raw_response.get("stage") != expected_stages[request_index - 1]
            or raw_response.get("model") != TENANT01_PROVIDER_MODEL
        ):
            raise Tenant01EvidenceError(f"{card_id} 原始模型调用顺序或重试证据无效。")
        request_digest = raw_response.get("request_sha256")
        response_digest = raw_response.get("response_sha256")
        response = raw_response.get("response")
        if (
            not _sha256_text(request_digest)
            or not _sha256_text(response_digest)
            or not isinstance(response, dict)
            or not response
            or response.get("model") != TENANT01_PROVIDER_MODEL
            or _canonical_digest(response) != response_digest
        ):
            raise Tenant01EvidenceError(f"{card_id} 原始模型请求或响应摘要无效。")
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices:
            raise Tenant01EvidenceError(f"{card_id} 原始模型响应为空。")
        first_choice = choices[0]
        message = first_choice.get("message") if isinstance(first_choice, dict) else None
        if (
            not isinstance(message, dict)
            or not isinstance(message.get("content"), str)
            or not str(message["content"]).strip()
        ):
            raise Tenant01EvidenceError(f"{card_id} 原始模型响应为空。")
        request_hashes.append(str(request_digest))
        response_hashes.append(str(response_digest))
    return {
        "raw_bundle_version": TENANT01_RAW_BUNDLE_VERSION,
        "provider_request_count": request_count,
        "provider_model": TENANT01_PROVIDER_MODEL,
        "provider_stages": list(expected_stages),
        "request_hashes": request_hashes,
        "response_hashes": response_hashes,
    }


def _target_contract(card_id: str) -> tuple[ContentTarget, MediaFormat]:
    if card_id in {"P1", "cross_platform_douyin"}:
        return "douyin_video", "video"
    return "xiaohongshu_graphic", "graphic"


def _primary_product_contract(card_id: str) -> ContentProduct:
    if card_id == "P1":
        return "dressing_decision"
    if card_id == "P2":
        return "product_truth"
    if card_id == "P4_series1":
        return "local_response"
    return "brand_life_narrative"


def _plan_allowlists(
    snapshot: dict[str, object],
    *,
    card_id: str,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    raw_direction = snapshot.get("original_direction")
    raw_selections = raw_direction.get("selections") if isinstance(raw_direction, dict) else None
    if not isinstance(raw_selections, list):
        raise Tenant01EvidenceError(f"{card_id} 缺少冻结创作选择范围。")
    tones: list[str] = [ACCOUNT_BASELINE_TONE_ID]
    mechanisms: list[str] = []
    for raw_selection in raw_selections:
        if not isinstance(raw_selection, dict):
            raise Tenant01EvidenceError(f"{card_id} 冻结创作选择范围无效。")
        axis = raw_selection.get("axis")
        stable_id = raw_selection.get("stable_id")
        if not isinstance(axis, str) or not isinstance(stable_id, str) or not stable_id:
            raise Tenant01EvidenceError(f"{card_id} 冻结创作选择范围无效。")
        if axis == "style":
            tones.append(stable_id)
        elif axis == "mechanism":
            mechanisms.append(stable_id)
    return tuple(dict.fromkeys(tones)), tuple(dict.fromkeys(mechanisms))


def _immutable_fact_blocks(
    snapshot: dict[str, object],
    *,
    card_id: str,
) -> tuple[ImmutableFactBlock, ...]:
    raw_blocks = snapshot.get("immutable_product_fact_blocks")
    if not isinstance(raw_blocks, list):
        raise Tenant01EvidenceError(f"{card_id} 缺少冻结商品事实块。")
    blocks: list[ImmutableFactBlock] = []
    for raw_block in raw_blocks:
        if not isinstance(raw_block, dict) or set(raw_block) != {
            "fact_block_id",
            "fact_id",
            "canonical_text",
            "renderer_version",
            "visible_order",
        }:
            raise Tenant01EvidenceError(f"{card_id} 冻结商品事实块结构无效。")
        visible_order = raw_block.get("visible_order")
        if (
            not all(
                isinstance(raw_block.get(field), str)
                and bool(str(raw_block[field]).strip())
                for field in (
                    "fact_block_id",
                    "fact_id",
                    "canonical_text",
                    "renderer_version",
                )
            )
            or type(visible_order) is not int
            or visible_order < 1
        ):
            raise Tenant01EvidenceError(f"{card_id} 冻结商品事实块字段无效。")
        blocks.append(
            ImmutableFactBlock(
                fact_block_id=str(raw_block["fact_block_id"]),
                fact_id=str(raw_block["fact_id"]),
                canonical_text=str(raw_block["canonical_text"]),
                renderer_version=str(raw_block["renderer_version"]),
                visible_order=visible_order,
            )
        )
    if len({block.fact_block_id for block in blocks}) != len(blocks):
        raise Tenant01EvidenceError(f"{card_id} 冻结商品事实块重复。")
    return tuple(blocks)


def _compile_bound_delivery(
    snapshot: dict[str, object],
    *,
    card_id: str,
    primary_product: ContentProduct,
    kernel: CreativeKernelV1,
    publication: PublicationContractV2,
    product_value: ProductValueContract | None,
    expected_media_format: MediaFormat,
) -> CompiledDelivery:
    raw_account = snapshot.get("account_expression")
    if not isinstance(raw_account, dict) or not isinstance(
        raw_account.get("default_production_conditions"),
        str,
    ):
        raise Tenant01EvidenceError(f"{card_id} 缺少冻结制作条件。")
    try:
        envelope, media_program = frozen_media_contract(snapshot)
        products = frozen_product_facts(snapshot)
        blocks = _immutable_fact_blocks(snapshot, card_id=card_id)
    except (DomainError, GenerationFailed, TypeError, ValueError) as exc:
        raise Tenant01EvidenceError(
            f"{card_id} 冻结媒体或商品编译输入无效。"
        ) from exc
    expected_target, _ = _target_contract(card_id)
    expected_platform_shape = platform_shape(
        expected_target,
        expected_media_format,
    )
    if (
        envelope is None
        or media_program is None
        or products is None
        or envelope.media_format != expected_media_format
        or envelope.platform_shape != expected_platform_shape
    ):
        raise Tenant01EvidenceError(f"{card_id} 冻结媒体合同没有绑定发布目标。")
    trusted_fact_texts: list[tuple[str, str]] = []
    for unit in kernel.units:
        if unit.track != "trusted_fact":
            continue
        if len(unit.fact_refs) != 1:
            raise Tenant01EvidenceError(f"{card_id} 冻结可信事实单元无效。")
        trusted_fact_texts.append((unit.fact_refs[0], unit.text))
    try:
        return compile_delivery(
            DeliveryCompileInput(
                primary_product=primary_product,
                media_format=envelope.media_format,
                products=products,
                production_conditions=str(
                    raw_account["default_production_conditions"]
                ),
                allowed_resource_ids=envelope.resource_ids,
                immutable_fact_blocks=blocks,
                trusted_fact_texts=tuple(trusted_fact_texts),
                media_capability_envelope=envelope,
                media_program=media_program,
                product_value_contract=product_value,
                publication_contract=publication,
            ),
            kernel,
        )
    except (DomainError, GenerationFailed, TypeError, ValueError) as exc:
        raise Tenant01EvidenceError(
            f"{card_id} 无法从冻结输入重编译成品。"
        ) from exc


def compile_tenant01_snapshot_delivery(
    snapshot: dict[str, object],
    *,
    card_id: str,
) -> CompiledDelivery:
    """Deterministically rebuild one golden-card artifact from its snapshot."""

    if (
        snapshot.get("delivery_compiler_version")
        != DELIVERY_COMPILER_VERSION
        or snapshot.get("writer_model") != TENANT01_PROVIDER_MODEL
    ):
        raise Tenant01EvidenceError(
            f"{card_id} 编译器或 Writer 模型版本漂移。"
        )
    raw_publication = snapshot.get("publication_contract")
    try:
        plan = creative_plan_from_document(snapshot.get("creative_plan_v2"))
        publication = publication_contract_from_document(raw_publication)
        kernel = kernel_from_document(snapshot.get("creative_kernel_v2"))
    except (DomainError, TypeError, ValueError) as exc:
        raise Tenant01EvidenceError(
            f"{card_id} 冻结编译合同结构无效。"
        ) from exc
    computed_kernel_digest = kernel_digest(kernel)
    if (
        publication_contract_digest(publication)
        != snapshot.get("publication_contract_digest")
        or _canonical_digest(raw_publication)
        != snapshot.get("publication_contract_digest")
        or computed_kernel_digest != snapshot.get("expression_plan_digest")
        or computed_kernel_digest != snapshot.get("reviewed_kernel_digest")
        or creative_units_digest(kernel)
        != snapshot.get("reviewed_creative_digest")
    ):
        raise Tenant01EvidenceError(f"{card_id} 冻结编译合同摘要无效。")
    raw_product_value = snapshot.get("product_value_contract")
    raw_product_digest = snapshot.get("product_value_contract_digest")
    product_value: ProductValueContract | None = None
    if raw_product_value is None and raw_product_digest is not None:
        raise Tenant01EvidenceError(f"{card_id} 商品语义计划结构无效。")
    if raw_product_value is not None:
        if not _sha256_text(raw_product_digest):
            raise Tenant01EvidenceError(f"{card_id} 商品语义计划结构无效。")
        try:
            product_value = product_value_contract_from_document(
                raw_product_value
            )
        except DomainError as exc:
            raise Tenant01EvidenceError(
                f"{card_id} 商品语义计划结构无效。"
            ) from exc
        if (
            product_value_contract_digest(product_value)
            != raw_product_digest
        ):
            raise Tenant01EvidenceError(f"{card_id} 商品语义计划摘要无效。")
    _, expected_media_format = _target_contract(card_id)
    return _compile_bound_delivery(
        snapshot,
        card_id=card_id,
        primary_product=plan.primary_value,
        kernel=kernel,
        publication=publication,
        product_value=product_value,
        expected_media_format=expected_media_format,
    )


def _artifact_binding(
    path: Path,
    *,
    card_id: str,
) -> tuple[
    dict[str, object],
    dict[str, object],
    dict[str, object],
    dict[str, str],
]:
    document = _json_object(path)
    if document.get("suite_version") != TENANT01_SUITE_VERSION or document.get("card_id") != card_id:
        raise Tenant01EvidenceError(f"{card_id} 成品文件绑定到了另一张卡。")
    outline = document.get("outline")
    body = document.get("body")
    if not isinstance(outline, str) or not outline.strip():
        raise Tenant01EvidenceError(f"{card_id} 缺少可见标题。")
    if not isinstance(body, str) or not body.strip():
        raise Tenant01EvidenceError(f"{card_id} 缺少完整成品。")
    expected_visible = visible_digest(outline, body)
    if document.get("visible_digest") != expected_visible:
        raise Tenant01EvidenceError(f"{card_id} visible_digest 无法复算。")
    persistence: dict[str, object] = {
        field: _uuid_text(document.get(field), label=f"{card_id} {field}")
        for field in ("task_id", "run_id", "version_id")
    }
    version = document.get("version")
    if type(version) is not int or version < 1:
        raise Tenant01EvidenceError(f"{card_id} version 缺少正式正整数版本。")
    persistence["version"] = version
    snapshot = document.get("formal_snapshot")
    if not isinstance(snapshot, dict):
        raise Tenant01EvidenceError(f"{card_id} 缺少正式任务快照。")
    user_premise = snapshot.get("user_premise")
    if not isinstance(user_premise, str) or not user_premise.strip():
        raise Tenant01EvidenceError(f"{card_id} 缺少冻结用户原始输入。")
    packet = snapshot.get("brand_context_packet")
    if not isinstance(packet, dict) or packet.get("packet_version") != "brand-context-packet-v2":
        raise Tenant01EvidenceError(f"{card_id} 没有绑定当前品牌发布投影。")
    projection_id = _uuid_text(
        packet.get("publication_projection_id"),
        label=f"{card_id} publication_projection_id",
    )
    projection_version = packet.get("publication_projection_version")
    projection_digest = packet.get("publication_projection_digest")
    packet_digest = packet.get("packet_digest")
    raw_segments = packet.get("segments")
    if (
        type(projection_version) is not int
        or projection_version < 1
        or not _sha256_text(projection_digest)
        or not _sha256_text(packet_digest)
        or not isinstance(raw_segments, list)
        or not raw_segments
    ):
        raise Tenant01EvidenceError(f"{card_id} 发布投影版本或摘要无效。")
    packet_segments: list[dict[str, object]] = []
    for raw_segment in raw_segments:
        if not isinstance(raw_segment, dict):
            raise Tenant01EvidenceError(f"{card_id} 发布投影来源无效。")
        segment = cast(dict[str, object], raw_segment)
        for field in (
            "segment_id",
            "source_document_id",
            "source_document_version_id",
        ):
            _uuid_text(segment.get(field), label=f"{card_id} {field}")
        exact_text = segment.get("exact_text")
        if (
            not isinstance(exact_text, str)
            or not exact_text.strip()
            or segment.get("semantic_kind") not in {"brand_fact", "expression_constraint", "creative_method"}
            or segment.get("evidence_level") != "confirmed_publication"
            or not str(segment.get("source_id", "")).strip()
            or not str(segment.get("source_version", "")).strip()
            or not str(segment.get("visibility_scope", "")).strip()
            or not _sha256_text(segment.get("source_digest"))
            or segment.get("digest") != hashlib.sha256(exact_text.encode()).hexdigest()
        ):
            raise Tenant01EvidenceError(f"{card_id} 发布投影来源或正文摘要无效。")
        packet_segments.append(segment)
    if packet_digest != brand_context_packet_digest(
        projection_id=projection_id,
        projection_version=projection_version,
        projection_digest=str(projection_digest),
        segments=packet_segments,
    ):
        raise Tenant01EvidenceError(f"{card_id} 品牌上下文摘要无法复算。")
    raw_publication = snapshot.get("publication_contract")
    publication_digest = snapshot.get("publication_contract_digest")
    if not isinstance(raw_publication, dict) or not _sha256_text(publication_digest):
        raise Tenant01EvidenceError(f"{card_id} 缺少冻结发布责任合同。")
    try:
        publication = publication_contract_from_document(raw_publication)
    except DomainError as exc:
        raise Tenant01EvidenceError(f"{card_id} 冻结发布责任合同结构无效。") from exc
    if (
        publication.contract_version != PUBLICATION_CONTRACT_VERSION
        or publication_contract_digest(publication) != publication_digest
        or _canonical_digest(raw_publication) != publication_digest
        or publication.publication_projection_id != projection_id
        or publication.publication_projection_version != projection_version
        or publication.publication_projection_digest != projection_digest
    ):
        raise Tenant01EvidenceError(f"{card_id} 发布责任合同来源或摘要无效。")
    raw_plan = snapshot.get("creative_plan_v2")
    if not isinstance(raw_plan, dict):
        raise Tenant01EvidenceError(f"{card_id} 缺少冻结创作计划。")
    try:
        plan = creative_plan_from_document(raw_plan)
    except DomainError as exc:
        raise Tenant01EvidenceError(f"{card_id} 冻结创作计划结构无效。") from exc
    expected_target, expected_media_format = _target_contract(card_id)
    expected_platform_shape = platform_shape(
        expected_target,
        expected_media_format,
    )
    if snapshot.get("publishing_target") != expected_target:
        raise Tenant01EvidenceError(f"{card_id} 发布目标没有绑定黄金卡。")
    allowed_tones, allowed_mechanisms = _plan_allowlists(
        snapshot,
        card_id=card_id,
    )
    try:
        validate_creative_plan(
            plan,
            user_turns=(user_premise,),
            allowed_tone_ids=allowed_tones,
            allowed_mechanism_ids=allowed_mechanisms,
            expected_primary_value=_primary_product_contract(card_id),
            expected_platform_shape=expected_platform_shape,
        )
    except DomainError as exc:
        raise Tenant01EvidenceError(f"{card_id} 冻结创作计划没有绑定正式选择范围。") from exc
    expected_topic = "\n".join(item.strip() for item in plan.topic_spans if item.strip())
    if (
        plan.plan_version != PLAN_VERSION
        or publication.primary_product != plan.primary_value
        or publication.topic_origin != plan.topic_origin
        or any(topic not in user_premise for topic in plan.topic_spans)
        or (plan.topic_origin == "explicit_user" and publication.topic != expected_topic)
    ):
        raise Tenant01EvidenceError(f"{card_id} 发布责任合同没有绑定当前创作计划。")
    source_candidates = user_fact_candidates((user_premise,))
    if len(publication.intake_spans) != len(source_candidates) or any(
        (
            span.source_id,
            span.exact_text,
            span.turn_index,
            span.start_offset,
            span.end_offset,
            span.start_byte,
            span.end_byte,
        )
        != (
            candidate.source_id,
            candidate.exact_text,
            candidate.turn_index,
            candidate.start_offset,
            candidate.end_offset,
            candidate.start_byte,
            candidate.end_byte,
        )
        for span, candidate in zip(
            publication.intake_spans,
            source_candidates,
            strict=True,
        )
    ):
        raise Tenant01EvidenceError(f"{card_id} 发布责任合同输入跨度没有绑定用户原文。")
    profile_id = snapshot.get("account_expression_profile_id")
    profile_version = snapshot.get("account_expression_profile_version")
    if (
        _uuid_text(profile_id, label=f"{card_id} source_profile_id") != publication.source_profile_id
        or type(profile_version) is not int
        or profile_version < 1
        or profile_version != publication.source_profile_version
    ):
        raise Tenant01EvidenceError(f"{card_id} 发布责任合同没有绑定当前画像版本。")
    raw_account = snapshot.get("account_expression")
    if not isinstance(raw_account, dict):
        raise Tenant01EvidenceError(f"{card_id} 缺少冻结账号表达来源。")
    account_fields = (
        "identity_position",
        "audience_relationship",
        "content_territories",
        "authority_boundary",
        "default_production_conditions",
    )
    if (
        _uuid_text(raw_account.get("profile_id"), label=f"{card_id} account profile_id")
        != publication.source_profile_id
        or type(raw_account.get("version")) is not int
        or raw_account.get("version") != publication.source_profile_version
        or any(
            not isinstance(raw_account.get(field), str)
            or not str(raw_account[field]).strip()
            for field in account_fields
        )
    ):
        raise Tenant01EvidenceError(f"{card_id} 冻结账号表达来源无效。")
    raw_frame = snapshot.get("narrative_frame")
    try:
        frame = frame_from_document(raw_frame)
    except DomainError as exc:
        raise Tenant01EvidenceError(f"{card_id} 冻结事实轨结构无效。") from exc
    user_fact_by_id = {fact.source_id: fact.exact_text for fact in frame.user_facts}
    actuality_spans = {
        span.source_id: span.exact_text for span in publication.intake_spans if span.role == "observable_actuality"
    }
    if (
        set(publication.frozen_fact_refs) != set(frame.allowed_fact_ids)
        or actuality_spans != user_fact_by_id
        or tuple(publication.known_conditions) != tuple(dict.fromkeys(user_fact_by_id.values()))
        or any(
            span.role
            != (
                "observable_actuality"
                if span.source_id in user_fact_by_id
                else "creation_instruction"
            )
            for span in publication.intake_spans
        )
        or any(
            span.source_id in user_fact_by_id
            for span in publication.intake_spans
            if span.role != "observable_actuality"
        )
    ):
        raise Tenant01EvidenceError(f"{card_id} 现实事实与创作指令边界漂移。")
    product_value = None
    raw_product_value = snapshot.get("product_value_contract")
    product_value_digest = snapshot.get("product_value_contract_digest")
    if raw_product_value is None and product_value_digest is None:
        if (
            publication.primary_product in {"product_truth", "visual_styling_story"}
            or publication.product_value_contract_digest is not None
        ):
            raise Tenant01EvidenceError(f"{card_id} 商品语义计划绑定漂移。")
    elif not isinstance(raw_product_value, dict) or not _sha256_text(product_value_digest):
        raise Tenant01EvidenceError(f"{card_id} 商品语义计划结构无效。")
    else:
        try:
            product_value = product_value_contract_from_document(raw_product_value)
        except DomainError as exc:
            raise Tenant01EvidenceError(f"{card_id} 商品语义计划结构无效。") from exc
        if (
            product_value_contract_digest(product_value) != product_value_digest
            or publication.product_value_contract_digest != product_value_digest
            or product_value.primary_product != publication.primary_product
        ):
            raise Tenant01EvidenceError(f"{card_id} 商品语义计划摘要无效。")
    expected_publication = build_publication_contract(
        primary_product=plan.primary_value,
        topic_spans=plan.topic_spans,
        topic_origin=plan.topic_origin,
        known_conditions=tuple(fact.exact_text for fact in frame.user_facts),
        frozen_fact_refs=tuple(frame.allowed_fact_ids),
        intake_spans=publication.intake_spans,
        account_identity=str(raw_account["identity_position"]),
        account_audience=str(raw_account["audience_relationship"]),
        account_attention=str(raw_account["content_territories"]),
        account_response_boundary=str(raw_account["authority_boundary"]),
        source_profile_id=str(raw_account["profile_id"]),
        source_profile_version=cast(int, raw_account["version"]),
        publication_projection_id=projection_id,
        publication_projection_version=projection_version,
        publication_projection_digest=str(projection_digest),
        product_value_contract_digest=(
            product_value_contract_digest(product_value)
            if product_value is not None
            else None
        ),
    )
    if _canonical_digest(
        publication_contract_document(expected_publication)
    ) != _canonical_digest(raw_publication):
        raise Tenant01EvidenceError(f"{card_id} 发布责任合同语义没有绑定冻结输入。")
    raw_kernel = snapshot.get("creative_kernel_v2")
    expression_plan_digest = snapshot.get("expression_plan_digest")
    reviewed_kernel_digest = snapshot.get("reviewed_kernel_digest")
    reviewed_creative_digest = snapshot.get("reviewed_creative_digest")
    if (
        not isinstance(raw_kernel, dict)
        or not _sha256_text(expression_plan_digest)
        or not _sha256_text(reviewed_kernel_digest)
        or not _sha256_text(reviewed_creative_digest)
    ):
        raise Tenant01EvidenceError(f"{card_id} 缺少冻结创作单元。")
    try:
        kernel = kernel_from_document(raw_kernel)
    except (DomainError, TypeError, ValueError) as exc:
        raise Tenant01EvidenceError(f"{card_id} 冻结创作单元无效。") from exc
    computed_kernel_digest = kernel_digest(kernel)
    if (
        computed_kernel_digest != expression_plan_digest
        or computed_kernel_digest != reviewed_kernel_digest
        or creative_units_digest(kernel) != reviewed_creative_digest
    ):
        raise Tenant01EvidenceError(f"{card_id} 冻结创作单元摘要无效。")
    for unit in kernel.writable_units:
        haystack = outline if unit.purpose == "title" else body
        if unit.text not in haystack:
            raise Tenant01EvidenceError(f"{card_id} 最终成品没有绑定冻结 Writer 单元。")
    if (
        snapshot.get("delivery_compiler_version") != DELIVERY_COMPILER_VERSION
        or snapshot.get("writer_model") != TENANT01_PROVIDER_MODEL
    ):
        raise Tenant01EvidenceError(f"{card_id} 编译器或 Writer 模型版本漂移。")
    compiled = _compile_bound_delivery(
        snapshot,
        card_id=card_id,
        primary_product=plan.primary_value,
        kernel=kernel,
        publication=publication,
        product_value=product_value,
        expected_media_format=expected_media_format,
    )
    expected_production = asdict(compiled.production)
    expected_provenance = {
        field: list(sources)
        for field, sources in compiled.visible_provenance.items()
    }
    if (
        compiled.outline != outline
        or compiled.body != body
        or document.get("production") != expected_production
        or snapshot.get("visible_provenance") != expected_provenance
        or snapshot.get("delivery_resource_refs")
        != list(compiled.resource_refs)
    ):
        raise Tenant01EvidenceError(f"{card_id} 最终 artifact 不是冻结输入的确定性编译结果。")
    if expected_media_format == "video":
        body_region = "\n".join(
            (
                str(expected_production["natural_guide"]),
                str(expected_production["spoken_lines"]),
            )
        )
        media_fields: tuple[str, ...] = (
            "cover_or_first_frame",
            "viewing_flow",
            "visual_actions",
            "subtitles",
            "sound_and_production",
        )
    else:
        body_region = "\n".join(
            (
                str(expected_production["natural_guide"]),
                str(expected_production["full_body"]),
            )
        )
        media_fields = (
            "hero_image",
            "image_sequence",
            "layout_and_production",
        )
    media_region = "\n".join(
        str(expected_production[field]) for field in media_fields
    )
    optional_capture = expected_production.get("optional_capture_suggestion")
    if isinstance(optional_capture, str) and optional_capture:
        media_region = f"{media_region}\n{optional_capture}"
    review_regions = {
        "title": outline,
        "body": body_region,
        "media": media_region,
        "caption": str(expected_production["release_caption_and_interaction"]),
    }
    return (
        document,
        persistence,
        {
            "projection_id": projection_id,
            "projection_version": projection_version,
            "projection_digest": projection_digest,
            "brand_context_packet_digest": packet_digest,
            "creative_plan_version": plan.plan_version,
            "publication_contract_version": publication.contract_version,
            "publication_contract_digest": publication_digest,
            "expression_plan_digest": expression_plan_digest,
            "reviewed_kernel_digest": reviewed_kernel_digest,
            "reviewed_creative_digest": reviewed_creative_digest,
            "source_profile_id": publication.source_profile_id,
            "source_profile_version": publication.source_profile_version,
        },
        review_regions,
    )


def _sha256_text(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _validate_review(
    review: Tenant01HumanReview,
    *,
    artifact_sha256: str,
    visible_digest_value: str,
    review_regions: dict[str, str],
) -> dict[str, object]:
    if (
        review.artifact_sha256 != artifact_sha256
        or review.visible_digest != visible_digest_value
    ):
        raise Tenant01EvidenceError(f"{review.card_id} 人工审阅没有预先绑定当前 artifact。")
    if set(review.scores) != set(TENANT01_REVIEW_DIMENSIONS):
        raise Tenant01EvidenceError(f"{review.card_id} 人工评分维度不完整。")
    if any(type(score) is not int or not 1 <= score <= 5 for score in review.scores.values()):
        raise Tenant01EvidenceError(f"{review.card_id} 人工评分必须为 1—5。")
    for dimension in TENANT01_REVIEW_DIMENSIONS:
        if review.scores[dimension] < 4:
            raise Tenant01EvidenceError(f"{review.card_id} 未通过 {dimension} 硬门。")
    if set(review.hard_boundaries) != set(TENANT01_HARD_BOUNDARIES) or any(
        value is not True for value in review.hard_boundaries.values()
    ):
        raise Tenant01EvidenceError(f"{review.card_id} 事实或资源硬边界未通过。")
    if set(review.excerpts) != {"title", "body", "media", "caption"}:
        raise Tenant01EvidenceError(f"{review.card_id} 人工审阅引用不完整。")
    normalized_excerpts: list[str] = []
    for field, excerpt in review.excerpts.items():
        if not isinstance(excerpt, str):
            raise Tenant01EvidenceError(f"{review.card_id} {field} 引用缺少有意义文本。")
        normalized = "".join(
            character.casefold()
            for character in excerpt
            if character.isalnum()
        )
        if len(normalized) < 6:
            raise Tenant01EvidenceError(f"{review.card_id} {field} 引用缺少有意义文本。")
        if excerpt not in review_regions[field]:
            raise Tenant01EvidenceError(f"{review.card_id} {field} 引用不在对应成品分区中。")
        normalized_excerpts.append(normalized)
    if len(set(normalized_excerpts)) != len(normalized_excerpts):
        raise Tenant01EvidenceError(f"{review.card_id} 人工审阅引用不能跨分区复用。")
    if review.verdict != "PASS":
        raise Tenant01EvidenceError(f"{review.card_id} 人工二元结论不是 PASS。")
    if set(review.demonstration_checks) != set(TENANT01_DEMONSTRATION_CHECKS) or any(
        value is not True for value in review.demonstration_checks.values()
    ):
        raise Tenant01EvidenceError(f"{review.card_id} 可演示成品检查未通过。")
    if set(review.comparison) != set(TENANT01_COMPARISON_FIELDS) or any(
        not isinstance(value, str) or not value.strip()
        for value in review.comparison.values()
    ):
        raise Tenant01EvidenceError(f"{review.card_id} 跨卡比较依据不完整。")
    if not review.brand_basis.strip():
        raise Tenant01EvidenceError(f"{review.card_id} 缺少品牌或账号关系来源。")
    if not review.notes.strip():
        raise Tenant01EvidenceError(f"{review.card_id} 人工审阅结论为空。")
    return {
        "card_id": review.card_id,
        "artifact_file": review.artifact_file,
        "artifact_sha256": review.artifact_sha256,
        "visible_digest": review.visible_digest,
        "scores": review.scores,
        "excerpts": review.excerpts,
        "hard_boundaries": review.hard_boundaries,
        "demonstration_checks": review.demonstration_checks,
        "comparison": review.comparison,
        "brand_basis": review.brand_basis,
        "verdict": review.verdict,
        "notes": review.notes,
    }


def _assert_cross_card_distinct(
    artifacts: list[dict[str, object]],
) -> None:
    owners: dict[str, str] = {}
    for artifact in artifacts:
        card_id = str(artifact["card_id"])
        snapshot = artifact.get("formal_snapshot")
        if not isinstance(snapshot, dict):
            raise Tenant01EvidenceError(f"{card_id} 缺少正式任务快照。")
        raw_kernel = snapshot.get("creative_kernel_v2")
        raw_publication = snapshot.get("publication_contract")
        if not isinstance(raw_kernel, dict) or not isinstance(raw_publication, dict):
            raise Tenant01EvidenceError(f"{card_id} 缺少发布创作证据。")
        try:
            kernel = kernel_from_document(raw_kernel)
            publication = publication_contract_from_document(raw_publication)
        except (DomainError, TypeError, ValueError) as exc:
            raise Tenant01EvidenceError(f"{card_id} 发布创作证据无效。") from exc
        protected_account_texts = tuple(
            "".join(value.split())
            for value in (
                publication.account_identity,
                publication.account_audience,
                publication.account_attention,
                publication.account_response_boundary,
            )
            if len("".join(value.split())) >= 12
        )
        for unit in kernel.writable_units:
            if unit.text_source != "writer":
                continue
            normalized_unit = "".join(unit.text.split())
            if any(source in normalized_unit for source in protected_account_texts):
                raise Tenant01EvidenceError(f"{card_id} 把账号编辑许可原句复制进了成品。")
            for paragraph in unit.text.split("\n\n"):
                line = " ".join(paragraph.split())
                if len(line) < 32:
                    continue
                previous = owners.get(line)
                if previous is not None and previous != card_id:
                    raise Tenant01EvidenceError(f"{previous} 与 {card_id} 存在非必要 Writer 完整段落重复。")
                owners[line] = card_id


def _assert_preflight(path: Path) -> dict[str, object]:
    document = _json_object(path)
    if (
        document.get("card_id") != "P5_no_media"
        or document.get("provider_calls") != 0
        or document.get("persistence_delta") != [0, 0, 0]
        or document.get("result_kind") != "question"
    ):
        raise Tenant01EvidenceError("P5 无图反证未保持 0/0/0 与零模型调用。")
    return document


def _assert_dm01(path: Path) -> dict[str, object]:
    document = _json_object(path)
    required = {
        "task_id",
        "v1_run_id",
        "v1_version_id",
        "v2_run_id",
        "v2_version_id",
    }
    identifiers = document.get("identifiers")
    if not isinstance(identifiers, dict) or set(identifiers) != required:
        raise Tenant01EvidenceError("DM01 证据缺少 V1/V2 正式标识。")
    for field in required:
        _uuid_text(identifiers[field], label=f"DM01 {field}")
    if (
        document.get("model") != "dm01-rule-compiler-v1"
        or document.get("provider_calls") != 0
        or document.get("provider_usage") not in ({}, None)
        or document.get("rules_total") != 13
        or document.get("generation_rules") != 11
        or document.get("v1_v2_v1") is not True
        or document.get("inventory_conservation") is not True
        or document.get("ai_generated") is not False
    ):
        raise Tenant01EvidenceError("DM01 隔离卡没有满足纯文字、零模型和库存守恒合同。")
    return document


def _generation_ledger(
    path: Path,
    *,
    implementation_sha: str,
) -> dict[str, dict[str, object]]:
    if path.stat().st_mode & 0o222:
        raise Tenant01EvidenceError("生成账本必须在 generate 阶段封为只读。")
    document = _json_object(path)
    if set(document) != {
        "ledger_version",
        "suite_version",
        "implementation_sha",
        "provider_config",
        "cards",
    }:
        raise Tenant01EvidenceError("生成账本结构漂移。")
    provider = document.get("provider_config")
    raw_cards = document.get("cards")
    if (
        document.get("ledger_version") != TENANT01_GENERATION_LEDGER_VERSION
        or document.get("suite_version") != TENANT01_SUITE_VERSION
        or document.get("implementation_sha") != implementation_sha
        or provider
        != {
            "model": TENANT01_PROVIDER_MODEL,
            "temperature": 0,
            "max_retries": 0,
        }
        or not isinstance(raw_cards, list)
    ):
        raise Tenant01EvidenceError("生成账本没有绑定当前实现或 provider。")
    records: dict[str, dict[str, object]] = {}
    required_fields = {
        "card_id",
        "task_id",
        "run_id",
        "version_id",
        "version",
        "artifact_file",
        "artifact_sha256",
        "visible_digest",
        "raw_response_file",
        "raw_response_sha256",
        "provider_stages",
        "request_hashes",
        "response_hashes",
    }
    for raw_record in raw_cards:
        if not isinstance(raw_record, dict) or set(raw_record) != required_fields:
            raise Tenant01EvidenceError("生成账本逐卡结构漂移。")
        card_id = raw_record.get("card_id")
        version = raw_record.get("version")
        stages = raw_record.get("provider_stages")
        request_hashes = raw_record.get("request_hashes")
        response_hashes = raw_record.get("response_hashes")
        if (
            not isinstance(card_id, str)
            or card_id not in TENANT01_CARD_IDS
            or card_id in records
            or type(version) is not int
            or version < 1
            or raw_record.get("artifact_file") != f"{card_id}.artifact.json"
            or raw_record.get("raw_response_file") != f"{card_id}.raw.json"
            or not _sha256_text(raw_record.get("artifact_sha256"))
            or not _sha256_text(raw_record.get("visible_digest"))
            or not _sha256_text(raw_record.get("raw_response_sha256"))
            or not isinstance(stages, list)
            or tuple(stages) != ("intake", "writer")
            or not isinstance(request_hashes, list)
            or not isinstance(response_hashes, list)
            or len(request_hashes) != len(stages)
            or len(response_hashes) != len(stages)
            or any(not _sha256_text(value) for value in (*request_hashes, *response_hashes))
        ):
            raise Tenant01EvidenceError(f"{card_id} 生成账本字段无效。")
        for field in ("task_id", "run_id", "version_id"):
            _uuid_text(raw_record.get(field), label=f"{card_id} ledger {field}")
        records[card_id] = cast(dict[str, object], raw_record)
    if set(records) != TENANT01_CARD_IDS:
        raise Tenant01EvidenceError("生成账本黄金卡覆盖不完整。")
    return records


def write_tenant01_evidence(
    root: Path,
    *,
    implementation_sha: str,
    schema_revision: str,
    image_digest: str,
    source_manifest_digest: str,
    artifacts: tuple[Tenant01ArtifactInput, ...],
    reviews: tuple[Tenant01HumanReview, ...],
    p5_preflight_file: str,
    dm01_file: str,
) -> None:
    if len(implementation_sha) != 40 or any(character not in "0123456789abcdef" for character in implementation_sha):
        raise Tenant01EvidenceError("实现 SHA 无效。")
    if not schema_revision or not image_digest.startswith("sha256:") or not _sha256_text(source_manifest_digest):
        raise Tenant01EvidenceError("schema 或镜像 digest 未冻结。")
    if root.stat().st_mode & 0o077:
        raise Tenant01EvidenceError("证据目录权限必须为 0700。")
    if {item.card_id for item in artifacts} != TENANT01_CARD_IDS:
        raise Tenant01EvidenceError("黄金卡覆盖不完整。")
    if len({item.card_id for item in artifacts}) != len(artifacts):
        raise Tenant01EvidenceError("黄金卡重复。")
    review_by_card = {review.card_id: review for review in reviews}
    if set(review_by_card) != TENANT01_CARD_IDS or len(review_by_card) != len(reviews):
        raise Tenant01EvidenceError("人工审阅覆盖不完整或重复。")
    ledger_path = _private_child(root, TENANT01_GENERATION_LEDGER_FILE)
    ledger_by_card = _generation_ledger(
        ledger_path,
        implementation_sha=implementation_sha,
    )

    artifact_records: list[dict[str, object]] = []
    review_records: list[dict[str, object]] = []
    bound_artifacts: list[dict[str, object]] = []
    projection_bindings: list[dict[str, object]] = []
    for item in artifacts:
        artifact_path = _private_child(root, item.artifact_file)
        raw_path = _private_child(root, item.raw_response_file)
        raw_binding = _raw_binding(raw_path, card_id=item.card_id)
        artifact, persistence, projection, review_regions = _artifact_binding(
            artifact_path,
            card_id=item.card_id,
        )
        artifact_sha256 = sha256_file(artifact_path)
        raw_response_sha256 = sha256_file(raw_path)
        review = review_by_card[item.card_id]
        if review.artifact_file != item.artifact_file:
            raise Tenant01EvidenceError(f"{item.card_id} 人工审阅引用了另一文件。")
        validated_review = _validate_review(
            review,
            artifact_sha256=artifact_sha256,
            visible_digest_value=str(artifact["visible_digest"]),
            review_regions=review_regions,
        )
        expected_ledger_record = {
            "card_id": item.card_id,
            **persistence,
            "artifact_file": item.artifact_file,
            "artifact_sha256": artifact_sha256,
            "visible_digest": artifact["visible_digest"],
            "raw_response_file": item.raw_response_file,
            "raw_response_sha256": raw_response_sha256,
            "provider_stages": raw_binding["provider_stages"],
            "request_hashes": raw_binding["request_hashes"],
            "response_hashes": raw_binding["response_hashes"],
        }
        if ledger_by_card[item.card_id] != expected_ledger_record:
            raise Tenant01EvidenceError(f"{item.card_id} 文件不再匹配只读生成账本。")
        bound_artifacts.append(artifact)
        projection_bindings.append(projection)
        artifact_records.append(
            {
                "card_id": item.card_id,
                "artifact_file": item.artifact_file,
                "artifact_sha256": artifact_sha256,
                "raw_response_file": item.raw_response_file,
                "raw_response_sha256": raw_response_sha256,
                **raw_binding,
                "visible_digest": artifact["visible_digest"],
                "publication_projection": projection,
                **persistence,
            }
        )
        review_records.append(validated_review)

    for field in ("task_id", "run_id", "version_id"):
        values = [str(record[field]) for record in artifact_records]
        if len(set(values)) != len(values):
            raise Tenant01EvidenceError(f"十一张卡复用了同一个 {field}。")
    _assert_cross_card_distinct(bound_artifacts)
    projection_keys = {
        (
            str(item["projection_id"]),
            int(cast(int, item["projection_version"])),
            str(item["projection_digest"]),
        )
        for item in projection_bindings
    }
    if len(projection_keys) != 1:
        raise Tenant01EvidenceError("十一张卡没有使用同一个已确认品牌发布投影。")

    p5_path = _private_child(root, p5_preflight_file)
    dm01_path = _private_child(root, dm01_file)
    _assert_preflight(p5_path)
    _assert_dm01(dm01_path)
    _write_private_json(
        root / "human-review.json",
        {
            "review_contract": "TENANT-01-HUMAN-REVIEW-V1",
            "reviews": review_records,
            "hard_boundary_violations": 0,
            "all_cards_binary_pass": True,
            "all_dimensions_at_least_four": True,
        },
    )
    _write_private_json(
        root / "manifest.json",
        {
            "manifest_version": "TENANT-01-EVIDENCE-V1",
            "implementation_sha": implementation_sha,
            "schema_revision": schema_revision,
            "image_digest": image_digest,
            "source_manifest_digest": source_manifest_digest,
            "generation_ledger": {
                "file": TENANT01_GENERATION_LEDGER_FILE,
                "sha256": sha256_file(ledger_path),
            },
            "publication_projection": {
                "id": next(iter(projection_keys))[0],
                "version": next(iter(projection_keys))[1],
                "digest": next(iter(projection_keys))[2],
            },
            "provider_config": {
                "model": TENANT01_PROVIDER_MODEL,
                "temperature": 0,
                "max_retries": 0,
            },
            "artifacts": artifact_records,
            "p5_preflight": {
                "file": p5_preflight_file,
                "sha256": sha256_file(p5_path),
            },
            "dm01": {"file": dm01_file, "sha256": sha256_file(dm01_path)},
        },
    )
    files = sorted(path for path in root.iterdir() if path.is_file() and path.name != "SHA256SUMS")
    checksum = "".join(f"{sha256_file(path)}  {path.name}\n" for path in files)
    _write_private_bytes(root / "SHA256SUMS", checksum.encode())


def _write_private_json(path: Path, value: object) -> None:
    payload = (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode()
    _write_private_bytes(path, payload)


def _write_private_bytes(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        remaining = memoryview(payload)
        while remaining:
            written = os.write(descriptor, remaining)
            remaining = remaining[written:]
    finally:
        os.close(descriptor)
    path.chmod(0o600)
