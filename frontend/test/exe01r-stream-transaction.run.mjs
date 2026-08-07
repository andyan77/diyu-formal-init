// R3 · a stream that breaks its own contract must commit nothing.
//
// The unit tests in contract_stream.test.ts prove the guard refuses. This one
// proves the refusal is transactional at the workspace: after an after-terminal
// violation the artifact, the version list and the assistant transcript are all
// exactly as they were, and the composer still holds what the person typed.

import { installDom, runSuite } from "./dom-harness.mjs";
import {
  ACCOUNT_PROFILE,
  BOOTSTRAP,
  EXPRESSION_CATALOG,
  PREFERENCE,
  version
} from "./exe01r-fixtures.mjs";

const dom = installDom("http://localhost/content?target=xiaohongshu_graphic");
dom.window.__DIYU_BOOTSTRAP__ = BOOTSTRAP;

const ndjson = lines => ({
  ok: true,
  status: 200,
  headers: { get: () => "application/x-ndjson" },
  body: {
    getReader() {
      const encoder = new TextEncoder();
      const chunks = lines.map(line => `${JSON.stringify(line)}\n`);
      let index = 0;
      return {
        read: async () =>
          index < chunks.length
            ? { done: false, value: encoder.encode(chunks[index++]) }
            : { done: true, value: undefined },
        releaseLock: () => undefined
      };
    }
  }
});

// The offending stream: a complete, valid result followed by one more event.
// Everything before the violation is legal, which is exactly what makes it a
// good test — a guard that only rejected obvious garbage would let this land.
const VIOLATING_STREAM = [
  { event: "received" },
  { event: "generating" },
  { event: "completed", result: version() },
  { event: "finalizing" }
];

const requests = [];
globalThis.fetch = async (input, init = {}) => {
  const url = new URL(String(input), "http://localhost");
  const method = init.method ?? "GET";
  requests.push({ method, path: url.pathname, query: url.search });
  if (url.pathname === "/api/v1/content/stream") return ndjson(VIOLATING_STREAM);
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

globalThis.__DIYU_EXE01R_STREAM__ = { window: dom.window, requests };

await runSuite(
  new URL("./exe01r_stream_transaction.test.tsx", import.meta.url),
  "exe01r-stream-transaction"
);
