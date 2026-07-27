import { build } from "esbuild";
import { rm } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { JSDOM } from "jsdom";

const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
  url: "http://localhost/",
  pretendToBeVisual: true
});
for (const name of [
  "window",
  "document",
  "navigator",
  "Event",
  "CustomEvent",
  "KeyboardEvent",
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
let reducedMotion = false;
const adminRequests = [];
const organizations = [
  {
    id: "11111111-1111-4111-8111-111111111111",
    name: "笛语服饰管理组织",
    level: "company",
    organization_level: "company",
    business_data_kind: "formal_business_data"
  },
  {
    id: "11111111-1111-4111-8111-111111111112",
    name: "浙江区域",
    level: "region",
    organization_level: "region",
    business_data_kind: "formal_business_data"
  },
  {
    id: "11111111-1111-4111-8111-111111111113",
    name: "柯桥门店",
    level: "operating_unit",
    organization_level: "operating_unit",
    business_data_kind: "formal_business_data"
  }
];
let operators = [];
let accounts = [];
let products = [
  {
    sku: "DEMO-A",
    display_name: "牛角扣外套",
    facts: {
      category: "外套",
      observable_features: "完整轮廓与牛角扣结构可见"
    },
    source_note: "品牌管理员录入",
    applicability: "演示资料",
    fact_version: 2,
    visibility_scope: "organizations",
    scope_organizations: [organizations[1]],
    updated_at: "2026-07-27T00:00:00Z"
  }
];
let organizationMaterials = [
  {
    id: "44444444-4444-4444-8444-444444444444",
    title: "浙江区域门店拍摄说明",
    original_filename: "shooting-note.txt",
    organization: "浙江区域",
    reference_note: "只参考已确认的室内制作条件",
    reference_version: 1,
    visibility_scope: "organizations",
    scope_organizations: [organizations[1]],
    created_at: "2026-07-27T00:00:00Z"
  }
];
let failedPath = null;
let unmetRequest = {
  stable_request_id: "UI04-UNMET-FIXTURE",
  request_text: "希望以后可以更容易整理门店当天的选题。",
  gap_type: "unclassified",
  status: "received",
  response_text: "",
  created_at: "2026-07-26T00:00:00Z"
};
dom.window.matchMedia = query => ({
  matches: query.includes("prefers-reduced-motion") && reducedMotion,
  media: query,
  onchange: null,
  addListener: () => undefined,
  removeListener: () => undefined,
  addEventListener: () => undefined,
  removeEventListener: () => undefined,
  dispatchEvent: () => true
});
globalThis.fetch = async (input, init = {}) => {
  const url = new URL(String(input), "http://localhost");
  const path = url.pathname;
  const method = String(init.method ?? "GET").toUpperCase();
  const body = init.body ? JSON.parse(String(init.body)) : null;
  adminRequests.push({ path, method, body });
  if (failedPath === path) {
    return {
      ok: false,
      status: 503,
      json: async () => ({ detail: "当前资料暂时无法读取，请稍后再试。" })
    };
  }
  let value = {};
  if (path === "/api/v1/admin/readiness") {
    value = {
      items: [
        {
          id: "account-expression",
          title: "品牌与账号表达",
          status: accounts.length ? "available" : "unavailable",
          evidence: accounts.length ? ["已有发布账号和当前账号画像"] : [],
          gaps: accounts.length ? [] : ["还缺一个逻辑发布账号"],
          impact: "影响内容能否以清楚身份开始",
          action: { label: "管理发布账号", section: "accounts" },
          source: "当前租户资料",
          version: "V1",
          evaluated_at: "2026-07-27T00:00:00Z"
        },
        {
          id: "product-content",
          title: "商品选择与解释",
          status: products.length ? "available" : "conditional",
          evidence: products.length ? ["已有商品事实"] : ["非商品内容仍可使用"],
          gaps: products.length ? [] : ["还缺商品资料"],
          impact: "只影响需要商品承重的内容",
          action: { label: "补商品资料", section: "library" },
          source: "当前品牌资料",
          version: "V1",
          evaluated_at: "2026-07-27T00:00:00Z"
        }
      ]
    };
  } else if (path === "/api/v1/tenant-management/team-usage") {
    value = {
      window_days: Number(url.searchParams.get("window_days") ?? "7"),
      members: {
        registered: operators.length,
        activated: operators.length,
        enabled: operators.filter(item => item.enabled).length,
        disabled: operators.filter(item => !item.enabled).length,
        active: operators.length,
        items: operators.map(item => ({
          id: item.id,
          display_name: item.display_name,
          entry_type: item.entry_type,
          enabled: item.enabled,
          last_used_at: "2026-07-27T00:00:00Z",
          content_attempts: item.capabilities?.includes("content") ? 3 : 0,
          display_attempts: item.capabilities?.includes("display") ? 1 : 0
        }))
      },
      activity: {
        content_attempts: 3,
        content_successes: 2,
        content_failures: 1,
        revisions: 1,
        series_continuations: 1,
        display_attempts: 1,
        display_successes: 1,
        display_failures: 0,
        rate_limited: 0
      },
      provider_usage: {
        label: "已记录模型用量",
        total_tokens: 1200,
        is_complete_billing_total: false
      },
      distribution: { publishing_identities: [], platforms: [] }
    };
  } else if (path === "/api/v1/tenant-management/operators" && method === "GET") {
    value = operators;
  } else if (path === "/api/v1/tenant-management/organizations") {
    value = organizations;
  } else if (path === "/api/v1/tenant-management/control-organizations") {
    value = organizations;
  } else if (path === "/api/v1/tenant-management/publishing-accounts" && method === "GET") {
    value = accounts;
  } else if (path === "/api/v1/tenant-management/brand-library" && method === "GET") {
    value = [];
  } else if (path === "/api/v1/tenant-management/brand-library" && method === "POST") {
    value = { id: "library-fixture", ...body };
  } else if (path === "/api/v1/tenant-management/brand-products" && method === "GET") {
    value = products;
  } else if (
    path === "/api/v1/tenant-management/organization-materials" &&
    method === "GET"
  ) {
    value = organizationMaterials;
  } else if (
    path === "/api/v1/tenant-management/organization-materials" &&
    method === "POST"
  ) {
    organizationMaterials = [
      ...organizationMaterials,
      {
        id: "55555555-5555-4555-8555-555555555555",
        title: body.title,
        original_filename: body.filename,
        organization: organizations.find(
          item => item.id === body.organization_id
        )?.name,
        reference_note: body.reference_note,
        reference_version: 1,
        visibility_scope: body.visibility_scope,
        scope_organizations: organizations.filter(item =>
          body.organization_ids?.includes(item.id)
        ),
        created_at: "2026-07-27T00:00:00Z"
      }
    ];
    value = organizationMaterials.at(-1);
  } else if (
    path === "/api/v1/ops/tenants" ||
    path === "/api/v1/display/tasks"
  ) {
    value = [];
  } else if (
    path === "/api/v1/ops/unmet-capability-requests" &&
    method === "GET"
  ) {
    value = [unmetRequest];
  } else if (
    path === "/api/v1/ops/unmet-capability-requests/UI04-UNMET-FIXTURE" &&
    method === "POST"
  ) {
    unmetRequest = { ...unmetRequest, ...body };
    value = unmetRequest;
  } else if (path === "/api/v1/tenant-management/users" && method === "POST") {
    operators = [
      {
        id: "22222222-2222-4222-8222-222222222222",
        display_name: body.display_name,
        username: body.username,
        organization_id: organizations[0].id,
        organization: organizations[0].name,
        entry_type: body.entry_type,
        enabled: true,
        capabilities: body.capabilities,
        manages_tenant: body.entry_type === "tenant_admin",
        account_grants: []
      }
    ];
    value = {
      user_id: operators[0].id,
      username: body.username,
      activation_link: "/activate/ui04-obviously-fake-browser-fixture"
    };
  } else if (
    path === "/api/v1/tenant-management/publishing-accounts" &&
    method === "POST"
  ) {
    accounts = [
      {
        id: "33333333-3333-4333-8333-333333333333",
        name: body.name,
        control_organization: {
          id: body.control_organization_id,
          name: organizations[0].name,
          source: "declared"
        },
        content_role: {
          name: body.content_role_name,
          authority_boundary: body.initial_profile.authority_boundary
        },
        profile: {
          id: "profile-fixture",
          version: 1,
          segments: body.initial_profile
        },
        platform_targets: [
          {
            account_id: "carrier-fixture",
            target: body.target,
            platform: "抖音",
            media: "视频"
          }
        ],
        carrier_count: 1,
        operators: [{ id: body.operator_id, display_name: operators[0]?.display_name ?? "成员" }]
      }
    ];
    value = accounts[0];
  } else if (
    path === "/api/v1/tenant-management/brand-products" &&
    method === "PUT"
  ) {
    products = [
      {
        sku: body.sku,
        display_name: body.display_name,
        facts: body,
        source_note: body.source_note,
        applicability: body.applicability,
        fact_version: 1
      }
    ];
    value = products[0];
  } else if (path.includes("/admin/brand-expression")) {
    value = { version: 1, status: "confirmed", draft: "真实、克制、有依据。" };
  } else if (path.includes("/ops/runtime-summary")) {
    value = { enabled_tenants: 3, content_runs: 12, display_runs: 4 };
  }
  return { ok: true, status: 200, json: async () => value };
};
globalThis.__DIYU_ADMIN_INTERACTION__ = {
  window: dom.window,
  requests: adminRequests,
  setReducedMotion: value => {
    reducedMotion = value;
  },
  setFailedPath: value => {
    failedPath = value;
  }
};

const workdir = fileURLToPath(new URL("../node_modules/.diyu-ui03-surfaces/", import.meta.url));
const outfile = `${workdir}interaction.mjs`;
try {
  await build({
    entryPoints: [fileURLToPath(new URL("./admin_interaction.test.tsx", import.meta.url))],
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
  await import(new URL("../node_modules/.diyu-ui03-surfaces/interaction.mjs", import.meta.url).href);
} finally {
  await rm(workdir, { recursive: true, force: true });
}
