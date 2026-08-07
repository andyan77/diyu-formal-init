import type {
  JSX,
  KeyboardEvent as ReactKeyboardEvent,
  MutableRefObject,
  ReactNode,
  RefObject
} from "react";

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
 * have made before, which face of the work you are looking at on a phone, and
 * what went wrong.
 *
 * All of it was inline in CreatorApp. It came out in EXE-01R because that file
 * gained scope guards and may not grow — and because none of it is about
 * creating content, which is what CreatorApp is for.
 */

type ScopeChange = (next: { publishingIdentityId?: string; target?: Target }) => void;

function IdentityControls({
  publishingIdentities,
  currentPublishingIdentityId,
  currentPublishingIdentity,
  hasResolvedIdentity,
  identityTriggerRef,
  onSwitchScope,
  onOpenAccount
}: {
  publishingIdentities: PublishingIdentity[];
  currentPublishingIdentityId: string;
  currentPublishingIdentity: PublishingIdentity;
  hasResolvedIdentity: boolean;
  identityTriggerRef: RefObject<HTMLButtonElement | null>;
  onSwitchScope: ScopeChange;
  onOpenAccount: () => void;
}): JSX.Element {
  return (
    <div className="creator-identity-controls">
      <label>
        <span>发布账号</span>
        <select
          aria-label="发布账号"
          value={currentPublishingIdentityId}
          onChange={event =>
            onSwitchScope({ publishingIdentityId: event.target.value })
          }
        >
          {/* Offered only while nothing is chosen: the workspace must never
              silently adopt an account on the person's behalf. */}
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
        onClick={onOpenAccount}
      >
        <strong>{currentPublishingIdentity.content_role}</strong>
        <span>{currentPublishingIdentity.profile_summary}</span>
      </button>
    </div>
  );
}

