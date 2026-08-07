import type {
  BootstrapContext,
  GenerationStage,
  PlatformTarget,
  PublishingIdentity,
  Target
} from "../../app/types";

/**
 * Plain-language names for what the workspace shows while it works.
 *
 * Lifted out of CreatorApp so the routing change could land without growing
 * that file, and so the advisor feature owns its own copy rather than the
 * shell it happens to render inside. Behaviour is unchanged; these are the
 * same tables and the same target metadata, moved.
 */

export const STAGE_LABELS: Record<GenerationStage, string> = {
  received: "已接收",
  compiling_context: "已准备本次条件",
  generating: "正在生成",
  validating: "正在检查",
  finalizing: "正在收尾"
};

export const FAILURE_STAGE_LABELS: Record<string, string> = {
  authentication: "登录状态",
  authorization: "资格与作用域检查",
  csrf: "页面提交校验",
  intake: "生成前输入检查",
  context: "资料与事实准备",
  provider: "内容生成服务",
  validation: "成品边界检查",
  persistence: "版本保存",
  rate_limit: "请求排队",
  transport: "网络传输",
  contract: "返回内容检查",
  unknown: "系统处理"
};

export function targetMetadata(target: Target, label?: string): PlatformTarget {
  if (target === "xiaohongshu_graphic") {
    return {
      value: target,
      label: label ?? "小红书图文",
      platform_label: "小红书",
      format_label: "图文"
    };
  }
  if (target === "xiaohongshu_video") {
    return {
      value: target,
      label: label ?? "小红书视频",
      platform_label: "小红书",
      format_label: "视频"
    };
  }
  if (target === "wechat_channels_video") {
    return {
      value: target,
      label: label ?? "微信视频号视频",
      platform_label: "微信视频号",
      format_label: "视频"
    };
  }
  return {
    value: target,
    label: label ?? "抖音视频",
    platform_label: "抖音",
    format_label: "视频"
  };
}

export function normalizedTargets(context: BootstrapContext): PlatformTarget[] {
  return (context.targets ?? []).map(item => ({
    ...targetMetadata(item.value, item.label),
    ...item
  }));
}

export function normalizedIdentities(
  context: BootstrapContext
): PublishingIdentity[] {
  if (context.publishing_identities?.length) return context.publishing_identities;
  const identity = context.identity ?? {};
  return [
    {
      id: identity.publishing_identity_id ?? identity.account_id ?? "current",
      name: identity.account ?? "当前发布账号",
      content_role: identity.content_role ?? "当前表达身份",
      profile_summary: identity.profile_summary ?? "沿用当前账号画像",
      platform_targets: normalizedTargets(context)
    }
  ];
}

export function humanDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? ""
    : new Intl.DateTimeFormat("zh-CN", { month: "numeric", day: "numeric" }).format(
        date
      );
}
