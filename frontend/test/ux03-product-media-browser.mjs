import { spawn } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

import { resolveChromePath } from "./chrome-path.mjs";

const required = name => {
  const value = process.env[name];
  if (!value) throw new Error(`缺少 ${name}`);
  return value;
};
const baseUrl = required("UX03_PRODUCT_MEDIA_BASE_URL").replace(/\/$/, "");
const adminToken = required("UX03_PRODUCT_MEDIA_ADMIN_TOKEN");
const creatorToken = required("UX03_PRODUCT_MEDIA_CREATOR_TOKEN");
const accountId = required("UX03_PRODUCT_MEDIA_ACCOUNT_ID");
const forbiddenMaterial = required(
  "UX03_PRODUCT_MEDIA_FORBIDDEN_MATERIAL"
);
const skipBinding =
  process.env.UX03_PRODUCT_MEDIA_SKIP_BINDING === "1";
const products = [
  required("UX03_PRODUCT_MEDIA_PRODUCT_1"),
  required("UX03_PRODUCT_MEDIA_PRODUCT_2")
];
const materials = [
  required("UX03_PRODUCT_MEDIA_MATERIAL_1"),
  required("UX03_PRODUCT_MEDIA_MATERIAL_2")
];
const repo = resolve(new URL("../..", import.meta.url).pathname);
const chromePath = resolveChromePath({ configured: process.env.UX03_CHROME });
if (!chromePath) throw new Error("未找到本机 Chrome");
const { default: WebSocket } = await import(
  pathToFileURL(join(repo, "frontend", "node_modules", "ws", "index.js")).href
);
const profile = mkdtempSync(join(tmpdir(), "ux03-product-media-browser-"));
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
    "--remote-debugging-port=0",
    `--user-data-dir=${profile}`,
    "about:blank"
  ],
  { stdio: ["ignore", "ignore", "pipe"] }
);
const wait = milliseconds =>
  new Promise(resolvePromise => setTimeout(resolvePromise, milliseconds));
const ensure = (value, message) => {
  if (!value) throw new Error(message);
};
let socket;
const failures = [];
const lifecycleEvents = [];
let taskId = "";

