#!/usr/bin/env python3
"""Render every server-side HTML page to static files for visual regression.

`src/gateway/api/html.py` writes class names as plain strings — `entry-page`,
`entry-choice`, `eyebrow`, `primary` — that no component ever mentions. They are
exactly the styles a TSX-only grep would call dead, so the dead-style cleanup
has to be checked against these pages specifically. The renderers are pure
functions with no database or app dependency, which makes the check cheap and
deterministic.

Usage:
    python3 scripts/exe01/render_server_pages.py --out DIR --css PATH
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.gateway.api import html  # noqa: E402

# Representative arguments; the point is to exercise every class name these
# renderers emit, not to reproduce any particular runtime state.
PAGES: dict[str, object] = {
    "tenant_admin_access_denied": lambda: html.render_tenant_admin_access_denied(),
    "tenant_user_access_denied": lambda: html.render_tenant_user_access_denied(
        "租户用户入口", "/tenant-admin", "返回租户管理入口"
    ),
    "tenant_data_missing": lambda: html.render_tenant_data_missing(
        "内容创作入口",
        "这个账号还没有获得正式品牌资料。",
        "/tenant-admin",
        "前往租户管理端补充",
    ),
    "login_failure": lambda: html.render_login_failure(
        "租户用户登录", "/login", "用户名或密码不正确。"
    ),
    "activation_failure": lambda: html.render_activation_failure(
        "这个一次性链接已经使用过了。"
    ),
    "spa_shell_noscript": lambda: html.render_spa_shell(
        {"application": "tenant_user", "identity": {"tenant": "笛语服饰"}}
    ),
}


def localize(markup: str, css_href: str) -> str:
    """Point the stylesheet at a local build and drop the module script."""
    markup = markup.replace("/app/assets/index.css", css_href)
    return markup.replace(
        "<script type='module' src='/app/assets/index.js'></script>", ""
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--css", type=Path, required=True)
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    css_target = args.out / "styles.css"
    css_target.write_bytes(args.css.read_bytes())

    for name, render in PAGES.items():
        markup = localize(render(), "./styles.css")  # type: ignore[operator]
        # The noscript fallback is the only styled content in the SPA shell, so
        # unwrap it to make it visible to a headless browser.
        if name == "spa_shell_noscript":
            markup = markup.replace("<noscript>", "<div>").replace(
                "</noscript>", "</div>"
            )
        (args.out / f"{name}.html").write_text(markup, encoding="utf-8")
        print(f"rendered {name}.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
