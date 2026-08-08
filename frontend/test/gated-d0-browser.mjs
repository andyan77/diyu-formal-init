import { spawn } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

import { build } from "esbuild";

import { resolveChromePath } from "./chrome-path.mjs";

const frontend = resolve(new URL("..", import.meta.url).pathname);
const repository = resolve(frontend, "..");
const chromePath = resolveChromePath({ configured: process.env.UX03_CHROME });
if (!chromePath) throw new Error("未找到本机 Chrome");
const workdir = mkdtempSync(join(tmpdir(), "gated-d0-browser-"));
const bundle = join(workdir, "bundle.js");
const profile = join(workdir, "profile");
let server;
let chrome;
let socket;

try {
  await build({
    entryPoints: [resolve(frontend, "test/gated-d0-browser-entry.tsx")],
    outfile: bundle,
    bundle: true,
    platform: "browser",
    format: "iife",
    target: "chrome120",
    jsx: "automatic",
    loader: { ".css": "empty" },
    logLevel: "warning"
  });
  const script = readFileSync(bundle);
  server = createServer((request, response) => {
    if (request.url === "/bundle.js") {
      response.writeHead(200, { "content-type": "text/javascript; charset=utf-8" });
      response.end(script);
      return;
    }
    response.writeHead(200, { "content-type": "text/html; charset=utf-8" });
    response.end("<!doctype html><html><body><div id='root'></div><script src='/bundle.js'></script></body></html>");
  });
  await new Promise(resolvePromise => server.listen(0, "127.0.0.1", resolvePromise));
  const address = server.address();
  if (!address || typeof address === "string") throw new Error("测试 HTTP 服务启动失败");

  chrome = spawn(
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
      "--remote-debugging-port=0",
      `--user-data-dir=${profile}`,
      "about:blank"
    ],
    { stdio: ["ignore", "ignore", "pipe"] }
  );
  const websocketUrl = await new Promise((resolvePromise, reject) => {
    let stderr = "";
    const timer = setTimeout(() => reject(new Error("Chrome DevTools 启动超时")), 10000);
    chrome.stderr.on("data", chunk => {
      stderr += chunk.toString();
      const match = stderr.match(/DevTools listening on (ws:\/\/[^\s]+)/);
      if (match) {
        clearTimeout(timer);
        resolvePromise(match[1]);
      }
    });
    chrome.once("exit", code => reject(new Error(`Chrome 提前退出 ${code}`)));
  });
  const { default: WebSocket } = await import(
    pathToFileURL(join(repository, "frontend/node_modules/ws/index.js")).href
  );
  socket = new WebSocket(websocketUrl);
  await new Promise((resolvePromise, reject) => {
    socket.once("open", resolvePromise);
    socket.once("error", reject);
  });
  let nextId = 0;
  const pending = new Map();
  const runtimeExceptions = [];
  socket.on("message", raw => {
    const message = JSON.parse(raw.toString());
    if (message.method === "Runtime.exceptionThrown") {
      runtimeExceptions.push(message.params?.exceptionDetails?.exception?.description ?? "unknown exception");
    }
    if (!message.id) return;
    const waiter = pending.get(message.id);
    if (!waiter) return;
    pending.delete(message.id);
    if (message.error) waiter.reject(new Error(JSON.stringify(message.error)));
    else waiter.resolve(message.result ?? {});
  });
  const send = (method, params = {}, sessionId) => new Promise((resolvePromise, reject) => {
    const id = ++nextId;
    pending.set(id, { resolve: resolvePromise, reject });
    socket.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
  });
  const target = await send("Target.createTarget", { url: `http://127.0.0.1:${address.port}/` });
  const attached = await send("Target.attachToTarget", { targetId: target.targetId, flatten: true });
  const sessionId = attached.sessionId;
  await send("Runtime.enable", {}, sessionId);
  const started = Date.now();
  let result;
  while (Date.now() - started < 20000) {
    const evaluated = await send(
      "Runtime.evaluate",
      { expression: "window.__GATED_D0_RESULT__", returnByValue: true },
      sessionId
    );
    result = evaluated.result?.value;
    if (result) break;
    await new Promise(resolvePromise => setTimeout(resolvePromise, 50));
  }
  if (!result) throw new Error("Chrome D0 交互测试超时");
  if (result.status !== "PASS") {
    throw new Error(`${result.detail}; runtime=${runtimeExceptions.join(" | ")}`);
  }
  const evidence = {
    browser: "headless-chrome",
    status: result.status,
    detail: result.detail,
    preview_requests: result.requests.filter(item => item.path.endsWith("/preview")).length,
    candidate_requests: result.requests.filter(item => item.path.endsWith("/candidates")).length,
    confirm_requests: result.requests.filter(item => item.path.endsWith("/confirm")).length
  };
  process.stdout.write(`${JSON.stringify(evidence)}\n`);
} finally {
  socket?.close();
  if (chrome) {
    const exited = new Promise(resolvePromise => chrome.once("exit", resolvePromise));
    chrome.kill("SIGTERM");
    const stopped = await Promise.race([
      exited.then(() => true),
      new Promise(resolvePromise => setTimeout(() => resolvePromise(false), 2000))
    ]);
    if (!stopped) {
      chrome.kill("SIGKILL");
      await exited;
    }
  }
  await new Promise(resolvePromise => server?.close(resolvePromise));
  rmSync(workdir, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
}
