from __future__ import annotations

import argparse
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import psycopg
import pytest

from src.brain.content_service import ContentService
from src.infrastructure.postgres_repository import PostgresContentRepository
from src.infrastructure.tenant_lifecycle import (
    TENANT_LIFECYCLE_CONTRACT_VERSION,
    TenantLifecycleClassifier,
    TenantLifecyclePlan,
)
from src.infrastructure.tenant_source_importer import TenantSourceImporter
from src.infrastructure.workbench_repository import PostgresWorkbenchRepository
from src.shared.account_editorial_lens import (
    ACCOUNT_EDITORIAL_LENS_V1_VERSION,
    ACCOUNT_EDITORIAL_LENS_V2_VERSION,
    ACCOUNT_EDITORIAL_LENS_V3_VERSION,
    ACCOUNT_EDITORIAL_LENS_VERSION,
    AccountEditorialLensV1,
    AccountEditorialLensV2,
    AccountEditorialLensV3,
    account_editorial_lens_digest,
    account_editorial_lens_document,
    account_editorial_lens_from_document,
    build_account_editorial_lens,
)
from src.shared.brand_publication import (
    brand_context_packet_digest,
    brand_context_packet_v3_digest,
)
from src.shared.content_snapshot import (
    frozen_media_contract,
    frozen_product_facts,
    visible_context_basis,
)
from src.shared.creative_kernel import (
    KERNEL_VERSION,
    OBSERVATION_ONLY_PROGRAM,
    CreativeKernelV1,
    build_creative_kernel_v5,
    build_kernel_skeleton,
    creative_units_digest,
    kernel_digest,
    kernel_document,
    kernel_from_document,
)
from src.shared.creative_plan import (
    ACCOUNT_BASELINE_TONE_ID,
    TopicOrigin,
    build_creative_plan,
    creative_plan_document,
    platform_shape,
)
from src.shared.delivery_compiler import (
    DELIVERY_COMPILER_V5_VERSION,
    DELIVERY_COMPILER_VERSION,
    DeliveryCompileInput,
    compile_delivery,
)
from src.shared.errors import DomainError, GenerationFailed
from src.shared.factual_basis import (
    FrozenFactRecord,
    ImmutableFactBlock,
    brand_fact_records,
    build_product_fact_packet,
    immutable_fact_blocks_document,
    immutable_product_fact_blocks,
    product_fact_records,
)
from src.shared.media_program import (
    build_media_capability_envelope,
    media_envelope_digest,
    media_envelope_document,
    media_program_digest,
    media_program_document,
    select_media_program,
)
from src.shared.narrative import (
    frame_document,
    frame_from_document,
    new_frame,
    user_fact_candidates,
    visible_digest,
)
from src.shared.product_value import (
    P2ProductDecisionBasisV2,
    build_product_decision_basis_v2,
    build_product_value_contract,
    product_value_contract_digest,
    product_value_contract_document,
    product_value_contract_from_document,
)
from src.shared.publication_contract import (
    NEGATIVE_SAFETY_RULE_IDS,
    PUBLICATION_CONTRACT_VERSION,
    AccountEditorialPermissionV3,
    BrandContextUseV3,
    PlatformDirectionV3,
    ProductDecisionBasisRefV2,
    PublicationContractV2,
    PublicationInputSpanV1,
    build_publication_contract,
    build_publication_contract_v3,
    negative_safety_contract_text,
    publication_contract_digest,
    publication_contract_document,
    publication_contract_from_document,
)
from src.shared.tenant_brand_sources import (
    classify_source_segment,
    freeze_source_batch,
    parse_source_document,
)
from src.shared.types import (
    AccountExpression,
    BrandContext,
    BrandContextPacketV2,
    BrandContextPacketV3,
    BrandContextSegment,
    ContentProduct,
    ContentTarget,
    MediaFormat,
    ProductFact,
    TenantManagementScope,
    TrustedScope,
)
from src.shared.writer_request import (
    WRITER_OUTPUT_VERSION,
    WriterOutputV3,
    build_writer_request_v3,
    writer_output_digest,
    writer_output_document,
    writer_request_digest,
    writer_request_document,
)
from src.tool import run_tenant01_golden_suite as tenant01_runner
from src.tool.run_tenant01_golden_suite import (
    _assert_final_suite_session_lease,
    _assert_formal_account_summary,
    _assert_formal_publication_summary,
    _assert_p2_product_ready,
    _FormalAccountSummary,
    _FormalPublicationSummary,
    _Journey,
    _next_evidence_series_title,
)
from src.tool.tenant01_evidence import (
    TENANT01_CARD_IDS,
    TENANT01_COMPARISON_FIELDS,
    TENANT01_DEMONSTRATION_CHECKS,
    TENANT01_GENERATION_LEDGER_FILE,
    TENANT01_GENERATION_LEDGER_VERSION,
    TENANT01_HARD_BOUNDARIES,
    TENANT01_PROVIDER_MODEL,
    TENANT01_REVIEW_DIMENSIONS,
    TENANT01_SUITE_VERSION,
    Tenant01ArtifactInput,
    Tenant01EvidenceError,
    Tenant01HumanReview,
    _artifact_binding,
    compile_tenant01_snapshot_delivery,
    sha256_file,
    write_tenant01_evidence,
)

_SOURCE_IDS = (
    "DIYU-CANDIDATE-PRODUCT-MASTER-001",
    "DIYU-BRAND-BASELINE-001",
    "DIYU-AUDIENCE-PROFILE-001",
    "DIYU-CONTENT-ROLE-001",
    "DIYU-CONTENT-GOVERNANCE-001",
    "DIYU-BRAND-VOICE-001",
    "DIYU-ACCOUNT-AUTHORITY-001",
    "DIYU-DISPLAY-EXPRESSION-001",
    "DIYU-BRAND-VISUAL-001",
    "DIYU-ASSET-CALLING-001",
    "DIYU-ASSET-VISUAL-ANALYSIS-001",
    "DIYU-ASSET-CATALOG-001",
    "DIYU-PRODUCT-TRADEOFF-P2-001",
    "DIYU-PRODUCT-PRICE-CORRECTION-001",
    "DIYU-ASSET-PRODUCT-INFERENCE-001",
    "DIYU-ACCOUNT-MATRIX-001",
    "DIYU-ORG-IP-ACCOUNT-MATRIX-001",
    "DIYU-TENANT-ORG-AUTH-001",
    "DIYU-ASSET-BRAND-UNIFICATION-001",
    "DIYU-STORE-FIXTURE-PROFILE-001",
    "DIYU-STORE-FIXTURE-COLLECTION-001",
)


def _write_source_batch(root: Path) -> None:
    for index, source_id in enumerate(_SOURCE_IDS, start=1):
        title = f"冻结资料 {index}"
        body = (
            f"# {title}\n\n"
            f"文档编号：{source_id}\n\n"
            "文档版本：V1\n\n"
            "状态：待品牌方验收\n\n"
            "## 已确认边界\n\n"
            f"这是 {source_id} 的稳定整段内容。"
            f"{'长段落保持完整。' * 180 if source_id == 'DIYU-BRAND-BASELINE-001' else ''}\n"
        )
        if source_id == "DIYU-CANDIDATE-PRODUCT-MASTER-001":
            product_sections = []
            for product_index in range(1, 15):
                product_sections.append(
                    "\n".join(
                        (
                            f"## DIYU-CSPU-{product_index:02d} 候选商品 {product_index}",
                            "",
                            "| 字段 | 原文 | 证据等级 |",
                            "| --- | --- | --- |",
                            f"| 品类 | 可观察品类 {product_index} | V |",
                            f"| 主色 | 可观察颜色 {product_index} | V |",
                            f"| 建议价格 | 候选价格 {product_index} | P |",
                            f"| 功效 | 待正式资料覆盖 {product_index} | R |",
                        )
                    )
                )
            body += "\n\n" + "\n\n".join(product_sections) + "\n"
        # Filenames deliberately carry no authority and may even disagree with
        # the embedded identity.  The parser must remain metadata-owned.
        (root / f"外部原文件名-{22 - index:02d}.md").write_text(body, encoding="utf-8")


def _write_private_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    path.chmod(0o600)


def _tenant01_json_digest(value: object) -> str:
    return sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    ).hexdigest()


def test_tenant01_final_suite_requires_confirmed_source_bound_publication() -> None:
    valid = _FormalPublicationSummary(
        public_brand_name="笛语",
        projection_status="confirmed",
        source_document_count=21,
        source_segment_count=5_046,
        source_bound_writer_item_count=2,
        publication_roles=frozenset({"public_brand_fact", "expression_constraint"}),
    )
    _assert_formal_publication_summary(valid)

    for invalid in (
        replace(valid, source_bound_writer_item_count=0),
        replace(valid, publication_roles=frozenset({"expression_constraint"})),
        replace(valid, projection_status="candidate"),
        replace(valid, public_brand_name="通用浏览器租户"),
    ):
        with pytest.raises(RuntimeError, match="source-bound"):
            _assert_formal_publication_summary(invalid)


def _tenant01_evidence_inputs(
    root: Path,
) -> tuple[
    tuple[Tenant01ArtifactInput, ...],
    tuple[Tenant01HumanReview, ...],
]:
    artifacts: list[Tenant01ArtifactInput] = []
    reviews: list[Tenant01HumanReview] = []
    for card_id in sorted(TENANT01_CARD_IDS):
        outline = f"{card_id} 标题证据"
        artifact_file = f"{card_id}.artifact.json"
        raw_file = f"{card_id}.raw.json"
        projection_id = "11111111-1111-4111-8111-111111111111"
        projection_digest = "d" * 64
        packet_segments = [
            {
                "segment_id": str(uuid4()),
                "source_document_id": "22222222-2222-4222-8222-222222222222",
                "source_document_version_id": "33333333-3333-4333-8333-333333333333",
                "source_id": "brand_source_segment:test",
                "source_version": "V1",
                "semantic_kind": "expression_constraint",
                "evidence_level": "confirmed_publication",
                "visibility_scope": "brand_all",
                "digest": sha256(f"{card_id} 已确认表达约束".encode()).hexdigest(),
                "exact_text": f"{card_id} 已确认表达约束",
                "source_digest": sha256(f"{card_id} 不可变来源".encode()).hexdigest(),
            }
        ]
        packet_digest = brand_context_packet_digest(
            projection_id=projection_id,
            projection_version=1,
            projection_digest=projection_digest,
            segments=packet_segments,
        )
        primary_product: ContentProduct = (
            "dressing_decision"
            if card_id == "P1"
            else "product_truth"
            if card_id == "P2"
            else "local_response"
            if card_id == "P4_series1"
            else "brand_life_narrative"
        )
        target: ContentTarget = "douyin_video" if card_id in {"P1", "cross_platform_douyin"} else "xiaohongshu_graphic"
        media_format: MediaFormat = "video" if target == "douyin_video" else "graphic"
        product_value = None
        products: tuple[ProductFact, ...] = ()
        if card_id == "P2":
            product = ProductFact(
                "TEST-P2",
                {
                    "category": "双面短外套",
                    "colors": ["炭灰纯色", "深绿细格纹"],
                },
                display_name="测试双面短外套",
            )
            products = (product,)
            product_value = build_product_value_contract(
                primary_product="product_truth",
                products=products,
            )
            assert product_value is not None
        product_records = tuple(record for product in products for record in product_fact_records(product))
        frame = new_frame(
            "general_observation",
            (),
            tuple(record.fact_id for record in product_records),
        )
        source_text = f"请完成 {card_id}。"
        candidate = user_fact_candidates((source_text,))[0]
        span = PublicationInputSpanV1(
            source_id=candidate.source_id,
            role="creation_instruction",
            exact_text=candidate.exact_text,
            turn_index=candidate.turn_index,
            start_offset=candidate.start_offset,
            end_offset=candidate.end_offset,
            start_byte=candidate.start_byte,
            end_byte=candidate.end_byte,
        )
        topic_origin: TopicOrigin = "system_selected" if card_id == "zero_topic" else "explicit_user"
        plan = build_creative_plan(
            topic_spans=(source_text,),
            primary_value=primary_product,
            tone_ids=(ACCOUNT_BASELINE_TONE_ID,),
            mechanism_id=None,
            target_shape=platform_shape(target, media_format),
            topic_origin=topic_origin,
        )
        envelope = build_media_capability_envelope(
            platform_shape=plan.platform_shape,
            media_format=media_format,
        )
        series_position = (
            1 if card_id == "P4_series1" else 2 if card_id == "series2" else 3 if card_id == "series3" else None
        )
        media_program = select_media_program(
            primary_product=primary_product,
            envelope=envelope,
            mechanism_id=plan.mechanism_id,
            series_position=series_position,
            fact_count=len(product_records),
            topic_origin=topic_origin,
        )
        publication = build_publication_contract(
            primary_product=primary_product,
            topic_spans=(source_text,),
            topic_origin=topic_origin,
            known_conditions=(),
            frozen_fact_refs=tuple(frame.allowed_fact_ids),
            intake_spans=(span,),
            account_identity="测试表达身份",
            account_audience="需要清楚选择的受众",
            account_attention="先看具体条件再形成判断",
            account_response_boundary="不补造现实或商品事实",
            source_profile_id="44444444-4444-4444-8444-444444444444",
            source_profile_version=2,
            publication_projection_id=projection_id,
            publication_projection_version=1,
            publication_projection_digest=projection_digest,
            product_value_contract_digest=(
                product_value_contract_digest(product_value) if product_value is not None else None
            ),
        )
        kernel = build_kernel_skeleton(
            frame=frame,
            fact_registry=product_records,
            constraint_refs=("constraint:publication-contract-v2",),
            program_id=OBSERVATION_ONLY_PROGRAM,
            allowed_resource_ids=(),
            media_format=media_format,
            kernel_version=KERNEL_VERSION,
            primary_product=primary_product,
        )
        writer_text = {
            "title": outline,
            "natural_guide": f"{card_id} 导读证据，说明读者能获得什么。",
            "body": f"{card_id} 正文证据，说明本篇的主要价值。",
            "release_caption": f"{card_id} 发布配文证据，不扩写事实。",
        }
        kernel = replace(
            kernel,
            units=tuple(
                replace(unit, text=writer_text[unit.purpose]) if unit.text_source == "writer" else unit
                for unit in kernel.units
            ),
        )
        product_packet = build_product_fact_packet(
            products,
            allowed_fact_ids=frame.allowed_product_fact_ids,
        )
        fact_blocks = immutable_product_fact_blocks(product_packet)
        kernel = replace(
            kernel,
            selected_fact_block_ids=tuple(block.fact_block_id for block in fact_blocks),
        )
        compiled = compile_delivery(
            DeliveryCompileInput(
                primary_product=primary_product,
                media_format=media_format,
                products=products,
                production_conditions="测试制作条件",
                allowed_resource_ids=envelope.resource_ids,
                immutable_fact_blocks=fact_blocks,
                trusted_fact_texts=tuple((record.fact_id, record.exact_text) for record in product_records),
                media_capability_envelope=envelope,
                media_program=media_program,
                product_value_contract=product_value,
                publication_contract=publication,
            ),
            kernel,
        )
        body = compiled.body
        production = asdict(compiled.production)
        product_documents = [
            {
                "sku": product.sku,
                "display_name": product.display_name,
                "facts": product.facts,
                "source_kind": product.source_kind,
                "source_note": product.source_note,
                "fact_version": product.fact_version,
                "applicability": product.applicability,
                "product_id": (str(product.product_id) if product.product_id else None),
                "product_version_id": (str(product.product_version_id) if product.product_version_id else None),
            }
            for product in products
        ]
        _write_private_json(
            root / artifact_file,
            {
                "suite_version": TENANT01_SUITE_VERSION,
                "card_id": card_id,
                "task_id": str(uuid4()),
                "run_id": str(uuid4()),
                "version_id": str(uuid4()),
                "version": 1,
                "outline": compiled.outline,
                "body": body,
                "visible_digest": visible_digest(compiled.outline, body),
                "production": production,
                "formal_snapshot": {
                    "brand_context_packet": {
                        "packet_version": "brand-context-packet-v2",
                        "packet_digest": packet_digest,
                        "publication_projection_id": projection_id,
                        "publication_projection_version": 1,
                        "publication_projection_digest": projection_digest,
                        "segments": packet_segments,
                    },
                    "account_expression_profile_id": ("44444444-4444-4444-8444-444444444444"),
                    "account_expression_profile_version": 2,
                    "account_expression": {
                        "profile_id": "44444444-4444-4444-8444-444444444444",
                        "version": 2,
                        "identity_position": "测试表达身份",
                        "authority_boundary": "不补造现实或商品事实",
                        "audience_relationship": "需要清楚选择的受众",
                        "content_territories": "先看具体条件再形成判断",
                        "default_production_conditions": "测试制作条件",
                    },
                    "original_direction": {"selections": []},
                    "publishing_target": target,
                    "user_premise": source_text,
                    "creative_plan_v2": creative_plan_document(plan),
                    "publication_contract": publication_contract_document(publication),
                    "publication_contract_digest": publication_contract_digest(publication),
                    "product_value_contract": (
                        product_value_contract_document(product_value) if product_value is not None else None
                    ),
                    "product_value_contract_digest": (
                        product_value_contract_digest(product_value) if product_value is not None else None
                    ),
                    "product_facts": product_documents,
                    "narrative_frame": frame_document(frame),
                    "creative_kernel_v2": kernel_document(kernel),
                    "expression_plan_digest": kernel_digest(kernel),
                    "delivery_compiler_version": DELIVERY_COMPILER_VERSION,
                    "writer_model": TENANT01_PROVIDER_MODEL,
                    "immutable_product_fact_blocks": (immutable_fact_blocks_document(fact_blocks)),
                    "visible_provenance": {
                        field: list(sources) for field, sources in compiled.visible_provenance.items()
                    },
                    "delivery_resource_refs": list(compiled.resource_refs),
                    "media_capability_envelope": media_envelope_document(envelope),
                    "media_capability_envelope_digest": media_envelope_digest(envelope),
                    "media_program": media_program_document(media_program),
                    "media_program_digest": media_program_digest(media_program),
                    "reviewed_kernel_digest": kernel_digest(kernel),
                    "reviewed_creative_digest": creative_units_digest(kernel),
                },
            },
        )
        raw_responses: list[dict[str, object]] = []
        for request_index, stage in enumerate(("intake", "writer"), start=1):
            response = {
                "id": f"{card_id}-{stage}",
                "model": TENANT01_PROVIDER_MODEL,
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {"card_id": card_id, "stage": stage},
                                ensure_ascii=False,
                            )
                        }
                    }
                ],
            }
            raw_responses.append(
                {
                    "request_index": request_index,
                    "transport_retries": 0,
                    "stage": stage,
                    "model": TENANT01_PROVIDER_MODEL,
                    "request_sha256": sha256(f"{card_id}:{stage}:request".encode()).hexdigest(),
                    "response_sha256": _tenant01_json_digest(response),
                    "response": response,
                }
            )
        _write_private_json(
            root / raw_file,
            {
                "raw_bundle_version": "ux03-gate-c-provider-stages-v1",
                "card_id": card_id,
                "request_count": 2,
                "responses": raw_responses,
            },
        )
        artifacts.append(Tenant01ArtifactInput(card_id, artifact_file, raw_file))
        artifact_sha256 = sha256_file(root / artifact_file)
        visible_digest_value = visible_digest(compiled.outline, body)
        media_excerpt = str(production["cover_or_first_frame" if media_format == "video" else "hero_image"])
        reviews.append(
            Tenant01HumanReview(
                card_id=card_id,
                artifact_file=artifact_file,
                artifact_sha256=artifact_sha256,
                visible_digest=visible_digest_value,
                scores={dimension: 4 for dimension in TENANT01_REVIEW_DIMENSIONS},
                excerpts={
                    "title": f"{card_id} 标题证据",
                    "body": f"{card_id} 正文证据",
                    "media": media_excerpt,
                    "caption": f"{card_id} 发布配文证据",
                },
                hard_boundaries={boundary: True for boundary in TENANT01_HARD_BOUNDARIES},
                demonstration_checks={check: True for check in TENANT01_DEMONSTRATION_CHECKS},
                comparison={field: f"{card_id} {field} 独立比较结论" for field in TENANT01_COMPARISON_FIELDS},
                brand_basis=f"projection:test / profile:{card_id}",
                verdict="PASS",
                notes="已逐字阅读最终可见成品，与评分引用一致。",
                hard_boundary="PASS",
                product_usable="PASS",
                quality_dimensions={dimension: 4 for dimension in TENANT01_REVIEW_DIMENSIONS},
                dimension_rationales={
                    dimension: f"{card_id} {dimension} 引用成品的独立判断依据"
                    for dimension in TENANT01_REVIEW_DIMENSIONS
                },
                title_excerpt=f"{card_id} 标题证据",
                body_excerpt=f"{card_id} 正文证据",
                media_excerpt=media_excerpt,
                caption_excerpt=f"{card_id} 发布配文证据",
                quality_observations=(),
                residual_risks=(),
                reviewer_scope="最终 artifact 标题、正文、媒体结构与发布配文",
                reviewer_kind="single_execution_product_review",
                reviewed_at="2026-08-02T12:00:00+00:00",
            )
        )
    _write_private_json(
        root / "p5-no-media.json",
        {
            "card_id": "P5_no_media",
            "provider_calls": 0,
            "persistence_delta": [0, 0, 0],
            "result_kind": "question",
        },
    )
    _write_private_json(
        root / "dm01.json",
        {
            "identifiers": {
                "task_id": str(uuid4()),
                "v1_run_id": str(uuid4()),
                "v1_version_id": str(uuid4()),
                "v2_run_id": str(uuid4()),
                "v2_version_id": str(uuid4()),
            },
            "model": "dm01-rule-compiler-v1",
            "provider_calls": 0,
            "provider_usage": {},
            "rules_total": 13,
            "generation_rules": 11,
            "v1_v2_v1": True,
            "inventory_conservation": True,
            "ai_generated": False,
        },
    )
    _write_tenant01_generation_ledger(
        root,
        artifacts=tuple(artifacts),
        implementation_sha="a" * 40,
    )
    return tuple(artifacts), tuple(reviews)


