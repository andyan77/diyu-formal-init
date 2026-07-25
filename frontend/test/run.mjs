// Bundle the interaction check with the bundler the project already uses, then run it.  Nothing
// else is installed and nothing is generated that has to be kept in sync by hand.
//
// The DOM is installed here, before the bundle is imported, because react-dom decides at module
// evaluation time whether it is running in a browser.  A window created later would leave it in
// its legacy fallback, where a plain input event never reaches onChange.
import { build } from "esbuild";
import { rm } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { JSDOM } from "jsdom";

const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
  url: "http://localhost/content",
  pretendToBeVisual: true
});
// defineProperty rather than assignment: Node 20 has no global navigator, while Node 22 defines
// one as a getter-only accessor, and plain assignment to that throws in a module.
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
  await (await import("node:fs/promises")).readFile(new URL("./fixtures.json", import.meta.url), "utf8")
);
globalThis.fetch = async (input, init) => {
  const path = String(input).split("?")[0];
  const headers = init?.headers ?? {};
  requests.push({
    method: init?.method ?? "GET",
    path,
    body: init?.body ? JSON.parse(String(init.body)) : null,
    preferenceSession: headers["X-Diyu-Preference-Session"] ?? null
  });
  const payload = routes[path] ?? {};
  return { ok: true, json: async () => payload };
};
globalThis.__DIYU_INTERACTION__ = { requests, window: dom.window };

const workdir = fileURLToPath(new URL("../node_modules/.diyu-interaction/", import.meta.url));
const outfile = `${workdir}interaction.mjs`;
try {
  await build({
    entryPoints: [fileURLToPath(new URL("./interaction.test.tsx", import.meta.url))],
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
  await import(new URL("../node_modules/.diyu-interaction/interaction.mjs", import.meta.url).href);
} finally {
  await rm(workdir, { recursive: true, force: true });
}
