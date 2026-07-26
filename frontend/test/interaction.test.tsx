import assert from "node:assert/strict";
import { act } from "react";
import { createRoot } from "react-dom/client";
import Root from "../src/main";

// The window, the recording fetch and the canned routes are installed by test/run.mjs before
// this bundle is imported; see the comment there for why the order matters.
const harness = (globalThis as unknown as {
  __DIYU_INTERACTION__: {
    requests: Array<{ method: string; path: string; body: unknown; preferenceSession: string | null }>;
    copiedTexts: string[];
    exportedBlobs: Blob[];
    window: Window & typeof globalThis;
  };
}).__DIYU_INTERACTION__;
const requests = harness.requests;
const copiedTexts = harness.copiedTexts;
const exportedBlobs = harness.exportedBlobs;
const window = harness.window;
const document = window.document;

function texts(selector: string): string[] {
  return Array.from(document.querySelectorAll(selector)).map(node => (node.textContent ?? "").trim());
}

function find(selector: string, contains: string): HTMLElement {
  const node = Array.from(document.querySelectorAll(selector)).find(item =>
    (item.textContent ?? "").includes(contains)
  );
  assert.ok(node, `找不到包含「${contains}」的 ${selector}`);
  return node as HTMLElement;
}

async function click(node: Element): Promise<void> {
  await act(async () => {
    node.dispatchEvent(new window.MouseEvent("click", { bubbles: true, cancelable: true }));
  });
}

async function settle(): Promise<void> {
  await act(async () => {
    await new Promise(resolve => setTimeout(resolve, 0));
  });
  await act(async () => {
    await new Promise(resolve => setTimeout(resolve, 0));
  });
}

