// Capture the FE-00 visual evidence matrix and run an accessibility scan.
//
// AGENTS.md §14.7 requires every UI deliverable to ship screenshots at
// 1440×900, 390×844, 200% zoom and prefers-reduced-motion, covering the
// loading, empty, error and long-text states, taken from deterministic data
// with animation disabled so a rerun produces the same bytes. This walks the
// FE-00 prototypes frame by frame and does exactly that, then runs axe-core
// over each prototype.
//
//   node frontend/tools/fe00-evidence.mjs --out DIR

import { spawn } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { resolveChromePath } from "../test/chrome-path.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, "..", "..");
const FE00 = join(REPO, "docs/前端UI架构/FE-00");

// 200% browser zoom halves the CSS viewport; that is the reflow being checked.
const CONDITIONS = [
  { name: "1440x900", width: 1440, height: 900, motion: "no-preference" },
  { name: "200pct-zoom", width: 720, height: 450, motion: "no-preference" },
  { name: "reduced-motion", width: 1440, height: 900, motion: "reduce" }
];
const MOBILE_CONDITIONS = [
  { name: "390x844", width: 390, height: 844, motion: "no-preference" },
  { name: "200pct-zoom", width: 195, height: 422, motion: "no-preference" },
  { name: "reduced-motion", width: 390, height: 844, motion: "reduce" }
];

const DESKTOP_FRAMES = [
  "fe00-today", "fe00-advisor", "fe00-proposal", "fe00-producing", "fe00-package",
  "fe00-empty", "fe00-loading", "fe00-failure", "fe00-cross-account",
  "fe00-gap", "fe00-legacy", "fe00-longtext"
];

const argOf = flag => {
  const index = process.argv.indexOf(flag);
  if (index < 0) throw new Error(`missing ${flag}`);
  return resolve(process.argv[index + 1]);
};
const outDir = argOf("--out");
mkdirSync(outDir, { recursive: true });

const chromePath = resolveChromePath({ configured: process.env.EXE01_CHROME });
if (!chromePath) throw new Error("未找到本机 Chrome");
const axeSource = readFileSync(join(HERE, "..", "node_modules/axe-core/axe.min.js"), "utf8");
const { default: WebSocket } = await import(
  pathToFileURL(join(HERE, "..", "node_modules", "ws", "index.js")).href
);

const profile = mkdtempSync(join(tmpdir(), "fe00-evidence-"));
const chrome = spawn(chromePath, [
  "--headless=new", "--no-sandbox", "--disable-gpu", "--disable-background-networking",
  "--disable-component-update", "--disable-default-apps", "--disable-sync",
  "--no-first-run", "--force-device-scale-factor=1", "--hide-scrollbars",
  "--allow-file-access-from-files", "--force-prefers-reduced-motion",
  "--remote-debugging-port=0", `--user-data-dir=${profile}`, "about:blank"
], { stdio: ["ignore", "ignore", "pipe"] });

const websocketUrl = await new Promise((done, fail) => {
  let buffer = "";
  const timer = setTimeout(() => fail(new Error("Chrome DevTools 启动超时")), 15000);
  chrome.stderr.on("data", chunk => {
    buffer += chunk.toString();
    const match = buffer.match(/ws:\/\/[^\s]+/);
    if (match) { clearTimeout(timer); done(match[0]); }
  });
});

const socket = new WebSocket(websocketUrl);
await new Promise((done, fail) => { socket.on("open", done); socket.on("error", fail); });

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

const openPage = async (fileUrl, condition) => {
  const { targetId } = await send("Target.createTarget", { url: "about:blank" });
  const { sessionId } = await send("Target.attachToTarget", { targetId, flatten: true });
  await send("Page.enable", {}, sessionId);
  await send("Emulation.setDeviceMetricsOverride", {
    width: condition.width, height: condition.height,
    deviceScaleFactor: 1, mobile: condition.width < 500
  }, sessionId);
  await send("Emulation.setEmulatedMedia", {
    features: [{ name: "prefers-reduced-motion", value: condition.motion }]
  }, sessionId);
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
  await send("Page.navigate", { url: fileUrl }, sessionId);
  await loaded;
  return { targetId, sessionId };
};

