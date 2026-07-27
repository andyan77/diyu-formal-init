import assert from "node:assert/strict";
import { act } from "react";
import { createRoot } from "react-dom/client";
import Root from "../src/app/Root";

const harness = (globalThis as unknown as {
  __DIYU_ADMIN_INTERACTION__: {
    window: Window & typeof globalThis;
    setReducedMotion: (value: boolean) => void;
  };
}).__DIYU_ADMIN_INTERACTION__;
const { window, setReducedMotion } = harness;
const document = window.document;
const bootstrapWindow = window as unknown as {
  __DIYU_BOOTSTRAP__: Record<string, unknown> | null;
};

async function click(node: Element): Promise<void> {
  await act(async () => {
    node.dispatchEvent(new window.MouseEvent("click", { bubbles: true, cancelable: true }));
  });
}

async function settle(): Promise<void> {
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
      operator: "品牌管理员",
      organization: "笛语服饰管理组织",
      brand: "笛语服饰"
    }
  });
  assert.match(document.body.textContent ?? "", /概览与待处理/);
  assert.match(document.body.textContent ?? "", /成员与权限/);
  assert.match(document.body.textContent ?? "", /品牌与创作资料/);
  assert.doesNotMatch(document.body.textContent ?? "", /下一阶段|施工|验收/);
  assert.doesNotMatch(
    document.body.textContent ?? "",
    /已可使用|保持就绪|运行正常|笛语运维|需求反馈/
  );
  assert.equal(document.querySelector('a[href*="section=demo"]'), null);
  assert.equal(document.querySelector(".creator-app"), null);
  assert.equal(document.querySelector('textarea[aria-label="内容需求"]'), null);
  await unmount(root);

  root = await renderAt("/ops", {
    application: "ops",
    formal_runtime: true,
    runtime_summary: { enabled_tenants: 3, content_runs: 12 },
    pending_requests: 2
  });
  assert.match(document.body.textContent ?? "", /当前运行汇总/);
  assert.match(document.body.textContent ?? "", /启用租户/);
  assert.equal(document.querySelector(".creator-app"), null);
  assert.doesNotMatch(
    document.body.textContent ?? "",
    /成员与权限|发布账号|生成内容|已可使用|保持就绪|运行正常/
  );
  await unmount(root);

  process.stdout.write("UI-03 public, auth and isolated shell checks passed\n");
}

main().catch(error => {
  process.stderr.write(
    `${String(error && (error as Error).stack ? (error as Error).stack : error)}\n`
  );
  process.exit(1);
});
