import assert from "node:assert/strict";
import { act } from "react";
import { createRoot } from "react-dom/client";
import Root from "../src/app/Root";
import TenantAdminApp from "../src/app/TenantAdminApp";
import type { BootstrapContext } from "../src/app/types";

const harness = (globalThis as unknown as {
  __DIYU_ADMIN_INTERACTION__: {
    window: Window & typeof globalThis;
    requests: Array<{ path: string; method: string; body: Record<string, unknown> | null }>;
    copiedTexts: string[];
    setReducedMotion: (value: boolean) => void;
    setClipboardFailure: (value: boolean) => void;
  };
}).__DIYU_ADMIN_INTERACTION__;
const { window, requests, copiedTexts, setReducedMotion, setClipboardFailure } = harness;
const document = window.document;
const bootstrapWindow = window as unknown as {
  __DIYU_BOOTSTRAP__: Record<string, unknown> | null;
};

async function click(node: Element): Promise<void> {
  await act(async () => {
    node.dispatchEvent(new window.MouseEvent("click", { bubbles: true, cancelable: true }));
  });
}

function find(selector: string, text: string): HTMLElement {
  const value = Array.from(document.querySelectorAll(selector)).find(item =>
    (item.textContent ?? "").includes(text)
  );
  assert.ok(value, `找不到 ${selector} 中的「${text}」`);
  return value as HTMLElement;
}

async function input(
  node: HTMLInputElement | HTMLTextAreaElement,
  value: string
): Promise<void> {
  await act(async () => {
    const prototype =
      node instanceof window.HTMLTextAreaElement
        ? window.HTMLTextAreaElement.prototype
        : window.HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(prototype, "value")
      ?.set?.call(node, value);
    node.dispatchEvent(new window.Event("input", { bubbles: true }));
  });
}

async function select(node: HTMLSelectElement, value: string): Promise<void> {
  await act(async () => {
    Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, "value")
      ?.set?.call(node, value);
    node.dispatchEvent(new window.Event("change", { bubbles: true }));
  });
}

async function settle(): Promise<void> {
  for (let index = 0; index < 4; index += 1) {
    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 0));
    });
  }
}

async function renderAt(
  path: string,
  bootstrap: Record<string, unknown>
): Promise<ReturnType<typeof createRoot>> {
  window.history.replaceState({}, "", path);
  bootstrapWindow.__DIYU_BOOTSTRAP__ = bootstrap;
  const container = document.getElementById("root");
  assert.ok(container);
  const root = createRoot(container);
  await act(async () => root.render(<Root />));
  await settle();
  return root;
}

async function renderTenantAdmin(
  context: BootstrapContext,
  onPasswordUpdated: (path: string) => void
): Promise<ReturnType<typeof createRoot>> {
  window.history.replaceState({}, "", "/tenant-admin");
  const container = document.getElementById("root");
  assert.ok(container);
  const root = createRoot(container);
  await act(async () =>
    root.render(
      <TenantAdminApp
        context={context}
        onPasswordUpdated={onPasswordUpdated}
      />
    )
  );
  await settle();
  return root;
}

