import assert from "node:assert/strict";
import { act } from "react";
import { createRoot } from "react-dom/client";
import Root from "../src/main";

const harness = (globalThis as unknown as {
  __DIYU_ADMIN_INTERACTION__: {
    requests: Array<{ method: string; path: string; body: unknown }>;
    window: Window & typeof globalThis;
  };
}).__DIYU_ADMIN_INTERACTION__;
const requests = harness.requests;
const window = harness.window;
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

  await click(find(".sidebar nav button", "本轮商品资料"));
  await settle();
  const sku = document.querySelector('input[placeholder="商品稳定编号"]') as HTMLInputElement;
  assert.equal(sku.value, "DIYU-CSPU-001", "首份候选商品草案应自动预填");
  assert.match(document.body.textContent ?? "", /草案在你确认前不会参与生成/);
  await click(find("button", "确认并保存为当前商品事实"));
  await settle();
  const productRequest = requests.find(item =>
    item.method === "PUT" && item.path === "/api/v1/tenant-management/brand-products"
  );
  assert.ok(productRequest);
  assert.equal(
    (productRequest.body as { confirm_as_current_brand_fact: boolean }).confirm_as_current_brand_fact,
    true
  );

  await click(find(".sidebar nav button", "账号与操作人"));
  await settle();
  await click(find("summary", "表达画像"));
  await settle();
  const control = document.querySelector('select[aria-label="声明控制组织"]') as HTMLSelectElement;
  assert.equal(control.value, "org-hq", "推断的控制组织应只作为待确认预选值");
  assert.match(document.body.textContent ?? "", /依据现有候选资料预填/);
  assert.match(
    (document.querySelector('.profile-field textarea') as HTMLTextAreaElement).value,
    /总部岗位型表达身份/
  );

  const carrierName = document.querySelector(
    'input[placeholder="这个平台上的内部内容载体名称"]'
  ) as HTMLInputElement;
  assert.equal(carrierName.value, "笛语服饰品牌官方账号·小红书");
  await click(find("button", "确认并建立内部内容载体"));
  await settle();
  const carrierRequest = requests.find(item =>
    item.method === "POST" && item.path === "/api/v1/tenant-management/platform-carriers"
  );
  assert.ok(carrierRequest);
  assert.deepEqual(carrierRequest.body, {
    source_account_id: "account-hq",
    name: "笛语服饰品牌官方账号·小红书",
    channel: "小红书",
    operator_id: "operator-1",
    confirm_internal_carrier: true
  });
  await click(find("button", "生成一次性重置链接"));
  await settle();
  assert.ok(requests.some(item =>
    item.method === "POST"
    && item.path === "/api/v1/tenant-management/users/operator-1/reset"
  ));
  assert.match(document.body.textContent ?? "", /一次性激活或重置链接/);

  await act(async () => root.unmount());
  process.stdout.write("frontend admin prefill interaction checks passed\n");
}

main().catch(error => {
  process.stderr.write(`${String(error && (error as Error).stack ? (error as Error).stack : error)}\n`);
  process.exit(1);
});
