// Does an FE-00 prototype reflow, or does it just get wider than the window?
//
// AGENTS.md §14.7 puts 200% zoom in the evidence matrix, and the previous
// evidence run "covered" it by halving the CSS viewport and then screenshotting
// the same fixed-width clip — so all 12 zoom captures were byte-identical to
// their baselines and nothing was actually checked. This measures the property
// that matters instead: at 200% zoom the document must not be wider than the
// window it is in.
//
//   node frontend/tools/fe00-reflow-check.mjs
//
// Exits non-zero when a prototype overflows horizontally. Fixing an overflow
// means changing the prototype's visual layout, which is a design decision —
// see approved-prototypes.md P2v2/P3v2 rather than editing the layout here.

import { spawn } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { resolveChromePath } from "../test/chrome-path.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, "..", "..");
const FE00 = join(REPO, "docs/前端UI架构/FE-00");
const chromePath = resolveChromePath({ configured: process.env.EXE01_CHROME });
const { default: WebSocket } = await import(pathToFileURL(join(REPO, "frontend/node_modules/ws/index.js")).href);
const profile = mkdtempSync(join(tmpdir(), "probe-"));
const chrome = spawn(chromePath, ["--headless=new","--no-sandbox","--disable-gpu","--no-first-run","--hide-scrollbars","--allow-file-access-from-files","--remote-debugging-port=0",`--user-data-dir=${profile}`,"about:blank"], { stdio:["ignore","ignore","pipe"] });
const wsUrl = await new Promise((ok,bad)=>{let b="";const t=setTimeout(()=>bad(new Error("timeout")),15000);chrome.stderr.on("data",c=>{b+=c;const m=b.match(/ws:\/\/[^\s]+/);if(m){clearTimeout(t);ok(m[0]);}});});
const socket = new WebSocket(wsUrl);
await new Promise((ok,bad)=>{socket.on("open",ok);socket.on("error",bad);});
let id=0; const pending=new Map();
socket.on("message", raw=>{const f=JSON.parse(raw.toString());const e=pending.get(f.id);if(!e)return;pending.delete(f.id);f.error?e.bad(new Error(JSON.stringify(f.error))):e.ok(f.result);});
const send=(m,p={},s)=>new Promise((ok,bad)=>{const i=++id;pending.set(i,{ok,bad});socket.send(JSON.stringify({id:i,method:m,params:p,sessionId:s}));});

const results = [];
for (const [label, file, w, h] of [["desktop","原型-桌面-1440x900.html",1440,900],["mobile","原型-移动-390x844.html",390,844]]) {
  for (const [name, cw, ch, dsf] of [[`${label}-base`, w, h, 1], [`${label}-200pct`, Math.round(w/2), Math.round(h/2), 2]]) {
    const { targetId } = await send("Target.createTarget", { url: "about:blank" });
    const { sessionId } = await send("Target.attachToTarget", { targetId, flatten: true }, undefined);
    await send("Page.enable", {}, sessionId);
    await send("Emulation.setDeviceMetricsOverride", { width: cw, height: ch, deviceScaleFactor: dsf, mobile: cw < 500 }, sessionId);
    await send("Page.navigate", { url: pathToFileURL(join(FE00, file)).href }, sessionId);
    await new Promise(r => setTimeout(r, 900));
    const out = await send("Runtime.evaluate", {
      expression: `JSON.stringify({
        scrollWidth: document.documentElement.scrollWidth,
        clientWidth: document.documentElement.clientWidth,
        innerWidth: window.innerWidth,
        dpr: window.devicePixelRatio,
        visualScale: window.visualViewport ? window.visualViewport.scale : null,
        reducedMotion: matchMedia("(prefers-reduced-motion: reduce)").matches,
        animated: Array.from(document.querySelectorAll("*")).filter(node => {
          const style = getComputedStyle(node);
          return style.animationName !== "none" ||
            (style.transitionDuration !== "0s" && style.transitionProperty !== "none");
        }).length
      })`,
      returnByValue: true
    }, sessionId);
    const measured = JSON.parse(out.result.value);
    const overflow = measured.scrollWidth > measured.clientWidth;
    results.push({ condition: name, ...measured, overflow });
    console.log(
      `${name.padEnd(18)} scrollWidth=${String(measured.scrollWidth).padStart(5)}` +
      ` clientWidth=${String(measured.clientWidth).padStart(5)}` +
      ` animated=${measured.animated}` +
      `  ${overflow ? "OVERFLOW" : "ok"}`
    );
    await send("Target.closeTarget", { targetId });
  }
}
socket.close(); chrome.kill(); await new Promise(d=>chrome.once("exit",d)); rmSync(profile,{recursive:true,force:true,maxRetries:5});

const failing = results.filter(item => item.overflow);
if (failing.length) {
  console.error("");
  console.error("FAIL 以下条件下原型横向溢出，200% 重排不成立：");
  for (const item of failing) {
    console.error(
      `  ${item.condition}: 文档宽 ${item.scrollWidth} > 视口宽 ${item.clientWidth}`
    );
  }
  console.error("");
  console.error("这需要改原型的视觉布局，属设计裁决：见 approved-prototypes.md");
  console.error("的 P2v2 / P3v2，不要在这里改布局把检查做绿。");
  process.exitCode = 1;
} else {
  console.log("\nPASS 两份原型在 200% 缩放下都不横向溢出");
}