async function main(): Promise<void> {
  setReducedMotion(false);
  let root = await renderAt("/", { application: "public" });
  const rhythms = Array.from(document.querySelectorAll(".rhythm"));
  assert.equal(rhythms.length, 3);
  assert.deepEqual(
    rhythms.map(item => item.getAttribute("cx")),
    ["210", "210", "210"],
    "三个临时节奏点必须沿正式 VI 的竖向中轴排列"
  );
  assert.deepEqual(
    rhythms.map(item => item.getAttribute("cy")),
    ["132", "160", "188"]
  );
  await click(find("button", "跳过"));
  assert.ok(document.querySelector(".public-home")?.classList.contains("motion-finished"));
  await act(async () => root.unmount());

  setReducedMotion(true);
  root = await renderAt("/", { application: "public" });
  assert.ok(document.querySelector(".public-home")?.classList.contains("motion-finished"));
  assert.equal(document.querySelector(".motion-final img")?.getAttribute("src"), "/assets/diyu-logo-primary.svg");
  await act(async () => root.unmount());

  root = await renderAt("/login", {
    application: "login",
    entry: "tenant-user"
  });
  assert.match(document.body.textContent ?? "", /内容创作/);
  assert.equal(document.querySelector('[name="totp_code"]'), null);
  await act(async () => root.unmount());

  root = await renderAt("/tenant-admin/login", {
    application: "login",
    entry: "tenant-admin"
  });
  assert.match(document.body.textContent ?? "", /品牌管理/);
  assert.equal(document.querySelector('[name="totp_code"]'), null);
  assert.match(document.body.textContent ?? "", /忘记密码/);
  assert.match(
    document.body.textContent ?? "",
    /另一名品牌管理员或笛语运维.*一次性重设密码链接/
  );
  await act(async () => root.unmount());

  root = await renderAt("/ops/login", {
    application: "login",
    entry: "ops"
  });
  assert.match(document.body.textContent ?? "", /笛语运维/);
  assert.ok(document.querySelector('[name="totp_code"]'));
  assert.match(document.body.textContent ?? "", /身份验证器 6 位码/);
  assert.match(document.body.textContent ?? "", /来自已绑定的身份验证器/);
  await act(async () => root.unmount());

  root = await renderAt("/activate/ui05-reset-fixture", {
    application: "activation",
    activation_purpose: "reset"
  });
  assert.match(document.body.textContent ?? "", /重设密码.*重新设置密码/s);
  assert.match(document.body.textContent ?? "", /更新密码/);
  const resetPassword = document.querySelector(
    'input[name="password"]'
  ) as HTMLInputElement | null;
  const resetConfirmation = document.querySelector(
    'input[name="password_confirm"]'
  ) as HTMLInputElement | null;
  assert.ok(resetPassword);
  assert.ok(resetConfirmation);
  await input(resetPassword, "a-long-enough-password");
  await input(resetConfirmation, "a-different-password");
  const activationForm = document.querySelector("form");
  assert.ok(activationForm);
  let submissionAllowed = true;
  await act(async () => {
    submissionAllowed = activationForm.dispatchEvent(
      new window.Event("submit", { bubbles: true, cancelable: true })
    );
  });
  assert.equal(submissionAllowed, false, "两次密码不一致时必须阻止表单提交");
  assert.match(document.body.textContent ?? "", /两次输入的密码不一致/);
  assert.equal(document.activeElement, resetConfirmation);
  await act(async () => root.unmount());

  let passwordRedirect = "";
  root = await renderTenantAdmin({
    application: "tenant_management",
    formal_runtime: true,
    identity: {
      operator_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
      operator: "品牌管理员",
      organization: "笛语服饰管理组织",
      brand: "笛语服饰"
    }
  }, path => {
    passwordRedirect = path;
  });
  for (const label of [
    "概览与当前待办",
    "团队使用",
    "成员与入口资格",
    "发布账号与账号画像",
    "品牌资料库",
    "当前可用与待补"
  ]) {
    assert.match(document.body.textContent ?? "", new RegExp(label));
  }
  assert.equal(document.querySelector(".creator-app"), null);
  assert.equal(document.querySelector('a[href="/content"]'), null);
  assert.doesNotMatch(document.body.textContent ?? "", /开始创作|进入创作/);
  assert.match(document.body.textContent ?? "", /今天需要处理什么/);
  await click(find("button", "菜单"));
  assert.equal(
    document.querySelectorAll(".tenant-nav nav button").length,
    7,
    "移动管理菜单必须包含六个管理栏目和账户安全"
  );
  assert.match(
    document.activeElement?.textContent ?? "",
    /概览与当前待办/,
    "菜单打开后焦点进入第一个栏目"
  );
  await click(find(".tenant-nav button", "概览与当前待办"));

  await click(find(".tenant-nav button", "成员与入口资格"));
  await click(find("button", "添加成员"));
  const memberInputs = Array.from(
    document.querySelectorAll(".tenant-drawer input")
  ) as HTMLInputElement[];
  await input(memberInputs[0], "门店内容成员");
  await input(memberInputs[1], "ui05-member");
  await select(
    document.querySelector(".tenant-drawer select") as HTMLSelectElement,
    "11111111-1111-4111-8111-111111111111"
  );
  await click(find(".tenant-drawer label", "租户管理员"));
  assert.doesNotMatch(document.querySelector(".tenant-drawer")?.textContent ?? "", /获准操作的发布账号/);
  await click(find(".tenant-drawer label", "租户用户"));
  assert.match(document.querySelector(".tenant-drawer")?.textContent ?? "", /内容创作/);
  assert.match(document.querySelector(".tenant-drawer")?.textContent ?? "", /陈列搭配/);
  assert.equal(
    (find(".tenant-drawer button", "创建并生成一次性激活链接") as HTMLButtonElement)
      .disabled,
    true,
    "内容创作资格没有发布账号时不能创建"
  );
  await click(find(".tenant-drawer label", "总部品牌内容运营"));
  await click(find(".tenant-drawer button", "创建并生成一次性激活链接"));
  await settle();
  const memberCreate = requests.find(
    item => item.path === "/api/v1/tenant-management/users" && item.method === "POST"
  );
  assert.equal(memberCreate?.body?.entry_type, "tenant_user");
  assert.deepEqual(memberCreate?.body?.capabilities, ["content"]);
  assert.deepEqual(memberCreate?.body?.publishing_identity_ids, [
    "33333333-3333-4333-8333-333333333333"
  ]);
  assert.equal(memberCreate?.body?.grants_material_maintenance, false);
  assert.deepEqual(
    memberCreate?.body?.expression_profile_maintenance_account_ids,
    [],
    "账号使用资格不得静默授予画像维护权"
  );
  const activationAnchor = document.querySelector(
    '.one-time-link a[href="https://diyu.example/activate/ui04-obviously-fake-browser-fixture"]'
  );
  assert.ok(activationAnchor, "完整 HTTPS 激活地址必须可直接点击");
  await click(find(".one-time-link button", "复制链接"));
  await settle();
  assert.equal(
    copiedTexts.at(-1),
    "https://diyu.example/activate/ui04-obviously-fake-browser-fixture",
    "显示值与复制值必须使用同一个服务端完整 URL"
  );
  const activationCopyFeedback = find(
    ".one-time-link [role=status]",
    "链接已复制"
  );
  assert.ok(
    activationCopyFeedback.closest(".tenant-drawer"),
    "激活链接复制反馈必须位于当前成员抽屉内"
  );
  assert.doesNotMatch(document.body.textContent ?? "", /链接已发送|已交付/);

  await click(find(".tenant-drawer button", "关闭"));
  await click(find("button", "查看与处理"));
  assert.match(
    document.querySelector(".tenant-drawer")?.textContent ?? "",
    /生成一次性重设密码链接/
  );
  await click(find(".tenant-drawer button", "生成一次性重设密码链接"));
  await settle();
  assert.match(
    document.body.textContent ?? "",
    /新的一次性重设密码链接已生成，此前未使用的重设链接已失效/
  );
  assert.match(
    document.querySelector(".tenant-drawer")?.textContent ?? "",
    /ui05-obviously-fake-reset-fixture/
  );
  assert.ok(
    document.querySelector(
      '.one-time-link a[href="https://diyu.example/activate/ui05-obviously-fake-reset-fixture"]'
    ),
    "完整 HTTPS 重设地址必须可直接点击"
  );
  setClipboardFailure(true);
  await click(find(".one-time-link button", "复制重设链接"));
  await settle();
  const failedResetCopyFeedback = find(
    ".one-time-link [role=status]",
    "未能自动复制，请手动选择上方链接"
  );
  assert.ok(
    failedResetCopyFeedback.closest(".tenant-drawer"),
    "重设链接复制失败反馈必须位于当前成员抽屉内"
  );
  setClipboardFailure(false);
  await click(find(".one-time-link button", "复制重设链接"));
  await settle();
  assert.equal(
    copiedTexts.at(-1),
    "https://diyu.example/activate/ui05-obviously-fake-reset-fixture"
  );
  const successfulResetCopyFeedback = find(
    ".one-time-link [role=status]",
    "链接已复制"
  );
  assert.ok(
    successfulResetCopyFeedback.closest(".tenant-drawer"),
    "重设链接复制成功反馈必须位于当前成员抽屉内"
  );

  const disablePath =
    "/api/v1/tenant-management/users/22222222-2222-4222-8222-222222222222/disable";
  const disableCount = (): number =>
    requests.filter(item => item.path === disablePath && item.method === "POST").length;
  assert.equal(disableCount(), 0);
  await click(find(".tenant-drawer button", "停用成员"));
  assert.equal(disableCount(), 0, "停用成员首击不得调用 API");
  assert.match(document.querySelector('[role="alertdialog"]')?.textContent ?? "", /无法继续登录/);
  assert.match(
    document.querySelector('[role="alertdialog"]')?.textContent ?? "",
    /当前会话和工作资格/
  );
  assert.match(document.activeElement?.textContent ?? "", /确认停用/);
  await click(find('[role="alertdialog"] button', "取消"));
  assert.equal(disableCount(), 0, "取消停用不得改变成员状态");
  const disableTriggerAfterCancel = find(
    ".tenant-drawer button",
    "停用成员"
  ) as HTMLButtonElement;
  assert.equal(disableTriggerAfterCancel.isConnected, true);
  assert.equal(
    document.activeElement,
    disableTriggerAfterCancel,
    "取消后焦点必须返回重新挂载的真实停用按钮"
  );
  await click(disableTriggerAfterCancel);
  const escapeDialog = document.querySelector('[role="alertdialog"]');
  assert.ok(escapeDialog);
  await act(async () => {
    escapeDialog.dispatchEvent(
      new window.KeyboardEvent("keydown", {
        key: "Escape",
        bubbles: true,
        cancelable: true
      })
    );
  });
  await settle();
  const disableTriggerAfterEscape = find(
    ".tenant-drawer button",
    "停用成员"
  ) as HTMLButtonElement;
  assert.equal(disableTriggerAfterEscape.isConnected, true);
  assert.equal(
    document.activeElement,
    disableTriggerAfterEscape,
    "Escape 后焦点必须返回重新挂载的真实停用按钮"
  );
  await click(find(".tenant-drawer button", "停用成员"));
  const confirmDisable = find('[role="alertdialog"] button', "确认停用");
  await act(async () => {
    confirmDisable.dispatchEvent(
      new window.MouseEvent("click", { bubbles: true, cancelable: true })
    );
    confirmDisable.dispatchEvent(
      new window.MouseEvent("click", { bubbles: true, cancelable: true })
    );
  });
  await settle();
  assert.equal(disableCount(), 1, "确认停用只能调用一次 API");
  assert.match(document.body.textContent ?? "", /成员已停用/);
  await click(find("button", "查看与处理"));
  await click(find(".tenant-drawer button", "恢复成员并生成激活链接"));
  await settle();
  assert.match(
    document.querySelector(".tenant-drawer")?.textContent ?? "",
    /ui05-restored-fixture/
  );
  await click(find(".tenant-drawer button", "关闭"));

  await click(find(".tenant-nav button", "发布账号与账号画像"));
  const createAccountButton = find(
    "button",
    "创建发布账号"
  ) as HTMLButtonElement;
  assert.equal(
    createAccountButton.disabled,
    true,
    "全新租户未确认品牌表达基线时不得进入账号创建"
  );
  const baselineDraft = document.querySelector(
    ".brand-expression-baseline textarea"
  ) as HTMLTextAreaElement;
  await input(baselineDraft, `${baselineDraft.value}\n管理员确认后的修订。`);
  await click(find(".brand-expression-baseline button", "确认当前品牌表达"));
  await settle();
  const baselineConfirmation = requests.find(
    item =>
      item.path === "/api/v1/admin/brand-expression/confirm" &&
      item.method === "POST"
  );
  assert.match(
    String(baselineConfirmation?.body?.draft ?? ""),
    /管理员确认后的修订/
  );
  assert.equal(
    (find("button", "创建发布账号") as HTMLButtonElement).disabled,
    false
  );
  await click(find("button", "创建发布账号"));
  const accountInputs = Array.from(
    document.querySelectorAll(".tenant-drawer input")
  ) as HTMLInputElement[];
  await input(accountInputs[0], "总部品牌内容运营");
  await input(accountInputs[1], "品牌官方");
  const accountSelects = Array.from(
    document.querySelectorAll(".tenant-drawer select")
  ) as HTMLSelectElement[];
  assert.deepEqual(
    Array.from(accountSelects[1].options).map(option => option.textContent),
    ["请选择负责团队", "笛语服饰管理组织", "浙江区域", "柯桥门店"],
    "逻辑账号必须显式选择当前租户的控制组织"
  );
  await select(accountSelects[0], "institutional_account");
  await select(accountSelects[1], "11111111-1111-4111-8111-111111111111");
  await select(accountSelects[2], "22222222-2222-4222-8222-222222222222");
  const profileValues = [
    "以总部品牌内容运营身份出现",
    "代表已确认品牌立场，不代替门店陈述经历",
    "与受众保持克制、平等的交流关系",
    "长期解释品牌选择与穿着关系",
    "一人、一部手机、普通室内"
  ];
  const profileFields = Array.from(
    document.querySelectorAll(".tenant-drawer textarea")
  ) as HTMLTextAreaElement[];
  assert.equal(profileFields.length, 5, "创建发布账号时只建立一份完整五段画像");
  for (const [index, value] of profileValues.entries()) {
    await input(profileFields[index], value);
  }
  await click(find(".tenant-drawer button", "创建发布账号"));
  await settle();
  const accountCreate = requests.find(
    item =>
      item.path === "/api/v1/tenant-management/publishing-accounts" &&
      item.method === "POST"
  );
  assert.equal(accountCreate?.body?.content_role_name, "品牌官方");
  assert.equal(accountCreate?.body?.speaker_kind, "institutional_account");
  assert.equal("target" in (accountCreate?.body ?? {}), false);
  assert.equal(accountCreate?.body?.channel, "抖音");
  assert.equal(
    accountCreate?.body?.operator_can_maintain_expression_profile,
    false,
    "创建账号不得静默授予画像维护权"
  );
  assert.equal("voice_boundary" in (accountCreate?.body ?? {}), false);
  assert.deepEqual(accountCreate?.body?.initial_profile, {
    identity_position: profileValues[0],
    authority_boundary: profileValues[1],
    audience_relationship: profileValues[2],
    content_territories: profileValues[3],
    default_production_conditions: profileValues[4]
  });
  const speakerSelect = document.querySelector(
    'select[aria-label="总部品牌内容运营表达主体"]'
  ) as HTMLSelectElement | null;
  assert.ok(speakerSelect, "发布账号必须显示结构化表达主体声明");
  await select(speakerSelect, "personal_ip_account");
  await settle();
  const speakerUpdate = requests.find(
    item =>
      item.path.endsWith(
        "/publishing-accounts/33333333-3333-4333-8333-333333333333/speaker-kind"
      ) && item.method === "PATCH"
  );
  assert.equal(speakerUpdate?.body?.speaker_kind, "personal_ip_account");
  await click(find("button", "添加平台"));
  const targetSelects = Array.from(
    document.querySelectorAll(".tenant-drawer select")
  ) as HTMLSelectElement[];
  await select(targetSelects[0], "wechat_channels_video");
  await click(find(".tenant-drawer button", "添加平台"));
  await settle();
  const platformCreate = requests.find(
    item =>
      item.path === "/api/v1/tenant-management/platform-carriers" &&
      item.method === "POST"
  );
  assert.equal(platformCreate?.body?.channel, "微信视频号");
  assert.equal("target" in (platformCreate?.body ?? {}), false);
  assert.doesNotMatch(
    JSON.stringify(platformCreate?.body ?? {}),
    /微信号"/,
    "微信视频号不得再通过字符串删除“视频”推导"
  );

  await click(find(".tenant-nav button", "团队使用"));
  await settle();
  assert.match(document.body.textContent ?? "", /已记录模型用量/);
  assert.match(document.body.textContent ?? "", /不等同于账单/);
  assert.ok(
    requests.some(item => item.path === "/api/v1/tenant-management/team-usage"),
    "团队使用必须读取本租户聚合接口"
  );

  await click(find(".tenant-nav button", "品牌资料库"));
  await settle();
  for (const label of ["品牌全员", "总部专用", "指定区域"]) {
    assert.match(document.body.textContent ?? "", new RegExp(label));
  }
  assert.match(document.body.textContent ?? "", /牛角扣外套/);
  assert.match(document.body.textContent ?? "", /品牌管理员录入/);
  assert.match(document.body.textContent ?? "", /浙江区域门店拍摄说明/);
  assert.match(document.body.textContent ?? "", /shooting-note.txt/);
  await click(find(".library-list button", "查看版本与维护"));
  await settle();
  assert.match(document.querySelector(".tenant-drawer")?.textContent ?? "", /历史版本/);
  await click(find(".tenant-drawer button", "停用资料"));
  await settle();
  assert.ok(
    requests.some(
      item =>
        item.path.endsWith(
          "/brand-library/66666666-6666-4666-8666-666666666666/enabled"
        ) && item.body?.enabled === false
    ),
    "品牌文字资料停用必须写入正式生命周期接口"
  );
  await click(find(".tenant-drawer button", "恢复资料"));
  await click(find(".tenant-drawer button", "关闭"));

  await click(find(".product-list button", "查看版本与维护"));
  await settle();
  assert.match(document.querySelector(".tenant-drawer")?.textContent ?? "", /V2 · 当前版本/);
  await click(find(".tenant-drawer button", "查看字段预览"));
  await settle();
  const productConfirmation = find(
    ".tenant-drawer label",
    "我确认这些是当前品牌可负责的商品事实"
  ).querySelector("input") as HTMLInputElement;
  await click(productConfirmation);
  await click(find(".tenant-drawer button", "保存新版本"));
  await settle();
  assert.ok(
    requests.some(
      item =>
        item.path === "/api/v1/tenant-management/brand-products/preview" &&
        item.method === "POST"
    ),
    "商品字段必须先经过正式预览接口"
  );

  await click(find(".material-list button", "查看版本与维护"));
  await settle();
  assert.match(document.querySelector(".tenant-drawer")?.textContent ?? "", /历史版本/);
  const productBindingSelect = find(
    ".tenant-drawer label",
    "选择已确认商品"
  ).querySelector("select") as HTMLSelectElement;
  await select(
    productBindingSelect,
    "77777777-7777-4777-8777-777777777701"
  );
  await click(find(".tenant-drawer button", "建立商品关联"));
  await settle();
  assert.ok(
    requests.some(
      item =>
        item.path.endsWith(
          "/organization-materials/44444444-4444-4444-8444-444444444444/product-bindings"
        ) &&
        item.method === "POST" &&
        item.body?.product_id ===
          "77777777-7777-4777-8777-777777777701"
    ),
    "商品与组织官方素材必须通过正式关联接口明确登记"
  );
  assert.match(
    document.querySelector(".tenant-drawer")?.textContent ?? "",
    /牛角扣外套.*DEMO-A/s
  );
  await click(find(".tenant-drawer button", "停用关联"));
  await settle();
  assert.ok(
    requests.some(
      item =>
        item.path.includes("/product-bindings/") &&
        item.path.endsWith("/enabled") &&
        item.body?.enabled === false
    ),
    "商品素材关联必须具备正式停用消费者"
  );
  await click(find(".tenant-drawer button", "恢复关联"));
  await settle();
  const materialNote = find(
    ".tenant-drawer label",
    "人工说明"
  ).querySelector("textarea") as HTMLTextAreaElement;
  await input(materialNote, "复核后的组织素材说明");
  await click(find(".tenant-drawer button", "保存新版本"));
  await settle();
  assert.ok(
    requests.some(
      item =>
        item.path.endsWith(
          "/organization-materials/44444444-4444-4444-8444-444444444444/versions"
        ) && item.method === "POST"
    ),
    "组织素材说明必须形成新版本"
  );
  await click(find(".tenant-drawer button", "关闭"));

  await click(find("button", "新增资料"));
  const scope = Array.from(document.querySelectorAll(".tenant-drawer select")).at(-1) as
    | HTMLSelectElement
    | undefined;
  assert.ok(scope);
  await select(scope, "organizations");
  assert.match(document.querySelector(".tenant-drawer")?.textContent ?? "", /未选择的其他区域默认不可使用/);
  assert.equal(
    (find(".tenant-drawer button", "查看导入预览") as HTMLButtonElement).disabled,
    true,
    "指定区域未选具体组织时不能保存"
  );
  const regionChoice = find(
    ".tenant-drawer fieldset",
    "选择可用区域"
  ).querySelector("input") as HTMLInputElement;
  await click(regionChoice);
  await input(
    find(".tenant-drawer label", "资料名称").querySelector("input") as HTMLInputElement,
    "华东区域表达边界"
  );
  await input(
    find(".tenant-drawer label", "粘贴文字资料").querySelector(
      "textarea"
    ) as HTMLTextAreaElement,
    "只描述已经确认的门店条件。"
  );
  await input(
    find(".tenant-drawer label", "自然来源说明").querySelector(
      "textarea"
    ) as HTMLTextAreaElement,
    "华东区域管理员确认"
  );
  await click(find(".tenant-drawer button", "查看导入预览"));
  await settle();
  assert.match(document.querySelector(".tenant-drawer")?.textContent ?? "", /尚未保存/);
  assert.equal(
    requests.filter(
      item =>
        item.path === "/api/v1/tenant-management/brand-library" &&
        item.method === "POST"
    ).length,
    0,
    "导入预览不得直接保存正式资料"
  );
  await click(find(".tenant-drawer button", "确认保存为当前版本"));
  await settle();
  assert.ok(
    requests.some(
      item =>
        item.path === "/api/v1/tenant-management/brand-library" &&
        item.method === "POST" &&
        item.body?.confirm_as_current === true
    ),
    "管理员明确确认后才保存当前资料"
  );

  await click(find("button", "维护商品事实"));
  assert.match(document.querySelector(".tenant-drawer")?.textContent ?? "", /明确确认后/);
  assert.match(document.querySelector(".tenant-drawer")?.textContent ?? "", /导入 CSV/);
  assert.equal(
    (find(".tenant-drawer button", "查看字段预览") as HTMLButtonElement).disabled,
    true,
    "商品候选没有明确确认时不能升级为事实"
  );
  const productScope = find(
    ".tenant-drawer label",
    "商品事实可用范围"
  ).querySelector("select") as HTMLSelectElement;
  await select(productScope, "organizations");
  const productRegions = find(".tenant-drawer fieldset", "选择可用区域");
  assert.match(productRegions.textContent ?? "", /浙江区域/);
  assert.doesNotMatch(
    productRegions.textContent ?? "",
    /笛语服饰管理组织|柯桥门店/,
    "商品指定区域不得混入总部或门店组织"
  );
  await click(find(".tenant-drawer button", "关闭"));
  await click(find("button", "添加组织官方素材"));
  assert.match(document.querySelector(".tenant-drawer")?.textContent ?? "", /人工说明/);
  assert.doesNotMatch(document.querySelector(".tenant-drawer")?.textContent ?? "", /私人素材/);
  await click(find(".tenant-drawer button", "关闭"));
  await click(find(".tenant-nav button", "当前可用与待补"));
  await settle();
  assert.match(document.body.textContent ?? "", /判断依据/);
  assert.match(document.body.textContent ?? "", /缺少资料/);
  assert.match(document.body.textContent ?? "", /影响/);
  assert.doesNotMatch(document.body.textContent ?? "", /知识完整度|生产就绪百分比/);

  for (const forbidden of ["tenant_id", "ContentRole", "RLS", "schema", "测试通过"]) {
    assert.doesNotMatch(document.body.textContent ?? "", new RegExp(forbidden));
  }

  await click(find(".tenant-account-menu summary", "品牌管理员"));
  await click(find(".tenant-account-menu button", "账户安全"));
  let passwordFields = Array.from(
    document.querySelectorAll(".tenant-drawer input")
  ) as HTMLInputElement[];
  assert.equal(passwordFields.length, 3);
  await input(passwordFields[0], "incorrect-current-password");
  await input(passwordFields[1], "replacement-password-2026");
  await input(passwordFields[2], "different-password-2026");
  const passwordRequestsBeforeMismatch = requests.filter(
    item => item.path === "/api/v1/auth/password"
  ).length;
  await click(find(".tenant-drawer button", "修改密码"));
  await settle();
  assert.match(document.body.textContent ?? "", /两次输入的新密码不一致/);
  assert.equal(
    requests.filter(item => item.path === "/api/v1/auth/password").length,
    passwordRequestsBeforeMismatch,
    "两次密码不一致时不得发送请求"
  );

  passwordFields = Array.from(
    document.querySelectorAll(".tenant-drawer input")
  ) as HTMLInputElement[];
  await input(passwordFields[2], "replacement-password-2026");
  await click(find(".tenant-drawer button", "修改密码"));
  await settle();
  assert.match(document.body.textContent ?? "", /当前密码不正确，请重新输入/);
  assert.equal(window.location.pathname, "/tenant-admin");

  passwordFields = Array.from(
    document.querySelectorAll(".tenant-drawer input")
  ) as HTMLInputElement[];
  await input(passwordFields[0], "correct-current-password");
  await click(find(".tenant-drawer button", "修改密码"));
  await settle();
  const successfulPasswordRequest = requests
    .filter(item => item.path === "/api/v1/auth/password")
    .at(-1);
  assert.deepEqual(successfulPasswordRequest?.body, {
    current_password: "correct-current-password",
    password: "replacement-password-2026"
  });
  assert.equal(
    "confirmation" in (successfulPasswordRequest?.body ?? {}),
    false,
    "确认密码不得发给服务端"
  );
  assert.equal(
    passwordRedirect,
    "/tenant-admin/login?password_updated=1",
    "成功修改密码后必须返回品牌管理登录页"
  );
  assert.deepEqual(
    Array.from(document.querySelectorAll<HTMLInputElement>(".tenant-drawer input")).map(
      field => field.value
    ),
    ["", "", ""],
    "成功后不得把任何密码继续留在页面字段中"
  );
  await act(async () => root.unmount());

  root = await renderAt("/tenant-admin/login?password_updated=1", {
    application: "login",
    entry: "tenant-admin"
  });
  assert.match(document.body.textContent ?? "", /密码已更新，请重新登录/);
  await act(async () => root.unmount());
}

await main();
