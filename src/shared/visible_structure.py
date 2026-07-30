from __future__ import annotations

import unicodedata

# Compiler-owned heading names are shared. Their parsing rules are not: legacy
# projection recognizes only the historical full-width colon, while Writer
# anti-spoofing reserves both full-width and ASCII forms.
INTERNAL_VISIBLE_HEADINGS = frozenset(
    {
        "当前选择",
        "改变条件",
        "下一步",
        "商品新增理解",
        "限制",
        "成立边界",
        "账号观察",
        "受众获得",
        "账号关系",
        "近场信号",
        "账号回应",
        "公开关系回报",
        "真实商品锚点",
        "演示商品锚点",
        "可见造型命题",
        "画面成立条件",
    }
)

LEGACY_PROJECTED_HEADINGS = (
    "标题",
    "自然导读",
    "内容概要",
    "封面/首帧",
    "完整观看链",
    "完整台词/解说",
    "画面与动作",
    "字幕",
    "声音与制作提示",
    "自然时长",
    "首图方案",
    "图序与每张职责",
    "完整发布正文",
    "拍摄/排版提示",
    "发布配文与互动",
    "变换边界",
    *tuple(sorted(INTERNAL_VISIBLE_HEADINGS)),
)

PRODUCT_VISIBLE_HEADINGS = (
    *LEGACY_PROJECTED_HEADINGS,
    "表达范围",
    "内容看点",
    "封面/开头",
    "画面动作",
    "字幕策略",
    "首图",
    "完整正文",
    "发布配文",
    "正文",
    "封面文案",
    "制作提示",
    "发布配文",
    "配文",
)

SERVER_VISIBLE_SCOPE_PREFIXES = (
    "真实原话｜",
    "已确认品牌信息｜",
    "已确认商品信息｜",
    "一般观察（不对应未提供的真实经历）｜",
    "可信事实＋",
    "你提到：",
    "已确认的品牌信息：",
    "已确认的商品信息：",
    "下面是创作性的生活观察，不对应真实人物或经历：",
    "不妨试试：",
    "假设有这样一幕：",
    "以下是情景演绎，不对应真实人物或经历：",
)

# Unicode Default_Ignorable_Code_Point as defined by DerivedCoreProperties.
# The security view removes these code points only for reserved-label matching;
# Writer-visible text is never rewritten. Including the complete property closes
# format, variation-selector and combining-grapheme-joiner evasions without
# turning this module into a general Unicode confusables system.
_DEFAULT_IGNORABLE_RANGES = (
    (0x00AD, 0x00AD),
    (0x034F, 0x034F),
    (0x061C, 0x061C),
    (0x115F, 0x1160),
    (0x17B4, 0x17B5),
    (0x180B, 0x180F),
    (0x200B, 0x200F),
    (0x202A, 0x202E),
    (0x2060, 0x206F),
    (0x3164, 0x3164),
    (0xFE00, 0xFE0F),
    (0xFEFF, 0xFEFF),
    (0xFFA0, 0xFFA0),
    (0xFFF0, 0xFFF8),
    (0x1BCA0, 0x1BCA3),
    (0x1D173, 0x1D17A),
    (0xE0000, 0xE0FFF),
)
_BIDIRECTIONAL_CONTROL_CHARACTERS = frozenset(
    {
        "\u061c",  # Arabic letter mark
        "\u200e",  # left-to-right mark
        "\u200f",  # right-to-left mark
        "\u202a",  # left-to-right embedding
        "\u202b",  # right-to-left embedding
        "\u202c",  # pop directional formatting
        "\u202d",  # left-to-right override
        "\u202e",  # right-to-left override
        "\u2066",  # left-to-right isolate
        "\u2067",  # right-to-left isolate
        "\u2068",  # first strong isolate
        "\u2069",  # pop directional isolate
    }
)


def _is_default_ignorable(character: str) -> bool:
    codepoint = ord(character)
    return unicodedata.category(character) == "Cf" or any(
        start <= codepoint <= end for start, end in _DEFAULT_IGNORABLE_RANGES
    )


def _security_match_view(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return "".join(character for character in normalized if not _is_default_ignorable(character))


_NORMALIZED_SCOPE_PREFIXES = tuple(_security_match_view(prefix) for prefix in SERVER_VISIBLE_SCOPE_PREFIXES)
_NORMALIZED_HEADINGS = tuple(_security_match_view(heading) for heading in PRODUCT_VISIBLE_HEADINGS)


def assert_writer_visible_text_safe(text: str) -> None:
    """Reject structural impersonation without rewriting natural Writer text."""

    if any(character in _BIDIRECTIONAL_CONTROL_CHARACTERS for character in text):
        raise ValueError("writer visible text contains bidirectional control characters")
    for line in text.splitlines():
        candidate = _security_match_view(line).lstrip()
        if any(candidate.startswith(prefix) for prefix in _NORMALIZED_SCOPE_PREFIXES):
            raise ValueError("writer forged a server wrapper by impersonating a server-owned scope label")
        if any(candidate.startswith(f"{heading}:") for heading in _NORMALIZED_HEADINGS):
            raise ValueError("writer forged a compiler-owned visible section heading")
