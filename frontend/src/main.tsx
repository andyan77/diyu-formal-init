import { useEffect, useMemo, useState } from "react";
import type { FormEvent, JSX, ReactNode } from "react";
import "./styles.css";

type Application = "content" | "display" | "tenant_user" | "tenant_management";
type Target = "douyin_video" | "xiaohongshu_video" | "xiaohongshu_graphic" | "wechat_channels_video";

interface Context {
  application: Application;
  generator_mode: "stub" | "deepseek";
  identity: Record<string, string>;
  targets?: Array<{ value: Target; label: string }>;
  formal_runtime?: boolean;
}

interface ContentVersion {
  kind: string;
  task_id: string;
  version_id: string;
  version: number;
  outline: string;
  body: string;
  ai_generated: boolean;
  aigc_label?: string | null;
  aigc_release_reminder?: string | null;
  target?: Target;
  target_key?: Target;
  adapted_from?: string | null;
  translation_notice?: string | null;
  applied_direction?: string[];
}

interface CatalogOption {
  stable_id: string;
  label: string;
  capability_state: string;
  body_related: boolean;
}

interface CatalogAxis {
  key: string;
  label: string;
  question: string;
  options: CatalogOption[];
}

interface ExpressionCatalog {
  catalog_version: string;
  body_related_enabled: boolean;
  preference_session: "normal" | "bypassed";
  saved_defaults: Record<string, string>;
  axes: CatalogAxis[];
}

interface ExpressionSegments {
  profile_id: string | null;
  version: number | null;
  content_role: string;
  identity_position: string;
  authority_boundary: string;
  audience_relationship: string;
  content_territories: string;
  default_production_conditions: string;
  is_draft?: boolean;
}

interface AccountExpression {
  account: string;
  content_role: string;
  control_organization?: string;
  control_organization_source?: "unset" | "inferred" | "declared";
  can_maintain: boolean;
  can_declare?: boolean;
  current: ExpressionSegments | null;
  draft?: ExpressionSegments | null;
  draft_source?: string | null;
  segment_labels: Record<string, string>;
}

interface CreationPreference {
  exists: boolean;
  enabled: boolean;
  version: number | null;
  direction_defaults: Record<string, string>;
  collaboration_note: string;
  body_related_opt_in: boolean;
}

interface Opportunity {
  id: string;
  title: string;
  seed_text: string;
  selections: Record<string, string>;
  material_ids: string[];
  why: string;
}

interface OpportunityList {
  catalog_version: string;
  profile_is_draft: boolean;
  items: Opportunity[];
  boundary: string;
}

interface PlanItem {
  title: string;
  note: string;
  selections: Record<string, string>;
}

interface ContentPlan {
  document: { items: PlanItem[] };
  updated_at: string | null;
}

interface UnmetRequest {
  stable_request_id: string;
  request_text: string;
  gap_type: string;
  status: string;
  response_text: string;
  created_at: string;
}

const SEGMENT_ORDER = [
  "identity_position",
  "authority_boundary",
  "audience_relationship",
  "content_territories",
  "default_production_conditions"
] as const;

interface DisplayVersion {
  kind: string;
  task_id: string;
  version_id: string;
  version: number;
  body: string;
}

interface ContentHistoryVersion extends Omit<ContentVersion, "kind" | "target" | "adapted_from"> {
  created_at: string;
}

interface DisplayHistoryVersion extends DisplayVersion {
  created_at: string;
}

interface RecentItem {
  task_id: string;
  version_id: string;
  version: number;
  title: string;
  target?: Target;
  updated_at: string;
  status: string;
}

interface Readiness {
  items: Array<{ id: string; title: string; detail: string; unlock: string; state: "ready" | "needs_action" }>;
}

interface BrandExpression {
  version: number;
  status: "draft" | "confirmed";
  draft: string;
}

interface Series {
  id: string;
  title: string;
  premise: string;
  revision: number;
  items: Array<{ task_id: string; position: number; title: string }>;
}

interface Material {
  id: string;
  title: string;
  media_type: string;
  scope: "personal" | "organization";
  created_at: string;
  status: string;
  reference_note?: string;
}

interface PublishingAccount {
  id: string;
  name: string;
  channel: string;
  content_role: string;
  voice_boundary: string;
  carrier_of_account_id?: string | null;
  carrier_of_account?: string | null;
  operators?: Array<{ id: string; display_name: string }>;
  business_data_kind?: "formal_business_data" | "synthetic_business_fixture";
}

interface TenantOrganization {
  id: string;
  name: string;
  business_data_kind?: "formal_business_data" | "synthetic_business_fixture";
}

interface CreatePublishingAccount {
  name: string;
  channel: "抖音" | "小红书" | "微信视频号";
  content_role_name: string;
  voice_boundary: string;
  operator_id: string;
}

interface BrandProduct {
  sku: string;
  display_name: string;
  facts: Record<string, unknown>;
  source_kind: string;
  source_note: string;
  fact_version: number;
  applicability: string;
  status: "active" | "retired";
  updated_by?: string | null;
  updated_at: string;
}

interface ProductPrefill {
  sku: string;
  display_name: string;
  category: string;
  colors: string[];
  material_or_structure: string;
  silhouette: string;
  observable_features: string;
  source_note: string;
  applicability: string;
  candidate_evidence: string;
}

interface PlatformCarrierPrefill {
  source_account_id: string;
  source_account_name: string;
  name: string;
  channel: CreatePublishingAccount["channel"];
  operator_id: string;
  operator_name: string;
}

interface OnboardingPrefill {
  schema_version?: string;
  status?: "review_candidate";
  source_summary?: string;
  source_refs?: string[];
  product_drafts: ProductPrefill[];
  platform_carrier_drafts: PlatformCarrierPrefill[];
}

interface Operator {
  id: string;
  display_name: string;
  username?: string;
  organization: string;
  publishing_accounts: string;
  default_persona: string;
  manages_tenant: boolean;
}

declare global {
  interface Window {
    __DIYU_BOOTSTRAP__?: Context | null;
  }
}

type QueryKey = readonly string[];

function useQuery<T>({ queryKey, queryFn, enabled = true }: { queryKey: QueryKey; queryFn: () => Promise<T>; enabled?: boolean }): { data: T | undefined; isLoading: boolean; error: Error | null } {
  const [data, setData] = useState<T>();
  const [isLoading, setLoading] = useState(enabled);
  const [error, setError] = useState<Error | null>(null);
  const key = queryKey.join("/");
  useEffect(() => {
    if (!enabled) return;
    let live = true;
    const load = (): void => { setLoading(true); queryFn().then(value => { if (live) { setData(value); setError(null); } }).catch(reason => { if (live) setError(reason instanceof Error ? reason : new Error("当前数据无法读取。")); }).finally(() => { if (live) setLoading(false); }); };
    const refresh = (event: Event): void => { if (event instanceof CustomEvent && (event.detail === key || event.detail === "*")) load(); };
    load(); window.addEventListener("diyu-refresh", refresh); return () => { live = false; window.removeEventListener("diyu-refresh", refresh); };
  }, [enabled, key]);
  return { data, isLoading, error };
}

function useMutation<T, V = void>({ mutationFn, onSuccess, onError }: { mutationFn: (value: V) => Promise<T>; onSuccess?: (value: T) => void; onError?: (error: Error) => void }): { mutate: (value: V) => void; isPending: boolean } {
  const [isPending, setPending] = useState(false);
  const mutate = (value: V): void => { setPending(true); mutationFn(value).then(value => onSuccess?.(value)).catch(reason => onError?.(reason instanceof Error ? reason : new Error("当前操作没有完成。"))).finally(() => setPending(false)); };
  return { mutate, isPending };
}

function useQueryClient(): { invalidateQueries: (value: { queryKey: QueryKey }) => void } {
  return { invalidateQueries: ({ queryKey }): void => { window.dispatchEvent(new CustomEvent("diyu-refresh", { detail: queryKey.join("/") })); } };
}

function useLocation(): { pathname: string } { return { pathname: window.location.pathname }; }
function Link({ to, className, children }: { to: string; className?: string; children: ReactNode }): JSX.Element { return <a href={to} className={className}>{children}</a>; }

// A temporary preference-free session declares itself on every request it makes, so the catalog,
// the opportunities, generation and revision all stop reading or writing the private preference.
let preferenceSession: "normal" | "bypass" = "normal";

function setPreferenceSession(value: "normal" | "bypass"): void {
  preferenceSession = value;
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(preferenceSession === "bypass" ? { "X-Diyu-Preference-Session": "bypass" } : {}),
      ...init?.headers
    },
    ...init
  });
  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => ({}));
    const detail = typeof payload === "object" && payload !== null && "detail" in payload ? String(payload.detail) : "当前操作没有完成，请稍后重试。";
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

function fileBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("无法读取素材原件。"));
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1] ?? "");
    reader.readAsDataURL(file);
  });
}

function App(): JSX.Element {
  const location = useLocation();
  const bootstrap = window.__DIYU_BOOTSTRAP__;
  const isEntry = location.pathname === "/";
  const { data: context } = useQuery({
    queryKey: ["session-context"],
    queryFn: () => api<Context>("/api/v1/session/context"),
    enabled: !isEntry && bootstrap !== null
  });
  if (isEntry || bootstrap === null) return <Entry />;
  if (!context) return <Loading label="正在确认当前工作身份……" />;
  if (location.pathname.startsWith("/tenant-admin")) return <TenantManagementShell context={context}><AdminWorkspace context={context} /></TenantManagementShell>;
  if (location.pathname.startsWith("/user")) return <UserPortal context={context} />;
  if (location.pathname.startsWith("/display")) return <WorkbenchShell context={context}><DisplayWorkbench context={context} /></WorkbenchShell>;
  return <WorkbenchShell context={context}><ContentWorkbench context={context} /></WorkbenchShell>;
}

function Entry(): JSX.Element {
  return <main className="entry-page">
    <header className="entry-brand"><img src="/assets/diyu-logo-horizontal.svg" alt="笛语" /></header>
    <section className="entry-copy"><p className="eyebrow">笛语</p><h1>进入你有资格使用的工作空间。</h1><p>租户用户工作和租户管理分别使用独立入口与独立导航。</p></section>
    <section className="entry-choices" aria-label="选择入口">
      <a href="/ui/select/user" className="entry-choice"><span>业务工作</span><strong>租户用户入口</strong><small>进入后再选择内容生产或陈列搭配。</small></a>
      <a href="/ui/select/admin" className="entry-choice"><span>当前租户</span><strong>租户管理入口</strong><small>维护入驻、企业发布账号与已登记操作人。</small></a>
    </section>
  </main>;
}

function UserPortal({ context }: { context: Context }): JSX.Element {
  const identity = context.identity;
  const [name, setName] = useState(identity.default_persona ?? "");
  const [boundary, setBoundary] = useState(identity.persona_boundary ?? "");
  const [notice, setNotice] = useState<string | null>(null);
  const persona = useMutation({ mutationFn: () => api<{ version: number }>("/api/v1/user/default-persona", { method: "POST", body: JSON.stringify({ name, boundary }) }), onSuccess: value => setNotice(`本人默认表达人设已更新为 V${value.version}。`), onError: error => setNotice(error.message) });
  const contentEntry = context.formal_runtime ? "/content" : "/ui/select/content";
  const displayEntry = context.formal_runtime ? "/display" : "/ui/select/display";
  return <main className="entry-page user-portal">
    <header className="entry-brand"><img src="/assets/diyu-logo-horizontal.svg" alt="笛语" /></header>
    <section className="entry-copy"><p className="eyebrow">租户用户工作台</p><h1>{identity.operator}，今天要完成什么？</h1><p>这里不显示租户管理页面或导航；业务工作只使用当前自然人已获授权的身份。</p></section>
    {notice && <Notice value={notice} onDismiss={() => setNotice(null)} />}
    <section className="entry-choices" aria-label="选择业务应用">
      <a href={contentEntry} className="entry-choice"><span>对外</span><strong>内容生产</strong><small>把判断整理成可直接制作与发布的成品。</small></a>
      <a href={displayEntry} className="entry-choice"><span>对内</span><strong>陈列搭配</strong><small>把本次库存整理成墙面双层挂杆参考执行方案。</small></a>
    </section>
    <form className="persona-card" onSubmit={event => { event.preventDefault(); persona.mutate(); }}><p className="eyebrow">本人默认表达人设</p><p>每个自然人只有这一份可维护的人设；它不等于企业发布账号的表达身份。</p><input value={name} onChange={event => setName(event.target.value)} maxLength={80} aria-label="本人默认表达人设名称" /><textarea value={boundary} onChange={event => setBoundary(event.target.value)} maxLength={500} aria-label="本人默认表达人设边界" /><button className="primary" disabled={persona.isPending}>{persona.isPending ? "正在保存……" : "更新我的默认人设"}</button></form>
    <PreferenceCard />
  </main>;
}

