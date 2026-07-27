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
  applied_direction: ["幽默玩梗"]
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

const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
  url: "http://localhost/content?target=xiaohongshu_graphic",
  pretendToBeVisual: true
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
let copyShouldFail = false;
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
dom.window.__DIYU_BOOTSTRAP__ = {
  application: "content",
  generator_mode: "deepseek",
  formal_runtime: true,
  identity: {
    operator: "总部内容运营甲",
    organization: "笛语服饰管理组织",
    account: "总部小红书发布账号",
    content_role: "品牌官方",
    brand: "笛语服饰"
  },
  current_target: "xiaohongshu_graphic",
  targets: [
    { value: "douyin_video", label: "抖音短视频" },
    { value: "xiaohongshu_video", label: "小红书视频" },
    { value: "xiaohongshu_graphic", label: "小红书图文" },
    { value: "wechat_channels_video", label: "微信视频号视频" }
  ]
};

globalThis.fetch = async (input, init = {}) => {
  const url = new URL(String(input), "http://localhost");
  const path = url.pathname;
  const method = init.method ?? "GET";
  const body = init.body ? JSON.parse(String(init.body)) : null;
  requests.push({ method, path, query: url.search, body });
  let payload = {};
  let ok = true;
  let status = 200;
  if (path === "/api/v1/content/expression-catalog") payload = catalogResponse(bodyEnabled);
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
  else if (
    path === "/api/v1/content" &&
    body?.creative_direction?.custom_text === "上新直播"
  ) {
    ok = false;
    status = 422;
    payload = {
      detail:
        "「上新直播」目前还缺少可靠资料或直接能力，暂不能稳定完成。你的原话会留在输入框中，可以换一种方向再试。"
    };
  } else if (path === "/api/v1/content") payload = v1;
  else if (path === "/api/v1/tasks/t1/revisions") {
    revised = true;
    payload = v2;
  } else if (path === "/api/v1/content/tasks/t1/versions") {
    payload = revised ? [v2, v1] : [v1];
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