async function main(): Promise<void> {
  const container = document.getElementById("root");
  assert.ok(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(<Root />);
  });
  await settle();

  // 1. Natural input is usable without opening anything; the panel stays collapsed.
  const composer = document.querySelector('textarea[aria-label="内容需求"]');
  assert.ok(composer, "自然输入区应当直接可用");
  const panel = document.querySelector("details.direction-panel") as HTMLDetailsElement;
  assert.equal(panel.open, false, "创作方向面板默认收起");

  // 2. A saved default is shown as a carried-over default, never as 不指定.
  const summary = (document.querySelector(".direction-summary")?.textContent ?? "").trim();
  assert.match(summary, /沿用你保存的默认/, `收起时应说明沿用默认，实际是「${summary}」`);
  assert.doesNotMatch(summary, /不指定/);
  await act(async () => {
    panel.open = true;
  });
  assert.ok(
    texts("button").some(label => label.includes("本次不用默认：干货攻略")),
    "每一轴都要能单独关掉这次的默认"
  );

  // 3. Switching an axis off is a third state: it is neither the default nor 不指定.
  await click(find("button", "本次不用默认：干货攻略"));
  const cleared = (document.querySelector(".direction-summary")?.textContent ?? "").trim();
  assert.match(cleared, /风格：本次不使用/, `关掉后应显示本次不使用，实际是「${cleared}」`);

  // 4. An original nobody wrote a note for cannot be selected, and the note entry is right there.
  const boxes = Array.from(document.querySelectorAll(".reference-picker input[type=checkbox]"));
  assert.equal(boxes.length, 2);
  assert.equal((boxes[0] as HTMLInputElement).disabled, false, "文字素材可以直接勾选");
  assert.equal((boxes[1] as HTMLInputElement).disabled, true, "缺人工说明的图片不可勾选");
  await click(find(".reference-picker button", "先补一句说明"));
  const noteInput = document.querySelector('.reference-note-form input') as HTMLInputElement;
  assert.ok(noteInput, "应当就地提供补写说明的入口");
  await act(async () => {
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")?.set;
    setter?.call(noteInput, "这张图里是那条裤子的口袋。");
    noteInput.dispatchEvent(new window.Event("input", { bubbles: true }));
  });
  const noteButton = find(".reference-note-form button", "保存这句说明") as HTMLButtonElement;
  await click(noteButton);
  await settle();
  assert.ok(
    requests.some(item => item.method === "PATCH" && item.path === "/api/v1/materials/asset-image/reference-note"),
    "补写说明应当写回这份原件"
  );

  // 5. This task's real request carries the switched-off axis, and only that.
  await act(async () => {
    const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value")?.set;
    setter?.call(composer, "帮我讲清这次要说什么。");
    composer.dispatchEvent(new window.Event("input", { bubbles: true }));
  });
  await click(find(".composer-foot button", "生成当前成品"));
  await settle();
  const created = requests.filter(item => item.method === "POST" && item.path === "/api/v1/content");
  assert.equal(created.length, 1);
  const direction = (created[0].body as { creative_direction: { cleared_axes: string[]; selections: Record<string, string> } }).creative_direction;
  assert.deepEqual(direction.cleared_axes, ["style"]);
  assert.deepEqual(direction.selections, {});
  const artifactText = document.querySelector(".artifact-text")?.textContent ?? "";
  assert.match(artifactText, /内容概要：受众会得到一个能直接使用的观察方法/);
  assert.match(artifactText, /完整台词\/解说：先看结构，再查性能/);
  for (const internal of ["账号观察", "受众获得", "账号关系", "演示商品锚点", "可见造型命题", "画面成立条件"]) {
    assert.doesNotMatch(artifactText, new RegExp(internal), `页面不得显示内部脚手架「${internal}」`);
  }
  await click(find(".artifact-actions button", "复制"));
  assert.equal(copiedTexts.length, 1);
  assert.match(copiedTexts[0], /AI 辅助生成/);
  assert.match(copiedTexts[0], /发布提醒：发布前请使用平台 AI 内容声明功能/);
  assert.match(copiedTexts[0], /内容概要：受众会得到一个能直接使用的观察方法/);
  await click(find(".artifact-actions button", "导出"));
  assert.equal(exportedBlobs.length, 1);
  const exported = await exportedBlobs[0].text();
  assert.equal(exported, copiedTexts[0], "复制和导出必须使用同一用户可见口径");
  for (const internal of ["账号观察", "受众获得", "账号关系", "演示商品锚点", "可见造型命题", "画面成立条件"]) {
    assert.doesNotMatch(exported, new RegExp(internal), `导出不得显示内部脚手架「${internal}」`);
  }

  // 6. A temporary preference-free session really stops reading the private preference.
  const beforeSession = requests.length;
  const bypass = find(".direction-foot label", "临时不读取").querySelector("input") as HTMLInputElement;
  await act(async () => {
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "checked")?.set;
    setter?.call(bypass, true);
    bypass.dispatchEvent(new window.Event("click", { bubbles: true }));
  });
  await settle();
  const afterSession = requests.slice(beforeSession);
  assert.ok(afterSession.length > 0, "进入临时会话应当重新读取当前面板");
  assert.ok(
    afterSession.every(item => item.preferenceSession === "bypass"),
    "临时会话期间每一次请求都要声明自己"
  );
  assert.ok(
    !afterSession.some(item => item.path === "/api/v1/user/creation-preferences"),
    "临时会话期间不再读取私人偏好"
  );
  assert.ok(
    !texts(".direction-foot button").some(label => label.includes("以后优先这样帮我")),
    "临时会话期间不提供写入偏好的按钮"
  );
  await act(async () => {
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "checked")?.set;
    setter?.call(bypass, false);
    bypass.dispatchEvent(new window.Event("click", { bubbles: true }));
  });
  await settle();

  // 7. A plan item only comes back to the natural input area; it creates nothing.
  await click(find(".sidebar nav button", "内容计划"));
  await settle();
  const beforePlan = requests.filter(item => item.method === "POST" && item.path === "/api/v1/content").length;
  await click(find(".plan-row button", "用这条开始"));
  await settle();
  const afterPlan = requests.filter(item => item.method === "POST" && item.path === "/api/v1/content").length;
  assert.equal(afterPlan, beforePlan, "点「用这条开始」之前不得创建任务");
  const returned = document.querySelector('textarea[aria-label="内容需求"]') as HTMLTextAreaElement;
  assert.match(returned.value, /先讲清楚我们从什么位置说话/);
  assert.match(returned.value, /只用已经确认的品牌立场。/);

  // 8. The identity drawer opens the existing profile card instead of a new settings page.
  await click(find(".identity-bar dd button", "去看这张画像"));
  await settle();
  assert.ok(
    texts(".page-heading h1").some(title => title.includes("这个账号从什么位置说话")),
    "身份抽屉应当能进入现有账号画像编辑卡"
  );

  await act(async () => {
    root.unmount();
  });
  process.stdout.write("frontend interaction checks passed\n");
}

main().catch(error => {
  process.stderr.write(`${String(error && (error as Error).stack ? (error as Error).stack : error)}\n`);
  process.exit(1);
});