def _tenant01_v3_artifact(root: Path) -> Path:
    card_id = "P2"
    source_text = "请解释这件双面短外套的选择价值。"
    candidate = user_fact_candidates((source_text,))[0]
    input_role = PublicationInputSpanV1(
        source_id=candidate.source_id,
        role="creation_instruction",
        exact_text=candidate.exact_text,
        turn_index=candidate.turn_index,
        start_offset=candidate.start_offset,
        end_offset=candidate.end_offset,
        start_byte=candidate.start_byte,
        end_byte=candidate.end_byte,
    )
    product = ProductFact(
        "TEST-P2-V3",
        {
            "category": "双面短外套",
            "colors": ["炭灰纯色", "深绿细格纹"],
        },
        display_name="测试双面短外套",
    )
    products = (product,)
    product_records = product_fact_records(product)
    frame = new_frame(
        "general_observation",
        (),
        tuple(record.fact_id for record in product_records),
    )
    plan = build_creative_plan(
        topic_spans=(source_text,),
        primary_value="product_truth",
        tone_ids=(ACCOUNT_BASELINE_TONE_ID,),
        mechanism_id=None,
        target_shape=platform_shape("xiaohongshu_graphic", "graphic"),
        topic_origin="explicit_user",
    )
    envelope = build_media_capability_envelope(
        platform_shape=plan.platform_shape,
        media_format="graphic",
    )
    media_program = select_media_program(
        primary_product="product_truth",
        envelope=envelope,
        mechanism_id=plan.mechanism_id,
        topic_origin=plan.topic_origin,
        fact_count=len(product_records),
        series_position=None,
    )
    product_basis = build_product_decision_basis_v2(
        primary_product="product_truth",
        products=products,
    )
    assert product_basis is not None
    fact_blocks = immutable_product_fact_blocks(
        build_product_fact_packet(
            products,
            allowed_fact_ids=frame.allowed_product_fact_ids,
        )
    )
    selected_blocks = tuple(block for block in fact_blocks if block.fact_id in product_basis.supporting_fact_refs)

    projection_id = "11111111-1111-4111-8111-111111111111"
    projection_digest = "d" * 64
    segment_id = "55555555-5555-4555-8555-555555555555"
    segment_text = "先回应具体处境，再给受众保留选择空间。"
    packet_segments = [
        {
            "segment_id": segment_id,
            "source_document_id": "22222222-2222-4222-8222-222222222222",
            "source_document_version_id": ("33333333-3333-4333-8333-333333333333"),
            "source_id": "brand_source_segment:v3-test",
            "source_version": "V1",
            "semantic_kind": "expression_constraint",
            "evidence_level": "confirmed_publication",
            "visibility_scope": "brand_all",
            "digest": sha256(segment_text.encode()).hexdigest(),
            "exact_text": segment_text,
            "source_digest": sha256(b"v3 immutable source").hexdigest(),
        }
    ]
    packet_digest = brand_context_packet_v3_digest(
        projection_id=projection_id,
        projection_version=1,
        projection_digest=projection_digest,
        available_segment_refs=(segment_id,),
        frozen_segment_refs=(segment_id,),
        consumed_segment_refs=(segment_id,),
        displayed_segment_refs=(),
        segments=packet_segments,
    )
    publication = build_publication_contract_v3(
        input_roles=(input_role,),
        topic_origin="explicit_user",
        topic=source_text,
        content_product="product_truth",
        central_job="解释已确认商品事实如何帮助用户做选择",
        audience_payoff="获得一条商品专属的选择判断",
        explicit_user_controls=(source_text,),
        account_editorial_permission=AccountEditorialPermissionV3(
            identity="测试表达身份",
            audience="需要清楚选择的受众",
            attention_order="先看具体条件再形成判断",
            response_posture="回应具体处境并保留选择空间",
            refusals="不补造现实或商品事实",
            allowed_stance="允许形成条件化选择建议",
            source_profile_id="44444444-4444-4444-8444-444444444444",
            source_profile_version=2,
        ),
        frozen_fact_refs=tuple(frame.allowed_fact_ids),
        product_decision_basis=ProductDecisionBasisRefV2(
            contract_version=product_basis.contract_version,
            digest=product_value_contract_digest(product_basis),
            supporting_fact_refs=product_basis.supporting_fact_refs,
        ),
        series_delta=None,
        platform_direction=PlatformDirectionV3(
            target="xiaohongshu_graphic",
            media_format="graphic",
            direction_version="platform-direction-v3-test",
            direction_digest="e" * 64,
        ),
        media_capability_ref=media_envelope_digest(envelope),
        brand_context_use=BrandContextUseV3(
            available_refs=(segment_id,),
            frozen_refs=(segment_id,),
            consumed_refs=(segment_id,),
            displayed_refs=(),
        ),
        publication_projection_id=projection_id,
        publication_projection_version=1,
        publication_projection_digest=projection_digest,
    )
    writer_request = build_writer_request_v3(
        publication,
        product_decision_basis=product_basis,
        prior_output=None,
        revision_instruction=None,
    )
    writer_output = WriterOutputV3(
        output_version=WRITER_OUTPUT_VERSION,
        title="双面不是多一个答案，而是多一次取舍",
        natural_guide="这篇从两面之间的可见差异，说明选择怎样成立。",
        creative_body=(
            "如果你确实需要两种不同的可见重点，这个选择才有价值。"
            "同一时刻主要呈现其中一面，也意味着暂时放下另一面的视觉重点。"
        ),
        publication_caption="先想清楚今天希望哪一面成为重点，再做选择。",
    )
    output_digest = writer_output_digest(writer_output)
    kernel = build_creative_kernel_v5(
        writer_output_digest=output_digest,
        trusted_fact_refs=product_basis.supporting_fact_refs,
        selected_fact_blocks=selected_blocks,
        media_program_id=media_program.program_id,
        media_unit_bindings=media_program.unit_bindings,
    )
    compiled = compile_delivery(
        DeliveryCompileInput(
            primary_product="product_truth",
            media_format="graphic",
            products=products,
            production_conditions="测试制作条件",
            allowed_resource_ids=envelope.resource_ids,
            immutable_fact_blocks=fact_blocks,
            trusted_fact_texts=tuple((record.fact_id, record.exact_text) for record in product_records),
            media_capability_envelope=envelope,
            media_program=media_program,
            product_value_contract=product_basis,
            publication_contract=publication,
            writer_output=writer_output,
        ),
        kernel,
    )
    product_documents = [
        {
            "sku": product.sku,
            "display_name": product.display_name,
            "facts": product.facts,
            "source_kind": product.source_kind,
            "source_note": product.source_note,
            "fact_version": product.fact_version,
            "applicability": product.applicability,
            "product_id": None,
            "product_version_id": None,
        }
    ]
    snapshot = {
        "brand_context_packet": {
            "packet_version": "brand-context-packet-v3",
            "packet_digest": packet_digest,
            "publication_projection_id": projection_id,
            "publication_projection_version": 1,
            "publication_projection_digest": projection_digest,
            "available_segment_refs": [segment_id],
            "frozen_segment_refs": [segment_id],
            "consumed_segment_refs": [segment_id],
            "displayed_segment_refs": [],
            "segments": packet_segments,
        },
        "account_expression_profile_id": ("44444444-4444-4444-8444-444444444444"),
        "account_expression_profile_version": 2,
        "account_expression": {
            "profile_id": "44444444-4444-4444-8444-444444444444",
            "version": 2,
            "identity_position": "测试表达身份",
            "authority_boundary": "不补造现实或商品事实",
            "audience_relationship": "需要清楚选择的受众",
            "content_territories": "先看具体条件再形成判断",
            "default_production_conditions": "测试制作条件",
        },
        "original_direction": {"selections": []},
        "publishing_target": "xiaohongshu_graphic",
        "user_premise": source_text,
        "creative_plan_v2": creative_plan_document(plan),
        "publication_contract": publication_contract_document(publication),
        "publication_contract_digest": publication_contract_digest(publication),
        "product_value_contract": product_value_contract_document(product_basis),
        "product_value_contract_digest": product_value_contract_digest(product_basis),
        "product_facts": product_documents,
        "narrative_frame": frame_document(frame),
        "writer_request_v3": writer_request_document(writer_request),
        "writer_request_v3_digest": writer_request_digest(writer_request),
        "writer_output_v3": writer_output_document(writer_output),
        "writer_output_v3_digest": output_digest,
        "creative_kernel_v5": kernel_document(kernel),
        "expression_plan_digest": kernel_digest(kernel),
        "deterministic_checked_kernel_digest": kernel_digest(kernel),
        "reviewed_creative_digest": output_digest,
        "delivery_compiler_version": DELIVERY_COMPILER_V5_VERSION,
        "writer_model": TENANT01_PROVIDER_MODEL,
        "immutable_product_fact_blocks": immutable_fact_blocks_document(selected_blocks),
        "visible_provenance": {field: list(sources) for field, sources in compiled.visible_provenance.items()},
        "delivery_resource_refs": list(compiled.resource_refs),
        "media_capability_envelope": media_envelope_document(envelope),
        "media_capability_envelope_digest": media_envelope_digest(envelope),
        "media_program": media_program_document(media_program),
        "media_program_digest": media_program_digest(media_program),
    }
    path = root / "P2.v3.artifact.json"
    _write_private_json(
        path,
        {
            "suite_version": TENANT01_SUITE_VERSION,
            "card_id": card_id,
            "task_id": str(uuid4()),
            "run_id": str(uuid4()),
            "version_id": str(uuid4()),
            "version": 1,
            "outline": compiled.outline,
            "body": compiled.body,
            "visible_digest": visible_digest(
                compiled.outline,
                compiled.body,
            ),
            "production": asdict(compiled.production),
            "formal_snapshot": snapshot,
        },
    )
    return path


def test_product_decision_basis_v2_contains_a_consumer_tradeoff_not_a_safety_disclaimer() -> None:
    product = ProductFact(
        sku="HOLDOUT-STRUCTURE-01",
        display_name="结构轮廓测试商品",
        facts={
            "material_or_structure": "双层结构",
            "silhouette": "短款直线轮廓",
        },
        source_kind="synthetic_confirmed_product_record",
    )

    basis = build_product_decision_basis_v2(
        primary_product="product_truth",
        products=(product,),
    )

    assert isinstance(basis, P2ProductDecisionBasisV2)
    assert basis.decision_axis == "confirmed_structure_and_silhouette"
    machine_plan = "\n".join(
        (
            basis.product_specific_understanding,
            basis.tradeoff,
            basis.condition_of_validity,
        )
    )
    assert "结构" in basis.tradeoff
    assert "轮廓" in basis.tradeoff
    assert all(marker not in machine_plan for marker in ("不能据此", "尚未确认", "验收", "合同", "事实许可"))


