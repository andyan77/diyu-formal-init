import { useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent, JSX, KeyboardEvent as ReactKeyboardEvent } from "react";
import { BrandMark } from "../components/Brand";
import {
  FAILURE_STAGE_LABELS,
  STAGE_LABELS,
  humanDate,
  normalizedIdentities,
  targetMetadata
} from "../features/advisor/labels";
import { useAdvisorScope } from "../features/advisor/useAdvisorScope";
import {
  ContentStreamContractError,
  guardContentStream,
  isStageEvent
} from "../shared/contracts/contentStream";
import {
  ApiError,
  api,
  scopedContentPath,
  streamApi,
  transferredContent
} from "../services/api";
import { MaterialsPanel } from "./MaterialsPanel";
import { SeriesPanel } from "./SeriesPanel";
import type { SeriesSelection } from "./SeriesPanel";
import type {
  AccountExpression,
  AccountExpressionProfileFields,
  AssistantReply,
  BootstrapContext,
  CatalogAxis,
  ContentStreamEvent,
  ContentVersion,
  ConversationTurn,
  CreationPreference,
  ExpressionCatalog,
  GenerationStage,
  Material,
  PlatformTarget,
  PublishingIdentity,
  RecentContent,
  Target
} from "./types";

type ConversationMessage = {
  id: number;
  speaker: "user" | "assistant";
  text: string;
};

type FailedAttempt = {
  kind: "stream" | "revision";
  instruction: string;
  interactionMode?: "conversation" | "generate";
  requestId: string;
};

type FailureDiagnostic = {
  stage: string;
  retryable: boolean;
  action: string;
  traceId: string;
};

const PRIMARY_AXES = new Set(["topic", "style", "form"]);
function targetOf(version: ContentVersion, fallback: Target): Target {
  return version.target_key ?? version.target ?? fallback;
}

function ArtifactBody({ value }: { value: string }): JSX.Element {
  const blocks = value.split(/\n{2,}/).map(item => item.trim()).filter(Boolean);
  return (
    <div className="artifact-body">
      {blocks.map((block, index) => {
        const split = block.match(/^([^：:\n]{2,16})[：:]\s*([\s\S]+)$/);
        return split ? (
          <section key={`${split[1]}-${index}`}>
            <h3>{split[1]}</h3>
            <p>{split[2]}</p>
          </section>
        ) : (
          <p key={`${block.slice(0, 12)}-${index}`}>{block}</p>
        );
      })}
    </div>
  );
}

function DirectionAxis({
  axis,
  selection,
  saved,
  cleared,
  onChoose,
  onClear,
  customValue,
  onCustom
}: {
  axis: CatalogAxis;
  selection?: string;
  saved?: string;
  cleared: boolean;
  onChoose: (value: string) => void;
  onClear: () => void;
  customValue?: string;
  onCustom: (value: string) => void;
}): JSX.Element {
  const [expanded, setExpanded] = useState(false);
  const [search, setSearch] = useState("");
  const savedLabel = axis.options.find(option => option.stable_id === saved)?.label;
  const normalizedSearch = search.trim().toLocaleLowerCase();
  const matching = normalizedSearch
    ? axis.options.filter(option =>
        option.label.toLocaleLowerCase().includes(normalizedSearch)
      )
    : axis.options;
  const visible = expanded ? matching : matching.slice(0, 4);
  const canKeepCustom =
    Boolean(search.trim()) &&
    !axis.options.some(option => option.label === search.trim());
  return (
    <fieldset className="direction-axis">
      <legend>
        <span>{axis.label}</span>
        <small>{axis.question}</small>
      </legend>
      <div className="direction-options">
        {visible.map(option => {
          const selected = selection === option.stable_id;
          const inherited = !selection && !cleared && saved === option.stable_id;
          return (
            <button
              key={option.stable_id}
              type="button"
              aria-pressed={selected}
              className={selected ? "selected" : inherited ? "inherited" : ""}
              onClick={() => onChoose(option.stable_id)}
            >
              {option.label}
              {inherited && <small>默认</small>}
            </button>
          );
        })}
        {(selection || saved) && (
          <button
            type="button"
            className={cleared ? "selected quiet-choice" : "quiet-choice"}
            aria-pressed={cleared}
            onClick={onClear}
          >
            本次不使用{savedLabel ? `「${savedLabel}」` : ""}
          </button>
        )}
        {(axis.options.length > 4 || expanded) && (
          <button
            type="button"
            className="quiet-choice"
            aria-expanded={expanded}
            onClick={() => setExpanded(value => !value)}
          >
            {expanded ? "收起" : "更多 / 搜索"}
          </button>
        )}
      </div>
      {expanded && (
        <div className="axis-search">
          <input
            type="search"
            value={search}
            onChange={event => setSearch(event.target.value)}
            placeholder={`搜索或输入更多${axis.label}`}
          />
          {canKeepCustom && (
            <button type="button" onClick={() => onCustom(search.trim())}>
              保留“{search.trim()}”作为本次要求
            </button>
          )}
          {customValue && <small>本次保留：{customValue}</small>}
        </div>
      )}
    </fieldset>
  );
}

