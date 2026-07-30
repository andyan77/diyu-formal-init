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
const baseUrl = required("UX03_GATE_C_BASE_URL").replace(/\/$/, "");
const sessionToken = required("UX03_GATE_C_SESSION_TOKEN");
const accountId = required("UX03_GATE_C_ACCOUNT_ID");
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
const profile = mkdtempSync(join(tmpdir(), "ux03-gate-c-browser-"));
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
const createdTaskIds = [];
const lifecycleEvents = [];
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
  await send(
    "Page.addScriptToEvaluateOnNewDocument",
    {
      source: `(() => {
        const original = window.fetch.bind(window);
        window.__ux03Streams = [];
        window.fetch = async (...args) => {
          const response = await original(...args);
          const raw = typeof args[0] === "string" ? args[0] : args[0]?.url ?? "";
          if (String(raw).includes("/api/v1/content/stream")) {
            const captured = { body: null, error: null };
            window.__ux03Streams.push(captured);
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
  await send(
    "Network.setCookie",
    {
      name: "diyu_session",
      value: sessionToken,
      url: baseUrl,
      path: "/",
      httpOnly: true,
      secure: false,
      sameSite: "Lax"
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
        // Navigation may briefly replace the execution context.
      }
      await wait(100);
    }
    const body = await evaluate("document.body?.innerText.slice(0,1600) ?? ''");
    throw new Error(`等待超时：${label}；页面：${body}`);
  };
  const viewport = async (width, height) => {
    await send(
      "Emulation.setDeviceMetricsOverride",
      { width, height, deviceScaleFactor: 1, mobile: width <= 640 },
      sessionId
    );
    await wait(100);
    const value = await evaluate(`(() => ({
      overflow: document.documentElement.scrollWidth -
        document.documentElement.clientWidth,
      shortPrimary: [...document.querySelectorAll('button.primary')]
        .filter(node =>
          getComputedStyle(node).display !== 'none' &&
          node.getClientRects().length > 0
        )
        .filter(node => node.getBoundingClientRect().height < 44)
        .map(node => ({
          text: node.textContent.trim(),
          height: node.getBoundingClientRect().height
        }))
    }))()`);
    ensure(value.overflow <= 1, `${width}px 出现页面级横向溢出`);
    ensure(
      value.shortPrimary.length === 0,
      `${width}px 实心主动作小于 44px：${JSON.stringify(value.shortPrimary)}`
    );
  };
  const click = async (selector, text) => {
    const value = await evaluate(`(() => {
      const nodes=[...document.querySelectorAll(${JSON.stringify(selector)})]
        .filter(node => getComputedStyle(node).display !== 'none');
      const node=${text === undefined
        ? "nodes[0]"
        : `nodes.find(item => item.textContent.trim().includes(${JSON.stringify(text)}))`};
      if(!node)return {ok:false,items:nodes.map(item=>item.textContent.trim())};
      node.scrollIntoView({block:'center',inline:'nearest'});
      node.click();
      return {ok:true};
    })()`);
    ensure(value?.ok, `无法点击 ${text ?? selector}：${JSON.stringify(value)}`);
    await wait(120);
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
  const clickAxis = async (label, text) => {
    const clicked = await evaluate(`(() => {
      const axis=[...document.querySelectorAll('.direction-axis')]
        .find(node=>node.querySelector('legend')?.textContent.includes(${JSON.stringify(label)}));
      const button=[...(axis?.querySelectorAll('button')??[])]
        .find(node=>node.textContent.includes(${JSON.stringify(text)}));
      if(!button)return false;
      button.click();
      return true;
    })()`);
    ensure(clicked, `无法在 ${label} 选择 ${text}`);
    await wait(100);
  };
  const clickFirstAxisOption = async label => {
    const clicked = await evaluate(`(() => {
      const axis=[...document.querySelectorAll('.direction-axis')]
        .find(node=>node.querySelector('legend')?.textContent.includes(${JSON.stringify(label)}));
      const button=[...(axis?.querySelectorAll('.direction-options button')??[])]
        .find(node=>!node.classList.contains('quiet-choice'));
      if(!button)return false;
      button.click();
      return true;
    })()`);
    ensure(clicked, `无法在 ${label} 选择常用项`);
    await wait(100);
  };

  await viewport(1440, 900);
  await send(
    "Page.navigate",
    {
      url: `${baseUrl}/content?publishing_identity_id=${accountId}&target=xiaohongshu_graphic`
    },
    sessionId
  );
  await waitFor(
    "document.readyState==='complete' && Boolean(document.querySelector('.creator-composer textarea'))",
    "正式创作工作台"
  );
  await waitFor(
    "!document.querySelector('.direction-toggle')?.disabled",
    "创作控制加载"
  );
  ensure(
    !(await evaluate("Boolean(document.querySelector('.direction-panel'))")),
    "创作方向不应默认展开"
  );
  await click(".direction-toggle", "创作方向");
  await waitFor(
    "document.querySelectorAll('.direction-axis').length >= 3",
    "首屏创作方向"
  );
  await clickAxis("题材", "更多 / 搜索");
  const topicSearch = await evaluate(`(() => {
    const axis=[...document.querySelectorAll('.direction-axis')]
      .find(node=>node.querySelector('legend')?.textContent.includes('题材'));
    const input=axis?.querySelector('input[type=search]');
    if(!input)return null;
    input.setAttribute('data-ux03-topic-search','true');
    return true;
  })()`);
  ensure(topicSearch, "题材搜索入口不存在");
  await fill('input[data-ux03-topic-search="true"]', "婆媳");
  await clickAxis("题材", "婆媳");
  await clickFirstAxisOption("风格");
  await clickAxis("风格", "本次不使用");
  await click(".direction-content > button", "更多：讲法与系列互动");
  await waitFor(
    "document.querySelectorAll('.direction-axis').length === 5",
    "五轴创作方向"
  );
  await clickAxis("讲法", "更多 / 搜索");
  const mechanismSearch = await evaluate(`(() => {
    const axis=[...document.querySelectorAll('.direction-axis')]
      .find(node=>node.querySelector('legend')?.textContent.includes('讲法'));
    const input=axis?.querySelector('input[type=search]');
    if(!input)return null;
    input.setAttribute('data-ux03-search','true');
    return true;
  })()`);
  ensure(mechanismSearch, "讲法搜索入口不存在");
  await fill('input[data-ux03-search="true"]', "先用反差，再把选择留给读者");
  await clickAxis("讲法", "保留“先用反差");
  await fill(
    ".custom-direction input",
    "婆媳，不把任何一方写成反派"
  );
  ensure(
    await evaluate(
      "document.querySelector('.direction-toggle')?.innerText.includes('婆媳')"
    ),
    "开放方向没有形成可见本次状态"
  );
  record("五轴方向与开放自定义", {
    axes: 5,
    cleared_default: true,
    custom_preserved: true
  });

  const textareaFocus = await evaluate(`(() => {
    const node=document.querySelector('.creator-composer textarea');
    node?.focus();
    const style=node ? getComputedStyle(node) : null;
    return Boolean(node && document.activeElement===node &&
      (style.outlineStyle!=='none' || style.boxShadow!=='none'));
  })()`);
  ensure(textareaFocus, "创作输入焦点不可见");
  await fill(
    ".creator-composer textarea",
    "今天店里忙了一天，想写一条不把任何人写成反派的小红书。"
  );
  await click(".composer-submit button.primary", "生成内容");
  await waitFor(
    "Boolean(document.querySelector('.creator-artifact')) && Boolean(window.__ux03Streams?.[0]?.body)",
    "原子完整成品",
    40000
  );
  const streamText = await evaluate("window.__ux03Streams[0].body");
  for (const line of streamText.split("\n").filter(Boolean)) {
    const event = JSON.parse(line);
    lifecycleEvents.push(event.event);
    if (event.event === "completed") {
      createdTaskIds.push(event.result.task_id);
    }
  }
  ensure(
    JSON.stringify(lifecycleEvents) ===
      JSON.stringify([
        "received",
        "compiling_context",
        "generating",
        "validating",
        "finalizing",
        "completed"
      ]),
    `生命周期不准确：${JSON.stringify(lifecycleEvents)}`
  );
  const artifact = await evaluate(`(() => {
    const body=document.querySelector('.creator-artifact')?.innerText ?? '';
    return {
      hasTitle: Boolean(document.querySelector('.artifact-title h2')?.textContent.trim()),
      body,
      scopeCount: (body.match(/创作|推演|一般观察/g)??[]).length,
      oldBoilerplate: [
        '从你提供的片段出发',
        '沿着正文主线',
        '你更愿意带走哪一种理解'
      ].filter(value=>body.includes(value))
    };
  })()`);
  ensure(artifact.hasTitle, "成品缺少作品标题");
  ensure(artifact.oldBoilerplate.length === 0, "旧说明书式文案仍在成品中");
  ensure(
    artifact.body.includes("完整正文") &&
      artifact.body.includes("发布配文"),
    "stub 纵向缺少完整成品结构"
  );
  record("真实阶段与原子成品", {
    lifecycle: lifecycleEvents,
    task_count: createdTaskIds.length
  });

  await viewport(768, 900);
  await send(
    "Emulation.setPageScaleFactor",
    { pageScaleFactor: 2 },
    sessionId
  );
  const zoomOverflow = await evaluate(
    "document.documentElement.scrollWidth-document.documentElement.clientWidth"
  );
  ensure(zoomOverflow <= 1, "等效 200% 缩放出现页面级横向溢出");
  await send(
    "Emulation.setPageScaleFactor",
    { pageScaleFactor: 1 },
    sessionId
  );
  await viewport(390, 844);
  await waitFor(
    "document.querySelectorAll('.mobile-work-tabs button').length===2",
    "移动端对话/成品工作面"
  );
  await click(".mobile-work-tabs button", "对话");
  await click(".creator-composer .text-action", "另起一条");
  await click(".direction-toggle", "创作方向");
  await waitFor(
    "Boolean(document.querySelector('.direction-panel[role=dialog]'))",
    "移动端创作方向抽屉"
  );
  const drawerFocus = await evaluate(
    "document.activeElement===document.querySelector('.direction-panel [aria-label=\"关闭创作方向\"]')"
  );
  ensure(drawerFocus, "移动创作方向打开后焦点未进入抽屉");
  await send(
    "Input.dispatchKeyEvent",
    { type: "keyDown", key: "Escape", code: "Escape" },
    sessionId
  );
  await send(
    "Input.dispatchKeyEvent",
    { type: "keyUp", key: "Escape", code: "Escape" },
    sessionId
  );
  await waitFor(
    "!document.querySelector('.direction-panel')",
    "Escape 关闭创作方向"
  );
  ensure(
    await evaluate(
      "document.activeElement===document.querySelector('.direction-toggle')"
    ),
    "抽屉关闭后焦点没有返回真实触发控件"
  );
  const mobileTargets = await evaluate(`(() => {
    const selectors=[
      '.direction-toggle',
      '.composer-submit button.primary',
      '.mobile-work-tabs button'
    ];
    return selectors.flatMap(selector=>[...document.querySelectorAll(selector)])
      .filter(node=>getComputedStyle(node).display!=='none')
      .every(node=>node.getBoundingClientRect().height>=44);
  })()`);
  ensure(mobileTargets, "移动端主要触控目标小于 44px");
  record("三视口、缩放、移动与键盘", {
    viewports: ["1440x900", "768x900", "390x844"],
    zoom: "200%",
    mobile_tabs: ["对话", "成品"]
  });

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
    `出现非模型外部请求：${unexpectedRequests.join(",")}`
  );
  const consoleErrors = browserEvents.filter(
    event =>
      event.method === "Runtime.exceptionThrown" ||
      (event.method === "Log.entryAdded" &&
        event.params?.entry?.level === "error")
  );
  ensure(consoleErrors.length === 0, "浏览器出现控制台错误");
  record("浏览器边界", {
    console_errors: 0,
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

console.log(
  JSON.stringify({
    results,
    failures,
    lifecycle_events: lifecycleEvents,
    created_task_ids: createdTaskIds
  })
);
process.exitCode = failures.length ? 1 : 0;
