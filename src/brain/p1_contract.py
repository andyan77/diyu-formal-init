from __future__ import annotations

import re

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
    if isinstance(artifact.production, VideoProductionBundle):
        required = vars(artifact.production).values()
        headings: tuple[str, ...] = (
            "标题",
            "自然导读",
            "封面/首帧",
            "完整观看链",
            "完整台词/解说",
            "画面与动作",
            "字幕",
            "声音与制作提示",
            "自然时长",
            "发布配文与互动",
        )
    elif isinstance(artifact.production, GraphicProductionBundle):
        required = vars(artifact.production).values()
        headings = (
            "标题",
            "自然导读",
            "首图方案",
            "图序与每张职责",
            "完整发布正文",
            "拍摄/排版提示",
            "发布配文与互动",
        )
    else:  # pragma: no cover - typing and constructors keep this unreachable.
        raise GenerationFailed("内容成品媒体格式无效")
    if any(not section.strip() for section in required):
        raise GenerationFailed("内容成品缺少可执行的媒体制作部分")
    if not all(heading in artifact.body for heading in headings):
        raise GenerationFailed("内容成品正文没有完整可见文字包")
    if not all(value in artifact.body for value in vars(contract).values()):
        raise GenerationFailed("内容成品没有忠实呈现当前主要产品的必要部分")
    if re.search(r"1[3-9]\d{9}|[\w.+-]+@[\w.-]+|订单号?\s*[:：]?\s*[A-Za-z0-9-]+", artifact.body):
        raise GenerationFailed("内容成品包含个人标识")
    if re.search(
        r"\bP[1-5]\b|dressing_decision|product_truth|brand_life_narrative|local_response|visual_styling_story",
        artifact.body,
        re.IGNORECASE,
    ):
        raise GenerationFailed("内容成品泄露内部产品标识")


def assert_p1_complete(artifact: GeneratedArtifact) -> None:
    """Compatibility entrypoint retained for the existing P1 callers."""
    assert_content_complete(artifact)
