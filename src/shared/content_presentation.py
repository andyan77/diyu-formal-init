from __future__ import annotations

import re

from src.shared.visible_structure import (
    INTERNAL_VISIBLE_HEADINGS,
    LEGACY_PROJECTED_HEADINGS,
)

_SECTION = re.compile(
    r"(?m)^(?P<heading>" + "|".join(re.escape(heading) for heading in LEGACY_PROJECTED_HEADINGS) + r")[：:]"
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
        if heading in INTERNAL_VISIBLE_HEADINGS or not value:
            continue
        visible_heading = "内容概要" if heading == "自然导读" else heading
        projected.append(f"{visible_heading}：{value}")
    return "\n\n".join(projected).strip()
