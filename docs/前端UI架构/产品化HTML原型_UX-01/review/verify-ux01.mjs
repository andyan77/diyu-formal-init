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
  const declaredTotal = await evaluate("window.UX01_REVIEW.total");
  record("连续状态数量动态一致", allScenes.length === declaredTotal, { actual: allScenes.length, declared: declaredTotal });

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
        const visible=e=>e.offsetParent!==null&&!e.closest('[inert]');
        const controls=[...document.querySelectorAll('button,a,input,select,textarea,summary')].filter(visible);
        const small=controls.filter(e=>{
          const target=e.matches('input[type=radio]')?e.closest('label'):e;
          const r=target.getBoundingClientRect();return r.width<44||r.height<44;
        }).map(e=>(e.getAttribute('aria-label')||e.textContent||e.value||e.tagName).trim().slice(0,30));
        const dead=[...document.querySelectorAll('button,a')].filter(visible).filter(e=>
          e.tagName==='BUTTON'
            ? !e.matches('[data-go],[data-action],[data-view],[data-journey],[data-page],[data-prev],[data-next],[data-home],[data-desktop],[data-mobile]')
            : !e.hasAttribute('href')&&!e.hasAttribute('data-action')
        ).map(e=>e.textContent.trim().slice(0,30));
        const unsupported=[...document.querySelectorAll('[data-action]')].filter(visible)
          .filter(e=>!window.UX01_PRODUCT?.supportsAction(e.dataset.action))
          .map(e=>e.dataset.action);
        const scenes=new Set(${JSON.stringify(allScenes)});
        const badTargets=[...document.querySelectorAll('[data-go],a[href*="?scene="]')].filter(visible)
          .map(e=>e.dataset.go||new URL(e.href).searchParams.get('scene'))
          .filter(target=>target&&!scenes.has(target));
        const primary=[...document.querySelectorAll('.primary')].filter(visible).length;
        return {overflow:document.documentElement.scrollWidth>document.documentElement.clientWidth+1,small,dead,unsupported,badTargets,primary,title:document.title};
      })()`);
      if (layout.overflow) failures.push({ name: `${scene}@${width} 横向溢出`, detail: layout });
      if (layout.small.length) failures.push({ name: `${scene}@${width} 触控目标`, detail: layout.small });
      if (layout.dead.length) failures.push({ name: `${scene}@${width} 死控件`, detail: layout.dead });
      if (layout.unsupported.length) failures.push({ name: `${scene}@${width} 无动作消费者`, detail: layout.unsupported });
      if (layout.badTargets.length) failures.push({ name: `${scene}@${width} 无效场景目标`, detail: layout.badTargets });
      if (layout.primary > 1) failures.push({ name: `${scene}@${width} 主动作`, detail: layout.primary });
    }
    record(`${width}x${height} 全状态布局`, !failures.some((item) => item.name.includes(`@${width}`)), `${allScenes.length} scenes`);
  }
  await navigate(`${productBase}?scene=home`);
  await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-motion", value: "reduce" }] }, sessionId);
  const reduced = await evaluate(`getComputedStyle(document.querySelector('.home-mark')).animationDuration`);
  record("减少动效", parseFloat(reduced) <= 0.001, reduced);

  const wait = (milliseconds = 100) => new Promise((resolvePromise) => setTimeout(resolvePromise, milliseconds));
  const ensure = (value, message) => {
    if (!value) throw new Error(message);
  };
  const click = async (selector) => {
    const clicked = await evaluate(`(() => {
      const node=document.querySelector(${JSON.stringify(selector)});
      if(!node)return false;node.click();return true;
    })()`);
    ensure(clicked, `未找到可点击控件 ${selector}`);
    await wait();
  };
  const setValue = async (selector, value, eventName = "input") => {
    const changed = await evaluate(`(() => {
      const node=document.querySelector(${JSON.stringify(selector)});
      if(!node)return false;node.value=${JSON.stringify(value)};
      node.dispatchEvent(new Event(${JSON.stringify(eventName)},{bubbles:true}));return true;
    })()`);
    ensure(changed, `未找到输入控件 ${selector}`);
    await wait(30);
  };
  const sceneNow = () => evaluate("window.UX01_PRODUCT?.scene");
  const scenario = async (name, callback) => {
    try {
      const detail = await callback();
      record(name, true, detail || "passed");
    } catch (error) {
      record(name, false, error instanceof Error ? error.message : String(error));
    }
  };

  await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-motion", value: "no-preference" }] }, sessionId);
  await send("Emulation.setDeviceMetricsOverride", { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false }, sessionId);

  await scenario("裸产品公共认证旅程", async () => {
    await navigate(`${productBase}?scene=home`);
    await click("button.primary[data-go='login-user']");
    ensure(await sceneNow() === "login-user", "首页主动作未进入租户用户登录");
    await click("form button.primary");
    ensure(await sceneNow() === "creator-empty", "租户用户登录未进入创作工作台");
    return "首页 → 租户用户登录 → 创作工作台";
  });

  await scenario("错入口恢复与反向证明", async () => {
    await navigate(`${productBase}?scene=wrong-entry`);
    const label = await evaluate("document.querySelector('button.primary')?.textContent.trim()");
    ensure(label === "返回内容创作登录", `错入口动作文字不符：${label}`);
    await click("button.primary");
    const target = await sceneNow();
    ensure(target === "login-user", `错入口恢复目标为 ${target}`);
    ensure(target !== "login-admin", "错入口仍错误进入管理员登录");
    return "wrong-entry → login-user，且不是 login-admin";
  });

  await scenario("链接失效与会话过期恢复目标", async () => {
    for (const entry of ["link-expired", "session-expired"]) {
      await navigate(`${productBase}?scene=${entry}`);
      await click("button.primary");
      ensure(await sceneNow() === "login-user", `${entry} 未返回内容创作登录`);
    }
    return "两种恢复均进入 login-user";
  });

  await scenario("成员入口资格键盘互斥", async () => {
    await navigate(`${productBase}?scene=admin-member-qualify`);
    let values = await evaluate(`({
      user:document.querySelector('input[value="user"]').checked,
      fields:!document.querySelector('[data-user-qualification]').hidden
    })`);
    ensure(values.user && values.fields, "默认未选租户用户或工作字段未显示");
    await evaluate(`document.querySelector('input[value="admin"]').focus()`);
    await send("Input.dispatchKeyEvent", { type: "keyDown", key: " ", code: "Space", windowsVirtualKeyCode: 32 }, sessionId);
    await send("Input.dispatchKeyEvent", { type: "keyUp", key: " ", code: "Space", windowsVirtualKeyCode: 32 }, sessionId);
    await wait(60);
    values = await evaluate(`({
      admin:document.querySelector('input[value="admin"]').checked,
      hidden:document.querySelector('[data-user-qualification]').hidden,
      disabled:[...document.querySelectorAll('[data-user-field]')].every(e=>e.disabled),
      selected:[...document.querySelectorAll('[data-user-field]')].every(e=>e.selectedIndex===-1),
      message:!document.querySelector('[data-admin-qualification]').hidden
    })`);
    ensure(values.admin && values.hidden && values.disabled && values.selected && values.message, JSON.stringify(values));
    await evaluate(`document.querySelector('input[value="user"]').focus()`);
    await send("Input.dispatchKeyEvent", { type: "keyDown", key: " ", code: "Space", windowsVirtualKeyCode: 32 }, sessionId);
    await send("Input.dispatchKeyEvent", { type: "keyUp", key: " ", code: "Space", windowsVirtualKeyCode: 32 }, sessionId);
    await wait(60);
    ensure(await evaluate("!document.querySelector('[data-user-qualification]').hidden"), "键盘无法切回租户用户");
    return "默认用户 → 键盘切管理员 → 清空并禁用创作字段 → 键盘切回";
  });

  await scenario("管理员创建成员与本地激活", async () => {
    await navigate(`${productBase}?scene=admin-members`);
    await click("button[data-go='admin-member-create']");
    await click("button[data-go='admin-member-qualify']");
    await click("button[data-go='admin-activation']");
    const before = events.filter((item) => item.method === "Network.requestWillBeSent")
      .map((item) => item.params?.request?.url || "").filter((url) => /^https?:\/\//.test(url)).length;
    await click("a[data-action='activate-demo']");
    ensure(await sceneNow() === "activate", "演示激活链接没有进入本地 activate 场景");
    const after = events.filter((item) => item.method === "Network.requestWillBeSent")
      .map((item) => item.params?.request?.url || "").filter((url) => /^https?:\/\//.test(url)).length;
    ensure(after === before, "演示激活链接产生外部网络请求");
    return "成员 → 资格 → 完整链接 → 本地激活，无生产请求";
  });

  await scenario("创建发布账号形成结果", async () => {
    await navigate(`${productBase}?scene=admin-account`);
    await click("button[data-go='admin-account-create']");
    ensure(await sceneNow() === "admin-account-create", "创建账号仍跳到旧画像");
    const fields = await evaluate(`['账号名称','账号类型','负责组织','表达身份','初始平台目标'].every(t=>document.body.textContent.includes(t))`);
    ensure(fields, "创建账号字段不完整");
    await click("button[data-action='save-account']");
    ensure(await sceneNow() === "admin-account-created", "保存后未进入新账号结果");
    ensure(await evaluate("document.body.textContent.includes('柯桥门店日常')"), "结果未显示新账号");
    return "账号表单 → 保存 → 新账号详情";
  });

  await scenario("添加平台保持账号画像", async () => {
    await navigate(`${productBase}?scene=admin-platforms`);
    await click("button[data-action='open-platform-drawer']");
    ensure(await evaluate("document.querySelector('[role=dialog]')?.textContent.includes('只增加目标，不复制或切换账号画像')"), "平台抽屉未说明账号边界");
    await click("button[data-action='confirm-platform']");
    ensure(await evaluate("document.querySelector('[data-platform-list]').textContent.includes('微信视频号')"), "新增平台未回写账号卡");
    return "添加微信视频号 · 视频，账号画像不变";
  });

  await scenario("新增资料三级范围与区域条件", async () => {
    await navigate(`${productBase}?scene=admin-library-create`);
    ensure(await evaluate("document.querySelector('[data-region-choice]').hidden"), "区域选择不应默认显示");
    await setValue("[data-library-scope]", "region", "change");
    ensure(await evaluate("!document.querySelector('[data-region-choice]').hidden"), "指定区域未显示区域选择");
    await click("button[data-action='save-library']");
    ensure(await sceneNow() === "admin-library", "资料保存后未返回列表");
    const result = await evaluate("document.querySelector('[data-library-list]').textContent");
    ensure(result.includes("浙江区域门店拍摄补充") && result.includes("待处理"), "新增资料结果或状态缺失");
    return "品牌全员/总部/指定区域，指定区域出现选择并保存为 V1 待处理";
  });

  await scenario("团队使用 7/30 日真实切换", async () => {
    await navigate(`${productBase}?scene=admin-usage`);
    const before = await evaluate("document.querySelector('[data-usage-content]').textContent");
    await click("button[data-action='usage-30']");
    const after = await evaluate("document.querySelector('[data-usage-content]').textContent");
    ensure(before !== after && after.includes("近 30 日") && after.includes("96,320"), "30 日口径没有产生可见变化");
    await click("button[data-action='usage-7']");
    ensure(await evaluate("document.querySelector('[data-usage-content]').textContent.includes('近 7 日')"), "无法切回 7 日");
    return "口径、指标和成员摘要均变化";
  });

  await scenario("创作方向选择搜索自定义清除", async () => {
    await navigate(`${productBase}?scene=creator-compose`);
    const seed = "婆媳主题，但不要把任何一方写成反派。";
    await setValue(".composer textarea", seed);
    await click("button[data-action='open-directions']");
    ensure(await evaluate("document.querySelector('[role=dialog]')?.contains(document.activeElement)"), "抽屉打开后焦点未进入");
    await click("button[data-action='select-direction'][data-dimension='topic'][data-value='婆媳']");
    await click("button[data-action='show-direction-more'][data-dimension='style']");
    await setValue("input[data-direction-input='style']", "有一点冷幽默");
    await click("button[data-action='apply-direction-custom'][data-dimension='style']");
    await click("button[data-action='save-directions']");
    ensure(await evaluate("document.querySelector('[data-action=open-directions]').textContent.includes('2')"), "已选方向没有回到输入区");
    ensure(await evaluate(`document.querySelector('.composer textarea').value===${JSON.stringify(seed)}`), "方向操作丢失原输入");
    await click("button[data-action='open-directions']");
    await click("button[data-action='clear-directions']");
    await click("button[data-action='save-directions']");
    ensure(await evaluate("document.querySelector('[data-action=open-directions]').textContent.includes('可选')"), "无法清除本次方向");
    return "题材原样选择、更多/搜索、自然语言自定义、保存与清除";
  });

  await scenario("系列素材与账号画像均有消费者", async () => {
    await navigate(`${productBase}?scene=creator-compose`);
    const seed = await evaluate("document.querySelector('.composer textarea').value");
    await click("button[data-action='open-series']");
    await click("input[name='assist-choice'][value='门店日常']");
    await click("button[data-action='save-series']");
    ensure(await evaluate("document.querySelector('[data-action=open-series]').textContent.includes('门店日常')"), "系列选择无结果");
    await click("button[data-action='open-material']");
    await click("input[name='assist-choice'][value='今日门店照片']");
    await click("button[data-action='save-material']");
    ensure(await evaluate("document.querySelector('[data-action=open-material]').textContent.includes('今日门店照片')"), "素材选择无结果");
    await click("button[data-action='open-account-profile']");
    ensure(await evaluate("document.querySelector('[role=dialog]')?.textContent.includes('只读账号画像')"), "账号画像未打开");
    await click("button[data-action='close-drawer']");
    ensure(await evaluate(`document.querySelector('.composer textarea').value===${JSON.stringify(seed)}`), "辅助抽屉丢失输入");
    return "系列、素材、只读账号画像均有可见结果且不丢输入";
  });

  await scenario("内容 V1→V2→V1→当前 V2", async () => {
    await navigate(`${productBase}?scene=creator-v1`);
    ensure(!await evaluate("document.querySelector('.history').textContent.includes('V2')"), "V1 阶段提前显示未来 V2");
    await click("button[data-action='open-versions']");
    ensure(!await evaluate("document.querySelector('[role=dialog]').textContent.includes('V2')"), "V1 版本抽屉提前显示 V2");
    await click("button[data-action='close-drawer']");
    await setValue(".composer textarea", "别讲道理，荒诞一点。");
    await click(".composer button.primary");
    ensure(await sceneNow() === "creator-v2", "修改没有形成 V2");
    await click(".history button[data-go='creator-history-v1']");
    ensure(await sceneNow() === "creator-history-v1", "无法从历史侧栏回读 V1");
    ensure(await evaluate("document.querySelector('.artifact').dataset.viewedVersion==='1'"), "回读版本不是 V1");
    await click(".history-reading a");
    ensure(await sceneNow() === "creator-current", "无法回到当前 V2");
    return "V1 无未来版本 → 修改 V2 → 历史 V1 → 当前 V2";
  });

  await scenario("移动端版本入口与双工作面", async () => {
    await send("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 1, mobile: true }, sessionId);
    await navigate(`${productBase}?scene=creator-v2`);
    await click("button[data-view='artifact']");
    await click("button[data-action='open-versions']");
    await click("button[data-go='creator-history-v1']");
    ensure(await sceneNow() === "creator-history-v1", "移动版本入口未进入历史 V1");
    await click("button[data-action='open-versions']");
    await click("button[data-go='creator-current']");
    ensure(await sceneNow() === "creator-current", "移动版本入口未回到当前 V2");
    await click("button[data-view='conversation']");
    ensure(await evaluate("document.querySelector('.creator-grid').dataset.view==='conversation'"), "移动双工作面无法切回对话");
    return "移动成品 → 版本 → V1 → 当前 V2 → 对话";
  });

  await scenario("DM01 当前与历史标签", async () => {
    await send("Emulation.setDeviceMetricsOverride", { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false }, sessionId);
    await navigate(`${productBase}?scene=dm-entry`);
    await click("button[data-go='dm-input']");
    await click("button[data-go='dm-v1']");
    ensure(await evaluate("document.querySelector('[data-plan-identity=current]').textContent.includes('当前版 · V1')"), "V1 当前标签错误");
    await click("button[data-go='dm-v2']");
    ensure(await evaluate("document.querySelector('[data-plan-identity=current]').textContent.includes('当前版 · V2')"), "V2 当前标签错误");
    await click("button[data-go='dm-history']");
    const historical = await evaluate("document.querySelector('[data-plan-identity=history]').textContent");
    ensure(historical.includes("历史版 · V1") && historical.includes("当前版本仍为 V2"), "DM01 历史身份错误");
    return "当前 V1 → 当前 V2 → 历史 V1（当前仍为 V2）";
  });

  await scenario("真实 focus-visible 与抽屉焦点返回", async () => {
    await navigate(`${productBase}?scene=creator-compose`);
    const focus = async (selector) => evaluate(`(() => {
      const node=document.querySelector(${JSON.stringify(selector)});node.focus();
      const style=getComputedStyle(node);return {outline:style.outlineStyle,width:style.outlineWidth,shadow:style.boxShadow};
    })()`);
    const textarea = await focus(".composer textarea");
    ensure((textarea.outline !== "none" && parseFloat(textarea.width) > 0) || textarea.shadow !== "none", `textarea 焦点不可见 ${JSON.stringify(textarea)}`);
    const opener = "[data-action='open-directions']";
    await click(opener);
    ensure(await evaluate("document.querySelector('[role=dialog]').contains(document.activeElement)"), "焦点未进入抽屉");
    const closeStyle = await focus("[data-action='close-drawer']");
    ensure(closeStyle.outline !== "none" && parseFloat(closeStyle.width) > 0, "关闭按钮焦点不可见");
    await send("Input.dispatchKeyEvent", { type: "keyDown", key: "Escape", code: "Escape", windowsVirtualKeyCode: 27 }, sessionId);
    await send("Input.dispatchKeyEvent", { type: "keyUp", key: "Escape", code: "Escape", windowsVirtualKeyCode: 27 }, sessionId);
    await wait(60);
    ensure(await evaluate(`document.activeElement===document.querySelector(${JSON.stringify(opener)})`), "关闭抽屉后焦点未返回触发控件");
    return { textarea, closeStyle };
  });

  await scenario("移动管理员菜单七栏可达", async () => {
    await send("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 1, mobile: true }, sessionId);
    const expected = ["admin-overview", "admin-members", "admin-account", "admin-library", "admin-usage", "admin-readiness", "admin-security"];
    for (const targetScene of expected) {
      await navigate(`${productBase}?scene=admin-overview`);
      await click("button[data-action='open-admin-menu']");
      const count = await evaluate("document.querySelectorAll('.drawer-nav a').length");
      ensure(count === 7, `移动菜单只有 ${count} 项`);
      await click(`.drawer-nav a[href="?scene=${targetScene}"]`);
      await wait(80);
      ensure(await sceneNow() === targetScene, `移动菜单无法到达 ${targetScene}`);
    }
    await navigate(`${productBase}?scene=admin-overview`);
    await evaluate("document.querySelector(\"button[data-action='open-admin-menu']\").focus()");
    await send("Input.dispatchKeyEvent", { type: "keyDown", key: " ", code: "Space", windowsVirtualKeyCode: 32 }, sessionId);
    await send("Input.dispatchKeyEvent", { type: "keyUp", key: " ", code: "Space", windowsVirtualKeyCode: 32 }, sessionId);
    await wait(60);
    ensure(await evaluate("Boolean(document.querySelector('[role=dialog]'))"), "键盘无法打开移动管理员菜单");
    await evaluate("document.querySelector(\".drawer-nav a[href='?scene=admin-security']\").focus()");
    await send("Input.dispatchKeyEvent", { type: "keyDown", key: "Enter", code: "Enter", windowsVirtualKeyCode: 13 }, sessionId);
    await send("Input.dispatchKeyEvent", { type: "keyUp", key: "Enter", code: "Enter", windowsVirtualKeyCode: 13 }, sessionId);
    await wait(80);
    ensure(await sceneNow() === "admin-security", "键盘无法从移动菜单进入账户安全");
    return "概览、成员、账号、资料、使用、诊断、安全 7/7；键盘可打开并进入";
  });

  const consoleErrors = events.filter((event) => event.method === "Runtime.exceptionThrown" || (event.method === "Runtime.consoleAPICalled" && event.params?.type === "error"));
  record("无控制台错误", consoleErrors.length === 0, consoleErrors.length);
  const external = events.filter((event) => event.method === "Network.requestWillBeSent")
    .map((event) => event.params?.request?.url || "")
    .filter((url) => /^https?:\/\//.test(url));
  record("无外部网络请求", external.length === 0, external);
} finally {
  if (socket?.readyState === WebSocket.OPEN) socket.close();
  if (chrome.exitCode === null) {
    chrome.kill("SIGTERM");
    await Promise.race([
      new Promise((resolvePromise) => chrome.once("exit", resolvePromise)),
      new Promise((resolvePromise) => setTimeout(resolvePromise, 2000))
    ]);
  }
  rmSync(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
}

if (failures.length) {
  console.error(JSON.stringify({ status: "failed", failures, results }, null, 2));
  process.exit(1);
}
console.log(JSON.stringify({ status: "passed", checks: results.length, scenes: results.find((item) => item.name === "连续状态数量动态一致")?.detail?.actual }, null, 2));
