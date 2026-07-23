from __future__ import annotations

from html import escape
from urllib.parse import urlencode


def render_workbench(mode: str, result: dict[str, object] | None, notice: str | None = None) -> str:
    artifact = ""
    if result:
        task_id = escape(str(result["task_id"]))
        version_id = escape(str(result["version_id"]))
        version = escape(str(result["version"]))
        artifact = f"""
        <section class=\"artifact\">
          <p class=\"version\">版本 V{version}</p>
          <h2>内容概要</h2><p>{escape(str(result["outline"]))}</p>
          <h2>完整文字成品</h2><article>{escape(str(result["body"]))}</article>
          <form method=\"post\" action=\"/ui/revise\">
            <input type=\"hidden\" name=\"task_id\" value=\"{task_id}\">
            <label>自然语言修改 <textarea name=\"instruction\" required maxlength=\"1000\" placeholder=\"例如：语气更轻一点，保留判断边界。\"></textarea></label>
            <button type=\"submit\">生成 V{int(str(result["version"])) + 1}</button>
          </form>
          <form method=\"post\" action=\"/ui/save\"><input type=\"hidden\" name=\"version_id\" value=\"{version_id}\"><input type=\"hidden\" name=\"task_id\" value=\"{task_id}\"><input type=\"hidden\" name=\"version\" value=\"{version}\"><button type=\"submit\">主动保存 V{version}</button></form>
          <form method=\"post\" action=\"/ui/reuse\"><input type=\"hidden\" name=\"reuse_saved_version_id\" value=\"{version_id}\"><label>以已保存 V{version} 为前情新建任务<textarea name=\"weak_seed\" required maxlength=\"1000\" placeholder=\"说明这次要怎样继续；未保存时系统会拒绝复用。\"></textarea></label><button type=\"submit\">明确复用并新建</button></form>
        </section>"""
    banner = (
        "离线确定性测试模式：此页结果不是实际模型调用。"
        if mode == "stub"
        else "已连接 DeepSeek 真实生成模式。"
    )
    message = f'<p class="notice">{escape(notice)}</p>' if notice else ""
    return f"""<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\"><title>笛语 · P1 内容工作台</title>
    <style>body{{max-width:780px;margin:36px auto;padding:0 18px;background:#faf9f7;color:#272421;font:16px/1.7 system-ui}}textarea{{width:100%;min-height:96px}}button{{margin:10px 0;padding:8px 14px}}article{{white-space:pre-wrap;background:#fff;padding:18px;border-radius:8px}}.mode,.notice{{padding:10px;background:#eee7df}}.version{{color:#765d4c}}</style>
    </head><body><h1>笛语 P1 内容工作台</h1><p class=\"mode\">{banner}</p>{message}
    <form method=\"post\" action=\"/ui/generate\"><label>把今天遇到的穿衣情境说出来<textarea name=\"weak_seed\" required maxlength=\"1000\" placeholder=\"例如：下午开完一个挺正式的会……\"></textarea></label><button type=\"submit\">生成完整 P1 成品</button></form>{artifact}</body></html>"""


def workbench_location(result: dict[str, object], notice: str | None = None) -> str:
    query = {"task": str(result["task_id"]), "version": str(result["version"])}
    if notice:
        query["notice"] = notice
    return "/?" + urlencode(query)
