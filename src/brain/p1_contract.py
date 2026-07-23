from __future__ import annotations

import re

from src.shared.errors import GenerationFailed
from src.shared.types import GeneratedArtifact


def assert_p1_complete(artifact: GeneratedArtifact) -> None:
    """Validate the small structured P1 contract, not a surface-word score."""
    if not artifact.body.strip():
        raise GenerationFailed("P1 成品为空")
    contract = artifact.semantic_contract
    if (
        not contract.choice.strip()
        or not contract.boundary.strip()
        or not contract.next_action.strip()
    ):
        raise GenerationFailed("P1 成品缺少选择、边界或下一步行动")
    if re.search(r"1[3-9]\d{9}|[\w.+-]+@[\w.-]+|订单号?\s*[:：]?\s*[A-Za-z0-9-]+", artifact.body):
        raise GenerationFailed("P1 成品包含个人标识")
