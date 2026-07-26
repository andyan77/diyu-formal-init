from __future__ import annotations

import re

_INTERNAL_HEADINGS = frozenset(
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
_VISIBLE_HEADINGS = (
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
    *_INTERNAL_HEADINGS,
)
_SECTION = re.compile(
    r"(?m)^(?P<heading>"
    + "|".join(re.escape(heading) for heading in _VISIBLE_HEADINGS)
    + r")："
)


def project_content_body(body: str) -> str:
    """Return the one user-facing projection used by UI, history, copy and export.

    Historical versions retain their immutable stored bodies. This projection removes only
    compiler-owned semantic-contract sections and keeps the complete production artifact.
    """

    matches = list(_SECTION.finditer(body))
    if not matches:
        return body.strip()
    projected: list[str] = []
    prefix = body[: matches[0].start()].strip()
    if prefix:
        projected.append(prefix)
    for index, match in enumerate(matches):
        heading = match.group("heading")
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        value = body[match.end() : end].strip()
        if heading in _INTERNAL_HEADINGS or not value:
            continue
        visible_heading = "内容概要" if heading == "自然导读" else heading
        projected.append(f"{visible_heading}：{value}")
    return "\n\n".join(projected).strip()
