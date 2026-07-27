import { useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent, JSX, KeyboardEvent as ReactKeyboardEvent } from "react";
import { BrandMark } from "../components/Brand";
import { api, transferredContent } from "../services/api";
import type {
  AccountExpression,
  AssistantReply,
  BootstrapContext,
  CatalogAxis,
  ContentVersion,
  CreationPreference,
  ExpressionCatalog,
  Material,
  RecentContent,
  Target
} from "./types";

type ConversationMessage = {
  id: number;
  speaker: "user" | "assistant";
  text: string;
};

const PRIMARY_AXES = new Set(["topic", "style", "form"]);

function targetOf(version: ContentVersion, fallback: Target): Target {
  return version.target_key ?? version.target ?? fallback;
}

function humanDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? ""
    : new Intl.DateTimeFormat("zh-CN", { month: "numeric", day: "numeric" }).format(date);
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
  onClear
}: {
  axis: CatalogAxis;
  selection?: string;
  saved?: string;
  cleared: boolean;
  onChoose: (value: string) => void;
  onClear: () => void;
}): JSX.Element {
  const savedLabel = axis.options.find(option => option.stable_id === saved)?.label;
  return (
    <fieldset className="direction-axis">
      <legend>
        <span>{axis.label}</span>
        <small>{axis.question}</small>
      </legend>
      <div className="direction-options">
        {axis.options.map(option => {
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
      </div>
    </fieldset>
  );
}

function DirectionPanel({
  catalog,
  selections,
  clearedAxes,
  customText,
  materials,
  materialIds,
  onSelections,
  onClearedAxes,
  onCustomText,
  onMaterialIds,
  onSaveDefaults,
  saving
}: {
  catalog: ExpressionCatalog | null;
  selections: Record<string, string>;
  clearedAxes: string[];
  customText: string;
  materials: Material[];
  materialIds: string[];
  onSelections: (value: Record<string, string>) => void;
  onClearedAxes: (value: string[]) => void;
  onCustomText: (value: string) => void;
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
    />
  );
  return (
    <div className="direction-content">
      {primary.map(renderAxis)}
      <button className="text-action" type="button" onClick={() => setMore(value => !value)}>
        {more ? "收起更多" : "更多：讲法与连续方式"}
      </button>
      {more && <div className="more-directions">{secondary.map(renderAxis)}</div>}
      <label className="custom-direction">
        没有合适的？直接说你想要的方向。
        <input
          value={customText}
          onChange={event => onCustomText(event.target.value)}
          maxLength={500}
          placeholder="例如：像给熟悉的朋友解释，不用口号。"
        />
        <small>你的原话会随本次任务保留，不会被悄悄换成相近选项。</small>
      </label>
      {materials.length > 0 && (
        <fieldset className="material-options">
          <legend>本次素材（可选）</legend>
          {materials.map(material => {
            const readable =
              material.media_type === "text" || Boolean(material.reference_note?.trim());
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

function AccountDrawer({
  context,
  preference,
  profile,
  onClose,
  onPreference
}: {
  context: BootstrapContext;
  preference: CreationPreference | null;
  profile: AccountExpression | null;
  onClose: () => void;
  onPreference: (value: CreationPreference) => void;
}): JSX.Element {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const panelRef = useRef<HTMLElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeRef.current?.focus();
  }, []);

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
      const next = await api<CreationPreference>("/api/v1/user/creation-preferences", {
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
            <h2 id="account-drawer-title">{identity.account ?? "当前发布账号"}</h2>
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
            <dd>{identity.content_role ?? "—"}</dd>
          </div>
          <div>
            <dt>负责团队</dt>
            <dd>{identity.organization ?? "—"}</dd>
          </div>
        </dl>
        {profile?.current && (
          <section className="profile-summary">
            <h3>账号定位 · V{profile.current.version}</h3>
            <p>{profile.current.identity_position}</p>
            <p>{profile.current.audience_relationship}</p>
          </section>
        )}
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
            {error && <p className="inline-error">{error}</p>}
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
  context
}: {
  context: BootstrapContext;
}): JSX.Element {
  const currentTarget =
    context.current_target ?? context.targets?.[0]?.value ?? "douyin_video";
  const [catalog, setCatalog] = useState<ExpressionCatalog | null>(null);
  const [preference, setPreference] = useState<CreationPreference | null>(null);
  const [profile, setProfile] = useState<AccountExpression | null>(null);
  const [materials, setMaterials] = useState<Material[]>([]);
  const [recent, setRecent] = useState<RecentContent[]>([]);
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [seed, setSeed] = useState("");
  const [selections, setSelections] = useState<Record<string, string>>({});
  const [clearedAxes, setClearedAxes] = useState<string[]>([]);
  const [customText, setCustomText] = useState("");
  const [materialIds, setMaterialIds] = useState<string[]>([]);
  const [directionsOpen, setDirectionsOpen] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const [mobileView, setMobileView] = useState<"conversation" | "artifact">("conversation");
  const [current, setCurrent] = useState<ContentVersion | null>(null);
  const [viewed, setViewed] = useState<ContentVersion | null>(null);
  const [versions, setVersions] = useState<ContentVersion[]>([]);
  const [pending, setPending] = useState(false);
  const [savingDefaults, setSavingDefaults] = useState(false);
  const [notice, setNotice] = useState("");
  const [loadError, setLoadError] = useState("");
  const identityTriggerRef = useRef<HTMLButtonElement>(null);

  const identity = context.identity ?? {};
  const targetLabel =
    context.targets?.find(item => item.value === currentTarget)?.label ?? "当前平台";
  const bodyOptIn = preference?.body_related_opt_in ?? false;

  const loadWorkspace = async (): Promise<void> => {
    setLoadError("");
    try {
      const [catalogValue, preferenceValue, materialValue, profileValue] =
        await Promise.all([
          api<ExpressionCatalog>("/api/v1/content/expression-catalog"),
          api<CreationPreference>("/api/v1/user/creation-preferences"),
          api<Material[]>("/api/v1/materials"),
          api<AccountExpression>("/api/v1/content/account-expression-profile")
        ]);
      setCatalog(catalogValue);
      setPreference(preferenceValue);
      setMaterials(materialValue);
      setProfile(profileValue);
      const currentRecent = await api<RecentContent[]>(
        `/api/v1/content/tasks?target=${currentTarget}`
      );
      setRecent(
        currentRecent
          .slice()
          .sort((left, right) => right.updated_at.localeCompare(left.updated_at))
      );
    } catch (reason) {
      setLoadError(reason instanceof Error ? reason.message : "当前工作空间没有准备好。");
    }
  };

  useEffect(() => {
    void loadWorkspace();
    // The server bootstrap is immutable for this page load. A target change navigates and creates
    // a new page bootstrap, so no client account guess belongs in this dependency list.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const reloadCatalog = async (): Promise<void> => {
    const value = await api<ExpressionCatalog>("/api/v1/content/expression-catalog");
    setCatalog(value);
  };

  const clearOneTimeControls = (): void => {
    setSeed("");
    setSelections({});
    setClearedAxes([]);
    setCustomText("");
    setMaterialIds([]);
    setDirectionsOpen(false);
  };

  const loadVersions = async (artifact: ContentVersion): Promise<void> => {
    if (targetOf(artifact, currentTarget) !== currentTarget) {
      throw new Error("这份成品属于另一个平台，请先切换平台再打开。");
    }
    const values = await api<ContentVersion[]>(
      `/api/v1/content/tasks/${artifact.task_id}/versions?target=${currentTarget}`
    );
    setVersions(values);
  };

  const openRecent = async (item: RecentContent): Promise<void> => {
    const target = item.target ?? currentTarget;
    if (target !== currentTarget) {
      window.location.assign(`/content?target=${target}`);
      return;
    }
    setPending(true);
    setNotice("");
    try {
      const value = await api<ContentVersion>(
        `/api/v1/tasks/${item.task_id}/versions/${item.version}?target=${currentTarget}`
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

  const submit = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    const instruction = seed.trim();
    if (!instruction || pending) return;
    if (current && targetOf(current, currentTarget) !== currentTarget) {
      window.location.assign(`/content?target=${targetOf(current, currentTarget)}`);
      return;
    }
    setPending(true);
    setNotice("");
    setMessages(value => [
      ...value,
      { id: Date.now(), speaker: "user", text: instruction }
    ]);
    try {
      if (current) {
        const payload = await api<ContentVersion | AssistantReply>(
          `/api/v1/tasks/${current.task_id}/revisions`,
          {
            method: "POST",
            body: JSON.stringify({
              instruction,
              target: currentTarget,
              source_target: currentTarget
            })
          }
        );
        if (!("task_id" in payload)) {
          setMessages(value => [
            ...value,
            { id: Date.now() + 1, speaker: "assistant", text: payload.message }
          ]);
        } else {
          setCurrent(payload);
          setViewed(payload);
          await loadVersions(payload);
          setMessages(value => [
            ...value,
            {
              id: Date.now() + 1,
              speaker: "assistant",
              text: `已经按你的话改成 V${payload.version}，上一版完整保留。`
            }
          ]);
          setMobileView("artifact");
        }
      } else {
        const payload = await api<ContentVersion | AssistantReply>("/api/v1/content", {
          method: "POST",
          body: JSON.stringify({
            weak_seed: instruction,
            target: currentTarget,
            creative_direction: {
              catalog_version: catalog?.catalog_version ?? null,
              selections,
              cleared_axes: clearedAxes,
              custom_text: customText.trim(),
              body_related_opt_in: catalog?.body_related_enabled ?? false
            },
            use_personal_preferences: true,
            material_ids: materialIds,
            series_id: null,
            series_position: null
          })
        });
        if (!("task_id" in payload)) {
          setMessages(value => [
            ...value,
            { id: Date.now() + 1, speaker: "assistant", text: payload.message }
          ]);
        } else {
          setCurrent(payload);
          setViewed(payload);
          await loadVersions(payload);
          setMessages(value => [
            ...value,
            {
              id: Date.now() + 1,
              speaker: "assistant",
              text: "第一版已经整理好。你可以直接阅读，也可以继续告诉我哪里要变。"
            }
          ]);
          setMobileView("artifact");
        }
      }
      setSeed("");
      setDirectionsOpen(false);
    } catch (reason) {
      setNotice(
        reason instanceof Error
          ? reason.message
          : "这次没有生成内容，你的输入仍然保留。"
      );
    } finally {
      setPending(false);
    }
  };

  const saveDefaults = async (): Promise<void> => {
    if (!preference || savingDefaults) return;
    const effective = { ...catalog?.saved_defaults };
    clearedAxes.forEach(axis => delete effective[axis]);
    Object.assign(effective, selections);
    setSavingDefaults(true);
    setNotice("");
    try {
      const value = await api<CreationPreference>("/api/v1/user/creation-preferences", {
        method: "PUT",
        body: JSON.stringify({
          enabled: true,
          direction_defaults: effective,
          clear_direction_defaults: Object.keys(effective).length === 0,
          collaboration_note: preference.collaboration_note,
          body_related_opt_in: preference.body_related_opt_in
        })
      });
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
      const stableId = selections[axis.key] ?? catalog.saved_defaults[axis.key];
      const option = axis.options.find(item => item.stable_id === stableId);
      return option ? [`${axis.label}：${option.label}`] : [];
    });
    return labels.length ? labels.join(" · ") : "这次不预设方向";
  }, [catalog, clearedAxes, selections]);

  return (
    <div className={`creator-app ${current ? "has-artifact" : "empty-creator"}`}>
      <header className="creator-topbar">
        <a className="creator-brand" href="/user">
          <BrandMark compact />
        </a>
        <button
          ref={identityTriggerRef}
          className="identity-trigger"
          type="button"
          onClick={() => setAccountOpen(true)}
        >
          <strong>{identity.account ?? "当前发布账号"}</strong>
          <span>
            {identity.content_role ?? "当前表达身份"} · {targetLabel}
          </span>
        </button>
        <label className="target-switch">
          <span className="sr-only">切换平台版本</span>
          <select
            value={currentTarget}
            onChange={event => {
              window.location.assign(`/content?target=${event.target.value}`);
            }}
          >
            {(context.targets ?? []).map(item => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
      </header>

      <aside className="creator-history">
        <button className="new-content" type="button" onClick={startFresh}>
          ＋ 新创作
        </button>
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
              <h1>今天想说什么？</h1>
              <p>写一句想法就可以，其他的交给笛语。</p>
            </div>
          ) : (
            messages.map(message => (
              <article key={message.id} className={`message ${message.speaker}`}>
                <span>{message.speaker === "user" ? "你" : "笛语"}</span>
                <p>{message.text}</p>
              </article>
            ))
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
            aria-label={current ? "修改要求" : "内容需求"}
            value={seed}
            onChange={event => setSeed(event.target.value)}
            maxLength={1000}
            placeholder={
              current
                ? `告诉我 V${current.version} 哪些地方要变，其他内容会保留。`
                : "例如：想讲讲进门后只想自己看看，沉默也应该被尊重。"
            }
          />
          {!current && (
            <>
              <button
                className="direction-toggle"
                type="button"
                aria-expanded={directionsOpen}
                onClick={() => setDirectionsOpen(value => !value)}
              >
                <span>创作方向（可选）</span>
                <small>{directionSummary}</small>
              </button>
              {directionsOpen && (
                <DirectionPanel
                  catalog={catalog}
                  selections={selections}
                  clearedAxes={clearedAxes}
                  customText={customText}
                  materials={materials}
                  materialIds={materialIds}
                  onSelections={setSelections}
                  onClearedAxes={setClearedAxes}
                  onCustomText={setCustomText}
                  onMaterialIds={setMaterialIds}
                  onSaveDefaults={() => void saveDefaults()}
                  saving={savingDefaults}
                />
              )}
            </>
          )}
          <div className="composer-submit">
            {current && (
              <button className="text-action" type="button" onClick={startFresh}>
                另起一条
              </button>
            )}
            <button className="primary" type="submit" disabled={!seed.trim() || pending}>
              {pending ? "正在整理……" : current ? `生成 V${current.version + 1}` : "生成内容"}
            </button>
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
          preference={preference}
          profile={profile}
          onClose={() => {
            setAccountOpen(false);
            identityTriggerRef.current?.focus();
          }}
          onPreference={updatePreference}
        />
      )}
      {bodyOptIn && <span className="sr-only">体型相关方向已由本人主动启用</span>}
    </div>
  );
}
