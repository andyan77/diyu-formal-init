import assert from "node:assert/strict";
import { act } from "react";
import { createRoot } from "react-dom/client";

import Root from "../src/app/Root";

const harness = (
  globalThis as unknown as {
    __DIYU_EXE01R_SCOPE__: {
      window: Window & typeof globalThis;
      requests: Array<{ method: string; path: string; identity: string }>;
      releaseStream: () => void;
    };
  }
).__DIYU_EXE01R_SCOPE__;
const { window, requests, releaseStream } = harness;
const document = window.document;

const HQ = "identity-hq";
const STORE = "identity-store";
const DRAFT_HQ = "总部这条先放着，我还没想好结尾。";

let checks = 0;
const ensure = (value: unknown, message: string): void => {
  assert.ok(value, message);
  checks += 1;
};
const same = (actual: unknown, expected: unknown, message: string): void => {
  assert.equal(actual, expected, message);
  checks += 1;
};

async function settle(rounds = 5): Promise<void> {
  for (let round = 0; round < rounds; round += 1) {
    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 0));
    });
  }
}

async function type(value: string): Promise<void> {
  const node = document.querySelector("textarea") as HTMLTextAreaElement;
  assert.ok(node, "找不到创作输入框");
  await act(async () => {
    Object.getOwnPropertyDescriptor(
      window.HTMLTextAreaElement.prototype,
      "value"
    )?.set?.call(node, value);
    node.dispatchEvent(new window.Event("input", { bubbles: true }));
  });
  await settle();
}

async function chooseAccount(id: string): Promise<void> {
  const select = document.querySelector(
    'select[aria-label="发布账号"]'
  ) as HTMLSelectElement;
  assert.ok(select, "找不到发布账号选择器");
  await act(async () => {
    Object.getOwnPropertyDescriptor(
      window.HTMLSelectElement.prototype,
      "value"
    )?.set?.call(select, id);
    select.dispatchEvent(new window.Event("change", { bubbles: true }));
  });
  await settle();
}

const composerValue = (): string =>
  (document.querySelector("textarea") as HTMLTextAreaElement).value;
const urlIdentity = (): string | null =>
  new URL(window.location.href).searchParams.get("publishing_identity_id");

const container = document.getElementById("root");
assert.ok(container);
const root = createRoot(container);
await act(async () => root.render(<Root />));
await settle();

same(urlIdentity(), HQ, "初始账号应来自地址栏");

// Account A types, submits, and the reply is deliberately never delivered yet.
await type(DRAFT_HQ);
const submit = document.querySelector(".composer-submit button[type='submit']");
assert.ok(submit, "找不到提交按钮");
await act(async () => {
  submit.dispatchEvent(new window.MouseEvent("click", { bubbles: true, cancelable: true }));
});
await settle();
ensure(
  requests.some(item => item.path === "/api/v1/content/stream" && item.identity === HQ),
  "生成请求没有带上总部账号"
);

// Switch to B while A's generation is still open.
await chooseAccount(STORE);
same(urlIdentity(), STORE, "切换账号后地址栏没有跟上");
same(composerValue(), "", "切到新账号后不得显示上一个账号的草稿");
same(
  document.querySelectorAll(".message").length,
  0,
  "切到新账号后不得留下上一个账号的对话"
);

// Now let A's result arrive. It belongs to an account that is no longer here.
releaseStream();
await settle(8);

same(
  document.querySelector(".creator-artifact"),
  null,
  "上一个账号的成品落进了当前账号的工作区"
);
same(
  document.querySelectorAll(".message.assistant").length,
  0,
  "上一个账号的回复落进了当前账号的对话"
);
same(composerValue(), "", "上一个账号的回复改动了当前账号的输入框");
same(urlIdentity(), STORE, "迟到的回复不得改变当前账号");

// Back returns to A, with A's own draft.
await act(async () => {
  window.history.back();
});
await settle(8);

same(urlIdentity(), HQ, "后退没有回到上一个账号");
same(composerValue(), DRAFT_HQ, "回到原账号后草稿没有恢复");
same(
  document.querySelector(".creator-artifact"),
  null,
  "回到原账号不应凭空出现一份成品"
);

await settle();
await act(async () => root.unmount());
console.log(`EXE-01R scope transaction checks passed (${checks} assertions)`);
