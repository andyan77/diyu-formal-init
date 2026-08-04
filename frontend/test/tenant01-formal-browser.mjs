import { createHash, randomUUID } from "node:crypto";
import {
  chmodSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { spawn } from "node:child_process";

import { resolveChromePath } from "./chrome-path.mjs";

const required = name => {
  const value = process.env[name];
  if (!value) throw new Error(`缺少 ${name}`);
  return value;
};
const ensure = (value, message) => {
  if (!value) throw new Error(message);
};
const wait = milliseconds =>
  new Promise(resolvePromise => setTimeout(resolvePromise, milliseconds));
const digest = value =>
  createHash("sha256").update(String(value), "utf8").digest("hex");

const baseUrl = required("TENANT01_BROWSER_BASE_URL").replace(/\/$/, "");
const credentialPath = required("TENANT01_BROWSER_CREDENTIALS");
const contextPath = required("TENANT01_CONTEXT_EVIDENCE");
const outputPath = required("TENANT01_BROWSER_OUTPUT");
const candidateSha = required("TENANT01_CANDIDATE_SHA");
const expectFormallyTested =
  process.env.TENANT01_EXPECT_FORMALLY_TESTED === "1";
const expectAigc = process.env.TENANT01_EXPECT_AIGC === "1";
const credentials = JSON.parse(readFileSync(credentialPath, "utf8"));
const contextEvidence = JSON.parse(readFileSync(contextPath, "utf8"));
ensure(credentials.candidate_sha === candidateSha, "浏览器凭据候选 SHA 漂移");
ensure(contextEvidence.candidate_sha === candidateSha, "上下文证据候选 SHA 漂移");
ensure(credentials.tenant_id === contextEvidence.tenant_id, "浏览器租户与上下文租户不一致");
const expectedCurrentProjection = contextEvidence.projection_isolation;
const expectedFormalMemberUsername = contextEvidence.member_journey?.username;
ensure(
  expectedCurrentProjection?.new_projection_status === "confirmed" &&
    Number.isInteger(expectedCurrentProjection?.new_projection_version),
  "浏览器缺少纵向确认后的 current projection 绑定"
);
ensure(expectedFormalMemberUsername, "浏览器缺少正式成员登录身份绑定");

const repo = resolve(new URL("../..", import.meta.url).pathname);
const chromePath = resolveChromePath({ configured: process.env.TENANT01_CHROME });
if (!chromePath) throw new Error("未找到本机 Chrome");

const { default: WebSocket } = await import(
  pathToFileURL(join(repo, "frontend", "node_modules", "ws", "index.js")).href
);
const profile = mkdtempSync(join(tmpdir(), "tenant01-formal-browser-"));
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

const checks = [];
const record = (id, detail) => checks.push({ id, status: "PASS", detail });
const consoleErrors = [];
const requestedUrls = new Set();
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
    if (message.method === "Runtime.exceptionThrown") {
      consoleErrors.push("runtime-exception");
    }
    if (
      message.method === "Runtime.consoleAPICalled" &&
      message.params?.type === "error"
    ) {
      consoleErrors.push("console-error");
    }
    if (
      message.method === "Log.entryAdded" &&
      ["error", "warning"].includes(message.params?.entry?.level)
    ) {
      const entry = message.params.entry;
      consoleErrors.push({
        kind: `log-${entry.level}`,
        source: entry.source,
        text: String(entry.text ?? "").slice(0, 300),
        url: String(entry.url ?? "").replace(baseUrl, "<local>")
      });
    }
    if (message.method === "Network.requestWillBeSent") {
      requestedUrls.add(message.params?.request?.url ?? "");
    }
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
    await send("Log.enable", {}, sessionId);
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
      if (response.exceptionDetails) {
        throw new Error(JSON.stringify(response.exceptionDetails));
      }
      return response.result?.value;
    };
    const location = () => evaluate("location.pathname + location.search");
    const waitFor = async (expression, label, timeout = 30000) => {
      const started = Date.now();
      while (Date.now() - started < timeout) {
        try {
          if (await evaluate(expression)) return;
        } catch {
          // Navigation briefly removes the execution context.
        }
        await wait(100);
      }
      const body = await evaluate("document.body?.innerText.slice(0,900) ?? ''");
      throw new Error(`等待超时：${label}；${await location()}；${body}`);
    };
    const navigate = async path => {
      await send(
        "Page.navigate",
        { url: /^https?:\/\//.test(path) ? path : `${baseUrl}${path}` },
        sessionId
      );
      await waitFor("document.readyState === 'complete'", `加载 ${path}`);
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
    const fillLabel = async (container, label, value) => {
      const changed = await evaluate(`(() => {
        const root=document.querySelector(${JSON.stringify(container)});
        const owner=[...(root?.querySelectorAll('label')??[])].find(
          node=>node.textContent.trim().startsWith(${JSON.stringify(label)})
        );
        const node=owner?.querySelector('input,textarea');
        if(!node)return false;
        const prototype=node.tagName==='TEXTAREA'
          ? HTMLTextAreaElement.prototype
          : HTMLInputElement.prototype;
        Object.getOwnPropertyDescriptor(prototype,'value').set.call(
          node,${JSON.stringify(value)}
        );
        node.dispatchEvent(new Event('input',{bubbles:true}));
        node.dispatchEvent(new Event('change',{bubbles:true}));
        return true;
      })()`);
      ensure(changed, `找不到标签输入控件 ${container}:${label}`);
      await wait(100);
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
        `找不到可点击控件 ${selector}:${text ?? ""}；${JSON.stringify(clicked?.candidates ?? [])}`
      );
      await wait(100);
    };
    const selectText = async (selector, text) => {
      const selected = await evaluate(`(() => {
        const node=document.querySelector(${JSON.stringify(selector)});
        const option=[...(node?.options??[])].find(
          item=>item.textContent.trim()===${JSON.stringify(text)}
        );
        if(!node||!option)return false;
        Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value')
          .set.call(node,option.value);
        node.dispatchEvent(new Event('change',{bubbles:true}));
        return true;
      })()`);
      ensure(selected, `找不到选择项 ${selector}:${text}`);
    };
    const setViewport = async (width, height) => {
      await send(
        "Emulation.setDeviceMetricsOverride",
        { width, height, deviceScaleFactor: 1, mobile: width <= 640 },
        sessionId
      );
      await wait(120);
    };
    const setScale = async scale => {
      await send(
        "Emulation.setPageScaleFactor",
        { pageScaleFactor: scale },
        sessionId
      );
      await wait(120);
    };
    return {
      browserContextId: context.browserContextId,
      sessionId,
      evaluate,
      waitFor,
      navigate,
      fill,
      fillLabel,
      click,
      selectText,
      setViewport,
      setScale,
      location
    };
  };

  const login = async (page, route, username, password, expectedRoute) => {
    await page.navigate(route);
    await page.waitFor(
      "document.querySelector('input[name=username]') !== null",
      `登录页 ${route}`
    );
    await page.fill('input[name="username"]', username);
    await page.fill('input[name="password"]', password);
    await page.click('button[type="submit"]', "登录");
    await page.waitFor(
      `location.pathname===${JSON.stringify(expectedRoute)}`,
      `登录进入 ${expectedRoute}`
    );
  };

  const publicPage = await createPage();
  await publicPage.navigate("/");
  await publicPage.waitFor(
    "document.querySelector('.public-home') !== null",
    "公共首页"
  );
  const skipVisible = await publicPage.evaluate(
    "[...document.querySelectorAll('button')].some(node=>node.textContent.includes('跳过'))"
  );
  if (skipVisible) await publicPage.click("button", "跳过");
  await publicPage.waitFor(
    "document.body.innerText.includes('开始创作')",
    "首页行动入口"
  );
  ensure(
    await publicPage.evaluate(
      "document.body.innerText.includes('品牌管理') && document.body.innerText.includes('笛语运维') && document.body.innerText.includes('重播动效')"
    ),
    "公共首页三类入口或重播动效缺失"
  );
  record("PUBLIC_HOME", {
    start: true,
    tenant_admin: true,
    operations: true,
    skip_replay: true
  });
  await publicPage.navigate("/status");
  await publicPage.waitFor(
    "document.body.innerText.includes('服务状态')",
    "公开状态页"
  );
  ensure(
    await publicPage.evaluate(
      "!document.body.innerText.includes('全部能力 ready')"
    ),
    "公开状态页把能力真值混成全部 ready"
  );
  record("PUBLIC_STATUS", { dynamic_projection: true, static_all_ready: false });

  const admin = await createPage({ width: 1440, height: 900 });
  await login(
    admin,
    "/tenant-admin/login",
    credentials.admin_username,
    credentials.admin_password,
    "/tenant-admin"
  );
  await admin.waitFor(
    "document.body.innerText.includes('成员与入口资格')",
    "管理员导航"
  );
  record("ADMIN_LOGIN", { role: "tenant_admin", route: "/tenant-admin" });
  await admin.click("nav button", "成员与入口资格");
  await admin.waitFor(
    "document.querySelectorAll('.tenant-list article').length >= 4",
    "正式成员列表"
  );
  const memberTruth = await admin.evaluate(`(() => {
    const cards=[...document.querySelectorAll('.tenant-list article')];
    const same=cards.filter(node=>node.querySelector('h2')?.textContent.trim()==='柯桥店阿丹');
    return {
      sameDisplayNames:same.length,
      exactUsername:same.some(node=>node.innerText.includes('登录用户名：' + ${JSON.stringify(expectedFormalMemberUsername)})),
      fields:same.every(node=>node.innerText.includes('登录用户名：') && node.innerText.includes('柯桥店'))
    };
  })()`);
  ensure(
    memberTruth.sameDisplayNames >= 2 &&
      memberTruth.exactUsername &&
      memberTruth.fields,
    "同显示名成员或不可变登录身份没有在正式 UI 中正确呈现"
  );
  record("ADMIN_MEMBER_IDENTITY", memberTruth);

  await admin.click("button", "添加成员");
  await admin.waitFor(
    "document.querySelector('.tenant-drawer') !== null",
    "添加成员抽屉"
  );
  await admin.evaluate(`(() => {
    const drawer=document.querySelector('.tenant-drawer');
    const display=[...drawer.querySelectorAll('label')]
      .find(node=>node.textContent.trim().startsWith('陈列搭配'))
      ?.querySelector('input[type="checkbox"]');
    display?.click();
  })()`);
  await admin.waitFor(
    "document.querySelector('.tenant-drawer')?.innerText.includes('当前没有正式门店档案，暂不能开通陈列搭配；不影响内容生产。')",
    "无正式门店时的陈列资格提示"
  );
  const prerequisiteTruth = await admin.evaluate(`(() => {
    const drawer=document.querySelector('.tenant-drawer');
    return {
      requiredFields:['姓名或工作名','登录用户名','所属组织','入口类型','业务资格']
        .every(text=>drawer.innerText.includes(text)),
      accountChoice:drawer.innerText.includes('笛语服饰品牌内容账号'),
      prerequisiteList:drawer.innerText.includes('创建前条件'),
      dm01Gap:drawer.innerText.includes('当前没有正式门店档案，暂不能开通陈列搭配；不影响内容生产。'),
      submitDisabled:drawer.querySelector('button.primary')?.disabled===true
    };
  })()`);
  ensure(
    Object.values(prerequisiteTruth).every(Boolean),
    `成员创建前置、账号选择或无门店 DM01 失败关闭不完整：${JSON.stringify(prerequisiteTruth)}`
  );
  record("ADMIN_MEMBER_PREREQUISITES", prerequisiteTruth);

  const browserMemberDisplayName = "浏览器正式验收成员";
  const browserMemberUsername = `笛语浏览验收-${randomUUID().replaceAll("-", "").slice(0, 10)}`;
  const activationPassword = `Aa!${randomUUID().replaceAll("-", "")}`;
  const resetPassword = `Bb!${randomUUID().replaceAll("-", "")}`;
  await admin.evaluate(`(() => {
    const drawer=document.querySelector('.tenant-drawer');
    const labels=[...(drawer?.querySelectorAll('label')??[])];
    const tenantUser=labels.find(node=>node.textContent.includes('租户用户'))
      ?.querySelector('input[type="radio"]');
    if(tenantUser && !tenantUser.checked)tenantUser.click();
  })()`);
  await wait(150);
  await admin.evaluate(`(() => {
    const labels=[...document.querySelectorAll('.tenant-drawer label')];
    const content=labels.find(node=>node.textContent.trim().startsWith('内容创作'))
      ?.querySelector('input[type="checkbox"]');
    const display=labels.find(node=>node.textContent.trim().startsWith('陈列搭配'))
      ?.querySelector('input[type="checkbox"]');
    if(content && !content.checked)content.click();
    if(display?.checked)display.click();
  })()`);
  await wait(150);
  await admin.fillLabel(".tenant-drawer", "姓名或工作名", browserMemberDisplayName);
  await admin.fillLabel(".tenant-drawer", "登录用户名", browserMemberUsername);
  await admin.selectText(".tenant-drawer select", "柯桥店");
  await wait(150);
  await admin.click(
    ".tenant-drawer label",
    "使用 笛语服饰品牌内容账号"
  );
  await admin.waitFor(
    "document.querySelector('.tenant-drawer button[type=submit].primary')?.disabled===false",
    "浏览器正式成员创建条件"
  );
  await admin.click(
    ".tenant-drawer button[type=submit]",
    "创建并生成一次性激活链接"
  );
  await admin.waitFor(
    "document.querySelector('.tenant-drawer .one-time-link a[href*=\"/activate/\"]')!==null",
    "正式一次性激活链接"
  );
  await admin.click(".tenant-drawer .one-time-link button", "复制链接");
  await admin.waitFor(
    "document.querySelector('.tenant-drawer .one-time-link [role=status]')?.innerText.includes('链接已复制')===true",
    "复制激活链接反馈"
  );
  const activationHref = await admin.evaluate(
    "document.querySelector('.tenant-drawer .one-time-link a[href*=\"/activate/\"]')?.href"
  );
  ensure(
    typeof activationHref === "string" && activationHref.startsWith("https://"),
    "正式激活链接不是完整 HTTPS URL"
  );
  const activationPage = await createPage();
  await activationPage.navigate(new URL(activationHref).pathname);
  await activationPage.waitFor(
    "document.body.innerText.includes('设置你的密码') && document.body.innerText.includes('至少 12 个字符')",
    "正式激活页密码要求"
  );
  await activationPage.fill('input[name="password"]', activationPassword);
  await activationPage.fill('input[name="password_confirm"]', activationPassword);
  await activationPage.click('button[type="submit"]', "完成设置");
  await activationPage.waitFor("location.pathname==='/login'", "正式成员激活完成");
  await login(
    activationPage,
    "/login",
    browserMemberUsername,
    activationPassword,
    "/user"
  );
  await activationPage.click("a", "开始创作");
  await activationPage.waitFor(
    "location.pathname==='/content' && document.body.innerText.includes('还没有成品')",
    "新成员正式空状态"
  );
  record("ADMIN_ACTIVATION_LINK_BROWSER", {
    full_https_url: true,
    copied: true,
    password_minimum: 12,
    activated: true
  });
  record("FORMAL_EMPTY_STATE", { task_created: false, visible: true });

  await admin.click(".tenant-drawer button", "关闭");
  await admin.waitFor(
    "document.querySelector('.tenant-drawer')===null",
    "关闭成员创建抽屉"
  );
  const openedBrowserMember = await admin.evaluate(`(() => {
    const card=[...document.querySelectorAll('.tenant-list article')]
      .find(node=>node.innerText.includes(${JSON.stringify(browserMemberUsername)}));
    card?.querySelector('button')?.click();
    return Boolean(card);
  })()`);
  ensure(openedBrowserMember, "浏览器正式成员没有进入成员列表");
  await admin.waitFor(
    `document.querySelector('.tenant-drawer')?.innerText.includes(${JSON.stringify(browserMemberUsername)})===true`,
    "浏览器正式成员详情"
  );
  await admin.click(
    ".tenant-drawer button",
    "生成一次性重设密码链接"
  );
  await admin.waitFor(
    "document.querySelector('.tenant-drawer .reset-link')!==null",
    "正式一次性重设链接"
  );
  await admin.click(".tenant-drawer .one-time-link button", "复制重设链接");
  await admin.waitFor(
    "document.querySelector('.tenant-drawer .one-time-link [role=status]')?.innerText.includes('链接已复制')===true",
    "复制重设链接反馈"
  );
  const resetHref = await admin.evaluate(
    "document.querySelector('.tenant-drawer .one-time-link a[href*=\"/activate/\"]')?.href"
  );
  ensure(
    typeof resetHref === "string" && resetHref.startsWith("https://"),
    "正式重设链接不是完整 HTTPS URL"
  );
  const resetPage = await createPage();
  await resetPage.navigate(new URL(resetHref).pathname);
  await resetPage.waitFor(
    "document.body.innerText.includes('重新设置密码') && document.body.innerText.includes('至少 12 个字符')",
    "正式重设页密码要求"
  );
  await resetPage.fill('input[name="password"]', resetPassword);
  await resetPage.fill('input[name="password_confirm"]', resetPassword);
  await resetPage.click('button[type="submit"]', "更新密码");
  await resetPage.waitFor("location.pathname==='/login'", "正式密码重设完成");
  await login(resetPage, "/login", browserMemberUsername, resetPassword, "/user");
  record("ADMIN_RESET_LINK_BROWSER", {
    full_https_url: true,
    copied: true,
    password_minimum: 12,
    reset_login: true
  });
  await admin.click(".tenant-drawer button", "关闭");

  await admin.click("nav button", "品牌资料库");
  await admin.waitFor(
    "document.body.innerText.includes('管理组织')",
    "品牌资料库组织入口"
  );
  const organizationName = `浏览器验收组织-${randomUUID().replaceAll("-", "").slice(0, 8)}`;
  const renamedOrganization = `${organizationName}-修改`;
  await admin.click("button", "管理组织");
  await admin.waitFor(
    "document.querySelector('.tenant-drawer .organization-lifecycle')!==null",
    "组织生命周期抽屉"
  );
  await admin.fillLabel(".tenant-drawer", "组织名称", organizationName);
  await admin.selectText(".tenant-drawer select", "区域");
  await admin.click(".tenant-drawer button.primary", "建立组织");
  await admin.waitFor(
    `document.querySelector('.tenant-drawer')?.innerText.includes(${JSON.stringify(organizationName)})===true`,
    "正式组织建立"
  );
  const selectedForEdit = await admin.evaluate(`(() => {
    const row=[...document.querySelectorAll('.tenant-drawer .organization-lifecycle li')]
      .find(node=>node.innerText.includes(${JSON.stringify(organizationName)}));
    const button=[...(row?.querySelectorAll('button')??[])]
      .find(node=>node.textContent.trim()==='修改');
    button?.click();
    return Boolean(button);
  })()`);
  ensure(selectedForEdit, "正式组织没有可用的不可变 ID 修改入口");
  await admin.fillLabel(".tenant-drawer", "组织名称", renamedOrganization);
  await admin.click(".tenant-drawer button.primary", "保存修改");
  await admin.waitFor(
    `document.querySelector('.tenant-drawer')?.innerText.includes(${JSON.stringify(renamedOrganization)})===true`,
    "正式组织修改"
  );
  const disabledOrganization = await admin.evaluate(`(() => {
    const row=[...document.querySelectorAll('.tenant-drawer .organization-lifecycle li')]
      .find(node=>node.innerText.includes(${JSON.stringify(renamedOrganization)}));
    const button=[...(row?.querySelectorAll('button')??[])]
      .find(node=>node.textContent.trim()==='停用');
    button?.click();
    return Boolean(button);
  })()`);
  ensure(disabledOrganization, "空组织没有精确停用入口");
  await admin.waitFor(
    `(() => { const row=[...document.querySelectorAll('.tenant-drawer .organization-lifecycle li')].find(node=>node.innerText.includes(${JSON.stringify(renamedOrganization)})); return row?.innerText.includes('已停用')===true; })()`,
    "正式组织停用"
  );
  await admin.click(".tenant-drawer button", "关闭");
  await admin.click("nav button", "成员与入口资格");
  await admin.click("button", "添加成员");
  await admin.waitFor(
    "document.querySelector('.tenant-drawer select')!==null",
    "停用组织成员选择器"
  );
  ensure(
    await admin.evaluate(
      `![...document.querySelectorAll('.tenant-drawer select option')].some(node=>node.textContent.trim()===${JSON.stringify(renamedOrganization)})`
    ),
    "已停用组织仍进入正式成员选择器"
  );
  await admin.click(".tenant-drawer button", "关闭");
  await admin.click("nav button", "品牌资料库");
  await admin.click("button", "管理组织");
  await admin.waitFor(
    "document.querySelector('.tenant-drawer .organization-lifecycle')!==null",
    "组织恢复抽屉"
  );
  const restoredOrganization = await admin.evaluate(`(() => {
    const row=[...document.querySelectorAll('.tenant-drawer .organization-lifecycle li')]
      .find(node=>node.innerText.includes(${JSON.stringify(renamedOrganization)}));
    const button=[...(row?.querySelectorAll('button')??[])]
      .find(node=>node.textContent.trim()==='恢复');
    button?.click();
    return Boolean(button);
  })()`);
  ensure(restoredOrganization, "已停用组织没有精确恢复入口");
  await admin.waitFor(
    `(() => { const row=[...document.querySelectorAll('.tenant-drawer .organization-lifecycle li')].find(node=>node.innerText.includes(${JSON.stringify(renamedOrganization)})); return row?.innerText.includes('使用中')===true; })()`,
    "正式组织恢复"
  );
  record("ADMIN_ORGANIZATION_LIFECYCLE_BROWSER", {
    created: true,
    renamed_by_id: true,
    disabled: true,
    absent_from_new_member_selector: true,
    restored: true
  });
  await admin.click(".tenant-drawer button", "关闭");

  await admin.waitFor(
    "document.querySelectorAll('.publication-list > article').length>=2 && document.querySelectorAll('.product-list article').length===14",
    "正式发布投影与商品"
  );
  const publicationTruth = await admin.evaluate(`(() => {
    const versions=[...document.querySelectorAll('.publication-list > article')];
    const current=versions.find(node=>node.innerText.includes('当前使用'));
    const historical=versions.filter(node=>node.innerText.includes('历史版本'));
    const rows=[...(current?.querySelectorAll('li')??[])];
    return {
      referenceEntries:document.querySelectorAll('.library-list:not(.publication-list) article').length,
      products:document.querySelectorAll('.product-list article').length,
      currentVersion:document.querySelector('#brand-publication-title')?.parentElement?.innerText.includes(
        '当前 V'+${JSON.stringify(expectedCurrentProjection.new_projection_version)}
      )===true,
      currentItems:rows.length,
      allSourceBound:rows.every(node=>node.innerText.includes('来源：') && node.innerText.includes('适用：')),
      threeRoles:['公开品牌信息','表达边界','创作方法']
        .every(role=>rows.some(node=>node.innerText.includes(role))),
      baselineHistory:historical.some(node=>node.innerText.includes('表达边界'))
    };
  })()`);
  ensure(
    publicationTruth.products === 14 &&
      publicationTruth.currentVersion &&
      publicationTruth.currentItems === 8 &&
      publicationTruth.allSourceBound &&
      publicationTruth.threeRoles &&
      publicationTruth.baselineHistory,
    "正式发布投影的版本、来源、角色、适用范围或历史不完整"
  );
  record("ADMIN_PUBLICATION_PROJECTION", publicationTruth);

  await admin.click("nav button", "当前可用与待补");
  await admin.waitFor(
    "document.querySelectorAll('.capability-matrix tbody tr').length===58",
    "58 项四列真值矩阵"
  );
  const readinessTruth = await admin.evaluate(`(() => {
    const body=document.body.innerText;
    const allText=document.body.textContent;
    const gaps=[...document.querySelectorAll('.guide-gaps li')].map(node=>node.innerText);
    return {
      matrixRows:document.querySelectorAll('.capability-matrix tbody tr').length,
      sourceTruth:body.includes('5046') && body.includes('21') && body.includes('8'),
      gaps:['P4','P5','DM01'].every(id=>gaps.some(item=>item.includes(id))),
      roles:body.includes('笛语系统运维管理员') &&
        body.includes('笛语服饰租户管理员') &&
        body.includes('笛语服饰租户用户'),
      sendGenerate:body.includes('发送只进行普通交流，不建立任务、运行或版本。') &&
        body.includes('生成内容才建立正式任务、运行和不可变版本。'),
      p2BySku:allText.includes('DIYU-CSPU-004') &&
        allText.includes('每次任务只加载该 SKU 的事实') &&
        allText.includes('尚缺字段'),
      formallyTested:body.includes('同一候选正式实测 58 项'),
      serviceStates:['unknown','degraded','unavailable'].every(state=>allText.includes(state)),
      noAllReady:!body.includes('全部能力 ready')
    };
  })()`);
  ensure(
    readinessTruth.matrixRows === 58 &&
      readinessTruth.sourceTruth &&
      readinessTruth.gaps &&
      readinessTruth.roles &&
      readinessTruth.sendGenerate &&
      readinessTruth.p2BySku &&
      readinessTruth.formallyTested === expectFormallyTested &&
      readinessTruth.serviceStates &&
      readinessTruth.noAllReady,
    `管理员使用说明或四列真值矩阵与正式资料不一致：${JSON.stringify(readinessTruth)}`
  );
  record("ADMIN_READINESS_GUIDE", {
    ...readinessTruth,
    expectedFormallyTested: expectFormallyTested
  });

  const content = await createPage({ width: 768, height: 900 });
  await login(
    content,
    "/login",
    credentials.content_username,
    credentials.content_password,
    "/user"
  );
  await content.waitFor(
    "document.body.innerText.includes('开始创作')",
    "租户用户入口"
  );
  await content.click(".user-help summary", "使用说明");
  ensure(
    await content.evaluate(
      "document.querySelectorAll('.capability-matrix tbody tr').length===58 && document.body.innerText.includes('P5') && document.body.innerText.includes('DM01') && document.body.innerText.includes('DIYU-CSPU-004')"
    ),
    "租户用户简明帮助未读取共享动态真值"
  );
  record("USER_GUIDE", { shared_dynamic_truth: true, matrix_rows: 58 });
  await content.click("a", "开始创作");
  await content.waitFor(
    `location.pathname==='/content' && document.querySelector('textarea[aria-label="内容需求"]')!==null`,
    "正式内容工作台"
  );
  await content.click(".composer-context-basis summary", "本次依据");
  const contentScope = await content.evaluate(`({
    account:document.querySelector('select[aria-label="发布账号"]')?.selectedOptions[0]?.textContent.trim(),
    platforms:[...document.querySelector('select[aria-label="平台"]')?.options??[]]
      .map(item=>item.textContent.trim()),
    hasSend:[...document.querySelectorAll('.composer-submit button')].some(node=>node.textContent.trim()==='发送'),
    hasGenerate:[...document.querySelectorAll('.composer-submit button')].some(node=>node.textContent.includes('生成内容')),
    sourceDisclosure:document.querySelector('.composer-context-basis')?.innerText.includes('不会加载整库')===true
  })`);
  ensure(
    contentScope.account === "笛语服饰品牌内容账号" &&
      contentScope.platforms.includes("抖音") &&
      contentScope.platforms.includes("小红书") &&
      contentScope.platforms.includes("微信视频号") &&
      contentScope.hasSend &&
      contentScope.hasGenerate &&
      contentScope.sourceDisclosure,
    `发布账号、平台、发送/生成或最小充分上下文说明不完整：${JSON.stringify(contentScope)}`
  );
  record("CONTENT_SCOPE", contentScope);

  const factoryInput = "今天去工厂验厂，今年量装大货的车缝品质有了大幅度的提升";
  await content.fill('textarea[aria-label="内容需求"]', factoryInput);
  await content.click(".composer-submit button", "发送");
  await content.waitFor(
    "document.querySelector('.message.assistant')!==null",
    "普通发送结果",
    60000
  );
  ensure(
    !(await content.evaluate("document.querySelector('.creator-artifact')!==null")),
    "普通发送错误创建成品"
  );
  record("CONTENT_SEND_ONLY", { artifact_created: false, input_kind: "factory_actuality" });
  await wait(2200);
  await content.fill('textarea[aria-label="内容需求"]', factoryInput);
  await content.click(".composer-submit button.primary", "生成内容");
  await content.waitFor(
    "document.querySelector('.creator-artifact .eyebrow')?.textContent.includes('V1')",
    "精确验厂输入 V1",
    60000
  );
  await content.click(".artifact-context-basis summary", "本次依据");
  const v1 = await content.evaluate(`(() => {
    const pane=document.querySelector('.creator-artifact');
    return {
      body:pane?.innerText??'',
      content:[
        pane?.querySelector('.artifact-title h2')?.textContent.trim()??'',
        pane?.querySelector('.artifact-body')?.innerText.trim()??''
      ].join('\\n'),
      aigc:pane?.innerText.includes('AI 辅助生成')===true,
      context:pane?.querySelector('.artifact-context-basis')?.innerText??''
    };
  })()`);
  ensure(
    v1.body.includes("工厂") &&
      v1.body.includes("车缝") &&
      v1.body.includes("提升") &&
      v1.aigc === expectAigc &&
      v1.context.includes("品牌资料") &&
      v1.context.includes("本次未使用"),
    `精确验厂 V1 的用户事实、AIGC 或非商品边界不完整：${JSON.stringify({
      userActuality:
        v1.body.includes("工厂") &&
        v1.body.includes("车缝") &&
        v1.body.includes("提升"),
      aigc: v1.aigc,
      context: v1.context
    })}`
  );
  record("FACTORY_V1", {
    body_sha256: digest(v1.body),
    user_actuality_visible: true,
    product_fact_used: false,
    aigc: v1.aigc,
    model_quality_proven: expectAigc,
    evidence_scope: expectAigc
      ? "frozen_candidate_provider_writer"
      : "controlled_pre_freeze_writer"
  });
  await wait(2200);
  await content.fill(
    'textarea[aria-label="修改要求"]',
    "保留事实不变，把开头改得更自然、更像短视频口播。"
  );
  await content.click(".composer-submit button.primary", "修改成 V2");
  await content.waitFor(
    "document.querySelector('.creator-artifact .eyebrow')?.textContent.includes('V2')",
    "自然修改 V2",
    60000
  );
  const v2Content = await content.evaluate(`(() => {
    const pane=document.querySelector('.creator-artifact');
    return [
      pane?.querySelector('.artifact-title h2')?.textContent.trim()??'',
      pane?.querySelector('.artifact-body')?.innerText.trim()??''
    ].join('\\n');
  })()`);
  ensure(v2Content !== v1.content, "修改要求没有形成不同的 V2 成品");
  await content.click(".version-history summary", "历史版本");
  await content.click(".version-history button", "V1");
  ensure(
    await content.evaluate(
      "document.querySelector('.history-reading')?.innerText.includes('当前版仍是 V2')===true"
    ),
    "V1 回读没有保留当前 V2 身份"
  );
  const v1Again = await content.evaluate(`(() => {
    const pane=document.querySelector('.creator-artifact');
    return [
      pane?.querySelector('.artifact-title h2')?.textContent.trim()??'',
      pane?.querySelector('.artifact-body')?.innerText.trim()??''
    ].join('\\n');
  })()`);
  await content.click(".history-reading button", "回到当前版");
  ensure(
    v1Again === v1.content &&
      (await content.evaluate(
        "document.querySelector('.creator-artifact .eyebrow')?.textContent.includes('当前版本')===true"
      )) &&
      (await content.evaluate(`(() => {
        const pane=document.querySelector('.creator-artifact');
        return [
          pane?.querySelector('.artifact-title h2')?.textContent.trim()??'',
          pane?.querySelector('.artifact-body')?.innerText.trim()??''
        ].join('\\n')===${JSON.stringify(v2Content)};
      })()`)),
    "V1→V2→V1→V2 回读发生漂移"
  );
  await content.click(".artifact-actions button", "复制");
  await content.waitFor(
    "document.body.textContent.includes('已复制 V2 全文')",
    "复制当前 V2"
  );
  await send("Browser.setDownloadBehavior", {
    behavior: "allow",
    downloadPath: profile,
    browserContextId: content.browserContextId
  });
  await content.click(".artifact-actions button", "导出");
  await content.waitFor(
    "document.body.textContent.includes('已导出 V2')",
    "导出当前 V2"
  );
  record("CONTENT_V2_HISTORY_COPY_EXPORT", {
    v1_sha256: digest(v1Again),
    v2_sha256: digest(v2Content),
    immutable_difference: true,
    copy: true,
    export: true
  });

  await content.setViewport(390, 844);
  await content.waitFor(
    "document.querySelector('.mobile-work-tabs')!==null",
    "移动双工作面"
  );
  const mobileTruth = await content.evaluate(`(() => {
    const buttons=[...document.querySelectorAll('.mobile-work-tabs button')];
    const touch=[...document.querySelectorAll('.mobile-work-tabs button,.composer-submit button')]
      .filter(node=>node.getClientRects().length>0)
      .every(node=>node.getBoundingClientRect().height>=44);
    return {
      tabs:buttons.map(node=>node.textContent.trim()),
      overflow:document.documentElement.scrollWidth-document.documentElement.clientWidth,
      touch
    };
  })()`);
  ensure(
    mobileTruth.tabs.includes("对话") &&
      mobileTruth.tabs.includes("成品") &&
      mobileTruth.overflow <= 1 &&
      mobileTruth.touch,
    `390×844 双工作面、44px 触控或横向溢出不合格：${JSON.stringify(mobileTruth)}`
  );
  await content.click(".mobile-work-tabs button", "对话");
  const focusTruth = await content.evaluate(`(() => {
    const button=[...document.querySelectorAll('.composer-submit button')]
      .find(node=>getComputedStyle(node).display!=='none');
    button?.focus();
    const style=button?getComputedStyle(button):null;
    return {
      focused:document.activeElement===button,
      visible:Boolean(style) &&
        (style.outlineStyle!=='none' || style.boxShadow!=='none')
    };
  })()`);
  ensure(focusTruth.focused && focusTruth.visible, "键盘焦点不可见");
  await content.setViewport(768, 900);
  const mediumOverflow = await content.evaluate(
    "document.documentElement.scrollWidth-document.documentElement.clientWidth"
  );
  await content.setViewport(1440, 900);
  await content.setScale(2);
  const zoomOverflow = await content.evaluate(
    "document.documentElement.scrollWidth-document.documentElement.clientWidth"
  );
  await content.setScale(1);
  ensure(mediumOverflow <= 1 && zoomOverflow <= 1, "768 或 200% 等效缩放出现横向溢出");
  record("RESPONSIVE_ACCESSIBILITY", {
    viewports: ["1440x900", "768x900", "390x844", "200%"],
    keyboard_focus: true,
    touch_44px: true,
    horizontal_overflow: false
  });

  await content.click(".composer-submit button", "另起一条");
  const draft = "这是一条切换平台后必须保留的未提交输入";
  await content.fill('textarea[aria-label="内容需求"]', draft);
  await content.selectText('select[aria-label="平台"]', "小红书");
  await content.waitFor(
    `location.pathname==='/content' && document.querySelector('textarea[aria-label="内容需求"]')?.value.length>0`,
    "平台切换后恢复草稿"
  );
  ensure(
    await content.evaluate(
      `document.querySelector('textarea[aria-label="内容需求"]')?.value===${JSON.stringify(draft)}`
    ),
    "账号/平台切换丢失未提交输入"
  );
  record("CONTENT_DRAFT_PERSISTENCE", { platform_switch: true, draft_preserved: true });

  await content.navigate("/display");
  await content.waitFor("document.body!==null", "无 DM01 权限路径");
  const displayDeniedText = await content.evaluate("document.body.innerText");
  ensure(
    displayDeniedText.includes("陈列") || displayDeniedText.includes("权限"),
    "无门店/无资格 DM01 路径没有给出可理解结果"
  );
  await content.navigate("/user");
  await content.waitFor(
    "document.body.innerText.includes('开始创作')",
    "权限拒绝后会话保持"
  );
  record("PERMISSION_DENIAL_SESSION", {
    display_denied: true,
    session_preserved: true,
    login_redirected: false
  });

  const unexpectedExternalRequests = [...requestedUrls].filter(value => {
    if (!value) return false;
    if (value.startsWith(baseUrl)) return false;
    return !["data:", "blob:", "about:"].some(prefix => value.startsWith(prefix));
  });
  const expectedNegativeLogs = consoleErrors.filter(entry =>
    typeof entry === "object" &&
    entry?.kind === "log-error" &&
    entry?.source === "network" &&
    entry?.url === "<local>/display" &&
    entry?.text.includes("422")
  );
  const unexpectedConsoleErrors = consoleErrors.filter(
    entry => !expectedNegativeLogs.includes(entry)
  );
  ensure(
    expectedNegativeLogs.length === 1 && unexpectedConsoleErrors.length === 0,
    `正式浏览器出现意外控制台错误：${JSON.stringify(consoleErrors)}`
  );
  ensure(
    unexpectedExternalRequests.length === 0,
    "正式浏览器出现意外外部请求"
  );
  record("BROWSER_SAFETY", {
    console_errors: 0,
    expected_negative_network_logs: expectedNegativeLogs.length,
    unexpected_external_requests: 0
  });

  const output = {
    schema_version: "tenant01-formal-browser-evidence-v1",
    candidate_sha: candidateSha,
    tenant_id: credentials.tenant_id,
    chrome_binary: chromePath,
    checks,
    viewports: ["1440x900", "768x900", "390x844", "200%"],
    console_errors: unexpectedConsoleErrors,
    expected_negative_network_logs: expectedNegativeLogs,
    unexpected_external_requests: unexpectedExternalRequests,
    raw_source_text_logged: false,
    credentials_logged: false,
    verdict: "PASS"
  };
  mkdirSync(dirname(outputPath), { recursive: true, mode: 0o700 });
  chmodSync(dirname(outputPath), 0o700);
  writeFileSync(outputPath, JSON.stringify(output, null, 2) + "\n", {
    encoding: "utf8",
    mode: 0o600,
    flag: "wx"
  });
  chmodSync(outputPath, 0o600);
} finally {
  if (socket?.readyState === WebSocket.OPEN) socket.close();
  if (!chrome.killed) chrome.kill("SIGTERM");
  await wait(100);
  rmSync(profile, { recursive: true, force: true });
}
