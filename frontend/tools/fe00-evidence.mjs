// Capture the FE-00 visual evidence matrix, and record enough about each
// capture that the next reader can tell whether it proves anything.
//
// The first version of this tool "covered" 200% zoom by halving the CSS
// viewport and then screenshotting the same fixed-width clip, so all twelve
// zoom captures were byte-identical to their baselines. The condition was
// listed and nothing was checked. Two things changed:
//
//   - zoom is emulated for real (CSS viewport halved *and* devicePixelRatio 2),
//     so a zoom capture has different pixel dimensions from its baseline and
//     assert_visual_evidence.py can refuse two identical hashes for one frame;
//   - the mobile prototype is captured state by state instead of as one long
//     all-states strip, which showed everything and demonstrated nothing.
//
// Reflow acceptance at 200% belongs to the real product pages (founder decision
// A, guide EXE-01R section R4); these fixed-canvas prototypes are exempt, and
// the manifest says so per capture rather than leaving it implied.
//
//   node frontend/tools/fe00-evidence.mjs --out DIR

import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { resolveChromePath } from "../test/chrome-path.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, "..", "..");
const FE00 = join(REPO, "docs/前端UI架构/FE-00");

const DESKTOP_FRAMES = [
  "fe00-today", "fe00-advisor", "fe00-proposal", "fe00-producing", "fe00-package",
  "fe00-empty", "fe00-loading", "fe00-failure", "fe00-cross-account",
  "fe00-gap", "fe00-legacy", "fe00-longtext"
];
const MOBILE_FRAMES = [
  "fe00-m-today", "fe00-m-advisor", "fe00-m-basis", "fe00-m-proposal",
  "fe00-m-package", "fe00-m-failure", "fe00-m-cross-account", "fe00-m-states",
  "fe00-m-longtext"
];

const DOCUMENTS = [
  {
    label: "desktop",
    file: "原型-桌面-1440x900.html",
    frames: DESKTOP_FRAMES,
    conditions: [
      { name: "base", width: 1440, height: 900, scale: 1, reflow: "enforced" },
      { name: "zoom200", width: 720, height: 450, scale: 2, reflow: "na-by-design" }
    ]
  },
  {
    label: "mobile",
    file: "原型-移动-390x844.html",
    frames: MOBILE_FRAMES,
    conditions: [
      { name: "base", width: 390, height: 844, scale: 1, reflow: "enforced" },
      { name: "zoom200", width: 195, height: 422, scale: 2, reflow: "na-by-design" }
    ]
  }
];

const argOf = flag => {
  const index = process.argv.indexOf(flag);
  if (index < 0) throw new Error(`missing ${flag}`);
  return resolve(process.argv[index + 1]);
};
const outDir = argOf("--out");
mkdirSync(outDir, { recursive: true });

