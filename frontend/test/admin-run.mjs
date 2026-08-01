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
let clipboardShouldFail = false;
const adminRequests = [];
const copiedTexts = [];
Object.defineProperty(globalThis.navigator, "clipboard", {
  value: {
    writeText: async value => {
      if (clipboardShouldFail) {
        throw new dom.window.DOMException("Clipboard denied", "NotAllowedError");
      }
      copiedTexts.push(value);
    }
  },
  configurable: true
});
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
let displayStores = [];
let accounts = [
  {
    id: "33333333-3333-4333-8333-333333333333",
    name: "总部品牌内容运营",
    enabled: true,
    control_organization: {
      id: organizations[0].id,
      name: organizations[0].name,
      source: "declared"
    },
    content_role: {
      name: "品牌官方",
      authority_boundary: "只使用已确认品牌事实",
      speaker_kind: "institutional_account"
    },
    profile: {
      id: "profile-existing",
      version: 1,
      segments: {
        identity_position: "品牌整体表达",
        authority_boundary: "只使用已确认品牌事实",
        audience_relationship: "平等交流",
        content_territories: "品牌与穿着",
        default_production_conditions: "一人一部手机"
      }
    },
    operators: [],
    platform_targets: [
      {
        account_id: "33333333-3333-4333-8333-333333333333",
        target: "xiaohongshu_graphic",
        platform: "小红书",
        media: "图文",
        enabled: true
      }
    ],
    carrier_count: 1
  }
];
let brandEntries = [
  {
    id: "66666666-6666-4666-8666-666666666666",
    category: "reference",
    title: "品牌表达参考",
    source_note: "品牌管理员确认",
    content: "保持真实、克制和清楚。",
    version: "V1",
    status: "active",
    current_version_id: "brand-version-1",
    visibility_scope: "brand_all",
    scope_organizations: [],
    updated_at: "2026-07-27T00:00:00Z",
    impact: "供当前品牌的创作工作参考"
  },
  {
    id: "66666666-6666-4666-8666-666666666667",
    category: "reference",
    title: "笛语品牌身份与内容战略基线",
    source_note: "源文档 DIYU-BRAND-BASELINE-001；原始状态：待品牌方验收",
    content: "私有源文档正文只在管理员详情中回读。",
    version: "V1",
    status: "active",
    current_version_id: "source-version-1",
    visibility_scope: "brand_all",
    scope_organizations: [],
    updated_at: "2026-08-01T00:00:00Z",
    impact: "按稳定语义段和证据等级供相关任务使用",
    source_document: true,
    source_digest: "a".repeat(64),
    activation_status: "brand_user_authorized"
  }
];
let products = [
  {
    id: "77777777-7777-4777-8777-777777777701",
    sku: "DEMO-A",
    display_name: "牛角扣外套",
    facts: {
      category: "外套",
      observable_features: "完整轮廓与牛角扣结构可见"
    },
    source_note: "品牌管理员录入",
    applicability: "演示资料",
    fact_version: 2,
    current_version_id: "product-version-2",
    status: "active",
    visibility_scope: "organizations",
    scope_organizations: [organizations[1]],
    updated_at: "2026-07-27T00:00:00Z",
    field_evidence: [
      {
        field_name: "可见颜色",
        exact_text: "炭灰",
        evidence_level: "V",
        allowed_in_product_fact: true,
        source_digest: "b".repeat(64)
      },
      {
        field_name: "建议价格",
        exact_text: "仅供候选讨论",
        evidence_level: "P",
        allowed_in_product_fact: false,
        source_digest: "c".repeat(64)
      }
    ]
  }
];
let productMediaBindings = [];
let organizationMaterials = [
  {
    id: "44444444-4444-4444-8444-444444444444",
    title: "浙江区域门店拍摄说明",
    original_filename: "shooting-note.txt",
    organization: "浙江区域",
    reference_note: "只参考已确认的室内制作条件",
    reference_version: 1,
    status: "active",
    visibility_scope: "organizations",
    scope_organizations: [organizations[1]],
    created_at: "2026-07-27T00:00:00Z"
  }
];
let brandBaseline = {
  version: 1,
  status: "draft",
  draft: "真实、克制、有依据。"
};
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
      brand_name: "笛语",
      software_truth: {
        usable: 58,
        defective: 0,
        placeholder: 0,
        not_built: 6,
        unproven: 0
      },
      tenant_data_items: [
        {
          id: "tenant-non-product",
          title: "普通非商品内容",
          state: "ready_after_admin_action",
          evidence: ["品牌表达资料与账号画像分开核对"],
          missing: ["确认一份可操作账号"],
          impact: "影响品牌日常表达",
          unaffected: "不影响管理员维护组织和资料",
          action: { label: "管理发布账号", section: "publishing-accounts" }
        },
        {
          id: "tenant-visual",
          title: "P5 商品视觉",
          state: "data_missing",
          evidence: ["当前没有已选择的真实商品媒体"],
          missing: ["为两件商品登记真实图片或视频"],
          impact: "只影响商品视觉成品",
          unaffected: "不影响 P1—P4 与纯文字内容",
          action: { label: "补充组织官方素材", section: "brand-library" }
        }
      ],
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
        logged_in: operators.length,
        product_active: operators.length,
        active: operators.length,
        items: operators.map(item => ({
          id: item.id,
          display_name: item.display_name,
          entry_type: item.entry_type,
          enabled: item.enabled,
          last_login_at: "2026-07-27T00:00:00Z",
          last_product_action_at: "2026-07-27T00:00:00Z",
          last_used_at: "2026-07-27T00:00:00Z",
          content_attempts: item.capabilities?.includes("content") ? 3 : 0,
          display_attempts: item.capabilities?.includes("display") ? 1 : 0
        }))
      },
      activity: {
        content_attempts: 3,
        content_successes: 2,
        content_failures: 1,
        conversations: 2,
        first_generations: 1,
        revisions: 1,
        series_continuations: 1,
        dm01_plans: 1,
        display_attempts: 1,
        display_successes: 1,
        display_failures: 0,
        rate_limited: 0,
        successful_runs: 3,
        failed_runs: 1
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
  } else if (
    path === "/api/v1/tenant-management/display-stores" &&
    method === "GET"
  ) {
    value = displayStores;
  } else if (
    path === "/api/v1/tenant-management/display-stores" &&
    method === "POST"
  ) {
    const store = {
      id: "99999999-9999-4999-8999-999999999901",
      name: body.name,
      enabled: true,
      control_organization_id: body.control_organization_id,
      execution_organization_id: body.execution_organization_id,
      execution_organization:
        organizations.find(item => item.id === body.execution_organization_id)?.name ?? "",
      current_profile: {
        id: "99999999-9999-4999-8999-999999999902",
        version: 1,
        label: "V1",
        rail_profile: {
          upper_comfort_capacity: body.upper_comfort_capacity,
          lower_comfort_capacity: body.lower_comfort_capacity
        }
      }
    };
    displayStores = [store, ...displayStores];
    value = store;
  } else if (
    path.match(/^\/api\/v1\/tenant-management\/display-stores\/[^/]+\/versions$/) &&
    method === "POST"
  ) {
    const storeId = path.split("/").at(-2);
    displayStores = displayStores.map(item =>
      item.id === storeId
        ? {
            ...item,
            name: body.name,
            current_profile: {
              id: "99999999-9999-4999-8999-999999999903",
              version: (item.current_profile?.version ?? 0) + 1,
              label: `V${(item.current_profile?.version ?? 0) + 1}`,
              rail_profile: {
                upper_comfort_capacity: body.upper_comfort_capacity,
                lower_comfort_capacity: body.lower_comfort_capacity
              }
            }
          }
        : item
    );
    value = displayStores.find(item => item.id === storeId);
  } else if (
    path.match(/^\/api\/v1\/tenant-management\/display-stores\/[^/]+\/enabled$/) &&
    method === "PUT"
  ) {
    const storeId = path.split("/").at(-2);
    displayStores = displayStores.map(item =>
      item.id === storeId ? { ...item, enabled: body.enabled } : item
    );
    value = displayStores.find(item => item.id === storeId);
  } else if (path === "/api/v1/tenant-management/publishing-accounts" && method === "GET") {
    value = accounts;
  } else if (path === "/api/v1/tenant-management/onboarding-prefill") {
    value = {
      account_profile_candidate: {
        identity_position: "品牌账号的待确认表达身份",
        authority_boundary: "只使用已确认事实",
        audience_relationship: "与受众平等交流",
        content_territories: "品牌长期内容",
        default_production_conditions: "一人一部手机"
      },
      account_profile_candidate_source: "确定性冷启动候选，保存前必须纠正。"
    };
  } else if (path === "/api/v1/tenant-management/brand-library" && method === "GET") {
    value = brandEntries;
  } else if (
    path === "/api/v1/tenant-management/brand-library/preview" &&
    method === "POST"
  ) {
    value = { ...body, saved: false, message: "这是导入预览" };
  } else if (path === "/api/v1/tenant-management/brand-library" && method === "POST") {
    const created = {
      id: "library-fixture",
      ...body,
      current_version_id: "library-version-1",
      scope_organizations: organizations.filter(item =>
        body.organization_ids?.includes(item.id)
      ),
      updated_at: "2026-07-27T00:00:00Z",
      impact: "供当前品牌的创作工作参考"
    };
    brandEntries = [created, ...brandEntries];
    value = created;
  } else if (
    path.match(/^\/api\/v1\/tenant-management\/brand-library\/[^/]+\/versions$/) &&
    method === "GET"
  ) {
    const entryId = path.split("/").at(-2);
    const entry = brandEntries.find(item => item.id === entryId) ?? brandEntries[0];
    value = [
      {
        id: "library-version-1",
        version_number: 1,
        version: entry.version,
        title: entry.title,
        source_note: entry.source_note,
        content: entry.content,
        visibility_scope: entry.visibility_scope,
        organization_ids: entry.scope_organizations.map(item => item.id),
        status: entry.status,
        is_current: true,
        created_at: entry.updated_at
      }
    ];
  } else if (
    path.match(/^\/api\/v1\/tenant-management\/brand-library\/[^/]+\/versions$/) &&
    method === "POST"
  ) {
    const entryId = path.split("/").at(-2);
    brandEntries = brandEntries.map(item =>
      item.id === entryId ? { ...item, ...body, status: "active" } : item
    );
    value = { id: "library-version-2", version_number: 2, ...body };
  } else if (
    path.match(/^\/api\/v1\/tenant-management\/brand-library\/[^/]+\/enabled$/) &&
    method === "PUT"
  ) {
    const entryId = path.split("/").at(-2);
    brandEntries = brandEntries.map(item =>
      item.id === entryId
        ? { ...item, status: body.enabled ? "active" : "retired" }
        : item
    );
    value = brandEntries.find(item => item.id === entryId);
  } else if (path === "/api/v1/tenant-management/brand-products" && method === "GET") {
    value = products;
  } else if (
    path === "/api/v1/tenant-management/brand-products/preview" &&
    method === "POST"
  ) {
    value = { rows: [], saved: false, message: "这是字段预览" };
  } else if (
    path.match(/^\/api\/v1\/tenant-management\/brand-products\/[^/]+\/versions$/) &&
    method === "GET"
  ) {
    const sku = decodeURIComponent(path.split("/").at(-2));
    const product = products.find(item => item.sku === sku) ?? products[0];
    value = [
      {
        id: "product-version-2",
        fact_version: product.fact_version,
        display_name: product.display_name,
        facts: product.facts,
        source_note: product.source_note,
        applicability: product.applicability,
        visibility_scope: product.visibility_scope,
        organization_ids: product.scope_organizations.map(item => item.id),
        status: product.status,
        is_current: true,
        created_at: product.updated_at
      }
    ];
  } else if (
    path.match(/^\/api\/v1\/tenant-management\/brand-products\/[^/]+\/enabled$/) &&
    method === "PUT"
  ) {
    const sku = decodeURIComponent(path.split("/").at(-2));
    products = products.map(item =>
      item.sku === sku
        ? { ...item, status: body.enabled ? "active" : "retired" }
        : item
    );
    value = products.find(item => item.sku === sku);
  } else if (
    path === "/api/v1/tenant-management/brand-products" &&
    method === "PUT"
  ) {
    const existing = products.find(item => item.sku === body.sku);
    const saved = {
      ...existing,
      ...body,
      id:
        existing?.id ??
        "77777777-7777-4777-8777-777777777702",
      facts: {
        category: body.category,
        colors: body.colors,
        material_or_structure: body.material_or_structure,
        silhouette: body.silhouette,
        observable_features: body.observable_features
      },
      fact_version: (existing?.fact_version ?? 0) + 1,
      current_version_id: "product-version-current",
      status: "active",
      scope_organizations: organizations.filter(item =>
        body.organization_ids?.includes(item.id)
      ),
      updated_at: "2026-07-28T00:00:00Z"
    };
    products = [saved, ...products.filter(item => item.sku !== body.sku)];
    value = saved;
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
    path.match(
      /^\/api\/v1\/tenant-management\/organization-materials\/[^/]+\/versions$/
    ) &&
    method === "GET"
  ) {
    const assetId = path.split("/").at(-2);
    const material =
      organizationMaterials.find(item => item.id === assetId) ??
      organizationMaterials[0];
    value = [
      {
        id: "material-version-1",
        version: material.reference_version,
        title: material.title,
        reference_note: material.reference_note,
        visibility_scope: material.visibility_scope,
        organization_ids: material.scope_organizations.map(item => item.id),
        status: material.status,
        is_current: true,
        created_at: material.created_at
      }
    ];
  } else if (
    path.match(
      /^\/api\/v1\/tenant-management\/organization-materials\/[^/]+\/versions$/
    ) &&
    method === "POST"
  ) {
    const assetId = path.split("/").at(-2);
    organizationMaterials = organizationMaterials.map(item =>
      item.id === assetId
        ? {
            ...item,
            title: body.title,
            reference_note: body.reference_note,
            visibility_scope: body.visibility_scope,
            scope_organizations: organizations.filter(organization =>
              body.organization_ids?.includes(organization.id)
            ),
            reference_version: item.reference_version + 1
          }
        : item
    );
    value = { id: "material-version-2", version_number: 2, ...body };
  } else if (
    path.match(
      /^\/api\/v1\/tenant-management\/organization-materials\/[^/]+\/enabled$/
    ) &&
    method === "PUT"
  ) {
    const assetId = path.split("/").at(-2);
    organizationMaterials = organizationMaterials.map(item =>
      item.id === assetId
        ? { ...item, status: body.enabled ? "active" : "inactive" }
        : item
    );
    value = organizationMaterials.find(item => item.id === assetId);
  } else if (
    path.match(
      /^\/api\/v1\/tenant-management\/organization-materials\/[^/]+\/product-bindings$/
    ) &&
    method === "GET"
  ) {
    const assetId = path.split("/").at(-2);
    value = productMediaBindings.filter(item => item.asset_id === assetId);
  } else if (
    path.match(
      /^\/api\/v1\/tenant-management\/organization-materials\/[^/]+\/product-bindings$/
    ) &&
    method === "POST"
  ) {
    const assetId = path.split("/").at(-2);
    const product = products.find(item => item.id === body.product_id);
    const binding = {
      id: "88888888-8888-4888-8888-888888888801",
      asset_id: assetId,
      product_id: product.id,
      usage_kind: "existing_product_media",
      status: "active",
      sku: product.sku,
      product_name: product.display_name,
      product_status: product.status,
      product_version_id: product.current_version_id,
      product_version: product.fact_version,
      created_at: "2026-07-29T00:00:00Z",
      updated_at: "2026-07-29T00:00:00Z"
    };
    productMediaBindings = [
      binding,
      ...productMediaBindings.filter(
        item =>
          item.asset_id !== assetId ||
          item.product_id !== product.id
      )
    ];
    value = binding;
  } else if (
    path.match(
      /^\/api\/v1\/tenant-management\/organization-materials\/[^/]+\/product-bindings\/[^/]+\/enabled$/
    ) &&
    method === "PUT"
  ) {
    const bindingId = path.split("/").at(-2);
    productMediaBindings = productMediaBindings.map(item =>
      item.id === bindingId
        ? { ...item, status: body.enabled ? "active" : "inactive" }
        : item
    );
    value = productMediaBindings.find(item => item.id === bindingId);
  } else if (path === "/api/v1/ops/tenants" && method === "POST") {
    value = {
      tenant_id: "77777777-7777-4777-8777-777777777777",
      administrator_id: "88888888-8888-4888-8888-888888888888",
      username: body.administrator_username,
      activation_link: "/activate/ui04-ops-fixture",
      activation_url: "https://diyu.example/activate/ui04-ops-fixture"
    };
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
        maintains_organization_materials: body.grants_material_maintenance,
        account_grants: [],
        display_store_grants: displayStores
          .filter(item => body.display_store_ids?.includes(item.id))
          .map(item => ({
            store_id: item.id,
            store_name: item.name,
            store_enabled: item.enabled
          }))
      }
    ];
    value = {
      user_id: operators[0].id,
      username: body.username,
      activation_link: "/activate/ui04-obviously-fake-browser-fixture",
      activation_url:
        "https://diyu.example/activate/ui04-obviously-fake-browser-fixture"
    };
  } else if (
    path === "/api/v1/tenant-management/users/22222222-2222-4222-8222-222222222222/reset" &&
    method === "POST"
  ) {
    value = {
      reset_link: "/activate/ui05-obviously-fake-reset-fixture",
      reset_url:
        "https://diyu.example/activate/ui05-obviously-fake-reset-fixture"
    };
  } else if (
    path === "/api/v1/tenant-management/users/22222222-2222-4222-8222-222222222222/disable" &&
    method === "POST"
  ) {
    operators = operators.map(operator => ({ ...operator, enabled: false }));
    value = { disabled: true };
  } else if (
    path === "/api/v1/tenant-management/users/22222222-2222-4222-8222-222222222222/restore" &&
    method === "POST"
  ) {
    operators = operators.map(operator => ({ ...operator, enabled: true }));
    value = {
      user_id: "22222222-2222-4222-8222-222222222222",
      activation_link: "/activate/ui05-restored-fixture",
      activation_url:
        "https://diyu.example/activate/ui05-restored-fixture"
    };
  } else if (path === "/api/v1/auth/password" && method === "POST") {
    if (body.current_password === "incorrect-current-password") {
      return {
        ok: false,
        status: 401,
        json: async () => ({ detail: "当前密码不正确" })
      };
    }
    value = { changed: true };
  } else if (
    path === "/api/v1/tenant-management/publishing-accounts" &&
    method === "POST"
  ) {
    accounts = [
      {
        id: "33333333-3333-4333-8333-333333333333",
        name: body.name,
        enabled: true,
        control_organization: {
          id: body.control_organization_id,
          name: organizations[0].name,
          source: "declared"
        },
        content_role: {
          name: body.content_role_name,
          authority_boundary: body.initial_profile.authority_boundary,
          speaker_kind: body.speaker_kind
        },
        profile: {
          id: "profile-fixture",
          version: 1,
          segments: body.initial_profile
        },
        platform_targets: [
          {
            account_id: "carrier-fixture",
            target:
              body.channel === "微信视频号"
                ? "wechat_channels_video"
                : body.channel === "小红书"
                  ? "xiaohongshu_graphic"
                  : "douyin_video",
            platform: body.channel,
            media: body.channel === "小红书" ? "图文" : "视频",
            enabled: true
          }
        ],
        carrier_count: 1,
        operators: []
      }
    ];
    value = accounts[0];
  } else if (
    path.endsWith("/speaker-kind") &&
    path.startsWith("/api/v1/tenant-management/publishing-accounts/") &&
    method === "PATCH"
  ) {
    accounts = accounts.map(account => ({
      ...account,
      content_role: {
        ...account.content_role,
        speaker_kind: body.speaker_kind
      }
    }));
    value = {
      account_id: accounts[0]?.id,
      speaker_kind: body.speaker_kind
    };
  } else if (
    path === "/api/v1/tenant-management/platform-carriers" &&
    method === "POST"
  ) {
    accounts = accounts.map(account => ({
      ...account,
      platform_targets: [
        ...account.platform_targets,
        {
          account_id: "carrier-wechat-fixture",
          target: "wechat_channels_video",
          platform: body.channel,
          media: "视频",
          enabled: true
        }
      ]
    }));
    value = {
      id: "carrier-wechat-fixture",
      channel: body.channel,
      carrier_of_account_id: body.source_account_id
    };
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
  } else if (
    path === "/api/v1/admin/brand-expression/confirm" &&
    method === "POST"
  ) {
    brandBaseline = {
      version: brandBaseline.status === "confirmed" ? 2 : 1,
      status: "confirmed",
      draft: body.draft
    };
    value = brandBaseline;
  } else if (path === "/api/v1/admin/brand-expression") {
    value = brandBaseline;
  } else if (path.includes("/ops/runtime-summary")) {
    value = { enabled_tenants: 3, content_runs: 12, display_runs: 4 };
  }
  return { ok: true, status: 200, json: async () => value };
};
globalThis.__DIYU_ADMIN_INTERACTION__ = {
  window: dom.window,
  requests: adminRequests,
  copiedTexts,
  setReducedMotion: value => {
    reducedMotion = value;
  },
  setClipboardFailure: value => {
    clipboardShouldFail = value;
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
