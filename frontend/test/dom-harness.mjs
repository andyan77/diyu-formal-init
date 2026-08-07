// Shared JSDOM + esbuild scaffolding for the EXE-01R interaction suites.
//
// run.mjs, admin-run.mjs and ui04-user-paths.run.mjs each grew their own copy
// of this setup. The three are left alone on purpose — rewriting a passing
// journey suite to save duplication risks changing what it asserts — but the
// suites added here share one copy rather than starting a fourth and fifth.

import { build } from "esbuild";
import { rm } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { JSDOM } from "jsdom";

const GLOBALS = [
  "window",
  "document",
  "navigator",
  "Event",
  "CustomEvent",
  "MouseEvent",
  "KeyboardEvent",
  "Node",
  "HTMLElement",
  "HTMLInputElement",
  "HTMLTextAreaElement",
  "HTMLSelectElement",
  "getComputedStyle"
];

/** Build a JSDOM window at `url` and publish the globals React expects. */
export function installDom(url) {
  const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
    url,
    pretendToBeVisual: true
  });
  const mediaListeners = new Set();
  Object.defineProperty(dom.window, "matchMedia", {
    value: query => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: (_event, listener) => mediaListeners.add(listener),
      removeEventListener: (_event, listener) => mediaListeners.delete(listener),
      addListener: listener => mediaListeners.add(listener),
      removeListener: listener => mediaListeners.delete(listener),
      dispatchEvent: () => true
    }),
    configurable: true
  });
  for (const name of GLOBALS) {
    Object.defineProperty(globalThis, name, {
      value: dom.window[name] ?? dom.window,
      configurable: true,
      writable: true
    });
  }
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  return dom;
}

/** Bundle one .tsx suite and run it; the build directory never survives. */
export async function runSuite(entryUrl, slug) {
  const workdir = fileURLToPath(
    new URL(`../node_modules/.diyu-${slug}/`, import.meta.url)
  );
  const outfile = `${workdir}suite.mjs`;
  try {
    await build({
      entryPoints: [fileURLToPath(entryUrl)],
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
    await import(new URL(`../node_modules/.diyu-${slug}/suite.mjs`, import.meta.url).href);
  } finally {
    await rm(workdir, { recursive: true, force: true });
  }
}
