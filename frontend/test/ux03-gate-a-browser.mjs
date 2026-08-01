import { spawn } from "node:child_process";
import { existsSync, mkdtempSync, rmSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const required = name => {
  const value = process.env[name];
  if (!value) throw new Error(`缺少 ${name}`);
  return value;
};

const baseUrl = required("UX03_BASE_URL").replace(/\/$/, "");
const publicUrl = required("UX03_PUBLIC_URL").replace(/\/$/, "");
const activationPath = required("UX03_ADMIN_ACTIVATION_PATH");
const adminUsername = required("UX03_ADMIN_USERNAME");
const adminPassword = required("UX03_ADMIN_PASSWORD");
const suffix = required("UX03_SUFFIX");
const hqUsername = `ux03-browser-hq-${suffix}`;
const storeUsername = `ux03-browser-store-${suffix}`;
const hqPassword = `UX03-browser-HQ-${suffix}-password`;
const storePassword = `UX03-browser-store-${suffix}-password`;
const hqDisplayName = `总部内容用户 ${suffix}`;
const storeDisplayName = `门店内容用户 ${suffix}`;
const storeOrganizationName = `UX03 浏览器门店 ${suffix}`;
const hqAccountName = `总部逻辑发布账号 ${suffix}`;
const storeAccountName = `门店逻辑发布账号 ${suffix}`;
const repo = resolve(fileURLToPath(new URL("../..", import.meta.url)));
const chromeCandidates = [
  process.env.UX03_CHROME,
  "/usr/bin/google-chrome",
  "/usr/bin/chromium",
  "/home/faye/.cache/puppeteer/chrome/linux-148.0.7778.97/chrome-linux64/chrome"
].filter(Boolean);
const chromePath = chromeCandidates.find(
  path => existsSync(path) && statSync(path).isFile()
);
if (!chromePath) throw new Error("未找到本机 Chrome");

const { default: WebSocket } = await import(
  pathToFileURL(join(repo, "frontend", "node_modules", "ws", "index.js")).href
);
const profile = mkdtempSync(join(tmpdir(), "ux03-gate-a-browser-"));
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
          // A navigation may briefly expose no execution context.
        }
        await wait(100);
      }
      const body = await evaluate(
        "document.body?.innerText.slice(0, 900) ?? ''"
      );
      const location = await evaluate(
        "location.pathname + location.search"
      );
      throw new Error(`等待超时：${label}；当前 ${location}；页面：${body}`);
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
          node,
          ${JSON.stringify(value)}
        );
        node.dispatchEvent(new Event('input',{bubbles:true}));
        node.dispatchEvent(new Event('change',{bubbles:true}));
        return true;
      })()`);
      ensure(changed, `找不到输入控件 ${selector}`);
    };
    const labeledControl = async (label, selector, value) => {
      const changed = await evaluate(`(() => {
        const labels=[...document.querySelectorAll('.tenant-drawer label')];
        const wrapper=labels.find(
          node=>node.textContent.trim().startsWith(${JSON.stringify(label)})
        );
        const control=wrapper?.querySelector(${JSON.stringify(selector)});
        if(!control)return {changed:false,labels:labels.map(node=>node.textContent.trim())};
        if(control.tagName==='SELECT'){
          const option=[...control.options].find(
            item=>item.textContent.trim()===${JSON.stringify(value)}
              || item.textContent.includes(${JSON.stringify(value)})
          );
          if(!option)return {changed:false,options:[...control.options].map(item=>item.textContent.trim())};
          Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value')
            .set.call(control,option.value);
        }else{
          const owner=control.tagName==='TEXTAREA'
            ? HTMLTextAreaElement.prototype
            : HTMLInputElement.prototype;
          Object.getOwnPropertyDescriptor(owner,'value').set.call(
            control,
            ${JSON.stringify(value)}
          );
        }
        control.dispatchEvent(new Event('input',{bubbles:true}));
        control.dispatchEvent(new Event('change',{bubbles:true}));
        return {changed:true};
      })()`);
      ensure(changed?.changed, `无法设置 ${label}：${JSON.stringify(changed)}`);
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
    const clickIn = async (containerSelector, containerText, buttonText) => {
      const clicked = await evaluate(`(() => {
        const container=[...document.querySelectorAll(${JSON.stringify(containerSelector)})]
          .find(node=>node.textContent.includes(${JSON.stringify(containerText)}));
        const button=[...(container?.querySelectorAll('button')??[])]
          .find(node=>node.textContent.trim().includes(${JSON.stringify(buttonText)}));
        if(!button)return false;
        button.scrollIntoView({block:'center',inline:'nearest'});
        button.click();
        return true;
      })()`);
      ensure(clicked, `无法在 ${containerText} 中点击 ${buttonText}`);
      await wait(100);
    };
    const toggleLabeledCheckbox = async label => {
      const toggled = await evaluate(`(() => {
        const wrapper=[...document.querySelectorAll('.tenant-drawer label')]
          .find(node=>node.textContent.includes(${JSON.stringify(label)}));
        const input=wrapper?.querySelector('input[type=checkbox],input[type=radio]');
        if(!input)return false;
        input.click();
        return input.checked;
      })()`);
      ensure(toggled, `无法选择 ${label}`);
    };
    const setViewport = async (width, height) => {
      await send(
        "Emulation.setDeviceMetricsOverride",
        { width, height, deviceScaleFactor: 1, mobile: width <= 640 },
        sessionId
      );
      await wait(100);
    };
    return {
      browserContextId: context.browserContextId,
      sessionId,
      evaluate,
      waitFor,
      navigate,
      fill,
      labeledControl,
      click,
      clickIn,
      toggleLabeledCheckbox,
      setViewport
    };
  };

  const activateAndLogin = async (
    page,
    path,
    username,
    password,
    loginPath
  ) => {
    await page.navigate(path);
    await page.waitFor(
      "document.querySelector('input[name=password_confirm]') !== null",
      "一次性激活页"
    );
    await page.fill('input[name="password"]', password);
    await page.fill('input[name="password_confirm"]', password);
    await page.click('button[type="submit"]', "完成设置");
    await page.waitFor(
      `location.pathname === ${JSON.stringify(loginPath)}`,
      "激活后登录入口"
    );
    await page.waitFor(
      "document.querySelector('input[name=username]') !== null",
      "登录表单"
    );
    await page.fill('input[name="username"]', username);
    await page.fill('input[name="password"]', password);
    await page.click('button[type="submit"]', "登录");
  };

  const admin = await createPage();
  await activateAndLogin(
    admin,
    activationPath,
    adminUsername,
    adminPassword,
    "/tenant-admin/login"
  );
  await admin.waitFor(
    "location.pathname === '/tenant-admin' && document.body.innerText.includes('发布账号与账号画像')",
    "管理员正式入口"
  );
  ensure(
    !(await admin.evaluate(
      "document.body.innerText.includes('开始创作')"
    )),
    "管理员页面不应出现创作入口"
  );

  await admin.click("nav button", "发布账号与账号画像");
  await admin.waitFor(
    "document.querySelector('.brand-expression-baseline textarea') !== null",
    "品牌表达基线草案"
  );
  ensure(
    await admin.evaluate(
      "[...document.querySelectorAll('button')].find(node=>node.textContent.includes('创建发布账号'))?.disabled===true"
    ),
    "未确认品牌基线时创建账号没有失败关闭"
  );
  const baselineDraft = await admin.evaluate(
    "document.querySelector('.brand-expression-baseline textarea').value"
  );
  ensure(baselineDraft.length > 20, "系统没有给出确定性品牌表达草案");
  await admin.fill(
    ".brand-expression-baseline textarea",
    `${baselineDraft}\n管理员确认：总部与门店只陈述各自有来源的现实。`
  );
  await admin.click(
    ".brand-expression-baseline button",
    "确认当前品牌表达"
  );
  await admin.waitFor(
    "document.body.innerText.includes('当前确认版本 V1')",
    "品牌表达基线正式确认"
  );
  ensure(
    await admin.evaluate(
      "[...document.querySelectorAll('button')].find(node=>node.textContent.includes('创建发布账号'))?.disabled===false"
    ),
    "品牌基线确认后仍不能创建账号"
  );
  record("品牌表达基线草案、修订、确认与回读", {
    deterministic_prefill: true,
    confirmed_version: 1
  });

  await admin.click("nav button", "品牌资料库");
  await admin.waitFor(
    "document.querySelectorAll('.library-list article').length===21 && document.querySelectorAll('.product-list article').length===14",
    "21 份源文档与 14 个候选商品正式回读"
  );
  ensure(
    await admin.evaluate(
      "[...document.querySelectorAll('.library-list article')].every(node=>node.innerText.includes('源文档'))"
    ),
    "授权批次没有以可追溯源文档呈现"
  );
  record("TENANT-01 授权源资料与候选商品回读", {
    source_documents: 21,
    candidate_products: 14,
    private_text_logged: false
  });
  await admin.click("nav button", "当前可用与待补");
  await admin.waitFor(
    `(() => {
      const item=[...document.querySelectorAll('[aria-labelledby="tenant-data-readiness-title"] .readiness-list article')]
        .find(node=>node.innerText.includes('P5 商品视觉'));
      return item?.innerText.includes('当前缺资料') &&
        item?.innerText.includes('至少为两件不同商品登记并明确选择真实图片或视频') &&
        item?.innerText.includes('不影响 P1—P4 与纯文字内容');
    })()`,
    "P5 无真实媒体的局部资料缺口"
  );
  ensure(
    await admin.evaluate(
      "document.querySelector('[aria-labelledby=software-readiness-title]')?.innerText.includes('58 项真实可用')"
    ),
    "资料缺口错误降低了软件功能真值"
  );
  record("软件能力与笛语服饰资料就绪度分离", {
    software_truth: "58/0/0/6/0",
    p5: "data_missing",
    p5_scope: "只影响商品视觉"
  });
  await admin.click("nav button", "品牌资料库");
  await admin.waitFor(
    "document.querySelectorAll('.library-list article').length===21",
    "返回品牌资料库"
  );
  await admin.click("button", "新增资料");
  await admin.waitFor(
    "document.querySelector('.tenant-drawer')?.innerText.includes('新增品牌资料')",
    "新增资料抽屉"
  );
  await admin.labeledControl("可用范围", "select", "指定区域");
  await admin.click(".tenant-drawer button", "需要新的组织");
  await admin.waitFor(
    "document.querySelector('.tenant-drawer')?.innerText.includes('建立组织')",
    "建立组织抽屉"
  );
  await admin.labeledControl("组织名称", "input", storeOrganizationName);
  await admin.labeledControl(
    "组织层级",
    "select",
    "经营单位 / 门店"
  );
  await admin.click(".tenant-drawer button.primary", "建立组织");
  await admin.waitFor(
    "document.body.innerText.includes('组织已建立。它的层级来自你的明确选择')",
    "门店组织建立反馈"
  );
  await admin.click(".tenant-drawer button", "关闭");

  const createMember = async ({
    displayName,
    username,
    organizationLabel
  }) => {
    await admin.click("nav button", "成员与入口资格");
    await admin.click("button", "添加成员");
    await admin.waitFor(
      "document.querySelector('.tenant-drawer') !== null",
      "添加成员抽屉"
    );
    await admin.labeledControl("姓名或工作名", "input", displayName);
    await admin.labeledControl("登录用户名", "input", username);
    await admin.labeledControl("所属组织", "select", organizationLabel);
    ensure(
      await admin.evaluate(`(() => {
        const label=[...document.querySelectorAll('.tenant-drawer label')]
          .find(node=>node.textContent.trim()==='内容创作');
        const input=label?.querySelector('input[type=checkbox]');
        if(!input)return false;
        if(input.checked)input.click();
        return input.checked===false;
      })()`),
      "无法在账号建立前关闭内容创作资格"
    );
    await admin.click(
      ".tenant-drawer button.primary",
      "创建并生成一次性激活链接"
    );
    await admin.waitFor(
      "document.querySelector('.one-time-link code') !== null",
      "成员完整激活链接"
    );
    const value = await admin.evaluate(
      "document.querySelector('.one-time-link code')?.textContent.trim()"
    );
    ensure(
      value.startsWith(`${publicUrl}/activate/`),
      "成员激活链接不是完整可信 URL"
    );
    await admin.click(".tenant-drawer button", "关闭");
    return new URL(value).pathname;
  };

  await admin.click("nav button", "成员与入口资格");
  await admin.click("button", "添加成员");
  await admin.waitFor(
    "document.querySelector('.tenant-drawer select')?.options.length > 1",
    "总部组织选择"
  );
  const companyName = await admin.evaluate(
    "document.querySelector('.tenant-drawer select').options[1].textContent.trim()"
  );
  await admin.click(".tenant-drawer button", "关闭");
  const hqActivationPath = await createMember({
    displayName: hqDisplayName,
    username: hqUsername,
    organizationLabel: companyName
  });
  const storeActivationPath = await createMember({
    displayName: storeDisplayName,
    username: storeUsername,
    organizationLabel: storeOrganizationName
  });
  record("两个自然人及所属组织", {
    headquarters: companyName,
    store: storeOrganizationName
  });

  const createAccount = async ({
    name,
    role,
    organization,
    target
  }) => {
    await admin.click("nav button", "发布账号与账号画像");
    await admin.click("button", "创建发布账号");
    await admin.waitFor(
      "document.querySelector('.tenant-drawer')?.innerText.includes('账号画像')",
      "创建发布账号抽屉"
    );
    await admin.labeledControl("发布账号名称", "input", name);
    await admin.labeledControl("账号类型短标签", "input", role);
    await admin.labeledControl("负责团队", "select", organization);
    ensure(
      !(await admin.evaluate(
        "document.querySelector('.tenant-drawer')?.innerText.includes('首位使用者')"
      )),
      "创建发布账号不应静默绑定成员或画像维护资格"
    );
    await admin.labeledControl("首个平台", "select", target);
    const profileValues = await admin.evaluate(`(() => {
      const fields=[...document.querySelectorAll('.tenant-drawer fieldset textarea')];
      return fields.map(item=>item.value);
    })()`);
    ensure(
      profileValues.length === 5 && profileValues.every(value => value.trim()),
      "五段画像候选没有完整预填"
    );
    await admin.click(".tenant-drawer button.primary", "创建发布账号");
    await admin.waitFor(
      `document.body.innerText.includes(${JSON.stringify(name)}) && !document.querySelector('.tenant-drawer')`,
      "发布账号正式回读"
    );
  };

  await createAccount({
    name: hqAccountName,
    role: "总部品牌表达",
    organization: companyName,
    target: "抖音 · 视频"
  });
  await createAccount({
    name: storeAccountName,
    role: "门店内容表达",
    organization: storeOrganizationName,
    target: "小红书 · 图文 / 视频"
  });

  const addPlatform = async (accountName, target) => {
    await admin.clickIn(
      ".publishing-account-list > article",
      accountName,
      "添加平台"
    );
    await admin.waitFor(
      "document.querySelector('.tenant-drawer') !== null",
      "添加平台抽屉"
    );
    await admin.labeledControl("平台及其可用形式", "select", target);
    ensure(
      !(await admin.evaluate(
        "document.querySelector('.tenant-drawer')?.innerText.includes('使用者')"
      )),
      "添加平台不应改变成员资格"
    );
    await admin.click(".tenant-drawer button.primary", "添加平台");
    await admin.waitFor(
      "!document.querySelector('.tenant-drawer')",
      `添加平台 ${target}`
    );
  };
  await addPlatform(hqAccountName, "小红书 · 图文 / 视频");
  await addPlatform(hqAccountName, "微信视频号 · 视频");
  const accountProjection = await admin.evaluate(`(() => {
    const account=[...document.querySelectorAll('.publishing-account-list > article')]
      .find(node=>node.textContent.includes(${JSON.stringify(hqAccountName)}));
    return account?.innerText ?? '';
  })()`);
  ensure(accountProjection.includes("抖音视频"), "总部账号缺少抖音目标");
  ensure(accountProjection.includes("小红书图文"), "总部账号缺少小红书图文");
  ensure(accountProjection.includes("小红书视频"), "总部账号缺少小红书视频");
  ensure(accountProjection.includes("微信视频号"), "微信视频号映射错误");
  ensure(!accountProjection.includes("微信号"), "非法微信号映射仍存在");
  ensure(
    accountProjection.match(/账号画像 V1/g)?.length === 1,
    "多平台错误复制了账号画像"
  );
  record("一个逻辑发布账号的多平台与五段画像 V1", {
    targets: 4,
    profile_copies: 1,
    wechat_label: "微信视频号"
  });

  const assignMember = async ({
    displayName,
    accountName,
    maintenance
  }) => {
    await admin.click("nav button", "成员与入口资格");
    await admin.clickIn(".tenant-list article", displayName, "查看与处理");
    await admin.waitFor(
      "document.querySelector('.tenant-drawer') !== null",
      "成员资格抽屉"
    );
    ensure(
      await admin.evaluate(`(() => {
        const label=[...document.querySelectorAll('.tenant-drawer label')]
          .find(node=>node.textContent.trim()==='内容创作');
        const input=label?.querySelector('input[type=checkbox]');
        if(!input)return false;
        if(!input.checked)input.click();
        return input.checked===true;
      })()`),
      "无法分配内容创作资格"
    );
    ensure(
      await admin.evaluate(`(() => {
        const label=[...document.querySelectorAll('.tenant-drawer label')]
          .find(node=>node.textContent.includes(${JSON.stringify(`使用 ${accountName}`)}));
        const input=label?.querySelector('input[type=checkbox]');
        if(!input)return false;
        if(!input.checked)input.click();
        return input.checked===true;
      })()`),
      `无法分配 ${accountName} 使用资格`
    );
    if (maintenance) {
      ensure(
        await admin.evaluate(`(() => {
          const labels=[...document.querySelectorAll('.tenant-drawer label')]
            .filter(node=>node.textContent.includes('可维护五段画像'));
          const input=labels.at(-1)?.querySelector('input[type=checkbox]');
          if(!input)return false;
          if(!input.checked)input.click();
          return input.checked===true;
        })()`),
        "无法分配五段画像维护资格"
      );
    }
    await admin.click(".tenant-drawer button.primary", "保存入口资格");
    await admin.waitFor(
      "document.body.innerText.includes('成员资格已更新')",
      "成员工作资格保存"
    );
    await admin.click(".tenant-drawer button", "关闭");
  };
  await assignMember({
    displayName: hqDisplayName,
    accountName: hqAccountName,
    maintenance: false
  });
  await assignMember({
    displayName: storeDisplayName,
    accountName: storeAccountName,
    maintenance: true
  });
  record("使用资格与画像维护资格独立", {
    headquarters_maintenance: false,
    store_maintenance: true
  });

  await admin.click("nav button", "发布账号与账号画像");
  await admin.clickIn(
    ".publishing-account-list > article",
    hqAccountName,
    "停用账号"
  );
  await admin.waitFor(
    `(() => {
      const card=[...document.querySelectorAll('.publishing-account-list > article')]
        .find(node=>node.textContent.includes(${JSON.stringify(hqAccountName)}));
      return card?.innerText.includes('已停用');
    })()`,
    "发布账号停用"
  );
  await admin.click("nav button", "成员与入口资格");
  await admin.clickIn(".tenant-list article", hqDisplayName, "查看与处理");
  await admin.waitFor(
    "document.querySelector('.tenant-drawer')?.innerText.includes('已停用，不能用于新工作')",
    "成员抽屉保留停用账号授权"
  );
  ensure(
    await admin.evaluate(`(() => {
      const label=[...document.querySelectorAll('.tenant-drawer label')]
        .find(node=>node.textContent.includes(${JSON.stringify(`使用 ${hqAccountName}`)}));
      const input=label?.querySelector('input[type=checkbox]');
      return input?.checked===true && input.disabled===false;
    })()`),
    "已有停用账号授权不能被显式保留或移除"
  );
  await admin.click(".tenant-drawer button.primary", "保存入口资格");
  await admin.waitFor(
    "document.body.innerText.includes('成员资格已更新')",
    "停用账号存在时编辑成员"
  );
  await admin.click(".tenant-drawer button", "关闭");
  await admin.click("nav button", "发布账号与账号画像");
  await admin.clickIn(
    ".publishing-account-list > article",
    hqAccountName,
    "恢复账号"
  );
  await admin.waitFor(
    `(() => {
      const card=[...document.querySelectorAll('.publishing-account-list > article')]
        .find(node=>node.textContent.includes(${JSON.stringify(hqAccountName)}));
      return card?.innerText.includes('已启用');
    })()`,
    "发布账号恢复"
  );
  record("停用账号授权与成员编辑接缝", {
    disabled_grant_visible: true,
    unrelated_edit_saved: true,
    historical_grant_preserved: true
  });

  const inspectUser = async ({
    activation,
    username,
    password,
    displayName,
    organization,
    accountName,
    expectedPlatforms,
    width,
    canMaintain
  }) => {
    const user = await createPage({ width, height: width <= 640 ? 844 : 900 });
    await activateAndLogin(
      user,
      activation,
      username,
      password,
      "/login"
    );
    await user.waitFor(
      "location.pathname === '/user' && document.body.innerText.includes('开始创作')",
      "租户用户正式入口"
    );
    const portalText = await user.evaluate("document.body.innerText");
    ensure(portalText.includes(displayName), "自然人投影不正确");
    ensure(portalText.includes(organization), "所属组织投影不正确");
    ensure(
      !portalText.includes("成员与入口资格"),
      "租户用户错误进入管理职责"
    );
    await user.click("a", "开始创作");
    await user.waitFor(
      "location.pathname === '/content' && document.querySelector('select[aria-label=\"发布账号\"]') !== null",
      "正式创作端账号选择"
    );
    const scope = await user.evaluate(`(() => ({
      account:document.querySelector('select[aria-label="发布账号"]')?.selectedOptions[0]?.textContent.trim(),
      platforms:[...document.querySelector('select[aria-label="平台"]')?.options??[]]
        .map(item=>item.textContent.trim()),
      pageWidth:document.documentElement.scrollWidth,
      viewport:window.innerWidth
    }))()`);
    ensure(scope.account?.includes(accountName), "获准逻辑发布账号投影错误");
    for (const platform of expectedPlatforms) {
      ensure(
        scope.platforms.includes(platform),
        `缺少获准内容目标 ${platform}`
      );
    }
    if (expectedPlatforms.length === 1 && expectedPlatforms[0] === "小红书") {
      const formats = await user.evaluate(
        "[...document.querySelector('select[aria-label=\"内容形式\"]').options].map(item=>item.value)"
      );
      ensure(
        formats.includes("xiaohongshu_graphic") &&
          formats.includes("xiaohongshu_video"),
        "小红书图文和视频没有共享同一逻辑账号"
      );
    }
    ensure(scope.pageWidth <= scope.viewport + 1, "页面出现横向溢出");
    const originalAccount = scope.account;
    if (scope.platforms.length > 1) {
      await user.evaluate(`(() => {
        const select=document.querySelector('select[aria-label="平台"]');
        select.value=select.options[1].value;
        select.dispatchEvent(new Event('change',{bubbles:true}));
      })()`);
      await user.waitFor(
        "document.querySelector('select[aria-label=\"平台\"]')?.selectedIndex===1",
        "切换平台与形式"
      );
      ensure(
        (await user.evaluate(
          "document.querySelector('select[aria-label=\"发布账号\"]')?.selectedOptions[0]?.textContent.trim()"
        )) === originalAccount,
        "切换平台错误切换了逻辑发布账号"
      );
    }
    await user.click("button.identity-trigger");
    await user.waitFor(
      "document.querySelector('.account-drawer') !== null",
      "只读账号画像"
    );
    const identity = await user.evaluate(
      "document.querySelector('.account-drawer')?.innerText"
    );
    ensure(identity.includes(organization), "负责团队错误使用登录人组织");
    ensure(identity.includes("V1"), "账号画像版本投影缺失");
    ensure(
      identity.includes("维护账号画像") === canMaintain,
      "画像维护动作没有按照可信授权投影"
    );
    const focused = await user.evaluate(`(() => {
      const node=document.activeElement;
      if(!node)return false;
      const style=getComputedStyle(node);
      return node.isConnected &&
        (style.outlineStyle!=='none' || style.boxShadow!=='none');
    })()`);
    ensure(focused, "抽屉焦点不可见");
    return user;
  };

  const hqUser = await inspectUser({
    activation: hqActivationPath,
    username: hqUsername,
    password: hqPassword,
    displayName: hqDisplayName,
    organization: companyName,
    accountName: hqAccountName,
    expectedPlatforms: [
      "抖音",
      "小红书",
      "微信视频号"
    ],
    width: 1440,
    canMaintain: false
  });
  const storeUser = await inspectUser({
    activation: storeActivationPath,
    username: storeUsername,
    password: storePassword,
    displayName: storeDisplayName,
    organization: storeOrganizationName,
    accountName: storeAccountName,
    expectedPlatforms: ["小红书"],
    width: 390,
    canMaintain: true
  });
  await storeUser.click(".account-drawer button", "维护账号画像");
  await storeUser.waitFor(
    "document.querySelectorAll('.account-profile-editor textarea').length===5",
    "五段画像编辑器"
  );
  ensure(
    await storeUser.evaluate(`(() => {
      const textarea=document.querySelectorAll('.account-profile-editor textarea')[3];
      if(!textarea)return false;
      Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value')
        .set.call(textarea,'门店日常、在地回应和已确认商品取舍。');
      textarea.dispatchEvent(new Event('input',{bubbles:true}));
      textarea.dispatchEvent(new Event('change',{bubbles:true}));
      return true;
    })()`),
    "无法编辑当前账号五段画像"
  );
  await storeUser.click(".account-profile-editor button.primary", "保存为 V2");
  await storeUser.waitFor(
    "document.querySelector('.account-drawer')?.innerText.includes('账号定位 · V2')",
    "内容用户保存画像 V2"
  );
  await storeUser.click(".account-drawer button[aria-label=关闭]");
  await storeUser.evaluate(`(() => {
    const select=document.querySelector('select[aria-label="内容形式"]');
    select.value='xiaohongshu_video';
    select.dispatchEvent(new Event('change',{bubbles:true}));
  })()`);
  await storeUser.waitFor(
    "new URLSearchParams(location.search).get('target')==='xiaohongshu_video' && document.querySelector('button.identity-trigger') !== null",
    "同一账号切换小红书形式"
  );
  await storeUser.click("button.identity-trigger");
  await storeUser.waitFor(
    "document.querySelector('.account-drawer')?.innerText.includes('V2') && document.querySelector('.account-drawer')?.innerText.includes('门店日常、在地回应和已确认商品取舍。')",
    "跨形式共享同一画像 V2"
  );
  record("内容用户画像 V1 到 V2 与跨平台共享", {
    maintenance_consumer: true,
    current_version: 2,
    shared_logical_account: true
  });
  await admin.setViewport(768, 900);
  ensure(
    await admin.evaluate(
      "document.documentElement.scrollWidth <= window.innerWidth + 1"
    ),
    "768px 管理端横向溢出"
  );
  await admin.setViewport(390, 844);
  ensure(
    await admin.evaluate(
      "document.documentElement.scrollWidth <= window.innerWidth + 1"
    ),
    "390px 管理端横向溢出"
  );
  await send(
    "Emulation.setPageScaleFactor",
    { pageScaleFactor: 2 },
    admin.sessionId
  );
  ensure(
    await admin.evaluate(
      "document.documentElement.scrollWidth <= window.innerWidth + 1"
    ),
    "200% 等效缩放出现页面级横向溢出"
  );
  record("正式身份投影、平台切换与响应式", {
    desktop: "1440x900",
    intermediate: "768x900",
    mobile: "390x844",
    zoom: "200%",
    logical_account_unchanged: true
  });

  const baseOrigin = new URL(baseUrl).origin;
  const externalRequests = events
    .filter(event => event.method === "Network.requestWillBeSent")
    .map(event => event.params?.request?.url)
    .filter(Boolean)
    .filter(url => {
      const parsed = new URL(url);
      return !["data:", "blob:"].includes(parsed.protocol) &&
        parsed.origin !== baseOrigin;
    });
  ensure(
    externalRequests.length === 0,
    `出现意外外部请求：${externalRequests.join(", ")}`
  );
  const browserErrors = events.filter(
    event =>
      event.method === "Runtime.exceptionThrown" ||
      (event.method === "Log.entryAdded" &&
        event.params?.entry?.level === "error")
  );
  ensure(
    browserErrors.length === 0,
    `浏览器控制台错误：${JSON.stringify(browserErrors)}`
  );
  record("浏览器安全与职责边界", {
    external_requests: 0,
    console_errors: 0,
    admin_creator_entry: false,
    user_admin_entry: false
  });

  // Keep the pages alive through all assertions; teardown below removes their
  // isolated browser contexts and no credentials are persisted.
  ensure(hqUser && storeUser, "用户浏览器上下文没有完整建立");
} catch (error) {
  failures.push(error instanceof Error ? error.stack ?? error.message : String(error));
} finally {
  try {
    socket?.close();
  } catch {
    // Best-effort browser teardown only.
  }
  chrome.kill("SIGTERM");
  const exited = chrome.exitCode !== null || await Promise.race([
    new Promise(resolvePromise => chrome.once("exit", () => resolvePromise(true))),
    wait(5000).then(() => false)
  ]);
  if (!exited && chrome.exitCode === null) {
    chrome.kill("SIGKILL");
    await Promise.race([
      new Promise(resolvePromise => chrome.once("exit", resolvePromise)),
      wait(2000)
    ]);
  }
  let profileRemoved = false;
  for (let attempt = 0; attempt < 40; attempt += 1) {
    try {
      rmSync(profile, { recursive: true, force: true });
      profileRemoved = true;
      break;
    } catch (error) {
      const code = error && typeof error === "object" ? error.code : "";
      if (!new Set(["EBUSY", "ENOTEMPTY", "EPERM"]).has(code)) throw error;
      await wait(250);
    }
  }
  if (!profileRemoved) failures.push("隔离 Chrome 目录未能在有界等待内清理");
}

console.log(JSON.stringify({ results, failures }, null, 2));
if (failures.length) process.exit(1);
