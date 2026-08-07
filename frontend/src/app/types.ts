export type Target =
  | "douyin_video"
  | "xiaohongshu_video"
  | "xiaohongshu_graphic"
  | "wechat_channels_video";

export interface PlatformTarget {
  value: Target;
  label: string;
  platform_label: string;
  format_label: string;
}

export interface PublishingIdentity {
  id: string;
  name: string;
  profile_summary: string;
  content_role: string;
  control_organization?: string | null;
  profile_id?: string | null;
  profile_version?: number | null;
  can_maintain_profile?: boolean;
  platform_targets: PlatformTarget[];
}

export interface FormalCapabilityItem {
  id: string;
  role: string;
  route: string;
  title: string;
  consumer: string;
  software_implemented: boolean;
  data_state: "satisfied" | "partial" | "missing" | "not_required";
  permission_state: "granted" | "not_granted" | "not_applicable";
  formally_tested: boolean;
  supplement_href: string;
}

export interface FormalCapabilityMatrix {
  registry_version: string;
  runtime_sha: string;
  schema_revision: string;
  generated_at: string;
  truth_sources: string[];
  summary: {
    implemented: number;
    not_built: number;
    data_satisfied: number;
    permission_granted: number;
    formally_tested: number;
  };
  items: FormalCapabilityItem[];
}

export interface UsageGuideTruth {
  identity_model: string[];
  relationship: string;
  send_vs_generate: { send: string; generate: string };
  administrator_steps: string[];
  named_member_examples: string[];
  current_counts: Record<string, number>;
  content_path_state: "satisfied" | "partial" | "missing";
  brand_context_summary: {
    status: "source_bound_confirmed" | "needs_admin_confirmation";
    message: string;
  };
  truth_boundaries: string[];
  product_fact_readiness: Array<{
    sku: string;
    display_name: string;
    current_facts: Array<{ field: string; value: string }>;
    missing_fields: string[];
    can_do: string;
    cannot_promise: string;
  }>;
  service_status_meanings: Array<{
    state: "unknown" | "degraded" | "unavailable";
    meaning: string;
  }>;
  common_errors: Array<{ code: string; meaning: string }>;
  data_missing: Array<{
    id: "P4" | "P5" | "DM01";
    missing: boolean;
    message: string;
    supplement_href: string;
  }>;
}

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
  activation_purpose?: "activate" | "reset";
  activation_error?: string;
  current_target?: Target | null;
  targets?: PlatformTarget[];
  publishing_identities?: PublishingIdentity[];
  current_publishing_identity_id?: string | null;
  formal_runtime?: boolean;
  generator_mode?: "stub" | "deepseek";
  capabilities?: Array<"content" | "display" | "materials">;
  display_stores?: Array<{ id: string; name: string }>;
  capability_matrix?: FormalCapabilityMatrix;
  usage_guide?: UsageGuideTruth;
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
  context_basis?: {
    account: string;
    platform_and_format: string;
    brand_material_categories: string[];
    has_product_facts: boolean;
    selected_material_count: number;
    gaps: string[];
  };
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
  product_media?: Array<{
    binding_id: string;
    product_id: string;
    sku: string;
    product_name: string;
    product_version: number;
  }>;
}

export interface AccountExpressionProfileFields {
  identity_position: string;
  authority_boundary: string;
  audience_relationship: string;
  content_territories: string;
  default_production_conditions: string;
}

export interface AccountExpression {
  account: string;
  content_role: string;
  can_maintain: boolean;
  current: (AccountExpressionProfileFields & {
    version: number;
    profile_id: string;
  }) | null;
  draft?: AccountExpressionProfileFields | null;
}

export type AssistantReply = {
  kind: "chat" | "question" | "handoff";
  message: string;
};

export type ConversationTurn = {
  role: "user" | "assistant";
  content: string;
};

export type GenerationStage =
  | "received"
  | "compiling_context"
  | "generating"
  | "validating"
  | "finalizing";

/**
 * The conversation replies the content stream can carry.
 *
 * `greeting` is small talk. The server produces it in create_from_weak_seed
 * (content_service.py 213/222/229/312) and app.py:2883 relabels a chat reply
 * as one, and respond_to_conversation returns that result unchanged — so it
 * reaches this stream and the UI must accept it. It renders as an assistant
 * message, exactly like `chat`.
 */
export type ConversationKind = "chat" | "question" | "greeting";

export type ContentStreamEvent =
  | { event: GenerationStage }
  | {
      event: "conversation";
      kind: ConversationKind;
      message: string;
      conversation_id?: string | null;
      direct_generation_available?: boolean;
    }
  | {
      event: "target_conflict";
      mentioned_target: Target;
      label: string;
      message?: string;
    }
  | { event: "completed"; result: ContentVersion; conversation_id?: string | null }
  | {
      event: "failed";
      detail?: string;
      message?: string;
      error_code?: string;
      failure_stage?: string;
      retryable?: boolean;
      action?: string;
      trace_id?: string;
      suggestions?: string[];
    };

export type FailedAttempt = {
  kind: "stream" | "revision";
  instruction: string;
  interactionMode?: "conversation" | "generate";
  requestId: string;
};

export type FailureDiagnostic = {
  stage: string;
  retryable: boolean;
  action: string;
  traceId: string;
};
