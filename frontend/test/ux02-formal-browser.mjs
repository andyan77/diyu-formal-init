import { spawn } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

import { resolveChromePath } from "./chrome-path.mjs";

const required = (name) => {
  const value = process.env[name];
  if (!value) throw new Error(`缺少 ${name}`);
  return value;
};

const baseUrl = required("UX02_BASE_URL").replace(/\/$/, "");
const expectedPublicUrl = (process.env.UX02_EXPECTED_PUBLIC_URL ?? baseUrl).replace(/\/$/, "");
const adminUsername = required("UX02_ADMIN_USERNAME");
const adminPassword = required("UX02_ADMIN_PASSWORD");
const newUserPassword = required("UX02_NEW_USER_PASSWORD");
const expectedAccountName = required("UX02_EXPECTED_ACCOUNT_NAME");
const expectedPlatform = required("UX02_EXPECTED_PLATFORM");
const boundedAdminOnly = process.env.UX02_BOUNDED_ADMIN_ONLY === "1";
const adminViewportWidth = Number(process.env.UX02_ADMIN_VIEWPORT_WIDTH ?? "1440");
const adminViewportHeight = Number(process.env.UX02_ADMIN_VIEWPORT_HEIGHT ?? "900");
const newUsername = `ux02-browser-${Date.now()}`;
const newDisplayName = `UX-02 浏览器成员 ${newUsername.slice(-6)}`;
const resetUserPassword = `${newUserPassword}-reset`;
const repo = resolve(new URL("../..", import.meta.url).pathname);
const chromePath = resolveChromePath({ configured: process.env.UX02_CHROME });
if (!chromePath) throw new Error("未找到本机 Chrome");

const { default: WebSocket } = await import(
  pathToFileURL(join(repo, "frontend", "node_modules", "ws", "index.js")).href
);
const profile = mkdtempSync(join(tmpdir(), "ux02-formal-browser-"));
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

