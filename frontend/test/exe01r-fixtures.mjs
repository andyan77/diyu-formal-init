// Deterministic fixtures shared by the EXE-01R interaction suites.
//
// Two publishing identities, because every contract this package added is
// about what happens when you move between them.

export const IDENTITY_HQ = "identity-hq";
export const IDENTITY_STORE = "identity-store";

const HQ_TARGETS = [
  { value: "douyin_video", label: "抖音视频", platform_label: "抖音", format_label: "视频" },
  { value: "xiaohongshu_graphic", label: "小红书图文", platform_label: "小红书", format_label: "图文" },
  { value: "xiaohongshu_video", label: "小红书视频", platform_label: "小红书", format_label: "视频" }
];
const STORE_TARGETS = [
  { value: "douyin_video", label: "抖音视频", platform_label: "抖音", format_label: "视频" },
  { value: "xiaohongshu_graphic", label: "小红书图文", platform_label: "小红书", format_label: "图文" }
];

export const BOOTSTRAP = {
  application: "content",
  generator_mode: "stub",
  formal_runtime: true,
  identity: {
    tenant_id: "00000000-0000-0000-0000-000000000001",
    operator_id: "00000000-0000-0000-0000-000000000011",
    operator: "总部内容运营甲",
    organization: "笛语服饰管理组织",
    account: "总部品牌内容运营",
    content_role: "品牌官方",
    brand: "笛语服饰"
  },
  current_target: "xiaohongshu_graphic",
  current_publishing_identity_id: IDENTITY_HQ,
  publishing_identities: [
    {
      id: IDENTITY_HQ,
      name: "总部品牌内容运营",
      content_role: "品牌官方",
      profile_summary: "从品牌整体选择和长期表达的位置说话。",
      platform_targets: HQ_TARGETS
    },
    {
      id: IDENTITY_STORE,
      name: "柯桥门店人物",
      content_role: "门店人物",
      profile_summary: "从门店日常和本人可确认的观察出发。",
      platform_targets: STORE_TARGETS
    }
  ],
  targets: HQ_TARGETS,
  capabilities: ["content"]
};

export const version = (overrides = {}) => ({
  kind: "content",
  task_id: "task-hq-1",
  version_id: "version-hq-1",
  version: 1,
  outline: "沉默，也可以被尊重",
  body: "完整台词：有人走进门店，只想自己看看。",
  ai_generated: true,
  aigc_label: "AI 辅助生成",
  aigc_release_reminder: "发布前请使用平台 AI 内容声明功能。",
  target_key: "xiaohongshu_graphic",
  ...overrides
});

export const EXPRESSION_CATALOG = {
  catalog_version: "catalog-v1",
  body_related_enabled: false,
  preference_session: "normal",
  saved_defaults: {},
  axes: []
};

export const PREFERENCE = {
  enabled: false,
  direction_defaults: {},
  collaboration_note: "",
  body_related_opt_in: false
};

export const ACCOUNT_PROFILE = {
  account: "总部小红书发布账号",
  content_role: "品牌官方",
  current: null
};
