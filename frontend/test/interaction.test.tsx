import assert from "node:assert/strict";
import { act } from "react";
import { createRoot } from "react-dom/client";
import Root from "../src/app/Root";

const harness = (globalThis as unknown as {
  __DIYU_INTERACTION__: {
    requests: Array<{ method: string; path: string; query: string; body: unknown }>;
    copiedTexts: string[];
    exportedBlobs: Blob[];
    setCopyFailure: (value: boolean) => void;
    window: Window & typeof globalThis;
  };
}).__DIYU_INTERACTION__;
const { requests, copiedTexts, exportedBlobs, setCopyFailure, window } = harness;
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

async function input(node: HTMLInputElement | HTMLTextAreaElement, value: string): Promise<void> {
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
  await act(async () => root.render(<Root />));
  await settle();

  assert.ok(
    !requests.some(item => item.path === "/api/v1/session/context"),
    "正式 /content 必须消费页面 bootstrap，不能用通用上下文覆盖可信目标"
  );
  assert.deepEqual(
    requests
      .filter(item => item.path === "/api/v1/content/tasks")
      .map(item => item.query),
    ["?target=xiaohongshu_graphic"],
    "历史只能读取服务端为当前页面解析的平台作用域"
  );
  assert.match(document.querySelector(".identity-trigger")?.textContent ?? "", /总部小红书发布账号/);
  assert.match(document.querySelector(".identity-trigger")?.textContent ?? "", /品牌官方/);
  const target = document.querySelector(".target-switch select") as HTMLSelectElement;
  assert.equal(target.value, "xiaohongshu_graphic");
  assert.equal(target.selectedOptions[0]?.textContent, "小红书图文");
  assert.equal(document.querySelector(".creator-artifact"), null, "空态不应常驻巨大成品面板");
  assert.equal(document.querySelectorAll(".mobile-work-tabs button").length, 0);
  for (const forbidden of ["Tenant", "ContentRole", "RLS", "schema", "GenerationRun"]) {
    assert.doesNotMatch(document.body.textContent ?? "", new RegExp(forbidden));
  }

  const directionToggle = find("button", "创作方向（可选）");
  assert.equal(directionToggle.getAttribute("aria-expanded"), "false");
  await click(directionToggle);
  assert.equal(document.querySelectorAll(".direction-axis").length, 3, "首屏只展开题材、风格、形式");
  assert.match(document.body.textContent ?? "", /没有合适的？直接说你想要的方向/);
  assert.doesNotMatch(document.body.textContent ?? "", /显高显瘦|小个子|微胖梨形|苹果型/);
  for (const nonStable of ["反精致", "上新直播", "到店核销", "CAT-SOURCE-GAP"]) {
    assert.doesNotMatch(document.body.textContent ?? "", new RegExp(nonStable));
  }
  await click(find("button", "更多：讲法与连续方式"));
  assert.equal(document.querySelectorAll(".direction-axis").length, 5);
  assert.equal(
    document.querySelectorAll(".direction-options button:not(.quiet-choice)").length,
    21,
    "默认目录必须完全来自服务端并恰好显示 21 项"
  );

  const custom = document.querySelector(".custom-direction input") as HTMLInputElement;
  const composer = document.querySelector(
    'textarea[aria-label="内容需求"]'
  ) as HTMLTextAreaElement;
  await input(custom, "上新直播");
  await input(composer, "请按这个方向整理一份完整内容。");
  await click(find(".composer-submit button", "生成内容"));
  await settle();
  assert.equal(document.querySelector(".creator-artifact"), null);
  assert.equal(custom.value, "上新直播");
  assert.equal(composer.value, "请按这个方向整理一份完整内容。");
  assert.match(
    document.querySelector(".conversation-notice")?.textContent ?? "",
    /暂不能稳定完成/
  );

  const humour = find(".direction-options button", "幽默玩梗");
  await click(humour);
  await input(custom, "保留判断，但像一位熟悉门店的人自然说。");
  const unreadable = Array.from(
    document.querySelectorAll(".material-options input")
  ).find(item => (item.parentElement?.textContent ?? "").includes("尚未说明的图片")) as
    | HTMLInputElement
    | undefined;
  assert.equal(unreadable?.disabled, true, "缺人工说明的图片不可勾选");
  const material = document.querySelector(".material-options input:not(:disabled)") as HTMLInputElement;
  await click(material);
  await click(find(".direction-footer button", "以后优先这样帮我"));
  await settle();
  const savedDefault = requests.find(
    item =>
      item.method === "PUT" &&
      item.path === "/api/v1/user/creation-preferences" &&
      Boolean(
        (item.body as { direction_defaults?: Record<string, string> } | null)
          ?.direction_defaults?.style
      )
  );
  assert.ok(savedDefault, "只有显式选择「以后优先这样帮我」才保存个人默认");
  await click(find(".direction-options button", "本次不使用"));
  assert.equal(
    find(".direction-options button", "本次不使用").getAttribute("aria-pressed"),
    "true"
  );
  await click(humour);

  await click(document.querySelector(".identity-trigger") as HTMLElement);
  await settle();
  assert.equal(
    (document.activeElement as HTMLElement | null)?.getAttribute("aria-label"),
    "关闭"
  );
  assert.match(document.querySelector(".account-drawer")?.textContent ?? "", /账号定位 · V2/);
  const bodyToggle = document.querySelector(".switch-line input") as HTMLInputElement;
  await click(bodyToggle);
  await settle();
  assert.ok(
    requests.some(item => item.method === "PUT" && item.path === "/api/v1/user/creation-preferences"),
    "体型方向只能由本人显式保存后开启"
  );
  assert.match(document.querySelector(".account-drawer")?.textContent ?? "", /系统不会自行推断/);
  await click(document.querySelector(".account-drawer .icon-button") as HTMLElement);
  await settle();
  assert.equal(document.activeElement, document.querySelector(".identity-trigger"));
  await click(document.querySelector(".identity-trigger") as HTMLElement);
  await settle();
  await act(async () => {
    document.querySelector(".account-drawer")?.dispatchEvent(
      new window.KeyboardEvent("keydown", { key: "Escape", bubbles: true })
    );
  });
  await settle();
  assert.equal(document.querySelector(".account-drawer"), null);
  assert.equal(document.activeElement, document.querySelector(".identity-trigger"));
  assert.equal(
    document.querySelectorAll(".direction-options button:not(.quiet-choice)").length,
    25,
    "本人主动启用后，服务端目录才增加 4 项体型方向"
  );

  await input(composer, "走进门店只想自己看看，这种沉默是不是也应该被尊重？");
  await click(find(".composer-submit button", "生成内容"));
  await settle();
  const created = requests.find(
    item =>
      item.method === "POST" &&
      item.path === "/api/v1/content" &&
      (item.body as { creative_direction?: { custom_text?: string } } | null)
        ?.creative_direction?.custom_text ===
        "保留判断，但像一位熟悉门店的人自然说。"
  );
  assert.ok(created);
  const createBody = created.body as {
    target: string;
    material_ids: string[];
    creative_direction: {
      selections: Record<string, string>;
      custom_text: string;
      body_related_opt_in: boolean;
    };
  };
  assert.equal(createBody.target, "xiaohongshu_graphic");
  assert.deepEqual(createBody.material_ids, ["11111111-1111-4111-8111-111111111111"]);
  assert.equal(
    createBody.creative_direction.custom_text,
    "保留判断，但像一位熟悉门店的人自然说。"
  );
  assert.equal(createBody.creative_direction.body_related_opt_in, true);
  assert.ok(Object.values(createBody.creative_direction.selections).length === 1);
  assert.match(document.querySelector(".creator-artifact")?.textContent ?? "", /当前版本 · V1/);
  assert.match(document.querySelector(".creator-artifact")?.textContent ?? "", /内容概要/);
  assert.match(document.querySelector(".creator-artifact")?.textContent ?? "", /完整台词/);
  assert.match(document.querySelector(".creator-artifact")?.textContent ?? "", /画面与动作/);
  assert.match(document.querySelector(".creator-artifact")?.textContent ?? "", /AI 辅助生成/);

  const revision = document.querySelector('textarea[aria-label="修改要求"]') as HTMLTextAreaElement;
  await input(revision, "判断保留，但不要像宣言，改成一人面对手机能自然说出的版本。");
  await click(find(".composer-submit button", "生成 V2"));
  await settle();
  assert.match(document.querySelector(".creator-artifact")?.textContent ?? "", /当前版本 · V2/);
  assert.match(
    document.querySelector(".translation-notice")?.textContent ?? "",
    /保留了.*轻松感，收成克制的冷幽默/
  );

  await click(find(".artifact-actions button", "复制"));
  await click(find(".artifact-actions button", "导出"));
  assert.equal(copiedTexts.length, 1);
  assert.equal(exportedBlobs.length, 1);
  assert.equal(await exportedBlobs[0].text(), copiedTexts[0]);
  assert.match(copiedTexts[0], /AI 辅助生成/);
  assert.match(copiedTexts[0], /发布提醒/);
  assert.match(copiedTexts[0], /完整台词/);
  assert.ok(
    copiedTexts[0].indexOf("保留了你想要的轻松感") <
      copiedTexts[0].indexOf("内容概要")
  );
  assert.ok(copiedTexts[0].indexOf("内容概要") < copiedTexts[0].indexOf("AI 辅助生成"));
  setCopyFailure(true);
  await click(find(".artifact-actions button", "复制"));
  await settle();
  assert.match(
    document.querySelector(".conversation-notice")?.textContent ?? "",
    /没有复制成功/
  );
  setCopyFailure(false);

  await click(document.querySelector(".version-history summary") as HTMLElement);
  assert.match(
    document.querySelector(".version-history summary")?.textContent ?? "",
    /历史版本（1）/
  );
  await click(find(".version-history button", "V1"));
  assert.match(document.querySelector(".history-reading")?.textContent ?? "", /当前版仍是 V2/);
  assert.match(document.querySelector(".creator-artifact")?.textContent ?? "", /历史版本 · V1/);
  await click(find(".history-reading button", "回到当前版"));
  assert.match(document.querySelector(".creator-artifact")?.textContent ?? "", /当前版本 · V2/);
  assert.equal(document.querySelectorAll(".mobile-work-tabs button").length, 2);

  assert.ok(
    !document.querySelector(".creator-app")?.textContent?.includes("概览与待处理"),
    "创作壳不得混入租户管理业务 DOM"
  );
  await click(find(".composer-submit button", "另起一条"));
  await click(find("button", "创作方向（可选）"));
  assert.equal(
    (document.querySelector(".custom-direction input") as HTMLInputElement).value,
    ""
  );
  assert.equal(document.querySelectorAll(".material-options input:checked").length, 0);
  assert.equal(
    document.querySelectorAll(".direction-options button[aria-pressed='true']").length,
    0,
    "上一次的本次选择不得带入新任务"
  );
  await act(async () => root.unmount());
  process.stdout.write("UI-03 creator interaction checks passed\n");
}

main().catch(error => {
  process.stderr.write(
    `${String(error && (error as Error).stack ? (error as Error).stack : error)}\n`
  );
  process.exit(1);
});
