// R1 · a reply for the account you left must not land in the account you moved
// to, and moving back must find your own draft where you left it.
//
// The stream for account A is held open on purpose. The switch happens while it
// is in flight, and A's result is only released afterwards — which is exactly
// the race that used to put one account's words under another's name.

import { installDom, runSuite } from "./dom-harness.mjs";
import {
  ACCOUNT_PROFILE,
  BOOTSTRAP,
  EXPRESSION_CATALOG,
  IDENTITY_HQ,
  IDENTITY_STORE,
  PREFERENCE,
  version
} from "./exe01r-fixtures.mjs";

const dom = installDom(
  `http://localhost/content?publishing_identity_id=${IDENTITY_HQ}&target=xiaohongshu_graphic`
);
dom.window.__DIYU_BOOTSTRAP__ = BOOTSTRAP;

let releaseStream = null;
const held = new Promise(resolve => {
  releaseStream = resolve;
});

/** A stream whose final chunk only arrives when the test says so. */
const heldStream = () => {
  const encoder = new TextEncoder();
  const opening = [{ event: "received" }, { event: "generating" }]
    .map(line => `${JSON.stringify(line)}\n`)
    .join("");
  const closing = `${JSON.stringify({
    event: "completed",
    result: version({ outline: "总部账号的成品", body: "只属于总部账号。" })
  })}\n`;
  let stage = 0;
  return {
    ok: true,
    status: 200,
    headers: { get: () => "application/x-ndjson" },
    body: {
      getReader: () => ({
        read: async () => {
          if (stage === 0) {
            stage = 1;
            return { done: false, value: encoder.encode(opening) };
          }
          if (stage === 1) {
            stage = 2;
            await held;
            return { done: false, value: encoder.encode(closing) };
          }
          return { done: true, value: undefined };
        },
        releaseLock: () => undefined
      })
    }
  };
};

const requests = [];
const recent = {
  [IDENTITY_HQ]: [],
  [IDENTITY_STORE]: []
};

globalThis.fetch = async (input, init = {}) => {
  const url = new URL(String(input), "http://localhost");
  // The workspace scopes GETs through the query string and the stream through
  // its JSON body, so both readings are recorded.
  const body = init.body ? JSON.parse(String(init.body)) : null;
  const identity =
    url.searchParams.get("publishing_identity_id") ??
    body?.publishing_identity_id ??
    "";
  requests.push({ method: init.method ?? "GET", path: url.pathname, identity });
  if (init.signal?.aborted) throw Object.assign(new Error("aborted"), { name: "AbortError" });
  if (url.pathname === "/api/v1/content/stream") return heldStream();
  const payload = {
    "/api/v1/content/expression-catalog": EXPRESSION_CATALOG,
    "/api/v1/user/creation-preferences": PREFERENCE,
    "/api/v1/materials": [],
    "/api/v1/content/account-expression-profile": ACCOUNT_PROFILE,
    "/api/v1/content/tasks": recent[identity] ?? []
  }[url.pathname];
  if (payload === undefined) {
    return { ok: false, status: 404, json: async () => ({ detail: url.pathname }) };
  }
  return { ok: true, status: 200, json: async () => payload };
};

globalThis.__DIYU_EXE01R_SCOPE__ = {
  window: dom.window,
  requests,
  releaseStream: () => releaseStream()
};

await runSuite(
  new URL("./exe01r_scope_transaction.test.tsx", import.meta.url),
  "exe01r-scope-transaction"
);
