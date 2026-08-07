import assert from "node:assert/strict";
import { act } from "react";
import { createRoot } from "react-dom/client";

import Root from "../src/app/Root";

const harness = (
  globalThis as unknown as {
    __DIYU_EXE01R_STREAM__: {
      window: Window & typeof globalThis;
      requests: Array<{ method: string; path: string; query: string }>;
    };
  }
).__DIYU_EXE01R_STREAM__;
const { window } = harness;
const document = window.document;

let checks = 0;
const ensure = (value: unknown, message: string): void => {
  assert.ok(value, message);
  checks += 1;
};

async function settle(): Promise<void> {
  for (let round = 0; round < 5; round += 1) {
    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 0));
    });
  }
}

async function click(node: Element): Promise<void> {
  await act(async () => {
    node.dispatchEvent(new window.MouseEvent("click", { bubbles: true, cancelable: true }));
  });
  await settle();
}

async function type(node: HTMLTextAreaElement, value: string): Promise<void> {
  await act(async () => {
    Object.getOwnPropertyDescriptor(
      window.HTMLTextAreaElement.prototype,
      "value"
    )?.set?.call(node, value);
    node.dispatchEvent(new window.Event("input", { bubbles: true }));
  });
  await settle();
}

function composer(): HTMLTextAreaElement {
  const node = document.querySelector("textarea");
  assert.ok(node, "找不到创作输入框");
  return node as HTMLTextAreaElement;
}

const container = document.getElementById("root");
assert.ok(container);
const root = createRoot(container);
await act(async () => root.render(<Root />));
await settle();

const TYPED = "最近店里总有人只想自己看看。";
await type(composer(), TYPED);
ensure(composer().value === TYPED, "输入没有写进创作框");

const submit = document.querySelector(".composer-submit button[type='submit']");
assert.ok(submit, "找不到提交按钮");
await click(submit);
await settle();

// The stream carried a complete, well-formed result — and then kept talking.
// Nothing it said may reach the workspace.
ensure(
  document.querySelector(".creator-artifact") === null,
  "违约流仍然把成品挂上了工作区"
);
ensure(
  document.querySelector(".version-history") === null,
  "违约流仍然写入了版本列表"
);
ensure(
  document.querySelectorAll(".message.assistant").length === 0,
  "违约流仍然追加了助手消息"
);
ensure(
  document.querySelector(".generation-progress") === null,
  "违约后暂态进度没有清掉"
);
ensure(composer().value === TYPED, "违约流清掉了用户输入");

const userMessages = Array.from(document.querySelectorAll(".message.user")).map(
  node => node.textContent ?? ""
);
ensure(
  userMessages.some(text => text.includes(TYPED)),
  "用户自己的消息不应被回滚"
);

const banner = document.querySelector(".generation-failure");
ensure(banner !== null, "没有出现失败横幅");
const bannerText = banner?.textContent ?? document.body.textContent ?? "";
ensure(bannerText.includes("输入仍然保留"), "没有显示安全错误文案");
ensure(!bannerText.includes("after_terminal"), "安全文案泄漏了内部违约代号");

// Let every in-flight promise land before teardown, so a late setState
// cannot fire into an unmounted tree and log a spurious act() warning.
await settle();
await act(async () => root.unmount());
console.log(`EXE-01R stream transaction checks passed (${checks} assertions)`);
