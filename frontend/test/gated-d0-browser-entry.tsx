import { createRoot } from "react-dom/client";

import TenantAdminApp from "../src/app/TenantAdminApp";

declare global {
  interface Window {
    __GATED_D0_RESULT__?: { status: "PASS" | "FAIL"; detail: string; requests?: RequestRecord[] };
  }
}

type RequestRecord = {
  path: string;
  method: string;
  body: Record<string, unknown> | null;
};

const requests: RequestRecord[] = [];
const source = {
  source_segment_id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
  source_document_id: "ffffffff-ffff-4fff-8fff-ffffffffffff",
  source_id: "DIYU-BRAND-BASELINE-001",
  source_title: "笛语品牌身份与内容战略基线",
  source_version: "v1",
  source_digest: "b".repeat(64),
  source_document_digest: "e".repeat(64),
  source_locator: "§一",
  heading_path: ["品牌身份"],
  semantic_kind: "brand_fact",
  source_text: "笛语从真实穿衣问题出发。"
};
let publication: {
  contract_version: string;
  current: Record<string, unknown> | null;
  history: Record<string, unknown>[];
} = {
  contract_version: "brand-publication-projection-v2",
  current: null,
  history: [] as Record<string, unknown>[]
};

function response(value: unknown): Response {
  return { ok: true, status: 200, json: async () => value } as Response;
}

function publicationCandidate(body: Record<string, unknown> | null): Record<string, unknown> {
  const items = (body?.items ?? []) as Array<Record<string, unknown>>;
  return {
    id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
    version: 1,
    status: "candidate",
    digest: "d".repeat(64),
    contract_version: "brand-publication-projection-v2",
    created_at: "2026-08-08T00:00:00Z",
    confirmed_at: null,
    is_current: false,
    items: items.map((item, index) => ({
      ...item,
      position: index + 1,
      source_kind: "brand_source_segment",
      source_segment_id: source.source_segment_id,
      source_document_id: source.source_document_id,
      source_id: source.source_id,
      source_locator: source.source_locator,
      source_label: source.source_title,
      source_version: source.source_version,
      source_digest: source.source_digest,
      source_document_digest: source.source_document_digest,
      scope_organization_ids: item.organization_ids,
      authority_class: "headquarters_formal",
      semantic_subject_type: "brand",
      semantic_subject_id: null,
      claim_key: "identity",
      scope_contract_version: "publication-item-scope-v2"
    }))
  };
}

function confirmPublication(): Record<string, unknown> {
  const candidate = publication.history[0] ?? {};
  const confirmed = {
    ...candidate, status: "confirmed", confirmed_at: "2026-08-08T00:01:00Z", is_current: true
  };
  publication = { ...publication, current: confirmed, history: [confirmed] };
  return confirmed;
}

function fixtureResponse(
  path: string, method: string, body: Record<string, unknown> | null
): Response {
  if (path === "/api/v1/tenant-management/brand-library") return response([]);
  if (path === "/api/v1/tenant-management/brand-publication" && method === "GET") {
    return response(publication);
  }
  if (path === "/api/v1/tenant-management/brand-publication/sources") return response([source]);
  if (path === "/api/v1/tenant-management/brand-feedback-observations") return response([]);
  if (path === "/api/v1/tenant-management/brand-relevance-governance") {
    return response({ authorizations: [], qualifications: [] });
  }
  if (path === "/api/v1/tenant-management/organizations") {
    return response([
      {
        id: "11111111-1111-4111-8111-111111111111",
        name: "笛语总部",
        level: "company",
        organization_level: "company",
        enabled: true,
        business_data_kind: "formal_business_data"
      }
    ]);
  }
  if (
    path === "/api/v1/tenant-management/brand-products" ||
    path === "/api/v1/tenant-management/organization-materials"
  ) return response([]);
  if (path === "/api/v1/tenant-management/brand-publication/preview" && method === "POST") {
    const items = (body?.items ?? []) as unknown[];
    return response({
      contract_version: "brand-publication-projection-v2",
      version: 1,
      digest: "d".repeat(64),
      item_count: items.length
    });
  }
  if (path === "/api/v1/tenant-management/brand-publication/candidates" && method === "POST") {
    const candidate = publicationCandidate(body);
    publication = { ...publication, history: [candidate] };
    return response(candidate);
  }
  if (
    /^\/api\/v1\/tenant-management\/brand-publication\/[^/]+\/confirm$/.test(path) &&
    method === "POST"
  ) {
    return response(confirmPublication());
  }
  return response({});
}

