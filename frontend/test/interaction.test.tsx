import assert from "node:assert/strict";
import { act } from "react";
import { createRoot } from "react-dom/client";
import Root from "../src/app/Root";

// Cross-milestone UI contracts retained by this formal interaction journey:
// 空态不应常驻巨大成品面板；首屏只展开题材、风格、形式；
// 默认目录必须完全来自服务端；体型方向只能由本人显式保存后开启；
// 创作壳不得混入租户管理业务 DOM。
const harness = (globalThis as unknown as {
  __DIYU_INTERACTION__: {
    requests: Array<{
      method: string;
      path: string;
      query: string;
      body: Record<string, unknown> | null;
    }>;
    copiedTexts: string[];
    exportedBlobs: Blob[];
    window: Window & typeof globalThis;
  };
}).__DIYU_INTERACTION__;
const { requests, copiedTexts, exportedBlobs, window } = harness;
const document = window.document;

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

async function input(
  node: HTMLInputElement | HTMLTextAreaElement,
  value: string
): Promise<void> {
  await act(async () => {
    const prototype =
      node instanceof window.HTMLTextAreaElement
        ? window.HTMLTextAreaElement.prototype
        : window.HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(prototype, "value")?.set?.call(node, value);
    node.dispatchEvent(new window.Event("input", { bubbles: true }));
  });
}

async function settle(): Promise<void> {
  for (let index = 0; index < 5; index += 1) {
    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 0));
    });
  }
}

async function send(value: string): Promise<void> {
  const composer = document.querySelector(
    'textarea[aria-label="内容需求"]'
  ) as HTMLTextAreaElement;
  await input(composer, value);
  await click(find(".composer-submit button", "发送"));
  await settle();
}