def test_product_decision_basis_v2_fails_closed_without_a_real_choice_dimension() -> None:
    product = ProductFact(
        sku="HOLDOUT-ONE-FIELD-01",
        display_name="单字段测试商品",
        facts={"material_or_structure": "双层结构"},
        source_kind="synthetic_confirmed_product_record",
    )

    with pytest.raises(GenerationFailed, match="还不足以形成商品专属理解"):
        build_product_decision_basis_v2(
            primary_product="product_truth",
            products=(product,),
        )


def test_product_decision_basis_v2_treats_multiple_colors_as_one_relation_not_variants() -> None:
    product = ProductFact(
        sku="HOLDOUT-COLOR-RELATION-01",
        display_name="拼色测试商品",
        facts={"colors": ["黑色", "红色等强对比"]},
        source_kind="synthetic_confirmed_product_record",
    )

    basis = build_product_decision_basis_v2(
        primary_product="product_truth",
        products=(product,),
    )

    assert isinstance(basis, P2ProductDecisionBasisV2)
    assert basis.decision_axis == "internal_color_relationship"
    machine_plan = "\n".join(
        (
            basis.product_specific_understanding,
            basis.tradeoff,
            basis.condition_of_validity,
        )
    )
    assert "颜色关系" in machine_plan
    assert "强对比" in machine_plan
    assert all(marker not in machine_plan for marker in ("两种颜色", "两种可见选择", "其中一种颜色"))


def _write_tenant01_generation_ledger(
    root: Path,
    *,
    artifacts: tuple[Tenant01ArtifactInput, ...],
    implementation_sha: str,
) -> None:
    ledger_path = root / TENANT01_GENERATION_LEDGER_FILE
    if ledger_path.exists():
        ledger_path.chmod(0o600)
    records: list[dict[str, object]] = []
    for item in artifacts:
        artifact_path = root / item.artifact_file
        raw_path = root / item.raw_response_file
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        responses = raw["responses"]
        records.append(
            {
                "card_id": item.card_id,
                "task_id": artifact["task_id"],
                "run_id": artifact["run_id"],
                "version_id": artifact["version_id"],
                "version": artifact["version"],
                "artifact_file": item.artifact_file,
                "artifact_sha256": sha256_file(artifact_path),
                "visible_digest": artifact["visible_digest"],
                "raw_response_file": item.raw_response_file,
                "raw_response_sha256": sha256_file(raw_path),
                "provider_stages": [response["stage"] for response in responses],
                "request_hashes": [response["request_sha256"] for response in responses],
                "response_hashes": [response["response_sha256"] for response in responses],
            }
        )
    _write_private_json(
        ledger_path,
        {
            "ledger_version": TENANT01_GENERATION_LEDGER_VERSION,
            "suite_version": TENANT01_SUITE_VERSION,
            "implementation_sha": implementation_sha,
            "provider_config": {
                "model": TENANT01_PROVIDER_MODEL,
                "temperature": 0,
                "max_retries": 0,
            },
            "cards": records,
        },
    )
    ledger_path.chmod(0o400)


def test_tenant01_evidence_replays_publication_v3_without_legacy_oracle(
    tmp_path: Path,
) -> None:
    tmp_path.chmod(0o700)
    path = _tenant01_v3_artifact(tmp_path)

    document, _, projection, regions = _artifact_binding(
        path,
        card_id="P2",
    )

    assert projection["publication_contract_version"] == ("publication-contract-v3")
    assert projection["deterministic_checked_kernel_digest"]
    assert regions["title"] == document["outline"]
    assert "商品编辑目标" not in str(document["body"])
    assert "如果你确实需要两种不同的可见重点，这个选择才有价值。" in str(document["body"])
    assert "先认清自己最不能妥协的条件" not in str(document["body"])
    assert "下次再观察" not in str(document["body"])
    production = cast(dict[str, object], document["production"])
    assert "如果你确实需要两种不同的可见重点，这个选择才有价值。" in str(production["image_sequence"])
    snapshot = cast(dict[str, object], document["formal_snapshot"])
    product_basis = cast(dict[str, object], snapshot["product_value_contract"])
    for internal_field in (
        "product_specific_understanding",
        "tradeoff",
        "condition_of_validity",
    ):
        assert str(product_basis[internal_field]) not in str(document["body"])

    replayed_packet = ContentService._brand_context_packet_from_snapshot(snapshot)
    assert isinstance(replayed_packet, BrandContextPacketV3)
    assert replayed_packet.consumed_segment_refs
    assert replayed_packet.displayed_segment_refs == ()


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("writer_request", "Writer 请求没有绑定唯一 V3 发布合同"),
        ("brand_use", "发布责任合同来源、状态或摘要无效"),
    ),
)
def test_tenant01_evidence_v3_rejects_rehashed_binding_drift(
    tmp_path: Path,
    mutation: str,
    message: str,
) -> None:
    tmp_path.chmod(0o700)
    path = _tenant01_v3_artifact(tmp_path)
    document = json.loads(path.read_text(encoding="utf-8"))
    snapshot = document["formal_snapshot"]
    if mutation == "writer_request":
        snapshot["writer_request_v3"]["central_job"] = "伪造的 Writer 责任"
        snapshot["writer_request_v3_digest"] = _tenant01_json_digest(snapshot["writer_request_v3"])
    else:
        packet = snapshot["brand_context_packet"]
        packet["consumed_segment_refs"] = []
        packet["displayed_segment_refs"] = []
        packet["packet_digest"] = brand_context_packet_v3_digest(
            projection_id=packet["publication_projection_id"],
            projection_version=packet["publication_projection_version"],
            projection_digest=packet["publication_projection_digest"],
            available_segment_refs=packet["available_segment_refs"],
            frozen_segment_refs=packet["frozen_segment_refs"],
            consumed_segment_refs=packet["consumed_segment_refs"],
            displayed_segment_refs=packet["displayed_segment_refs"],
            segments=packet["segments"],
        )
    _write_private_json(path, document)

    with pytest.raises(Tenant01EvidenceError, match=message):
        _artifact_binding(path, card_id="P2")


def _recompile_tenant01_artifact(path: Path) -> tuple[str, str]:
    document = json.loads(path.read_text(encoding="utf-8"))
    snapshot = document["formal_snapshot"]
    kernel = kernel_from_document(snapshot["creative_kernel_v2"])
    publication = publication_contract_from_document(snapshot["publication_contract"])
    assert isinstance(publication, PublicationContractV2)
    assert isinstance(kernel, CreativeKernelV1)
    raw_product_value = snapshot["product_value_contract"]
    product_value = (
        product_value_contract_from_document(raw_product_value) if isinstance(raw_product_value, dict) else None
    )
    envelope, media_program = frozen_media_contract(snapshot)
    products = frozen_product_facts(snapshot)
    assert envelope is not None
    assert media_program is not None
    assert products is not None
    raw_blocks = snapshot["immutable_product_fact_blocks"]
    assert isinstance(raw_blocks, list)
    blocks = tuple(
        ImmutableFactBlock(
            fact_block_id=block["fact_block_id"],
            fact_id=block["fact_id"],
            canonical_text=block["canonical_text"],
            renderer_version=block["renderer_version"],
            visible_order=block["visible_order"],
        )
        for block in raw_blocks
    )
    compiled = compile_delivery(
        DeliveryCompileInput(
            primary_product=cast(ContentProduct, publication.primary_product),
            media_format=envelope.media_format,
            products=products,
            production_conditions=snapshot["account_expression"]["default_production_conditions"],
            allowed_resource_ids=envelope.resource_ids,
            immutable_fact_blocks=blocks,
            trusted_fact_texts=tuple(
                (unit.fact_refs[0], unit.text) for unit in kernel.units if unit.track == "trusted_fact"
            ),
            media_capability_envelope=envelope,
            media_program=media_program,
            product_value_contract=product_value,
            publication_contract=publication,
        ),
        kernel,
    )
    document["outline"] = compiled.outline
    document["body"] = compiled.body
    document["visible_digest"] = visible_digest(
        compiled.outline,
        compiled.body,
    )
    document["production"] = asdict(compiled.production)
    snapshot["visible_provenance"] = {field: list(sources) for field, sources in compiled.visible_provenance.items()}
    snapshot["delivery_resource_refs"] = list(compiled.resource_refs)
    _write_private_json(path, document)
    return sha256_file(path), document["visible_digest"]


def _rebind_tenant01_review(
    root: Path,
    reviews: tuple[Tenant01HumanReview, ...],
    *,
    card_id: str,
    excerpts: dict[str, str] | None = None,
) -> tuple[Tenant01HumanReview, ...]:
    artifact_path = root / f"{card_id}.artifact.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    return tuple(
        replace(
            review,
            artifact_sha256=sha256_file(artifact_path),
            visible_digest=artifact["visible_digest"],
            excerpts=(excerpts if excerpts is not None else review.excerpts),
            title_excerpt=(excerpts["title"] if excerpts is not None else review.title_excerpt),
            body_excerpt=(excerpts["body"] if excerpts is not None else review.body_excerpt),
            media_excerpt=(excerpts["media"] if excerpts is not None else review.media_excerpt),
            caption_excerpt=(excerpts["caption"] if excerpts is not None else review.caption_excerpt),
        )
        if review.card_id == card_id
        else review
        for review in reviews
    )


def _tenant01_file_state(root: Path) -> dict[str, tuple[int, str]]:
    return {
        path.name: (
            path.stat().st_mode & 0o777,
            sha256(path.read_bytes()).hexdigest(),
        )
        for path in root.iterdir()
        if path.is_file()
    }


def _write_tenant01_suite_config(
    root: Path,
    *,
    implementation_sha: str,
    evidence_kind: str | None = None,
) -> None:
    ledger_path = root / TENANT01_GENERATION_LEDGER_FILE
    if not ledger_path.exists():
        _write_private_json(ledger_path, {"fixture": "preflight-only"})
        ledger_path.chmod(0o400)
    document: dict[str, object] = {
        "suite_version": TENANT01_SUITE_VERSION,
        "implementation_sha": implementation_sha,
        "provider_config": {
            "model": TENANT01_PROVIDER_MODEL,
            "temperature": 0,
            "max_retries": 0,
        },
        "cards": sorted(TENANT01_CARD_IDS),
        "generation_ledger": {
            "file": TENANT01_GENERATION_LEDGER_FILE,
            "sha256": sha256_file(ledger_path),
        },
    }
    if evidence_kind is not None:
        document["evidence_kind"] = evidence_kind
    _write_private_json(root / "suite-config.json", document)


def _tenant01_finalize_args(root: Path, implementation_sha: str) -> argparse.Namespace:
    return argparse.Namespace(
        evidence_root=str(root),
        implementation_sha=implementation_sha,
        review_file=str(root / "review-input.json"),
        schema_revision="20260813_40",
        image_digest="sha256:" + "b" * 64,
        source_manifest_digest="e" * 64,
    )


def _tenant01_review_v2_document(
    reviews: tuple[Tenant01HumanReview, ...],
) -> dict[str, object]:
    return {
        "review_contract": "TENANT-01-HUMAN-REVIEW-V2",
        "reviews": [
            {
                "card_id": review.card_id,
                "artifact_file": review.artifact_file,
                "artifact_sha256": review.artifact_sha256,
                "visible_digest": review.visible_digest,
                "hard_boundary": review.hard_boundary,
                "product_usable": review.product_usable,
                "quality_dimensions": review.quality_dimensions,
                "dimension_rationales": review.dimension_rationales,
                "title_excerpt": review.title_excerpt,
                "body_excerpt": review.body_excerpt,
                "media_excerpt": review.media_excerpt,
                "caption_excerpt": review.caption_excerpt,
                "quality_observations": list(review.quality_observations),
                "residual_risks": list(review.residual_risks),
                "reviewer_scope": review.reviewer_scope,
                "reviewer_kind": review.reviewer_kind,
                "reviewed_at": review.reviewed_at,
                "verdict": review.verdict,
            }
            for review in reviews
        ],
    }