function TenantManagementShell({ context, children }: { context: Context; children: ReactNode }): JSX.Element {
  const identity = context.identity;
  return <div className="app-frame management-frame"><header className="topbar"><span className="wordmark"><img src="/assets/diyu-logo-horizontal.svg" alt="笛语" /></span><p className="management-title">租户管理</p><details className="identity-bar"><summary><span>{identity.operator}</span><span className="identity-org">· {identity.organization}</span></summary><dl><div><dt>代表组织</dt><dd>{identity.organization}</dd></div><div><dt>当前范围</dt><dd>{identity.brand}</dd></div></dl></details></header><div className="application-body">{children}</div></div>;
}

function WorkbenchShell({ context, children }: { context: Context; children: ReactNode }): JSX.Element {
  const location = useLocation();
  const contentActive = location.pathname.startsWith("/content");
  const displayActive = location.pathname.startsWith("/display");
  const identity = context.identity;
  const contentEntry = context.formal_runtime ? "/content" : "/ui/select/content";
  const displayEntry = context.formal_runtime ? "/display" : "/ui/select/display";
  const expression = useQuery({
    queryKey: ["account-expression"],
    queryFn: () => api<AccountExpression>("/api/v1/content/account-expression-profile"),
    enabled: context.application === "content"
  });
  const profile = expression.data?.current;
  return <div className="app-frame">
    <header className="topbar">
      <Link className="wordmark" to="/user"><img src="/assets/diyu-logo-horizontal.svg" alt="笛语" /></Link>
      <nav className="app-switcher" aria-label="工作域">
        <a className={contentActive ? "active" : ""} aria-current={contentActive ? "page" : undefined} href={contentEntry}>内容生产</a>
        <a className={displayActive ? "active" : ""} aria-current={displayActive ? "page" : undefined} href={displayEntry}>陈列搭配</a>
      </nav>
      <details className="identity-bar"><summary><span>{identity.operator}</span><span className="identity-org">· {identity.organization}</span></summary><dl>
        <div><dt>代表组织</dt><dd>{identity.organization}</dd></div>
        <div><dt>{context.application === "content" ? "发布账号" : "当前门店"}</dt><dd>{context.application === "content" ? identity.account : identity.store}</dd></div>
        {context.application === "content" && <div><dt>表达身份</dt><dd>{identity.content_role}</dd></div>}
        {context.application === "content" && <div><dt>账号画像</dt><dd>{profile ? `当前 V${profile.version} · ${profile.identity_position.slice(0, 60)}${profile.identity_position.length > 60 ? "……" : ""}` : "还没有保存过版本；可在「账号画像」里先看草案。"}<button type="button" className="ghost" onClick={() => window.dispatchEvent(new CustomEvent("diyu-open-surface", { detail: "profile" }))}>去看这张画像</button></dd></div>}
      </dl></details>
    </header>
    {context.application === "content" && identity.business_data_kind === "synthetic_business_fixture" && <div className="notice" role="status"><strong>等深模拟业务资料</strong>：这里的组织、表达身份、商品和内容是生产验收夹具，不代表真实员工、真实在售商品或真实经营记录。</div>}
    <div className="application-body">{children}</div>
  </div>;
}

function ContentWorkbench({ context }: { context: Context }): JSX.Element {
  const client = useQueryClient();
  const [artifact, setArtifact] = useState<ContentVersion | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [mobileView, setMobileView] = useState<"conversation" | "artifact">("conversation");
  const [surface, setSurface] = useState<"compose" | "series" | "materials" | "profile" | "plan">("compose");
  // The whole composing state lives here so a failed request never loses the person's input.
  const [seed, setSeed] = useState("");
  const [target, setTarget] = useState<Target>(context.targets?.[0]?.value ?? "douyin_video");
  const [selections, setSelections] = useState<Record<string, string>>({});
  const [clearedAxes, setClearedAxes] = useState<string[]>([]);
  const [customText, setCustomText] = useState("");
  const [noPreferenceSession, setNoPreferenceSession] = useState(false);
  const [materialIds, setMaterialIds] = useState<string[]>([]);
  const [seriesId, setSeriesId] = useState("");
  const [seriesPosition, setSeriesPosition] = useState("");
  const recent = useQuery({
    queryKey: ["content-recent", ...(context.targets?.map(item => item.value) ?? [])],
    queryFn: async () => {
      const targetValues = context.targets?.map(item => item.value) ?? ["douyin_video"];
      const batches = await Promise.all(
        targetValues.map(value => api<RecentItem[]>(`/api/v1/content/tasks?target=${value}`))
      );
      return Array.from(
        new Map(batches.flat().map(item => [item.task_id, item])).values()
      ).sort((left, right) => right.updated_at.localeCompare(left.updated_at));
    }
  });
  const series = useQuery({ queryKey: ["series"], queryFn: () => api<Series[]>("/api/v1/content/series") });
  const catalog = useQuery({ queryKey: ["expression-catalog"], queryFn: () => api<ExpressionCatalog>("/api/v1/content/expression-catalog") });
  const materials = useQuery({ queryKey: ["materials"], queryFn: () => api<Material[]>("/api/v1/materials") });
  const opportunities = useQuery({ queryKey: ["opportunities"], queryFn: () => api<OpportunityList>("/api/v1/content/opportunities", { method: "POST" }) });
  // In a preference-free session the private preference is not read at all, here included.
  const preference = useQuery({ queryKey: ["creation-preference"], queryFn: () => api<CreationPreference>("/api/v1/user/creation-preferences"), enabled: !noPreferenceSession });
  useEffect(() => {
    const open = (event: Event): void => { if (event instanceof CustomEvent && typeof event.detail === "string") setSurface(event.detail as typeof surface); };
    window.addEventListener("diyu-open-surface", open);
    return () => window.removeEventListener("diyu-open-surface", open);
  }, []);
  const create = useMutation({
    mutationFn: () => api<ContentVersion | { kind: string; message: string }>("/api/v1/content", {
      method: "POST",
      body: JSON.stringify({
        weak_seed: seed.trim(),
        target,
        creative_direction: {
          catalog_version: catalog.data?.catalog_version ?? null,
          selections,
          cleared_axes: clearedAxes,
          custom_text: customText.trim(),
          body_related_opt_in: catalog.data?.body_related_enabled ?? false
        },
        use_personal_preferences: !noPreferenceSession,
        material_ids: materialIds,
        series_id: seriesId || null,
        series_position: seriesPosition ? Number(seriesPosition) : null
      })
    }),
    onSuccess: payload => {
      if ("task_id" in payload) { setArtifact(payload); setMobileView("artifact"); setNotice(null); client.invalidateQueries({ queryKey: ["content-recent"] }); client.invalidateQueries({ queryKey: ["series"] }); }
      else setNotice(payload.message);
    },
    onError: error => setNotice(error.message)
  });
  const appliedDefaults = catalog.data?.saved_defaults ?? {};
  const saveDefaults = useMutation({
    // Only the axis defaults change here; the note you wrote in your own entry is left alone.
    // What gets saved is what is actually steering this task — a saved default you did not touch
    // stays saved, and an axis you switched off for this task is the one that is dropped.
    mutationFn: () => {
      const effective: Record<string, string> = {};
      Object.entries(appliedDefaults).forEach(([axis, value]) => { if (!clearedAxes.includes(axis)) effective[axis] = value; });
      Object.entries(selections).forEach(([axis, value]) => { effective[axis] = value; });
      return api<CreationPreference>("/api/v1/user/creation-preferences", {
        method: "PUT",
        body: JSON.stringify({ enabled: true, direction_defaults: effective, clear_direction_defaults: Object.keys(effective).length === 0, collaboration_note: preference.data?.collaboration_note ?? "", body_related_opt_in: preference.data?.body_related_opt_in ?? false })
      });
    },
    onSuccess: value => { client.invalidateQueries({ queryKey: ["creation-preference"] }); client.invalidateQueries({ queryKey: ["expression-catalog"] }); setNotice(`以后会优先按这个方向帮你（第 ${value.version} 版偏好），你写过的偏好说明没有变。随时可以关闭或删除。`); },
    onError: error => setNotice(error.message)
  });
  const open = async (item: RecentItem): Promise<void> => {
    try { setArtifact(await api<ContentVersion>(`/api/v1/tasks/${item.task_id}/versions/${item.version}?target=${item.target ?? "douyin_video"}`)); setMobileView("artifact"); }
    catch (error) { setNotice(error instanceof Error ? error.message : "无法读取这份成品。"); }
  };
  const surfaces: Array<[typeof surface, string]> = [["compose", "开始一条内容"], ["series", "连续系列"], ["materials", "我的素材"], ["profile", "账号画像"], ["plan", "内容计划"]];
  const sidebar = <aside className="sidebar"><p className="sidebar-label">内容生产</p><nav aria-label="内容生产工作面">{surfaces.map(([key, label]) => <button key={key} type="button" aria-current={surface === key ? "page" : undefined} className={surface === key ? "active" : ""} onClick={() => setSurface(key)}>{label}</button>)}</nav><p className="sidebar-label">最近成品</p><RecentList items={recent.data ?? []} loading={recent.isLoading} onOpen={open} /></aside>;
  const startFromPlan = (item: PlanItem): void => {
    // Only the title, the note and the direction come back to the natural input area.  Nothing
    // is created until the person presses 生成当前成品 themself.
    setSeed([item.title, item.note].filter(value => value.trim()).join("\n"));
    setSelections(item.selections ?? {});
    setClearedAxes([]);
    setSurface("compose");
    setNotice("已经把这条计划带回输入区，你可以改完再生成。现在还没有创建任何任务。");
  };
  if (surface !== "compose") {
    return <section className="workbench content-workbench">{sidebar}<main className="admin-main">
      {surface === "series" && <SeriesPanel onContinue={(selectedSeries, position) => { setSeriesId(selectedSeries.id); setSeriesPosition(position ? String(position) : ""); setSeed(`接着《${selectedSeries.title}》做下一篇。`); setSurface("compose"); setNotice(position ? `已经选中《${selectedSeries.title}》的第 ${position} 个位置；你可以继续补充这篇要说什么。` : `已经选中《${selectedSeries.title}》；生成成功后会接到当前最后一篇后面。`); }} />}
      {surface === "materials" && <MaterialsPanel />}
      {surface === "profile" && <AccountProfilePanel />}
      {surface === "plan" && <PlanPanel onStart={startFromPlan} />}
    </main></section>;
  }
  return <section className="workbench content-workbench">
    {sidebar}
    <main className={`conversation-pane ${mobileView === "artifact" ? "mobile-hidden" : ""}`} id="compose">
      <div className="pane-heading"><p className="eyebrow">内容生产</p><h1>自然说清这次想完成什么。</h1><p>系统只会使用当前账号可代表的品牌与发布范围。</p></div>
      {context.generator_mode === "stub" && <p className="mode-note">本地确定性测试模式：不冒充真实模型调用。</p>}
      {notice && <Notice value={notice} onDismiss={() => setNotice(null)} />}
      <ContentComposer
        targets={context.targets ?? []}
        busy={create.isPending}
        seed={seed}
        onSeed={setSeed}
        target={target}
        onTarget={setTarget}
        onSubmit={() => { if (seed.trim()) create.mutate(); }}
        series={series.data ?? []}
        seriesId={seriesId}
        onSeriesId={value => { setSeriesId(value); setSeriesPosition(""); }}
        seriesPosition={seriesPosition}
        onSeriesPosition={setSeriesPosition}
      >
        <DirectionPanel
          catalog={catalog.data}
          selections={selections}
          clearedAxes={clearedAxes}
          savedDefaults={appliedDefaults}
          onSelect={(axis, value) => { setSelections(current => { const next = { ...current }; if (value) next[axis] = value; else delete next[axis]; return next; }); setClearedAxes(current => current.filter(item => item !== axis)); }}
          onClear={axis => { setSelections(current => { const next = { ...current }; delete next[axis]; return next; }); setClearedAxes(current => current.includes(axis) ? current.filter(item => item !== axis) : [...current, axis]); }}
          customText={customText}
          onCustomText={setCustomText}
          noPreferenceSession={noPreferenceSession}
          onNoPreferenceSession={value => { setNoPreferenceSession(value); setPreferenceSession(value ? "bypass" : "normal"); client.invalidateQueries({ queryKey: ["expression-catalog"] }); client.invalidateQueries({ queryKey: ["opportunities"] }); }}
          materials={materials.data ?? []}
          materialIds={materialIds}
          onMaterialIds={setMaterialIds}
          onNotice={setNotice}
          onSaveDefaults={() => saveDefaults.mutate()}
          savingDefaults={saveDefaults.isPending}
        />
      </ContentComposer>
      <OpportunityBoard
        data={opportunities.data}
        loading={opportunities.isLoading}
        onPick={item => { setSeed(item.seed_text); setSelections(item.selections); setClearedAxes([]); setMaterialIds(item.material_ids); setNotice(null); }}
        onRefresh={() => client.invalidateQueries({ queryKey: ["opportunities"] })}
      />
      <UnmetRequestForm selections={selections} customText={customText} onNotice={setNotice} />
    </main>
    <ArtifactPane mobileView={mobileView} onShowConversation={() => setMobileView("conversation")} artifact={artifact} onArtifact={setArtifact} onNotice={setNotice} context={context} />
    <MobileTabs first="对话" second="成品" value={mobileView} onChange={setMobileView} />
  </section>;
}