const captureFrame = async (sessionId, frameId, file) => {
  const box = await send("Runtime.evaluate", {
    expression: `(() => {
      const node = document.getElementById(${JSON.stringify(frameId)});
      if (!node) return "null";
      node.scrollIntoView();
      const target = node.querySelector(".fe00-frame, .fe00-phone") || node;
      const r = target.getBoundingClientRect();
      return JSON.stringify({
        x: Math.round(r.left + window.scrollX), y: Math.round(r.top + window.scrollY),
        width: Math.round(r.width), height: Math.round(r.height)
      });
    })()`,
    returnByValue: true
  }, sessionId);
  const clip = JSON.parse(box.result.value);
  if (!clip) return null;
  const shot = await send("Page.captureScreenshot", {
    format: "png", captureBeyondViewport: true, clip: { ...clip, scale: 1 }
  }, sessionId);
  writeFileSync(file, Buffer.from(shot.data, "base64"));
  return clip;
};

const runAxe = async sessionId => {
  await send("Runtime.evaluate", { expression: axeSource }, sessionId);
  const result = await send("Runtime.evaluate", {
    expression: `axe.run(document, {resultTypes:["violations"]}).then(r => JSON.stringify(
      r.violations.map(v => ({
        id: v.id, impact: v.impact, help: v.help, count: v.nodes.length,
        targets: v.nodes.slice(0, 8).map(n => n.target.join(" ")),
        summary: v.nodes[0] && v.nodes[0].failureSummary
      }))))`,
    awaitPromise: true, returnByValue: true
  }, sessionId);
  return JSON.parse(result.result.value);
};

const manifest = { schema: "exe01.fe00_evidence.v1", captures: [], axe: {} };

try {
  for (const [label, fileName, frames, conditions] of [
    ["desktop", "原型-桌面-1440x900.html", DESKTOP_FRAMES, CONDITIONS],
    ["mobile", "原型-移动-390x844.html", null, MOBILE_CONDITIONS]
  ]) {
    const fileUrl = pathToFileURL(join(FE00, fileName)).href;
    for (const condition of conditions) {
      const { targetId, sessionId } = await openPage(fileUrl, condition);
      if (frames) {
        for (const frameId of frames) {
          const name = `${label}--${frameId.replace("fe00-", "")}--${condition.name}.png`;
          const clip = await captureFrame(sessionId, frameId, join(outDir, name));
          if (clip) manifest.captures.push({ file: name, frame: frameId, ...condition, ...clip });
        }
      } else {
        const name = `${label}--all-states--${condition.name}.png`;
        const shot = await send("Page.captureScreenshot",
          { format: "png", captureBeyondViewport: true }, sessionId);
        writeFileSync(join(outDir, name), Buffer.from(shot.data, "base64"));
        manifest.captures.push({ file: name, frame: "all", ...condition });
      }
      if (condition.name === conditions[0].name) {
        manifest.axe[label] = await runAxe(sessionId);
      }
      await send("Target.closeTarget", { targetId });
      console.log(`captured ${label} @ ${condition.name}`);
    }
  }
  writeFileSync(join(outDir, "evidence-manifest.json"),
    `${JSON.stringify(manifest, null, 2)}\n`);
  const blocking = Object.values(manifest.axe).flat()
    .filter(v => v.impact === "serious" || v.impact === "critical");
  console.log(`axe violations: ${Object.values(manifest.axe).flat().length} total, ` +
    `${blocking.length} serious/critical`);
  if (blocking.length) {
    console.error(JSON.stringify(blocking, null, 2));
    process.exitCode = 1;
  }
} finally {
  socket.close();
  chrome.kill();
  await new Promise(done => chrome.once("exit", done));
  rmSync(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
}