def test_final_suite_session_must_outlive_the_complete_run(
    app_database_url: str,
    migrator_database_url: str,
) -> None:
    raw_token = f"tenant01-final-session-{uuid4()}"
    token_digest = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    session_id = uuid4()
    with (
        psycopg.connect(migrator_database_url) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute("SELECT tenant_id, id FROM users ORDER BY id LIMIT 1")
        user = cursor.fetchone()
        assert user is not None
        tenant_id = UUID(str(user[0]))
        user_id = UUID(str(user[1]))
        cursor.execute(
            """
            INSERT INTO tenant_sessions
                (id, tenant_id, user_id, audience, token_digest, expires_at)
            VALUES (%s, %s, %s, 'tenant-user', %s, %s)
            """,
            (
                session_id,
                tenant_id,
                user_id,
                token_digest,
                datetime.now(timezone.utc) + timedelta(minutes=5),
            ),
        )
    journey = _Journey(tenant_id, raw_token, uuid4(), "LEASE-TEST")
    try:
        with pytest.raises(RuntimeError, match="fresh tenant-user session lease"):
            _assert_final_suite_session_lease(app_database_url, journey)
        with (
            psycopg.connect(migrator_database_url) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                "UPDATE tenant_sessions SET expires_at = %s WHERE id = %s",
                (
                    datetime.now(timezone.utc) + timedelta(minutes=30),
                    session_id,
                ),
            )
        _assert_final_suite_session_lease(app_database_url, journey)
    finally:
        with (
            psycopg.connect(migrator_database_url) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute("DELETE FROM tenant_sessions WHERE id = %s", (session_id,))


def test_final_suite_requires_current_formal_account_profile() -> None:
    valid = _FormalAccountSummary(
        logical_account_id=uuid4(),
        account_name="笛语·穿衣编辑",
        business_data_kind="formal_business_data",
        enabled=True,
        control_organization_declared=True,
        content_role="穿衣编辑",
        profile_id=uuid4(),
        profile_version=2,
        complete_segment_count=5,
        profile_confirmed_by_enabled_manager=True,
    )

    _assert_formal_account_summary(valid)
    for invalid in (
        replace(valid, business_data_kind="synthetic_business_fixture"),
        replace(valid, control_organization_declared=False),
        replace(valid, complete_segment_count=4),
        replace(valid, profile_confirmed_by_enabled_manager=False),
    ):
        with pytest.raises(RuntimeError, match="administrator-confirmed"):
            _assert_formal_account_summary(invalid)


def test_final_suite_series_title_is_natural_and_unique_per_creator(
    app_database_url: str,
    migrator_database_url: str,
) -> None:
    with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT tenant_id, id FROM users ORDER BY id LIMIT 1")
        row = cursor.fetchone()
        assert row is not None
        tenant_id = UUID(str(row[0]))
        user_id = UUID(str(row[1]))
        cursor.execute(
            "SELECT count(*) FROM content_series WHERE tenant_id = %s AND created_by = %s",
            (tenant_id, user_id),
        )
        count_row = cursor.fetchone()
        assert count_row is not None
        before = int(count_row[0])

    title = _next_evidence_series_title(
        app_database_url,
        tenant_id=tenant_id,
        created_by=user_id,
    )

    assert title == f"把选择留给人的三篇观察 · 第{before + 1}组"


def _write_tenant01_fixture_evidence(
    root: Path,
    artifacts: tuple[Tenant01ArtifactInput, ...],
    reviews: tuple[Tenant01HumanReview, ...],
) -> None:
    write_tenant01_evidence(
        root,
        implementation_sha="a" * 40,
        schema_revision="20260813_40",
        image_digest="sha256:" + "b" * 64,
        source_manifest_digest="e" * 64,
        artifacts=artifacts,
        reviews=reviews,
        p5_preflight_file="p5-no-media.json",
        dm01_file="dm01.json",
    )


def test_tenant01_freezes_twenty_one_sources_and_fourteen_products(tmp_path: Path) -> None:
    _write_source_batch(tmp_path)

    documents = freeze_source_batch(tmp_path)

    assert len(documents) == 21
    assert {document.source_id for document in documents} == set(_SOURCE_IDS)
    assert len({document.normalized_sha256 for document in documents}) == 21
    products = tuple(product for document in documents for product in document.products)
    assert len(products) == 14
    assert len({product.sku for product in products}) == 14
    assert all(product.fact_fields for product in products)
    assert all("建议价格" not in product.fact_fields and "功效" not in product.fact_fields for product in products)
    evidence = tuple(field for product in products for field in product.fields)
    assert {level for field in evidence for level in field.evidence_levels} == {
        "V",
        "P",
        "R",
    }
    assert all(field.allowed_in_product_fact == (field.evidence_levels == ("V",)) for field in evidence)
    assert sum(len(document.segments) for document in documents) > len(documents)
    assert all(
        segment.exact_text != document.normalized_content for document in documents for segment in document.segments
    )


def test_account_editorial_lens_freezes_distinct_profile_inputs_and_publication() -> None:
    segment_text = "先回应具体处境，再给出克制而明确的判断。"
    segment = BrandContextSegment(
        segment_id="11111111-1111-4111-8111-111111111111",
        source_document_id="22222222-2222-4222-8222-222222222222",
        source_document_version_id="33333333-3333-4333-8333-333333333333",
        source_id="brand_source_segment:test",
        source_version="V1",
        semantic_kind="expression_constraint",
        evidence_level="confirmed_publication",
        visibility_scope="brand_all",
        digest=sha256(segment_text.encode()).hexdigest(),
        exact_text=segment_text,
        source_digest="a" * 64,
    )
    packet = BrandContextPacketV2(
        "brand-context-packet-v2",
        "b" * 64,
        "44444444-4444-4444-8444-444444444444",
        3,
        "c" * 64,
        (segment,),
    )
    expression = AccountExpression(
        UUID("55555555-5555-4555-8555-555555555555"),
        7,
        "不应复制的身份原句",
        "不应复制的权威边界",
        "不应复制的受众原句",
        "不应复制的内容领地",
        "不应复制的制作条件",
        False,
    )

    lens = build_account_editorial_lens(
        primary_product="brand_life_narrative",
        account_expression=expression,
        brand_context_packet=packet,
    )

    assert lens is not None
    document = account_editorial_lens_document(lens)
    assert document["contract_version"] == ACCOUNT_EDITORIAL_LENS_VERSION
    assert document["source_profile_version"] == 7
    assert document["publication_projection_version"] == 3
    assert len(account_editorial_lens_digest(lens)) == 64
    serialized = json.dumps(document, ensure_ascii=False)
    assert "不应复制的身份原句" in serialized
    assert "不应复制的受众原句" in serialized
    assert "不应复制的内容领地" in serialized
    assert "题材没有商品、服饰或门店时" in serialized
    assert "不能无损替换到另一件生活琐事" in serialized
    assert "不得猜测" in serialized
    assert "互相复述" in serialized


def test_publication_contract_is_one_negative_boundary_not_a_sentence_dsl() -> None:
    source_text = "今天不知道发什么，帮我做一条小红书。"
    candidate = user_fact_candidates((source_text,))[0]
    span = PublicationInputSpanV1(
        source_id=candidate.source_id,
        role="creation_instruction",
        exact_text=candidate.exact_text,
        turn_index=candidate.turn_index,
        start_offset=candidate.start_offset,
        end_offset=candidate.end_offset,
        start_byte=candidate.start_byte,
        end_byte=candidate.end_byte,
    )
    contract = build_publication_contract(
        primary_product="brand_life_narrative",
        topic_spans=(source_text,),
        topic_origin="system_selected",
        known_conditions=(),
        frozen_fact_refs=(),
        intake_spans=(span,),
        account_identity="穿衣编辑",
        account_audience="需要日常选择帮助的人",
        account_attention="先看具体条件，再回应受众",
        account_response_boundary="不补造现实事实",
        source_profile_id="55555555-5555-4555-8555-555555555555",
        source_profile_version=7,
        publication_projection_id="44444444-4444-4444-8444-444444444444",
        publication_projection_version=3,
        publication_projection_digest="a" * 64,
        product_value_contract_digest=None,
    )

    document = publication_contract_document(contract)
    serialized = json.dumps(document, ensure_ascii=False)
    assert contract.contract_version == PUBLICATION_CONTRACT_VERSION
    assert contract.prohibited_reality_or_product_claims == NEGATIVE_SAFETY_RULE_IDS
    safety_contract = negative_safety_contract_text()
    assert "不替现实人物、对象或事件判定未提供的原因、内部状态、变化或结果" in safety_contract
    assert "一般建议保持建议、条件或假设身份" in safety_contract
    assert contract.topic_origin == "system_selected"
    assert "自主选择一个具体生活题材" in contract.central_job
    assert not {
        "sentence_shape",
        "claim_contract",
        "allowed_claims",
        "unit_responsibilities",
        "text_shape",
    } & set(document)
    assert "必须是问句" not in serialized
    assert "必须二选一" not in serialized
    assert "下次观察" not in serialized


def test_account_editorial_lens_historical_v1_remains_readable_without_upgrade() -> None:
    historical = AccountEditorialLensV1(
        contract_version=ACCOUNT_EDITORIAL_LENS_V1_VERSION,
        primary_product="brand_life_narrative",
        source_profile_id="55555555-5555-4555-8555-555555555555",
        source_profile_version=2,
        publication_projection_id="44444444-4444-4444-8444-444444444444",
        publication_projection_version=1,
        publication_projection_digest="a" * 64,
        brand_context_packet_digest="b" * 64,
        relationship_principle="历史关系",
        topic_fidelity="历史题材",
        fact_boundary="历史事实边界",
        viewer_value_requirement="历史观看回报",
        closure_boundary="历史收束",
    )

    parsed = account_editorial_lens_from_document(account_editorial_lens_document(historical))

    assert parsed == historical
    assert parsed.contract_version == ACCOUNT_EDITORIAL_LENS_V1_VERSION


def test_account_editorial_lens_historical_v2_remains_readable_without_upgrade() -> None:
    historical = AccountEditorialLensV2(
        contract_version=ACCOUNT_EDITORIAL_LENS_V2_VERSION,
        primary_product="brand_life_narrative",
        source_profile_id="55555555-5555-4555-8555-555555555555",
        source_profile_version=2,
        publication_projection_id="44444444-4444-4444-8444-444444444444",
        publication_projection_version=1,
        publication_projection_digest="a" * 64,
        brand_context_packet_digest="b" * 64,
        relationship_principle="历史关系",
        topic_fidelity="历史题材",
        fact_boundary="历史事实边界",
        viewer_value_requirement="历史观看回报",
        closure_boundary="历史收束",
        title_responsibility="历史标题职责",
        natural_guide_responsibility="历史导读职责",
        body_responsibility="历史正文职责",
        release_caption_responsibility="历史配文职责",
        actuality_response_boundary="历史现实回应边界",
        series_progression_boundary="历史系列推进边界",
    )

    parsed = account_editorial_lens_from_document(account_editorial_lens_document(historical))

    assert parsed == historical
    assert parsed.contract_version == ACCOUNT_EDITORIAL_LENS_V2_VERSION


def test_account_editorial_lens_historical_v3_remains_readable_without_upgrade() -> None:
    historical = AccountEditorialLensV3(
        contract_version=ACCOUNT_EDITORIAL_LENS_V3_VERSION,
        primary_product="brand_life_narrative",
        source_profile_id="55555555-5555-4555-8555-555555555555",
        source_profile_version=7,
        publication_projection_id="44444444-4444-4444-8444-444444444444",
        publication_projection_version=3,
        publication_projection_digest="a" * 64,
        brand_context_packet_digest="b" * 64,
        relationship_principle="历史关系",
        topic_fidelity="历史题材",
        fact_boundary="历史事实边界",
        viewer_value_requirement="历史观看回报",
        closure_boundary="历史收束",
        title_responsibility="历史标题职责",
        natural_guide_responsibility="历史导读职责",
        body_responsibility="历史正文职责",
        release_caption_responsibility="历史配文职责",
        actuality_response_boundary="历史现实回应边界",
        series_progression_boundary="历史系列推进边界",
        identity_position_input="历史身份",
        authority_boundary_input="历史权限",
        audience_relationship_input="历史受众",
        content_territories_input="历史内容领地",
    )

    parsed = account_editorial_lens_from_document(account_editorial_lens_document(historical))

    assert parsed == historical
    assert parsed.contract_version == ACCOUNT_EDITORIAL_LENS_V3_VERSION


def test_visible_brand_fact_requires_brand_to_be_the_explicit_subject() -> None:
    exact_fact = "笛语提供面向日常穿衣选择的品牌内容。"
    context = BrandContext(
        brand_name="笛语",
        positioning="清楚表达",
        decision_order="先条件后选择",
        tone="克制",
        account_name="笛语编辑",
        operator_name="编辑",
        organization_name="总部",
        content_role_name="穿衣编辑",
        content_role_boundary="不代替受众决定",
        audience_description="需要日常选择的人",
        strategy_version="v1",
        platform="小红书",
        media_format="图文",
        production_conditions="抽象编排",
        brand_reference_context=(exact_fact,),
    )

    ordinary = ContentService._frame_with_brand_facts(
        None,
        (),
        context,
        "早上凉、中午热，今天怎么穿更稳妥？",
    )
    explicit = ContentService._frame_with_brand_facts(
        None,
        (),
        context,
        "笛语为什么把日常穿衣选择讲得这么克制？",
    )

    assert ordinary.allowed_brand_fact_ids == ()
    assert explicit.allowed_brand_fact_ids == tuple(record.fact_id for record in brand_fact_records((exact_fact,)))


def test_tenant01_content_product_taxonomy_is_not_an_insertable_brand_fact() -> None:
    heading = ("十二、五类内容产品与受众价值",)

    assert (
        classify_source_segment(
            "DIYU-AUDIENCE-PROFILE-001",
            heading,
            "内部内容产品分类只用于决定怎样表达。",
        )
        == "expression_constraint"
    )
    assert (
        classify_source_segment(
            "DIYU-AUDIENCE-PROFILE-001",
            ("稳定目标人群",),
            "面向需要日常穿衣选择帮助的人。",
        )
        == "brand_fact"
    )
    assert (
        classify_source_segment(
            "DIYU-AUDIENCE-PROFILE-001",
            ("十八、本批验收项",),
            "验收目录只用于核对资料覆盖。",
        )
        == "source_catalog_only"
    )


def test_source_identity_uses_embedded_metadata_not_filename(tmp_path: Path) -> None:
    source = tmp_path / "文件名与标题互换也不影响身份.md"
    source.write_text(
        "# 内嵌权威标题\n\n"
        "文档编号：DIYU-BRAND-BASELINE-001\n\n"
        "版本：V7\n\n"
        "状态：待品牌方验收\n\n"
        "## 稳定事实\n\n品牌公开名称为笛语。\n",
        encoding="utf-8",
    )

    document = parse_source_document(source)

    assert document.source_id == "DIYU-BRAND-BASELINE-001"
    assert document.embedded_title == "内嵌权威标题"
    assert document.source_version == "V7"
    assert document.provenance_filename == source.name
    assert all(
        segment.semantic_kind == "source_catalog_only"
        for segment in document.segments
        if segment.exact_text.startswith(("文档编号", "版本", "状态"))
    )
    assert document.segments[-1].semantic_kind == "brand_fact"


def test_source_batch_fails_before_partial_use(tmp_path: Path) -> None:
    _write_source_batch(tmp_path)
    missing = next(tmp_path.glob("*.md"))
    missing.unlink()

    with pytest.raises(ValueError, match="21 份 Markdown"):
        freeze_source_batch(tmp_path)


def test_private_source_text_is_not_part_of_public_import_manifest(tmp_path: Path) -> None:
    _write_source_batch(tmp_path)
    documents = freeze_source_batch(tmp_path)
    public_projection = {
        "source_digests": [
            {
                "source_id": document.source_id,
                "version": document.source_version,
                "normalized_sha256": document.normalized_sha256,
            }
            for document in documents
        ],
        "counts": {
            "documents": len(documents),
            "segments": sum(len(document.segments) for document in documents),
            "products": sum(len(document.products) for document in documents),
        },
    }

    serialized = json.dumps(public_projection, ensure_ascii=False)
    assert "稳定整段内容" not in serialized
    assert "候选价格" not in serialized
    assert "normalized_sha256" in serialized


def test_visible_context_basis_is_frozen_business_language_only() -> None:
    snapshot = {
        "brand_context_packet": {
            "segments": [
                {"semantic_kind": "brand_fact", "segment_id": "private-id"},
                {"semantic_kind": "creative_method", "segment_id": "another-id"},
            ]
        },
        "product_facts": [{"sku": "PRIVATE-SKU"}],
        "material_snapshots": [],
    }

    result = visible_context_basis(
        snapshot,
        account_name="笛语官方账号",
        channel="小红书",
        media_format="graphic",
    )

    assert result == {
        "account": "笛语官方账号",
        "platform_and_format": "小红书 · 图文",
        "brand_material_categories": ["品牌已确认资料", "品牌创作方法"],
        "has_product_facts": True,
        "selected_material_count": 0,
        "gaps": ["本次没有选择制作素材"],
    }
    assert "private-id" not in json.dumps(result)


def test_visible_context_basis_v3_reports_only_consumed_or_displayed_materials() -> None:
    snapshot = {
        "brand_context_packet": {
            "packet_version": "brand-context-packet-v3",
            "available_segment_refs": ["brand-available", "method-used"],
            "frozen_segment_refs": ["method-used"],
            "consumed_segment_refs": ["method-used"],
            "displayed_segment_refs": [],
            "segments": [
                {
                    "semantic_kind": "brand_fact",
                    "segment_id": "brand-available",
                },
                {
                    "semantic_kind": "creative_method",
                    "segment_id": "method-used",
                },
            ],
        },
        "product_facts": [],
        "material_snapshots": [],
    }

    result = visible_context_basis(
        snapshot,
        account_name="笛语官方账号",
        channel="小红书",
        media_format="graphic",
    )

    assert result["brand_material_categories"] == ["品牌创作方法"]
    assert "品牌已确认资料" not in cast(
        list[str],
        result["brand_material_categories"],
    )


def _import_scope(database_url: str) -> tuple[TenantManagementScope, UUID]:
    tenant_id = uuid4()
    brand_id = uuid4()
    organization_id = uuid4()
    manager_id = uuid4()
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO tenants (id, name) VALUES (%s, %s)",
            (tenant_id, f"TENANT-01 importer {tenant_id.hex[:8]}"),
        )
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),))
        cursor.execute(
            "INSERT INTO organizations "
            "(id, tenant_id, name, organization_level, business_data_kind) "
            "VALUES (%s, %s, '导入管理组织', 'company', 'formal_business_data')",
            (organization_id, tenant_id),
        )
        cursor.execute(
            "INSERT INTO brands "
            "(id, tenant_id, name, positioning, decision_order, tone) "
            "VALUES (%s, %s, '笛语服饰', '待导入', '待导入', '待导入')",
            (brand_id, tenant_id),
        )
        cursor.execute(
            "INSERT INTO users "
            "(id, tenant_id, organization_id, display_name, entry_kind, business_data_kind) "
            "VALUES (%s, %s, %s, '导入管理员', 'tenant_admin', 'formal_business_data')",
            (manager_id, tenant_id, organization_id),
        )
        cursor.execute(
            "INSERT INTO tenant_management_grants (id, tenant_id, user_id) VALUES (%s, %s, %s)",
            (uuid4(), tenant_id, manager_id),
        )
    return TenantManagementScope(tenant_id, manager_id, brand_id), organization_id


def _delete_import_scope(database_url: str, scope: TenantManagementScope) -> None:
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(scope.tenant_id),))
        for table in (
            "brand_publication_projection_items",
            "brand_product_field_evidence",
            "brand_product_versions",
            "brand_source_segments",
            "brand_source_document_versions",
        ):
            cursor.execute(f"ALTER TABLE {table} DISABLE TRIGGER USER")  # noqa: S608
        try:
            cursor.execute(
                "UPDATE brand_source_documents SET current_version_id = NULL WHERE tenant_id = %s",
                (scope.tenant_id,),
            )
            cursor.execute(
                "UPDATE brand_products SET current_version_id = NULL WHERE tenant_id = %s",
                (scope.tenant_id,),
            )
            cursor.execute(
                "UPDATE brands SET current_publication_projection_id = NULL WHERE tenant_id = %s",
                (scope.tenant_id,),
            )
            for table in (
                "brand_publication_projection_items",
                "brand_publication_projections",
                "brand_product_field_evidence",
                "brand_product_versions",
                "brand_products",
                "content_accounts",
                "brand_source_segments",
                "brand_source_document_versions",
                "brand_source_documents",
                "activity_events",
                "tenant_management_grants",
                "users",
                "organizations",
                "brands",
            ):
                cursor.execute(f"DELETE FROM {table} WHERE tenant_id = %s", (scope.tenant_id,))  # noqa: S608
            cursor.execute("DELETE FROM tenants WHERE id = %s", (scope.tenant_id,))
        finally:
            for table in (
                "brand_publication_projection_items",
                "brand_product_field_evidence",
                "brand_product_versions",
                "brand_source_segments",
                "brand_source_document_versions",
            ):
                cursor.execute(f"ALTER TABLE {table} ENABLE TRIGGER USER")  # noqa: S608


