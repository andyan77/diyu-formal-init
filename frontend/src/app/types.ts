export type Target =
  | "douyin_video"
  | "xiaohongshu_video"
  | "xiaohongshu_graphic"
  | "wechat_channels_video";

export interface BootstrapContext {
  application:
    | "public"
    | "login"
    | "activation"
    | "content"
    | "display"
    | "tenant_user"
    | "tenant_management"
    | "ops"
    | "status";
  identity?: Record<string, string>;
  entry?: "tenant-user" | "tenant-admin" | "ops";
  current_target?: Target | null;
  targets?: Array<{ value: Target; label: string }>;
  formal_runtime?: boolean;
  generator_mode?: "stub" | "deepseek";
  capabilities?: Array<"content" | "display">;
  service_state?: "available" | "unavailable";
  runtime_summary?: Record<string, number | null>;
  pending_requests?: number;
}

export interface ContentVersion {
  kind: "content";
  task_id: string;
  version_id: string;
  version: number;
  outline: string;
  body: string;
  ai_generated: boolean;
  aigc_label?: string | null;
  aigc_release_reminder?: string | null;
  target?: Target | null;
  target_key?: Target | null;
  adapted_from?: string | null;
  translation_notice?: string | null;
  applied_direction?: string[];
  created_at?: string;
}

export interface RecentContent {
  task_id: string;
  version_id: string;
  version: number;
  title: string;
  target?: Target;
  updated_at: string;
  status: string;
}

export interface CatalogOption {
  stable_id: string;
  label: string;
  capability_state: "verified" | "composable";
  body_related: boolean;
}

export interface CatalogAxis {
  key: "topic" | "mechanism" | "style" | "form" | "continuity";
  label: string;
  question: string;
  options: CatalogOption[];
}

export interface ExpressionCatalog {
  catalog_version: string;
  body_related_enabled: boolean;
  preference_session: "normal" | "bypassed";
  saved_defaults: Record<string, string>;
  axes: CatalogAxis[];
}

export interface CreationPreference {
  exists: boolean;
  enabled: boolean;
  version: number | null;
  direction_defaults: Record<string, string>;
  collaboration_note: string;
  body_related_opt_in: boolean;
}

export interface Material {
  id: string;
  title: string;
  media_type: "text" | "image" | "video" | string;
  scope: "personal" | "organization";
  created_at: string;
  status: string;
  reference_note?: string;
}

export interface AccountExpression {
  account: string;
  content_role: string;
  current: {
    version: number;
    identity_position: string;
    authority_boundary: string;
    audience_relationship: string;
    content_territories: string;
    default_production_conditions: string;
  } | null;
}

export type AssistantReply = {
  kind: "greeting" | "question" | "handoff";
  message: string;
};
