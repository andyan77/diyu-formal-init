import { build } from "esbuild";
import { rm } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { JSDOM } from "jsdom";

const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
  url: "http://localhost/display",
  pretendToBeVisual: true
});

for (const name of [
  "window",
  "document",
  "navigator",
  "Event",
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

const requests = [];
const copiedTexts = [];
Object.defineProperty(dom.window.navigator, "clipboard", {
  value: { writeText: async value => copiedTexts.push(String(value)) },
  configurable: true
});
dom.window.confirm = () => true;

let displayQuestion = false;
let displayRevised = false;
let series = [
  {
    id: "s1",
    title: "门店里的安静时刻",
    premise: "让每一篇接住前一个真实处境。",
    revision: 2,
    items: [
      { task_id: "t1", position: 1, title: "第一篇" },
      { task_id: "t2", position: 2, title: "第二篇" }
    ]
  }
];
let materials = [
  {
    id: "m1",
    title: "我的文字观察",
    media_type: "text",
    scope: "personal",
    created_at: "2026-07-26T00:00:00Z",
    status: "active",
    reference_note: ""
  },
  {
    id: "m2",
    title: "还没有说明的图片",
    media_type: "image",
    scope: "personal",
    created_at: "2026-07-26T00:00:00Z",
    status: "active",
    reference_note: ""
  },
  {
    id: "m3",
    title: "组织里的商品细节",
    media_type: "image",
    scope: "organization",
    created_at: "2026-07-26T00:00:00Z",
    status: "active",
    reference_note: "只有袖口和扣子。"
  }
];
let organizationMaterials = [
  {
    id: "om1",
    title: "总部官方版式参考",
    media_type: "image",
    status: "active",
    reference_note: "仅记录版式与留白，不补造现实对象。",
    reference_version: 1,
    organization_id: "org-hq",
    organization: "总部团队"
  }
];
let organizationMaterialVersions = [
  {
    id: "omv1",
    version: 1,
    title: "总部官方版式参考",
    reference_note: "仅记录版式与留白，不补造现实对象。",
    is_current: true,
    created_at: "2026-08-01T00:00:00Z"
  }
];

const displayV1 = {
  kind: "display",
  task_id: "d1",
  version_id: "dv1",
  version: 1,
  body: "门店墙面挂杆参考方案\n\n左侧（主焦点）：上杆 外套×2（正挂）；下杆 裤装×1（侧挂）。\n\n中间（中性承接）：上杆 衬衫×2（正挂）；下杆 针织×1（侧挂）。\n\n右侧（较弱回应）：上杆 裙装×1（正挂）；下杆 留空。\n\n执行步骤：1. 先挂左侧。2. 再补中间。"
};
const displayV2 = {
  ...displayV1,
  version_id: "dv2",
  version: 2,
  body: "门店墙面挂杆参考方案\n\n本次只将中间上杆的衬衫减少一件，其余保持不动。\n\n左侧（主焦点）：上杆 外套×2（正挂）；下杆 裤装×1（侧挂）。\n\n中间（中性承接）：上杆 衬衫×1（正挂）；下杆 针织×1（侧挂）。\n\n右侧（较弱回应）：上杆 裙装×1（正挂）；下杆 留空。\n\n执行步骤：1. 先挂左侧。2. 再补中间。"
};

globalThis.fetch = async (input, init = {}) => {
  const url = new URL(String(input), "http://localhost");
  const path = url.pathname;
  const method = init.method ?? "GET";
  const body = init.body ? JSON.parse(String(init.body)) : null;
  requests.push({ method, path, body });
  let payload = {};
  let status = 200;

  if (path === "/api/v1/display/tasks") {
    payload = [{ task_id: "d1", version_id: displayRevised ? "dv2" : "dv1", version: displayRevised ? 2 : 1, title: "本次墙面方案", updated_at: "2026-07-26T00:00:00Z" }];
  } else if (path === "/api/v1/display/products") {
    payload = [
      { sku: "SKU-A", display_name: "上装 A", display_family: "upper", product_version_id: "pv-a" },
      { sku: "SKU-B", display_name: "下装 B", display_family: "lower", product_version_id: "pv-b" }
    ];
  } else if (path === "/api/v1/display" && method === "POST") {
    payload = displayQuestion ? { kind: "question", message: "请补充这组墙的上下挂杆条件。" } : displayV1;
  } else if (path === "/api/v1/display-tasks/d1/revisions") {
    displayRevised = true;
    payload = displayV2;
  } else if (path === "/api/v1/display/tasks/d1/versions") {
    payload = displayRevised ? [displayV2, displayV1] : [displayV1];
  } else if (path === "/api/v1/display-tasks/d1/versions/1") {
    payload = displayV1;
  } else if (path === "/api/v1/content/series" && method === "GET") {
    payload = series;
  } else if (path === "/api/v1/content/series" && method === "POST") {
    const created = { id: "s2", title: body.title, premise: body.premise, revision: 1, items: [] };
    series = [created, ...series];
    payload = created;
  } else if (path === "/api/v1/content/series/s1/items" && method === "PUT") {
    series = series.map(item => item.id === "s1" ? { ...item, revision: 3, items: body.task_ids.map((task_id, index) => ({ ...item.items.find(entry => entry.task_id === task_id), task_id, position: index + 1 })) } : item);
    payload = series.find(item => item.id === "s1");
  } else if (path === "/api/v1/user/organization-materials" && method === "GET") {
    payload = organizationMaterials;
  } else if (path === "/api/v1/user/organization-materials/om1/versions" && method === "GET") {
    payload = organizationMaterialVersions;
  } else if (path === "/api/v1/user/organization-materials/om1/versions" && method === "POST") {
    organizationMaterialVersions = organizationMaterialVersions.map(item => ({
      ...item,
      is_current: false
    }));
    organizationMaterialVersions.unshift({
      id: "omv2",
      version: 2,
      title: body.title,
      reference_note: body.reference_note,
      is_current: true,
      created_at: "2026-08-01T00:01:00Z"
    });
    organizationMaterials = organizationMaterials.map(item =>
      item.id === "om1"
        ? {
            ...item,
            title: body.title,
            reference_note: body.reference_note,
            reference_version: 2
          }
        : item
    );
    payload = organizationMaterials[0];
  } else if (path === "/api/v1/user/organization-materials/om1/enabled" && method === "PUT") {
    organizationMaterials = organizationMaterials.map(item =>
      item.id === "om1"
        ? { ...item, status: body.enabled ? "active" : "inactive" }
        : item
    );
    payload = organizationMaterials[0];
  } else if (path === "/api/v1/materials" && method === "GET") {
    payload = materials;
  } else if (path === "/api/v1/materials/m2/reference-note" && method === "PATCH") {
    materials = materials.map(item => item.id === "m2" ? { ...item, reference_note: body.reference_note } : item);
    payload = materials.find(item => item.id === "m2");
  } else {
    status = 404;
    payload = { detail: `未准备的测试请求：${method} ${path}` };
  }
  return { ok: status < 400, status, json: async () => payload };
};

globalThis.__DIYU_UI04_USER_PATHS__ = { window: dom.window, requests, copiedTexts, setDisplayQuestion: value => { displayQuestion = value; } };

const workdir = fileURLToPath(new URL("../node_modules/.diyu-ui04-user-paths/", import.meta.url));
const outfile = `${workdir}interaction.mjs`;
try {
  await build({
    entryPoints: [fileURLToPath(new URL("./ui04_user_paths.test.tsx", import.meta.url))],
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
  await import(new URL("../node_modules/.diyu-ui04-user-paths/interaction.mjs", import.meta.url).href);
} finally {
  await rm(workdir, { recursive: true, force: true });
}