function TargetControls({
  hasResolvedIdentity,
  currentTarget,
  currentTargetMetadata,
  platformLabels,
  formatTargets,
  availableTargets,
  onSwitchScope
}: {
  hasResolvedIdentity: boolean;
  currentTarget: Target;
  currentTargetMetadata: { label: string; platform_label: string };
  platformLabels: string[];
  formatTargets: Array<{ value: Target; format_label: string }>;
  availableTargets: Array<{ value: Target; platform_label: string }>;
  onSwitchScope: ScopeChange;
}): JSX.Element {
  return (
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
            if (next) onSwitchScope({ target: next.value });
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
          onChange={event =>
            onSwitchScope({ target: event.target.value as Target })
          }
        >
          {formatTargets.map(item => (
            <option key={item.value} value={item.value}>
              {item.format_label}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}

/** Who you are posting as, and where it is going. */
export function CreatorTopBar(
  props: Parameters<typeof IdentityControls>[0] &
    Parameters<typeof TargetControls>[0]
): JSX.Element {
  return (
    <header className="creator-topbar">
      <a className="creator-brand" href="/user">
        <BrandMark compact />
      </a>
      <IdentityControls {...props} />
      <TargetControls {...props} />
    </header>
  );
}

function CreatorTools({
  hasResolvedIdentity,
  seriesSelection,
  materialIds,
  toolReturnFocus,
  onOpenTool
}: {
  hasResolvedIdentity: boolean;
  seriesSelection: SeriesSelection | null;
  materialIds: string[];
  toolReturnFocus: MutableRefObject<HTMLButtonElement | null>;
  onOpenTool: (which: "series" | "materials") => void;
}): JSX.Element {
  // Remember the button that opened the drawer, so closing it returns the
  // keyboard where it came from rather than to the top of the page.
  const open = (which: "series" | "materials") =>
    (event: { currentTarget: HTMLButtonElement }): void => {
      toolReturnFocus.current = event.currentTarget;
      onOpenTool(which);
    };
  return (
    <div className="creator-tools" aria-label="创作资料">
      <button type="button" disabled={!hasResolvedIdentity} onClick={open("series")}>
        <span>连续系列</span>
        <small>{seriesSelection ? "本次已选择" : "创建、继续与编排"}</small>
      </button>
      <button type="button" disabled={!hasResolvedIdentity} onClick={open("materials")}>
        <span>我的素材</span>
        <small>
          {materialIds.length ? `本次参考 ${materialIds.length} 份` : "管理与选择"}
        </small>
      </button>
    </div>
  );
}

function RecentList({
  recent,
  current,
  onOpenRecent
}: {
  recent: RecentContent[];
  current: ContentVersion | null;
  onOpenRecent: (item: RecentContent) => void;
}): JSX.Element {
  return (
    <nav aria-label="最近成品">
      {recent.length === 0 && <span className="empty-history">还没有成品</span>}
      {recent.map(item => (
        <button
          type="button"
          key={item.task_id}
          className={current?.task_id === item.task_id ? "active" : ""}
          onClick={() => void onOpenRecent(item)}
        >
          <span>{item.title}</span>
          <small>
            V{item.version} · {humanDate(item.updated_at)}
          </small>
        </button>
      ))}
    </nav>
  );
}

/** New-creation, resource drawers and the recent list. */
export function CreatorHistoryRail({
  onStartFresh,
  ...rest
}: Parameters<typeof CreatorTools>[0] &
  Parameters<typeof RecentList>[0] & { onStartFresh: () => void }): JSX.Element {
  return (
    <aside className="creator-history">
      <button className="new-content" type="button" onClick={onStartFresh}>
        ＋ 新创作
      </button>
      <CreatorTools {...rest} />
      <p>最近</p>
      <RecentList {...rest} />
    </aside>
  );
}

/**
 * The modal shell the resource panels open into.
 *
 * Only the frame lives here — which panel goes inside stays with the workspace,
 * so this file does not have to know how series and materials are chosen.
 */
export function CreatorToolDrawer({
  which,
  drawerRef,
  closeRef,
  onClose,
  onKeyDown,
  children
}: {
  which: "series" | "materials";
  drawerRef: RefObject<HTMLElement | null>;
  closeRef: RefObject<HTMLButtonElement | null>;
  onClose: () => void;
  onKeyDown: (event: ReactKeyboardEvent<HTMLElement>) => void;
  children: ReactNode;
}): JSX.Element {
  return (
    <div className="drawer-layer" role="presentation" onMouseDown={onClose}>
      <aside
        ref={drawerRef}
        className="creator-tool-drawer"
        role="dialog"
        aria-modal="true"
        aria-label={which === "series" ? "连续系列" : "我的素材"}
        onMouseDown={event => event.stopPropagation()}
        onKeyDown={onKeyDown}
      >
        <button
          ref={closeRef}
          className="icon-button tool-drawer-close"
          type="button"
          aria-label="关闭"
          onClick={onClose}
        >
          ×
        </button>
        {children}
      </aside>
    </div>
  );
}

function FailureDiagnosticList({
  diagnostic
}: {
  diagnostic: FailureDiagnostic;
}): JSX.Element {
  return (
    <dl className="failure-diagnostic">
      <div>
        <dt>发生阶段</dt>
        <dd>{FAILURE_STAGE_LABELS[diagnostic.stage] ?? "系统处理"}</dd>
      </div>
      <div>
        <dt>是否值得重试</dt>
        <dd>{diagnostic.retryable ? "可以" : "先按提示处理"}</dd>
      </div>
      {diagnostic.traceId && (
        <div>
          <dt>定位编号</dt>
          <dd>
            <code>{diagnostic.traceId}</code>
          </dd>
        </div>
      )}
    </dl>
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
}): JSX.Element | null {
  if (!generationFailed) return null;
  return (
    <div className="generation-failure" role="alert">
      <p>{generationFailureMessage}</p>
      {failureDiagnostic && <FailureDiagnosticList diagnostic={failureDiagnostic} />}
      {failureDiagnostic?.action && (
        <p className="failure-action">下一步：{failureDiagnostic.action}</p>
      )}
      <div>
        <button type="button" onClick={onDismiss}>
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
  );
}
