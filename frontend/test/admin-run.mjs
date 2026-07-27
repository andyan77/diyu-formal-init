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
    business_data_kind: "formal_business_data"
  }
];
let operators = [];
let accounts = [];
let products = [];
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
      items:
        operators.length && accounts.length && products.length
          ? []
          : [
              {
                id: "first-publishing-chain",
                title: "补齐首个创作身份",
                detail: "还缺成员、发布账号或商品资料。",
                unlock: "开始日常创作",
                state: "needs_action"
              }
            ]
    };
  } else if (path === "/api/v1/tenant-management/operators" && method === "GET") {
    value = operators;
  } else if (path === "/api/v1/tenant-management/organizations") {
    value = organizations;
  } else if (path === "/api/v1/tenant-management/control-organizations") {
    value = organizations;
  } else if (path === "/api/v1/tenant-management/publishing-accounts" && method === "GET") {
    value = accounts;
  } else if (path === "/api/v1/tenant-management/brand-products" && method === "GET") {
    value = products;
  } else if (
    path === "/api/v1/tenant-management/organization-materials" ||
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
        publishing_accounts: "",
        manages_tenant: Boolean(body.grants_tenant_management),
        maintains_organization_materials: Boolean(body.grants_material_maintenance),
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
        channel: body.channel,
        content_role: body.content_role_name,
        voice_boundary: body.voice_boundary,
        carrier_of_account_id: null,
        carrier_of_account: null,
        operators: [{ id: body.operator_id, display_name: operators[0].display_name }]
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
