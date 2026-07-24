_NON_AI_CONTENT_MODELS = frozenset({"deterministic-content-test-stub"})
_AIGC_LABEL = "AI 辅助生成"
_AIGC_RELEASE_REMINDER = "发布到当前平台前，请使用平台提供的 AI 内容声明功能；以发布页当前规则为准。"

AIGC_DISCLOSURE_RULE: dict[str, str] = {
    "name": "人工智能生成合成内容标识办法",
    "source": "https://www.cac.gov.cn/2025-03/14/c_1743654684782215.htm",
    "applies_to": "笛语交付的模型生成文字成品；DM01 确定性陈列方案不适用。",
    "verified_on": "2026-07-23",
    "effective_on": "2025-09-01",
}


def is_ai_generated_content(model: object) -> bool:
    """Classify a persisted content run without trusting a client-provided source flag."""
    return isinstance(model, str) and bool(model.strip()) and model not in _NON_AI_CONTENT_MODELS


def aigc_disclosure(model: object) -> tuple[str | None, str | None]:
    """Return user-facing disclosure text from the persisted generation source only."""
    if not is_ai_generated_content(model):
        return None, None
    return _AIGC_LABEL, _AIGC_RELEASE_REMINDER
