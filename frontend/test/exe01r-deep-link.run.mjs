// R2 · /content/tasks/:taskId?version=N opens that task at that version.
//
// The id used to be a prop CreatorApp declared and never read, so the address
// resolved to an empty workspace. Three journeys: the link works, a version
// that does not exist ends somewhere you can leave, and a task belonging to
// another account says so instead of pretending it is missing.

import { installDom, runSuite } from "./dom-harness.mjs";
import {
  ACCOUNT_PROFILE,
  BOOTSTRAP,
  EXPRESSION_CATALOG,
  PREFERENCE,
  version
} from "./exe01r-fixtures.mjs";

const OPEN_TASK = "task-open";
const FORBIDDEN_TASK = "task-not-yours";

const VERSIONS = [
  version({ task_id: OPEN_TASK, version_id: "v1", version: 1, outline: "第一版标题", body: "第一版正文。" }),
  version({ task_id: OPEN_TASK, version_id: "v2", version: 2, outline: "第二版标题", body: "第二版正文。" }),
  version({ task_id: OPEN_TASK, version_id: "v3", version: 3, outline: "第三版标题", body: "第三版正文。" })
];

const dom = installDom("http://localhost/content/tasks/task-open?version=2");
dom.window.__DIYU_BOOTSTRAP__ = BOOTSTRAP;

const requests = [];
globalThis.fetch = async (input, init = {}) => {
  const url = new URL(String(input), "http://localhost");
  requests.push({ method: init.method ?? "GET", path: url.pathname });
  if (url.pathname === `/api/v1/content/tasks/${FORBIDDEN_TASK}/versions`) {
    return {
      ok: false,
      status: 403,
      json: async () => ({ detail: "当前账号没有获准打开这条内容" })
    };
  }
  if (url.pathname === `/api/v1/content/tasks/${OPEN_TASK}/versions`) {
    return { ok: true, status: 200, json: async () => VERSIONS };
  }
  const payload = {
    "/api/v1/content/expression-catalog": EXPRESSION_CATALOG,
    "/api/v1/user/creation-preferences": PREFERENCE,
    "/api/v1/materials": [],
    "/api/v1/content/account-expression-profile": ACCOUNT_PROFILE,
    "/api/v1/content/tasks": []
  }[url.pathname];
  if (payload === undefined) {
    return { ok: false, status: 404, json: async () => ({ detail: url.pathname }) };
  }
  return { ok: true, status: 200, json: async () => payload };
};

globalThis.__DIYU_EXE01R_DEEPLINK__ = {
  window: dom.window,
  requests,
  OPEN_TASK,
  FORBIDDEN_TASK
};

await runSuite(
  new URL("./exe01r_deep_link.test.tsx", import.meta.url),
  "exe01r-deep-link"
);