def test_tenant01_import_is_atomic_idempotent_and_evidence_bounded(
    app_database_url: str,
    migrator_database_url: str,
    tmp_path: Path,
) -> None:
    scope, _ = _import_scope(migrator_database_url)
    importer = TenantSourceImporter(app_database_url)
    try:
        _write_source_batch(tmp_path)
        product_source = next(
            path
            for path in tmp_path.glob("*.md")
            if "DIYU-CANDIDATE-PRODUCT-MASTER-001" in path.read_text(encoding="utf-8")
        )
        original_product_source = product_source.read_text(encoding="utf-8")
        product_source.write_text(
            original_product_source.replace("| V |", "| P |"),
            encoding="utf-8",
        )
        invalid_plan = importer.dry_run(scope, tmp_path)
        with pytest.raises(DomainError, match="没有可进入 ProductFact"):
            importer.apply(invalid_plan)
        with psycopg.connect(app_database_url) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(scope.tenant_id),))
            cursor.execute(
                "SELECT (SELECT count(*) FROM brand_source_documents), (SELECT count(*) FROM brand_products)"
            )
            assert cursor.fetchone() == (0, 0)

        product_source.write_text(original_product_source, encoding="utf-8")
        plan = importer.dry_run(scope, tmp_path)
        manifest_text = json.dumps(plan.public_manifest(), ensure_ascii=False)
        assert "稳定整段内容" not in manifest_text and "候选价格" not in manifest_text
        first = importer.apply(plan)
        assert first["inserted_documents"] == 21
        assert first["inserted_products"] == 14
        second_plan = importer.dry_run(scope, tmp_path)
        assert {action for _, action in second_plan.document_actions} == {"no_op"}
        assert {action for _, action in second_plan.product_actions} == {"no_op"}
        assert importer.apply(second_plan) == {
            "batch_digest": second_plan.batch_digest,
            "inserted_documents": 0,
            "inserted_segments": 0,
            "inserted_products": 0,
            "inserted_product_fields": 0,
        }

        with psycopg.connect(app_database_url) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(scope.tenant_id),))
            cursor.execute(
                "SELECT "
                "(SELECT count(*) FROM brand_source_documents), "
                "(SELECT count(*) FROM brand_source_segments), "
                "(SELECT count(*) FROM brand_products), "
                "(SELECT count(*) FROM brand_product_field_evidence "
                " WHERE allowed_in_product_fact), "
                "(SELECT count(*) FROM brand_product_field_evidence "
                " WHERE allowed_in_product_fact AND evidence_level <> 'V'), "
                "(SELECT count(*) FROM brand_product_versions "
                " WHERE facts->>'category' <> '' "
                "   AND jsonb_array_length(facts->'colors') > 0), "
                "(SELECT count(*) FROM material_assets), "
                "(SELECT count(*) FROM product_media_bindings)"
            )
            counts = cursor.fetchone()
            assert counts is not None
            assert counts[0] == 21 and counts[2:] == (14, 28, 0, 14, 0, 0)
            assert counts[1] > 21

        changed = next(path for path in tmp_path.glob("*.md") if path != product_source)
        changed.write_text(
            changed.read_text(encoding="utf-8") + "\n同版本冲突内容。\n",
            encoding="utf-8",
        )
        with pytest.raises(DomainError, match="已存在不同摘要"):
            importer.dry_run(scope, tmp_path)
    finally:
        _delete_import_scope(migrator_database_url, scope)


def test_tenant01_brand_context_is_task_relevant_typed_and_deterministic(
    app_database_url: str,
    migrator_database_url: str,
    tmp_path: Path,
) -> None:
    management_scope, organization_id = _import_scope(migrator_database_url)
    account_id = uuid4()
    legacy_taxonomy_segment_id = uuid4()
    legacy_acceptance_segment_id = uuid4()
    importer = TenantSourceImporter(app_database_url)
    try:
        _write_source_batch(tmp_path)
        importer.apply(importer.dry_run(management_scope, tmp_path))
        with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, current_version_id FROM brand_source_documents "
                "WHERE tenant_id = %s AND source_id = 'DIYU-AUDIENCE-PROFILE-001'",
                (management_scope.tenant_id,),
            )
            source_row = cursor.fetchone()
            assert source_row is not None
            legacy_text = "P3 只是内部内容产品标签，不是可插入成品的品牌事实。"
            cursor.execute(
                "INSERT INTO brand_source_segments "
                "(id, tenant_id, brand_id, document_id, document_version_id, "
                " segment_key, heading_path, source_locator, exact_text, "
                " semantic_kind, evidence_level, applicability, digest) "
                "VALUES (%s, %s, %s, %s, %s, 'legacy-taxonomy', %s, "
                " 'line:999', %s, 'brand_fact', 'brand_user_authorized', "
                " '只用于测试旧解析器记录的安全投影', %s)",
                (
                    legacy_taxonomy_segment_id,
                    management_scope.tenant_id,
                    management_scope.brand_id,
                    source_row[0],
                    source_row[1],
                    ["十二、五类内容产品与受众价值"],
                    legacy_text,
                    sha256(legacy_text.encode()).hexdigest(),
                ),
            )
            acceptance_text = "验收目录包含内部内容产品代号，不是品牌事实。"
            cursor.execute(
                "INSERT INTO brand_source_segments "
                "(id, tenant_id, brand_id, document_id, document_version_id, "
                " segment_key, heading_path, source_locator, exact_text, "
                " semantic_kind, evidence_level, applicability, digest) "
                "VALUES (%s, %s, %s, %s, %s, 'legacy-acceptance', %s, "
                " 'line:1000', %s, 'brand_fact', 'brand_user_authorized', "
                " '只用于测试旧解析器验收目录的安全投影', %s)",
                (
                    legacy_acceptance_segment_id,
                    management_scope.tenant_id,
                    management_scope.brand_id,
                    source_row[0],
                    source_row[1],
                    ["十八、本批验收项"],
                    acceptance_text,
                    sha256(acceptance_text.encode()).hexdigest(),
                ),
            )
            cursor.execute(
                "INSERT INTO content_accounts "
                "(id, tenant_id, brand_id, name, channel, control_organization_id, "
                " control_organization_source) "
                "VALUES (%s, %s, %s, '笛语正式账号', '小红书', %s, 'declared')",
                (
                    account_id,
                    management_scope.tenant_id,
                    management_scope.brand_id,
                    organization_id,
                ),
            )
        with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT segment.id, source.source_id "
                "FROM brand_source_segments segment "
                "JOIN brand_source_documents source "
                "ON source.tenant_id = segment.tenant_id AND source.id = segment.document_id "
                "WHERE segment.tenant_id = %s "
                "AND segment.exact_text LIKE '这是 %%' "
                "AND source.source_id = ANY(%s)",
                (
                    management_scope.tenant_id,
                    [
                        "DIYU-BRAND-BASELINE-001",
                        "DIYU-CONTENT-ROLE-001",
                        "DIYU-DISPLAY-EXPRESSION-001",
                    ],
                ),
            )
            source_ids = {str(row[1]): UUID(str(row[0])) for row in cursor.fetchall()}
        assert set(source_ids) == {
            "DIYU-BRAND-BASELINE-001",
            "DIYU-CONTENT-ROLE-001",
            "DIYU-DISPLAY-EXPRESSION-001",
        }
        publication = PostgresWorkbenchRepository(app_database_url).create_brand_publication_candidate(
            management_scope,
            (
                {
                    "source_segment_id": source_ids["DIYU-BRAND-BASELINE-001"],
                    "publication_role": "public_brand_fact",
                    "published_text": "笛语面向需要清楚日常穿衣选择的人。",
                    "applicability": ["product_truth"],
                },
                {
                    "source_segment_id": source_ids["DIYU-CONTENT-ROLE-001"],
                    "publication_role": "expression_constraint",
                    "published_text": "先回应具体处境，再给出克制而明确的判断。",
                    "applicability": [
                        "dressing_decision",
                        "product_truth",
                        "brand_life_narrative",
                        "local_response",
                        "visual_styling_story",
                    ],
                },
                {
                    "source_segment_id": source_ids["DIYU-DISPLAY-EXPRESSION-001"],
                    "publication_role": "creative_method",
                    "published_text": "围绕一个可感知的变化展开，不复述资料标签。",
                    "applicability": ["product_truth", "brand_life_narrative"],
                },
                {
                    "source_segment_id": legacy_taxonomy_segment_id,
                    "publication_role": "internal_only",
                    "published_text": legacy_text,
                    "applicability": [],
                },
                {
                    "source_segment_id": legacy_acceptance_segment_id,
                    "publication_role": "internal_only",
                    "published_text": acceptance_text,
                    "applicability": [],
                },
            ),
        )
        projection_id = UUID(str(publication["id"]))
        PostgresWorkbenchRepository(app_database_url).confirm_brand_publication_projection(
            management_scope, projection_id
        )

        scope = TrustedScope(
            management_scope.tenant_id,
            management_scope.user_id,
            management_scope.brand_id,
            account_id,
        )
        context = BrandContext(
            brand_name="笛语",
            positioning="只使用已确认的品牌选择",
            decision_order="先人后衣",
            tone="克制",
            account_name="笛语正式账号",
            operator_name="内容用户",
            organization_name="总部",
            content_role_name="品牌穿衣编辑",
            content_role_boundary="不补造商品事实",
            audience_description="需要日常选择帮助的人",
            strategy_version="V1",
            platform="小红书",
            media_format="图文",
            production_conditions="单人低成本制作",
        )
        product = ProductFact(
            sku="DIYU-CSPU-14",
            display_name="候选商品 14",
            facts={"category": "可观察品类 14", "colors": ["可观察颜色 14"]},
            source_kind="tenant_source_import",
            source_note="字段级 V 证据",
            fact_version=1,
            applicability="本次商品",
        )
        repository = PostgresContentRepository(app_database_url)

        selected = repository.select_brand_context_for_task(
            scope,
            context,
            "解释 DIYU-CSPU-14 的可见选择，同时保持内容产品边界",
            "product_truth",
            (product,),
        )
        repeated = repository.select_brand_context_for_task(
            scope,
            context,
            "解释 DIYU-CSPU-14 的可见选择，同时保持内容产品边界",
            "product_truth",
            (product,),
        )

        assert selected.context_packet is not None
        assert repeated.context_packet is not None
        assert selected.context_packet.packet_digest == repeated.context_packet.packet_digest
        assert all(
            sha256(item.exact_text.encode()).hexdigest() == item.digest for item in selected.context_packet.segments
        )
        assert all(item.source_digest is not None for item in selected.context_packet.segments)
        assert selected.context_packet.packet_version == "brand-context-packet-v3"
        assert isinstance(selected.context_packet, BrandContextPacketV3)
        assert (
            set(selected.context_packet.displayed_segment_refs)
            <= set(selected.context_packet.consumed_segment_refs)
            <= set(selected.context_packet.frozen_segment_refs)
            <= set(selected.context_packet.available_segment_refs)
        )
        assert selected.context_packet.publication_projection_id == str(projection_id)
        assert selected.context_packet.publication_projection_digest == publication["digest"]
        assert selected.candidate_product_guidance_context == ()
        assert selected.brand_reference_context == tuple(
            item.exact_text for item in selected.context_packet.segments if item.semantic_kind == "brand_fact"
        )
        visible_text = "\n".join(item.exact_text for item in selected.context_packet.segments)
        assert "笛语面向需要清楚日常穿衣选择的人" in visible_text
        assert "先回应具体处境" in visible_text
        assert "围绕一个可感知的变化" in visible_text
        assert legacy_text not in visible_text
        assert acceptance_text not in visible_text
        assert "可观察品类 14" not in visible_text
        assert all(
            item.semantic_kind in {"brand_fact", "expression_constraint", "creative_method"}
            for item in selected.context_packet.segments
        )

        life_selected = repository.select_brand_context_for_task(
            scope,
            context,
            "今天喝了一直喝的咖啡，忽然觉得味道有点不一样。",
            "brand_life_narrative",
            (),
        )
        assert life_selected.context_packet is not None
        assert life_selected.brand_reference_context == ()
        assert all(item.semantic_kind != "brand_fact" for item in life_selected.context_packet.segments)
        assert "笛语面向需要清楚日常穿衣选择的人" not in "\n".join(
            item.exact_text for item in life_selected.context_packet.segments
        )

        with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
            cursor.execute(
                "UPDATE brands SET current_publication_projection_id = NULL WHERE tenant_id = %s AND id = %s",
                (management_scope.tenant_id, management_scope.brand_id),
            )
        with pytest.raises(DomainError, match="品牌管理员确认"):
            repository.select_brand_context_for_task(
                scope,
                context,
                "没有发布投影时不能读取原始资料",
                "brand_life_narrative",
                (),
            )
    finally:
        _delete_import_scope(migrator_database_url, management_scope)


