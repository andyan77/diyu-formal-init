import { build } from "esbuild";
import { readFile, rm } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { JSDOM } from "jsdom";

const catalogDocument = JSON.parse(
  await readFile(
    new URL("../../config/content_expression/catalog-v1.json", import.meta.url),
    "utf8"
  )
);
let savedDefaults = {};
const catalogResponse = bodyEnabled => ({
  catalog_version: catalogDocument.catalog_version,
  body_related_enabled: bodyEnabled,
  preference_session: "normal",
  saved_defaults: savedDefaults,
  axes: catalogDocument.axes.map(axis => ({
    key: axis.key,
    label: axis.label,
    question: axis.question,
    options: catalogDocument.entries
      .filter(entry => entry.axis === axis.key && (bodyEnabled || !entry.body_related))
      .map(entry => ({
        stable_id: entry.stable_id,
        label: entry.label,
        capability_state: entry.capability_state,
        body_related: entry.body_related
      }))
  }))
});

const v1 = {
  kind: "content",
  task_id: "t1",
  version_id: "v1",
  version: 1,
  outline: "沉默，也可以被尊重",
  body:
    "内容概要：这版把门店里的沉默当成一种可以被尊重的选择，让观众带走一个不施压的判断。\n\n标题：沉默，也可以被尊重\n\n完整台词：有人走进门店，只想自己看看。我们可以先把解释放一放，让选择慢一点发生。\n\n画面与动作：手机固定，一人面对镜头自然说完；中间留一次停顿。\n\n发布配文：想自己看一会儿，也是一种清楚的选择。",
  ai_generated: true,
  aigc_label: "AI 辅助生成",
  aigc_release_reminder: "发布前请使用平台 AI 内容声明功能。",
  target_key: "xiaohongshu_graphic",
  applied_direction: ["幽默玩梗"],
  context_basis: {
    account: "总部品牌内容运营",
    platform_and_format: "小红书 · 图文",
    brand_material_categories: ["品牌已确认资料", "品牌表达边界"],
    has_product_facts: true,
    selected_material_count: 2,
    gaps: []
  }
};
const v2 = {
  ...v1,
  version_id: "v2",
  version: 2,
  outline: "先让人安静看一会儿",
  body:
    "内容概要：保留尊重沉默的判断，改成一人面对手机能自然说出的版本。\n\n标题：先让人安静看一会儿\n\n完整台词：有时候进店，就是想先看看。那就先看，不用急着把每件衣服都解释一遍。合适的衣服不会因为安静十秒就错过你。\n\n画面与动作：手机固定，创作者站在空墙前说；最后自然停一下。\n\n发布配文：先看一会儿，再决定要不要聊。",
  translation_notice: "保留了你想要的轻松感，收成克制的冷幽默，不做吵闹玩梗。"
};
const v3 = {
  ...v2,
  version_id: "v3",
  version: 3,
  outline: "失败后重放形成的新版本"
};