window.fetch = async (input, init = {}) => {
  const path = new URL(String(input), window.location.href).pathname;
  const method = String(init.method ?? "GET").toUpperCase();
  const body = init.body ? JSON.parse(String(init.body)) as Record<string, unknown> : null;
  requests.push({ path, method, body });
  return fixtureResponse(path, method, body);
};

function byText(selector: string, text: string): HTMLElement {
  const node = Array.from(document.querySelectorAll(selector)).find(item =>
    (item.textContent ?? "").includes(text)
  );
  if (!(node instanceof HTMLElement)) throw new Error(`missing ${selector}: ${text}`);
  return node;
}

function click(node: HTMLElement): void {
  node.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
}

function setValue(node: HTMLInputElement | HTMLTextAreaElement, value: string): void {
  const prototype = node instanceof HTMLTextAreaElement
    ? HTMLTextAreaElement.prototype
    : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(prototype, "value")?.set?.call(node, value);
  node.dispatchEvent(new Event("input", { bubbles: true }));
}

async function waitFor(check: () => boolean, label: string): Promise<void> {
  const started = performance.now();
  while (performance.now() - started < 10000) {
    if (check()) return;
    await new Promise(resolve => setTimeout(resolve, 25));
  }
  throw new Error(`timeout: ${label}; body=${document.body.textContent?.slice(0, 500) ?? ""}`);
}

async function renderAdminLibrary(): Promise<void> {
  const root = document.getElementById("root");
  if (!root) throw new Error("missing root");
  createRoot(root).render(
    <TenantAdminApp
      context={{
        application: "tenant_management",
        formal_runtime: true,
        identity: {
          operator_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
          operator: "品牌管理员",
          organization: "笛语总部",
          brand: "笛语"
        }
      }}
      onPasswordUpdated={() => undefined}
    />
  );
  await waitFor(() => document.body.textContent?.includes("品牌资料库") === true, "admin shell");
  click(byText("button", "品牌资料库"));
  await waitFor(() => document.body.textContent?.includes("核对创作端品牌表达") === true, "library");
}

async function run(): Promise<void> {
  await renderAdminLibrary();
  click(byText("button", "核对创作端品牌表达"));
  await waitFor(() => document.querySelector(".publication-source-list input") !== null, "publication drawer");
  click(document.querySelector(".publication-source-list input") as HTMLInputElement);
  await waitFor(() => document.querySelector(".publication-draft textarea") !== null, "draft");
  setValue(
    document.querySelector(".publication-draft textarea") as HTMLTextAreaElement,
    "笛语帮助人们看清日常穿衣选择。"
  );
  click(byText(".publication-applicability label", "穿衣选择"));
  click(byText(".tenant-drawer button", "预览 V2 合同"));
  await waitFor(() => document.body.textContent?.includes("待保存 V1") === true, "preview");
  click(byText(".tenant-drawer button", "保存为待确认版本"));
  await waitFor(
    () => requests.some(item => item.path.endsWith("/candidates") && item.method === "POST"),
    "candidate request"
  );
  const candidate = requests.find(item => item.path.endsWith("/candidates") && item.method === "POST");
  const item = ((candidate?.body?.items ?? []) as Array<Record<string, unknown>>)[0];
  if (
    item.visibility_scope !== "brand_all" ||
    !Array.isArray(item.organization_ids) ||
    item.organization_ids.length !== 0 ||
    item.fact_subject !== "brand_identity" ||
    typeof item.effective_at !== "string"
  ) throw new Error("business-owned V2 fields did not reach the API request");
  for (const forbidden of [
    "tenant_id", "brand_id", "contract_version", "scope_contract_version",
    "authority_class", "source_ref", "source_version", "source_digest"
  ]) {
    if (forbidden in item) throw new Error(`client submitted server-owned ${forbidden}`);
  }
  await waitFor(
    () => document.body.textContent?.includes("确认作为当前品牌表达") === true,
    "candidate readback"
  );
  click(byText("button", "确认作为当前品牌表达"));
  await waitFor(
    () => requests.some(request => request.path.endsWith("/confirm") && request.method === "POST"),
    "confirm request"
  );
  await waitFor(() => document.body.textContent?.includes("当前使用") === true, "confirmed readback");
  window.__GATED_D0_RESULT__ = {
    status: "PASS",
    detail: "React V2 preview/save/confirm/readback contract passed",
    requests
  };
}

void run().catch(error => {
  window.__GATED_D0_RESULT__ = {
    status: "FAIL",
    detail: error instanceof Error ? error.stack ?? error.message : String(error),
    requests
  };
});