function DirectionPanel({
  catalog,
  selections,
  clearedAxes,
  customText,
  customAxes,
  materials,
  materialIds,
  onSelections,
  onClearedAxes,
  onCustomText,
  onCustomAxes,
  onMaterialIds,
  onSaveDefaults,
  saving
}: {
  catalog: ExpressionCatalog | null;
  selections: Record<string, string>;
  clearedAxes: string[];
  customText: string;
  customAxes: Record<string, string>;
  materials: Material[];
  materialIds: string[];
  onSelections: (value: Record<string, string>) => void;
  onClearedAxes: (value: string[]) => void;
  onCustomText: (value: string) => void;
  onCustomAxes: (value: Record<string, string>) => void;
  onMaterialIds: (value: string[]) => void;
  onSaveDefaults: () => void;
  saving: boolean;
}): JSX.Element {
  const [more, setMore] = useState(false);
  if (!catalog) {
    return <p className="subtle-status">正在准备创作方向……</p>;
  }
  const primary = catalog.axes.filter(axis => PRIMARY_AXES.has(axis.key));
  const secondary = catalog.axes.filter(axis => !PRIMARY_AXES.has(axis.key));
  const renderAxis = (axis: CatalogAxis): JSX.Element => (
    <DirectionAxis
      key={axis.key}
      axis={axis}
      selection={selections[axis.key]}
      saved={catalog.saved_defaults[axis.key]}
      cleared={clearedAxes.includes(axis.key)}
      onChoose={value => {
        onSelections({ ...selections, [axis.key]: value });
        onClearedAxes(clearedAxes.filter(item => item !== axis.key));
        if (customAxes[axis.key]) {
          const next = { ...customAxes };
          delete next[axis.key];
          onCustomAxes(next);
        }
      }}
      onClear={() => {
        const next = { ...selections };
        delete next[axis.key];
        onSelections(next);
        onClearedAxes(
          clearedAxes.includes(axis.key)
            ? clearedAxes.filter(item => item !== axis.key)
            : [...clearedAxes, axis.key]
        );
      }}
      customValue={customAxes[axis.key]}
      onCustom={value => {
        const nextSelections = { ...selections };
        delete nextSelections[axis.key];
        onSelections(nextSelections);
        onClearedAxes(clearedAxes.filter(item => item !== axis.key));
        onCustomAxes({ ...customAxes, [axis.key]: value });
      }}
    />
  );
  return (
    <div className="direction-content">
      {primary.map(renderAxis)}
      <button className="text-action" type="button" onClick={() => setMore(value => !value)}>
        {more ? "收起更多" : "更多：讲法与系列互动"}
      </button>
      {more && <div className="more-directions">{secondary.map(renderAxis)}</div>}
      <label className="custom-direction">
        还有其他要求？直接用自己的话说。
        <input
          value={customText}
          onChange={event => onCustomText(event.target.value)}
          maxLength={500}
          placeholder="例如：像给熟悉的朋友解释，不用口号。"
        />
        <small>人物关系和你的原话会随本次任务保留，不会被悄悄换成相近选项。</small>
      </label>
      {materials.length > 0 && (
        <fieldset className="material-options">
          <legend>本次素材（可选）</legend>
          {materials.map(material => {
            const readable =
              material.media_type === "text" || Boolean(material.reference_note?.trim());
            const selectedPosition = materialIds.indexOf(material.id);
            const visualRole =
              selectedPosition >= 0 && Boolean(material.product_media?.length)
                ? selectedPosition === 0
                  ? "主视觉"
                  : selectedPosition === 1
                    ? "辅助视觉"
                    : "普通参考"
                : "";
            return (
              <label key={material.id} className={!readable ? "unavailable" : ""}>
                <input
                  type="checkbox"
                  disabled={!readable}
                  checked={materialIds.includes(material.id)}
                  onChange={event =>
                    onMaterialIds(
                      event.target.checked
                        ? [...materialIds, material.id]
                        : materialIds.filter(item => item !== material.id)
                    )
                  }
                />
                <span>
                  {material.title}
                  <small>
                    {material.scope === "personal" ? "我的素材" : "组织素材"}
                    {!readable ? " · 还缺一句可读说明" : ""}
                    {visualRole ? ` · ${visualRole}` : ""}
                  </small>
                </span>
              </label>
            );
          })}
        </fieldset>
      )}
      <div className="direction-footer">
        <span>所有选择只影响这一次。</span>
        <button
          className="text-action"
          type="button"
          disabled={saving}
          onClick={onSaveDefaults}
        >
          {saving ? "正在保存……" : "以后优先这样帮我"}
        </button>
      </div>
    </div>
  );
}

function editableAccountProfile(
  value:
    | AccountExpression["current"]
    | AccountExpression["draft"]
    | null
    | undefined
): AccountExpressionProfileFields | null {
  return value
    ? {
        identity_position: value.identity_position,
        authority_boundary: value.authority_boundary,
        audience_relationship: value.audience_relationship,
        content_territories: value.content_territories,
        default_production_conditions: value.default_production_conditions
      }
    : null;
}

function AccountDrawer({
  context,
  publishingIdentity,
  preferencePath,
  preference,
  profile,
  profilePath,
  onClose,
  onPreference,
  onProfile
}: {
  context: BootstrapContext;
  publishingIdentity: PublishingIdentity;
  preferencePath: string;
  preference: CreationPreference | null;
  profile: AccountExpression | null;
  profilePath: string;
  onClose: () => void;
  onPreference: (value: CreationPreference) => void;
  onProfile: (value: AccountExpression) => void;
}): JSX.Element {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [editingProfile, setEditingProfile] = useState(false);
  const [profileDraft, setProfileDraft] =
    useState<AccountExpressionProfileFields | null>(
      editableAccountProfile(profile?.current ?? profile?.draft)
    );
  const panelRef = useRef<HTMLElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeRef.current?.focus();
  }, []);
  useEffect(() => {
    setProfileDraft(
      editableAccountProfile(profile?.current ?? profile?.draft)
    );
    setEditingProfile(false);
  }, [profile]);

  const handleKeyDown = (event: ReactKeyboardEvent<HTMLElement>): void => {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
      return;
    }
    if (event.key !== "Tab") return;
    const focusable = Array.from(
      panelRef.current?.querySelectorAll<HTMLElement>(
        "a[href], button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled)"
      ) ?? []
    );
    const first = focusable[0];
    const last = focusable.at(-1);
    if (!first || !last) return;
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  const toggleBodyDirections = async (): Promise<void> => {
    if (!preference || saving) return;
    setSaving(true);
    setError("");
    try {
      const next = await api<CreationPreference>(preferencePath, {
        method: "PUT",
        body: JSON.stringify({
          enabled: preference.enabled,
          direction_defaults: preference.direction_defaults,
          clear_direction_defaults: false,
          collaboration_note: preference.collaboration_note,
          body_related_opt_in: !preference.body_related_opt_in
        })
      });
      onPreference(next);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "没有保存成功。");
    } finally {
      setSaving(false);
    }
  };
  const saveProfile = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    if (!profile?.can_maintain || !profileDraft || saving) return;
    setSaving(true);
    setError("");
    try {
      const saved = await api<NonNullable<AccountExpression["current"]>>(
        profilePath,
        {
        method: "POST",
        body: JSON.stringify(profileDraft)
        }
      );
      onProfile({ ...profile, current: saved, draft: null });
      setEditingProfile(false);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "账号画像没有保存成功。"
      );
    } finally {
      setSaving(false);
    }
  };
  const identity = context.identity ?? {};
  return (
    <div className="drawer-layer" role="presentation" onMouseDown={onClose}>
      <aside
        ref={panelRef}
        className="account-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="account-drawer-title"
        onMouseDown={event => event.stopPropagation()}
        onKeyDown={handleKeyDown}
      >
        <header>
          <div>
            <p className="eyebrow">当前发布身份</p>
            <h2 id="account-drawer-title">{publishingIdentity.name}</h2>
          </div>
          <button
            ref={closeRef}
            className="icon-button"
            type="button"
            aria-label="关闭"
            onClick={onClose}
          >
            ×
          </button>
        </header>
        <dl className="identity-details">
          <div>
            <dt>表达身份</dt>
            <dd>{publishingIdentity.content_role || identity.content_role || "—"}</dd>
          </div>
          <div>
            <dt>负责团队</dt>
            <dd>{publishingIdentity.control_organization ?? "—"}</dd>
          </div>
          <div>
            <dt>账号画像</dt>
            <dd>
              {publishingIdentity.profile_version
                ? `V${publishingIdentity.profile_version}`
                : "尚未确认"}
            </dd>
          </div>
        </dl>
        <p className="profile-one-line">{publishingIdentity.profile_summary}</p>
        {profile?.current && !editingProfile && (
          <section className="profile-summary">
            <h3>账号定位 · V{profile.current.version}</h3>
            <p>{profile.current.identity_position}</p>
            <p>{profile.current.authority_boundary}</p>
            <p>{profile.current.audience_relationship}</p>
            <p>{profile.current.content_territories}</p>
            <p>{profile.current.default_production_conditions}</p>
            {profile.can_maintain && (
              <button
                type="button"
                className="text-action"
                onClick={() => setEditingProfile(true)}
              >
                维护账号画像
              </button>
            )}
          </section>
        )}
        {profile?.can_maintain && editingProfile && profileDraft && (
          <form className="account-profile-editor" onSubmit={event => void saveProfile(event)}>
            <h3>
              基于当前 V{profile.current?.version ?? 0} 保存新版本
            </h3>
            {(
              [
                ["identity_position", "表达身份"],
                ["authority_boundary", "权威边界"],
                ["audience_relationship", "受众关系"],
                ["content_territories", "内容领地"],
                ["default_production_conditions", "长期制作条件"]
              ] as const
            ).map(([key, label]) => (
              <label key={key}>
                {label}
                <textarea
                  required
                  value={profileDraft[key]}
                  onChange={event =>
                    setProfileDraft(value =>
                      value
                        ? { ...value, [key]: event.target.value }
                        : value
                    )
                  }
                />
              </label>
            ))}
            <div className="drawer-actions">
              <button
                type="button"
                onClick={() => {
                  setProfileDraft(
                    editableAccountProfile(
                      profile.current ?? profile.draft
                    )
                  );
                  setEditingProfile(false);
                  setError("");
                }}
              >
                取消
              </button>
              <button className="primary" type="submit" disabled={saving}>
                {saving
                  ? "正在保存……"
                  : `保存为 V${(profile.current?.version ?? 0) + 1}`}
              </button>
            </div>
          </form>
        )}
        {profile && !profile.can_maintain && (
          <p className="profile-read-only">
            你可以查看完整账号画像；维护资格由账号负责团队单独分配。
          </p>
        )}
        {error && <p className="inline-error">{error}</p>}
        {preference && (
          <section className="personal-controls">
            <h3>我的创作偏好</h3>
            <label className="switch-line">
              <span>
                主动显示体型相关方向
                <small>只有你打开后才出现，系统不会自行推断。</small>
              </span>
              <input
                type="checkbox"
                checked={preference.body_related_opt_in}
                disabled={saving}
                onChange={() => void toggleBodyDirections()}
              />
            </label>
          </section>
        )}
      </aside>
    </div>
  );
}

