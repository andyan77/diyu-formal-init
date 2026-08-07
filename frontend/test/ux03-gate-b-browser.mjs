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
const baseUrl = required("UX03_GATE_B_BASE_URL").replace(/\/$/, "");
const username = required("UX03_GATE_B_USERNAME");
const password = required("UX03_GATE_B_PASSWORD");
const repo = resolve(new URL("../..", import.meta.url).pathname);
const chromePath = resolveChromePath({ configured: process.env.UX03_CHROME });
if (!chromePath) throw new Error("未找到本机 Chrome");
const { default: WebSocket } = await import(
  pathToFileURL(join(repo, "frontend", "node_modules", "ws", "index.js")).href
);
const profile = mkdtempSync(join(tmpdir(), "ux03-gate-b-browser-"));
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
const results = [];
const failures = [];
const record = (name, detail) => results.push({ name, status: "PASS", detail });
let socket;

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
  const waitFor = async (expression, label, timeout = 20000) => {
    const started = Date.now();
    while (Date.now() - started < timeout) {
      try {
        if (await evaluate(expression)) return;
      } catch {
        // Navigation may briefly remove the current execution context.
      }
      await wait(100);
    }
    const body = await evaluate("document.body?.innerText.slice(0,1200) ?? ''");
    throw new Error(`等待超时：${label}；页面：${body}`);
  };
  const navigate = async path => {
    await send("Page.navigate", { url: `${baseUrl}${path}` }, sessionId);
    await waitFor(`document.readyState === 'complete' && !document.querySelector('.page-loading')`, `加载 ${path}`);
  };
  const fill = async (selector, value) => {
    const changed = await evaluate(`(() => {
      const node=document.querySelector(${JSON.stringify(selector)});
      if(!node)return false;
      const owner=node.tagName==='TEXTAREA'
        ? HTMLTextAreaElement.prototype
        : HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(owner,'value').set.call(
        node,${JSON.stringify(value)}
      );
      node.dispatchEvent(new Event('input',{bubbles:true}));
      node.dispatchEvent(new Event('change',{bubbles:true}));
      return true;
    })()`);
    ensure(changed, `找不到输入控件 ${selector}`);
  };
  const labeledControl = async (label, selector, value) => {
    const changed = await evaluate(`(() => {
      const wrapper=[...document.querySelectorAll('.tenant-drawer label')]
        .find(node=>node.textContent.trim().startsWith(${JSON.stringify(label)}));
      const control=wrapper?.querySelector(${JSON.stringify(selector)});
      if(!control)return false;
      if(control.tagName==='SELECT'){
        const option=[...control.options].find(
          item=>item.textContent.includes(${JSON.stringify(value)})
        );
        if(!option)return false;
        Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value')
          .set.call(control,option.value);
      }else{
        const owner=control.tagName==='TEXTAREA'
          ? HTMLTextAreaElement.prototype
          : HTMLInputElement.prototype;
        Object.getOwnPropertyDescriptor(owner,'value').set.call(
          control,${JSON.stringify(value)}
        );
      }
      control.dispatchEvent(new Event('input',{bubbles:true}));
      control.dispatchEvent(new Event('change',{bubbles:true}));
      return true;
    })()`);
    ensure(changed, `无法设置 ${label}`);
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
    await wait(120);
  };
  const clickIn = async (containerSelector, containerText, buttonText) => {
    const clicked = await evaluate(`(() => {
      const container=[...document.querySelectorAll(${JSON.stringify(containerSelector)})]
        .find(node=>node.textContent.includes(${JSON.stringify(containerText)}));
      const button=[...(container?.querySelectorAll('button')??[])]
        .find(node=>node.textContent.includes(${JSON.stringify(buttonText)}));
      if(!button)return false;
      button.scrollIntoView({block:'center',inline:'nearest'});
      button.click();
      return true;
    })()`);
    ensure(clicked, `无法在 ${containerText} 中点击 ${buttonText}`);
    await wait(120);
  };
  const toggleLabel = async label => {
    const selected = await evaluate(`(() => {
      const wrapper=[...document.querySelectorAll('.tenant-drawer label')]
        .find(node=>node.textContent.includes(${JSON.stringify(label)}));
      const input=wrapper?.querySelector('input[type=checkbox],input[type=radio]');
      if(!input)return false;
      input.click();
      return input.checked;
    })()`);
    ensure(selected, `无法选择 ${label}`);
  };
  const viewport = async (width, height) => {
    await send(
      "Emulation.setDeviceMetricsOverride",
      { width, height, deviceScaleFactor: 1, mobile: width <= 640 },
      sessionId
    );
    await wait(120);
    const result = await evaluate(`(() => {
      const root=document.documentElement;
      const primary=[...document.querySelectorAll('button.primary')]
        .filter(node=>getComputedStyle(node).display!=='none');
      return {
        overflow:root.scrollWidth-root.clientWidth,
        shortPrimary:primary.some(node=>node.getBoundingClientRect().height<44)
      };
    })()`);
    ensure(result.overflow <= 1, `${width}px 页面出现横向溢出`);
    ensure(!result.shortPrimary, `${width}px 主动作小于 44px`);
  };

  await viewport(1440, 900);
  await navigate("/tenant-admin/login");
  await fill('input[name="username"]', username);
  await fill('input[name="password"]', password);
  await click('button[type="submit"]', "登录");
  await waitFor(
    "location.pathname==='/tenant-admin' && document.body.innerText.includes('品牌资料库')",
    "正式管理员入口"
  );
  await click("nav button", "品牌资料库");
  await waitFor(
    "document.body.innerText.includes('华东门店表达参考')",
    "读取正式资料"
  );

  await click("button", "新增资料");
  await labeledControl("资料名称", "input", "浏览器确认的品牌参考");
  await labeledControl("粘贴文字资料", "textarea", "只使用已确认来源，避免扩大事实。");
  await labeledControl("自然来源说明", "textarea", "浏览器 synthetic 管理员确认");
  await labeledControl("可用范围", "select", "指定区域");
  await toggleLabel("华东区域");
  await click(".tenant-drawer button.primary", "查看导入预览");
  await waitFor(
    "document.querySelector('.tenant-drawer')?.innerText.includes('尚未保存')",
    "文字资料导入预览"
  );
  await click(".tenant-drawer button.primary", "确认保存为当前版本");
  await waitFor(
    "document.body.innerText.includes('浏览器确认的品牌参考')",
    "正式资料确认保存"
  );
  await clickIn(
    ".library-list article",
    "浏览器确认的品牌参考",
    "查看版本与维护"
  );
  await labeledControl("新版本标记", "input", "V2");
  await labeledControl(
    "文字内容",
    "textarea",
    "只使用已确认来源，并明确当前适用区域。"
  );
  await click(".tenant-drawer button.primary", "保存新版本");
  await waitFor(
    "document.body.innerText.includes('已保存新版本')",
    "资料 V2 保存"
  );
  await click(".tenant-drawer button", "停用资料");
  await waitFor(
    "document.querySelector('.tenant-drawer')?.innerText.includes('已停用')",
    "资料停用"
  );
  await click(".tenant-drawer button", "恢复资料");
  await click(".tenant-drawer button", "关闭");
  record("品牌文字资料正式生命周期", { preview: true, versions: 2 });

  await clickIn(".product-list article", "EAST-01", "查看版本与维护");
  await waitFor(
    "document.querySelector('.tenant-drawer')?.innerText.includes('历史版本')",
    "商品版本历史"
  );
  await click(".tenant-drawer button.primary", "查看字段预览");
  await waitFor(
    "document.body.innerText.includes('字段预览已通过')",
    "商品字段预览"
  );
  await toggleLabel("我确认这些是当前品牌可负责的商品事实");
  await click(".tenant-drawer button.primary", "保存新版本");
  await waitFor(
    "!document.querySelector('.tenant-drawer')",
    "商品新版本保存"
  );
  await clickIn(".product-list article", "EAST-01", "查看版本与维护");
  await click(".tenant-drawer button", "停用商品事实");
  await waitFor(
    "document.querySelector('.tenant-drawer')?.innerText.includes('已停用')",
    "商品停用"
  );
  await click(".tenant-drawer button", "恢复商品事实");
  await click(".tenant-drawer button", "关闭");
  record("商品事实正式生命周期", { field_preview: true, restored: true });

  await clickIn(
    ".material-list article",
    "华东门店官方环境说明",
    "查看版本与维护"
  );
  await labeledControl(
    "人工说明",
    "textarea",
    "浏览器复核后的官方素材说明"
  );
  await click(".tenant-drawer button.primary", "保存新版本");
  await waitFor(
    "document.body.innerText.includes('素材说明与范围已保存为新版本')",
    "素材说明新版本"
  );
  await click(".tenant-drawer button", "停用素材");
  await waitFor(
    "document.querySelector('.tenant-drawer')?.innerText.includes('已停用')",
    "素材停用"
  );
  await click(".tenant-drawer button", "恢复素材");
  await click(".tenant-drawer button", "关闭");
  record("组织官方素材正式生命周期", { explicit_selection_boundary: true });

  await click("nav button", "团队使用");
  await waitFor(
    "document.body.innerText.includes('有实际产品动作')",
    "团队使用固定口径"
  );
  await click(".period-switch button", "近 30 日");
  await waitFor(
    "[...document.querySelectorAll('.period-switch button')].find(node=>node.textContent.includes('30'))?.getAttribute('aria-pressed')==='true'",
    "30 日统计"
  );
  record("团队使用 7/30 日", { distinct_login_and_product_action: true });

  await click("nav button", "当前可用与待补");
  await waitFor(
    "document.querySelectorAll('[aria-labelledby=software-readiness-title] .readiness-list article').length===6",
    "六类能力诊断"
  );
  ensure(
    await evaluate(
      "document.body.innerText.includes('明确冲突') && document.body.innerText.includes('不受影响')"
    ),
    "诊断缺少冲突或不受影响边界"
  );
  record("六类工作就绪诊断", { count: 6, bounded_gaps: true });

  for (const [width, height] of [
    [1440, 900],
    [768, 900],
    [390, 844]
  ]) {
    await viewport(width, height);
  }
  const focus = await evaluate(`(() => {
    const button=[...document.querySelectorAll('button')].find(
      node=>getComputedStyle(node).display!=='none'
    );
    button?.focus();
    const style=button ? getComputedStyle(button) : null;
    return Boolean(
      button && document.activeElement===button &&
      (style.outlineStyle!=='none' || style.boxShadow!=='none')
    );
  })()`);
  ensure(focus, "键盘焦点不可见");
  const badRequests = browserEvents
    .filter(event => event.method === "Network.requestWillBeSent")
    .map(event => event.params?.request?.url)
    .filter(
      url =>
        url &&
        !url.startsWith(baseUrl) &&
        !url.startsWith("data:") &&
        !url.startsWith("blob:")
    );
  ensure(badRequests.length === 0, `出现外部请求：${badRequests.join(",")}`);
  const consoleErrors = browserEvents.filter(
    event =>
      event.method === "Runtime.exceptionThrown" ||
      (event.method === "Log.entryAdded" &&
        event.params?.entry?.level === "error")
  );
  ensure(consoleErrors.length === 0, "浏览器出现控制台错误");
  record("三视口、键盘与网络边界", {
    viewports: ["1440x900", "768x900", "390x844"],
    external_requests: 0
  });
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
