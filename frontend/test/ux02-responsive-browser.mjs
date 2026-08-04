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

const baseUrl = required("UX02_BASE_URL").replace(/\/$/, "");
const adminUsername = required("UX02_ADMIN_USERNAME");
const adminPassword = required("UX02_ADMIN_PASSWORD");
const userUsername = required("UX02_EXISTING_USER");
const userPassword = required("UX02_NEW_USER_PASSWORD");
const existingAccountId = required("UX02_EXISTING_ACCOUNT_ID");
const existingTarget = required("UX02_EXISTING_TARGET");
const repo = resolve(new URL("../..", import.meta.url).pathname);
const chromePath = resolveChromePath({ configured: process.env.UX02_CHROME });
if (!chromePath) throw new Error("未找到本机 Chrome");

const { default: WebSocket } = await import(
  pathToFileURL(join(repo, "frontend", "node_modules", "ws", "index.js")).href
);
const profile = mkdtempSync(join(tmpdir(), "ux02-responsive-browser-"));
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
    "--ignore-certificate-errors",
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
  const events = [];
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
    events.push(message);
  });
  const send = (method, params = {}, sessionId) =>
    new Promise((resolvePromise, reject) => {
      const id = ++callId;
      pending.set(id, { resolve: resolvePromise, reject });
      socket.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
    });

  const page = async () => {
    const context = await send("Target.createBrowserContext");
    const target = await send("Target.createTarget", {
      url: "about:blank",
      browserContextId: context.browserContextId
    });
    const { sessionId } = await send("Target.attachToTarget", {
      targetId: target.targetId,
      flatten: true
    });
    await send("Page.enable", {}, sessionId);
    await send("Runtime.enable", {}, sessionId);
    await send("Network.enable", {}, sessionId);
    const evaluate = async expression => {
      const response = await send(
        "Runtime.evaluate",
        { expression, awaitPromise: true, returnByValue: true },
        sessionId
      );
      if (response.exceptionDetails) throw new Error(JSON.stringify(response.exceptionDetails));
      return response.result?.value;
    };
    const viewport = async (width, height) => {
      await send(
        "Emulation.setDeviceMetricsOverride",
        { width, height, deviceScaleFactor: 1, mobile: width <= 640 },
        sessionId
      );
      await wait(100);
    };
    const waitFor = async (expression, label, timeout = 20000) => {
      const started = Date.now();
      while (Date.now() - started < timeout) {
        if (await evaluate(expression)) return;
        await wait(100);
      }
      const location = await evaluate("location.pathname + location.search");
      const body = await evaluate("document.body.innerText.slice(0, 500)");
      throw new Error(`等待超时：${label}；当前 ${location}；页面：${body}`);
    };
    const navigate = async path => {
      await send("Page.navigate", { url: `${baseUrl}${path}` }, sessionId);
      await waitFor("document.readyState === 'complete'", `加载 ${path}`);
    };
    const fill = async (selector, value) => {
      ensure(
        await evaluate(`(() => {
          const node=document.querySelector(${JSON.stringify(selector)});
          if(!node)return false;
          const owner=node.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;
          Object.getOwnPropertyDescriptor(owner,'value').set.call(node,${JSON.stringify(value)});
          node.dispatchEvent(new Event('input',{bubbles:true}));
          node.dispatchEvent(new Event('change',{bubbles:true}));
          return true;
        })()`),
        `找不到输入控件 ${selector}`
      );
    };
    const click = async (selector, text) => {
      ensure(
        await evaluate(`(() => {
          const node=[...document.querySelectorAll(${JSON.stringify(selector)})]
            .find(item=>item.textContent.trim().includes(${JSON.stringify(text)}));
          if(!node)return false;
          node.click();
          return true;
        })()`),
        `找不到可点击控件 ${selector}:${text}`
      );
      await wait(100);
    };
    return { context, sessionId, evaluate, viewport, waitFor, navigate, fill, click };
  };

  const admin = await page();
  await admin.viewport(390, 844);
  await admin.navigate("/tenant-admin/login");
  await admin.fill('input[name="username"]', adminUsername);
  await admin.fill('input[name="password"]', adminPassword);
  await admin.click('button[type="submit"]', "登录");
  await admin.waitFor("location.pathname === '/tenant-admin'", "管理员登录");
  await admin.click("button", "菜单");
  ensure(
    await admin.evaluate("document.activeElement === document.querySelector('.tenant-nav nav button')"),
    "移动管理菜单打开后焦点没有进入"
  );
  const adminNavigation = await admin.evaluate(
    "[...document.querySelectorAll('.tenant-nav nav button')].map(node=>node.textContent.trim())"
  );
  ensure(adminNavigation.length === 7, "移动管理菜单没有覆盖七个栏目");
  ensure(
    await admin.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"),
    "移动管理页面出现横向溢出"
  );
  await admin.click(".tenant-nav nav button", "团队使用");
  await admin.waitFor("document.body.innerText.includes('近 7 日')", "移动菜单进入团队使用");
  results.push("移动管理员七栏菜单、焦点和 390×844 布局");

  const user = await page();
  await user.viewport(390, 844);
  await user.navigate("/login");
  await user.fill('input[name="username"]', userUsername);
  await user.fill('input[name="password"]', userPassword);
  await user.click('button[type="submit"]', "登录");
  await user.waitFor("location.pathname === '/user'", "租户用户登录");
  await user.navigate(
    `/content?publishing_identity_id=${encodeURIComponent(existingAccountId)}&target=${encodeURIComponent(existingTarget)}`
  );
  await user.waitFor(
    "document.querySelector('textarea[aria-label=\"内容需求\"]') !== null",
    "移动创作工作台"
  );
  ensure(
    await user.evaluate(`["发布账号","平台","内容形式"].every(label=>{
      const node=document.querySelector('select[aria-label="'+label+'"]')?.closest('label')?.querySelector('span');
      return node && getComputedStyle(node).display!=='none' && node.getBoundingClientRect().height>0;
    })`),
    "移动账号、平台或形式缺少可见标签"
  );
  ensure(
    await user.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"),
    "移动创作页面出现横向溢出"
  );
  await user.evaluate("document.body.tabIndex=-1; document.body.focus()");
  let composerReachedByKeyboard = false;
  for (let index = 0; index < 24; index += 1) {
    await send(
      "Input.dispatchKeyEvent",
      { type: "keyDown", key: "Tab", code: "Tab", windowsVirtualKeyCode: 9 },
      user.sessionId
    );
    await send(
      "Input.dispatchKeyEvent",
      { type: "keyUp", key: "Tab", code: "Tab", windowsVirtualKeyCode: 9 },
      user.sessionId
    );
    if (
      await user.evaluate(
        "document.activeElement?.getAttribute('aria-label') === '内容需求'"
      )
    ) {
      composerReachedByKeyboard = true;
      break;
    }
  }
  ensure(composerReachedByKeyboard, "键盘不能到达创作输入");
  ensure(
    await user.evaluate(`(() => {
      const style=getComputedStyle(document.activeElement);
      return style.outlineStyle!=='none' || style.boxShadow!=='none';
    })()`),
    "创作输入焦点不可见"
  );
  await user.click("button", "创作方向（可选）");
  ensure(
    await user.evaluate(`(() => {
      const panel=document.querySelector('.direction-panel');
      return panel?.getAttribute('aria-modal')==='true'
        && getComputedStyle(panel).position==='fixed'
        && document.activeElement?.getAttribute('aria-label')==='关闭创作方向';
    })()`),
    "移动创作方向不是可聚焦底部抽屉"
  );
  await user.evaluate(`document.querySelector('.direction-panel').dispatchEvent(
    new KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true})
  )`);
  await user.waitFor("document.querySelector('.direction-panel') === null", "Escape 关闭方向抽屉");
  ensure(
    await user.evaluate("document.activeElement?.classList.contains('direction-toggle')"),
    "方向抽屉关闭后焦点没有返回"
  );
  await user.click(".composer-resource-actions button", "连续系列");
  ensure(
    await user.evaluate(
      "document.activeElement?.getAttribute('aria-label') === '关闭'"
    ),
    "系列抽屉打开后焦点没有进入"
  );
  await user.evaluate(`document.querySelector('.creator-tool-drawer').dispatchEvent(
    new KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true})
  )`);
  await user.waitFor("document.querySelector('.creator-tool-drawer') === null", "Escape 关闭系列抽屉");
  await user.waitFor(
    "document.querySelector('.creator-history nav button') !== null",
    "移动版本入口可读取的正式历史"
  );
  await user.evaluate("document.querySelector('.creator-history nav button').click()");
  await user.waitFor("document.querySelector('.creator-artifact') !== null", "移动历史成品");
  ensure(
    await user.evaluate(
      "getComputedStyle(document.querySelector('.mobile-work-tabs')).display === 'grid'"
    ),
    "移动创作端没有对话/成品两个工作面"
  );
  await user.click(".mobile-work-tabs button", "成品");
  ensure(
    await user.evaluate("document.querySelector('.artifact-workspace')?.classList.contains('mobile-hidden') === false"),
    "移动成品工作面不能打开"
  );
  await user.waitFor(
    "document.querySelector('.version-history summary') !== null",
    "移动版本历史完成读取"
  );
  await user.click(".version-history summary", "历史版本");
  ensure(
    await user.evaluate("document.querySelectorAll('.version-history button').length >= 1"),
    "移动端没有版本入口"
  );
  results.push("移动创作双工作面、方向/系列抽屉和可见焦点");

  await user.viewport(768, 900);
  ensure(
    await user.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"),
    "中间宽度出现横向溢出"
  );
  await user.viewport(720, 450);
  ensure(
    await user.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"),
    "等效 200% 缩放宽度出现横向溢出"
  );
  await send(
    "Emulation.setEmulatedMedia",
    { media: "screen", features: [{ name: "prefers-reduced-motion", value: "reduce" }] },
    user.sessionId
  );
  await user.navigate("/");
  ensure(
    await user.evaluate(`(() => {
      const node=document.querySelector('.home-message');
      const style=getComputedStyle(node);
      return parseFloat(style.animationDuration||'0') <= 0.001
        && parseFloat(style.transitionDuration||'0') <= 0.001;
    })()`),
    "减少动效偏好没有生效"
  );
  results.push("中间宽度、等效 200% 缩放和减少动效");

  const baseOrigin = new URL(baseUrl).origin;
  const external = events
    .filter(event => event.method === "Network.requestWillBeSent")
    .map(event => event.params?.request?.url)
    .filter(Boolean)
    .filter(url => {
      const parsed = new URL(url);
      return !["data:", "blob:"].includes(parsed.protocol) && parsed.origin !== baseOrigin;
    });
  ensure(external.length === 0, `出现意外外部请求：${external.join(", ")}`);
  const errors = events.filter(event => event.method === "Runtime.exceptionThrown");
  ensure(errors.length === 0, `浏览器运行错误：${JSON.stringify(errors)}`);
  results.push("无外部请求和浏览器运行错误");
} catch (error) {
  failures.push(error instanceof Error ? error.stack ?? error.message : String(error));
} finally {
  socket?.close();
  chrome.kill("SIGTERM");
  await Promise.race([
    new Promise(resolvePromise => chrome.once("exit", resolvePromise)),
    wait(2000)
  ]);
  rmSync(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
}

console.log(JSON.stringify({ results, failures }, null, 2));
if (failures.length) process.exit(1);