def test_brand_publication_confirmation_is_scoped_atomic_and_serialized(
    app_database_url: str,
    migrator_database_url: str,
    tmp_path: Path,
) -> None:
    scope, _ = _import_scope(migrator_database_url)
    bait_scope, _ = _import_scope(migrator_database_url)
    repository = PostgresWorkbenchRepository(app_database_url)
    trigger_name = f"tenant01_projection_fail_{uuid4().hex}"
    function_name = f"{trigger_name}_fn"
    try:
        source_root = tmp_path / "source"
        bait_root = tmp_path / "bait"
        source_root.mkdir()
        bait_root.mkdir()
        _write_source_batch(source_root)
        _write_source_batch(bait_root)
        TenantSourceImporter(app_database_url).apply(TenantSourceImporter(app_database_url).dry_run(scope, source_root))
        TenantSourceImporter(app_database_url).apply(
            TenantSourceImporter(app_database_url).dry_run(bait_scope, bait_root)
        )
        with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT segment.id
                  FROM brand_source_segments segment
                  JOIN brand_source_documents source
                    ON source.tenant_id = segment.tenant_id
                   AND source.id = segment.document_id
                 WHERE segment.tenant_id = %s
                   AND source.source_id = 'DIYU-BRAND-BASELINE-001'
                   AND segment.exact_text LIKE '这是 %%'
                 ORDER BY segment.source_locator
                 LIMIT 1
                """,
                (scope.tenant_id,),
            )
            row = cursor.fetchone()
            assert row is not None
            source_segment_id = UUID(str(row[0]))
            other_brand_id = uuid4()
            other_document_id = uuid4()
            other_version_id = uuid4()
            other_segment_id = uuid4()
            other_text = "另一品牌的来源不能进入当前品牌投影。"
            cursor.execute(
                "INSERT INTO brands "
                "(id, tenant_id, name, positioning, decision_order, tone) "
                "VALUES (%s, %s, '同租户另一品牌', '独立', '独立', '独立')",
                (other_brand_id, scope.tenant_id),
            )
            cursor.execute(
                """
                INSERT INTO brand_source_documents
                    (id, tenant_id, brand_id, source_id, embedded_title,
                     provenance_filename, source_version, original_status,
                     activation_status, authorization_source,
                     authorization_at, status, current_version_id, created_by)
                VALUES (%s, %s, %s, 'OTHER-BRAND-SOURCE-001',
                        '另一品牌来源', 'other-private.md', 'V1', '已确认',
                        'brand_user_authorized', 'bounded_test', now(),
                        'active', NULL, %s)
                """,
                (other_document_id, scope.tenant_id, other_brand_id, scope.user_id),
            )
            cursor.execute(
                """
                INSERT INTO brand_source_document_versions
                    (id, tenant_id, brand_id, document_id, source_version,
                     embedded_title, provenance_filename, original_status,
                     activation_status, authorization_source,
                     authorization_at, raw_sha256, normalized_sha256,
                     source_size, source_mtime_ns, content, created_by)
                VALUES (%s, %s, %s, %s, 'V1', '另一品牌来源',
                        'other-private.md', '已确认', 'brand_user_authorized',
                        'bounded_test', now(), %s, %s, %s, 1, %s, %s)
                """,
                (
                    other_version_id,
                    scope.tenant_id,
                    other_brand_id,
                    other_document_id,
                    sha256(other_text.encode()).hexdigest(),
                    sha256(other_text.encode()).hexdigest(),
                    len(other_text.encode()),
                    other_text,
                    scope.user_id,
                ),
            )
            cursor.execute(
                "UPDATE brand_source_documents SET current_version_id = %s WHERE tenant_id = %s AND id = %s",
                (other_version_id, scope.tenant_id, other_document_id),
            )
            cursor.execute(
                """
                INSERT INTO brand_source_segments
                    (id, tenant_id, brand_id, document_id,
                     document_version_id, segment_key, heading_path,
                     source_locator, exact_text, semantic_kind,
                     evidence_level, applicability, digest)
                VALUES (%s, %s, %s, %s, %s, 'other-brand-line',
                        ARRAY['稳定品牌信息'], 'line:1', %s, 'brand_fact',
                        'brand_user_authorized', '另一品牌', %s)
                """,
                (
                    other_segment_id,
                    scope.tenant_id,
                    other_brand_id,
                    other_document_id,
                    other_version_id,
                    other_text,
                    sha256(other_text.encode()).hexdigest(),
                ),
            )

        def candidate(text: str) -> dict[str, object]:
            return repository.create_brand_publication_candidate(
                scope,
                (
                    {
                        "source_segment_id": source_segment_id,
                        "publication_role": "public_brand_fact",
                        "published_text": text,
                        "applicability": ["brand_life_narrative"],
                    },
                ),
            )

        with pytest.raises(DomainError, match="当前品牌正在使用"):
            PostgresWorkbenchRepository(app_database_url).create_brand_publication_candidate(
                bait_scope,
                (
                    {
                        "source_segment_id": source_segment_id,
                        "publication_role": "public_brand_fact",
                        "published_text": "跨租户来源不得成为候选。",
                        "applicability": ["brand_life_narrative"],
                    },
                ),
            )
        with pytest.raises(DomainError, match="当前品牌正在使用"):
            repository.create_brand_publication_candidate(
                scope,
                (
                    {
                        "source_segment_id": other_segment_id,
                        "publication_role": "public_brand_fact",
                        "published_text": "同租户另一品牌也必须失败关闭。",
                        "applicability": ["brand_life_narrative"],
                    },
                ),
            )

        with pytest.raises(DomainError, match="明确这条品牌表达适用于"):
            repository.create_brand_publication_candidate(
                scope,
                (
                    {
                        "source_segment_id": source_segment_id,
                        "publication_role": "public_brand_fact",
                        "published_text": "不能作为所有内容的无条件固定段落。",
                        "applicability": [],
                    },
                ),
            )

        first = candidate("第一版公开品牌定位。")
        first_id = UUID(str(first["id"]))
        repository.confirm_brand_publication_projection(scope, first_id)
        failed = candidate("事务失败时不得替换当前版本。")
        failed_id = UUID(str(failed["id"]))

        with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                CREATE FUNCTION {function_name}() RETURNS trigger
                LANGUAGE plpgsql AS $$
                BEGIN
                  IF NEW.current_publication_projection_id = '{failed_id}'::uuid THEN
                    RAISE EXCEPTION 'bounded pointer failure';
                  END IF;
                  RETURN NEW;
                END
                $$
                """
            )
            cursor.execute(
                f"""
                CREATE TRIGGER {trigger_name}
                BEFORE UPDATE ON brands FOR EACH ROW
                EXECUTE FUNCTION {function_name}()
                """
            )
        try:
            with pytest.raises(psycopg.Error, match="bounded pointer failure"):
                repository.confirm_brand_publication_projection(scope, failed_id)
        finally:
            with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
                cursor.execute(f"DROP TRIGGER {trigger_name} ON brands")
                cursor.execute(f"DROP FUNCTION {function_name}()")

        with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT current_publication_projection_id FROM brands WHERE tenant_id = %s AND id = %s",
                (scope.tenant_id, scope.brand_id),
            )
            assert cursor.fetchone() == (first_id,)
            cursor.execute(
                "SELECT status FROM brand_publication_projections WHERE tenant_id = %s AND id = %s",
                (scope.tenant_id, failed_id),
            )
            assert cursor.fetchone() == ("candidate",)

        concurrent_ids = (
            UUID(str(candidate("并发确认候选甲。")["id"])),
            UUID(str(candidate("并发确认候选乙。")["id"])),
        )
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = tuple(
                executor.map(
                    lambda projection_id: PostgresWorkbenchRepository(
                        app_database_url
                    ).confirm_brand_publication_projection(scope, projection_id),
                    concurrent_ids,
                )
            )
        assert {result["status"] for result in results} == {"confirmed"}
        with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT count(*) FILTER (WHERE status = 'confirmed'),
                       count(*) FILTER (
                         WHERE status = 'confirmed'
                           AND id = (
                             SELECT current_publication_projection_id
                               FROM brands
                              WHERE tenant_id = %s AND id = %s
                           )
                       )
                  FROM brand_publication_projections
                 WHERE tenant_id = %s AND brand_id = %s
                """,
                (
                    scope.tenant_id,
                    scope.brand_id,
                    scope.tenant_id,
                    scope.brand_id,
                ),
            )
            assert cursor.fetchone() == (1, 1)
    finally:
        _delete_import_scope(migrator_database_url, bait_scope)
        _delete_import_scope(migrator_database_url, scope)


def test_tenant01_source_provenance_rejects_cross_tenant_brand_reference(
    app_database_url: str,
    migrator_database_url: str,
) -> None:
    first, _ = _import_scope(migrator_database_url)
    second, _ = _import_scope(migrator_database_url)
    try:
        with psycopg.connect(app_database_url) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(first.tenant_id),))
            with pytest.raises(psycopg.errors.ForeignKeyViolation):
                cursor.execute(
                    "INSERT INTO brand_source_documents "
                    "(id, tenant_id, brand_id, source_id, embedded_title, "
                    " provenance_filename, source_version, original_status, "
                    " activation_status, authorization_source, status, created_by) "
                    "VALUES (%s, %s, %s, 'CROSS-TENANT', '错误跨租户资料', "
                    " 'private.md', 'V1', '待确认', 'brand_user_authorized', "
                    " 'negative-test', 'active', %s)",
                    (uuid4(), first.tenant_id, second.brand_id, first.user_id),
                )
    finally:
        _delete_import_scope(migrator_database_url, first)
        _delete_import_scope(migrator_database_url, second)


def test_exact_preimage_classification_is_atomic_and_revokes_hidden_access(
    app_database_url: str,
    migrator_database_url: str,
    tmp_path: Path,
) -> None:
    scope, organization_id = _import_scope(migrator_database_url)
    synthetic_organization_id = uuid4()
    synthetic_user_id = uuid4()
    legacy_user_id = uuid4()
    synthetic_account_id = uuid4()
    session_ids = (uuid4(), uuid4())
    plan_path = tmp_path / "lifecycle.json"
    try:
        with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(scope.tenant_id),))
            cursor.execute(
                "INSERT INTO organizations "
                "(id, tenant_id, name, organization_level, business_data_kind) "
                "VALUES (%s, %s, '明确夹具组织', 'operating_unit', 'formal_business_data')",
                (synthetic_organization_id, scope.tenant_id),
            )
            cursor.execute(
                "INSERT INTO users "
                "(id, tenant_id, organization_id, display_name, entry_kind, business_data_kind) "
                "VALUES (%s, %s, %s, '明确夹具成员', 'tenant_user', 'formal_business_data'), "
                "       (%s, %s, %s, '来源不明旧成员', 'tenant_user', 'formal_business_data')",
                (
                    synthetic_user_id,
                    scope.tenant_id,
                    synthetic_organization_id,
                    legacy_user_id,
                    scope.tenant_id,
                    organization_id,
                ),
            )
            cursor.execute(
                "INSERT INTO content_accounts "
                "(id, tenant_id, brand_id, name, channel, carrier_of_account_id, "
                " control_organization_id, business_data_kind) "
                "VALUES (%s, %s, %s, '明确夹具账号', '小红书', NULL, %s, 'formal_business_data')",
                (
                    synthetic_account_id,
                    scope.tenant_id,
                    scope.brand_id,
                    synthetic_organization_id,
                ),
            )
            cursor.execute(
                "INSERT INTO auth_grants (id, tenant_id, user_id, account_id, role_name) "
                "VALUES (%s, %s, %s, %s, 'operator')",
                (uuid4(), scope.tenant_id, synthetic_user_id, synthetic_account_id),
            )
            for session_id, user_id in zip(session_ids, (synthetic_user_id, legacy_user_id), strict=True):
                cursor.execute(
                    "INSERT INTO tenant_sessions "
                    "(id, tenant_id, user_id, audience, token_digest, expires_at) "
                    "VALUES (%s, %s, %s, 'tenant-user', %s, now() + interval '1 day')",
                    (session_id, scope.tenant_id, user_id, sha256(str(session_id).encode()).hexdigest()),
                )
        plan_path.write_text(
            json.dumps(
                {
                    "contract_version": TENANT_LIFECYCLE_CONTRACT_VERSION,
                    "tenant_id": str(scope.tenant_id),
                    "brand_id": str(scope.brand_id),
                    "actor_user_id": str(scope.user_id),
                    "objects": [
                        {
                            "table": "organizations",
                            "object_id": str(synthetic_organization_id),
                            "target_kind": "synthetic_business_fixture",
                        },
                        {
                            "table": "users",
                            "object_id": str(synthetic_user_id),
                            "target_kind": "synthetic_business_fixture",
                        },
                        {
                            "table": "users",
                            "object_id": str(legacy_user_id),
                            "target_kind": "legacy_hidden",
                        },
                        {
                            "table": "content_accounts",
                            "object_id": str(synthetic_account_id),
                            "target_kind": "synthetic_business_fixture",
                        },
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        plan = TenantLifecyclePlan.from_file(plan_path)
        result = TenantLifecycleClassifier(app_database_url).apply(plan)
        assert result["changed"] == 4
        assert TenantLifecycleClassifier(app_database_url).apply(plan)["already_classified"] == 4
        with psycopg.connect(app_database_url) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(scope.tenant_id),))
            cursor.execute(
                "SELECT id, business_data_kind, enabled FROM users WHERE tenant_id = %s AND id = ANY(%s) ORDER BY id",
                (scope.tenant_id, [synthetic_user_id, legacy_user_id]),
            )
            users = {UUID(str(row[0])): (str(row[1]), bool(row[2])) for row in cursor.fetchall()}
            assert users[synthetic_user_id] == ("synthetic_business_fixture", False)
            assert users[legacy_user_id] == ("legacy_hidden", True)
            cursor.execute(
                "SELECT count(*) FROM tenant_sessions "
                "WHERE tenant_id = %s AND user_id = ANY(%s) AND revoked_at IS NULL",
                (scope.tenant_id, [synthetic_user_id, legacy_user_id]),
            )
            assert cursor.fetchone() == (0,)
            cursor.execute(
                "SELECT enabled, platform_enabled, business_data_kind FROM content_accounts "
                "WHERE tenant_id = %s AND id = %s",
                (scope.tenant_id, synthetic_account_id),
            )
            assert cursor.fetchone() == (False, False, "synthetic_business_fixture")
        repository = PostgresWorkbenchRepository(app_database_url)
        visible_people = repository.management_operators(scope)
        assert synthetic_user_id not in {UUID(str(person["id"])) for person in visible_people}
        assert legacy_user_id not in {UUID(str(person["id"])) for person in visible_people}
        archived_people = repository.management_operators(
            scope,
            include_archived=True,
        )
        assert {synthetic_user_id, legacy_user_id} <= {UUID(str(person["id"])) for person in archived_people}
        visible_accounts = repository.management_accounts(scope)
        assert synthetic_account_id not in {UUID(str(account["id"])) for account in visible_accounts}
    finally:
        with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(scope.tenant_id),))
            cursor.execute("DELETE FROM tenant_sessions WHERE tenant_id = %s", (scope.tenant_id,))
            cursor.execute("DELETE FROM auth_grants WHERE tenant_id = %s", (scope.tenant_id,))
        _delete_import_scope(migrator_database_url, scope)


def test_tenant01_evidence_binds_artifacts_reviews_and_persistence(tmp_path: Path) -> None:
    tmp_path.chmod(0o700)
    artifacts, reviews = _tenant01_evidence_inputs(tmp_path)

    write_tenant01_evidence(
        tmp_path,
        implementation_sha="a" * 40,
        schema_revision="20260812_39",
        image_digest="sha256:" + "b" * 64,
        source_manifest_digest="e" * 64,
        artifacts=artifacts,
        reviews=reviews,
        p5_preflight_file="p5-no-media.json",
        dm01_file="dm01.json",
    )

    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    human_review = json.loads((tmp_path / "human-review.json").read_text(encoding="utf-8"))
    assert len(manifest["artifacts"]) == len(TENANT01_CARD_IDS)
    assert all(record["task_id"] and record["run_id"] and record["version_id"] for record in manifest["artifacts"])
    assert all(
        record["raw_bundle_version"] == "ux03-gate-c-provider-stages-v1" and record["provider_request_count"] == 2
        for record in manifest["artifacts"]
    )
    assert all(
        record["publication_projection"]["creative_plan_version"] == "creative-plan-v3"
        and record["publication_projection"]["reviewed_kernel_digest"]
        and record["publication_projection"]["reviewed_creative_digest"]
        for record in manifest["artifacts"]
    )
    assert human_review["hard_boundary_violations"] == 0
    assert all(record["excerpts"]["body"] for record in human_review["reviews"])
    assert "overall_average" not in human_review
    assert all("average_score" not in record for record in human_review["reviews"])
    assert all(not path.stat().st_mode & 0o077 for path in tmp_path.iterdir())


def test_tenant01_snapshot_recompile_keeps_unselected_product_facts_in_registry(
    tmp_path: Path,
) -> None:
    tmp_path.chmod(0o700)
    artifacts, _ = _tenant01_evidence_inputs(tmp_path)
    artifact = next(item for item in artifacts if item.card_id == "P2")
    document = json.loads((tmp_path / artifact.artifact_file).read_text(encoding="utf-8"))
    snapshot = cast(dict[str, object], document["formal_snapshot"])
    raw_kernel = cast(dict[str, object], snapshot["creative_kernel_v2"])
    units = cast(list[dict[str, object]], raw_kernel["units"])
    dropped = next(unit for unit in units if unit["track"] == "trusted_fact")
    dropped_ref = cast(list[str], dropped["fact_refs"])[0]
    dropped_text = str(dropped["text"])
    raw_kernel["units"] = [unit for unit in units if unit is not dropped]
    blocks = cast(list[dict[str, object]], snapshot["immutable_product_fact_blocks"])
    dropped_block_id = next(str(block["fact_block_id"]) for block in blocks if block["fact_id"] == dropped_ref)
    raw_kernel["selected_fact_block_ids"] = [
        value for value in cast(list[str], raw_kernel["selected_fact_block_ids"]) if value != dropped_block_id
    ]
    kernel = kernel_from_document(raw_kernel)
    assert isinstance(kernel, CreativeKernelV1)
    snapshot["expression_plan_digest"] = kernel_digest(kernel)
    snapshot["reviewed_kernel_digest"] = kernel_digest(kernel)
    snapshot["reviewed_creative_digest"] = creative_units_digest(kernel)

    publication = cast(dict[str, object], snapshot["publication_contract"])
    assert dropped_ref in cast(list[str], publication["frozen_fact_refs"])
    assert all(
        dropped_ref not in cast(list[str], unit["fact_refs"])
        for unit in cast(list[dict[str, object]], raw_kernel["units"])
    )
    compiled = compile_tenant01_snapshot_delivery(snapshot, card_id="P2")
    assert dropped_text not in compiled.body


@pytest.mark.parametrize("field", ("artifact_sha256", "visible_digest"))
def test_tenant01_evidence_rejects_review_bound_to_another_artifact(
    tmp_path: Path,
    field: str,
) -> None:
    tmp_path.chmod(0o700)
    artifacts, reviews = _tenant01_evidence_inputs(tmp_path)
    invalid = (
        replace(reviews[0], artifact_sha256="0" * 64)
        if field == "artifact_sha256"
        else replace(reviews[0], visible_digest="0" * 64)
    )

    with pytest.raises(Tenant01EvidenceError, match="没有预先绑定当前 artifact"):
        _write_tenant01_fixture_evidence(
            tmp_path,
            artifacts,
            (invalid, *reviews[1:]),
        )


@pytest.mark.parametrize("mutation", ("wrong_region", "reused_excerpt"))
def test_tenant01_evidence_rejects_unmeaningful_review_regions(
    tmp_path: Path,
    mutation: str,
) -> None:
    tmp_path.chmod(0o700)
    artifacts, reviews = _tenant01_evidence_inputs(tmp_path)
    card_id = "cross_platform_douyin"
    review_index = next(index for index, review in enumerate(reviews) if review.card_id == card_id)
    review = reviews[review_index]
    excerpts = dict(review.excerpts)
    if mutation == "wrong_region":
        excerpts["media"] = review.excerpts["body"]
        message = "media 引用不在对应成品分区"
    else:
        excerpts["body"] = card_id
        excerpts["caption"] = card_id
        message = "引用不能跨分区复用"
    invalid_reviews = list(reviews)
    invalid_reviews[review_index] = replace(review, excerpts=excerpts)

    with pytest.raises(Tenant01EvidenceError, match=message):
        _write_tenant01_fixture_evidence(
            tmp_path,
            artifacts,
            tuple(invalid_reviews),
        )


def test_tenant01_evidence_rejects_review_not_grounded_in_artifact(tmp_path: Path) -> None:
    tmp_path.chmod(0o700)
    artifacts, reviews = _tenant01_evidence_inputs(tmp_path)
    first = reviews[0]
    invalid = replace(
        first,
        excerpts={**first.excerpts, "body": "只复述任务快照，不在成品中"},
    )

    with pytest.raises(Tenant01EvidenceError, match="不在对应成品分区"):
        write_tenant01_evidence(
            tmp_path,
            implementation_sha="a" * 40,
            schema_revision="20260812_39",
            image_digest="sha256:" + "b" * 64,
            source_manifest_digest="e" * 64,
            artifacts=artifacts,
            reviews=(invalid, *reviews[1:]),
            p5_preflight_file="p5-no-media.json",
            dm01_file="dm01.json",
        )


def test_tenant01_evidence_rejects_rehashed_plan_contract_drift(
    tmp_path: Path,
) -> None:
    tmp_path.chmod(0o700)
    artifacts, reviews = _tenant01_evidence_inputs(tmp_path)
    coffee = next(item for item in artifacts if item.card_id == "coffee")
    path = tmp_path / coffee.artifact_file
    document = json.loads(path.read_text(encoding="utf-8"))
    snapshot = document["formal_snapshot"]
    snapshot["publication_contract"]["primary_product"] = "local_response"
    publication = publication_contract_from_document(snapshot["publication_contract"])
    snapshot["publication_contract_digest"] = publication_contract_digest(publication)
    _write_private_json(path, document)

    with pytest.raises(Tenant01EvidenceError, match="没有绑定当前创作计划"):
        _write_tenant01_fixture_evidence(tmp_path, artifacts, reviews)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("platform_shape", "douyin_video:video"),
        ("tone_ids", ["tone:forged"]),
        ("primary_value", "local_response"),
    ),
)
def test_tenant01_evidence_uses_formal_creative_plan_validation(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    tmp_path.chmod(0o700)
    artifacts, reviews = _tenant01_evidence_inputs(tmp_path)
    path = tmp_path / "coffee.artifact.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["formal_snapshot"]["creative_plan_v2"][field] = value
    _write_private_json(path, document)

    with pytest.raises(Tenant01EvidenceError, match="没有绑定正式选择范围"):
        _write_tenant01_fixture_evidence(tmp_path, artifacts, reviews)


@pytest.mark.parametrize(
    "field",
    ("central_job", "audience_payoff", "account_refusals"),
)
def test_tenant01_evidence_rebuilds_rehashed_publication_semantics(
    tmp_path: Path,
    field: str,
) -> None:
    tmp_path.chmod(0o700)
    artifacts, reviews = _tenant01_evidence_inputs(tmp_path)
    path = tmp_path / "coffee.artifact.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    snapshot = document["formal_snapshot"]
    snapshot["publication_contract"][field] = f"伪造 {field}"
    publication = publication_contract_from_document(snapshot["publication_contract"])
    snapshot["publication_contract_digest"] = publication_contract_digest(publication)
    _write_private_json(path, document)

    with pytest.raises(Tenant01EvidenceError, match="语义没有绑定冻结输入"):
        _write_tenant01_fixture_evidence(tmp_path, artifacts, reviews)


def test_tenant01_evidence_preserves_frozen_fact_reference_order(
    tmp_path: Path,
) -> None:
    tmp_path.chmod(0o700)
    artifacts, _ = _tenant01_evidence_inputs(tmp_path)
    path = tmp_path / "P2.artifact.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    snapshot = cast(dict[str, object], document["formal_snapshot"])
    frame = frame_from_document(snapshot["narrative_frame"])
    publication_document = cast(dict[str, object], snapshot["publication_contract"])
    frozen_refs = cast(list[str], publication_document["frozen_fact_refs"])
    reordered = [*frozen_refs[1:], frozen_refs[0]]
    if reordered == list(frame.allowed_fact_ids):
        reordered = list(reversed(reordered))
    assert set(reordered) == set(frame.allowed_fact_ids)
    assert reordered != list(frame.allowed_fact_ids)
    publication_document["frozen_fact_refs"] = reordered
    publication = publication_contract_from_document(publication_document)
    snapshot["publication_contract_digest"] = publication_contract_digest(publication)
    _write_private_json(path, document)

    rebound, _, _, _ = _artifact_binding(path, card_id="P2")

    rebound_snapshot = cast(dict[str, object], rebound["formal_snapshot"])
    rebound_publication = cast(dict[str, object], rebound_snapshot["publication_contract"])
    assert rebound_publication["frozen_fact_refs"] == reordered


def test_tenant01_evidence_keeps_style_instruction_outside_fact_track(
    tmp_path: Path,
) -> None:
    tmp_path.chmod(0o700)
    artifacts, _ = _tenant01_evidence_inputs(tmp_path)
    path = tmp_path / "P1.artifact.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    snapshot = cast(dict[str, object], document["formal_snapshot"])
    publication_document = cast(dict[str, object], snapshot["publication_contract"])
    spans = cast(list[dict[str, object]], publication_document["intake_spans"])
    assert len(spans) == 1
    spans[0]["role"] = "style_or_revision_instruction"
    publication = publication_contract_from_document(publication_document)
    snapshot["publication_contract_digest"] = publication_contract_digest(publication)
    _write_private_json(path, document)

    rebound, _, _, _ = _artifact_binding(path, card_id="P1")

    rebound_snapshot = cast(dict[str, object], rebound["formal_snapshot"])
    rebound_publication = cast(dict[str, object], rebound_snapshot["publication_contract"])
    rebound_spans = cast(list[dict[str, object]], rebound_publication["intake_spans"])
    assert rebound_spans[0]["role"] == "style_or_revision_instruction"


@pytest.mark.parametrize(
    "mutation",
    (
        "body",
        "production_body",
        "media",
        "caption",
        "visible_provenance",
        "resource_refs",
    ),
)
def test_tenant01_evidence_rejects_rehashed_delivery_output_drift(
    tmp_path: Path,
    mutation: str,
) -> None:
    tmp_path.chmod(0o700)
    artifacts, reviews = _tenant01_evidence_inputs(tmp_path)
    card_id = "coffee"
    path = tmp_path / f"{card_id}.artifact.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    if mutation == "body":
        document["body"] += "\n这段额外正文没有经过冻结编译。"
        document["visible_digest"] = visible_digest(
            document["outline"],
            document["body"],
        )
    elif mutation == "production_body":
        document["production"]["full_body"] += "\n伪造正文分区。"
    elif mutation == "media":
        document["production"]["hero_image"] += "\n伪造媒体说明。"
    elif mutation == "caption":
        document["production"]["release_caption_and_interaction"] += "\n伪造发布配文。"
    elif mutation == "visible_provenance":
        document["formal_snapshot"]["visible_provenance"]["body"] = ["unit:forged"]
    else:
        document["formal_snapshot"]["delivery_resource_refs"] = ["resource:forged"]
    _write_private_json(path, document)
    reviews = _rebind_tenant01_review(
        tmp_path,
        reviews,
        card_id=card_id,
    )
    _write_tenant01_generation_ledger(
        tmp_path,
        artifacts=artifacts,
        implementation_sha="a" * 40,
    )

    with pytest.raises(Tenant01EvidenceError, match="不是冻结输入的确定性编译结果"):
        _write_tenant01_fixture_evidence(tmp_path, artifacts, reviews)


@pytest.mark.parametrize(
    "digest_field",
    (
        "expression_plan_digest",
        "reviewed_kernel_digest",
        "reviewed_creative_digest",
    ),
)
def test_tenant01_evidence_rejects_each_unbound_creative_digest(
    tmp_path: Path,
    digest_field: str,
) -> None:
    tmp_path.chmod(0o700)
    artifacts, reviews = _tenant01_evidence_inputs(tmp_path)
    coffee = next(item for item in artifacts if item.card_id == "coffee")
    path = tmp_path / coffee.artifact_file
    document = json.loads(path.read_text(encoding="utf-8"))
    document["formal_snapshot"][digest_field] = "0" * 64
    _write_private_json(path, document)

    with pytest.raises(Tenant01EvidenceError, match="冻结创作单元摘要无效"):
        _write_tenant01_fixture_evidence(tmp_path, artifacts, reviews)


def test_tenant01_evidence_rejects_nonpositive_persisted_version(
    tmp_path: Path,
) -> None:
    tmp_path.chmod(0o700)
    artifacts, reviews = _tenant01_evidence_inputs(tmp_path)
    path = tmp_path / "coffee.artifact.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["version"] = 0
    _write_private_json(path, document)

    with pytest.raises(Tenant01EvidenceError, match="version 缺少正式正整数版本"):
        _write_tenant01_fixture_evidence(tmp_path, artifacts, reviews)


@pytest.mark.parametrize("field", ("task_id", "run_id", "version_id"))
def test_tenant01_evidence_rejects_cross_card_uuid_reuse(
    tmp_path: Path,
    field: str,
) -> None:
    tmp_path.chmod(0o700)
    artifacts, reviews = _tenant01_evidence_inputs(tmp_path)
    first_path = tmp_path / "P1.artifact.json"
    second_path = tmp_path / "P2.artifact.json"
    first = json.loads(first_path.read_text(encoding="utf-8"))
    second = json.loads(second_path.read_text(encoding="utf-8"))
    second[field] = first[field]
    _write_private_json(second_path, second)
    reviews = _rebind_tenant01_review(
        tmp_path,
        reviews,
        card_id="P2",
    )
    _write_tenant01_generation_ledger(
        tmp_path,
        artifacts=artifacts,
        implementation_sha="a" * 40,
    )

    with pytest.raises(
        Tenant01EvidenceError,
        match=rf"复用了同一个 {field}",
    ):
        _write_tenant01_fixture_evidence(tmp_path, artifacts, reviews)


def test_tenant01_evidence_rejects_p2_without_required_product_plan(
    tmp_path: Path,
) -> None:
    tmp_path.chmod(0o700)
    artifacts, reviews = _tenant01_evidence_inputs(tmp_path)
    p2 = next(item for item in artifacts if item.card_id == "P2")
    path = tmp_path / p2.artifact_file
    document = json.loads(path.read_text(encoding="utf-8"))
    snapshot = document["formal_snapshot"]
    snapshot["product_value_contract"] = None
    snapshot["product_value_contract_digest"] = None
    snapshot["publication_contract"]["product_value_contract_digest"] = None
    publication = publication_contract_from_document(snapshot["publication_contract"])
    snapshot["publication_contract_digest"] = publication_contract_digest(publication)
    _write_private_json(path, document)

    with pytest.raises(Tenant01EvidenceError, match="商品语义计划绑定漂移"):
        _write_tenant01_fixture_evidence(tmp_path, artifacts, reviews)


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("wrong_card", "绑定到了另一张卡或版本"),
        ("transport_retry", "调用顺序或重试证据无效"),
        ("wrong_stage", "调用顺序或重试证据无效"),
        ("wrong_model", "调用顺序或重试证据无效"),
        ("bad_request_hash", "请求或响应摘要无效"),
        ("empty_choices", "原始模型响应为空"),
        ("empty_content", "原始模型响应为空"),
        ("response_mismatch", "请求或响应摘要无效"),
    ),
)
def test_tenant01_evidence_rejects_unbound_raw_provider_metadata(
    tmp_path: Path,
    mutation: str,
    message: str,
) -> None:
    tmp_path.chmod(0o700)
    artifacts, reviews = _tenant01_evidence_inputs(tmp_path)
    coffee = next(item for item in artifacts if item.card_id == "coffee")
    path = tmp_path / coffee.raw_response_file
    document = json.loads(path.read_text(encoding="utf-8"))
    if mutation == "wrong_card":
        document["card_id"] = "P1"
    elif mutation == "transport_retry":
        document["responses"][0]["transport_retries"] = 1
    elif mutation == "wrong_stage":
        document["responses"][0]["stage"] = "repair"
    elif mutation == "wrong_model":
        document["responses"][0]["model"] = "forged-model"
        document["responses"][0]["response"]["model"] = "forged-model"
        document["responses"][0]["response_sha256"] = _tenant01_json_digest(document["responses"][0]["response"])
    elif mutation == "bad_request_hash":
        document["responses"][0]["request_sha256"] = "not-a-sha256"
    elif mutation == "empty_choices":
        document["responses"][0]["response"]["choices"] = []
        document["responses"][0]["response_sha256"] = _tenant01_json_digest(document["responses"][0]["response"])
    elif mutation == "empty_content":
        document["responses"][0]["response"]["choices"][0]["message"]["content"] = " "
        document["responses"][0]["response_sha256"] = _tenant01_json_digest(document["responses"][0]["response"])
    else:
        document["responses"][0]["response"]["choices"][0]["message"]["content"] = "篡改但不更新响应摘要"
    _write_private_json(path, document)

    with pytest.raises(Tenant01EvidenceError, match=message):
        _write_tenant01_fixture_evidence(tmp_path, artifacts, reviews)


def test_tenant01_evidence_ledger_binds_original_request_hash(
    tmp_path: Path,
) -> None:
    tmp_path.chmod(0o700)
    artifacts, reviews = _tenant01_evidence_inputs(tmp_path)
    path = tmp_path / "coffee.raw.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["responses"][0]["request_sha256"] = "f" * 64
    _write_private_json(path, document)

    with pytest.raises(Tenant01EvidenceError, match="不再匹配只读生成账本"):
        _write_tenant01_fixture_evidence(tmp_path, artifacts, reviews)


def test_tenant01_evidence_rejects_mutable_generation_ledger(
    tmp_path: Path,
) -> None:
    tmp_path.chmod(0o700)
    artifacts, reviews = _tenant01_evidence_inputs(tmp_path)
    (tmp_path / TENANT01_GENERATION_LEDGER_FILE).chmod(0o600)

    with pytest.raises(Tenant01EvidenceError, match="生成账本必须.*只读"):
        _write_tenant01_fixture_evidence(tmp_path, artifacts, reviews)


def test_tenant01_evidence_rejects_rehashed_input_span_not_in_user_premise(
    tmp_path: Path,
) -> None:
    tmp_path.chmod(0o700)
    artifacts, reviews = _tenant01_evidence_inputs(tmp_path)
    p1 = next(item for item in artifacts if item.card_id == "P1")
    path = tmp_path / p1.artifact_file
    document = json.loads(path.read_text(encoding="utf-8"))
    snapshot = document["formal_snapshot"]
    span = snapshot["publication_contract"]["intake_spans"][0]
    forged = user_fact_candidates(("请完成 X1。",))[0]
    span.update(
        {
            "source_id": forged.source_id,
            "exact_text": forged.exact_text,
            "turn_index": forged.turn_index,
            "start_offset": forged.start_offset,
            "end_offset": forged.end_offset,
            "start_byte": forged.start_byte,
            "end_byte": forged.end_byte,
        }
    )
    publication = publication_contract_from_document(snapshot["publication_contract"])
    snapshot["publication_contract_digest"] = publication_contract_digest(publication)
    _write_private_json(path, document)

    with pytest.raises(Tenant01EvidenceError, match="没有绑定用户原文"):
        _write_tenant01_fixture_evidence(tmp_path, artifacts, reviews)


@pytest.mark.parametrize(
    ("missing_key", "message"),
    (
        ("publication_contract", "缺少冻结发布责任合同"),
        ("creative_plan_v2", "缺少冻结创作计划"),
    ),
)
def test_tenant01_evidence_rejects_missing_publication_inputs(
    tmp_path: Path,
    missing_key: str,
    message: str,
) -> None:
    tmp_path.chmod(0o700)
    artifacts, reviews = _tenant01_evidence_inputs(tmp_path)
    coffee = next(item for item in artifacts if item.card_id == "coffee")
    path = tmp_path / coffee.artifact_file
    document = json.loads(path.read_text(encoding="utf-8"))
    snapshot = document["formal_snapshot"]
    del snapshot[missing_key]
    _write_private_json(path, document)

    with pytest.raises(Tenant01EvidenceError, match=message):
        write_tenant01_evidence(
            tmp_path,
            implementation_sha="a" * 40,
            schema_revision="20260813_40",
            image_digest="sha256:" + "b" * 64,
            source_manifest_digest="e" * 64,
            artifacts=artifacts,
            reviews=reviews,
            p5_preflight_file="p5-no-media.json",
            dm01_file="dm01.json",
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("low_natural_language", "natural_language"),
        ("missing_media_reference", "media 引用缺少有意义文本"),
        ("false_demonstration_check", "可演示成品检查未通过"),
    ),
)
def test_tenant01_evidence_rejects_dimension_and_binary_false_greens(
    tmp_path: Path,
    mutation: str,
    message: str,
) -> None:
    tmp_path.chmod(0o700)
    artifacts, reviews = _tenant01_evidence_inputs(tmp_path)
    first = reviews[0]
    scores = dict(first.scores)
    excerpts = dict(first.excerpts)
    checks = dict(first.demonstration_checks)
    if mutation == "low_natural_language":
        scores["natural_language"] = 3
    elif mutation == "missing_media_reference":
        excerpts["media"] = ""
    else:
        checks["scaffolding_free"] = False
    invalid = replace(
        first,
        scores=scores,
        excerpts=excerpts,
        demonstration_checks=checks,
        verdict="PASS",
    )
    with pytest.raises(Tenant01EvidenceError, match=message):
        write_tenant01_evidence(
            tmp_path,
            implementation_sha="a" * 40,
            schema_revision="20260813_40",
            image_digest="sha256:" + "b" * 64,
            source_manifest_digest="e" * 64,
            artifacts=artifacts,
            reviews=(invalid, *reviews[1:]),
            p5_preflight_file="p5-no-media.json",
            dm01_file="dm01.json",
        )


def test_tenant01_evidence_rejects_repeated_writer_paragraph_across_platforms(
    tmp_path: Path,
) -> None:
    tmp_path.chmod(0o700)
    artifacts, reviews = _tenant01_evidence_inputs(tmp_path)
    updated_reviews = list(reviews)
    repeated = "两个平台被故意设置成完全相同、长度足够触发检查的 Writer 正文段落，不能作为平台适配证据。"
    for card_id in ("cross_platform_xhs", "cross_platform_douyin"):
        item = next(record for record in artifacts if record.card_id == card_id)
        path = tmp_path / item.artifact_file
        document = json.loads(path.read_text(encoding="utf-8"))
        snapshot = document["formal_snapshot"]
        for unit in snapshot["creative_kernel_v2"]["units"]:
            if unit["purpose"] == "body" and unit["text_source"] == "writer":
                unit["text"] = repeated
        kernel = kernel_from_document(snapshot["creative_kernel_v2"])
        assert isinstance(kernel, CreativeKernelV1)
        snapshot["expression_plan_digest"] = kernel_digest(kernel)
        snapshot["reviewed_kernel_digest"] = kernel_digest(kernel)
        snapshot["reviewed_creative_digest"] = creative_units_digest(kernel)
        _write_private_json(path, document)
        artifact_sha256, visible_digest_value = _recompile_tenant01_artifact(path)
        review_index = next(index for index, review in enumerate(updated_reviews) if review.card_id == card_id)
        review = updated_reviews[review_index]
        updated_reviews[review_index] = replace(
            review,
            artifact_sha256=artifact_sha256,
            visible_digest=visible_digest_value,
            excerpts={**review.excerpts, "body": repeated},
            body_excerpt=repeated,
        )
    _write_tenant01_generation_ledger(
        tmp_path,
        artifacts=artifacts,
        implementation_sha="a" * 40,
    )
    with pytest.raises(Tenant01EvidenceError, match="非必要 Writer 完整段落重复"):
        _write_tenant01_fixture_evidence(
            tmp_path,
            artifacts,
            tuple(updated_reviews),
        )


def test_tenant01_evidence_allows_only_snapshot_bound_repeated_user_fact(
    tmp_path: Path,
) -> None:
    tmp_path.chmod(0o700)
    artifacts, reviews = _tenant01_evidence_inputs(tmp_path)
    updated_reviews = list(reviews)
    repeated_fact = "今天整理衣服时突然觉得少一点也能让选择更清楚。"
    target_cards = ("cross_platform_xhs", "cross_platform_douyin")
    for card_id in target_cards:
        item = next(record for record in artifacts if record.card_id == card_id)
        path = tmp_path / item.artifact_file
        document = json.loads(path.read_text(encoding="utf-8"))
        snapshot = document["formal_snapshot"]
        candidates = user_fact_candidates((repeated_fact,))
        spans = tuple(
            PublicationInputSpanV1(
                source_id=candidate.source_id,
                role="observable_actuality",
                exact_text=candidate.exact_text,
                turn_index=candidate.turn_index,
                start_offset=candidate.start_offset,
                end_offset=candidate.end_offset,
                start_byte=candidate.start_byte,
                end_byte=candidate.end_byte,
            )
            for candidate in candidates
        )
        frame = new_frame(
            "actuality_reflection",
            tuple(candidate.exact_text for candidate in candidates),
            (),
            user_fact_source_ids=tuple(candidate.source_id for candidate in candidates),
        )
        target: ContentTarget = "douyin_video" if card_id == "cross_platform_douyin" else "xiaohongshu_graphic"
        media_format: MediaFormat = "video" if target == "douyin_video" else "graphic"
        plan = build_creative_plan(
            topic_spans=(repeated_fact,),
            primary_value="brand_life_narrative",
            tone_ids=(ACCOUNT_BASELINE_TONE_ID,),
            mechanism_id=None,
            target_shape=platform_shape(target, media_format),
        )
        publication = build_publication_contract(
            primary_product="brand_life_narrative",
            topic_spans=(repeated_fact,),
            topic_origin="explicit_user",
            known_conditions=tuple(candidate.exact_text for candidate in candidates),
            frozen_fact_refs=tuple(frame.allowed_fact_ids),
            intake_spans=spans,
            account_identity="测试表达身份",
            account_audience="需要清楚选择的受众",
            account_attention="先看具体条件再形成判断",
            account_response_boundary="不补造现实或商品事实",
            source_profile_id="44444444-4444-4444-8444-444444444444",
            source_profile_version=2,
            publication_projection_id=("11111111-1111-4111-8111-111111111111"),
            publication_projection_version=1,
            publication_projection_digest="d" * 64,
            product_value_contract_digest=None,
        )
        kernel = build_kernel_skeleton(
            frame=frame,
            fact_registry=(
                FrozenFactRecord(
                    fact_id=candidates[0].source_id,
                    exact_text=candidates[0].exact_text,
                    fact_kind="user_actuality",
                ),
            ),
            constraint_refs=("constraint:publication-contract-v2",),
            program_id=OBSERVATION_ONLY_PROGRAM,
            allowed_resource_ids=(),
            media_format=media_format,
            kernel_version=KERNEL_VERSION,
            primary_product="brand_life_narrative",
        )
        writer_text = {
            "title": document["outline"],
            "natural_guide": f"{card_id} 导读证据，说明读者能获得什么。",
            "body": f"{card_id} 正文证据，说明本篇的主要价值。",
            "release_caption": f"{card_id} 发布配文证据，不扩写事实。",
        }
        kernel = replace(
            kernel,
            units=tuple(
                replace(unit, text=writer_text[unit.purpose]) if unit.text_source == "writer" else unit
                for unit in kernel.units
            ),
        )
        snapshot["user_premise"] = repeated_fact
        snapshot["creative_plan_v2"] = creative_plan_document(plan)
        snapshot["publication_contract"] = publication_contract_document(publication)
        snapshot["publication_contract_digest"] = publication_contract_digest(publication)
        snapshot["narrative_frame"] = frame_document(frame)
        snapshot["creative_kernel_v2"] = kernel_document(kernel)
        snapshot["expression_plan_digest"] = kernel_digest(kernel)
        snapshot["reviewed_kernel_digest"] = kernel_digest(kernel)
        snapshot["reviewed_creative_digest"] = creative_units_digest(kernel)
        _write_private_json(path, document)
        artifact_sha256, visible_digest_value = _recompile_tenant01_artifact(path)
        assert repeated_fact in json.loads(path.read_text(encoding="utf-8"))["body"]
        review_index = next(index for index, review in enumerate(updated_reviews) if review.card_id == card_id)
        updated_reviews[review_index] = replace(
            updated_reviews[review_index],
            artifact_sha256=artifact_sha256,
            visible_digest=visible_digest_value,
        )

    _write_tenant01_generation_ledger(
        tmp_path,
        artifacts=artifacts,
        implementation_sha="a" * 40,
    )
    _write_tenant01_fixture_evidence(
        tmp_path,
        artifacts,
        tuple(updated_reviews),
    )


def test_tenant01_artifact_projects_and_rebuilds_frozen_delivery(
    tmp_path: Path,
) -> None:
    tmp_path.chmod(0o700)
    artifacts, _ = _tenant01_evidence_inputs(tmp_path)
    source = json.loads(
        (tmp_path / next(item.artifact_file for item in artifacts if item.card_id == "coffee")).read_text(
            encoding="utf-8"
        )
    )
    snapshot = source["formal_snapshot"]
    user_premise = snapshot["user_premise"]
    artifact = tenant01_runner._artifact(
        tenant01_runner._Card(
            "coffee",
            user_premise,
            "xiaohongshu_graphic",
        ),
        {
            "task_id": source["task_id"],
            "version": source["version"],
            "outline": source["outline"],
            "body": source["body"],
        },
        snapshot,
        run_id=UUID(source["run_id"]),
        version_id=UUID(source["version_id"]),
    )

    projected = cast(dict[str, object], artifact["formal_snapshot"])
    assert projected["user_premise"] == user_premise
    assert projected["creative_plan_v2"] == snapshot["creative_plan_v2"]
    assert projected["reviewed_kernel_digest"] == snapshot["reviewed_kernel_digest"]
    assert projected["reviewed_creative_digest"] == snapshot["reviewed_creative_digest"]
    assert artifact["production"] == source["production"]


def test_tenant01_finalizer_rejects_dirty_worktree_without_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tmp_path.chmod(0o700)
    _write_private_json(tmp_path / "preserved.json", {"status": "failed"})
    before = _tenant01_file_state(tmp_path)
    implementation_sha = "a" * 40
    monkeypatch.setattr(tenant01_runner, "_current_head", lambda: implementation_sha)
    monkeypatch.setattr(tenant01_runner, "_git_status", lambda: " M src/tool")

    with pytest.raises(RuntimeError, match="clean worktree"):
        tenant01_runner._finalize(_tenant01_finalize_args(tmp_path, implementation_sha))

    assert _tenant01_file_state(tmp_path) == before


def test_tenant01_human_review_v2_parses_every_required_field(
    tmp_path: Path,
) -> None:
    tmp_path.chmod(0o700)
    _, reviews = _tenant01_evidence_inputs(tmp_path)
    review_path = tmp_path / "review-input.json"
    _write_private_json(review_path, _tenant01_review_v2_document(reviews))

    parsed = tenant01_runner._reviews(review_path)

    assert len(parsed) == len(TENANT01_CARD_IDS)
    assert all(review.hard_boundary == "PASS" for review in parsed)
    assert all(review.product_usable == "PASS" for review in parsed)
    assert all(review.dimension_rationales for review in parsed)
    assert all(review.reviewer_kind == "single_execution_product_review" for review in parsed)


def test_tenant01_human_review_v2_rejects_prefilled_pass_without_artifact_quotes(
    tmp_path: Path,
) -> None:
    tmp_path.chmod(0o700)
    _, reviews = _tenant01_evidence_inputs(tmp_path)
    document = _tenant01_review_v2_document(reviews)
    raw_reviews = document["reviews"]
    assert isinstance(raw_reviews, list)
    first = raw_reviews[0]
    assert isinstance(first, dict)
    first["body_excerpt"] = ""
    review_path = tmp_path / "review-input.json"
    _write_private_json(review_path, document)

    parsed = tenant01_runner._reviews(review_path)
    with pytest.raises(Tenant01EvidenceError, match="body 引用缺少有意义文本"):
        _write_tenant01_fixture_evidence(
            tmp_path,
            tuple(
                Tenant01ArtifactInput(
                    card_id,
                    f"{card_id}.artifact.json",
                    f"{card_id}.raw.json",
                )
                for card_id in sorted(TENANT01_CARD_IDS)
            ),
            parsed,
        )


@pytest.mark.parametrize(
    ("marker", "message"),
    (
        ("evidence_kind", "WIP evidence"),
        ("P2.failed.raw.json", "failed evidence root is immutable"),
        ("suite-failure.json", "failed evidence root is immutable"),
        ("human-review-failure.json", "failed evidence root is immutable"),
        ("human-review.json", "final evidence outputs already exist"),
        ("manifest.json", "final evidence outputs already exist"),
        ("SHA256SUMS", "final evidence outputs already exist"),
    ),
)
def test_tenant01_finalizer_preserves_nonfinal_or_existing_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    marker: str,
    message: str,
) -> None:
    tmp_path.chmod(0o700)
    implementation_sha = "a" * 40
    _write_tenant01_suite_config(
        tmp_path,
        implementation_sha=implementation_sha,
        evidence_kind=("wip_shared_root_diagnosis_only" if marker == "evidence_kind" else None),
    )
    if marker != "evidence_kind":
        _write_private_json(tmp_path / marker, {"status": "preserved"})
    before = _tenant01_file_state(tmp_path)
    monkeypatch.setattr(tenant01_runner, "_current_head", lambda: implementation_sha)
    monkeypatch.setattr(tenant01_runner, "_git_status", lambda: "")

    with pytest.raises(RuntimeError, match=message):
        tenant01_runner._finalize(_tenant01_finalize_args(tmp_path, implementation_sha))

    assert _tenant01_file_state(tmp_path) == before


@pytest.mark.parametrize(
    "mutation",
    ("wrong_sha", "wrong_provider", "incomplete_cards"),
)
def test_tenant01_finalizer_rejects_non_authoritative_suite_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    tmp_path.chmod(0o700)
    implementation_sha = "a" * 40
    _write_tenant01_suite_config(
        tmp_path,
        implementation_sha=implementation_sha,
    )
    config_path = tmp_path / "suite-config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if mutation == "wrong_sha":
        config["implementation_sha"] = "b" * 40
    elif mutation == "wrong_provider":
        config["provider_config"]["max_retries"] = 1
    else:
        config["cards"] = config["cards"][:-1]
    _write_private_json(config_path, config)
    before = _tenant01_file_state(tmp_path)
    monkeypatch.setattr(tenant01_runner, "_current_head", lambda: implementation_sha)
    monkeypatch.setattr(tenant01_runner, "_git_status", lambda: "")

    with pytest.raises(RuntimeError, match="not authoritative"):
        tenant01_runner._finalize(_tenant01_finalize_args(tmp_path, implementation_sha))

    assert _tenant01_file_state(tmp_path) == before


def test_tenant01_finalizer_rejects_generation_ledger_hash_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tmp_path.chmod(0o700)
    implementation_sha = "a" * 40
    _write_tenant01_suite_config(
        tmp_path,
        implementation_sha=implementation_sha,
    )
    config_path = tmp_path / "suite-config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["generation_ledger"]["sha256"] = "0" * 64
    _write_private_json(config_path, config)
    before = _tenant01_file_state(tmp_path)
    monkeypatch.setattr(tenant01_runner, "_current_head", lambda: implementation_sha)
    monkeypatch.setattr(tenant01_runner, "_git_status", lambda: "")

    with pytest.raises(
        RuntimeError,
        match="generation ledger is unavailable or mutable",
    ):
        tenant01_runner._finalize(_tenant01_finalize_args(tmp_path, implementation_sha))

    assert _tenant01_file_state(tmp_path) == before


def test_tenant01_golden_p2_preflight_requires_product_specific_value() -> None:
    with pytest.raises(RuntimeError, match="product-specific value contract"):
        _assert_p2_product_ready(
            (
                ProductFact(
                    "SKU-ONE-COLOR",
                    {"category": "上装", "colors": ["炭灰"]},
                    display_name="单一颜色候选商品",
                ),
            )
        )

    _assert_p2_product_ready(
        (
            ProductFact(
                "SKU-TWO-COLORS",
                {"category": "上装", "colors": ["炭灰", "深绿"]},
                display_name="两种可见颜色候选商品",
            ),
        )
    )
