import { spawn } from "node:child_process";
import { existsSync, mkdtempSync, rmSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const required = name => {
  const value = process.env[name];
  if (!value) throw new Error(`缺少 ${name}`);
  return value;
};
const baseUrl = required("UX03_GATE_D_BASE_URL").replace(/\/$/, "");
const username = required("UX03_GATE_D_USERNAME");
const password = required("UX03_GATE_D_PASSWORD");
const repo = resolve(new URL("../..", import.meta.url).pathname);
const chromePath = [
  process.env.UX03_CHROME,
  "/usr/bin/google-chrome",
  "/usr/bin/chromium",
  "/home/faye/.cache/puppeteer/chrome/linux-148.0.7778.97/chrome-linux64/chrome"
]
  .filter(Boolean)
  .find(path => existsSync(path) && statSync(path).isFile());
if (!chromePath) throw new Error("未找到本机 Chrome");
const { default: WebSocket } = await import(
  pathToFileURL(join(repo, "frontend", "node_modules", "ws", "index.js")).href
);
const profile = mkdtempSync(join(tmpdir(), "ux03-gate-d-browser-"));
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
const wait = milliseconds => new Promise(resolvePromise => setTimeout(resolvePromise, milliseconds));
const ensure = (value, message) => {
  if (!value) throw new Error(message);
};
const results = [];
const failures = [];
const record = (name, detail) => results.push({ name, status: "PASS", detail });
let socket;

try {
  const websocketUrl = await new Promise((resolvePromise, reject) => {
    let buffer = "";
    const timer = setTimeout(() => reject(new Error("Chrome DevTools 启动超时")), 10000);
    chrome.stderr.on("data", chunk => {
      buffer += chunk.toString();
      const match = buffer.match(/DevTools listening on (ws:\/\/[^\s]+)/);
      if (match) {
        clearTimeout(timer);
        resolvePromise(match[1]);
      }
    });
    chrome.once("exit", code => reject(new Error(`Chrome 提前退出 ${code}`)));
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
      socket.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
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
    "Browser.grantPermissions",
    { permissions: ["clipboardReadWrite"], origin: baseUrl, browserContextId: context.browserContextId }
  );
  const evaluate = async expression => {
    const response = await send(
      "Runtime.evaluate",
      { expression, awaitPromise: true, returnByValue: true },
      sessionId
    );
    if (response.exceptionDetails) throw new Error(JSON.stringify(response.exceptionDetails));
    return response.result?.value;
  };
  const waitFor = async (expression, label, timeout = 20000) => {
    const started = Date.now();
    while (Date.now() - started < timeout) {
      try {
        if (await evaluate(expression)) return;
      } catch {
        // Navigation may briefly replace the execution context.
      }
      await wait(100);
    }
    const body = await evaluate("document.body?.innerText.slice(0,1600) ?? ''");
    throw new Error(`等待超时：${label}；页面：${body}`);
  };
  const navigate = async path => {
    await send("Page.navigate", { url: `${baseUrl}${path}` }, sessionId);
    await waitFor("document.readyState === 'complete'", `加载 ${path}`);
  };
  const fill = async (selector, value) => {
    const changed = await evaluate(`(() => {
      const node=document.querySelector(${JSON.stringify(selector)});
      if(!node)return false;
      const owner=node.tagName==='TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(owner,'value').set.call(node,${JSON.stringify(value)});
      node.dispatchEvent(new Event('input',{bubbles:true}));
      node.dispatchEvent(new Event('change',{bubbles:true}));
      return true;
    })()`);
    ensure(changed, `找不到输入控件 ${selector}`);
  };
  const click = async (selector, text) => {
    const clicked = await evaluate(`(() => {
      const nodes=[...document.querySelectorAll(${JSON.stringify(selector)})];
      const node=${text === undefined
        ? "nodes[0]"
        : `nodes.find(item=>item.textContent.trim().includes(${JSON.stringify(text)}))`};
      if(!node)return {ok:false,items:nodes.map(item=>item.textContent.trim())};
      node.scrollIntoView({block:'center',inline:'nearest'});
      node.click();
      return {ok:true};
    })()`);
    ensure(clicked?.ok, `无法点击 ${text ?? selector}：${JSON.stringify(clicked)}`);
    await wait(100);
  };
  const viewport = async (width, height, scale = 1) => {
    await send(
      "Emulation.setDeviceMetricsOverride",
      { width, height, deviceScaleFactor: 1, mobile: width <= 640, scale },
      sessionId
    );
    await send("Emulation.setPageScaleFactor", { pageScaleFactor: scale }, sessionId);
    await wait(100);
    const result = await evaluate(`(() => {
      const root=document.documentElement;
      const visible=node=>getComputedStyle(node).display!=='none' && getComputedStyle(node).visibility!=='hidden' && node.getBoundingClientRect().height>0;
      const targets=[...document.querySelectorAll('button,a,input,textarea')].filter(visible);
      return {
        overflow:root.scrollWidth-root.clientWidth,
        shortPrimary:[...document.querySelectorAll('button.primary')]
          .filter(visible).some(node=>node.getBoundingClientRect().height<44),
        tinyMobile:innerWidth<=640 ? targets
          .filter(node=>node.tagName==='BUTTON' && node.getBoundingClientRect().height<44)
          .map(node=>({text:node.textContent.trim(),height:node.getBoundingClientRect().height})) : []
      };
    })()`);
    ensure(result.overflow <= 1, `${width}px/${scale}x 页面出现横向溢出`);
    ensure(!result.shortPrimary, `${width}px/${scale}x 主动作小于 44px`);
    ensure(result.tinyMobile.length === 0, `${width}px 移动按钮小于 44px：${JSON.stringify(result.tinyMobile)}`);
  };

  await viewport(1440, 900);
  await navigate("/login");
  await fill('input[name="username"]', username);
  await fill('input[name="password"]', password);
  await click('button[type="submit"]', "登录");
  await waitFor("location.pathname==='/user'", "正式租户用户入口");
  await click("a,button", "陈列搭配");
  await waitFor("Boolean(location.pathname.startsWith('/display') && document.querySelector('#display-inventory'))", "正式陈列入口");

  for (const label of ["Gate D 上装", "Gate D 下装", "资料待补商品"]) {
    await click(".display-product-picker button", label);
  }
  const inventory = await evaluate("document.querySelector('#display-inventory').value");
  ensure(inventory.includes("GD-UP-01") && inventory.includes("GD-LOW-01"), "商品选择没有写入本次库存");
  await fill("#display-inventory", "GD-UP-01 3 件、GD-LOW-01 3 件、GD-PENDING-01 2 件。");
  await click(".display-composer button.primary", "生成参考方案");
  await waitFor("document.querySelector('.display-artifact')?.innerText.includes('当前版本 · V1')", "生成 V1");
  const v1Body = await evaluate("document.querySelector('.display-plan-text')?.innerText ?? ''");
  ensure(v1Body.includes("逐商品库存对账"), "V1 正文没有逐商品库存对账");
  ensure(v1Body.includes("只计入库存对账"), "缺属性商品没有诚实说明暂不上墙");
  ensure(!/AIGC|示意图|效果图|确认人|已采用/.test(v1Body), "DM01 出现越界措辞");
  record("正式商品与规则生成 V1", { version: 1, inventory_preserved: true });

  await fill("#display-feedback", "右侧上杆 GD-UP-01 太挤，请减少一件；其他内容不变。");
  await click(".display-revision button.primary", "生成 V2");
  await waitFor("document.querySelector('.display-artifact')?.innerText.includes('当前版本 · V2')", "生成 V2");
  const v2Body = await evaluate("document.querySelector('.display-plan-text')?.innerText ?? ''");
  ensure(v2Body.includes("减少 1 件"), "V2 没有体现局部减少");

  await click(".display-version-history summary", "历史版本");
  await click(".display-version-history button", "阅读 V1");
  await waitFor("document.querySelector('.display-artifact')?.innerText.includes('历史版本 · V1')", "回读 V1");
  await click(".display-artifact-heading button", "复制");
  await waitFor("document.body.innerText.includes('已复制 V1')", "复制历史 V1");
  await click(".history-reading button", "回到当前版");
  await waitFor("document.querySelector('.display-artifact')?.innerText.includes('当前版本 · V2')", "返回当前 V2");
  await click(".display-artifact-heading button", "复制");
  await waitFor("document.body.innerText.includes('已复制 V2')", "复制当前 V2");
  record("V1→V2→V1→当前 V2 与复制", { current: 2, immutable_v1: v1Body !== v2Body });

  await fill("#display-feedback", "中间看起来再轻一点。");
  await click(".display-revision button.primary", "生成 V3");
  await waitFor("document.body.innerText.includes('请在一段话中说明要减少的商品')", "模糊修改自然提示");
  ensure(
    await evaluate("document.querySelector('.display-artifact')?.innerText.includes('当前版本 · V2')"),
    "失败提示后已有 V2 丢失"
  );
  ensure(
    (await evaluate("document.querySelector('#display-feedback').value")).includes("中间看起来"),
    "失败提示后输入丢失"
  );
  record("失败恢复", { current_version_preserved: 2, input_preserved: true });

  for (const [width, height, scale] of [
    [1440, 900, 1],
    [768, 900, 1],
    [390, 844, 1],
    [768, 900, 2]
  ]) {
    await viewport(width, height, scale);
  }
  await viewport(390, 844);
  const tabs = await evaluate("[...document.querySelectorAll('.display-mobile-tabs button')].map(node=>node.textContent.trim())");
  ensure(JSON.stringify(tabs) === JSON.stringify(["对话", "方案"]), "移动端不再是对话/方案两个主视图");
  await click(".display-mobile-tabs button", "对话");
  const focused = await evaluate(`(() => {
    const node=document.querySelector('.display-mobile-tabs button.active');
    node.focus();
    const style=getComputedStyle(node);
    return document.activeElement===node && (style.outlineStyle!=='none' || style.boxShadow!=='none');
  })()`);
  ensure(focused, "主要输入控件缺少可见键盘焦点");
  record("响应式、触控与键盘", { viewports: ["1440x900", "768x900", "390x844", "200%"] });

  await navigate("/status");
  await waitFor("document.body.innerText.includes('核心服务') && document.body.innerText.includes('内容生成')", "公共状态页");
  ensure(
    await evaluate("document.body.innerText.includes('纯文字陈列参考方案')"),
    "状态页没有独立展示纯文字陈列能力"
  );
  ensure(
    !(await evaluate("/DeepSeek|API|S3|schema|database/i.test(document.body.innerText)")),
    "状态页泄露内部依赖或供应商"
  );
  await click("button", "重新检查");
  record("公共状态页", { separated_surfaces: 3, request_is_observational: true });

  const unexpectedRequests = browserEvents
    .filter(event => event.method === "Network.requestWillBeSent")
    .map(event => event.params?.request?.url)
    .filter(url => url && !url.startsWith(baseUrl) && !url.startsWith("data:") && !url.startsWith("blob:"));
  ensure(unexpectedRequests.length === 0, `出现非必要外部请求：${unexpectedRequests.join(",")}`);
  const consoleErrors = browserEvents.filter(
    event =>
      event.method === "Runtime.exceptionThrown" ||
      (event.method === "Log.entryAdded" && event.params?.entry?.level === "error")
  );
  ensure(consoleErrors.length === 0, "浏览器出现控制台错误");
  record("浏览器边界", { external_requests: 0, console_errors: 0 });
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

console.log(JSON.stringify({ results, failures }));
process.exitCode = failures.length ? 1 : 0;
