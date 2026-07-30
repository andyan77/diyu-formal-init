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
  };
}).__DIYU_ADMIN_INTERACTION__;
const { window, requests, copiedTexts, setReducedMotion } = harness;
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
  const activationAnchor = document.querySelector(
    '.one-time-link a[href="https://diyu.example/activate/ui04-obviously-fake-browser-fixture"]'
  );
  assert.ok(activationAnchor, "完整 HTTPS 激活地址必须可直接点击");
  await click(find(".one-time-link button", "复制链接"));
  assert.equal(
    copiedTexts.at(-1),
    "https://diyu.example/activate/ui04-obviously-fake-browser-fixture",
    "显示值与复制值必须使用同一个服务端完整 URL"
  );

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
  await click(find(".one-time-link button", "复制重设链接"));
  assert.equal(
    copiedTexts.at(-1),
    "https://diyu.example/activate/ui05-obviously-fake-reset-fixture"
  );
  await click(find(".tenant-drawer button", "关闭"));
  await click(find(".tenant-nav button", "发布账号与账号画像"));
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
    ["请选择公司级组织", "笛语服饰管理组织"],
    "租户管理员创建并初始化画像时只能选择明确公司级负责团队"
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
  await click(find("button", "新增资料"));
  const scope = Array.from(document.querySelectorAll(".tenant-drawer select")).at(-1) as
    | HTMLSelectElement
    | undefined;
  assert.ok(scope);
  await select(scope, "organizations");
  assert.match(document.querySelector(".tenant-drawer")?.textContent ?? "", /未选择的其他区域默认不可使用/);
  assert.equal(
    (find(".tenant-drawer button", "保存资料") as HTMLButtonElement).disabled,
    true,
    "指定区域未选具体组织时不能保存"
  );

  await click(find(".tenant-drawer button", "关闭"));
  await click(find("button", "维护商品事实"));
  assert.match(document.querySelector(".tenant-drawer")?.textContent ?? "", /明确确认后/);
  assert.match(document.querySelector(".tenant-drawer")?.textContent ?? "", /导入 CSV/);
  assert.equal(
    (find(".tenant-drawer button", "保存商品事实") as HTMLButtonElement).disabled,
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
