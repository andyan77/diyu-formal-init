from __future__ import annotations

import re

from src.shared.delivery_compiler import (
    DELIVERY_COMPILER_VERSION,
    MEDIA_NATIVE_DELIVERY_COMPILER_VERSION,
)
from src.shared.errors import GenerationFailed
from src.shared.types import (
    GeneratedArtifact,
    GraphicProductionBundle,
    P1SemanticContract,
    P2SemanticContract,
    P3SemanticContract,
    P4SemanticContract,
    P5SemanticContract,
    VideoProductionBundle,
)


def assert_content_complete(artifact: GeneratedArtifact) -> None:
    """Validate one product contract plus its executable current-media pack."""
    if not artifact.body.strip():
        raise GenerationFailed("内容成品为空")
    contract = artifact.semantic_contract
    expected_types = {
        "dressing_decision": P1SemanticContract,
        "product_truth": P2SemanticContract,
        "brand_life_narrative": P3SemanticContract,
        "local_response": P4SemanticContract,
        "visual_styling_story": P5SemanticContract,
    }
    expected = expected_types[artifact.primary_product]
    if not isinstance(contract, expected) or any(
        not str(value).strip() for value in vars(contract).values()
    ):
        raise GenerationFailed("内容成品缺少当前主要产品的必要部分")
    compiler_version = (artifact.completion_snapshot_patch or {}).get(
        "delivery_compiler_version"
    )
    media_native = compiler_version in {
        MEDIA_NATIVE_DELIVERY_COMPILER_VERSION,
        DELIVERY_COMPILER_VERSION,
    }
    if isinstance(artifact.production, VideoProductionBundle):
        required = tuple(
            value
            for key, value in vars(artifact.production).items()
            if key != "optional_capture_suggestion"
        )
        headings: tuple[str, ...] = (
            (
                "标题",
                "表达范围",
                "内容看点",
                "封面/开头",
                "完整台词/解说",
                "画面动作",
                "字幕策略",
                "声音与制作提示",
                "自然时长",
                "发布配文",
            )
            if media_native
            else (
                "标题",
                "内容概要",
                "封面/首帧",
                "完整观看链",
                "完整台词/解说",
                "画面与动作",
                "字幕",
                "声音与制作提示",
                "自然时长",
                "发布配文与互动",
            )
        )
    elif isinstance(artifact.production, GraphicProductionBundle):
        required = tuple(
            value
            for key, value in vars(artifact.production).items()
            if key != "optional_capture_suggestion"
        )
        headings = (
            (
                "标题",
                "表达范围",
                "内容看点",
                "首图",
                "图序与每张职责",
                "完整正文",
                "拍摄/排版提示",
                "发布配文",
            )
            if media_native
            else (
                "标题",
                "内容概要",
                "首图方案",
                "图序与每张职责",
                "完整发布正文",
                "拍摄/排版提示",
                "发布配文与互动",
            )
        )
    else:  # pragma: no cover - typing and constructors keep this unreachable.
        raise GenerationFailed("内容成品媒体格式无效")
    if any(not section.strip() for section in required):
        raise GenerationFailed("内容成品缺少可执行的媒体制作部分")
    if not all(heading in artifact.body for heading in headings):
        raise GenerationFailed("内容成品正文没有完整可见文字包")
    if (
        artifact.production.optional_capture_suggestion
        and "可选补拍建议" not in artifact.body
    ):
        raise GenerationFailed("内容成品遗漏可见的可选补拍建议")
    # The semantic contract remains persisted and validated above, but it is no longer copied
    # verbatim into the user artifact as compiler scaffolding. Source binding and product-specific
    # generation checks establish the contract; the production bundle is the user-facing result.
    if re.search(r"1[3-9]\d{9}|[\w.+-]+@[\w.-]+|订单号?\s*[:：]?\s*[A-Za-z0-9-]+", artifact.body):
        raise GenerationFailed("内容成品包含个人标识")
    internal_marker_view = _without_frozen_fact_literals(artifact)
    if re.search(
        r"\bP[1-5]\b|dressing_decision|product_truth|brand_life_narrative|local_response|visual_styling_story",
        internal_marker_view,
        re.IGNORECASE,
    ):
        raise GenerationFailed("内容成品泄露内部产品标识")


def _without_frozen_fact_literals(artifact: GeneratedArtifact) -> str:
    """Keep trusted fact bytes while excluding them from internal-label scanning."""

    patch = artifact.completion_snapshot_patch
    if not isinstance(patch, dict):
        return artifact.body
    raw_blocks = patch.get("immutable_product_fact_blocks")
    if not isinstance(raw_blocks, list):
        return artifact.body
    value = artifact.body
    for raw_block in raw_blocks:
        if not isinstance(raw_block, dict):
            continue
        canonical_text = raw_block.get("canonical_text")
        if isinstance(canonical_text, str) and canonical_text:
            value = value.replace(canonical_text, "")
    return value


def assert_p1_complete(artifact: GeneratedArtifact) -> None:
    """Compatibility entrypoint retained for the existing P1 callers."""
    assert_content_complete(artifact)
