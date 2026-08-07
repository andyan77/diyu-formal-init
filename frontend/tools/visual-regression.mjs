// Screenshot a directory of static pages and dump every element's computed style.
//
// Screenshots are the required FE-03 artifact, but eyes are a weak oracle for
// "did deleting 94 CSS rules change anything?". The computed-style dump is the
// actual proof: run it once against the old stylesheet and once against the
// new one, and any difference in any property on any element shows up as a
// diff instead of a judgement call.
//
//   node frontend/tools/visual-regression.mjs --pages DIR --out DIR

import { spawn } from "node:child_process";
import { mkdirSync, mkdtempSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

import { resolveChromePath } from "../test/chrome-path.mjs";

const VIEWPORTS = [
  { name: "desktop-1440x900", width: 1440, height: 900 },
  { name: "mobile-390x844", width: 390, height: 844 }
];

const argOf = flag => {
  const index = process.argv.indexOf(flag);
  if (index < 0) throw new Error(`missing ${flag}`);
  return resolve(process.argv[index + 1]);
};

const pagesDir = argOf("--pages");
const outDir = argOf("--out");
mkdirSync(outDir, { recursive: true });

const chromePath = resolveChromePath({ configured: process.env.EXE01_CHROME });
if (!chromePath) throw new Error("未找到本机 Chrome");

const { default: WebSocket } = await import(
  pathToFileURL(join(resolve("."), "node_modules", "ws", "index.js")).href
);

const profile = mkdtempSync(join(tmpdir(), "exe01-visual-"));
const chrome = spawn(
  chromePath,
  [
    "--headless=new",
    "--no-sandbox",
    "--disable-gpu",
    "--disable-background-networking",
    "--disable-component-update",
    "--disable-default-apps",
    "--disable-sync",
    "--no-first-run",
    "--force-device-scale-factor=1",
    "--hide-scrollbars",
    "--remote-debugging-port=0",
    `--user-data-dir=${profile}`,
    "about:blank"
  ],
  { stdio: ["ignore", "ignore", "pipe"] }
);

const websocketUrl = await new Promise((done, fail) => {
  let buffer = "";
  const timer = setTimeout(() => fail(new Error("Chrome DevTools 启动超时")), 15000);
  chrome.stderr.on("data", chunk => {
    buffer += chunk.toString();
    const match = buffer.match(/ws:\/\/[^\s]+/);
    if (match) {
      clearTimeout(timer);
      done(match[0]);
    }
  });
});

const socket = new WebSocket(websocketUrl);
await new Promise((done, fail) => {
  socket.on("open", done);
  socket.on("error", fail);
});

let nextId = 0;
const pending = new Map();
socket.on("message", raw => {
  const frame = JSON.parse(raw.toString());
  const entry = pending.get(frame.id);
  if (!entry) return;
  pending.delete(frame.id);
  frame.error ? entry.fail(new Error(JSON.stringify(frame.error))) : entry.done(frame.result);
});

const send = (method, params = {}, sessionId) =>
  new Promise((done, fail) => {
    const id = ++nextId;
    pending.set(id, { done, fail });
    socket.send(JSON.stringify({ id, method, params, sessionId }));
  });

// Every declared property of every element, so nothing can shift unnoticed.
const DUMP_STYLES = `(() => {
  const out = [];
  document.querySelectorAll("*").forEach((node, index) => {
    const style = window.getComputedStyle(node);
    const record = { i: index, tag: node.tagName, cls: node.className || "" };
    for (const property of style) record[property] = style.getPropertyValue(property);
    out.push(record);
  });
  return JSON.stringify(out);
})()`;

const pages = readdirSync(pagesDir).filter(name => name.endsWith(".html")).sort();
const styles = {};

try {
  for (const page of pages) {
    for (const viewport of VIEWPORTS) {
      const { targetId } = await send("Target.createTarget", { url: "about:blank" });
      const { sessionId } = await send("Target.attachToTarget", {
        targetId,
        flatten: true
      });
      await send("Page.enable", {}, sessionId);
      await send(
        "Emulation.setDeviceMetricsOverride",
        {
          width: viewport.width,
          height: viewport.height,
          deviceScaleFactor: 1,
          mobile: viewport.width < 500
        },
        sessionId
      );
      const loaded = new Promise(done => {
        const listener = raw => {
          const frame = JSON.parse(raw.toString());
          if (frame.method === "Page.loadEventFired" && frame.sessionId === sessionId) {
            socket.off("message", listener);
            done();
          }
        };
        socket.on("message", listener);
      });
      await send(
        "Page.navigate",
        { url: pathToFileURL(join(pagesDir, page)).href },
        sessionId
      );
      await loaded;

      const shot = await send(
        "Page.captureScreenshot",
        { format: "png", captureBeyondViewport: true },
        sessionId
      );
      const stem = `${page.replace(/\.html$/, "")}--${viewport.name}`;
      writeFileSync(join(outDir, `${stem}.png`), Buffer.from(shot.data, "base64"));

      const dumped = await send(
        "Runtime.evaluate",
        { expression: DUMP_STYLES, returnByValue: true },
        sessionId
      );
      styles[stem] = JSON.parse(dumped.result.value);
      await send("Target.closeTarget", { targetId });
      console.log(`captured ${stem}`);
    }
  }
  writeFileSync(
    join(outDir, "computed-styles.json"),
    `${JSON.stringify(styles, null, 0)}\n`
  );
} finally {
  socket.close();
  chrome.kill();
  // Chrome keeps writing its profile for a moment after SIGTERM; removing it
  // before the process is gone races and throws ENOTEMPTY.
  await new Promise(done => chrome.once("exit", done));
  rmSync(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
}
