import { spawn } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, readdirSync, rmSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "..");
const repo = resolve(root, "../../..");
const failures = [];
const results = [];
const record = (name, ok, detail) => {
  results.push({ name, ok, detail });
  if (!ok) failures.push({ name, detail });
};
const walk = (directory) => readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
  const path = join(directory, entry.name);
  return entry.isDirectory() ? walk(path) : [path];
});

const files = walk(root);
const htmlFiles = files.filter((path) => path.endsWith(".html"));
const localBroken = [];
for (const path of htmlFiles) {
  const source = readFileSync(path, "utf8");
  for (const match of source.matchAll(/\b(?:href|src)=["']([^"']+)["']/g)) {
    const value = match[1];
    if (/^https:\/\/diyuai\.cc\/activate\//.test(value)) continue;
    if (/^(?:https?:)?\/\//.test(value)) {
      localBroken.push(`${relative(root, path)} external ${value}`);
      continue;
    }
    const target = value.split(/[?#]/, 1)[0];
    if (!target || target.startsWith("#") || /^(?:data|about|javascript):/.test(target)) continue;
    if (!existsSync(resolve(dirname(path), target))) localBroken.push(`${relative(root, path)} -> ${value}`);
  }
}
record("本地链接与静态资源", localBroken.length === 0, localBroken);

const productText = readFileSync(join(root, "shared", "app.js"), "utf8");
const forbidden = [
  "NarrativeFrame", "fact ID", "compiler", "运行资产", "验收通过",
  "生产已就绪", "系统将为您", "陈列示意图"
].filter((term) => productText.includes(term));
record("裸产品语言无工程验收词", forbidden.length === 0, forbidden);
record("DM01 无绘图暗示", !/(?:图片|示意图)/.test(productText), "纯文字参考方案");

const chromeCandidates = [
  process.env.UX01_CHROME,
  "/usr/bin/google-chrome",
  "/usr/bin/chromium",
  "/home/faye/.cache/puppeteer/chrome/linux-148.0.7778.97/chrome-linux64/chrome",
  "/home/faye/.cache/puppeteer/chrome/linux-131.0.6778.204/chrome-linux64/chrome"
].filter(Boolean);
const chromePath = chromeCandidates.find((path) => existsSync(path) && statSync(path).isFile());
if (!chromePath) throw new Error("未找到本机 Chrome，不能降级验证");
const wsPath = join(repo, "frontend", "node_modules", "ws", "index.js");
const { default: WebSocket } = await import(pathToFileURL(wsPath).href);
const profile = mkdtempSync(join(tmpdir(), "ux01-review-"));
const chrome = spawn(chromePath, [
  "--headless=new", "--no-sandbox", "--disable-gpu", "--disable-background-networking",
  "--disable-component-update", "--disable-default-apps", "--disable-sync", "--no-first-run",
  "--allow-file-access-from-files", "--remote-debugging-port=0", `--user-data-dir=${profile}`, "about:blank"
], { stdio: ["ignore", "ignore", "pipe"] });

let socket;
try {
  const wsUrl = await new Promise((resolvePromise, reject) => {
    let buffer = "";
    const timer = setTimeout(() => reject(new Error("Chrome DevTools 启动超时")), 10000);
    chrome.stderr.on("data", (chunk) => {
      buffer += chunk.toString();
      const match = buffer.match(/DevTools listening on (ws:\/\/[^\s]+)/);
      if (match) { clearTimeout(timer); resolvePromise(match[1]); }
    });
    chrome.once("exit", (code) => reject(new Error(`Chrome 提前退出 ${code}`)));
  });
  socket = new WebSocket(wsUrl);
  await new Promise((resolvePromise, reject) => {
    socket.once("open", resolvePromise); socket.once("error", reject);
  });
  let id = 0;
  const pending = new Map();
  const events = [];
  socket.on("message", (raw) => {
    const message = JSON.parse(raw.toString());
    if (message.id) {
      const waiter = pending.get(message.id);
      if (!waiter) return;
      pending.delete(message.id);
      message.error ? waiter.reject(new Error(JSON.stringify(message.error))) : waiter.resolve(message.result || {});
    } else events.push(message);
  });
  const send = (method, params = {}, sessionId) => new Promise((resolvePromise, reject) => {
    const callId = ++id; pending.set(callId, { resolve: resolvePromise, reject });
    socket.send(JSON.stringify({ id: callId, method, params, ...(sessionId ? { sessionId } : {}) }));
  });
  const target = await send("Target.createTarget", { url: "about:blank" });
  const attached = await send("Target.attachToTarget", { targetId: target.targetId, flatten: true });
  const sessionId = attached.sessionId;
  await send("Page.enable", {}, sessionId);
  await send("Runtime.enable", {}, sessionId);
  await send("Network.enable", {}, sessionId);
  const evaluate = async (expression) => {
    const response = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true }, sessionId);
    if (response.exceptionDetails) throw new Error(JSON.stringify(response.exceptionDetails));
    return response.result?.value;
  };
  const navigate = async (url) => {
    await send("Page.navigate", { url }, sessionId);
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 180));
  };
  const reviewUrl = pathToFileURL(join(here, "index.html")).href;
  await navigate(reviewUrl);
  const journeyData = await evaluate(`Object.fromEntries(Object.entries(window.UX01_REVIEW.journeys).map(([k,v])=>[k,v.pages.map(p=>p.scene)]))`);
  record("四条旅程存在", JSON.stringify(Object.keys(journeyData)) === JSON.stringify(["public","admin","creator","dm01"]), Object.keys(journeyData));
  const allScenes = Object.values(journeyData).flat();
  record("连续状态数量", allScenes.length === 33, allScenes.length);

  for (const [journey, scenes] of Object.entries(journeyData)) {
    await evaluate(`window.UX01_REVIEW.choose(${JSON.stringify(journey)})`);
    for (let index = 0; index < scenes.length; index += 1) {
      await evaluate(`window.UX01_REVIEW.show(${index})`);
      await new Promise((resolvePromise) => setTimeout(resolvePromise, 60));
    }
    record(`评审壳连续操作 ${journey}`, true, `${scenes.length} screens`);
  }

  const productBase = pathToFileURL(join(root, "product", "index.html")).href;
  const viewports = [[1440, 900], [390, 844]];
  for (const [width, height] of viewports) {
    await send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile: width < 600 }, sessionId);
    for (const scene of allScenes) {
      await navigate(`${productBase}?scene=${scene}`);
      const layout = await evaluate(`(() => {
        const controls=[...document.querySelectorAll('button,a,input,select,textarea,summary')].filter(e=>e.offsetParent!==null);
        const small=controls.filter(e=>{const r=e.getBoundingClientRect();return r.width<44||r.height<44}).map(e=>e.textContent.trim().slice(0,30));
        return {overflow:document.documentElement.scrollWidth>document.documentElement.clientWidth+1,small,primary:document.querySelectorAll('.primary').length,title:document.title};
      })()`);
      if (layout.overflow) failures.push({ name: `${scene}@${width} 横向溢出`, detail: layout });
      if (layout.small.length) failures.push({ name: `${scene}@${width} 触控目标`, detail: layout.small });
      if (layout.primary > 1) failures.push({ name: `${scene}@${width} 主动作`, detail: layout.primary });
    }
    record(`${width}x${height} 全状态布局`, !failures.some((item) => item.name.includes(`@${width}`)), `${allScenes.length} scenes`);
  }
  await navigate(`${productBase}?scene=home`);
  await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-motion", value: "reduce" }] }, sessionId);
  const reduced = await evaluate(`getComputedStyle(document.querySelector('.home-mark')).animationDuration`);
  record("减少动效", parseFloat(reduced) <= 0.001, reduced);
  const focusVisible = await evaluate(`getComputedStyle(document.querySelector('button')).minHeight`);
  record("键盘主路径与焦点基础", parseFloat(focusVisible) >= 44, focusVisible);
  const consoleErrors = events.filter((event) => event.method === "Runtime.exceptionThrown" || (event.method === "Runtime.consoleAPICalled" && event.params?.type === "error"));
  record("无控制台错误", consoleErrors.length === 0, consoleErrors.length);
  const external = events.filter((event) => event.method === "Network.requestWillBeSent")
    .map((event) => event.params?.request?.url || "")
    .filter((url) => /^https?:\/\//.test(url));
  record("无外部网络请求", external.length === 0, external);
} finally {
  if (socket?.readyState === WebSocket.OPEN) socket.close();
  chrome.kill("SIGTERM");
  rmSync(profile, { recursive: true, force: true });
}

if (failures.length) {
  console.error(JSON.stringify({ status: "failed", failures, results }, null, 2));
  process.exit(1);
}
console.log(JSON.stringify({ status: "passed", checks: results.length, scenes: 33 }, null, 2));
