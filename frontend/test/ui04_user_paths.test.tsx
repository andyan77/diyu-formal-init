import assert from "node:assert/strict";
import { act, useState } from "react";
import type { JSX } from "react";
import { createRoot } from "react-dom/client";
import DisplayApp from "../src/app/DisplayApp";
import { MaterialsPanel } from "../src/app/MaterialsPanel";
import { SeriesPanel } from "../src/app/SeriesPanel";
import type { SeriesSelection } from "../src/app/SeriesPanel";

const harness = (globalThis as unknown as {
  __DIYU_UI04_USER_PATHS__: {
    window: Window & typeof globalThis;
    requests: Array<{ method: string; path: string; body: unknown }>;
    copiedTexts: string[];
    setDisplayQuestion: (value: boolean) => void;
  };
}).__DIYU_UI04_USER_PATHS__;
const { window, requests, copiedTexts, setDisplayQuestion } = harness;
const document = window.document;

function find(selector: string, text: string): HTMLElement {
  const value = Array.from(document.querySelectorAll(selector)).find(item => (item.textContent ?? "").includes(text));
  assert.ok(value, `找不到 ${selector} 中的「${text}」`);
  return value as HTMLElement;
}

async function settle(): Promise<void> {
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 0)); });
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 0)); });
}

async function click(node: Element): Promise<void> {
  await act(async () => {
    node.dispatchEvent(new window.MouseEvent("click", { bubbles: true, cancelable: true }));
  });
}

async function input(node: HTMLInputElement | HTMLTextAreaElement, value: string): Promise<void> {
  await act(async () => {
    const prototype = node instanceof window.HTMLTextAreaElement ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(prototype, "value")?.set?.call(node, value);
    node.dispatchEvent(new window.Event("input", { bubbles: true }));
  });
}

async function render(view: React.ReactNode): Promise<ReturnType<typeof createRoot>> {
  const container = document.getElementById("root");
  assert.ok(container);
  const root = createRoot(container);
  await act(async () => root.render(view));
  await settle();
  return root;
}

function SeriesHarness(): JSX.Element {
  const [selected, setSelected] = useState<SeriesSelection | null>(null);
  const [continued, setContinued] = useState<SeriesSelection | null>(null);
  const [opened, setOpened] = useState("");
  return <><SeriesPanel selected={selected} onSelect={setSelected} onContinue={setContinued} onOpenTask={setOpened} target="douyin_video" /><output data-selected={JSON.stringify(selected)} data-continued={JSON.stringify(continued)} data-opened={opened} /></>;
}

function MaterialsHarness(): JSX.Element {
  const [selected, setSelected] = useState<string[]>([]);
  return <><MaterialsPanel selectedIds={selected} onSelectedIdsChange={setSelected} /><output data-selected={JSON.stringify(selected)} /></>;
}

async function displayJourney(): Promise<void> {
  const displayContext = {
    application: "display" as const,
    identity: { account: "柯桥门店账号", content_role: "门店陈列" }
  };
  const root = await render(<DisplayApp context={displayContext} />);
  assert.ok(document.querySelector(".display-app"));
  const inventory = document.querySelector("#display-inventory") as HTMLTextAreaElement;
  await input(inventory, "今天这组墙可用：SKU-A 3 件、SKU-B 2 件。");
  await click(find("button", "生成参考方案"));
  await settle();
  assert.match(document.body.textContent ?? "", /当前版本 · V1/);
  assert.match(document.body.textContent ?? "", /左侧.*上杆.*下杆/);
  assert.doesNotMatch(document.body.textContent ?? "", /AIGC|AI|示意|预览|确认|授权|审批|批准|是否采用|责任/);
  const feedback = document.querySelector("#display-feedback") as HTMLTextAreaElement;
  await input(feedback, "中间上杆的衬衫少一件，其余保持不动。");
  await click(find("button", "生成 V2"));
  await settle();
  assert.match(document.body.textContent ?? "", /当前版本 · V2/);
  await click(find("button", "阅读 V1"));
  assert.match(document.body.textContent ?? "", /历史版本 · V1/);
  await click(find("button", "复制"));
  assert.equal(copiedTexts.at(-1)?.includes("左侧（主焦点）"), true);
  assert.ok(requests.some(item => item.method === "POST" && item.path === "/api/v1/display" && Object.keys(item.body as object).join(",") === "inventory_text"));
  assert.ok(requests.some(item => item.method === "POST" && item.path === "/api/v1/display-tasks/d1/revisions" && Object.keys(item.body as object).join(",") === "feedback"));
  await act(async () => root.unmount());

  setDisplayQuestion(true);
  const questionRoot = await render(<DisplayApp context={displayContext} />);
  const questionInventory = document.querySelector("#display-inventory") as HTMLTextAreaElement;
  await input(questionInventory, "今天这组墙可用：SKU-A 3 件。");
  await click(find("button", "生成参考方案"));
  await settle();
  assert.match(document.body.textContent ?? "", /请补充这组墙的上下挂杆条件/);
  assert.equal(document.querySelector(".display-artifact-heading"), null, "追问不能生成半版本");
  await act(async () => questionRoot.unmount());
  setDisplayQuestion(false);
}