function ContentComposer({ targets, busy, seed, onSeed, target, onTarget, onSubmit, series, seriesId, onSeriesId, seriesPosition, onSeriesPosition, children }: { targets: Array<{ value: Target; label: string }>; busy: boolean; seed: string; onSeed: (value: string) => void; target: Target; onTarget: (value: Target) => void; onSubmit: () => void; series: Series[]; seriesId: string; onSeriesId: (value: string) => void; seriesPosition: string; onSeriesPosition: (value: string) => void; children: ReactNode }): JSX.Element {
  const submit = (event: FormEvent): void => { event.preventDefault(); onSubmit(); };
  return <form className="composer" onSubmit={submit}><label>这次要做成<select value={target} onChange={event => onTarget(event.target.value as Target)}>{targets.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label><textarea value={seed} onChange={event => onSeed(event.target.value)} maxLength={1000} placeholder="例如：我想把一件衣服的取舍说清楚，别只讲卖点。" aria-label="内容需求" />{series.length > 0 && <div className="series-compose"><label>放进连续系列<select value={seriesId} onChange={event => onSeriesId(event.target.value)}><option value="">这次不承接系列</option>{series.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label>{seriesId && <label>放在第几篇<input type="number" min={1} max={999} value={seriesPosition} onChange={event => onSeriesPosition(event.target.value)} placeholder="留空就是接着下一篇" aria-label="系列位置" /></label>}<small>{seriesId ? "留空会接到最后；也可以跳到第 5 篇或指定中间位置。只有生成成功才会写入系列。" : "普通生成、阅读、复制和导出都不会改变系列。"}</small></div>}{children}<div className="composer-foot"><span>不需要填写表单；必要时只追问一个会改变成品的问题。</span><button className="primary" disabled={busy}>{busy ? "正在整理成品……" : "生成当前成品"}</button></div></form>;
}

type AxisState = "explicit" | "default" | "cleared" | "unset";

function DirectionPanel({ catalog, selections, clearedAxes, savedDefaults, onSelect, onClear, customText, onCustomText, noPreferenceSession, onNoPreferenceSession, materials, materialIds, onMaterialIds, onNotice, onSaveDefaults, savingDefaults }: { catalog: ExpressionCatalog | undefined; selections: Record<string, string>; clearedAxes: string[]; savedDefaults: Record<string, string>; onSelect: (axis: string, value: string) => void; onClear: (axis: string) => void; customText: string; onCustomText: (value: string) => void; noPreferenceSession: boolean; onNoPreferenceSession: (value: boolean) => void; materials: Material[]; materialIds: string[]; onMaterialIds: (value: string[]) => void; onNotice: (value: string) => void; onSaveDefaults: () => void; savingDefaults: boolean }): JSX.Element {
  // Three states per axis, kept apart on purpose: chosen for this task, carried over from a
  // saved default, or switched off this time.  Carrying a default over is never shown as 不指定.
  const stateOf = (axis: CatalogAxis): AxisState => {
    if (selections[axis.key]) return "explicit";
    if (clearedAxes.includes(axis.key)) return "cleared";
    return savedDefaults[axis.key] ? "default" : "unset";
  };
  const optionOf = (axis: CatalogAxis, state: AxisState): CatalogOption | undefined =>
    axis.options.find(item => item.stable_id === (state === "explicit" ? selections[axis.key] : savedDefaults[axis.key]));
  const chosen = (catalog?.axes ?? []).flatMap(axis => {
    const state = stateOf(axis);
    if (state === "cleared") return [`${axis.label}：本次不使用`];
    const option = optionOf(axis, state);
    if (!option || state === "unset") return [];
    return [state === "default" ? `${option.label}（沿用你保存的默认）` : option.label];
  });
  const summary = chosen.join("、") || "不指定也可以，直接自然说就行";
  return <details className="direction-panel">
    <summary><span className="direction-title">创作方向（可选）</span><span className="direction-summary">{summary}</span></summary>
    <div className="direction-body">
      {(catalog?.axes ?? []).map(axis => {
        const state = stateOf(axis);
        const savedOption = axis.options.find(item => item.stable_id === savedDefaults[axis.key]);
        return <div className="direction-row" key={axis.key}>
          <span className="direction-axis">{axis.label}<small>{axis.question}</small></span>
          <div className="direction-options" role="group" aria-label={`${axis.label}：${axis.question}`}>
            {savedOption
              ? <button type="button" aria-pressed={state === "cleared"} className={state === "cleared" ? "active" : ""} onClick={() => onClear(axis.key)}>{state === "cleared" ? `恢复默认：${savedOption.label}` : `本次不用默认：${savedOption.label}`}</button>
              : <button type="button" aria-pressed={state === "unset"} className={state === "unset" ? "active" : ""} onClick={() => onSelect(axis.key, "")}>不指定</button>}
            {axis.options.map(option => <button key={option.stable_id} type="button" aria-pressed={selections[axis.key] === option.stable_id} className={selections[axis.key] === option.stable_id ? "active" : ""} onClick={() => onSelect(axis.key, selections[axis.key] === option.stable_id ? "" : option.stable_id)}>{option.label}</button>)}
            {state === "default" && savedOption && <span className="direction-default">这一轴沿用你保存的默认：{savedOption.label}</span>}
            {state === "cleared" && <span className="direction-default">这一轴本次不使用</span>}
          </div>
        </div>;
      })}
      <label className="direction-custom">还想补一句就写在这里<textarea value={customText} onChange={event => onCustomText(event.target.value)} maxLength={500} /></label>
      <ReferencePicker materials={materials} materialIds={materialIds} onMaterialIds={onMaterialIds} onNotice={onNotice} />
      <div className="direction-foot">
        <label className="minor-check"><input type="checkbox" checked={noPreferenceSession} onChange={event => onNoPreferenceSession(event.target.checked)} />临时不读取也不写入我的私人偏好</label>
        {!noPreferenceSession && <button type="button" onClick={onSaveDefaults} disabled={savingDefaults}>{savingDefaults ? "正在保存……" : "以后优先这样帮我"}</button>}
      </div>
      <p className="muted">{noPreferenceSession ? "现在是临时无偏好会话：目录、可以这样开始、生成和修改都不读也不写你的私人偏好，「我的」入口在这期间也不打开。取消勾选就恢复。" : "这里选的只用于这一次。只有你点上面那个按钮，才会存成以后的默认；生成本身从不改你的偏好。体型相关的方向默认不显示，要用可以在「我的」入口自己打开。"}</p>
    </div>
  </details>;
}

function ReferencePicker({ materials, materialIds, onMaterialIds, onNotice }: { materials: Material[]; materialIds: string[]; onMaterialIds: (value: string[]) => void; onNotice: (value: string) => void }): JSX.Element {
  const client = useQueryClient();
  const [writing, setWriting] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const toggle = (id: string): void => onMaterialIds(materialIds.includes(id) ? materialIds.filter(item => item !== id) : [...materialIds, id]);
  const save = useMutation({
    mutationFn: (value: { id: string; note: string }) => api<Material>(`/api/v1/materials/${value.id}/reference-note`, { method: "PATCH", body: JSON.stringify({ reference_note: value.note }) }),
    onSuccess: () => { setWriting(null); setNote(""); client.invalidateQueries({ queryKey: ["materials"] }); onNotice("已经记下你写的原件说明，现在可以把它选进这次参考了。"); },
    onError: error => onNotice(error.message)
  });
  const usable = (item: Material): boolean => item.media_type === "text" || Boolean(item.reference_note);
  return <fieldset className="reference-picker">
    <legend>这次参考（可选）</legend>
    <p className="muted">只使用你在这里勾选的文字素材，或你自己给图片、视频原件写下的说明；系统不会去看原件画面。</p>
    {materials.length === 0
      ? <p className="empty-inline">还没有可以参考的素材。可以先去「我的素材」保存一份。</p>
      : <ul>{materials.map(item => <li key={item.id}>
        <label><input type="checkbox" checked={materialIds.includes(item.id)} disabled={!usable(item)} onChange={() => toggle(item.id)} /><strong>{item.title}</strong><span>{item.media_type === "text" ? "文字素材" : item.reference_note ? "已写原件说明" : "还没写说明，先补一句才能选"}</span></label>
        {!usable(item) && (writing === item.id
          ? <span className="reference-note-form"><input value={note} maxLength={500} aria-label={`给《${item.title}》补一句说明`} placeholder="这份原件里有什么可以参考？" onChange={event => setNote(event.target.value)} /><button type="button" disabled={save.isPending || note.trim().length < 2} onClick={() => save.mutate({ id: item.id, note: note.trim() })}>保存这句说明</button></span>
          : <button type="button" className="ghost" onClick={() => { setWriting(item.id); setNote(""); }}>先补一句说明</button>)}
      </li>)}</ul>}
  </fieldset>;
}

function OpportunityBoard({ data, loading, onPick, onRefresh }: { data: OpportunityList | undefined; loading: boolean; onPick: (item: Opportunity) => void; onRefresh: () => void }): JSX.Element {
  return <section className="starter-prompts">
    <h2>可以这样开始</h2>
    {loading && <p className="muted">正在看当前账号可以先做什么……</p>}
    {(data?.items ?? []).map(item => <button key={item.id} type="button" onClick={() => onPick(item)}><strong>{item.title}</strong><span>{item.why}</span></button>)}
    {data && <p className="muted">{data.boundary}{data.profile_is_draft ? " 当前账号画像还是草案，保存后建议会更贴合。" : ""}</p>}
    <button type="button" className="ghost" onClick={onRefresh}>重新读一遍</button>
  </section>;
}

function UnmetRequestForm({ selections, customText, onNotice }: { selections: Record<string, string>; customText: string; onNotice: (value: string) => void }): JSX.Element {
  const client = useQueryClient();
  const [text, setText] = useState("");
  const mine = useQuery({ queryKey: ["unmet-requests"], queryFn: () => api<UnmetRequest[]>("/api/v1/content/unmet-capability-requests") });
  const submit = useMutation({
    mutationFn: () => api<UnmetRequest>("/api/v1/content/unmet-capability-requests", { method: "POST", body: JSON.stringify({ request_text: text.trim(), creative_direction: { selections, custom_text: customText.trim() } }) }),
    onSuccess: () => { setText(""); client.invalidateQueries({ queryKey: ["unmet-requests"] }); onNotice("已经记下你的需求。它只是一条候选，不会改变目录、知识或你的偏好。"); },
    onError: error => onNotice(error.message)
  });
  return <details className="unmet-panel">
    <summary>没找到你想要的方向？</summary>
    <form onSubmit={event => { event.preventDefault(); if (text.trim().length >= 4) submit.mutate(); }}>
      <label>用你自己的话说清楚想做什么<textarea value={text} onChange={event => setText(event.target.value)} maxLength={1000} /></label>
      <button className="primary" disabled={submit.isPending}>{submit.isPending ? "正在记录……" : "提交这条需求"}</button>
    </form>
    {(mine.data ?? []).length > 0 && <ul className="unmet-list">{(mine.data ?? []).map(item => <li key={item.stable_request_id}><strong>{item.request_text}</strong><span>{item.status === "answered" ? item.response_text : "已登记，等待人工分类和回告"}</span></li>)}</ul>}
  </details>;
}

function ExpressionProfileCard({ heading, detail, data, saving, onSave }: { heading: string; detail: string; data: AccountExpression; saving: boolean; onSave: (values: Record<string, string>) => void }): JSX.Element {
  const base = data.current ?? data.draft ?? null;
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(SEGMENT_ORDER.map(key => [key, base ? String(base[key] ?? "") : ""]))
  );
  return <article className="expression-card profile-card">
    <div>
      <p className="eyebrow">{heading}</p>
      <h2>{data.account}</h2>
      <p>{detail}</p>
      <p className="muted">
        表达身份：{data.content_role}
        {data.control_organization ? ` · 控制组织：${data.control_organization}` : ""}
        {data.current ? ` · 当前 V${data.current.version}` : " · 还没有保存过版本，下面是可编辑草案"}
      </p>
      {!data.current && data.draft_source && <p className="muted">草案来源边界：{data.draft_source}</p>}
    </div>
    {SEGMENT_ORDER.map(key => <label key={key} className="profile-field">
      <span>{data.segment_labels[key] ?? key}</span>
      <textarea value={values[key] ?? ""} onChange={event => setValues(current => ({ ...current, [key]: event.target.value }))} maxLength={800} disabled={!data.can_maintain} />
    </label>)}
    <div className="expression-foot">
      <span>{data.can_maintain ? "保存后形成新版本，旧版本永久保留。" : "你现在只能查看这张画像；维护资格由账号控制组织决定。"}</span>
      {data.can_maintain && <button className="primary" disabled={saving} onClick={() => onSave(values)}>{saving ? "正在保存……" : "保存为当前版本"}</button>}
    </div>
  </article>;
}

function AccountProfilePanel(): JSX.Element {
  const client = useQueryClient();
  const [notice, setNotice] = useState<string | null>(null);
  const profile = useQuery({ queryKey: ["account-expression"], queryFn: () => api<AccountExpression>("/api/v1/content/account-expression-profile") });
  const save = useMutation({
    mutationFn: (values: Record<string, string>) => api<ExpressionSegments>("/api/v1/content/account-expression-profile/versions", { method: "POST", body: JSON.stringify(values) }),
    onSuccess: value => { client.invalidateQueries({ queryKey: ["account-expression"] }); setNotice(`已保存为当前版本 V${value.version}。旧版本仍然可读，历史成品继续引用它当时用的版本。`); },
    onError: error => setNotice(error.message)
  });
  return <>
    <header className="page-heading"><p className="eyebrow">账号画像</p><h1>这个账号从什么位置说话。</h1><p>五段人话，一次写清；它决定表达位置和资格边界，不决定这次讲什么题材。</p></header>
    {notice && <Notice value={notice} onDismiss={() => setNotice(null)} />}
    {profile.isLoading && <Loading label="正在读取账号画像……" />}
    {profile.data && <ExpressionProfileCard
      key={profile.data.current?.profile_id ?? "draft"}
      heading="当前发布账号"
      detail="题材、风格、时长和这次的人物、设备、素材都不写进这里。"
      data={profile.data}
      saving={save.isPending}
      onSave={values => save.mutate(values)}
    />}
  </>;
}

function PlanPanel({ onStart }: { onStart: (item: PlanItem) => void }): JSX.Element {
  const client = useQueryClient();
  const [notice, setNotice] = useState<string | null>(null);
  const plan = useQuery({ queryKey: ["content-plan"], queryFn: () => api<ContentPlan>("/api/v1/content/plan") });
  const [items, setItems] = useState<PlanItem[] | null>(null);
  const current = items ?? plan.data?.document.items ?? [];
  const save = useMutation({
    mutationFn: (next: PlanItem[]) => api<ContentPlan>("/api/v1/content/plan", { method: "PUT", body: JSON.stringify({ items: next }) }),
    onSuccess: value => { setItems(value.document.items); client.invalidateQueries({ queryKey: ["content-plan"] }); setNotice("计划已保存。它只是一份可改的清单，不会自动开工。"); },
    onError: error => setNotice(error.message)
  });
  return <>
    <header className="page-heading"><p className="eyebrow">内容计划</p><h1>先记下来，什么时候做由你决定。</h1><p>这里不排期、不提醒、不打分；「用这条开始」只是把它带回输入区，点「生成当前成品」才会真正开工。</p></header>
    {notice && <Notice value={notice} onDismiss={() => setNotice(null)} />}
    <section className="series-create">
      {current.map((item, index) => <div key={`${item.title}-${index}`} className="plan-row">
        <input value={item.title} maxLength={120} aria-label={`第 ${index + 1} 条计划标题`} onChange={event => setItems(current.map((entry, position) => position === index ? { ...entry, title: event.target.value } : entry))} />
        <input value={item.note} maxLength={500} aria-label={`第 ${index + 1} 条计划备注`} placeholder="备注（可选）" onChange={event => setItems(current.map((entry, position) => position === index ? { ...entry, note: event.target.value } : entry))} />
        <button type="button" disabled={!item.title.trim()} onClick={() => onStart(item)}>用这条开始</button>
        <button type="button" onClick={() => setItems(current.filter((_, position) => position !== index))}>删除</button>
      </div>)}
      {current.length === 0 && <p className="empty-inline">还没有计划项。</p>}
      <div className="plan-actions">
        <button type="button" disabled={current.length >= 20} onClick={() => setItems([...current, { title: "", note: "", selections: {} }])}>新增一条</button>
        <button className="primary" disabled={save.isPending} onClick={() => save.mutate(current.filter(item => item.title.trim()))}>{save.isPending ? "正在保存……" : "保存计划"}</button>
      </div>
    </section>
  </>;
}

function PreferenceCard(): JSX.Element {
  const client = useQueryClient();
  const [notice, setNotice] = useState<string | null>(null);
  const preference = useQuery({ queryKey: ["creation-preference"], queryFn: () => api<CreationPreference>("/api/v1/user/creation-preferences") });
  const [note, setNote] = useState<string | null>(null);
  const value = preference.data;
  const write = useMutation({
    mutationFn: (payload: Record<string, unknown>) => api<CreationPreference>("/api/v1/user/creation-preferences", { method: "PUT", body: JSON.stringify(payload) }),
    onSuccess: () => { client.invalidateQueries({ queryKey: ["creation-preference"] }); setNote(null); setNotice("已更新你的私人创作偏好。"); },
    onError: error => setNotice(error.message)
  });
  const remove = useMutation({
    mutationFn: () => api<{ message: string }>("/api/v1/user/creation-preferences", { method: "DELETE" }),
    onSuccess: result => { client.invalidateQueries({ queryKey: ["creation-preference"] }); setNote(null); setNotice(result.message); },
    onError: error => setNotice(error.message)
  });
  if (!value) return <Loading label="正在读取你的私人创作偏好……" />;
  const body = note ?? value.collaboration_note;
  return <section className="persona-card">
    <p className="eyebrow">我的私人创作偏好</p>
    <p>只有你自己能看和改。它不进入企业账号画像、系列、正式知识或业务留痕；关闭或删除都不会影响已有成品。</p>
    {notice && <Notice value={notice} onDismiss={() => setNotice(null)} />}
    <p className="muted">{value.exists ? `第 ${value.version} 版 · ${value.enabled ? "正在使用" : "已关闭"}` : "还没有保存过；每次面板选择默认只用于这一次。"}</p>
    <textarea value={body} maxLength={500} aria-label="私人创作偏好说明" onChange={event => setNote(event.target.value)} />
    <label className="minor-check"><input type="checkbox" checked={value.body_related_opt_in} onChange={event => write.mutate({ enabled: value.enabled, direction_defaults: value.direction_defaults, collaboration_note: body, body_related_opt_in: event.target.checked })} />显示体型相关的创作方向（默认不显示）</label>
    <div className="plan-actions">
      <button type="button" disabled={write.isPending} onClick={() => write.mutate({ enabled: true, direction_defaults: value.direction_defaults, collaboration_note: body, body_related_opt_in: value.body_related_opt_in })}>{value.enabled ? "保存修改" : "恢复使用"}</button>
      <button type="button" disabled={write.isPending || !value.exists || !value.enabled} onClick={() => write.mutate({ enabled: false, direction_defaults: value.direction_defaults, collaboration_note: body, body_related_opt_in: value.body_related_opt_in })}>先关闭</button>
      <button type="button" disabled={remove.isPending || !value.exists} onClick={() => { if (window.confirm("删除后找不回来。系列、成品和账号画像都不会受影响。")) remove.mutate(); }}>删除</button>
    </div>
  </section>;
}

function AdminAccountExpression({ accountId }: { accountId: string }): JSX.Element {
  const client = useQueryClient();
  const [notice, setNotice] = useState<string | null>(null);
  const profile = useQuery({ queryKey: ["management-expression", accountId], queryFn: () => api<AccountExpression>(`/api/v1/tenant-management/publishing-accounts/${accountId}/expression-profile`) });
  const save = useMutation({
    mutationFn: (values: Record<string, string>) => api<ExpressionSegments>(`/api/v1/tenant-management/publishing-accounts/${accountId}/expression-profile/versions`, { method: "POST", body: JSON.stringify(values) }),
    onSuccess: value => { client.invalidateQueries({ queryKey: ["management-expression", accountId] }); setNotice(`已保存为当前版本 V${value.version}。`); },
    onError: error => setNotice(error.message)
  });
  if (!profile.data) return <p className="muted">正在读取这个账号的表达画像……</p>;
  return <details className="admin-expression">
    <summary>{profile.data.current ? `表达画像 · 当前 V${profile.data.current.version}` : "表达画像 · 还没有保存过版本"}</summary>
    {notice && <Notice value={notice} onDismiss={() => setNotice(null)} />}
    <ControlOrganizationCard accountId={accountId} data={profile.data} onNotice={setNotice} />
    <ExpressionProfileCard
      key={profile.data.current?.profile_id ?? `draft-${accountId}`}
      heading="本组织控制的发布账号"
      detail="只有账号控制组织里的有权主体可以保存版本；账号使用资格不等于画像维护资格。"
      data={profile.data}
      saving={save.isPending}
      onSave={values => save.mutate(values)}
    />
  </details>;
}

function ControlOrganizationCard({ accountId, data, onNotice }: { accountId: string; data: AccountExpression; onNotice: (value: string) => void }): JSX.Element {
  const client = useQueryClient();
  const [organizationId, setOrganizationId] = useState("");
  const organizations = useQuery({ queryKey: ["control-organizations"], queryFn: () => api<TenantOrganization[]>("/api/v1/tenant-management/control-organizations"), enabled: data.can_declare === true });
  useEffect(() => {
    if (organizationId || !data.control_organization || !organizations.data) return;
    const inferred = organizations.data.find(item => item.name === data.control_organization);
    if (inferred) setOrganizationId(inferred.id);
  }, [data.control_organization, organizationId, organizations.data]);
  const declare = useMutation({
    mutationFn: () => api<{ control_organization: string }>(`/api/v1/tenant-management/publishing-accounts/${accountId}/control-organization`, { method: "POST", body: JSON.stringify({ organization_id: organizationId }) }),
    onSuccess: value => { client.invalidateQueries({ queryKey: ["management-expression", accountId] }); onNotice(`已声明由「${value.control_organization}」控制这个账号。只有这一步成立，画像才有人可以维护。`); },
    onError: error => onNotice(error.message)
  });
  const source = data.control_organization_source ?? "unset";
  return <div className="control-organization">
    <p className="muted">
      控制组织：{data.control_organization || "还没有声明"}
      {source === "inferred" ? "（迁移时按创建事件推断，不作为依据；需要有权主体明确声明）" : source === "declared" ? "（已明确声明）" : ""}
    </p>
    {data.can_declare && <div className="plan-actions">
      <select value={organizationId} onChange={event => setOrganizationId(event.target.value)} aria-label="声明控制组织"><option value="">选择控制这个账号的组织</option>{organizations.data?.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select>
      <button type="button" disabled={!organizationId || declare.isPending} onClick={() => declare.mutate()}>{declare.isPending ? "正在声明……" : "声明控制组织"}</button>
    </div>}
  </div>;
}

function disclosureForTransfer(artifact: ContentVersion): string {
  if (!artifact.ai_generated || !artifact.aigc_label || !artifact.aigc_release_reminder) return artifact.body;
  return `${artifact.aigc_label}\n发布提醒：${artifact.aigc_release_reminder}\n\n${artifact.body}`;
}

function ArtifactPane({ artifact, onArtifact, onNotice, context, mobileView, onShowConversation }: { artifact: ContentVersion | null; onArtifact: (value: ContentVersion) => void; onNotice: (value: string) => void; context: Context; mobileView: "conversation" | "artifact"; onShowConversation: () => void }): JSX.Element {
  const client = useQueryClient();
  const [instruction, setInstruction] = useState("");
  const [platformTarget, setPlatformTarget] = useState<Target>("douyin_video");
  const versions = useQuery({ queryKey: ["content-versions", artifact?.task_id ?? "none", artifact?.target_key ?? "douyin_video"], queryFn: () => api<ContentHistoryVersion[]>(`/api/v1/content/tasks/${artifact?.task_id}/versions?target=${artifact?.target_key ?? "douyin_video"}`), enabled: artifact !== null });
  useEffect(() => { if (artifact?.target_key) setPlatformTarget(artifact.target_key); }, [artifact?.target_key]);
  const revise = useMutation({
    mutationFn: () => { const target = artifact?.target_key ?? "douyin_video"; return api<ContentVersion | { kind: string; message: string }>(`/api/v1/tasks/${artifact?.task_id}/revisions`, { method: "POST", body: JSON.stringify({ instruction, target, source_target: target }) }); },
    onSuccess: value => {
      // A task that froze no conditions answers with a question instead of a version.
      if (!("task_id" in value)) { onNotice(value.message); return; }
      onArtifact(value); setInstruction(""); client.invalidateQueries({ queryKey: ["content-recent"] }); client.invalidateQueries({ queryKey: ["content-versions", value.task_id] });
    },
    onError: error => onNotice(error.message)
  });
  const recompile = useMutation({
    mutationFn: () => {
      const sourceTarget = artifact?.target_key ?? "douyin_video";
      return api<ContentVersion>(`/api/v1/tasks/${artifact?.task_id}/revisions`, {
        method: "POST",
        body: JSON.stringify({
          instruction: "另做这个平台的版本：保留核心判断、已确认商品事实、账号身份、系列前情和主要受众价值，按目标平台重组标题、开头、结构、媒体组织与发布辅助信息。",
          target: platformTarget,
          source_target: sourceTarget
        })
      });
    },
    onSuccess: value => { onArtifact(value); client.invalidateQueries({ queryKey: ["content-recent"] }); onNotice("新的平台版本已经做好，源版本仍然保留。"); },
    onError: error => onNotice(error.message)
  });
  const copy = async (): Promise<void> => { if (!artifact) return; await navigator.clipboard.writeText(disclosureForTransfer(artifact)).catch(() => undefined); onNotice("已复制当前成品全文。"); };
  const exportText = (): void => { if (!artifact) return; const blob = new Blob([disclosureForTransfer(artifact)], { type: "text/plain;charset=utf-8" }); const url = URL.createObjectURL(blob); const anchor = document.createElement("a"); anchor.href = url; anchor.download = `笛语内容-V${artifact.version}.txt`; anchor.click(); URL.revokeObjectURL(url); };
  return <aside className={`artifact-pane ${mobileView === "conversation" ? "mobile-hidden" : ""}`} aria-live="polite">
    {!artifact ? <EmptyArtifact title="成品会出现在这里" detail="生成后可以完整阅读、继续修改、复制或导出。旧版本始终保留。" /> : <>
      <div className="artifact-header"><div><p className="eyebrow">当前成品 · V{artifact.version}</p>{artifact.translation_notice && <p className="translation-notice" role="note">{artifact.translation_notice}</p>}<h2>{artifact.outline}</h2>{artifact.ai_generated && artifact.aigc_label && artifact.aigc_release_reminder && <><p className="artifact-disclosure">{artifact.aigc_label}</p><p className="artifact-reminder">{artifact.aigc_release_reminder}</p></>}{artifact.adapted_from && <p className="muted">{artifact.adapted_from}</p>}</div><div className="artifact-actions"><button onClick={copy}>复制</button><button onClick={exportText}>导出</button></div></div>
      {(artifact.applied_direction ?? []).length > 0 && <p className="applied-direction">这一版实际按：{(artifact.applied_direction ?? []).join("、")}</p>}
      <ArtifactText value={artifact.body} />
      <VersionRail versions={versions.data ?? []} currentVersion={artifact.version} onSelect={value => onArtifact({ ...value, kind: "content" })} />
      <form className="revision-form" onSubmit={event => { event.preventDefault(); if (instruction.trim()) revise.mutate(); }}><label>继续改，只说这次要变什么<textarea value={instruction} onChange={event => setInstruction(event.target.value)} placeholder="例如：把结尾改短一点，其他不动。" maxLength={1000} /></label><button className="primary" disabled={revise.isPending}>{revise.isPending ? "正在生成新版本……" : `生成 V${artifact.version + 1}`}</button></form>
      {(context.targets ?? []).length > 1 && <div className="platform-recompile"><label>另做平台版本<select value={platformTarget} onChange={event => setPlatformTarget(event.target.value as Target)}>{(context.targets ?? []).map(item => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label><button type="button" disabled={platformTarget === (artifact.target_key ?? "douyin_video") || recompile.isPending} onClick={() => recompile.mutate()}>{recompile.isPending ? "正在重编译……" : "生成这个平台的版本"}</button><small>会保留当前源版本；目标平台、形式和本次适配条件会随新任务保留。</small></div>}
      <div className="artifact-boundary"><span>{context.identity.account}</span><span>旧版本不会被覆盖</span></div>
      <button className="mobile-back" onClick={onShowConversation}>继续改一条新内容</button>
    </>}
  </aside>;
}

function DisplayWorkbench({ context }: { context: Context }): JSX.Element {
  const client = useQueryClient();
  const [artifact, setArtifact] = useState<DisplayVersion | null>(null);
  const [inventory, setInventory] = useState("");
  const [feedback, setFeedback] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [mobileView, setMobileView] = useState<"conversation" | "artifact">("conversation");
  const recent = useQuery({ queryKey: ["display-recent"], queryFn: () => api<RecentItem[]>("/api/v1/display/tasks") });
  const versions = useQuery({ queryKey: ["display-versions", artifact?.task_id ?? "none"], queryFn: () => api<DisplayHistoryVersion[]>(`/api/v1/display/tasks/${artifact?.task_id}/versions`), enabled: artifact !== null });
  const create = useMutation({ mutationFn: () => api<DisplayVersion | { kind: string; message: string }>("/api/v1/display", { method: "POST", body: JSON.stringify({ inventory_text: inventory }) }), onSuccess: value => { if ("task_id" in value) { setArtifact(value); setMobileView("artifact"); client.invalidateQueries({ queryKey: ["display-recent"] }); } else setNotice(value.message); }, onError: error => setNotice(error.message) });
  const revise = useMutation({ mutationFn: () => api<DisplayVersion | { kind: string; message: string }>(`/api/v1/display-tasks/${artifact?.task_id}/revisions`, { method: "POST", body: JSON.stringify({ feedback }) }), onSuccess: value => { if ("task_id" in value) { setArtifact(value); setFeedback(""); client.invalidateQueries({ queryKey: ["display-recent"] }); client.invalidateQueries({ queryKey: ["display-versions", value.task_id] }); } else setNotice(value.message); }, onError: error => setNotice(error.message) });
  const open = async (item: RecentItem): Promise<void> => { try { setArtifact(await api<DisplayVersion>(`/api/v1/display-tasks/${item.task_id}/versions/${item.version}`)); setMobileView("artifact"); } catch (error) { setNotice(error instanceof Error ? error.message : "无法读取这份方案。"); } };
  return <section className="workbench display-workbench">
    <aside className="sidebar"><p className="sidebar-label">陈列搭配</p><nav><a href="#inventory" className="active">新建墙面方案</a><a href="#recent">历史方案</a></nav><p className="sidebar-label">最近方案</p><RecentList items={recent.data ?? []} loading={recent.isLoading} onOpen={open} /></aside>
    <main className={`conversation-pane ${mobileView === "artifact" ? "mobile-hidden" : ""}`} id="inventory"><div className="pane-heading"><p className="eyebrow">陈列搭配</p><h1>先把这组墙的库存说清楚。</h1><p>清单只用于本次参考方案，不会写回或核验库存账。</p></div>{notice && <Notice value={notice} onDismiss={() => setNotice(null)} />}<form className="composer" onSubmit={event => { event.preventDefault(); if (inventory.trim()) create.mutate(); }}><textarea value={inventory} onChange={event => setInventory(event.target.value)} placeholder="今天这组墙可用：商品编号 3 件、商品编号 2 件……" aria-label="本次库存" /><div className="composer-foot"><span>DM01 只使用本次库存、当前规则和双层挂杆条件。</span><button className="primary" disabled={create.isPending}>{create.isPending ? "正在整理方案……" : "生成墙面方案"}</button></div></form></main>
    <aside className={`artifact-pane ${mobileView === "conversation" ? "mobile-hidden" : ""}`}>{!artifact ? <EmptyArtifact title="方案会出现在这里" detail="生成后可以完整阅读，再用自然反馈只改受影响的搭配组。" /> : <><div className="artifact-header"><div><p className="eyebrow">墙面方案 · V{artifact.version}</p><h2>墙面挂杆参考执行方案</h2></div><button onClick={() => navigator.clipboard.writeText(artifact.body).then(() => setNotice("已复制当前方案。"))}>复制</button></div><ArtifactText value={artifact.body} /><VersionRail versions={versions.data ?? []} currentVersion={artifact.version} onSelect={setArtifact} /><form className="revision-form" onSubmit={event => { event.preventDefault(); if (feedback.trim()) revise.mutate(); }}><label>门店自然反馈<textarea value={feedback} onChange={event => setFeedback(event.target.value)} placeholder="例如：右侧两件外套太厚，挂不下。" /></label><button className="primary" disabled={revise.isPending}>{revise.isPending ? "正在生成新版……" : `生成 V${artifact.version + 1}`}</button></form><p className="artifact-boundary"><span>文字参考建议与摆放示意，不是门店实拍，也不表示现场已经执行。</span></p></>}</aside>
    <MobileTabs first="对话" second="方案" value={mobileView} onChange={setMobileView} />
  </section>;
}

function AdminWorkspace({ context }: { context: Context }): JSX.Element {
  const [section, setSection] = useState<"readiness" | "operators" | "products">("readiness");
  return <section className="admin-workspace"><aside className="sidebar"><p className="sidebar-label">租户管理</p><nav aria-label="租户管理工作面"><button type="button" aria-current={section === "readiness" ? "page" : undefined} className={section === "readiness" ? "active" : ""} onClick={() => setSection("readiness")}>入驻与就绪</button><button type="button" aria-current={section === "operators" ? "page" : undefined} className={section === "operators" ? "active" : ""} onClick={() => setSection("operators")}>账号与操作人</button><button type="button" aria-current={section === "products" ? "page" : undefined} className={section === "products" ? "active" : ""} onClick={() => setSection("products")}>本轮商品资料</button></nav></aside><main className="admin-main">{section === "readiness" && <ReadinessPanel />}{section === "operators" && <OperatorPanel formalRuntime={context.formal_runtime === true} brandName={context.identity.brand} />}{section === "products" && <ProductFactsPanel />}</main></section>;
}

function OperatorPanel({ formalRuntime, brandName }: { formalRuntime: boolean; brandName: string }): JSX.Element {
  const client = useQueryClient();
  const operators = useQuery({ queryKey: ["operators"], queryFn: () => api<Operator[]>("/api/v1/tenant-management/operators") });
  const accounts = useQuery({ queryKey: ["publishing-accounts"], queryFn: () => api<PublishingAccount[]>("/api/v1/tenant-management/publishing-accounts") });
  const organizations = useQuery({ queryKey: ["tenant-organizations"], queryFn: () => api<TenantOrganization[]>("/api/v1/tenant-management/organizations"), enabled: formalRuntime });
  const controlOrganizations = useQuery({ queryKey: ["control-organizations"], queryFn: () => api<TenantOrganization[]>("/api/v1/tenant-management/control-organizations") });
  const onboarding = useQuery({ queryKey: ["onboarding-prefill"], queryFn: () => api<OnboardingPrefill>("/api/v1/tenant-management/onboarding-prefill") });
  const isDiyuFashion = brandName === "笛语服饰";
  const [newAccountName, setNewAccountName] = useState(isDiyuFashion ? "笛语服饰品牌官方账号" : "");
  const [channel, setChannel] = useState<CreatePublishingAccount["channel"]>("抖音");
  const [contentRoleName, setContentRoleName] = useState(isDiyuFashion ? "品牌官方 / 品牌定义者" : "");
  const [voiceBoundary, setVoiceBoundary] = useState(isDiyuFashion ? "代表品牌讲已确认的品牌立场、生活关系和内容方向；不冒充创始人、研发、门店或顾客，不讲未确认商品和经营事实。" : "");
  const [operatorId, setOperatorId] = useState("");
  const [controlOrganizationId, setControlOrganizationId] = useState("");
  const [operatorMaintainsProfile, setOperatorMaintainsProfile] = useState(false);
  const [carrierSourceId, setCarrierSourceId] = useState("");
  const [carrierName, setCarrierName] = useState("");
  const [carrierChannel, setCarrierChannel] = useState<CreatePublishingAccount["channel"]>("小红书");
  const [carrierOperatorId, setCarrierOperatorId] = useState("");
  const [didAutoLoadCarrier, setDidAutoLoadCarrier] = useState(false);
  const [displayName, setDisplayName] = useState("");
  const [accountId, setAccountId] = useState("");
  const [formalName, setFormalName] = useState("");
  const [formalUsername, setFormalUsername] = useState("");
  const [formalOrganizationId, setFormalOrganizationId] = useState("");
  const [formalAccountId, setFormalAccountId] = useState("");
  const [formalGrantsMaterialMaintenance, setFormalGrantsMaterialMaintenance] = useState(false);
  const [formalGrantsProfileMaintenance, setFormalGrantsProfileMaintenance] = useState(false);
  const [organizationName, setOrganizationName] = useState("");
  const [activationLink, setActivationLink] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  useEffect(() => {
    if (!operatorId && operators.data?.length === 1) {
      setOperatorId(operators.data[0].id);
    }
  }, [operatorId, operators.data]);
  useEffect(() => {
    if (didAutoLoadCarrier || carrierSourceId || carrierName || carrierOperatorId) return;
    const draft = onboarding.data?.platform_carrier_drafts[0];
    if (!draft) return;
    setCarrierSourceId(draft.source_account_id);
    setCarrierName(draft.name);
    setCarrierChannel(draft.channel);
    setCarrierOperatorId(draft.operator_id);
    setDidAutoLoadCarrier(true);
  }, [carrierName, carrierOperatorId, carrierSourceId, didAutoLoadCarrier, onboarding.data]);
  const createAccount = useMutation({
    mutationFn: () => api<PublishingAccount>("/api/v1/tenant-management/publishing-accounts", {
      method: "POST",
      body: JSON.stringify({
        name: newAccountName,
        channel,
        content_role_name: contentRoleName,
        voice_boundary: voiceBoundary,
        operator_id: operatorId,
        control_organization_id: controlOrganizationId || null,
        operator_can_maintain_expression_profile: operatorMaintainsProfile
      }),
    }),
    onSuccess: () => {
      setNewAccountName("");
      setChannel("抖音");
      setContentRoleName("");
      setVoiceBoundary("");
      setOperatorId("");
      setControlOrganizationId("");
      setOperatorMaintainsProfile(false);
      client.invalidateQueries({ queryKey: ["publishing-accounts"] });
      client.invalidateQueries({ queryKey: ["operators"] });
      client.invalidateQueries({ queryKey: ["readiness"] });
      setNotice("已建立企业发布账号和独立表达身份，并仅向所选自然人授予操作资格。未创建或共享密码。");
    },
    onError: error => setNotice(error.message),
  });
  const createCarrier = useMutation({ mutationFn: () => api<PublishingAccount>("/api/v1/tenant-management/platform-carriers", { method: "POST", body: JSON.stringify({ source_account_id: carrierSourceId, name: carrierName, channel: carrierChannel, operator_id: carrierOperatorId, confirm_internal_carrier: true }) }), onSuccess: () => { const next = onboarding.data?.platform_carrier_drafts.find(draft => draft.source_account_id !== carrierSourceId || draft.channel !== carrierChannel); if (next) { setCarrierSourceId(next.source_account_id); setCarrierName(next.name); setCarrierChannel(next.channel); setCarrierOperatorId(next.operator_id); } else { setCarrierSourceId(""); setCarrierName(""); setCarrierChannel("小红书"); setCarrierOperatorId(""); } client.invalidateQueries({ queryKey: ["publishing-accounts"] }); client.invalidateQueries({ queryKey: ["operators"] }); client.invalidateQueries({ queryKey: ["onboarding-prefill"] }); setNotice("内部平台内容载体已经建立；没有连接平台、索取凭据或创建账号组。"); }, onError: error => setNotice(error.message) });
  const create = useMutation({ mutationFn: () => api<Operator>("/api/v1/tenant-management/operators", { method: "POST", body: JSON.stringify({ display_name: displayName, account_id: accountId }) }), onSuccess: () => { setDisplayName(""); setAccountId(""); client.invalidateQueries({ queryKey: ["operators"] }); setNotice("已创建最小自然人操作身份并授予指定企业发布账号。未创建或共享密码。"); }, onError: error => setNotice(error.message) });
  const createFormalUser = useMutation({ mutationFn: () => api<{ activation_link: string }>("/api/v1/tenant-management/users", { method: "POST", body: JSON.stringify({ display_name: formalName, username: formalUsername, organization_id: formalOrganizationId || null, account_id: formalAccountId || null, grants_material_maintenance: formalGrantsMaterialMaintenance, grants_expression_profile_maintenance: formalGrantsProfileMaintenance }) }), onSuccess: value => { setFormalName(""); setFormalUsername(""); setFormalOrganizationId(""); setFormalAccountId(""); setFormalGrantsMaterialMaintenance(false); setFormalGrantsProfileMaintenance(false); setActivationLink(value.activation_link); client.invalidateQueries({ queryKey: ["operators"] }); setNotice("已建立独立自然人登录身份；请安全复制一次性激活链接交付本人。"); }, onError: error => setNotice(error.message) });
  const createOrganization = useMutation({ mutationFn: () => api<TenantOrganization>("/api/v1/tenant-management/organizations", { method: "POST", body: JSON.stringify({ name: organizationName.trim() }) }), onSuccess: value => { setOrganizationName(""); client.invalidateQueries({ queryKey: ["tenant-organizations"] }); client.invalidateQueries({ queryKey: ["control-organizations"] }); setNotice(`已创建组织“${value.name}”。`); }, onError: error => setNotice(error.message) });
  const resetFormalUser = useMutation<string, Operator>({
    mutationFn: async operator => {
      const value = await api<{ reset_link: string }>(`/api/v1/tenant-management/users/${operator.id}/reset`, { method: "POST" });
      return value.reset_link;
    },
    onSuccess: value => {
      setActivationLink(value);
      setNotice("已生成一次性重置链接。只有本人完成设置后，才会形成新的登录密码。");
    },
    onError: error => setNotice(error.message)
  });
  return <>
    <header className="page-heading"><p className="eyebrow">账号与操作人</p><h1>企业发布账号不是登录账号。</h1><p>多人可以运营同一企业发布账号；每一位内部、临时或外部代运营操作者都必须是单独登记的自然人身份。</p></header>
    {notice && <Notice value={notice} onDismiss={() => setNotice(null)} />}
    <section className="account-grid">{accounts.data?.map(account => <article key={account.id} className="series-card"><p className="eyebrow">{account.business_data_kind === "synthetic_business_fixture" ? "等深模拟业务资料 · " : ""}{account.channel}{account.carrier_of_account ? " · 平台版本载体" : " · 表达账号"}</p><h2>{account.name}</h2><p>企业表达身份：{account.content_role}</p>{account.carrier_of_account && <p>承接自：{account.carrier_of_account}</p>}<small>{account.voice_boundary}</small>{!account.carrier_of_account_id && <AdminAccountExpression accountId={account.id} />}</article>)}</section>
    <form className="series-create" onSubmit={event => {
      event.preventDefault();
      if (!newAccountName.trim() || !contentRoleName.trim() || !voiceBoundary.trim() || !operatorId) {
        setNotice("请完整填写发布账号、平台和表达身份，并选择一位已登记操作者。");
        return;
      }
      createAccount.mutate();
    }}>
      <p>新建企业发布账号，同时建立独立表达身份，并授权一位已经登记的自然人操作者。</p>
      <input value={newAccountName} onChange={event => setNewAccountName(event.target.value)} placeholder="企业发布账号名称" maxLength={120} aria-label="企业发布账号名称" />
      <select value={channel} onChange={event => setChannel(event.target.value as CreatePublishingAccount["channel"])} aria-label="发布平台"><option value="抖音">抖音</option><option value="小红书">小红书</option><option value="微信视频号">微信视频号</option></select>
      <input value={contentRoleName} onChange={event => setContentRoleName(event.target.value)} placeholder="独立表达身份名称" maxLength={80} aria-label="独立表达身份名称" />
      <textarea value={voiceBoundary} onChange={event => setVoiceBoundary(event.target.value)} placeholder="这份企业表达身份在什么边界内成立？" maxLength={500} aria-label="企业表达身份成立边界" />
      <select value={operatorId} onChange={event => setOperatorId(event.target.value)} aria-label="已登记操作者"><option value="">选择已登记操作者</option>{operators.data?.map(operator => <option key={operator.id} value={operator.id}>{operator.display_name} · {operator.organization}</option>)}</select>
      <select value={controlOrganizationId} onChange={event => setControlOrganizationId(event.target.value)} aria-label="控制这个账号的组织"><option value="">暂不声明控制组织（画像先无人可维护）</option>{controlOrganizations.data?.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select>
      <label className="minor-check"><input type="checkbox" checked={operatorMaintainsProfile} onChange={event => setOperatorMaintainsProfile(event.target.checked)} />允许这位实际使用者维护账号五段画像</label>
      <p className="muted">控制组织决定谁可以维护这个账号的表达画像。不选就先空着，之后由有权主体明确声明；系统不会按账号名、身份名或操作者姓名替你推断。</p>
      <button className="primary" disabled={createAccount.isPending}>{createAccount.isPending ? "正在创建……" : "创建账号并授权操作者"}</button>
    </form>
    <form className="series-create" onSubmit={event => { event.preventDefault(); if (carrierSourceId && carrierName.trim() && carrierOperatorId) createCarrier.mutate(); }}>
      <p>系统已按现有表达账号预填本次缺少的内部平台内容载体。它只用于另做平台版本，不连接平台，也不需要平台账号或凭据。</p>
      {(onboarding.data?.platform_carrier_drafts.length ?? 0) > 0 && <div className="plan-actions">{onboarding.data?.platform_carrier_drafts.map(draft => <button key={`${draft.source_account_id}-${draft.channel}`} type="button" onClick={() => { setCarrierSourceId(draft.source_account_id); setCarrierName(draft.name); setCarrierChannel(draft.channel); setCarrierOperatorId(draft.operator_id); }}>{draft.source_account_name} · {draft.channel}草案</button>)}</div>}
      <select value={carrierSourceId} onChange={event => setCarrierSourceId(event.target.value)}><option value="">选择原表达账号</option>{accounts.data?.filter(account => !account.carrier_of_account_id).map(account => <option key={account.id} value={account.id}>{account.name} · {account.channel}</option>)}</select>
      <select value={carrierChannel} onChange={event => setCarrierChannel(event.target.value as CreatePublishingAccount["channel"])}><option value="抖音">抖音</option><option value="小红书">小红书</option><option value="微信视频号">微信视频号</option></select>
      <input value={carrierName} onChange={event => setCarrierName(event.target.value)} placeholder="这个平台上的内部内容载体名称" maxLength={120} />
      <select value={carrierOperatorId} onChange={event => setCarrierOperatorId(event.target.value)}><option value="">选择现有实际使用者</option>{operators.data?.map(operator => <option key={operator.id} value={operator.id}>{operator.display_name} · {operator.organization}</option>)}</select>
      <button className="primary" disabled={createCarrier.isPending}>{createCarrier.isPending ? "正在建立……" : "确认并建立内部内容载体"}</button>
    </form>
    {formalRuntime ? <><form className="series-create" onSubmit={event => { event.preventDefault(); if (organizationName.trim()) createOrganization.mutate(); }}><p>真实门店或分支组织不在列表时，只需先创建一次。</p><input value={organizationName} onChange={event => setOrganizationName(event.target.value)} placeholder="真实组织或门店名称" maxLength={120} /><button className="primary" disabled={createOrganization.isPending}>{createOrganization.isPending ? "正在创建……" : "创建组织"}</button></form><form className="series-create" onSubmit={event => { event.preventDefault(); if (formalName.trim() && formalUsername.trim()) createFormalUser.mutate(); }}><p>创建独立自然人登录身份。发布账号不是密码；每位内部或外部操作者都必须各自激活并登录。</p><input value={formalName} onChange={event => setFormalName(event.target.value)} placeholder="自然人姓名或工作名" maxLength={80} /><input value={formalUsername} onChange={event => setFormalUsername(event.target.value)} placeholder="全平台唯一登录用户名" minLength={3} maxLength={80} /><select value={formalOrganizationId} onChange={event => setFormalOrganizationId(event.target.value)} aria-label="所属组织"><option value="">使用当前管理员所属组织</option>{organizations.data?.map(organization => <option key={organization.id} value={organization.id}>{organization.name}</option>)}</select><select value={formalAccountId} onChange={event => setFormalAccountId(event.target.value)}><option value="">暂不授予发布账号（可稍后配置）</option>{accounts.data?.filter(account => !account.carrier_of_account_id).map(account => <option key={account.id} value={account.id}>{account.name}</option>)}</select><label className="minor-check"><input type="checkbox" checked={formalGrantsMaterialMaintenance} onChange={event => setFormalGrantsMaterialMaintenance(event.target.checked)} />允许维护该组织素材</label><label className="minor-check"><input type="checkbox" checked={formalGrantsProfileMaintenance} disabled={!formalAccountId} onChange={event => setFormalGrantsProfileMaintenance(event.target.checked)} />允许维护所选账号五段画像</label><button className="primary" disabled={createFormalUser.isPending}>{createFormalUser.isPending ? "正在创建……" : "创建并生成激活链接"}</button>{activationLink && <p className="notice">一次性激活链接：<code>{activationLink}</code></p>}</form></> : <form className="series-create" onSubmit={event => { event.preventDefault(); if (displayName.trim() && accountId) create.mutate(); }}><p>登记一位实际操作者（不设置密码；生产开户与一次性激活在 M5-4）。</p><input value={displayName} onChange={event => setDisplayName(event.target.value)} placeholder="自然人姓名或工作名" maxLength={80} /><select value={accountId} onChange={event => setAccountId(event.target.value)}><option value="">授予哪个企业发布账号</option>{accounts.data?.filter(account => !account.carrier_of_account_id).map(account => <option key={account.id} value={account.id}>{account.name}</option>)}</select><button className="primary" disabled={create.isPending}>{create.isPending ? "正在登记……" : "登记并授权操作人"}</button></form>}
    {activationLink && <p className="notice">一次性激活或重置链接：<code>{activationLink}</code></p>}
    <section className="readiness-list">{operators.data?.map(operator => <article className="readiness-card ready" key={operator.id}><div><p className="eyebrow">{operator.manages_tenant ? "具备租户管理资格" : "业务操作人"}</p><h2>{operator.display_name}</h2><p>{operator.organization} · {operator.publishing_accounts || "尚未授予发布账号"}</p>{operator.username && <p>登录用户名：{operator.username}</p>}<small>{operator.default_persona ? `本人默认表达人设：${operator.default_persona}` : "尚未设置本人默认表达人设"}</small>{formalRuntime && operator.username && <button type="button" disabled={resetFormalUser.isPending} onClick={() => resetFormalUser.mutate(operator)}>生成一次性重置链接</button>}</div></article>)}</section>
  </>;
}

function ProductFactsPanel(): JSX.Element {
  const client = useQueryClient();
  const products = useQuery({ queryKey: ["brand-products"], queryFn: () => api<BrandProduct[]>("/api/v1/tenant-management/brand-products") });
  const onboarding = useQuery({ queryKey: ["onboarding-prefill"], queryFn: () => api<OnboardingPrefill>("/api/v1/tenant-management/onboarding-prefill") });
  const [sku, setSku] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [category, setCategory] = useState("");
  const [colors, setColors] = useState("");
  const [material, setMaterial] = useState("");
  const [silhouette, setSilhouette] = useState("");
  const [features, setFeatures] = useState("");
  const [sourceNote, setSourceNote] = useState("");
  const [applicability, setApplicability] = useState("仅用于当前品牌正式内容，直至品牌方更新");
  const [candidateEvidence, setCandidateEvidence] = useState("");
  const [didAutoLoadDraft, setDidAutoLoadDraft] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const loadDraft = (draft: ProductPrefill): void => {
    setSku(draft.sku);
    setDisplayName(draft.display_name);
    setCategory(draft.category);
    setColors(draft.colors.join("、"));
    setMaterial(draft.material_or_structure);
    setSilhouette(draft.silhouette);
    setFeatures(draft.observable_features);
    setSourceNote(draft.source_note);
    setApplicability(draft.applicability);
    setCandidateEvidence(draft.candidate_evidence);
  };
  useEffect(() => {
    if (didAutoLoadDraft || sku || !onboarding.data?.product_drafts[0]) return;
    const draft = onboarding.data.product_drafts[0];
    setSku(draft.sku);
    setDisplayName(draft.display_name);
    setCategory(draft.category);
    setColors(draft.colors.join("、"));
    setMaterial(draft.material_or_structure);
    setSilhouette(draft.silhouette);
    setFeatures(draft.observable_features);
    setSourceNote(draft.source_note);
    setApplicability(draft.applicability);
    setCandidateEvidence(draft.candidate_evidence);
    setDidAutoLoadDraft(true);
  }, [didAutoLoadDraft, onboarding.data, sku]);
  const save = useMutation({
    mutationFn: () => api<BrandProduct>("/api/v1/tenant-management/brand-products", {
      method: "PUT",
      body: JSON.stringify({
        sku: sku.trim(),
        display_name: displayName.trim(),
        category: category.trim(),
        colors: colors.split(/[、,，]/).map(item => item.trim()).filter(Boolean),
        material_or_structure: material.trim(),
        silhouette: silhouette.trim(),
        observable_features: features.trim(),
        source_note: sourceNote.trim(),
        applicability: applicability.trim(),
        confirm_as_current_brand_fact: true
      })
    }),
    onSuccess: value => {
      client.invalidateQueries({ queryKey: ["brand-products"] });
      client.invalidateQueries({ queryKey: ["onboarding-prefill"] });
      const next = onboarding.data?.product_drafts.find(draft => draft.sku !== value.sku);
      if (next) loadDraft(next);
      else { setSku(""); setDisplayName(""); setCategory(""); setColors(""); setMaterial(""); setSilhouette(""); setFeatures(""); setSourceNote(""); setCandidateEvidence(""); }
      setNotice(`已由当前品牌方确认并保存 ${value.display_name} 的第 ${value.fact_version} 版事实。`);
    },
    onError: error => setNotice(error.message)
  });
  return <>
    <header className="page-heading"><p className="eyebrow">真实商品事实</p><h1>纠正并确认本轮需要的 1—3 件商品。</h1><p>系统已从候选资料预填最小草案；价格、库存、性能、设计动机和推断字段没有带入。草案在你确认前不会参与生成。</p></header>
    {notice && <Notice value={notice} onDismiss={() => setNotice(null)} />}
    <section className="account-grid">{products.data?.map(product => <article className="series-card" key={product.sku}><p className="eyebrow">{product.source_kind === "synthetic_business_fixture" ? "演示商品事实 · " : ""}{product.sku} · 事实 V{product.fact_version}</p><h2>{product.display_name}</h2><p>{Object.entries(product.facts).map(([key, value]) => `${key}：${Array.isArray(value) ? value.join("、") : String(value)}`).join("；")}</p><small>来源：{product.source_note} · 范围：{product.applicability}{product.updated_by ? ` · 由 ${product.updated_by} 保存` : ""}</small></article>)}</section>
    {(onboarding.data?.product_drafts.length ?? 0) > 0 && <section className="account-grid">{onboarding.data?.product_drafts.map(draft => <article className="series-card" key={draft.sku}><p className="eyebrow">{draft.sku} · 可编辑候选草案</p><h2>{draft.display_name}</h2><p>{draft.candidate_evidence}</p><button type="button" onClick={() => loadDraft(draft)}>载入并纠正这份草案</button></article>)}</section>}
    <form className="series-create" onSubmit={event => { event.preventDefault(); if (sku.trim() && displayName.trim() && sourceNote.trim() && applicability.trim()) save.mutate(); }}>
      {candidateEvidence && <p className="muted">当前预填边界：{candidateEvidence}</p>}
      <input value={sku} onChange={event => setSku(event.target.value)} placeholder="商品稳定编号" maxLength={80} />
      <input value={displayName} onChange={event => setDisplayName(event.target.value)} placeholder="商品名称；候选名不准确时直接改" maxLength={120} />
      <input value={category} onChange={event => setCategory(event.target.value)} placeholder="品类（按本轮需要）" maxLength={120} />
      <input value={colors} onChange={event => setColors(event.target.value)} placeholder="颜色，用逗号分开" maxLength={200} />
      <textarea value={material} onChange={event => setMaterial(event.target.value)} placeholder="材质或结构（只有确认过才保留）" maxLength={500} />
      <textarea value={silhouette} onChange={event => setSilhouette(event.target.value)} placeholder="轮廓（只有确认过才保留）" maxLength={300} />
      <textarea value={features} onChange={event => setFeatures(event.target.value)} placeholder="肉眼可以确认的特征" maxLength={800} />
      <input value={sourceNote} onChange={event => setSourceNote(event.target.value)} placeholder="资料来源说明" maxLength={300} />
      <input value={applicability} onChange={event => setApplicability(event.target.value)} placeholder="这些事实适用于什么范围？" maxLength={300} />
      <button className="primary" disabled={save.isPending}>{save.isPending ? "正在保存……" : "确认并保存为当前商品事实"}</button>
    </form>
  </>;
}

function ReadinessPanel(): JSX.Element {
  const client = useQueryClient();
  const readiness = useQuery({ queryKey: ["readiness"], queryFn: () => api<Readiness>("/api/v1/admin/readiness") });
  const expression = useQuery({ queryKey: ["brand-expression"], queryFn: () => api<BrandExpression>("/api/v1/admin/brand-expression") });
  const [draft, setDraft] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  useEffect(() => { if (expression.data && draft === "") setDraft(expression.data.draft); }, [expression.data?.draft]);
  const confirm = useMutation({ mutationFn: () => api<BrandExpression>("/api/v1/admin/brand-expression/confirm", { method: "POST", body: JSON.stringify({ draft }) }), onSuccess: value => { client.invalidateQueries({ queryKey: ["readiness"] }); client.invalidateQueries({ queryKey: ["brand-expression"] }); setNotice(`品牌表达 V${value.version} 已由当前品牌方确认。`); }, onError: error => setNotice(error.message) });
  return <><header className="page-heading"><p className="eyebrow">企业管理</p><h1>入驻与就绪</h1><p>只列出现在真的会影响哪项能力的事项，不使用统一完成度。</p></header>{notice && <Notice value={notice} onDismiss={() => setNotice(null)} />}<section className="readiness-list">{readiness.isLoading ? <Loading label="正在读取当前就绪条件……" /> : readiness.data?.items.map(item => <article className={`readiness-card ${item.state}`} key={item.id}><div><p className="eyebrow">{item.state === "ready" ? "已具备" : "需要处理"}</p><h2>{item.title}</h2><p>{item.detail}</p><small>完成后：{item.unlock}</small></div>{item.id === "brand_expression" && item.state === "needs_action" && <button className="primary" onClick={() => document.getElementById("brand-expression")?.scrollIntoView({ behavior: "smooth" })}>确认草案</button>}</article>)}</section><section id="brand-expression" className="expression-card"><div><p className="eyebrow">品牌表达草案</p><h2>先判断“像不像我们”。</h2><p>这份草案可修改；未确认前不会被当成正式表达基线。</p></div><textarea value={draft} onChange={event => setDraft(event.target.value)} aria-label="品牌表达草案" /><div className="expression-foot"><span>{expression.data?.status === "confirmed" ? `已确认 V${expression.data.version}` : "等待确认"}</span><button className="primary" onClick={() => confirm.mutate()} disabled={confirm.isPending || draft.trim().length < 8}>{confirm.isPending ? "正在确认……" : "确认这版表达"}</button></div></section></>;
}

function SeriesPanel({ onContinue }: { onContinue: (series: Series, position?: number) => void }): JSX.Element {
  const client = useQueryClient();
  const series = useQuery({ queryKey: ["series"], queryFn: () => api<Series[]>("/api/v1/content/series") });
  const recent = useQuery({ queryKey: ["series-candidates"], queryFn: () => api<RecentItem[]>("/api/v1/content/tasks") });
  const [title, setTitle] = useState("");
  const [premise, setPremise] = useState("");
  const create = useMutation({ mutationFn: () => api<Series>("/api/v1/content/series", { method: "POST", body: JSON.stringify({ title, premise }) }), onSuccess: () => { setTitle(""); setPremise(""); client.invalidateQueries({ queryKey: ["series"] }); } });
  const add = useMutation({ mutationFn: ({ seriesId, taskId }: { seriesId: string; taskId: string }) => api<Series>(`/api/v1/content/series/${seriesId}/items`, { method: "POST", body: JSON.stringify({ task_id: taskId }) }), onSuccess: () => client.invalidateQueries({ queryKey: ["series"] }) });
  const reorder = useMutation({ mutationFn: ({ seriesId, taskIds }: { seriesId: string; taskIds: string[] }) => api<Series>(`/api/v1/content/series/${seriesId}/items`, { method: "PUT", body: JSON.stringify({ task_ids: taskIds }) }), onSuccess: () => client.invalidateQueries({ queryKey: ["series"] }) });
  const reset = useMutation({ mutationFn: (id: string) => api<Series>(`/api/v1/content/series/${id}/reset`, { method: "POST", body: JSON.stringify({}) }), onSuccess: () => client.invalidateQueries({ queryKey: ["series"] }) });
  return <><header className="page-heading"><p className="eyebrow">连续系列</p><h1>系列由你决定怎样继续。</h1><p>可以跳集、插集、改序；只有明确要求承接前情时才会把它带入下一次内容。</p></header><form className="series-create" onSubmit={event => { event.preventDefault(); if (title.trim()) create.mutate(); }}><input value={title} onChange={event => setTitle(event.target.value)} placeholder="系列名称" maxLength={100} /><textarea value={premise} onChange={event => setPremise(event.target.value)} placeholder="这组内容想持续谈什么？（可选）" maxLength={500} /><button className="primary">新建系列</button></form><section className="series-grid">{series.data?.map(item => <SeriesCard key={item.id} item={item} candidates={recent.data ?? []} onContinue={position => onContinue(item, position)} onAdd={(taskId) => add.mutate({ seriesId: item.id, taskId })} onMove={(from, to) => { const next = [...item.items]; const [moved] = next.splice(from, 1); next.splice(to, 0, moved); reorder.mutate({ seriesId: item.id, taskIds: next.map(entry => entry.task_id) }); }} onReset={() => reset.mutate(item.id)} />)}</section></>;
}

function SeriesCard({ item, candidates, onContinue, onAdd, onMove, onReset }: { item: Series; candidates: RecentItem[]; onContinue: (position?: number) => void; onAdd: (taskId: string) => void; onMove: (from: number, to: number) => void; onReset: () => void }): JSX.Element {
  const [taskId, setTaskId] = useState("");
  const [position, setPosition] = useState("");
  const available = candidates.filter(candidate => !item.items.some(entry => entry.task_id === candidate.task_id));
  return <article className="series-card"><p className="eyebrow">{item.items.length} 集已明确安排 · 编排 V{item.revision}</p><h2>{item.title}</h2><p>{item.premise || "还没有预设前情；每一集仍从当前任务开始。"}</p><div className="series-add"><button className="primary" type="button" onClick={() => onContinue()}>接着做下一篇</button><input type="number" min={1} max={999} value={position} onChange={event => setPosition(event.target.value)} placeholder="指定第几篇" aria-label={`《${item.title}》指定位置`} /><button type="button" disabled={!position} onClick={() => { if (position) onContinue(Number(position)); }}>去这个位置写</button></div><ol>{item.items.map((entry, index) => <li key={`${entry.task_id}-${entry.position}`}><span>第 {entry.position} 篇 · {entry.title}</span><span className="series-order"><button disabled={index === 0} onClick={() => onMove(index, index - 1)}>上移</button><button disabled={index === item.items.length - 1} onClick={() => onMove(index, index + 1)}>下移</button></span></li>)}</ol>{available.length > 0 && <div className="series-add"><select value={taskId} onChange={event => setTaskId(event.target.value)}><option value="">把已有成品插入系列</option>{available.map(candidate => <option key={candidate.task_id} value={candidate.task_id}>{candidate.title}</option>)}</select><button onClick={() => { if (taskId) { onAdd(taskId); setTaskId(""); } }}>插入</button></div>}<div><button onClick={onReset}>重置编排</button><span>不会删除已有成品</span></div></article>;
}

function MaterialsPanel(): JSX.Element {
  const client = useQueryClient();
  const materials = useQuery({ queryKey: ["materials"], queryFn: () => api<Material[]>("/api/v1/materials") });
  const [scope, setScope] = useState<"personal" | "organization">("personal");
  const [title, setTitle] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [minor, setMinor] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const upload = useMutation({ mutationFn: async () => api<Material>(`/api/v1/materials/${scope}`, { method: "POST", body: JSON.stringify({ title, filename: (file as File).name, content_type: (file as File).type || "application/octet-stream", content_base64: await fileBase64(file as File), declares_identifiable_minor: minor }) }), onSuccess: () => { setTitle(""); setFile(null); setMinor(false); client.invalidateQueries({ queryKey: ["materials"] }); }, onError: error => setNotice(error.message) });
  const remove = useMutation({ mutationFn: (id: string) => api<void>(`/api/v1/materials/${id}`, { method: "DELETE" }), onSuccess: () => client.invalidateQueries({ queryKey: ["materials"] }) });
  const own = useMemo(() => (materials.data ?? []).filter(item => item.scope === "personal"), [materials.data]);
  const org = useMemo(() => (materials.data ?? []).filter(item => item.scope === "organization"), [materials.data]);
  return <><header className="page-heading"><p className="eyebrow">素材边界</p><h1>私人素材与组织素材分开。</h1><p>文字、图片和视频保持原件，只能作为用户主动选择的创作参考；系统不会编辑、打码、匿名化或生成媒体文件。</p></header>{notice && <Notice value={notice} onDismiss={() => setNotice(null)} />}<section className="material-grid"><MaterialList title="我的私人素材" detail="只供本人在当前授权期主动选择使用。不会自动变成组织素材。" items={own} onDelete={id => { if (window.confirm("删除这份私人素材后无法恢复。")) remove.mutate(id); }} /><MaterialList title="本组织素材" detail="只能由明确维护人从组织入口录入；组织官方不等于正式品牌事实。" items={org} onDelete={id => remove.mutate(id)} /></section><form className="material-upload" onSubmit={event => { event.preventDefault(); if (title.trim() && file) upload.mutate(); }}><div><label>保存到<select value={scope} onChange={event => setScope(event.target.value as "personal" | "organization")}><option value="personal">我的私人素材</option><option value="organization">本组织素材</option></select></label><input value={title} onChange={event => setTitle(event.target.value)} placeholder="素材名称" maxLength={120} /><input type="file" accept="text/plain,.txt,.md,.csv,image/*,video/*" onChange={event => setFile(event.target.files?.[0] ?? null)} /></div><label className="minor-check"><input type="checkbox" checked={minor} onChange={event => setMinor(event.target.checked)} />我已知该原件含有可识别真人未成年人</label><p>若已知含有可识别真人未成年人，第一版会在保存前拒绝；系统不进行年龄识别。</p><button className="primary" disabled={upload.isPending}>{upload.isPending ? "正在保存……" : "保存原件"}</button></form></>;
}

function MaterialList({ title, detail, items, onDelete }: { title: string; detail: string; items: Material[]; onDelete: (id: string) => void }): JSX.Element { return <article className="material-zone"><h2>{title}</h2><p>{detail}</p>{items.length === 0 ? <p className="empty-inline">还没有素材。</p> : <ul>{items.map(item => <li key={item.id}><div><strong>{item.title}</strong><span>{item.media_type === "video" ? "视频原件" : item.media_type === "text" ? "文字原件" : "图片原件"} · {new Date(item.created_at).toLocaleDateString("zh-CN")}</span></div><button onClick={() => onDelete(item.id)}>删除</button></li>)}</ul>}</article>; }

function VersionRail<T extends { version_id: string; version: number; created_at: string }>({ versions, currentVersion, onSelect }: { versions: T[]; currentVersion: number; onSelect: (value: T) => void }): JSX.Element {
  if (versions.length < 2) return <p className="version-rail single">当前 V{currentVersion}；后续修改会自动保留旧版。</p>;
  return <nav className="version-rail" aria-label="版本历史"><span>版本</span>{versions.map(item => <button key={item.version_id} type="button" aria-current={item.version === currentVersion ? "true" : undefined} className={item.version === currentVersion ? "current" : ""} onClick={() => onSelect(item)}>V{item.version}{item.version === currentVersion ? " · 当前" : ""}</button>)}</nav>;
}

function RecentList({ items, loading, onOpen }: { items: RecentItem[]; loading: boolean; onOpen: (item: RecentItem) => void }): JSX.Element { if (loading) return <p className="muted">正在读取……</p>; if (!items.length) return <p className="muted">第一份成品做好后会出现在这里。</p>; return <ul className="recent-list" id="recent">{items.map(item => <li key={item.version_id}><button onClick={() => onOpen(item)}><strong>{item.title}</strong><span>V{item.version} · {item.updated_at}</span></button></li>)}</ul>; }
function ArtifactText({ value }: { value: string }): JSX.Element { return <article className="artifact-text">{value.split("\n").filter(Boolean).map((paragraph, index) => paragraph.startsWith("#") ? <h3 key={`${paragraph}-${index}`}>{paragraph.replace(/^#+\s*/, "")}</h3> : <p key={`${paragraph}-${index}`}>{paragraph}</p>)}</article>; }
function EmptyArtifact({ title, detail }: { title: string; detail: string }): JSX.Element { return <div className="empty-artifact"><span>笛语</span><h2>{title}</h2><p>{detail}</p></div>; }
function Notice({ value, onDismiss }: { value: string; onDismiss: () => void }): JSX.Element { return <div className="notice" role="status"><span>{value}</span><button aria-label="关闭提示" onClick={onDismiss}>×</button></div>; }
function Loading({ label }: { label: string }): JSX.Element { return <div className="loading" role="status">{label}</div>; }
function MobileTabs({ first, second, value, onChange }: { first: string; second: string; value: "conversation" | "artifact"; onChange: (value: "conversation" | "artifact") => void }): JSX.Element { return <nav className="mobile-tabs" aria-label="移动端工作面"><button type="button" aria-current={value === "conversation" ? "page" : undefined} className={value === "conversation" ? "active" : ""} onClick={() => onChange("conversation")}>{first}</button><button type="button" aria-current={value === "artifact" ? "page" : undefined} className={value === "artifact" ? "active" : ""} onClick={() => onChange("artifact")}>{second}</button></nav>; }

function Root(): JSX.Element { return <App />; }

export default Root;
