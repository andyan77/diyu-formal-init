import type { JSX, MutableRefObject, RefObject } from "react";

import { BrandMark } from "../../components/Brand";
import type {
  ContentVersion,
  FailedAttempt,
  FailureDiagnostic,
  PublishingIdentity,
  RecentContent,
  Target
} from "../../app/types";
import type { SeriesSelection } from "../../app/SeriesPanel";
import { FAILURE_STAGE_LABELS, humanDate } from "./labels";

/**
 * The frame around the creation workspace: who you are posting as, what you
 * have made before, and what went wrong.
 *
 * All three were inline in CreatorApp. They came out in EXE-01R because that
 * file gained scope guards and may not grow — and because none of them is
 * about creating content, which is what CreatorApp is for.
 */

export function CreatorTopBar({
  publishingIdentities,
  currentPublishingIdentityId,
  currentPublishingIdentity,
  hasResolvedIdentity,
  currentTarget,
  currentTargetMetadata,
  platformLabels,
  formatTargets,
  availableTargets,
  identityTriggerRef,
  onSwitchScope,
  onOpenAccount
}: {
  publishingIdentities: PublishingIdentity[];
  currentPublishingIdentityId: string;
  currentPublishingIdentity: PublishingIdentity;
  hasResolvedIdentity: boolean;
  currentTarget: Target;
  currentTargetMetadata: { label: string; platform_label: string };
  platformLabels: string[];
  formatTargets: Array<{ value: Target; format_label: string }>;
  availableTargets: Array<{ value: Target; platform_label: string }>;
  identityTriggerRef: RefObject<HTMLButtonElement | null>;
  onSwitchScope: (next: { publishingIdentityId?: string; target?: Target }) => void;
  onOpenAccount: () => void;
}): JSX.Element {
  const switchScope = onSwitchScope;
  const setAccountOpen = (open: boolean): void => {
    if (open) onOpenAccount();
  };
  return (
  <header className="creator-topbar">
    <a className="creator-brand" href="/user">
      <BrandMark compact />
    </a>
    <div className="creator-identity-controls">
      <label>
        <span>发布账号</span>
        <select
          aria-label="发布账号"
          value={currentPublishingIdentityId}
          onChange={event => {
            switchScope({ publishingIdentityId: event.target.value });
          }}
        >
          {!hasResolvedIdentity && <option value="">请选择发布账号</option>}
          {publishingIdentities.map(item => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
      </label>
      <button
        ref={identityTriggerRef}
        className="identity-trigger"
        type="button"
        disabled={!hasResolvedIdentity}
        onClick={() => setAccountOpen(true)}
      >
        <strong>{currentPublishingIdentity.content_role}</strong>
        <span>{currentPublishingIdentity.profile_summary}</span>
      </button>
    </div>
    <div className="creator-target-controls">
      <label>
        <span>平台</span>
        <select
          aria-label="平台"
          value={currentTargetMetadata.platform_label}
          disabled={!hasResolvedIdentity}
          onChange={event => {
            const next = availableTargets.find(
              item => item.platform_label === event.target.value
            );
            if (next) {
              switchScope({ target: next.value });
            }
          }}
        >
          {platformLabels.map(platform => (
            <option key={platform} value={platform}>
              {platform}
            </option>
          ))}
        </select>
      </label>
      <label>
        <span>内容形式</span>
        <select
          aria-label="内容形式"
          value={currentTarget}
          disabled={!hasResolvedIdentity}
          onChange={event => {
            switchScope({ target: event.target.value as Target });
          }}
        >
          {formatTargets.map(item => (
            <option key={item.value} value={item.value}>
              {item.format_label}
            </option>
          ))}
        </select>
      </label>
    </div>
  </header>
  );
}

/** New-creation, resource drawers and the recent list. */
export function CreatorHistoryRail({
  hasResolvedIdentity,
  seriesSelection,
  materialIds,
  recent,
  current,
  toolReturnFocus,
  onStartFresh,
  onOpenTool,
  onOpenRecent
}: {
  hasResolvedIdentity: boolean;
  seriesSelection: SeriesSelection | null;
  materialIds: string[];
  recent: RecentContent[];
  current: ContentVersion | null;
  toolReturnFocus: MutableRefObject<HTMLButtonElement | null>;
  onStartFresh: () => void;
  onOpenTool: (which: "series" | "materials") => void;
  onOpenRecent: (item: RecentContent) => void;
}): JSX.Element {
  const startFresh = onStartFresh;
  const setToolOpen = onOpenTool;
  const openRecent = onOpenRecent;
  return (
  <aside className="creator-history">
    <button className="new-content" type="button" onClick={startFresh}>
      ＋ 新创作
    </button>
    <div className="creator-tools" aria-label="创作资料">
      <button
        type="button"
        disabled={!hasResolvedIdentity}
        onClick={event => {
          toolReturnFocus.current = event.currentTarget;
          setToolOpen("series");
        }}
      >
        <span>连续系列</span>
        <small>{seriesSelection ? "本次已选择" : "创建、继续与编排"}</small>
      </button>
      <button
        type="button"
        disabled={!hasResolvedIdentity}
        onClick={event => {
          toolReturnFocus.current = event.currentTarget;
          setToolOpen("materials");
        }}
      >
        <span>我的素材</span>
        <small>{materialIds.length ? `本次参考 ${materialIds.length} 份` : "管理与选择"}</small>
      </button>
    </div>
    <p>最近</p>
    <nav aria-label="最近成品">
      {recent.length === 0 && <span className="empty-history">还没有成品</span>}
      {recent.map(item => (
        <button
          type="button"
          key={item.task_id}
          className={current?.task_id === item.task_id ? "active" : ""}
          onClick={() => void openRecent(item)}
        >
          <span>{item.title}</span>
          <small>
            V{item.version} · {humanDate(item.updated_at)}
          </small>
        </button>
      ))}
    </nav>
  </aside>
  );
}

/** What broke, whether retrying is safe, and how to retry. */
export function GenerationFailurePanel({
  generationFailed,
  generationFailureMessage,
  failureDiagnostic,
  lastFailedAttempt,
  pending,
  onRetry,
  onDismiss
}: {
  generationFailed: boolean;
  generationFailureMessage: string;
  failureDiagnostic: FailureDiagnostic | null;
  lastFailedAttempt: FailedAttempt | null;
  pending: boolean;
  onRetry: (attempt: FailedAttempt) => void;
  onDismiss: () => void;
}): JSX.Element {
  return (
    <>
  {generationFailed && (
    <div className="generation-failure" role="alert">
      <p>{generationFailureMessage}</p>
      {failureDiagnostic && (
        <dl className="failure-diagnostic">
          <div>
            <dt>发生阶段</dt>
            <dd>
              {FAILURE_STAGE_LABELS[failureDiagnostic.stage] ??
                "系统处理"}
            </dd>
          </div>
          <div>
            <dt>是否值得重试</dt>
            <dd>{failureDiagnostic.retryable ? "可以" : "先按提示处理"}</dd>
          </div>
          {failureDiagnostic.traceId && (
            <div>
              <dt>定位编号</dt>
              <dd><code>{failureDiagnostic.traceId}</code></dd>
            </div>
          )}
        </dl>
      )}
      {failureDiagnostic?.action && (
        <p className="failure-action">下一步：{failureDiagnostic.action}</p>
      )}
      <div>
        <button
          type="button"
          onClick={onDismiss}
        >
          继续补充
        </button>
        {failureDiagnostic?.retryable !== false && (
          <button
            type="button"
            className="primary"
            disabled={!lastFailedAttempt || pending}
            onClick={() => {
              if (lastFailedAttempt) onRetry(lastFailedAttempt);
            }}
          >
            再试一次
          </button>
        )}
      </div>
    </div>
  )}
    </>
  );
}