let socket;
const failures = [];
const results = [];
const strictOracleFailures = [];
const record = (name, detail) => results.push({ name, status: "PASS", detail });

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
      socket.send(
        JSON.stringify({
          id,
          method,
          params,
          ...(sessionId ? { sessionId } : {})
        })
      );
    });

  const createPage = async ({ width = 1440, height = 900 } = {}) => {
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
    await send(
      "Emulation.setDeviceMetricsOverride",
      { width, height, deviceScaleFactor: 1, mobile: width <= 640 },
      sessionId
    );
    await send("Browser.grantPermissions", {
      browserContextId: context.browserContextId,
      origin: baseUrl,
      permissions: ["clipboardReadWrite", "clipboardSanitizedWrite"]
    });
    const evaluate = async expression => {
      const response = await send(
        "Runtime.evaluate",
        { expression, awaitPromise: true, returnByValue: true },
        sessionId
      );
      if (response.exceptionDetails) throw new Error(JSON.stringify(response.exceptionDetails));
      return response.result?.value;
    };
    const location = () => evaluate("location.pathname + location.search");
    const waitFor = async (expression, label, timeout = 20000) => {
      const started = Date.now();
      while (Date.now() - started < timeout) {
        try {
          if (await evaluate(expression)) return;
        } catch {
          // A real navigation may briefly expose no document/body between the
          // outgoing and incoming page. Keep polling the requested condition;
          // a persistent failure is reported with the final page context below.
        }
        await wait(100);
      }
      const body = await evaluate("document.body?.innerText.slice(0, 600) ?? ''");
      throw new Error(`等待超时：${label}；当前 ${await location()}；页面：${body}`);
    };
    const navigate = async path => {
      await send(
        "Page.navigate",
        { url: /^https?:\/\//.test(path) ? path : `${baseUrl}${path}` },
        sessionId
      );
      await waitFor(`document.readyState === 'complete' && !document.querySelector('.page-loading')`, `加载 ${path}`);
    };
    const fill = async (selector, value) => {
      const changed = await evaluate(`(() => {
        const node=document.querySelector(${JSON.stringify(selector)});
        if(!node)return false;
        const owner=node.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;
        Object.getOwnPropertyDescriptor(owner,'value').set.call(node,${JSON.stringify(value)});
        node.dispatchEvent(new Event('input',{bubbles:true}));
        node.dispatchEvent(new Event('change',{bubbles:true}));
        return true;
      })()`);
      ensure(changed, `找不到输入控件 ${selector}`);
    };
    const selectFirstValue = async selector => {
      const selected = await evaluate(`(() => {
        const node=document.querySelector(${JSON.stringify(selector)});
        if(!node)return null;
        const option=[...node.options].find(item=>item.value);
        if(!option)return null;
        Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value').set.call(node,option.value);
        node.dispatchEvent(new Event('change',{bubbles:true}));
        return {value:option.value,label:option.textContent.trim()};
      })()`);
      ensure(selected, `找不到可选值 ${selector}`);
      return selected;
    };
    const selectText = async (selector, text) => {
      const selected = await evaluate(`(() => {
        const node=document.querySelector(${JSON.stringify(selector)});
        if(!node)return null;
        const option=[...node.options].find(item=>item.textContent.trim()===${JSON.stringify(text)});
        if(!option)return null;
        Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value').set.call(node,option.value);
        node.dispatchEvent(new Event('change',{bubbles:true}));
        return {value:option.value,label:option.textContent.trim()};
      })()`);
      ensure(selected, `找不到选项 ${selector}:${text}`);
      return selected;
    };
    const click = async (selector, text) => {
      const clicked = await evaluate(`(() => {
        const nodes=[...document.querySelectorAll(${JSON.stringify(selector)})];
        const node=${text === undefined
          ? "nodes[0]"
          : `nodes.find(item=>item.textContent.trim().includes(${JSON.stringify(text)}))`};
        if(!node)return {clicked:false,candidates:nodes.map(item=>item.textContent.trim())};
        node.scrollIntoView({block:'center',inline:'nearest'});
        node.click();
        return {clicked:true};
      })()`);
      ensure(
        clicked?.clicked,
        `找不到可点击控件 ${selector}${text ? `:${text}` : ""}；候选 ${JSON.stringify(clicked?.candidates ?? [])}`
      );
      await wait(80);
    };
    return {
      browserContextId: context.browserContextId,
      sessionId,
      evaluate,
      waitFor,
      navigate,
      fill,
      selectFirstValue,
      selectText,
      click,
      location
    };
  };

  const admin = await createPage({
    width: adminViewportWidth,
    height: adminViewportHeight
  });
  const inspectCopyFeedback = () =>
    admin.evaluate(`(() => {
      const drawer=document.querySelector('.tenant-drawer');
      const feedback=[...document.querySelectorAll('[role="status"]')]
        .find(node=>node.textContent.includes('链接已复制')
          || node.textContent.includes('未能自动复制'));
      if(!feedback)return {exists:false};
      const style=getComputedStyle(feedback);
      const rect=feedback.getBoundingClientRect();
      const x=Math.min(window.innerWidth-1,Math.max(0,rect.left+rect.width/2));
      const y=Math.min(window.innerHeight-1,Math.max(0,rect.top+rect.height/2));
      const top=document.elementFromPoint(x,y);
      return {
        exists:true,
        inside:drawer?.contains(feedback)===true,
        display:style.display,
        visibility:style.visibility,
        opacity:Number(style.opacity||'1'),
        inViewport:rect.width>0 && rect.height>0
          && rect.bottom>0 && rect.right>0
          && rect.top<window.innerHeight && rect.left<window.innerWidth,
        uncovered:top===feedback || feedback.contains(top)
      };
    })()`);
  const inspectDisableFocus = () =>
    admin.evaluate(`(() => {
      const trigger=[...document.querySelectorAll('.tenant-drawer button')]
        .find(node=>node.textContent.trim()==='停用成员');
      const style=trigger?getComputedStyle(trigger):null;
      return {
        exists:Boolean(trigger),
        connected:trigger?.isConnected===true,
        exact:document.activeElement===trigger,
        focusVisible:Boolean(style)
          && (style.outlineStyle!=='none' || style.boxShadow!=='none')
      };
    })()`);
  await admin.navigate("/tenant-admin/login");
  await admin.fill('input[name="username"]', adminUsername);
  await admin.fill('input[name="password"]', adminPassword);
  await admin.click('button[type="submit"]', "登录");
  await admin.waitFor("location.pathname === '/tenant-admin'", "管理员登录");
  await admin.waitFor(
    "document.body.innerText.includes('成员与入口资格')",
    "管理导航"
  );
  await admin.click("nav button", "成员与入口资格");
  await admin.waitFor("document.querySelector('h1')?.textContent.includes('入口职责')", "成员页面");
  await admin.click("button", "添加成员");
  await admin.waitFor("document.querySelector('.tenant-drawer') !== null", "添加成员抽屉");
  await admin.waitFor(
    "document.querySelector('.tenant-drawer select')?.options.length > 1",
    "组织列表"
  );
  await admin.waitFor(
    `document.querySelector('.tenant-drawer')?.innerText.includes(${JSON.stringify(expectedAccountName)})`,
    "发布账号列表"
  );
  await admin.fill(".tenant-drawer .tenant-form > label:nth-of-type(1) input", newDisplayName);
  await admin.fill(".tenant-drawer .tenant-form > label:nth-of-type(2) input", newUsername);
  await admin.selectFirstValue(".tenant-drawer select");
  const displaySelection = await admin.evaluate(`(() => {
    const input=[...document.querySelectorAll('.tenant-drawer fieldset label')]
      .filter(item=>item.textContent.includes('陈列搭配'))
      .map(item=>item.querySelector('input[type="checkbox"]'))
      .find(Boolean);
    if(!input)return false;
    input.click();
    return input.checked;
  })()`);
  ensure(displaySelection, "没有通过正式表单分配陈列搭配资格");
  const accountSelection = await admin.evaluate(`(() => {
    const labels=[...document.querySelectorAll('.tenant-drawer fieldset label')];
    const label=labels.find(item=>item.textContent.includes(${JSON.stringify(expectedAccountName)}));
    const input=label?.querySelector('input[type="checkbox"]');
    if(!input)return false;
    input.click();
    return input.checked;
  })()`);
  ensure(accountSelection, "没有通过正式表单分配预期发布账号");
  await admin.click(".tenant-drawer button.primary", "创建并生成");
  await admin.waitFor("document.querySelector('.one-time-link code') !== null", "完整激活链接", 20000);
  const activation = await admin.evaluate(`(() => {
    const value=document.querySelector('.one-time-link code')?.textContent.trim();
    const href=document.querySelector('.one-time-link a')?.href;
    return {value,href};
  })()`);
  ensure(
    activation.value?.startsWith(`${expectedPublicUrl}/activate/`),
    "显示值不是可信完整 HTTPS URL"
  );
  ensure(activation.href === activation.value, "显示值与点击目标不一致");
  await admin.click(".one-time-link button", "复制链接");
  await admin.waitFor(
    "document.body.textContent.includes('链接已复制')",
    "激活链接复制成功反馈"
  );
  const activationCopyFeedback = await inspectCopyFeedback();
  if (
    !activationCopyFeedback.exists ||
    !activationCopyFeedback.inside ||
    activationCopyFeedback.display === "none" ||
    activationCopyFeedback.visibility === "hidden" ||
    activationCopyFeedback.opacity <= 0 ||
    !activationCopyFeedback.inViewport ||
    !activationCopyFeedback.uncovered
  ) {
    strictOracleFailures.push({
      check: "activation_copy_feedback_visible_inside_drawer",
      detail: activationCopyFeedback
    });
  }
  const copiedActivation = await admin.evaluate("navigator.clipboard.readText()");
  ensure(copiedActivation === activation.value, "复制值与显示值不一致");
  record("管理员创建成员与完整激活链接", {
    username: newUsername,
    target: new URL(activation.value).origin,
    display_equals_copy: true
  });

  const user = await createPage();
  await user.navigate(
    expectedPublicUrl === baseUrl
      ? activation.value
      : `${baseUrl}${new URL(activation.value).pathname}`
  );
  await user.waitFor("document.querySelector('input[name=password]') !== null", "新会话激活页");
  await user.fill('input[name="password"]', newUserPassword);
  await user.fill('input[name="password_confirm"]', `${newUserPassword}-mismatch`);
  await user.click('button[type="submit"]', "完成设置");
  await user.waitFor(
    "location.pathname.startsWith('/activate/') && document.body.textContent.includes('两次输入的密码不一致')",
    "密码不一致留在激活页"
  );
  await user.fill('input[name="password_confirm"]', newUserPassword);
  await user.click('button[type="submit"]', "完成设置");
  await user.waitFor(
    "location.pathname === '/login' && document.querySelector('input[name=username]') !== null",
    "激活后用户登录入口"
  );
  await user.fill('input[name="username"]', newUsername);
  await user.fill('input[name="password"]', newUserPassword);
  await user.click('button[type="submit"]', "登录");
  await user.waitFor(
    "location.pathname === '/user' && document.body !== null",
    "租户用户登录"
  );
  ensure(
    await user.evaluate("document.body.textContent.includes('开始创作') && !document.body.textContent.includes('品牌管理')"),
    "租户用户入口职责不正确"
  );

  await admin.click(".tenant-drawer button", "关闭");
  const memberArticleOpened = await admin.evaluate(`(() => {
    const article=[...document.querySelectorAll('.tenant-list article')]
      .find(node=>node.textContent.includes(${JSON.stringify(newDisplayName)}));
    const button=article?.querySelector('button');
    if(!button)return false;
    button.click();
    return true;
  })()`);
  ensure(memberArticleOpened, "激活后无法重新打开新成员");
  await admin.waitFor("document.querySelector('.tenant-drawer') !== null", "成员详情");
  await admin.click(".tenant-drawer button", "生成一次性重设密码链接");
  await admin.waitFor(
    "document.querySelector('.one-time-link code.reset-link') !== null",
    "完整重设密码链接"
  );
  const resetUrl = await admin.evaluate(
    "document.querySelector('.one-time-link code.reset-link')?.textContent.trim()"
  );
  ensure(
    resetUrl?.startsWith(`${expectedPublicUrl}/activate/`),
    "重设链接不是可信完整 URL"
  );
  await admin.click(".one-time-link button", "复制重设链接");
  await admin.waitFor(
    "document.body.textContent.includes('链接已复制')",
    "重设链接复制成功反馈"
  );
  const resetCopyFeedback = await inspectCopyFeedback();
  if (
    !resetCopyFeedback.exists ||
    !resetCopyFeedback.inside ||
    resetCopyFeedback.display === "none" ||
    resetCopyFeedback.visibility === "hidden" ||
    resetCopyFeedback.opacity <= 0 ||
    !resetCopyFeedback.inViewport ||
    !resetCopyFeedback.uncovered
  ) {
    strictOracleFailures.push({
      check: "reset_copy_feedback_visible_inside_drawer",
      detail: resetCopyFeedback
    });
  }
  ensure(
    (await admin.evaluate("navigator.clipboard.readText()")) === resetUrl,
    "重设链接复制值与显示值不一致"
  );
  await user.navigate(
    expectedPublicUrl === baseUrl
      ? resetUrl
      : `${baseUrl}${new URL(resetUrl).pathname}`
  );
  await user.waitFor(
    "document.querySelector('input[name=password_confirm]') !== null",
    "新会话重设页"
  );
  await user.fill('input[name="password"]', resetUserPassword);
  await user.fill('input[name="password_confirm"]', `${resetUserPassword}-mismatch`);
  await user.click('button[type="submit"]', "更新密码");
  await user.waitFor(
    "location.pathname.startsWith('/activate/') && document.body.textContent.includes('两次输入的密码不一致')",
    "密码不一致留在重设页"
  );
  await user.fill('input[name="password_confirm"]', resetUserPassword);
  await user.click('button[type="submit"]', "更新密码");
  await user.waitFor(
    "location.pathname === '/login' && document.querySelector('input[name=username]') !== null",
    "重设后用户登录入口"
  );
  await user.fill('input[name="username"]', newUsername);
  await user.fill('input[name="password"]', resetUserPassword);
  await user.click('button[type="submit"]', "登录");
  await user.waitFor("location.pathname === '/user'", "重设后重新登录");
  record("激活与重设密码双重输入及复制反馈", {
    mismatch_did_not_consume_token: true,
    activation_copy_feedback: true,
    reset_copy_feedback: true
  });

  if (!boundedAdminOnly) {
  await user.click("a", "开始创作");
  await user.waitFor("location.pathname === '/content'", "进入正式创作工作台");
  await user.waitFor("document.querySelector('textarea[aria-label=\"内容需求\"]') !== null", "创作输入区");
  const creatorScope = await user.evaluate(`({
    account:document.querySelector('select[aria-label="发布账号"]')?.selectedOptions[0]?.textContent.trim(),
    platforms:[...document.querySelector('select[aria-label="平台"]')?.options??[]].map(item=>item.textContent.trim())
  })`);
  ensure(creatorScope.account?.includes(expectedAccountName), "租户用户未看到获准发布账号");
  ensure(creatorScope.platforms.includes(expectedPlatform), "同一账号没有预期平台目标");
  if (
    !(await user.evaluate(
      `document.querySelector('select[aria-label="平台"]')?.selectedOptions[0]?.textContent.trim()===${JSON.stringify(expectedPlatform)}`
    ))
  ) {
    await user.selectText('select[aria-label="平台"]', expectedPlatform);
    await user.waitFor(
      `location.pathname==='/content' && document.querySelector('select[aria-label="平台"]')?.selectedOptions[0]?.textContent.trim()===${JSON.stringify(expectedPlatform)}`,
      "切换到预期平台"
    );
    await user.waitFor("document.querySelector('textarea[aria-label=\"内容需求\"]') !== null", "平台切换后输入区");
  }

  await user.fill('textarea[aria-label="内容需求"]', "你好，先聊两句。");
  await user.click(".composer-submit button", "发送");
  await user.waitFor(
    "document.querySelector('.message.assistant') !== null",
    "普通发送返回对话但不生成",
    90000
  );
  ensure(
    !(await user.evaluate("document.querySelector('.creator-artifact') !== null")),
    "普通发送错误创建了版本"
  );
  // The production limiter intentionally rejects a second model submission from the same
  // natural person inside two seconds. This is a separate user action, not a retry.
  await wait(2200);
  const seed = "今天店里忙了一天，回家因为洗碗拌了两句，帮我发条小红书。";
  await user.fill('textarea[aria-label="内容需求"]', seed);
  await user.click(".composer-submit button.primary", "生成内容");
  await user.waitFor(
    "document.querySelector('.creator-artifact .eyebrow')?.textContent.includes('V1')",
    "低种子完整 V1",
    180000
  );
  ensure(
    await user.evaluate("document.querySelector('.creator-artifact')?.textContent.includes('AI 辅助生成')"),
    "V1 缺少 AIGC 提醒"
  );
  await user.waitFor(
    "document.body.innerText.includes('修改成 V2')",
    "V1 原子收尾"
  );
  await user.fill('textarea[aria-label="修改要求"]', "别讲道理，荒诞一点。");
  await user.click(".composer-submit button.primary", "修改成 V2");
  await user.waitFor(
    "document.querySelector('.creator-artifact .eyebrow')?.textContent.includes('V2')",
    "自然修改 V2",
    180000
  );
  await user.click(".version-history summary");
  await user.click(".version-history button", "V1");
  ensure(
    await user.evaluate("document.querySelector('.history-reading')?.textContent.includes('当前版仍是 V2')"),
    "历史 V1 与当前 V2 身份不清楚"
  );
  await user.click(".history-reading button", "回到当前版");
  ensure(
    await user.evaluate("document.querySelector('.creator-artifact .eyebrow')?.textContent.includes('当前版本')"),
    "不能返回当前 V2"
  );
  await user.click(".artifact-actions button", "复制");
  await user.waitFor("document.body.textContent.includes('已复制 V2 全文')", "复制当前查看版本");
  await send("Browser.setDownloadBehavior", {
    behavior: "allow",
    downloadPath: profile,
    browserContextId: user.browserContextId
  });
  await user.click(".artifact-actions button", "导出");
  await user.waitFor("document.body.textContent.includes('已导出 V2')", "导出当前查看版本");
  await user.navigate("/content");
  await user.waitFor(
    "[...document.querySelectorAll('.creator-history nav button')].some(node=>node.textContent.includes('V2'))",
    "刷新后历史 V2 可读",
    30000
  );
  record("租户用户低种子 V1/V2 与历史复制导出", {
    send_without_version: true,
    v1_v2_v1_current: true,
    refresh_persisted: true
  });

  await user.navigate("/user");
  await user.waitFor("document.body.innerText.includes('做陈列搭配')", "陈列搭配入口");
  await user.click("a", "做陈列搭配");
  await user.waitFor("location.pathname === '/display'", "进入陈列搭配");
  const inventory = {
    "ZX-C218": 3,
    "ZX-S104": 3,
    "ZX-K126": 4,
    "ZX-P211": 3,
    "ZX-V113": 3,
    "ZX-Q117": 4
  };
  for (const sku of Object.keys(inventory)) {
    await user.click(".display-product-picker button", sku);
  }
  const inventoryPrepared = await user.evaluate(`(() => {
    const quantities=${JSON.stringify(inventory)};
    for(const row of document.querySelectorAll('.display-selected-products > div')) {
      const sku=Object.keys(quantities).find(value=>row.textContent.includes(value));
      const input=row.querySelector('input[type="number"]');
      if(!sku||!input)continue;
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,String(quantities[sku]));
      input.dispatchEvent(new Event('input',{bubbles:true}));
      input.dispatchEvent(new Event('change',{bubbles:true}));
    }
    return [...document.querySelectorAll('.display-selected-products input')]
      .reduce((sum,node)=>sum+Number(node.value),0);
  })()`);
  ensure(inventoryPrepared === 20, "DM01 结构化商品数量没有保持");
  await user.click(".display-composer button.primary", "生成参考方案");
  await user.waitFor(
    "document.querySelector('.display-artifact .eyebrow')?.textContent.includes('V1')",
    "DM01 V1"
  );
  const displayV1 = await user.evaluate("document.querySelector('.display-artifact')?.innerText");
  ensure(displayV1.includes("20 件"), "DM01 V1 没有守恒到 20 件库存");
  ensure(!/(?:AIGC|AI 辅助生成|示意图|图片预览)/.test(displayV1), "DM01 错误出现模型或绘图暗示");
  await user.waitFor("document.body.innerText.includes('生成 V2')", "DM01 V1 原子收尾");
  await user.fill("#display-feedback", "中间上杆 ZX-V113 太挤，请减少一件；其他内容不变。");
  await user.click(".display-revision button.primary", "生成 V2");
  await user.waitFor(
    "document.querySelector('.display-artifact .eyebrow')?.textContent.includes('V2')",
    "DM01 V2"
  );
  await user.click(".display-version-history summary");
  await user.click(".display-version-history button", "阅读 V1");
  ensure(
    await user.evaluate("document.querySelector('.display-artifact .eyebrow')?.textContent.includes('历史版本')"),
    "DM01 V1 没有明确历史身份"
  );
  await user.click(".history-reading button", "回到当前版");
  ensure(
    await user.evaluate("document.querySelector('.display-artifact .eyebrow')?.textContent.includes('当前版本')"),
    "DM01 不能返回当前 V2"
  );
  await user.click(".display-artifact-heading button", "复制");
  await user.waitFor("document.body.innerText.includes('已复制 V2')", "DM01 复制当前版本");
  record("DM01 纯文字 V1/V2 与库存守恒", {
    inventory_units: 20,
    v1_v2_v1_current: true,
    aigc_or_image_hint: false
  });
  }

  await admin.navigate("/tenant-admin");
  await admin.waitFor(
    "document.body.innerText.includes('成员与入口资格')",
    "管理员重新进入"
  );
  await admin.click("nav button", "成员与入口资格");
  await admin.waitFor(
    `[...document.querySelectorAll('.tenant-list article')].some(node=>node.textContent.includes(${JSON.stringify(newDisplayName)}))`,
    "新成员刷新后可读"
  );
  const opened = await admin.evaluate(`(() => {
    const article=[...document.querySelectorAll('.tenant-list article')]
      .find(node=>node.textContent.includes(${JSON.stringify(newDisplayName)}));
    const button=article?.querySelector('button');
    if(!button)return false;
    button.click();
    return true;
  })()`);
  ensure(opened, "无法打开新成员");
  await admin.waitFor("document.querySelector('.tenant-drawer') !== null", "成员详情");
  await admin.click(".tenant-drawer button", "停用成员");
  ensure(
    await user.evaluate("location.pathname === '/user'"),
    "停用首击不应撤销旧会话"
  );
  await admin.waitFor(
    "document.querySelector('[role=alertdialog]') !== null",
    "停用成员二次确认"
  );
  await admin.click('[role="alertdialog"] button', "取消");
  await admin.waitFor(
    "document.querySelector('[role=alertdialog]') === null",
    "取消停用返回成员详情"
  );
  const cancelFocus = await inspectDisableFocus();
  if (!cancelFocus.exists || !cancelFocus.connected || !cancelFocus.exact || !cancelFocus.focusVisible) {
    strictOracleFailures.push({
      check: "cancel_returns_exact_connected_visible_focus",
      detail: cancelFocus
    });
  }
  ensure(
    await user.evaluate("location.pathname === '/user'"),
    "取消停用不应撤销旧会话"
  );
  await admin.click(".tenant-drawer button", "停用成员");
  await admin.waitFor(
    "document.querySelector('[role=alertdialog]') !== null",
    "Escape 前停用成员二次确认"
  );
  await admin.evaluate(`document.querySelector('[role=alertdialog]').dispatchEvent(
    new KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true})
  )`);
  await admin.waitFor(
    "document.querySelector('[role=alertdialog]') === null",
    "Escape 返回成员详情"
  );
  const escapeFocus = await inspectDisableFocus();
  if (!escapeFocus.exists || !escapeFocus.connected || !escapeFocus.exact || !escapeFocus.focusVisible) {
    strictOracleFailures.push({
      check: "escape_returns_exact_connected_visible_focus",
      detail: escapeFocus
    });
  }
  await admin.click(".tenant-drawer button", "停用成员");
  await admin.click('[role="alertdialog"] button', "确认停用");
  await admin.waitFor("document.body.textContent.includes('现有会话与工作资格已撤销')", "停用反馈");
  await user.navigate("/user");
  await user.waitFor(
    "location.pathname === '/login' && document.querySelector('input[name=username]') !== null",
    "停用后旧会话失效"
  );
  await user.fill('input[name="username"]', newUsername);
  await user.fill('input[name="password"]', resetUserPassword);
  await user.click('button[type="submit"]', "登录");
  await user.waitFor("document.body.textContent.includes('用户名、密码或当前入口不匹配')", "停用后登录失败");
  record("成员停用使旧会话与再次登录失效", true);

  const baseOrigin = new URL(baseUrl).origin;
  const externalRequests = events
    .filter(event => event.method === "Network.requestWillBeSent")
    .map(event => event.params?.request?.url)
    .filter(Boolean)
    .filter(url => {
      const parsed = new URL(url);
      return !["data:", "blob:"].includes(parsed.protocol) && parsed.origin !== baseOrigin;
    });
  ensure(externalRequests.length === 0, `出现意外外部请求：${externalRequests.join(", ")}`);
  const browserErrors = events.filter(
    event =>
      event.method === "Runtime.exceptionThrown" ||
      (event.method === "Log.entryAdded" && event.params?.entry?.level === "error")
  );
  ensure(browserErrors.length === 0, `浏览器控制台错误：${JSON.stringify(browserErrors)}`);
  ensure(
    strictOracleFailures.length === 0,
    `严格可见性／焦点 Oracle 失败：${JSON.stringify(strictOracleFailures)}`
  );
  record("浏览器安全边界", { external_requests: 0, console_errors: 0 });
} catch (error) {
  failures.push(error instanceof Error ? error.stack ?? error.message : String(error));
} finally {
  try {
    socket?.close();
  } catch {
    // Best-effort browser teardown only.
  }
  chrome.kill("SIGTERM");
  await Promise.race([
    new Promise(resolvePromise => chrome.once("exit", resolvePromise)),
    wait(2000)
  ]);
  rmSync(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
}

console.log(JSON.stringify({ results, failures, synthetic_username: newUsername }, null, 2));
if (failures.length) process.exit(1);
