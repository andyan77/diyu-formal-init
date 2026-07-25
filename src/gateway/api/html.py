from __future__ import annotations

import json
from html import escape
from urllib.parse import urlencode


def render_spa_shell(
    bootstrap: dict[str, object] | None = None,
    fallback_extra: str = "",
    fallback: str | None = None,
) -> str:
    """Serve one React entry without mirroring business state into server templates."""
    serialized = json.dumps(bootstrap, ensure_ascii=False).replace("<", "\\u003c")
    default_fallback = (
        "<h1>笛语</h1><p>请选择今天要完成的工作。</p>"
        "<p><a href='/ui/select/user'>租户用户入口</a> · "
        "<a href='/ui/select/admin'>租户管理入口</a></p>"
    )
    rendered_fallback = fallback if fallback is not None else default_fallback
    if bootstrap is not None:
        identity = bootstrap.get("identity")
        if isinstance(identity, dict):
            rendered_fallback += (
                "<p>"
                + " · ".join(
                    escape(str(value)) for value in identity.values() if isinstance(value, str)
                )
                + "</p>"
            )
    return (
        "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>笛语</title><link rel='stylesheet' href='/app/assets/index.css'></head><body>"
        "<div id='root'></div><noscript>" + rendered_fallback + fallback_extra + "</noscript>"
        "<script>window.__DIYU_BOOTSTRAP__=" + serialized + ";</script>"
        "<script type='module' src='/app/assets/index.js'></script></body></html>"
    )


def workbench_location(
    result: dict[str, object], notice: str | None = None, target: str | None = None
) -> str:
    query = {"task": str(result["task_id"]), "version": str(result["version"])}
    if target:
        query["target"] = target
    if notice:
        query["notice"] = notice
    return "/content?" + urlencode(query)