async function main(): Promise<void> {
  const container = document.getElementById("root");
  assert.ok(container);
  let root = createRoot(container);
  await act(async () => root.render(<Root />));
  await settle();

  const identitySelect = document.querySelector(
    'select[aria-label="发布账号"]'
  ) as HTMLSelectElement;
  assert.equal(identitySelect.value, "identity-hq");
  assert.deepEqual(
    Array.from(identitySelect.options).map(option => option.textContent),
    ["总部品牌内容运营", "柯桥门店人物"],
    "一个用户可以显式选择多个获准逻辑发布账号"
  );
  assert.equal(
    (document.querySelector('select[aria-label="平台"]') as HTMLSelectElement).value,
    "小红书"
  );
  assert.deepEqual(
    Array.from(
      (document.querySelector('select[aria-label="内容形式"]') as HTMLSelectElement)
        .options
    ).map(option => option.textContent),
    ["图文", "视频"],
    "同一逻辑账号内选择平台和形式，不切换账号画像"
  );
  assert.match(document.querySelector(".identity-trigger")?.textContent ?? "", /品牌官方/);
  assert.match(
    document.querySelector(".identity-trigger")?.textContent ?? "",
    /品牌整体选择和长期表达/
  );
  const expectedScope =
    "?publishing_identity_id=identity-hq&target=xiaohongshu_graphic";
  assert.ok(
    requests.some(
      item => item.path === "/api/v1/content/tasks" && item.query === expectedScope
    ),
    "历史读取必须携带服务端已解析的逻辑账号与目标"
  );

  await send("你好");
  assert.match(document.body.textContent ?? "", /你好。今天想聊点什么/);
  assert.equal(document.querySelector(".creator-artifact"), null);
  assert.equal(
    requests.filter(item => item.path === "/api/v1/content/stream").length,
    1,
    "普通交流走正式语义入口但不产生伪成品"
  );
  assert.deepEqual(
    requests.find(item => item.path === "/api/v1/content/stream")?.body
      ?.conversation,
    [],
    "当前消息只放在 message，不能在 conversation 中重复"
  );

  await send("最近店里总有人只想自己看看。");
  assert.doesNotMatch(document.body.textContent ?? "", /沉默也应该被尊重|什么时候适合主动介绍/);
  assert.equal(document.querySelector(".creator-artifact"), null);

  const directionToggle = find("button", "创作方向（可选）");
  assert.equal(directionToggle.getAttribute("aria-expanded"), "false");
  await click(directionToggle);
  assert.equal(document.querySelectorAll(".direction-axis").length, 3);
  await click(find("button", "更多：讲法与系列互动"));
  assert.equal(document.querySelectorAll(".direction-axis").length, 5);
  const custom = document.querySelector(".custom-direction input") as HTMLInputElement;
  await input(custom, "想聊婆媳之间买衣服意见不一样，不要把任何一方写成反派。");

  await send("最近店里总有人只想自己看看，帮我写条小红书。");
  const streamRequest = requests
    .filter(item => item.path === "/api/v1/content/stream")
    .at(-1);
  assert.equal(streamRequest?.body?.publishing_identity_id, "identity-hq");
  assert.equal(streamRequest?.body?.target, "xiaohongshu_graphic");
  const conversation = streamRequest?.body?.conversation as
    | Array<{ role: string; content: string }>
    | undefined;
  assert.equal(conversation?.at(-1)?.role, "assistant");
  assert.doesNotMatch(
    conversation?.at(-1)?.content ?? "",
    /沉默也应该被尊重|什么时候适合主动介绍/,
    "旧二选一追问不得恢复"
  );
  assert.match(
    String(
      (
        streamRequest?.body?.creative_direction as
          | { custom_text?: string }
          | undefined
      )?.custom_text
    ),
    /婆媳.*不要把任何一方写成反派/,
    "开放人物关系和边界必须原样进入本次 brief"
  );
  assert.match(document.querySelector(".creator-artifact")?.textContent ?? "", /当前版本 · V1/);
  assert.match(document.querySelector(".creator-artifact")?.textContent ?? "", /完整台词/);
  assert.match(
    document.body.textContent ?? "",
    /我先从想自己看一会儿这件小事写一版/,
    "系统自主选择方向时只显示一句自然承接并立即交付成品"
  );

  const revision = document.querySelector(
    'textarea[aria-label="修改要求"]'
  ) as HTMLTextAreaElement;
  await input(revision, "判断保留，改得更像门店人物自己的感受。");
  await click(find(".composer-submit button", "生成 V2"));
  await settle();
  assert.match(document.querySelector(".creator-artifact")?.textContent ?? "", /当前版本 · V2/);
  await click(find(".version-history summary", "历史版本"));
  await click(find(".version-history button", "V1"));
  assert.match(document.querySelector(".history-reading")?.textContent ?? "", /回读 V1/);
  await click(find(".history-reading button", "回到当前版"));

  await click(find(".artifact-actions button", "复制"));
  await click(find(".artifact-actions button", "导出"));
  assert.equal(copiedTexts.length, 1);
  assert.equal(exportedBlobs.length, 1);
  assert.equal(await exportedBlobs[0].text(), copiedTexts[0]);

  await input(
    document.querySelector(
      'textarea[aria-label="修改要求"]'
    ) as HTMLTextAreaElement,
    "模拟修改失败，但请保留这条要求。"
  );
  await click(find(".composer-submit button", "生成 V3"));
  await settle();
  assert.match(
    document.querySelector(".generation-failure")?.textContent ?? "",
    /想法仍然保留/
  );
  const failedRevisionCount = requests.filter(
    item => item.path === "/api/v1/tasks/t1/revisions"
  ).length;
  await click(find(".generation-failure button", "再试一次"));
  await settle();
  assert.equal(
    requests.filter(item => item.path === "/api/v1/tasks/t1/revisions").length,
    failedRevisionCount + 1,
    "修改失败后的再试一次必须重放同一条修改请求"
  );
  assert.match(
    document.querySelector(".creator-artifact")?.textContent ?? "",
    /当前版本 · V3/
  );

  await click(find("button", "另起一条"));
  await send("请改成抖音视频。");
  assert.match(document.querySelector(".target-conflict")?.textContent ?? "", /页面当前选的是小红书图文/);
  assert.equal(
    document.querySelector(".composer-submit .primary"),
    null,
    "平台冲突需要先解决，不能同时保留另一个实心发送动作"
  );
  await click(find(".target-conflict button", "继续使用小红书图文"));
  await settle();
  assert.ok(
    requests.some(
      item =>
        item.path === "/api/v1/content/stream" &&
        item.body?.target_conflict_resolution === "keep_selected"
    ),
    "页面明确选择优先，冲突必须由用户透明决定"
  );

  await click(find("button", "另起一条"));
  await send("模拟失败，请保留我的输入。");
  assert.match(document.querySelector(".generation-failure")?.textContent ?? "", /想法仍然保留/);
  assert.equal(document.querySelector(".creator-artifact"), null);
  assert.equal(
    document.querySelector(".composer-submit .primary"),
    null,
    "失败恢复卡片出现时不能同时保留另一个实心发送动作"
  );
  assert.equal(
    (document.querySelector('textarea[aria-label="内容需求"]') as HTMLTextAreaElement)
      .value,
    "模拟失败，请保留我的输入。"
  );
  for (const forbidden of [
    "内容边界无法在一次单元修复内满足",
    "模型 JSON",
    "Prompt",
    "RLS",
    "422"
  ]) {
    assert.doesNotMatch(document.body.textContent ?? "", new RegExp(forbidden));
  }
  const failedStreamCount = requests.filter(
    item => item.path === "/api/v1/content/stream"
  ).length;
  await click(find(".generation-failure button", "再试一次"));
  await settle();
  assert.equal(
    requests.filter(item => item.path === "/api/v1/content/stream").length,
    failedStreamCount + 1,
    "再试一次必须真实重放最近失败请求"
  );

  await act(async () => root.unmount());

  const bootstrapWindow = window as unknown as {
    __DIYU_BOOTSTRAP__: {
      current_publishing_identity_id?: string | null;
    };
  };
  bootstrapWindow.__DIYU_BOOTSTRAP__.current_publishing_identity_id = null;
  const requestCount = requests.length;
  root = createRoot(container);
  await act(async () => root.render(<Root />));
  await settle();
  assert.equal(
    (document.querySelector('select[aria-label="发布账号"]') as HTMLSelectElement)
      .value,
    "",
    "多账号且服务端没有解析当前账号时，客户端不得默认第一项"
  );
  assert.equal(
    requests.length,
    requestCount,
    "未显式选择发布账号时不得读取任何账号作用域资料"
  );
  const unresolvedComposer = document.querySelector(
    'textarea[aria-label="内容需求"]'
  ) as HTMLTextAreaElement;
  await input(unresolvedComposer, "请直接生成。");
  await click(find(".composer-submit button", "发送"));
  assert.match(document.querySelector(".conversation-notice")?.textContent ?? "", /先选择一个发布账号/);
  assert.equal(requests.length, requestCount);
  await act(async () => root.unmount());
}

await main();
