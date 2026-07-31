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
      cache: RequestCache;
    }>;
    copiedTexts: string[];
    exportedBlobs: Blob[];
    deferNextVersionLoad: () => void;
    releaseDeferredVersionLoad: () => void;
    setPublicStatus: (
      contentState: "available" | "degraded" | "unavailable" | "unknown",
      coreState?: "available" | "unavailable"
    ) => void;
    setPublicStatusFailure: (value: boolean) => void;
    window: Window & typeof globalThis;
  };
}).__DIYU_INTERACTION__;
const {
  requests,
  copiedTexts,
  exportedBlobs,
  deferNextVersionLoad,
  releaseDeferredVersionLoad,
  setPublicStatus,
  setPublicStatusFailure,
  window
} = harness;
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

  const seriesTrigger = find(
    ".composer-resource-actions button",
    "连续系列"
  ) as HTMLButtonElement;
  await click(seriesTrigger);
  await settle();
  assert.equal(
    document.activeElement?.getAttribute("aria-label"),
    "关闭",
    "创作资料抽屉打开后焦点必须进入抽屉"
  );
  await act(async () => {
    document.querySelector(".creator-tool-drawer")?.dispatchEvent(
      new window.KeyboardEvent("keydown", {
        key: "Escape",
        bubbles: true,
        cancelable: true
      })
    );
  });
  await settle();
  assert.equal(
    document.activeElement,
    seriesTrigger,
    "Escape 关闭抽屉后焦点必须回到触发按钮"
  );
  await click(find(".composer-resource-actions button", "素材"));
  await settle();
  assert.match(
    document.querySelector(".creator-tool-drawer")?.textContent ?? "",
    /已关联 登记商品一（ZX-ONE）/
  );
  assert.match(
    document.querySelector(".creator-tool-drawer")?.textContent ?? "",
    /已关联 登记商品二（ZX-TWO）/
  );
  for (const productName of ["登记商品一", "登记商品二"]) {
    const choice = find(
      ".material-picker label",
      productName
    ).querySelector("input") as HTMLInputElement;
    await click(choice);
  }
  assert.match(
    find(".material-picker label", "登记商品一").textContent ?? "",
    /主视觉/,
    "第一份明确选择的登记商品素材必须显示为主视觉"
  );
  assert.match(
    find(".material-picker label", "登记商品二").textContent ?? "",
    /辅助视觉/,
    "第二份明确选择的登记商品素材必须显示为辅助视觉"
  );
  await click(
    document.querySelector(".creator-tool-drawer .tool-drawer-close") as HTMLButtonElement
  );
  await settle();

  const initialComposer = document.querySelector(
    'textarea[aria-label="内容需求"]'
  ) as HTMLTextAreaElement;
  await input(
    initialComposer,
    "今天店里忙了一天，回家因为洗碗拌了两句，帮我发条小红书。"
  );
  assert.equal(
    window.sessionStorage.getItem("diyu-content-draft"),
    "今天店里忙了一天，回家因为洗碗拌了两句，帮我发条小红书。",
    "未提交输入必须保存在当前浏览器会话"
  );
  await click(find(".composer-submit button", "生成内容"));
  await settle();
  const directRequest = requests
    .filter(item => item.path === "/api/v1/content/stream")
    .at(-1);
  assert.equal(directRequest?.body?.interaction_mode, "generate");
  assert.equal(directRequest?.body?.direct_generate, true);
  assert.deepEqual(
    directRequest?.body?.material_ids,
    [
      "44444444-4444-4444-8444-444444444441",
      "44444444-4444-4444-8444-444444444442"
    ],
    "两件商品素材必须由用户在本次任务明确选择"
  );
  assert.equal(
    directRequest?.body?.product_media_intent,
    true,
    "两件已关联组织商品素材必须显式选择 P5 路由，但不能自行授予资源"
  );
  assert.match(document.querySelector(".creator-artifact")?.textContent ?? "", /当前版本 · V1/);
  await click(find("button", "另起一条"));

  await send("你好");
  assert.match(document.body.textContent ?? "", /你好。今天想聊点什么/);
  assert.equal(document.querySelector(".creator-artifact"), null);
  assert.equal(
    requests.filter(
      item =>
        item.path === "/api/v1/content/stream" &&
        item.body?.message === "你好"
    ).length,
    1,
    "普通交流走正式语义入口但不产生伪成品"
  );
  assert.deepEqual(
    requests.find(
      item =>
        item.path === "/api/v1/content/stream" &&
        item.body?.message === "你好"
    )?.body
      ?.conversation,
    [],
    "当前消息只放在 message，不能在 conversation 中重复"
  );
  assert.equal(
    requests.find(
      item =>
        item.path === "/api/v1/content/stream" &&
        item.body?.message === "你好"
    )?.body
      ?.interaction_mode,
    "conversation",
    "发送必须明确走不持久化交流动作"
  );

  await send("最近店里总有人只想自己看看。");
  assert.match(document.body.textContent ?? "", /可以把它直接做成一篇完整内容/);
  assert.equal(document.querySelector(".creator-artifact"), null);
  assert.equal(document.querySelector(".generation-progress"), null);
  assert.ok(find(".direct-generation-offer button", "直接生成"));

  const directionToggle = find("button", "创作方向（可选）");
  assert.equal(directionToggle.getAttribute("aria-expanded"), "false");
  await click(directionToggle);
  await settle();
  assert.equal(
    document.activeElement?.getAttribute("aria-label"),
    "关闭创作方向",
    "移动创作方向打开后焦点必须进入底部抽屉"
  );
  assert.equal(
    document.querySelector(".direction-panel")?.getAttribute("aria-modal"),
    "true"
  );
  await act(async () => {
    document.querySelector(".direction-panel")?.dispatchEvent(
      new window.KeyboardEvent("keydown", {
        key: "Escape",
        bubbles: true,
        cancelable: true
      })
    );
  });
  await settle();
  assert.equal(
    document.activeElement,
    directionToggle,
    "Escape 关闭创作方向后焦点必须回到触发按钮"
  );
  await click(directionToggle);
  assert.equal(document.querySelectorAll(".direction-axis").length, 3);
  await click(find("button", "更多：讲法与系列互动"));
  assert.equal(document.querySelectorAll(".direction-axis").length, 5);
  const custom = document.querySelector(".custom-direction input") as HTMLInputElement;
  await input(custom, "想聊婆媳之间买衣服意见不一样，不要把任何一方写成反派。");

  deferNextVersionLoad();
  await click(find(".direct-generation-offer button", "直接生成"));
  await settle();
  const streamRequest = requests
    .filter(item => item.path === "/api/v1/content/stream")
    .at(-1);
  assert.equal(streamRequest?.body?.publishing_identity_id, "identity-hq");
  assert.equal(streamRequest?.body?.target, "xiaohongshu_graphic");
  assert.equal(
    streamRequest?.body?.direct_generate,
    true,
    "轻量动作只把原输入作为一次明确生成请求提交"
  );
  assert.equal(streamRequest?.body?.interaction_mode, "generate");
  const conversation = streamRequest?.body?.conversation as
    | Array<{ role: string; content: string }>
    | undefined;
  assert.equal(conversation?.at(-1)?.role, "assistant");
  assert.match(conversation?.at(-1)?.content ?? "", /直接做成一篇完整内容/);
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

  const revision = document.querySelector(
    'textarea[aria-label="修改要求"]'
  ) as HTMLTextAreaElement;
  await input(revision, "别讲道理，荒诞一点。");
  releaseDeferredVersionLoad();
  await settle();
  assert.equal(
    revision.value,
    "别讲道理，荒诞一点。",
    "V1 显示后立即输入的修改要求不能被异步版本加载清空"
  );
  await input(revision, "判断保留，改得更像门店人物自己的感受。");
  await click(find(".composer-submit button", "修改成 V2"));
  await settle();
  assert.match(document.querySelector(".creator-artifact")?.textContent ?? "", /当前版本 · V2/);

  const versionCountBeforeConversation = requests.filter(
    item => item.path === "/api/v1/tasks/t1/revisions"
  ).length;
  await input(
    document.querySelector(
      'textarea[aria-label="修改要求"]'
    ) as HTMLTextAreaElement,
    "这一版的主线是什么？"
  );
  await click(find(".composer-submit button", "发送"));
  await settle();
  assert.equal(
    requests.filter(item => item.path === "/api/v1/tasks/t1/revisions").length,
    versionCountBeforeConversation,
    "已有成品时发送也不得创建新版本"
  );
  assert.equal(
    requests.filter(item => item.path === "/api/v1/content/stream").at(-1)?.body
      ?.interaction_mode,
    "conversation"
  );

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
  await click(find(".composer-submit button", "修改成 V3"));
  await settle();
  assert.match(
    document.querySelector(".generation-failure")?.textContent ?? "",
    /要求和已有版本都已保留/
  );
  const failedRevisionCount = requests.filter(
    item => item.path === "/api/v1/tasks/t1/revisions"
  ).length;
  const failedRevisionRequest = requests
    .filter(item => item.path === "/api/v1/tasks/t1/revisions")
    .at(-1);
  await click(find(".generation-failure button", "再试一次"));
  await settle();
  assert.equal(
    requests.filter(item => item.path === "/api/v1/tasks/t1/revisions").length,
    failedRevisionCount + 1,
    "修改失败后的再试一次必须重放同一条修改请求"
  );
  assert.equal(
    requests.filter(item => item.path === "/api/v1/tasks/t1/revisions").at(-1)
      ?.body?.request_id,
    failedRevisionRequest?.body?.request_id,
    "失败重试必须复用同一个幂等请求 ID"
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

  await send("模拟限流失败，请保留我的输入。");
  assert.match(document.querySelector(".generation-failure")?.textContent ?? "", /输入和已有成品都已保留/);
  assert.match(
    document.querySelector(".generation-failure")?.textContent ?? "",
    /当前请求较多，请稍后再试/
  );
  assert.equal(document.querySelector(".creator-artifact"), null);
  assert.equal(
    document.querySelector(".composer-submit .primary"),
    null,
    "失败恢复卡片出现时不能同时保留另一个实心发送动作"
  );
  assert.equal(
    (document.querySelector('textarea[aria-label="内容需求"]') as HTMLTextAreaElement)
      .value,
    "模拟限流失败，请保留我的输入。"
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
  const failedStreamRequest = requests
    .filter(item => item.path === "/api/v1/content/stream")
    .at(-1);
  await click(find(".generation-failure button", "再试一次"));
  await settle();
  assert.equal(
    requests.filter(item => item.path === "/api/v1/content/stream").length,
    failedStreamCount + 1,
    "再试一次必须真实重放最近失败请求"
  );
  assert.equal(
    requests.filter(item => item.path === "/api/v1/content/stream").at(-1)
      ?.body?.request_id,
    failedStreamRequest?.body?.request_id,
    "生成失败重试必须复用同一个幂等请求 ID"
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

  window.history.pushState({}, "", "/status");
  setPublicStatus("unknown");
  root = createRoot(container);
  await act(async () => root.render(<Root />));
  await settle();
  assert.match(document.body.textContent ?? "", /内容生成近期状态尚无法确认/);
  assert.match(document.body.textContent ?? "", /纯文字陈列参考方案可以使用/);

  setPublicStatus("degraded");
  await click(find("button", "重新检查"));
  await settle();
  assert.match(document.body.textContent ?? "", /内容生成暂时受影响/);
  assert.match(document.body.textContent ?? "", /纯文字陈列参考方案仍可使用/);

  setPublicStatus("unavailable");
  await click(find("button", "重新检查"));
  await settle();
  assert.match(document.body.textContent ?? "", /内容生成暂时受影响/);

  setPublicStatus("available");
  await click(find("button", "重新检查"));
  await settle();
  assert.match(document.body.textContent ?? "", /主要功能可以使用/);

  setPublicStatus("unknown", "unavailable");
  await click(find("button", "重新检查"));
  await settle();
  assert.match(document.body.textContent ?? "", /笛语暂时无法接单/);
  setPublicStatusFailure(true);
  await click(find("button", "重新检查"));
  await settle();
  assert.match(document.body.textContent ?? "", /当前状态暂无法确认/);
  assert.doesNotMatch(document.body.textContent ?? "", /笛语暂时无法接单/);
  assert.doesNotMatch(document.body.textContent ?? "", /主要功能可以使用/);
  assert.doesNotMatch(document.body.textContent ?? "", /正在检查/);
  setPublicStatusFailure(false);
  setPublicStatus("available");
  await click(find("button", "重新检查"));
  await settle();
  assert.match(document.body.textContent ?? "", /主要功能可以使用/);
  assert.doesNotMatch(document.body.textContent ?? "", /当前状态暂无法确认/);
  assert.doesNotMatch(document.body.textContent ?? "", /笛语暂时无法接单/);
  assert.equal(
    requests.filter(item => item.path === "/api/v1/status").every(item => item.method === "GET"),
    true,
    "状态页只能读取状态投影，不得创建内容任务或外部探测"
  );
  assert.equal(
    requests.filter(item => item.path === "/api/v1/status").every(item => item.cache === "no-store"),
    true,
    "状态页重新检查不得读取旧缓存"
  );
  await act(async () => root.unmount());
}

await main();