async function seriesJourney(): Promise<void> {
  const root = await render(<SeriesHarness />);
  await input(document.querySelector("#series-title") as HTMLInputElement, "新的连续观察");
  await click(find("button", "建立系列"));
  await settle();
  const output = document.querySelector("output") as HTMLOutputElement;
  assert.equal(JSON.parse(output.dataset.selected ?? "null").seriesId, "s2");
  const existing = Array.from(document.querySelectorAll(".series-entry")).find(item =>
    (item.textContent ?? "").includes("门店里的安静时刻")
  ) as HTMLElement;
  assert.ok(existing);
  await click(find(".series-item-open", "第 1 篇"));
  assert.equal(output.dataset.opened, "t1");
  await click(Array.from(existing.querySelectorAll("button")).find(item => item.textContent?.includes("接着做下一篇")) as HTMLElement);
  assert.equal(JSON.parse(output.dataset.continued ?? "null").seriesId, "s1");
  const position = existing.querySelector("input[type='number']") as HTMLInputElement;
  await input(position, "5");
  assert.equal(JSON.parse(output.dataset.selected ?? "null").position, 5);
  await click(Array.from(existing.querySelectorAll("li button")).find(item => item.textContent?.includes("下移")) as HTMLElement);
  await settle();
  const writes = requests.filter(item => item.path.startsWith("/api/v1/content/series") && item.method !== "GET");
  assert.ok(writes.some(item => item.method === "PUT" && item.path === "/api/v1/content/series/s1/items"));
  assert.ok(!writes.some(item => item.path.endsWith("/items") && item.method === "POST"), "系列写入只来自生成事务，不在面板里另加任务");
  await act(async () => root.unmount());
}

async function materialsJourney(): Promise<void> {
  const root = await render(<MaterialsHarness />);
  const checks = Array.from(document.querySelectorAll(".material-picker input")) as HTMLInputElement[];
  assert.equal(checks[1]?.disabled, true, "无人工说明的图片不能进入本次参考");
  await click(find("button", "补说明"));
  assert.equal(document.querySelector(".material-upload-form"), null, "补说明时只保留一个实心主动作");
  assert.equal(document.querySelectorAll(".materials-panel button.primary").length, 1);
  const note = document.querySelector(".material-note-form textarea") as HTMLTextAreaElement;
  await input(note, "这张图只拍到这件衣服的口袋位置。");
  await click(find(".material-note-form button", "保存说明"));
  await settle();
  const refreshed = Array.from(document.querySelectorAll(".material-picker input")) as HTMLInputElement[];
  assert.equal(refreshed[1]?.disabled, false);
  await click(refreshed[1]);
  const output = document.querySelector("output") as HTMLOutputElement;
  assert.deepEqual(JSON.parse(output.dataset.selected ?? "[]"), ["m2"]);
  const patch = requests.find(item => item.method === "PATCH" && item.path === "/api/v1/materials/m2/reference-note");
  assert.deepEqual(patch?.body, { reference_note: "这张图只拍到这件衣服的口袋位置。" });
  for (const request of requests.filter(item => item.path.startsWith("/api/v1/materials"))) {
    assert.doesNotMatch(JSON.stringify(request.body ?? {}), /tenant_id|brand_id|organization_id|account_id/);
  }
  await act(async () => root.unmount());
}

async function main(): Promise<void> {
  await displayJourney();
  await seriesJourney();
  await materialsJourney();
  process.stdout.write("UI-04 user-path interaction checks passed\n");
}

main().catch(error => {
  process.stderr.write(`${String(error instanceof Error ? error.stack : error)}\n`);
  process.exit(1);
});
