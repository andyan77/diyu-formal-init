import { build } from "esbuild";
import { rm } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { JSDOM } from "jsdom";

const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
  url: "http://localhost/tenant-admin",
  pretendToBeVisual: true
});
for (const name of [
  "window",
  "document",
  "navigator",
  "Event",
  "CustomEvent",
  "MouseEvent",
  "Node",
  "HTMLElement",
  "HTMLInputElement",
  "HTMLTextAreaElement",
  "HTMLSelectElement",
  "getComputedStyle"
]) {
  Object.defineProperty(globalThis, name, {
    value: dom.window[name] ?? dom.window,
    configurable: true,
    writable: true
  });
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const requests = [];
const routes = JSON.parse(
  await (await import("node:fs/promises")).readFile(
    new URL("./admin-fixtures.json", import.meta.url),
    "utf8"
  )
);
globalThis.fetch = async (input, init) => {
  const path = String(input).split("?")[0];
  const method = init?.method ?? "GET";
  requests.push({
    method,
    path,
    body: init?.body ? JSON.parse(String(init.body)) : null
  });
  const payload = routes[`${path}#${method}`] ?? routes[path] ?? {};
  return { ok: true, json: async () => payload };
};
globalThis.__DIYU_ADMIN_INTERACTION__ = { requests, window: dom.window };

const workdir = fileURLToPath(new URL("../node_modules/.diyu-admin-interaction/", import.meta.url));
const outfile = `${workdir}interaction.mjs`;
try {
  await build({
    entryPoints: [fileURLToPath(new URL("./admin_interaction.test.tsx", import.meta.url))],
    outfile,
    bundle: true,
    platform: "node",
    format: "esm",
    target: "node20",
    jsx: "automatic",
    external: ["jsdom", "react", "react-dom", "react/jsx-runtime", "react-dom/client"],
    loader: { ".css": "empty" },
    logLevel: "warning"
  });
  await import(
    new URL("../node_modules/.diyu-admin-interaction/interaction.mjs", import.meta.url).href
  );
} finally {
  await rm(workdir, { recursive: true, force: true });
}