try {
  const websocketUrl = await new Promise((resolvePromise, reject) => {
    let buffer = "";
    const timer = setTimeout(
      () => reject(new Error("Chrome DevTools 启动超时")),
      10000
    );
    chrome.stderr.on("data", chunk => {
      buffer += chunk.toString();
      const match = buffer.match(/DevTools listening on (ws:\/\/[^\s]+)/);
      if (match) {
        clearTimeout(timer);
        resolvePromise(match[1]);
      }
    });
    chrome.once("exit", code =>
      reject(new Error(`Chrome 提前退出 ${code}`))
    );
  });
  socket = new WebSocket(websocketUrl);
  await new Promise((resolvePromise, reject) => {
    socket.once("open", resolvePromise);
    socket.once("error", reject);
  });
  let callId = 0;
  const pending = new Map();
  const browserEvents = [];
  socket.on("message", raw => {
    const message = JSON.parse(raw.toString());
    if (message.id) {
      const waiter = pending.get(message.id);
      if (!waiter) return;
      pending.delete(message.id);
      if (message.error) waiter.reject(new Error(JSON.stringify(message.error)));
      else waiter.resolve(message.result ?? {});
      return;
    }
    browserEvents.push(message);
  });
  const send = (method, params = {}, sessionId) =>
    new Promise((resolvePromise, reject) => {
      const id = ++callId;
      pending.set(id, { resolve: resolvePromise, reject });
      socket.send(
        JSON.stringify({
          id,
          method,
          params,
          ...(sessionId ? { sessionId } : {})
        })
      );
    });
  const context = await send("Target.createBrowserContext");
  const target = await send("Target.createTarget", {
    url: "about:blank",
    browserContextId: context.browserContextId
  });
  const attached = await send("Target.attachToTarget", {
    targetId: target.targetId,
    flatten: true
  });
  const sessionId = attached.sessionId;
  await send("Page.enable", {}, sessionId);
  await send("Runtime.enable", {}, sessionId);
  await send("Network.enable", {}, sessionId);
  await send("Log.enable", {}, sessionId);
  await send(
    "Page.addScriptToEvaluateOnNewDocument",
    {
      source: `(() => {
        const original = window.fetch.bind(window);
        window.__ux03ProductMediaStreams = [];
        window.fetch = async (...args) => {
          const response = await original(...args);
          const raw = typeof args[0] === "string" ? args[0] : args[0]?.url ?? "";
          if (String(raw).includes("/api/v1/content/stream")) {
            const captured = { body: null, error: null };
            window.__ux03ProductMediaStreams.push(captured);
            response.clone().text().then(
              body => { captured.body = body; },
              error => { captured.error = String(error); }
            );
          }
          return response;
        };
      })();`
    },
    sessionId
  );
  const evaluate = async expression => {
    const response = await send(
      "Runtime.evaluate",
      { expression, awaitPromise: true, returnByValue: true },
      sessionId
    );
    if (response.exceptionDetails) {
      throw new Error(JSON.stringify(response.exceptionDetails));
    }
    return response.result?.value;
  };
  const waitFor = async (expression, label, timeout = 30000) => {
    const started = Date.now();
    while (Date.now() - started < timeout) {
      try {
        if (await evaluate(expression)) return;
      } catch {
        // Navigation briefly replaces the execution context.
      }
      await wait(100);
    }
    const body = await evaluate("document.body?.innerText.slice(0,1600) ?? ''");
    throw new Error(`等待超时：${label}；页面：${body}`);
  };
  const setCookie = async value => {
    await send(
      "Network.setCookie",
      {
        name: "diyu_session",
        value,
        url: baseUrl,
        path: "/",
        httpOnly: true,
        secure: false,
        sameSite: "Lax"
      },
      sessionId
    );
  };
  const clickText = async (selector, text) => {
    const clicked = await evaluate(`(() => {
      const node=[...document.querySelectorAll(${JSON.stringify(selector)})]
        .find(item =>
          getComputedStyle(item).display !== "none" &&
          item.textContent.trim().includes(${JSON.stringify(text)})
        );
      if (!node) return false;
      node.scrollIntoView({block:"center"});
      node.click();
      return true;
    })()`);
    ensure(clicked, `无法点击 ${text}`);
    await wait(150);
  };
  const navigate = async url => {
    await send("Page.navigate", { url }, sessionId);
    await waitFor("document.readyState==='complete'", url);
  };

  if (!skipBinding) {
    await send(
      "Emulation.setDeviceMetricsOverride",
      { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false },
      sessionId
    );
    await setCookie(adminToken);
    await navigate(`${baseUrl}/tenant-admin`);
    await waitFor(
      "Boolean(document.querySelector('.tenant-admin-app'))",
      "品牌管理"
    );
    await clickText(".tenant-nav button", "品牌资料库");
    await waitFor(
      "document.querySelectorAll('.material-list article').length >= 2",
      "组织官方素材"
    );
    for (let index = 0; index < 2; index += 1) {
      const opened = await evaluate(`(() => {
        const article=[...document.querySelectorAll('.material-list article')]
          .find(item=>item.textContent.includes(${JSON.stringify(materials[index])}));
        const button=article?.querySelector('button');
        if(!button)return false;
        button.click();
        return true;
      })()`);
      ensure(opened, `无法打开素材 ${materials[index]}`);
      await waitFor(
        "Boolean(document.querySelector('.tenant-drawer select'))",
        "素材商品关联"
      );
      const selected = await evaluate(`(() => {
        const select=[...document.querySelectorAll('.tenant-drawer select')]
          .find(item=>[...item.options].some(option =>
            option.textContent.includes(${JSON.stringify(products[index])})
          ));
        if(!select)return false;
        const option=[...select.options].find(item =>
          item.textContent.includes(${JSON.stringify(products[index])})
        );
        select.value=option.value;
        select.dispatchEvent(new Event('change',{bubbles:true}));
        return true;
      })()`);
      ensure(selected, `无法选择商品 ${products[index]}`);
      await clickText(".tenant-drawer button", "建立商品关联");
      await waitFor(
        `document.querySelector('.tenant-drawer')?.innerText.includes(${JSON.stringify(products[index])})`,
        "商品关联回写"
      );
      await clickText(".tenant-drawer header button", "关闭");
      await waitFor(
        "!document.querySelector('.tenant-drawer')",
        "关闭素材抽屉"
      );
    }
  }

  await setCookie(creatorToken);
  await send(
    "Emulation.setDeviceMetricsOverride",
    { width: 390, height: 844, deviceScaleFactor: 1, mobile: true },
    sessionId
  );
  await navigate(
    `${baseUrl}/content?publishing_identity_id=${accountId}&target=xiaohongshu_graphic`
  );
  await waitFor(
    "Boolean(document.querySelector('.creator-composer textarea'))",
    "正式创作端"
  );
  await clickText(".composer-resource-actions button", "素材");
  await waitFor(
    "document.querySelectorAll('.material-picker label').length >= 2",
    "本次素材选择"
  );
  const leakedHeadquartersMaterial = await evaluate(
    `document.querySelector('.creator-tool-drawer')?.innerText.includes(${JSON.stringify(forbiddenMaterial)}) ?? false`
  );
  ensure(
    !leakedHeadquartersMaterial,
    "区域账号看到了总部专用素材元数据"
  );
  for (const product of products) {
    const checked = await evaluate(`(() => {
      const label=[...document.querySelectorAll('.material-picker label')]
        .find(item=>item.textContent.includes(${JSON.stringify(product)}));
      const input=label?.querySelector('input[type=checkbox]');
      if(!input)return false;
      input.click();
      return input.checked;
    })()`);
    ensure(checked, `没有选中 ${product} 对应素材`);
  }
  await clickText(".creator-tool-drawer button[aria-label='关闭']", "×");
  const filled = await evaluate(`(() => {
    const node=document.querySelector('.creator-composer textarea');
    if(!node)return false;
    const setter=Object.getOwnPropertyDescriptor(
      HTMLTextAreaElement.prototype,'value'
    ).set;
    setter.call(node,'让这两件登记商品形成清楚的视觉重音。');
    node.dispatchEvent(new Event('input',{bubbles:true}));
    return true;
  })()`);
  ensure(filled, "无法填写 P5 低种子");
  await clickText(".composer-submit button.primary", "生成内容");
  await waitFor(
    "Boolean(document.querySelector('.creator-artifact')) && Boolean(window.__ux03ProductMediaStreams?.[0]?.body)",
    "P5 原子成品",
    45000
  );
  const streamText = await evaluate(
    "window.__ux03ProductMediaStreams[0].body"
  );
  for (const line of streamText.split("\n").filter(Boolean)) {
    const event = JSON.parse(line);
    lifecycleEvents.push(event.event);
    if (event.event === "completed") taskId = event.result.task_id;
  }
  ensure(taskId, "P5 没有形成正式版本");
  const overflow = await evaluate(
    "document.documentElement.scrollWidth-document.documentElement.clientWidth"
  );
  ensure(overflow <= 1, "390px P5 旅程出现横向溢出");
  const unexpectedRequests = browserEvents
    .filter(event => event.method === "Network.requestWillBeSent")
    .map(event => event.params?.request?.url)
    .filter(
      url =>
        url &&
        !url.startsWith(baseUrl) &&
        !url.startsWith("data:") &&
        !url.startsWith("blob:")
    );
  ensure(
    unexpectedRequests.length === 0,
    `出现外部请求：${unexpectedRequests.join(",")}`
  );
  const consoleErrors = browserEvents.filter(
    event =>
      event.method === "Runtime.exceptionThrown" ||
      (event.method === "Log.entryAdded" &&
        event.params?.entry?.level === "error")
  );
  ensure(consoleErrors.length === 0, "浏览器出现控制台错误");
} catch (error) {
  failures.push(error instanceof Error ? error.message : String(error));
} finally {
  try {
    socket?.close();
  } catch {
    // Best effort only.
  }
  chrome.kill("SIGTERM");
  await wait(100);
  rmSync(profile, { recursive: true, force: true });
}

console.log(
  JSON.stringify({
    failures,
    task_id: taskId,
    lifecycle_events: lifecycleEvents
  })
);
process.exitCode = failures.length ? 1 : 0;
