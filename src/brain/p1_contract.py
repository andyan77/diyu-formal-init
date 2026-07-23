from __future__ import annotations

import re

from src.shared.errors import GenerationFailed
from src.shared.types import GeneratedArtifact


def assert_p1_complete(artifact: GeneratedArtifact) -> None:
    """Validate the executable P1 deliverable without a word-count or style score."""
    if not artifact.body.strip():
        raise GenerationFailed("P1 成品为空")
    contract = artifact.semantic_contract
    if (
        not contract.choice.strip()
        or not contract.boundary.strip()
        or not contract.next_action.strip()
    ):
        raise GenerationFailed("P1 成品缺少选择、边界或下一步行动")
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
        raise GenerationFailed("P1 成品缺少可执行的媒体制作部分")
    if not all(
        value in artifact.body
        for value in (contract.choice, contract.boundary, contract.next_action)
    ):
        raise GenerationFailed("P1 成品正文没有忠实呈现选择、边界和下一步")
    if re.search(r"1[3-9]\d{9}|[\w.+-]+@[\w.-]+|订单号?\s*[:：]?\s*[A-Za-z0-9-]+", artifact.body):
        raise GenerationFailed("P1 成品包含个人标识")
