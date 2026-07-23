from __future__ import annotations

import re

from src.shared.errors import GenerationFailed
from src.shared.types import (
    GeneratedArtifact,
    P1SemanticContract,
    P2SemanticContract,
    P3SemanticContract,
    P4SemanticContract,
    P5SemanticContract,
)


def assert_content_complete(artifact: GeneratedArtifact) -> None:
    """Validate one product contract plus the executable video text pack."""
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
    if not isinstance(contract, expected) or any(not str(value).strip() for value in vars(contract).values()):
        raise GenerationFailed("内容成品缺少当前主要产品的必要部分")
    if any(
        not section.strip()
        for section in (
            artifact.production.natural_guide,
            artifact.production.spoken_lines,
            artifact.production.visual_actions,
            artifact.production.subtitles,
            artifact.production.sound_and_production,
        )
    ):
        raise GenerationFailed("内容成品缺少可执行的媒体制作部分")
    if not all(
        heading in artifact.body
        for heading in ("标题", "自然导读", "完整台词/解说", "画面与动作", "字幕", "声音与制作提示")
    ):
        raise GenerationFailed("内容成品正文没有完整可见文字包")
    if not all(value in artifact.body for value in vars(contract).values()):
        raise GenerationFailed("内容成品没有忠实呈现当前主要产品的必要部分")
    if re.search(r"1[3-9]\d{9}|[\w.+-]+@[\w.-]+|订单号?\s*[:：]?\s*[A-Za-z0-9-]+", artifact.body):
        raise GenerationFailed("内容成品包含个人标识")
    if re.search(r"\bP[1-5]\b|dressing_decision|product_truth|brand_life_narrative|local_response|visual_styling_story", artifact.body, re.IGNORECASE):
        raise GenerationFailed("内容成品泄露内部产品标识")


def assert_p1_complete(artifact: GeneratedArtifact) -> None:
    """Compatibility entrypoint retained for the existing P1 callers."""
    assert_content_complete(artifact)
