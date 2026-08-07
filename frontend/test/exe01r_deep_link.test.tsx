import assert from "node:assert/strict";
import { act } from "react";
import { createRoot } from "react-dom/client";

import Root from "../src/app/Root";

const harness = (
  globalThis as unknown as {
    __DIYU_EXE01R_DEEPLINK__: {
      window: Window & typeof globalThis;
      requests: Array<{ method: string; path: string }>;
      OPEN_TASK: string;
      FORBIDDEN_TASK: string;
    };
  }
).__DIYU_EXE01R_DEEPLINK__;
const { window, OPEN_TASK, FORBIDDEN_TASK } = harness;
const document = window.document;

let checks = 0;
const same = (actual: unknown, expected: unknown, message: string): void => {
  assert.equal(actual, expected, message);
  checks += 1;
};
const ensure = (value: unknown, message: string): void => {
  assert.ok(value, message);
  checks += 1;
};

async function settle(rounds = 6): Promise<void> {
  for (let round = 0; round < rounds; round += 1) {
    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 0));
    });
  }
}

const container = document.getElementById("root");
assert.ok(container);

async function visit(path: string): Promise<ReturnType<typeof createRoot>> {
  window.history.replaceState({}, "", path);
  const root = createRoot(container as HTMLElement);
  await act(async () => root.render(<Root />));
  await settle();
  return root;
}

const heading = (): string =>
  document.querySelector(".artifact-title h2")?.textContent ?? "";
const recovery = (): HTMLElement | null =>
  document.querySelector(".deep-link-recovery");

// 1. The link opens the task at the version it names — not the latest.
let root = await visit(`/content/tasks/${OPEN_TASK}?version=2`);
ensure(document.querySelector(".creator-artifact"), "深链没有打开成品");
same(heading(), "第二版标题", "深链没有打开地址里指定的版本");
same(recovery(), null, "正常深链不应出现恢复页");
await act(async () => root.unmount());

// Without ?version the highest one opens, which is what "the task" means.
root = await visit(`/content/tasks/${OPEN_TASK}`);
same(heading(), "第三版标题", "不带版本时应打开最高版本");
await act(async () => root.unmount());

// 2. A version that does not exist says so, and offers the way back.
root = await visit(`/content/tasks/${OPEN_TASK}?version=9`);
const missing = recovery();
ensure(missing, "版本不存在时没有恢复页");
ensure(
  (missing?.textContent ?? "").includes("没有第 9 版"),
  "恢复页没有说清楚缺的是哪一版"
);
ensure(
  Array.from(missing?.querySelectorAll("button") ?? []).some(node =>
    (node.textContent ?? "").includes("返回工作台")
  ),
  "恢复页没有返回工作台的出口"
);
same(
  document.querySelector(".creator-artifact"),
  null,
  "打不开的深链不应留下别的成品"
);

// The way out actually goes somewhere.
const back = Array.from(missing?.querySelectorAll("button") ?? []).find(node =>
  (node.textContent ?? "").includes("返回工作台")
);
await act(async () => {
  back?.dispatchEvent(new window.MouseEvent("click", { bubbles: true, cancelable: true }));
});
await settle();
same(new URL(window.location.href).pathname, "/content", "返回工作台没有离开死链");
await act(async () => root.unmount());

// 3. Someone else's task is refused as a permission problem, in plain words —
//    never dressed up as "this version does not exist".
root = await visit(`/content/tasks/${FORBIDDEN_TASK}`);
const denied = recovery();
ensure(denied, "无权限时没有恢复页");
const deniedText = denied?.textContent ?? "";
ensure(deniedText.includes("不属于当前发布账号"), "无权限没有说成权限问题");
ensure(!deniedText.includes("没有第"), "无权限被伪装成版本不存在");
same(
  document.querySelector(".creator-artifact"),
  null,
  "无权限的深链不应显示任何成品"
);

await settle();
await act(async () => root.unmount());
console.log(`EXE-01R deep link checks passed (${checks} assertions)`);