const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
  url: "http://localhost/content?target=xiaohongshu_graphic",
  pretendToBeVisual: true
});
const mediaListeners = new Set();
Object.defineProperty(dom.window, "matchMedia", {
  value: query => ({
    matches: query === "(max-width: 640px)",
    media: query,
    onchange: null,
    addEventListener: (_event, listener) => mediaListeners.add(listener),
    removeEventListener: (_event, listener) => mediaListeners.delete(listener),
    addListener: listener => mediaListeners.add(listener),
    removeListener: listener => mediaListeners.delete(listener),
    dispatchEvent: () => true
  }),
  configurable: true
});
for (const name of [
  "window",
  "document",
  "navigator",
  "Event",
  "CustomEvent",
  "MouseEvent",
  "Node",
  "HTMLElement",
  "HTMLInputElement",
  "HTMLTextAreaElement",
  "HTMLSelectElement",
  "getComputedStyle"
]) {
  Object.defineProperty(globalThis, name, {
    value: dom.window[name] ?? dom.window,
    configurable: true,
    writable: true
  });
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

let bodyEnabled = false;
let revised = false;
let currentRevision = v1;
let revisionFailureCount = 0;
let copyShouldFail = false;
let deferVersionLoad = false;
let releaseVersionLoad = null;
let publicStatusProjection = {
  contract_version: "public-service-status-v1",
  checked_at: "2026-07-31T12:00:00+00:00",
  provider_freshness_seconds: 900,
  core: { state: "available" },
  content_generation: { state: "unknown", observed_at: null, fresh_until: null },
  text_display: { state: "available" }
};
let publicStatusRequestFails = false;
const requests = [];
const copiedTexts = [];
const exportedBlobs = [];
Object.defineProperty(dom.window.navigator, "clipboard", {
  value: {
    writeText: async value => {
      if (copyShouldFail) throw new Error("clipboard denied");
      copiedTexts.push(String(value));
    }
  },
  configurable: true
});
URL.createObjectURL = blob => {
  exportedBlobs.push(blob);
  return "blob:diyu-export";
};
URL.revokeObjectURL = () => undefined;
dom.window.HTMLAnchorElement.prototype.click = () => undefined;
const supportedFormalCapabilityIds = Array.from({ length: 64 }, (_, index) => index + 1)
  .filter(value => ![33, 53, 59, 61, 62, 63].includes(value))
  .map(value => `FT-${String(value).padStart(3, "0")}`);
dom.window.__DIYU_BOOTSTRAP__ = {
  application: "content",
  generator_mode: "deepseek",
  formal_runtime: true,
  identity: {
    tenant_id: "tenant-0001",
    operator_id: "user-hq",
    operator: "总部内容运营甲",
    organization: "笛语服饰管理组织",
    account: "总部品牌内容运营",
    content_role: "品牌官方",
    brand: "笛语服饰"
  },
  current_target: "xiaohongshu_graphic",
  current_publishing_identity_id: "identity-hq",
  publishing_identities: [
    {
      id: "identity-hq",
      name: "总部品牌内容运营",
      content_role: "品牌官方",
      profile_summary: "从品牌整体选择和长期表达的位置说话。",
      platform_targets: [
        { value: "douyin_video", label: "抖音视频", platform_label: "抖音", format_label: "视频" },
        { value: "xiaohongshu_graphic", label: "小红书图文", platform_label: "小红书", format_label: "图文" },
        { value: "xiaohongshu_video", label: "小红书视频", platform_label: "小红书", format_label: "视频" },
        { value: "wechat_channels_video", label: "微信视频号", platform_label: "微信视频号", format_label: "视频" }
      ]
    },
    {
      id: "identity-store",
      name: "柯桥门店人物",
      content_role: "门店人物",
      profile_summary: "从门店日常和本人可确认的观察出发。",
      platform_targets: [
        { value: "douyin_video", label: "抖音视频", platform_label: "抖音", format_label: "视频" },
        { value: "xiaohongshu_graphic", label: "小红书图文", platform_label: "小红书", format_label: "图文" }
      ]
    }
  ],
  targets: [
    { value: "douyin_video", label: "抖音视频", platform_label: "抖音", format_label: "视频" },
    { value: "xiaohongshu_video", label: "小红书视频", platform_label: "小红书", format_label: "视频" },
    { value: "xiaohongshu_graphic", label: "小红书图文", platform_label: "小红书", format_label: "图文" },
    { value: "wechat_channels_video", label: "微信视频号", platform_label: "微信视频号", format_label: "视频" }
  ],
  capability_matrix: {
    registry_version: "formal-capabilities-v1",
    runtime_sha: "candidate-user-help-sha",
    schema_revision: "20260817_44",
    generated_at: "2026-08-04T12:00:00Z",
    truth_sources: ["formal-api", "postgresql", "production-observation"],
    summary: {
      implemented: 58,
      not_built: 0,
      data_satisfied: 43,
      permission_granted: 29,
      formally_tested: 58
    },
    items: supportedFormalCapabilityIds.map((id, index) => ({
      id,
      role: index < 10 ? "public" : "tenant_user",
      route: index < 10 ? "/status" : "/user",
      title: `正式能力 ${index + 1}`,
      consumer: "formal-api-postgresql",
      software_implemented: true,
      data_state: index < 43 ? "satisfied" : "missing",
      permission_state: index < 29 ? "granted" : "not_granted",
      formally_tested: true,
      supplement_href: "/tenant-admin?section=readiness"
    }))
  },
  usage_guide: {
    identity_model: [
      "笛语系统运维管理员：维护最小运维入口。",
      "笛语服饰租户管理员：管理组织、成员、账号与资料。",
      "笛语服饰租户用户：按本人资格创作、修改、复制和导出。"
    ],
    relationship: "自然人 → 工作资格 → 逻辑发布账号 → 平台和形式",
    send_vs_generate: {
      send: "发送：普通交流，不创建任务。",
      generate: "生成内容：创建正式任务、运行和版本。"
    },
    administrator_steps: [
      "创建组织。",
      "创建逻辑发布账号并配置平台目标、ContentRole 和五段画像。",
      "创建成员，分配账号资格并发送单次激活链接。"
    ],
    named_member_examples: ["笛语品控", "柯桥店阿丹"],
    current_counts: {
      formal_users: 2,
      content_users: 1,
      logical_accounts: 1,
      platform_targets: 4,
      profile_accounts: 1,
      active_products: 14,
      allowed_product_fact_fields: 26,
      organization_media: 0,
      product_media_products: 0,
      confirmed_stores: 0,
      formal_inventory_snapshots: 0
    },
    content_path_state: "partial",
    brand_context_summary: {
      status: "needs_admin_confirmation",
      message: "来源资料已保存，但还需管理员确认来源绑定版本。"
    },
    truth_boundaries: [
      "用户本轮陈述只在当前任务内冻结，不自动成为可复用品牌事实。",
      "系统不自动发布，采用和发布由用户完成。"
    ],
    product_fact_readiness: [
      {
        sku: "DIYU-CSPU-004",
        display_name: "男童复古拼色图形短袖",
        current_facts: [{ field: "品类", value: "短袖" }, { field: "色彩", value: "拼色" }],
        missing_fields: ["价格带", "功效"],
        can_do: "可基于下列已确认字段解释这件商品的选择依据；每次任务只加载该 SKU 的事实。",
        cannot_promise: "未列入当前可用事实的属性、工艺、性能、功效、体验和品牌保证均不能承诺。"
      }
    ],
    service_status_meanings: [
      { state: "unknown", meaning: "最近没有足够新鲜的真实观察。" },
      { state: "degraded", meaning: "最近观察到可恢复异常。" },
      { state: "unavailable", meaning: "最近观察到生成依赖不可用。" }
    ],
    common_errors: [
      { code: "USERNAME_TAKEN", meaning: "登录用户名已被使用，请改用候选用户名。" },
      { code: "PROVIDER_UNAVAILABLE", meaning: "生成服务暂不可用；输入已保留，可稍后重试。" }
    ],
    data_missing: [
      { id: "P4", missing: true, message: "当前没有正式门店事实。", supplement_href: "/tenant-admin?section=readiness" },
      { id: "P5", missing: true, message: "当前没有正式商品图片、视频及商品绑定。", supplement_href: "/tenant-admin?section=materials" },
      { id: "DM01", missing: true, message: "当前缺少正式门店档案和库存。", supplement_href: "/tenant-admin?section=readiness" }
    ]
  }
};

globalThis.fetch = async (input, init = {}) => {
  const url = new URL(String(input), "http://localhost");
  const path = url.pathname;
  const method = init.method ?? "GET";
  const body = init.body ? JSON.parse(String(init.body)) : null;
  requests.push({ method, path, query: url.search, body, cache: init.cache ?? "default" });
  let payload = {};
  let ok = true;
  let status = 200;
  if (path === "/api/v1/test-session-invalid") {
    ok = false;
    status = 401;
    payload = {
      detail: "当前登录已经失效",
      error_code: "AUTH_EXPIRED",
      failure_stage: "authentication",
      retryable: false,
      action: "请重新登录后继续。",
      trace_id: "00000000-0000-4000-8000-000000000401"
    };
  } else if (path === "/api/v1/test-permission-denied") {
    ok = false;
    status = 403;
    payload = {
      detail: "当前账号没有这项资格",
      error_code: "PERMISSION_DENIED",
      failure_stage: "authorization",
      retryable: false,
      action: "请留在当前页面，联系品牌管理员确认当前工作资格和作用域。",
      trace_id: "00000000-0000-4000-8000-000000000403"
    };
  } else if (path === "/api/v1/status" && publicStatusRequestFails) {
    ok = false;
    status = 503;
    payload = { detail: "状态暂不可用" };
  } else if (path === "/api/v1/status") payload = publicStatusProjection;
  else if (path === "/api/v1/content/expression-catalog") payload = catalogResponse(bodyEnabled);
  else if (path === "/api/v1/user/creation-preferences" && method === "GET") {
    payload = {
      exists: true,
      enabled: true,
      version: 1,
      direction_defaults: savedDefaults,
      collaboration_note: "",
      body_related_opt_in: bodyEnabled
    };
  } else if (path === "/api/v1/user/creation-preferences" && method === "PUT") {
    bodyEnabled = Boolean(body.body_related_opt_in);
    savedDefaults = body.clear_direction_defaults ? {} : body.direction_defaults ?? {};
    payload = {
      exists: true,
      enabled: true,
      version: 2,
      direction_defaults: savedDefaults,
      collaboration_note: body.collaboration_note ?? "",
      body_related_opt_in: bodyEnabled
    };
  } else if (path === "/api/v1/materials") {
    payload = [
      {
        id: "11111111-1111-4111-8111-111111111111",
        title: "门店观察手记",
        media_type: "text",
        scope: "personal",
        status: "active",
        created_at: "2026-07-26T00:00:00Z",
        reference_note: ""
      },
      {
        id: "22222222-2222-4222-8222-222222222222",
        title: "尚未说明的图片",
        media_type: "image",
        scope: "personal",
        status: "active",
        created_at: "2026-07-26T00:00:00Z",
        reference_note: ""
      },
      {
        id: "44444444-4444-4444-8444-444444444441",
        title: "登记商品一官方图片",
        media_type: "image",
        scope: "organization",
        status: "active",
        created_at: "2026-07-26T00:00:00Z",
        reference_note: "品牌确认原图",
        product_media: [
          {
            binding_id: "binding-product-one",
            product_id: "product-one",
            sku: "ZX-ONE",
            product_name: "登记商品一",
            product_version: 1
          }
        ]
      },
      {
        id: "44444444-4444-4444-8444-444444444442",
        title: "登记商品二官方图片",
        media_type: "image",
        scope: "organization",
        status: "active",
        created_at: "2026-07-26T00:00:00Z",
        reference_note: "品牌确认原图",
        product_media: [
          {
            binding_id: "binding-product-two",
            product_id: "product-two",
            sku: "ZX-TWO",
            product_name: "登记商品二",
            product_version: 1
          }
        ]
      }
    ];
  } else if (path === "/api/v1/content/series" && method === "GET") {
    payload = [
      {
        id: "33333333-3333-4333-8333-333333333333",
        title: "门店里的安静时刻",
        premise: "从真实门店位置继续观察人与选择。",
        revision: 2,
        items: [
          {
            task_id: "series-task-1",
            position: 1,
            title: "沉默，也可以被尊重"
          }
        ]
      }
    ];
  } else if (path === "/api/v1/content/account-expression-profile") {
    payload = {
      account: "总部小红书发布账号",
      content_role: "品牌官方",
      current: {
        version: 2,
        identity_position: "从品牌整体选择与长期表达的位置说话。",
        authority_boundary: "只使用已经确认的品牌和商品事实。",
        audience_relationship: "与受众平等交流，不施压。",
        content_territories: "穿衣选择、商品取舍和品牌生活。",
        default_production_conditions: "一人、一部手机、普通室内。"
      }
    };
  } else if (path === "/api/v1/content/tasks") payload = [];
  else if (path === "/api/v1/content/stream") {
    let events;
    if (body?.message === "你好") {
      events = [
        { event: "conversation", kind: "chat", message: "你好。今天想聊点什么？" }
      ];
    } else if (
      body?.message === "最近店里总有人只想自己看看。" &&
      body?.direct_generate !== true
    ) {
      events = [
        {
          event: "conversation",
          kind: "chat",
          message:
            "这个观察可以慢慢聊；如果你想，也可以把它直接做成一篇完整内容。",
          direct_generation_available: true
        }
      ];
    } else if (
      body?.message?.includes("抖音") &&
      body?.target_conflict_resolution !== "keep_selected"
    ) {
      events = [
        {
          event: "target_conflict",
          mentioned_target: "douyin_video",
          label: "抖音视频"
        }
      ];
    } else if (
      body?.message?.includes("模拟失败") ||
      body?.message?.includes("模拟限流失败")
    ) {
      events = [
        { event: "received" },
        { event: "compiling_context" },
        {
          event: "failed",
          message: body?.message?.includes("限流")
            ? "当前请求较多，请稍后再试。"
            : "这次还没能整理成一份可靠的成品。你的想法仍然保留。",
          error_code: body?.message?.includes("限流")
            ? "RATE_LIMITED"
            : "GENERATION_VALIDATION_FAILED",
          failure_stage: body?.message?.includes("限流")
            ? "rate_limit"
            : "validation",
          retryable: true,
          action: "输入已经保留，可以使用原输入重试。",
          trace_id: "00000000-0000-4000-8000-000000000429"
        }
      ];
    } else if (body?.interaction_mode === "conversation") {
      events = [
        {
          event: "conversation",
          kind: "chat",
          message: "这条先继续聊，不会创建新版本。"
        }
      ];
    } else {
      events = [
        { event: "received" },
        { event: "compiling_context" },
        { event: "generating" },
        { event: "validating" },
        { event: "finalizing" },
        { event: "completed", result: v1 }
      ];
    }
    return new Response(`${events.map(event => JSON.stringify(event)).join("\n")}\n`, {
      status: 200,
      headers: { "Content-Type": "application/x-ndjson" }
    });
  }
  else if (path === "/api/v1/tasks/t1/revisions") {
    if (
      body?.instruction?.includes("模拟修改失败") &&
      revisionFailureCount === 0
    ) {
      revisionFailureCount += 1;
      ok = false;
      status = 503;
      payload = { detail: "这次修改没有完成。" };
    } else {
      revised = true;
      currentRevision = body?.instruction?.includes("模拟修改失败") ? v3 : v2;
      payload = currentRevision;
    }
  } else if (path === "/api/v1/content/tasks/t1/versions") {
    if (deferVersionLoad) {
      await new Promise(resolve => {
        releaseVersionLoad = resolve;
      });
      deferVersionLoad = false;
      releaseVersionLoad = null;
    }
    payload = revised ? [currentRevision, v1] : [v1];
  } else if (path === "/api/v1/tasks/t1/versions/1") payload = v1;
  return {
    ok,
    status,
    json: async () => payload
  };
};

globalThis.__DIYU_INTERACTION__ = {
  requests,
  copiedTexts,
  exportedBlobs,
  setCopyFailure: value => {
    copyShouldFail = value;
  },
  deferNextVersionLoad: () => {
    deferVersionLoad = true;
  },
  releaseDeferredVersionLoad: () => {
    releaseVersionLoad?.();
  },
  setPublicStatus: (contentState, coreState = "available") => {
    publicStatusProjection = {
      ...publicStatusProjection,
      core: { state: coreState },
      content_generation: {
        state: contentState,
        observed_at: contentState === "unknown" ? null : "2026-07-31T11:58:00+00:00",
        fresh_until: contentState === "unknown" ? null : "2026-07-31T12:13:00+00:00"
      },
      text_display: { state: coreState }
    };
  },
  setPublicStatusFailure: value => {
    publicStatusRequestFails = value;
  },
  window: dom.window
};

const workdir = fileURLToPath(new URL("../node_modules/.diyu-ui03-interaction/", import.meta.url));
const outfile = `${workdir}interaction.mjs`;
try {
  await build({
    entryPoints: [fileURLToPath(new URL("./interaction.test.tsx", import.meta.url))],
    outfile,
    bundle: true,
    platform: "node",
    format: "esm",
    target: "node20",
    jsx: "automatic",
    external: ["jsdom", "react", "react-dom", "react/jsx-runtime", "react-dom/client"],
    loader: { ".css": "empty" },
    logLevel: "warning"
  });
  await import(new URL("../node_modules/.diyu-ui03-interaction/interaction.mjs", import.meta.url).href);
} finally {
  await rm(workdir, { recursive: true, force: true });
}
