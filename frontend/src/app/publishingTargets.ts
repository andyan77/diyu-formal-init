import type { Target } from "./types";

export type PublishingChannel = "抖音" | "小红书" | "微信视频号";

export const publishingTargetContract: Record<
  Target,
  { label: string; channel: PublishingChannel }
> = {
  douyin_video: { label: "抖音视频", channel: "抖音" },
  xiaohongshu_graphic: { label: "小红书图文", channel: "小红书" },
  xiaohongshu_video: { label: "小红书视频", channel: "小红书" },
  wechat_channels_video: { label: "微信视频号", channel: "微信视频号" }
};

export const publishingPlatformChoices: ReadonlyArray<{
  value: Target;
  label: string;
  targets: readonly Target[];
}> = [
  {
    value: "douyin_video",
    label: "抖音 · 视频",
    targets: ["douyin_video"]
  },
  {
    value: "xiaohongshu_graphic",
    label: "小红书 · 图文 / 视频",
    targets: ["xiaohongshu_graphic", "xiaohongshu_video"]
  },
  {
    value: "wechat_channels_video",
    label: "微信视频号 · 视频",
    targets: ["wechat_channels_video"]
  }
];

export function publishingChannelForTarget(target: Target): PublishingChannel {
  return publishingTargetContract[target].channel;
}
