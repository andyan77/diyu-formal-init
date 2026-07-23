from __future__ import annotations

from html import escape
from urllib.parse import urlencode


def render_home() -> str:
    return _page(
        "笛语",
        "<h1>笛语</h1><p>请选择今天要完成的工作。</p>"
        "<section class='choices'><a class='choice' href='/ui/select/content'><strong>内容生产（对外）</strong>"
        "<span>为品牌受众生成可直接制作的内容。</span></a>"
        "<a class='choice' href='/ui/select/display'><strong>陈列搭配（对内）</strong>"
        "<span>为门店生成墙面双层挂杆执行建议。</span></a></section>",
    )


def render_workbench(
    mode: str, identity: dict[str, str], result: dict[str, object] | None, notice: str | None = None
) -> str:
    artifact = ""
    if result:
        task_id = escape(str(result["task_id"]))
        version_id = escape(str(result["version_id"]))
        version = escape(str(result["version"]))
        artifact = f"""
        <section class="artifact"><p class="version">版本 V{version}</p>
          <h2>内容概要</h2><p>{escape(str(result["outline"]))}</p>
          <h2>完整文字成品</h2><article>{escape(str(result["body"]))}</article>
          <form method="post" action="/ui/revise"><input type="hidden" name="task_id" value="{task_id}">
            <label>自然语言修改 <textarea name="instruction" required maxlength="1000"></textarea></label><button>生成 V{int(str(result["version"])) + 1}</button></form>
          <form method="post" action="/ui/save"><input type="hidden" name="version_id" value="{version_id}"><input type="hidden" name="task_id" value="{task_id}"><input type="hidden" name="version" value="{version}"><button>主动保存 V{version}</button></form>
          <form method="post" action="/ui/reuse"><input type="hidden" name="reuse_version_id" value="{version_id}"><label>以当前 V{version} 为前情新建任务<textarea name="weak_seed" required maxlength="1000"></textarea></label><button>明确复用并新建</button></form>
        </section>"""
    banner = "离线确定性测试模式：此页结果不是实际模型调用。" if mode == "stub" else "已连接 DeepSeek 真实生成模式。"
    identity_text = _identity(("品牌", identity["brand"]), ("实际操作人", identity["operator"]), ("代表组织", identity["organization"]), ("发布账号", identity["account"]), ("内容角色", identity["content_role"]))
    content = f"<a href='/'>返回应用首页</a><h1>内容生产（对外）</h1>{identity_text}<p class='mode'>{banner}</p>{_notice(notice)}<form method='post' action='/ui/generate'><label>把今天遇到的穿衣情境说出来<textarea name='weak_seed' required maxlength='1000'></textarea></label><button>生成完整 P1 成品</button></form>{artifact}"
    return _page("笛语 · 内容生产", content)


def workbench_location(result: dict[str, object], notice: str | None = None) -> str:
    query = {"task": str(result["task_id"]), "version": str(result["version"])}
    if notice:
        query["notice"] = notice
    return "/content?" + urlencode(query)


def render_display_workbench(
    identity: dict[str, str], result: dict[str, object] | None = None, notice: str | None = None
) -> str:
    artifact = ""
    if result:
        artifact = f"<h2>墙面方案 V{escape(str(result['version']))}</h2><article>{escape(str(result['body']))}</article><form method='post' action='/ui/display/revise'><input type='hidden' name='task_id' value='{escape(str(result['task_id']))}'><textarea name='feedback' required></textarea><button>按自然反馈生成 V{int(str(result['version'])) + 1}</button></form>"
    identity_text = _identity(("品牌", identity["brand"]), ("实际操作人", identity["operator"]), ("执行组织", identity["organization"]), ("当前门店", identity["store"]), ("当前能力", "墙面双层挂杆执行方案"))
    content = f"<a href='/'>返回应用首页</a><h1>陈列搭配（对内）</h1>{identity_text}<p>DM01 确定性陈列编译：只从已验证的库存、品牌标准和挂杆档案生成方案。</p>{_notice(notice)}<form method='post' action='/ui/display/generate'><textarea name='inventory_text' required placeholder='今天这组墙可用：ZX-C218 3 件……'></textarea><button>生成墙面方案</button></form>{artifact}"
    return _page("陈列搭配（对内）", content)


def _identity(*items: tuple[str, str]) -> str:
    return "<section class='identity'><h2>当前身份</h2>" + "".join(
        f"<p><strong>{escape(label)}：</strong>{escape(value)}</p>" for label, value in items
    ) + "</section>"


def _notice(value: str | None) -> str:
    return f"<p class='notice'>{escape(value)}</p>" if value else ""


def _page(title: str, content: str) -> str:
    return f"<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><title>{escape(title)}</title><style>body{{max-width:780px;margin:36px auto;padding:0 18px;background:#F8F7F3;color:#171614;font:16px/1.7 system-ui}}textarea{{width:100%;min-height:96px}}button,.choice{{margin:10px 0;padding:9px 14px}}article,.identity{{white-space:pre-wrap;background:#fff;padding:18px;border-radius:8px}}.identity p{{margin:3px 0}}.mode,.notice{{padding:10px;background:#eee7df}}.version{{color:#B7462E}}.choices{{display:grid;gap:14px}}.choice{{display:grid;background:#fff;color:#171614;text-decoration:none;border-left:4px solid #B7462E}}.choice span{{font-size:.9em}}</style></head><body><img src='/assets/diyu-logo-horizontal.svg' alt='笛语' width='150'>{content}</body></html>"