function ArtifactPane({
  viewed,
  current,
  versions,
  onView,
  onCurrent,
  onNotice
}: {
  viewed: ContentVersion | null;
  current: ContentVersion | null;
  versions: ContentVersion[];
  onView: (value: ContentVersion) => void;
  onCurrent: () => void;
  onNotice: (value: string) => void;
}): JSX.Element {
  if (!viewed || !current) {
    return <></>;
  }
  const isCurrent = viewed.version_id === current.version_id;
  const transfer = transferredContent(viewed);
  const copy = async (): Promise<void> => {
    try {
      await navigator.clipboard.writeText(transfer);
      onNotice(`已复制 V${viewed.version} 全文。`);
    } catch {
      onNotice("没有复制成功，请允许浏览器访问剪贴板后再试。");
    }
  };
  const historicalVersions = versions.filter(
    version => version.version_id !== current.version_id
  );
  const exportText = (): void => {
    const blob = new Blob([transfer], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `笛语内容-V${viewed.version}.txt`;
    link.click();
    URL.revokeObjectURL(url);
    onNotice(`已导出 V${viewed.version}。`);
  };
  return (
    <aside className="creator-artifact" aria-label="完整成品">
      <header className="artifact-title">
        <div>
          <p className="eyebrow">{isCurrent ? "当前版本" : "历史版本"} · V{viewed.version}</p>
          <h2>{viewed.outline}</h2>
        </div>
        <div className="artifact-actions">
          <button type="button" onClick={() => void copy()}>
            复制
          </button>
          <button type="button" onClick={exportText}>
            导出
          </button>
        </div>
      </header>
      {!isCurrent && (
        <div className="history-reading">
          <span>你正在回读 V{viewed.version}，当前版仍是 V{current.version}。</span>
          <button type="button" onClick={onCurrent}>
            回到当前版
          </button>
        </div>
      )}
      {viewed.translation_notice && (
        <p className="translation-notice">{viewed.translation_notice}</p>
      )}
      {viewed.context_basis && (
        <details className="artifact-context-basis">
          <summary>本次依据</summary>
          <dl>
            <div><dt>当前账号</dt><dd>{viewed.context_basis.account}</dd></div>
            <div><dt>平台和形式</dt><dd>{viewed.context_basis.platform_and_format}</dd></div>
            <div>
              <dt>品牌资料</dt>
              <dd>
                {viewed.context_basis.brand_material_categories.length
                  ? viewed.context_basis.brand_material_categories.join("、")
                  : "本次没有使用品牌资料"}
              </dd>
            </div>
            <div><dt>商品资料</dt><dd>{viewed.context_basis.has_product_facts ? "已使用" : "本次未使用"}</dd></div>
            <div><dt>制作素材</dt><dd>{viewed.context_basis.selected_material_count ? `已选择 ${viewed.context_basis.selected_material_count} 份` : "本次未选择"}</dd></div>
            {viewed.context_basis.gaps.length > 0 && (
              <div><dt>当前缺口</dt><dd>{viewed.context_basis.gaps.join("；")}</dd></div>
            )}
          </dl>
        </details>
      )}
      <ArtifactBody value={viewed.body} />
      {viewed.ai_generated && viewed.aigc_label && viewed.aigc_release_reminder && (
        <footer className="aigc-note">
          <strong>{viewed.aigc_label}</strong>
          <span>{viewed.aigc_release_reminder}</span>
        </footer>
      )}
      {historicalVersions.length > 0 && (
        <details className="version-history">
          <summary>历史版本（{historicalVersions.length}）</summary>
          <div>
            {historicalVersions
              .slice()
              .sort((left, right) => right.version - left.version)
              .map(version => (
                <button
                  key={version.version_id}
                  type="button"
                  className={viewed.version_id === version.version_id ? "active" : ""}
                  onClick={() => onView(version)}
                >
                  <span>V{version.version}</span>
                  <small>
                    {version.version_id === current.version_id ? "当前版" : "完整保留"}
                  </small>
                </button>
              ))}
          </div>
        </details>
      )}
    </aside>
  );
}

export default function CreatorApp({
  context,
  taskId
}: {
  context: BootstrapContext;
  /** Present on /content/tasks/:taskId. The package page itself is EXE-07. */
  taskId?: string;
}): JSX.Element {
  const publishingIdentities = normalizedIdentities(context);
  const bootstrapIdentityId =
    context.current_publishing_identity_id ??
    (publishingIdentities.length === 1 ? publishingIdentities[0]?.id : null) ??
    "";
  const operatorIdentity = context.identity ?? {};
  // Account, platform and format come from the URL so switching is in-app and
  // the back button works; the server bootstrap is only the starting point.
  const advisorScope = useAdvisorScope({
    operator:
      operatorIdentity.operator_id ?? operatorIdentity.operator ?? "unknown-person",
    tenant: operatorIdentity.brand ?? "unknown-brand",
    fallbackPublishingIdentityId: bootstrapIdentityId,
    fallbackTarget: context.current_target ?? ""
  });
  const currentPublishingIdentityId = advisorScope.publishingIdentityId;
  const resolvedPublishingIdentity = publishingIdentities.find(
    item => item.id === currentPublishingIdentityId
  );
  const currentPublishingIdentity = resolvedPublishingIdentity ?? {
    id: "",
    name: "请选择发布账号",
    profile_summary: "选择后会显示这个账号的表达位置。",
    content_role: "尚未选择",
    platform_targets: [] as PlatformTarget[]
  };
  const hasResolvedIdentity = Boolean(resolvedPublishingIdentity);
  const availableTargets =
    currentPublishingIdentity.platform_targets.map(item => ({
      ...targetMetadata(item.value, item.label),
      ...item
    }));
  const currentTarget = availableTargets.some(
    item => item.value === advisorScope.target
  )
    ? (advisorScope.target as Target)
    : availableTargets[0]?.value ?? "douyin_video";
  const currentTargetMetadata =
    availableTargets.find(item => item.value === currentTarget) ??
    targetMetadata(currentTarget);
  const platformLabels = Array.from(
    new Set(availableTargets.map(item => item.platform_label))
  );
  const formatTargets = availableTargets.filter(
    item => item.platform_label === currentTargetMetadata.platform_label
  );
  const [catalog, setCatalog] = useState<ExpressionCatalog | null>(null);
  const [preference, setPreference] = useState<CreationPreference | null>(null);
  const [profile, setProfile] = useState<AccountExpression | null>(null);
  const [materials, setMaterials] = useState<Material[]>([]);
  const [recent, setRecent] = useState<RecentContent[]>([]);
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const { draft: seed, setDraft: setSeedValue } = advisorScope;
  const setSeed = (next: string | ((value: string) => string)): void => {
    setSeedValue(typeof next === "function" ? next(seed) : next);
  };
  const [selections, setSelections] = useState<Record<string, string>>({});
  const [clearedAxes, setClearedAxes] = useState<string[]>([]);
  const [customText, setCustomText] = useState("");
  const [customAxes, setCustomAxes] = useState<Record<string, string>>({});
  const [materialIds, setMaterialIds] = useState<string[]>([]);
  const [directionsOpen, setDirectionsOpen] = useState(false);
  const [compactDirections, setCompactDirections] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const [toolOpen, setToolOpen] = useState<"series" | "materials" | null>(null);
  const [seriesSelection, setSeriesSelection] = useState<SeriesSelection | null>(null);
  const [mobileView, setMobileView] = useState<"conversation" | "artifact">("conversation");
  const [current, setCurrent] = useState<ContentVersion | null>(null);
  const [viewed, setViewed] = useState<ContentVersion | null>(null);
  const [versions, setVersions] = useState<ContentVersion[]>([]);
  const [pending, setPending] = useState(false);
  const [stages, setStages] = useState<GenerationStage[]>([]);
  const [targetConflict, setTargetConflict] = useState<{
    target: Target;
    label: string;
    instruction: string;
    interactionMode: "conversation" | "generate";
    requestId: string;
  } | null>(null);
  const [directGenerationOffer, setDirectGenerationOffer] = useState<string | null>(
    null
  );
  const [generationFailed, setGenerationFailed] = useState(false);
  const [generationFailureMessage, setGenerationFailureMessage] = useState("");
  const [failureDiagnostic, setFailureDiagnostic] =
    useState<FailureDiagnostic | null>(null);
  const [lastFailedAttempt, setLastFailedAttempt] =
    useState<FailedAttempt | null>(null);
  const [savingDefaults, setSavingDefaults] = useState(false);
  const [notice, setNotice] = useState("");
  const [loadError, setLoadError] = useState("");
  const identityTriggerRef = useRef<HTMLButtonElement>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const toolDrawerRef = useRef<HTMLElement>(null);
  const toolCloseRef = useRef<HTMLButtonElement>(null);
  const toolReturnFocus = useRef<HTMLButtonElement | null>(null);
  const toolRestoreFocusPending = useRef(false);
  const directionToggleRef = useRef<HTMLButtonElement>(null);
  const directionPanelRef = useRef<HTMLElement>(null);
  const directionCloseRef = useRef<HTMLButtonElement>(null);

  const targetLabel = currentTargetMetadata.label;
  const bodyOptIn = preference?.body_related_opt_in ?? false;
  const productMediaIntent =
    materialIds.length === 2 &&
    materialIds.every(id =>
      materials.some(
        material =>
          material.id === id &&
          material.scope === "organization" &&
          Boolean(material.product_media?.length)
      )
    );
  const scope = (path: string): string =>
    scopedContentPath(path, currentPublishingIdentityId, currentTarget);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return undefined;
    const media = window.matchMedia("(max-width: 640px)");
    const update = (): void => setCompactDirections(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    if (directionsOpen && compactDirections) {
      directionCloseRef.current?.focus();
    }
  }, [compactDirections, directionsOpen]);

  const closeDirections = (): void => {
    if (compactDirections) {
      directionToggleRef.current?.focus();
    }
    setDirectionsOpen(false);
  };

  const handleDirectionKeyDown = (
    event: ReactKeyboardEvent<HTMLElement>
  ): void => {
    if (!compactDirections) return;
    if (event.key === "Escape") {
      event.preventDefault();
      closeDirections();
      return;
    }
    if (event.key !== "Tab") return;
    const focusable = Array.from(
      directionPanelRef.current?.querySelectorAll<HTMLElement>(
        "button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href]"
      ) ?? []
    );
    const first = focusable[0];
    const last = focusable.at(-1);
    if (!first || !last) return;
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  const loadWorkspace = async (): Promise<void> => {
    if (!hasResolvedIdentity) return;
    // Everything below belongs to the scope in force when the load started. If
    // the operator switches account while these are in flight, the replies are
    // for an account that is no longer on screen and must be dropped.
    const loadedFor = advisorScope.scopeKey;
    const stale = (): boolean => !advisorScope.isCurrent(loadedFor);
    setLoadError("");
    try {
      const [catalogValue, preferenceValue, materialValue, profileValue] =
        await Promise.all([
          api<ExpressionCatalog>(scope("/api/v1/content/expression-catalog")),
          api<CreationPreference>(scope("/api/v1/user/creation-preferences")),
          api<Material[]>(scope("/api/v1/materials")),
          api<AccountExpression>(
            scope("/api/v1/content/account-expression-profile")
          )
        ]);
      if (stale()) return;
      setCatalog(catalogValue);
      setPreference(preferenceValue);
      setMaterials(materialValue);
      setProfile(profileValue);
      const currentRecent = await api<RecentContent[]>(
        scope("/api/v1/content/tasks")
      );
      if (stale()) return;
      setRecent(
        currentRecent
          .slice()
          .sort((left, right) => right.updated_at.localeCompare(left.updated_at))
      );
    } catch (reason) {
      if (stale()) return;
      setLoadError(reason instanceof Error ? reason.message : "当前工作空间没有准备好。");
    }
  };

  useEffect(() => {
    // Switching account or platform no longer reloads the page, so the
    // workspace has to refetch for the new scope. `isCurrent` drops a reply
    // that arrives after the operator has already moved on, which is what
    // stops one account's materials from appearing under another's name.
    void loadWorkspace();
    // loadWorkspace closes over the scope it was created with, and guards its
    // own writes; the scope key is the honest dependency.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [advisorScope.scopeKey]);

  useEffect(
    () => () => {
      abortRef.current?.abort();
    },
    []
  );

  useEffect(() => {
    if (toolOpen) {
      toolCloseRef.current?.focus();
      return;
    }
    if (toolRestoreFocusPending.current) {
      toolRestoreFocusPending.current = false;
      toolReturnFocus.current?.focus();
    }
  }, [toolOpen]);

  /**
   * Change account, platform or format without leaving the page.
   *
   * This replaces `navigateWithDraft`, which wrote the composer text into
   * sessionStorage and then called `window.location.assign` — a full reload
   * whose only way to keep the draft was a key that ignored the target, so the
   * text you wrote for one account reappeared under another. The draft now
   * belongs to its scope (AdvisorDraftV1) and the switch is a URL change.
   */
  const switchScope = (
    next: { publishingIdentityId?: string; target?: Target },
    carried?: string
  ): void => {
    advisorScope.switchTo(next, carried);
  };

  const closeTool = (restoreFocus = true): void => {
    toolRestoreFocusPending.current = restoreFocus;
    setToolOpen(null);
    void loadWorkspace();
  };

  const handleToolKeyDown = (
    event: ReactKeyboardEvent<HTMLElement>
  ): void => {
    if (event.key === "Escape") {
      event.preventDefault();
      closeTool();
      return;
    }
    if (event.key !== "Tab") return;
    const focusable = Array.from(
      toolDrawerRef.current?.querySelectorAll<HTMLElement>(
        "a[href], button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled)"
      ) ?? []
    );
    const first = focusable[0];
    const last = focusable.at(-1);
    if (!first || !last) return;
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  const reloadCatalog = async (): Promise<void> => {
    const value = await api<ExpressionCatalog>(
      scope("/api/v1/content/expression-catalog")
    );
    setCatalog(value);
  };

  const clearOneTimeControls = (): void => {
    setSeed("");
    setSelections({});
    setClearedAxes([]);
    setCustomText("");
    setCustomAxes({});
    setMaterialIds([]);
    setSeriesSelection(null);
    setDirectionsOpen(false);
    setStages([]);
    setTargetConflict(null);
    setDirectGenerationOffer(null);
    setGenerationFailed(false);
    setGenerationFailureMessage("");
    setFailureDiagnostic(null);
    setLastFailedAttempt(null);
  };

  const loadVersions = async (artifact: ContentVersion): Promise<void> => {
    if (targetOf(artifact, currentTarget) !== currentTarget) {
      throw new Error("这份成品属于另一个平台，请先切换平台再打开。");
    }
    const values = await api<ContentVersion[]>(
      scope(`/api/v1/content/tasks/${artifact.task_id}/versions`)
    );
    setVersions(values);
  };

  const openRecent = async (item: RecentContent): Promise<void> => {
    const target = item.target ?? currentTarget;
    if (target !== currentTarget) {
      switchScope({ target });
      return;
    }
    setPending(true);
    setNotice("");
    try {
      const value = await api<ContentVersion>(
        scope(`/api/v1/tasks/${item.task_id}/versions/${item.version}`)
      );
      clearOneTimeControls();
      setMessages([]);
      setCurrent(value);
      setViewed(value);
      await loadVersions(value);
      setMobileView("artifact");
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : "无法打开这份成品。");
    } finally {
      setPending(false);
    }
  };

  const openSeriesTask = async (taskId: string): Promise<void> => {
    setPending(true);
    setNotice("");
    try {
      const values = await api<ContentVersion[]>(
        scope(`/api/v1/content/tasks/${taskId}/versions`)
      );
      const latest = values
        .slice()
        .sort((left, right) => right.version - left.version)[0];
      if (!latest) throw new Error("这个系列条目还没有可读成品。");
      clearOneTimeControls();
      setMessages([]);
      setVersions(values);
      setCurrent(latest);
      setViewed(latest);
      setToolOpen(null);
      setMobileView("artifact");
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : "无法打开这篇系列内容。");
    } finally {
      setPending(false);
    }
  };

  const creativeCustomText = (): string =>
    [
      ...Object.entries(customAxes).map(([axisKey, value]) => {
        const label = catalog?.axes.find(axis => axis.key === axisKey)?.label ?? axisKey;
        return `${label}：${value}`;
      }),
      customText.trim()
    ]
      .filter(Boolean)
      .join("；");

  const conversationTurns = (
    source: ConversationMessage[]
  ): ConversationTurn[] =>
    source.map(message => ({
      role: message.speaker,
      content: message.text
    }));

  const appendAssistant = (text: string): void => {
    setMessages(value => [
      ...value,
      { id: Date.now() + value.length, speaker: "assistant", text }
    ]);
  };

  const runCreationStream = async (
    instruction: string,
    appendUser: boolean,
    targetConflictResolution?: "keep_selected",
    interactionMode: "conversation" | "generate" = "conversation",
    requestId: string = crypto.randomUUID()
  ): Promise<void> => {
    if (pending) return;
    const priorMessages =
      !appendUser &&
      messages.at(-1)?.speaker === "user" &&
      messages.at(-1)?.text === instruction
        ? messages.slice(0, -1)
        : messages;
    const nextConversation = conversationTurns(priorMessages);
    if (appendUser) {
      setMessages(value => [
        ...value,
        { id: Date.now(), speaker: "user", text: instruction }
      ]);
    }
    setPending(true);
    setNotice("");
    setGenerationFailed(false);
    setGenerationFailureMessage("");
    setFailureDiagnostic(null);
    setLastFailedAttempt(null);
    setTargetConflict(null);
    setDirectGenerationOffer(null);
    setStages([]);
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    let terminal = false;
    try {
      for await (const streamEvent of guardContentStream(
        streamApi(
        "/api/v1/content/stream",
        {
          message: instruction,
          conversation: nextConversation,
          publishing_identity_id: currentPublishingIdentityId,
          target: currentTarget,
          target_conflict_resolution: targetConflictResolution,
          interaction_mode: interactionMode,
          direct_generate: interactionMode === "generate",
          request_id: requestId,
          creative_direction: {
            catalog_version: catalog?.catalog_version ?? null,
            selections,
            cleared_axes: clearedAxes,
            custom_text: creativeCustomText(),
            body_related_opt_in: catalog?.body_related_enabled ?? false
          },
          use_personal_preferences: true,
          material_ids: materialIds,
          product_media_intent: productMediaIntent,
          series_id: seriesSelection?.seriesId ?? null,
          series_position: seriesSelection?.position ?? null
        },
        controller.signal
        )
      )) {
        if (isStageEvent(streamEvent)) {
          const stage = streamEvent.event;
          setStages(value => (value.includes(stage) ? value : [...value, stage]));
          continue;
        }
        if (streamEvent.event === "conversation") {
          appendAssistant(streamEvent.message);
          setSeed(value => (value.trim() === instruction ? "" : value));
          setDirectGenerationOffer(
            streamEvent.direct_generation_available ? instruction : null
          );
          setDirectionsOpen(false);
          setLastFailedAttempt(null);
          terminal = true;
          continue;
        }
        if (streamEvent.event === "target_conflict") {
          setTargetConflict({
            target: streamEvent.mentioned_target,
            label: streamEvent.label,
            instruction,
            interactionMode,
            requestId
          });
          setLastFailedAttempt(null);
          terminal = true;
          continue;
        }
        if (streamEvent.event === "completed") {
          setCurrent(streamEvent.result);
          setViewed(streamEvent.result);
          // Clear only the request that just completed. Once the artifact is visible,
          // a person may immediately type the next instruction while history loads.
          setSeed(value => (value.trim() === instruction ? "" : value));
          setDirectGenerationOffer(null);
          await loadVersions(streamEvent.result);
          appendAssistant(
            "第一版已经整理好。你可以直接阅读，也可以继续告诉我哪里要变。"
          );
          setDirectionsOpen(false);
          setMobileView("artifact");
          setLastFailedAttempt(null);
          terminal = true;
          continue;
        }
        if (streamEvent.event === "failed") {
          setGenerationFailed(true);
          setGenerationFailureMessage(
            `${
              streamEvent.detail ??
              streamEvent.message ??
              "这次还没能整理成一份可靠的成品。"
            } 输入和已有成品都已保留。`
          );
          setFailureDiagnostic({
            stage: streamEvent.failure_stage ?? "unknown",
            retryable: streamEvent.retryable ?? true,
            action:
              streamEvent.action ??
              "输入已经保留，可以使用原输入重试。",
            traceId: streamEvent.trace_id ?? ""
          });
          setLastFailedAttempt({
            kind: "stream",
            instruction,
            interactionMode,
            requestId
          });
          terminal = true;
        }
      }
      if (!terminal) {
        setGenerationFailed(true);
        setGenerationFailureMessage(
          "连接提前结束了，输入和已有成品都已保留，可以安全重试。"
        );
        setFailureDiagnostic({
          stage: "transport",
          retryable: true,
          action: "网络恢复后可以使用原输入重试。",
          traceId: ""
        });
        setLastFailedAttempt({
          kind: "stream",
          instruction,
          interactionMode,
          requestId
        });
      }
    } catch (reason) {
      if (!(reason instanceof DOMException && reason.name === "AbortError")) {
        setGenerationFailed(true);
        if (reason instanceof ContentStreamContractError) {
          // The stream broke its own contract. Nothing it carried reaches the
          // workspace: the guard withheld the result, and the transient progress
          // trail goes with it so the failure is not shown mid-generation.
          setStages([]);
          setGenerationFailureMessage(reason.message);
          setFailureDiagnostic({
            stage: "contract",
            retryable: true,
            action: "输入已经保留，可以使用原输入重试。",
            traceId: ""
          });
        } else if (reason instanceof ApiError) {
          setGenerationFailureMessage(
            `${reason.message} 输入和已有成品都已保留。`
          );
          setFailureDiagnostic({
            stage: reason.failureStage,
            retryable: reason.retryable,
            action: reason.action,
            traceId: reason.traceId
          });
        } else {
          setGenerationFailureMessage(
            "网络没有完成这次请求。输入和已有成品都已保留，可以恢复后重试。"
          );
          setFailureDiagnostic({
            stage: "transport",
            retryable: true,
            action: "网络恢复后可以使用原输入重试。",
            traceId: ""
          });
        }
        setLastFailedAttempt({
          kind: "stream",
          instruction,
          interactionMode,
          requestId
        });
      }
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
      setPending(false);
    }
  };

  const runRevision = async (
    instruction: string,
    appendUser: boolean,
    requestId: string = crypto.randomUUID()
  ): Promise<void> => {
    if (!current || pending) return;
    setPending(true);
    setNotice("");
    setGenerationFailed(false);
    setGenerationFailureMessage("");
    setFailureDiagnostic(null);
    setLastFailedAttempt(null);
    if (appendUser) {
      setMessages(value => [
        ...value,
        { id: Date.now(), speaker: "user", text: instruction }
      ]);
    }
    try {
      const payload = await api<ContentVersion | AssistantReply>(
        scope(`/api/v1/tasks/${current.task_id}/revisions`),
        {
          method: "POST",
          body: JSON.stringify({
            instruction,
            publishing_identity_id: currentPublishingIdentityId,
            target: currentTarget,
            source_target: currentTarget,
            request_id: requestId
          })
        }
      );
      // Clear the submitted instruction before any asynchronous version-history
      // refresh. A newer instruction typed after V2 appears must remain untouched.
      setSeed(value => (value.trim() === instruction ? "" : value));
      if (!("task_id" in payload)) {
        appendAssistant(payload.message);
      } else {
        setCurrent(payload);
        setViewed(payload);
        await loadVersions(payload);
        appendAssistant(
          `已经按你的话改成 V${payload.version}，上一版完整保留。`
        );
        setMobileView("artifact");
      }
      setDirectionsOpen(false);
      setLastFailedAttempt(null);
    } catch (reason) {
      setGenerationFailed(true);
      if (reason instanceof ApiError) {
        setGenerationFailureMessage(
          `${reason.message} 你的要求和已有版本都已保留。`
        );
        setFailureDiagnostic({
          stage: reason.failureStage,
          retryable: reason.retryable,
          action: reason.action,
          traceId: reason.traceId
        });
      } else {
        setGenerationFailureMessage(
          "这次修改没有完成。你的要求和已有版本都已保留，可以安全重试。"
        );
        setFailureDiagnostic({
          stage: "transport",
          retryable: true,
          action: "网络恢复后可以使用同一修改要求重试。",
          traceId: ""
        });
      }
      setLastFailedAttempt({ kind: "revision", instruction, requestId });
    } finally {
      setPending(false);
    }
  };

  const submit = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    const instruction = seed.trim();
    if (!instruction || pending) return;
    if (!hasResolvedIdentity) {
      setNotice("请先选择一个发布账号。");
      return;
    }
    if (current && targetOf(current, currentTarget) !== currentTarget) {
      switchScope({ target: targetOf(current, currentTarget) });
      return;
    }
    if (!current) {
      await runCreationStream(instruction, true, undefined, "generate");
      return;
    }
    await runRevision(instruction, true);
  };

  const sendConversation = async (): Promise<void> => {
    const instruction = seed.trim();
    if (!instruction || pending) return;
    if (!hasResolvedIdentity) {
      setNotice("请先选择一个发布账号。");
      return;
    }
    await runCreationStream(instruction, true, undefined, "conversation");
  };

  const saveDefaults = async (): Promise<void> => {
    if (!preference || savingDefaults) return;
    const effective = { ...catalog?.saved_defaults };
    clearedAxes.forEach(axis => delete effective[axis]);
    Object.assign(effective, selections);
    setSavingDefaults(true);
    setNotice("");
    try {
      const value = await api<CreationPreference>(
        scope("/api/v1/user/creation-preferences"),
        {
        method: "PUT",
        body: JSON.stringify({
          enabled: true,
          direction_defaults: effective,
          clear_direction_defaults: Object.keys(effective).length === 0,
          collaboration_note: preference.collaboration_note,
          body_related_opt_in: preference.body_related_opt_in
        })
        }
      );
      setPreference(value);
      await reloadCatalog();
      setNotice("已经保存为你的默认方向；只会在你没有提出本次方向时使用。");
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : "默认方向没有保存成功。");
    } finally {
      setSavingDefaults(false);
    }
  };

  const updatePreference = (value: CreationPreference): void => {
    setPreference(value);
    void reloadCatalog();
  };

  const startFresh = (): void => {
    setCurrent(null);
    setViewed(null);
    setVersions([]);
    clearOneTimeControls();
    setMessages([]);
    setMobileView("conversation");
  };

  const directionSummary = useMemo(() => {
    if (!catalog) return "";
    const labels = catalog.axes.flatMap(axis => {
      if (clearedAxes.includes(axis.key)) return [`${axis.label}：本次不使用`];
      if (customAxes[axis.key]) return [`${axis.label}：${customAxes[axis.key]}`];
      const stableId = selections[axis.key] ?? catalog.saved_defaults[axis.key];
      const option = axis.options.find(item => item.stable_id === stableId);
      return option ? [`${axis.label}：${option.label}`] : [];
    });
    if (customText.trim()) labels.push(`补充：${customText.trim()}`);
    return labels.length ? labels.join(" · ") : "这次不预设方向";
  }, [catalog, clearedAxes, customAxes, customText, selections]);

  return (
    <div className={`creator-app ${current ? "has-artifact" : "empty-creator"}`}>
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

      <main
        className={`creator-conversation ${mobileView === "artifact" ? "mobile-hidden" : ""}`}
      >
        <section className="conversation-stream" aria-live="polite">
          {messages.length === 0 ? (
            <div className="creator-welcome">
              <p className="eyebrow">{targetLabel}</p>
              <h1>{hasResolvedIdentity ? "今天想说什么？" : "先选择发布账号"}</h1>
              <p>
                {hasResolvedIdentity
                  ? "写一句想法就可以，其他的交给笛语。"
                  : "选择后再决定平台和内容形式。"}
              </p>
            </div>
          ) : (
            messages.map(message => (
              <article key={message.id} className={`message ${message.speaker}`}>
                <span>{message.speaker === "user" ? "你" : "笛语"}</span>
                <p>{message.text}</p>
              </article>
            ))
          )}
          {pending && stages.length > 0 && (
            <div className="generation-progress" role="status" aria-live="polite">
              <span className="progress-pulse" aria-hidden="true" />
              <div>
                <strong>{STAGE_LABELS[stages.at(-1) ?? "received"]}</strong>
                <small>{targetLabel} · 完整成品会在检查完成后一次呈现</small>
              </div>
            </div>
          )}
          {targetConflict && (
            <div className="target-conflict" role="status">
              <p>
                你提到了{targetConflict.label}，但页面当前选的是{targetLabel}。这次想用哪个？
              </p>
              <div>
                <button
                  type="button"
                  onClick={() =>
                    void runCreationStream(
                      targetConflict.instruction,
                      false,
                      "keep_selected",
                      targetConflict.interactionMode,
                      targetConflict.requestId
                    )
                  }
                >
                  继续使用{targetLabel}
                </button>
                <button
                  type="button"
                  className="primary"
                  onClick={() => {
                    switchScope(
                      { target: targetConflict.target },
                      targetConflict.instruction
                    );
                  }}
                >
                  切换到{targetConflict.label}
                </button>
              </div>
            </div>
          )}
          {directGenerationOffer && !targetConflict && !generationFailed && (
            <div className="direct-generation-offer" role="status">
              <p>如果你是想把刚才这段直接做成完整内容，可以从这里继续。</p>
              <button
                type="button"
                className="primary"
                disabled={pending}
                onClick={() =>
                  void runCreationStream(
                    directGenerationOffer,
                    false,
                    undefined,
                    "generate"
                  )
                }
              >
                直接生成
              </button>
            </div>
          )}
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
                  onClick={() => {
                    setGenerationFailed(false);
                    setGenerationFailureMessage("");
                    setFailureDiagnostic(null);
                    setLastFailedAttempt(null);
                    composerRef.current?.focus();
                  }}
                >
                  继续补充
                </button>
                {failureDiagnostic?.retryable !== false && (
                  <button
                    type="button"
                    className="primary"
                    disabled={!lastFailedAttempt || pending}
                    onClick={() => {
                      if (!lastFailedAttempt) return;
                      if (lastFailedAttempt.kind === "stream") {
                        void runCreationStream(
                          lastFailedAttempt.instruction,
                          false,
                          undefined,
                          lastFailedAttempt.interactionMode ?? "conversation",
                          lastFailedAttempt.requestId
                        );
                      } else {
                        void runRevision(
                          lastFailedAttempt.instruction,
                          false,
                          lastFailedAttempt.requestId
                        );
                      }
                    }}
                  >
                    再试一次
                  </button>
                )}
              </div>
            </div>
          )}
          {loadError && (
            <div className="inline-error" role="alert">
              <span>{loadError}</span>
              <button type="button" onClick={() => void loadWorkspace()}>
                重新读取
              </button>
            </div>
          )}
          {notice && (
            <div className="conversation-notice" role="status">
              <span>{notice}</span>
              <button type="button" aria-label="关闭提示" onClick={() => setNotice("")}>
                ×
              </button>
            </div>
          )}
        </section>

        <form className="creator-composer" onSubmit={event => void submit(event)}>
          <textarea
            ref={composerRef}
            aria-label={current ? "修改要求" : "内容需求"}
            value={seed}
            onChange={event => setSeed(event.target.value)}
            maxLength={1000}
            placeholder={
              current
                ? `告诉我 V${current.version} 哪些地方要变，其他内容会保留。`
                : hasResolvedIdentity
                  ? "例如：想讲讲进门后只想自己看看，沉默也应该被尊重。"
                  : "请先在顶部选择发布账号。"
            }
          />
          {!current && (
            <>
              <div className="composer-resource-actions" aria-label="创作资料">
                <button
                  type="button"
                  disabled={!hasResolvedIdentity}
                  onClick={event => {
                    toolReturnFocus.current = event.currentTarget;
                    setToolOpen("series");
                  }}
                >
                  {seriesSelection ? "连续系列 · 已选择" : "连续系列"}
                </button>
                <button
                  type="button"
                  disabled={!hasResolvedIdentity}
                  onClick={event => {
                    toolReturnFocus.current = event.currentTarget;
                    setToolOpen("materials");
                  }}
                >
                  {materialIds.length ? `素材 · ${materialIds.length} 份` : "素材"}
                </button>
              </div>
              {(seriesSelection || materialIds.length > 0) && (
                <div className="composer-context" aria-label="本次承接">
                  {seriesSelection && (
                    <span>
                      连续系列
                      {seriesSelection.position ? ` · 第 ${seriesSelection.position} 篇` : ""}
                    </span>
                  )}
                  {materialIds.length > 0 && <span>参考素材 {materialIds.length} 份</span>}
                </div>
              )}
              <details className="composer-context-basis">
                <summary>本次依据</summary>
                <dl>
                  <div><dt>当前账号</dt><dd>{currentPublishingIdentity.name}</dd></div>
                  <div><dt>平台和形式</dt><dd>{currentTargetMetadata.platform_label} · {currentTargetMetadata.format_label}</dd></div>
                  <div><dt>品牌资料</dt><dd>系统会按这次题材选择相关资料，不会加载整库</dd></div>
                  <div><dt>商品资料</dt><dd>只有本次明确商品才会进入</dd></div>
                  <div><dt>制作素材</dt><dd>{materialIds.length ? `已选择 ${materialIds.length} 份` : "本次未选择"}</dd></div>
                </dl>
              </details>
              <button
                ref={directionToggleRef}
                className="direction-toggle"
                type="button"
                disabled={!hasResolvedIdentity}
                aria-expanded={directionsOpen}
                aria-controls="creator-direction-panel"
                onClick={() =>
                  directionsOpen ? closeDirections() : setDirectionsOpen(true)
                }
              >
                <span>创作方向（可选）</span>
                <small>{directionSummary}</small>
              </button>
              {directionsOpen && (
                <>
                  <button
                    className="direction-backdrop"
                    type="button"
                    aria-label="关闭创作方向"
                    onClick={closeDirections}
                  />
                  <section
                    id="creator-direction-panel"
                    ref={directionPanelRef}
                    className="direction-panel"
                    role={compactDirections ? "dialog" : "region"}
                    aria-modal={compactDirections ? "true" : undefined}
                    aria-label="创作方向"
                    onKeyDown={handleDirectionKeyDown}
                  >
                    <header className="direction-mobile-header">
                      <strong>创作方向</strong>
                      <button
                        ref={directionCloseRef}
                        className="icon-button"
                        type="button"
                        aria-label="关闭创作方向"
                        onClick={closeDirections}
                      >
                        ×
                      </button>
                    </header>
                    <DirectionPanel
                      catalog={catalog}
                      selections={selections}
                      clearedAxes={clearedAxes}
                      customText={customText}
                      customAxes={customAxes}
                      materials={materials}
                      materialIds={materialIds}
                      onSelections={setSelections}
                      onClearedAxes={setClearedAxes}
                      onCustomText={setCustomText}
                      onCustomAxes={setCustomAxes}
                      onMaterialIds={setMaterialIds}
                      onSaveDefaults={() => void saveDefaults()}
                      saving={savingDefaults}
                    />
                  </section>
                </>
              )}
            </>
          )}
          <div className="composer-submit">
            {current && (
              <button className="text-action" type="button" onClick={startFresh}>
                另起一条
              </button>
            )}
            {!targetConflict && !generationFailed && (
              <>
                <button
                  type="button"
                  disabled={!seed.trim() || pending}
                  onClick={() => void sendConversation()}
                >
                  发送
                </button>
                <button className="primary" type="submit" disabled={!seed.trim() || pending}>
                  {pending
                    ? STAGE_LABELS[stages.at(-1) ?? "received"]
                    : current
                      ? `修改成 V${current.version + 1}`
                      : "生成内容"}
                </button>
              </>
            )}
          </div>
        </form>
      </main>

      <div className={`artifact-workspace ${mobileView === "conversation" ? "mobile-hidden" : ""}`}>
        <ArtifactPane
          viewed={viewed}
          current={current}
          versions={versions}
          onView={setViewed}
          onCurrent={() => current && setViewed(current)}
          onNotice={setNotice}
        />
      </div>

      {current && (
        <nav className="mobile-work-tabs" aria-label="工作面切换">
          <button
            type="button"
            className={mobileView === "conversation" ? "active" : ""}
            onClick={() => setMobileView("conversation")}
          >
            对话
          </button>
          <button
            type="button"
            className={mobileView === "artifact" ? "active" : ""}
            onClick={() => setMobileView("artifact")}
          >
            成品
          </button>
        </nav>
      )}

      {accountOpen && (
        <AccountDrawer
          context={context}
          publishingIdentity={currentPublishingIdentity}
          preferencePath={scope("/api/v1/user/creation-preferences")}
          preference={preference}
          profile={profile}
          profilePath={scope(
            "/api/v1/content/account-expression-profile/versions"
          )}
          onClose={() => {
            setAccountOpen(false);
            identityTriggerRef.current?.focus();
          }}
          onPreference={updatePreference}
          onProfile={setProfile}
        />
      )}
      {toolOpen && (
        <div
          className="drawer-layer"
          role="presentation"
          onMouseDown={() => closeTool()}
        >
          <aside
            ref={toolDrawerRef}
            className="creator-tool-drawer"
            role="dialog"
            aria-modal="true"
            aria-label={toolOpen === "series" ? "连续系列" : "我的素材"}
            onMouseDown={event => event.stopPropagation()}
            onKeyDown={handleToolKeyDown}
          >
            <button
              ref={toolCloseRef}
              className="icon-button tool-drawer-close"
              type="button"
              aria-label="关闭"
              onClick={() => closeTool()}
            >
              ×
            </button>
            {toolOpen === "series" ? (
              <SeriesPanel
                selected={seriesSelection}
                onSelect={setSeriesSelection}
                publishingIdentityId={currentPublishingIdentityId}
                target={currentTarget}
                onOpenTask={taskId => void openSeriesTask(taskId)}
                onContinue={value => {
                  startFresh();
                  setSeriesSelection(value);
                  closeTool(false);
                }}
              />
            ) : (
              <MaterialsPanel
                selectedIds={materialIds}
                onSelectedIdsChange={setMaterialIds}
                publishingIdentityId={currentPublishingIdentityId}
                target={currentTarget}
              />
            )}
          </aside>
        </div>
      )}
      {bodyOptIn && <span className="sr-only">体型相关方向已由本人主动启用</span>}
    </div>
  );
}