const sha256 = buffer => createHash("sha256").update(buffer).digest("hex");
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
  "--no-first-run", "--hide-scrollbars", "--allow-file-access-from-files",
  "--force-prefers-reduced-motion", "--remote-debugging-port=0",
  `--user-data-dir=${profile}`, "about:blank"
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
  // Real zoom: fewer CSS pixels across the same physical width. Halving the
  // viewport alone would leave the capture byte-identical to the baseline.
  await send("Emulation.setDeviceMetricsOverride", {
    width: condition.width, height: condition.height,
    deviceScaleFactor: condition.scale, mobile: condition.width < 500
  }, sessionId);
  await send("Emulation.setEmulatedMedia", {
    features: [{ name: "prefers-reduced-motion", value: "reduce" }]
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

const evaluate = async (sessionId, expression) => {
  const result = await send("Runtime.evaluate", { expression, returnByValue: true }, sessionId);
  return result.result.value;
};

/** Physical pixel size straight out of the PNG header, not out of the request. */
const pngSize = buffer => {
  if (buffer.readUInt32BE(0) !== 0x89504e47) throw new Error("不是 PNG");
  if (buffer.toString("ascii", 12, 16) !== "IHDR") throw new Error("缺少 IHDR");
  return { width: buffer.readUInt32BE(16), height: buffer.readUInt32BE(20) };
};

const captureFrame = async (sessionId, frameId, file) => {
  const box = await evaluate(sessionId, `(() => {
    const node = document.getElementById(${JSON.stringify(frameId)});
    if (!node) return "null";
    node.scrollIntoView();
    const target = node.querySelector(".fe00-frame, .fe00-phone") || node;
    const r = target.getBoundingClientRect();
    return JSON.stringify({
      x: Math.round(r.left + window.scrollX), y: Math.round(r.top + window.scrollY),
      width: Math.round(r.width), height: Math.round(r.height)
    });
  })()`);
  const clip = JSON.parse(box);
  if (!clip) return null;
  const shot = await send("Page.captureScreenshot", {
    format: "png", captureBeyondViewport: true, clip: { ...clip, scale: 1 }
  }, sessionId);
  const bytes = Buffer.from(shot.data, "base64");
  writeFileSync(file, bytes);
  return { clip, bytes };
};

/**
 * Can the frame's primary action be reached by keyboard, and can you see where
 * you are when you get there? Same shape as ux02-responsive-browser.mjs.
 */
const keyboardProbe = async (sessionId, frameId) =>
  evaluate(sessionId, `(() => {
    const frame = document.getElementById(${JSON.stringify(frameId)});
    if (!frame) return null;
    const focusable = Array.from(frame.querySelectorAll(
      "a[href], button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex='-1'])"
    ));
    if (!focusable.length) return { frame: ${JSON.stringify(frameId)}, actions: 0, reachable: null, focusVisible: null, note: "静态画面，无可聚焦动作" };
    let reachable = 0, visible = 0;
    for (const node of focusable) {
      node.focus();
      if (document.activeElement === node) {
        reachable += 1;
        const style = getComputedStyle(node, ":focus-visible") || getComputedStyle(node);
        if (style.outlineStyle !== "none" || style.boxShadow !== "none" ||
            getComputedStyle(node).outlineStyle !== "none") visible += 1;
      }
    }
    return {
      frame: ${JSON.stringify(frameId)},
      actions: focusable.length,
      reachable,
      focusVisible: visible,
      escapeDialog: "N/A — 原型内没有对话框"
    };
  })()`);

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

const manifest = {
  schema: "exe01r.fe00_evidence.v2",
  // Binding the captures to the exact prototype bytes they came from: edit a
  // prototype without rerunning this and the assertion goes red.
  prototypes: Object.fromEntries(
    DOCUMENTS.map(doc => [doc.file, sha256(readFileSync(join(FE00, doc.file)))])
  ),
  decisions: {
    zoom200:
      "N/A-by-design — 固定画布原型豁免 200% 重排验收（founder 裁决 A，指南 EXE-01R 节 R4）；" +
      "截图仍真实采集以便同帧重复哈希检测生效，重排验收挂真实产品页。",
    reducedMotion:
      "N/A — 原型样式表无条件 animation:none/transition:none，实测 animated 计数为 0，" +
      "无动效可减；不以重复截图充当该条件证据。"
  },
  captures: [],
  keyboard: [],
  axe: {}
};

try {
  for (const doc of DOCUMENTS) {
    const fileUrl = pathToFileURL(join(FE00, doc.file)).href;
    for (const condition of doc.conditions) {
      const { targetId, sessionId } = await openPage(fileUrl, condition);
      const viewport = await evaluate(sessionId, `JSON.stringify({
        innerWidth: window.innerWidth, innerHeight: window.innerHeight,
        clientWidth: document.documentElement.clientWidth,
        scrollWidth: document.documentElement.scrollWidth,
        devicePixelRatio: window.devicePixelRatio,
        visualScale: window.visualViewport ? window.visualViewport.scale : null,
        reducedMotion: matchMedia("(prefers-reduced-motion: reduce)").matches,
        animated: Array.from(document.querySelectorAll("*")).filter(n => {
          const s = getComputedStyle(n);
          return s.animationName !== "none" ||
            (s.transitionDuration !== "0s" && s.transitionProperty !== "none");
        }).length
      })`);
      const measured = JSON.parse(viewport);
      for (const frameId of doc.frames) {
        const name = `${doc.label}--${frameId.replace(/^fe00-(m-)?/, "")}--${condition.name}.png`;
        const captured = await captureFrame(sessionId, frameId, join(outDir, name));
        if (!captured) throw new Error(`找不到画框 ${frameId}`);
        const size = pngSize(captured.bytes);
        manifest.captures.push({
          file: name,
          document: doc.file,
          frame: frameId,
          condition: condition.name,
          reflow: condition.reflow,
          zoom_mechanism:
            condition.scale === 1
              ? "none"
              : "Emulation.setDeviceMetricsOverride: CSS 视口减半 + deviceScaleFactor 2",
          css_viewport_width: condition.width,
          css_viewport_height: condition.height,
          device_scale_factor: condition.scale,
          png_width: size.width,
          png_height: size.height,
          sha256: sha256(captured.bytes),
          ...measured
        });
      }
      for (const frameId of doc.frames) {
        const probe = await keyboardProbe(sessionId, frameId);
        if (probe) manifest.keyboard.push({ condition: condition.name, ...probe });
      }
      if (condition.name === "base") manifest.axe[doc.label] = await runAxe(sessionId);
      await send("Target.closeTarget", { targetId });
      console.log(`captured ${doc.label} @ ${condition.name} (${doc.frames.length} frames)`);
    }
  }
  writeFileSync(join(outDir, "evidence-manifest.json"),
    `${JSON.stringify(manifest, null, 2)}\n`);
  const blocking = Object.values(manifest.axe).flat()
    .filter(v => v.impact === "serious" || v.impact === "critical");
  console.log(`captures: ${manifest.captures.length}, keyboard probes: ${manifest.keyboard.length}`);
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
