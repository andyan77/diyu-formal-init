import assert from "node:assert/strict";
import { act } from "react";
import { createRoot } from "react-dom/client";
import Root from "../src/app/Root";

const harness = (globalThis as unknown as {
  __DIYU_ADMIN_INTERACTION__: {
    window: Window & typeof globalThis;
    requests: Array<{ path: string; method: string; body: Record<string, unknown> | null }>;
    setReducedMotion: (value: boolean) => void;
    setFailedPath: (value: string | null) => void;
  };
}).__DIYU_ADMIN_INTERACTION__;
const { window, requests, setReducedMotion, setFailedPath } = harness;
const document = window.document;
const bootstrapWindow = window as unknown as {
  __DIYU_BOOTSTRAP__: Record<string, unknown> | null;
};

async function click(node: Element): Promise<void> {
  await act(async () => {
    node.dispatchEvent(new window.MouseEvent("click", { bubbles: true, cancelable: true }));
  });
}

function find(selector: string, text: string): HTMLElement {
  const value = Array.from(document.querySelectorAll(selector)).find(item =>
    (item.textContent ?? "").includes(text)
  );
  assert.ok(value, `找不到 ${selector} 中的「${text}」`);
  return value as HTMLElement;
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

async function select(node: HTMLSelectElement, value: string): Promise<void> {
  await act(async () => {
    Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, "value")
      ?.set?.call(node, value);
    node.dispatchEvent(new window.Event("change", { bubbles: true }));
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

async function renderAt(
  path: string,
  bootstrap: Record<string, unknown> | null
): Promise<ReturnType<typeof createRoot>> {
  window.history.replaceState({}, "", path);
  bootstrapWindow.__DIYU_BOOTSTRAP__ = bootstrap;
  const container = document.getElementById("root");
  assert.ok(container);
  const root = createRoot(container);
  await act(async () => root.render(<Root />));
  await settle();
  return root;
}

async function unmount(root: ReturnType<typeof createRoot>): Promise<void> {
  await act(async () => root.unmount());
}

async function main(): Promise<void> {
  setReducedMotion(false);
  let root = await renderAt("/", { application: "public" });
  assert.equal(
    document.querySelector(".motion-final img")?.getAttribute("src"),
    "/assets/diyu-logo-primary.svg",
    "A 动效必须交接正式 VI SVG"
  );
  assert.ok(document.querySelector(".seed-path.uncertain"));
  assert.ok(document.querySelector(".direction-turn"));
  assert.equal(document.querySelectorAll(".direction-turn").length, 1, "朱砂只承担一次方向转折");
  assert.equal(document.querySelectorAll(".motion-skip").length, 1);
  await click(document.querySelector(".motion-skip") as HTMLElement);
  assert.ok(document.querySelector(".public-home")?.classList.contains("motion-finished"));
  assert.equal(document.querySelector('a.button.primary')?.getAttribute("href"), "/login");
  assert.ok(document.querySelector('a[href="/tenant-admin/login"]'));
  assert.ok(document.querySelector('a[href="/ops/login"]'));
  await click(
    Array.from(document.querySelectorAll("button")).find(item =>
      item.textContent?.includes("重播动效")
    ) as HTMLElement
  );
  assert.equal(
    document.querySelector(".public-home")?.classList.contains("motion-finished"),
    false,
    "重播必须先恢复动效态"
  );
  await unmount(root);

  setReducedMotion(true);
  root = await renderAt("/", { application: "public" });
  assert.ok(document.querySelector(".public-home")?.classList.contains("motion-finished"));
  assert.equal(document.querySelector(".motion-skip"), null, "减少动效时直接进入正式 Logo 与首页");
  await unmount(root);

  root = await renderAt("/login", {
    application: "login",
    entry: "tenant-user"
  });
  assert.equal(document.querySelector("form")?.getAttribute("action"), "/login");
  assert.match(document.body.textContent ?? "", /内容创作/);
  assert.doesNotMatch(document.body.textContent ?? "", /品牌管理|笛语运维/);
  await unmount(root);

  root = await renderAt("/tenant-admin/login", {
    application: "login",
    entry: "tenant-admin"
  });
  assert.equal(
    document.querySelector("form")?.getAttribute("action"),
    "/tenant-admin/login"
  );
  assert.match(document.body.textContent ?? "", /品牌管理/);
  assert.equal(document.querySelector('input[name="totp_code"]'), null);
  await unmount(root);

  root = await renderAt("/ops/login", {
    application: "login",
    entry: "ops"
  });
  assert.equal(document.querySelector("form")?.getAttribute("action"), "/ops/login");
  assert.ok(document.querySelector('input[name="totp_code"]'));
  assert.doesNotMatch(document.body.textContent ?? "", /内容创作|品牌管理/);
  await unmount(root);

  root = await renderAt("/tenant-admin", {
    application: "tenant_management",
    formal_runtime: true,
    identity: {
      operator_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
      operator: "品牌管理员",
      organization: "笛语服饰管理组织",
      brand: "笛语服饰"
    }
  });
  assert.match(document.body.textContent ?? "", /概览与待处理/);
  assert.match(document.body.textContent ?? "", /成员与权限/);
  assert.match(document.body.textContent ?? "", /品牌管理/);
  assert.match(document.body.textContent ?? "", /先处理眼前需要补的资料/);
  assert.doesNotMatch(document.body.textContent ?? "", /下一阶段|施工|验收/);
  assert.doesNotMatch(
    document.body.textContent ?? "",
    /已可使用|保持就绪|运行正常|笛语运维|需求反馈/
  );
  assert.equal(document.querySelector('a[href*="section=demo"]'), null);
  assert.equal(document.querySelector(".creator-app"), null);
  assert.equal(document.querySelector('textarea[aria-label="内容需求"]'), null);
  assert.match(document.body.textContent ?? "", /补齐首个创作身份/);

  await click(find(".tenant-nav button", "成员与权限"));
  await settle();
  await click(find("button", "添加成员"));
  const memberInputs = Array.from(
    document.querySelectorAll(".tenant-drawer input")
  ) as HTMLInputElement[];
  await input(memberInputs[0], "门店内容成员");
  await input(memberInputs[1], "ui04-demo-member");
  await select(
    document.querySelector(".tenant-drawer select") as HTMLSelectElement,
    "11111111-1111-4111-8111-111111111111"
  );
  await click(find(".tenant-drawer button", "创建并生成体验链接"));
  await settle();
  assert.match(document.querySelector(".one-time-link")?.textContent ?? "", /一次性体验链接/);
  assert.match(
    document.querySelector(".one-time-link code")?.textContent ?? "",
    /ui04-obviously-fake-browser-fixture/
  );
  await click(find(".tenant-drawer button", "关闭"));
  assert.match(document.body.textContent ?? "", /尚未分配工作资格/);
  assert.doesNotMatch(document.body.textContent ?? "", /内容工作成员/);

  await click(find(".tenant-nav button", "发布账号"));
  await settle();
  await click(find("button", "创建发布账号"));
  const accountInputs = Array.from(
    document.querySelectorAll(".tenant-drawer input")
  ) as HTMLInputElement[];
  const accountTextareas = Array.from(
    document.querySelectorAll(".tenant-drawer textarea")
  ) as HTMLTextAreaElement[];
  const accountSelects = Array.from(
    document.querySelectorAll(".tenant-drawer select")
  ) as HTMLSelectElement[];
  await input(accountInputs[0], "门店人物发布账号");
  await input(accountInputs[1], "门店人物");
  await input(accountTextareas[0], "只表达本人可确认的门店观察。");
  await select(accountSelects[1], "22222222-2222-4222-8222-222222222222");
  await click(find(".tenant-drawer button", "创建发布账号"));
  await settle();
  assert.match(document.querySelector(".account-list")?.textContent ?? "", /门店人物发布账号/);
  assert.match(document.querySelector(".account-list")?.textContent ?? "", /门店人物/);

  await click(find(".tenant-nav button", "品牌、商品与组织素材"));
  await settle();
  await click(find("button", "添加商品"));
  const productInputs = Array.from(
    document.querySelectorAll(".tenant-drawer input")
  ) as HTMLInputElement[];
  const productTextareas = Array.from(
    document.querySelectorAll(".tenant-drawer textarea")
  ) as HTMLTextAreaElement[];
  await input(productInputs[0], "UI04-DEMO-A");
  await input(productInputs[1], "演示牛角扣外套");
  await input(productTextareas[2], "等深模拟商品资料，仅用于本次产品验收。");
  await input(productTextareas[3], "UI-04 合成演示范围");
  await click(find(".tenant-drawer button", "保存商品资料"));
  await settle();
  assert.match(document.querySelector(".product-list")?.textContent ?? "", /演示牛角扣外套/);

  await click(find(".tenant-nav button", "生产就绪与缺口"));
  await settle();
  assert.match(document.body.textContent ?? "", /当前没有需要处理的资料/);
  const memberCreate = requests.find(
    item => item.path === "/api/v1/tenant-management/users" && item.method === "POST"
  );
  const accountCreate = requests.find(
    item =>
      item.path === "/api/v1/tenant-management/publishing-accounts" &&
      item.method === "POST"
  );
  const productCreate = requests.find(
    item =>
      item.path === "/api/v1/tenant-management/brand-products" &&
      item.method === "PUT"
  );
  assert.equal(memberCreate?.body?.display_name, "门店内容成员");
  assert.equal(accountCreate?.body?.content_role_name, "门店人物");
  assert.equal(productCreate?.body?.confirm_as_current_brand_fact, true);
  assert.doesNotMatch(document.body.textContent ?? "", /ui04-obviously-fake-browser-fixture/);
  await unmount(root);

  root = await renderAt("/user", {
    application: "tenant_user",
    capabilities: ["content"],
    identity: { operator: "总部运营", account: "总部发布账号" }
  });
  assert.ok(document.querySelector('a[href="/content"]'));
  assert.equal(document.querySelector('a[href="/display"]'), null);
  assert.equal(document.querySelector(".tenant-admin-app"), null);
  await unmount(root);

  root = await renderAt("/user", {
    application: "tenant_user",
    capabilities: ["content", "display"],
    identity: { operator: "门店伙伴", account: "门店人物账号" }
  });
  assert.ok(document.querySelector('a[href="/content"]'));
  assert.ok(document.querySelector('a[href="/display"]'));
  await unmount(root);

  root = await renderAt("/display", {
    application: "display",
    identity: {
      operator: "门店伙伴",
      account: "门店人物账号",
      content_role: "门店人物"
    }
  });
  assert.ok(document.querySelector(".display-app"));
  assert.equal(document.querySelector(".creator-app"), null);
  assert.equal(document.querySelector(".tenant-admin-app"), null);
  await unmount(root);

  root = await renderAt("/ops", {
    application: "ops",
    formal_runtime: true,
    runtime_summary: { enabled_tenants: 3, content_runs: 12 },
    pending_requests: 2
  });
  assert.match(document.body.textContent ?? "", /今天需要处理什么/);
  assert.ok(document.querySelector('dl[aria-label="当前运行汇总"]'));
  assert.match(document.body.textContent ?? "", /启用租户/);
  assert.equal(document.querySelector(".creator-app"), null);
  assert.doesNotMatch(
    document.body.textContent ?? "",
    /成员与权限|发布账号|生成内容|已可使用|保持就绪|运行正常/
  );
  assert.match(document.body.textContent ?? "", /希望以后可以更容易整理门店当天的选题/);
  await click(find("button", "处理反馈"));
  const opsSelects = Array.from(
    document.querySelectorAll(".ops-feedback-form select")
  ) as HTMLSelectElement[];
  await select(opsSelects[0], "generation_method");
  await select(opsSelects[1], "answered");
  await input(
    document.querySelector(".ops-feedback-form textarea") as HTMLTextAreaElement,
    "这条需求已登记为后续方向，当前不会自动改变你的创作资料。"
  );
  await click(find(".ops-feedback-form button", "保存处理结果"));
  await settle();
  const feedbackReply = requests.find(
    item =>
      item.path ===
        "/api/v1/ops/unmet-capability-requests/UI04-UNMET-FIXTURE" &&
      item.method === "POST"
  );
  assert.equal(feedbackReply?.body?.status, "answered");
  assert.match(document.body.textContent ?? "", /已回告/);
  assert.equal(
    Array.from(document.querySelectorAll(".ops-metric"))
      .find(item => item.textContent?.includes("待处理反馈"))
      ?.querySelector("dd")?.textContent,
    "0",
    "已成功读取空集合后，不得回退显示旧的 bootstrap 待办数"
  );
  assert.doesNotMatch(
    document.body.textContent ?? "",
    /编辑目录|私人素材|自动激活/
  );
  await unmount(root);

  setFailedPath("/api/v1/admin/readiness");
  root = await renderAt("/tenant-admin", {
    application: "tenant_management",
    formal_runtime: true,
    identity: {
      operator_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
      operator: "品牌管理员",
      organization: "笛语服饰管理组织",
      brand: "笛语服饰"
    }
  });
  assert.match(document.body.textContent ?? "", /当前资料暂时无法读取/);
  assert.doesNotMatch(document.body.textContent ?? "", /当前没有需要处理的资料/);
  setFailedPath(null);
  await click(find("button", "重新读取"));
  await settle();
  assert.doesNotMatch(document.body.textContent ?? "", /当前资料暂时无法读取/);
  await unmount(root);

  setFailedPath("/api/v1/tenant-management/organizations");
  root = await renderAt("/tenant-admin", {
    application: "tenant_management",
    formal_runtime: true,
    identity: {
      operator_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
      operator: "品牌管理员",
      organization: "笛语服饰管理组织",
      brand: "笛语服饰"
    }
  });
  await click(find(".tenant-nav button", "成员与权限"));
  await settle();
  assert.match(document.body.textContent ?? "", /当前资料暂时无法读取/);
  assert.equal((find("button", "添加成员") as HTMLButtonElement).disabled, true);
  setFailedPath(null);
  await click(find("button", "重新读取"));
  await settle();
  assert.equal((find("button", "添加成员") as HTMLButtonElement).disabled, false);
  await unmount(root);

  root = await renderAt("/status", {
    application: "status",
    service_state: "available"
  });
  assert.match(document.body.textContent ?? "", /服务状态/);
  assert.match(document.body.textContent ?? "", /服务可以使用/);
  assert.doesNotMatch(document.body.textContent ?? "", /租户|数据库|供应商|SLA/);
  await unmount(root);

  process.stdout.write("UI-04 public, auth and isolated product space checks passed\n");
}

main().catch(error => {
  process.stderr.write(
    `${String(error && (error as Error).stack ? (error as Error).stack : error)}\n`
  );
  process.exit(1);
});
