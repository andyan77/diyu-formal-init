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
  target?: Target;
  target_key?: Target;
  adapted_from?: string | null;
}

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
  items: Array<{ task_id: string; position: number; title: string }>;
}

interface Material {
  id: string;
  title: string;
  media_type: string;
  scope: "personal" | "organization";
  created_at: string;
  status: string;
}

interface PublishingAccount {
  id: string;
  name: string;
  channel: string;
  content_role: string;
  voice_boundary: string;
}

interface CreatePublishingAccount {
  name: string;
  channel: "抖音" | "小红书" | "微信视频号";
  content_role_name: string;
  voice_boundary: string;
  operator_id: string;
}

interface Operator {
  id: string;
  display_name: string;
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

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...init?.headers },
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
      <a href={displayEntry} className="entry-choice"><span>对内</span><strong>陈列搭配</strong><small>把本次库存整理成墙面双层挂杆执行方案。</small></a>
    </section>
    <form className="persona-card" onSubmit={event => { event.preventDefault(); persona.mutate(); }}><p className="eyebrow">本人默认表达人设</p><p>每个自然人只有这一份可维护的人设；它不等于企业发布账号的表达身份。</p><input value={name} onChange={event => setName(event.target.value)} maxLength={80} aria-label="本人默认表达人设名称" /><textarea value={boundary} onChange={event => setBoundary(event.target.value)} maxLength={500} aria-label="本人默认表达人设边界" /><button className="primary" disabled={persona.isPending}>{persona.isPending ? "正在保存……" : "更新我的默认人设"}</button></form>
  </main>;
}

function TenantManagementShell({ context, children }: { context: Context; children: ReactNode }): JSX.Element {
  const identity = context.identity;
  return <div className="app-frame management-frame"><header className="topbar"><span className="wordmark"><img src="/assets/diyu-logo-horizontal.svg" alt="笛语" /></span><p className="management-title">租户管理</p><details className="identity-bar"><summary><span>{identity.operator}</span><span className="identity-org">· {identity.organization}</span></summary><dl><div><dt>实际操作人</dt><dd>{identity.operator}</dd></div><div><dt>当前范围</dt><dd>{identity.brand}</dd></div></dl></details></header><div className="application-body">{children}</div></div>;
}

function WorkbenchShell({ context, children }: { context: Context; children: ReactNode }): JSX.Element {
  const location = useLocation();
  const contentActive = location.pathname.startsWith("/content");
  const displayActive = location.pathname.startsWith("/display");
  const identity = context.identity;
  const contentEntry = context.formal_runtime ? "/content" : "/ui/select/content";
  const displayEntry = context.formal_runtime ? "/display" : "/ui/select/display";
  return <div className="app-frame">
    <header className="topbar">
      <Link className="wordmark" to="/user"><img src="/assets/diyu-logo-horizontal.svg" alt="笛语" /></Link>
      <nav className="app-switcher" aria-label="工作域">
        <a className={contentActive ? "active" : ""} href={contentEntry}>内容生产</a>
        <a className={displayActive ? "active" : ""} href={displayEntry}>陈列搭配</a>
      </nav>
      <details className="identity-bar"><summary><span>{identity.operator}</span><span className="identity-org">· {identity.organization}</span></summary><dl>
        <div><dt>实际操作人</dt><dd>{identity.operator}</dd></div>
        <div><dt>代表组织</dt><dd>{identity.organization}</dd></div>
        <div><dt>{context.application === "content" ? "发布账号" : "当前门店"}</dt><dd>{context.application === "content" ? identity.account : identity.store}</dd></div>
        {context.application === "content" && <div><dt>表达身份</dt><dd>{identity.content_role}</dd></div>}
      </dl></details>
    </header>
    <div className="application-body">{children}</div>
  </div>;
}

function ContentWorkbench({ context }: { context: Context }): JSX.Element {
  const client = useQueryClient();
  const [artifact, setArtifact] = useState<ContentVersion | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [mobileView, setMobileView] = useState<"conversation" | "artifact">("conversation");
  const [surface, setSurface] = useState<"compose" | "series" | "materials">("compose");
  const recent = useQuery({ queryKey: ["content-recent"], queryFn: () => api<RecentItem[]>("/api/v1/content/tasks") });
  const create = useMutation({
    mutationFn: ({ seed, target }: { seed: string; target: Target }) => api<ContentVersion | { kind: string; message: string }>("/api/v1/content", { method: "POST", body: JSON.stringify({ weak_seed: seed, target }) }),
    onSuccess: payload => {
      if ("task_id" in payload) { setArtifact(payload); setMobileView("artifact"); setNotice(null); client.invalidateQueries({ queryKey: ["content-recent"] }); }
      else setNotice(payload.message);
    },
    onError: error => setNotice(error.message)
  });
  const open = async (item: RecentItem): Promise<void> => {
    try { setArtifact(await api<ContentVersion>(`/api/v1/tasks/${item.task_id}/versions/${item.version}?target=${item.target ?? "douyin_video"}`)); setMobileView("artifact"); }
    catch (error) { setNotice(error instanceof Error ? error.message : "无法读取这份成品。"); }
  };
  const sidebar = <aside className="sidebar"><p className="sidebar-label">内容生产</p><nav><button className={surface === "compose" ? "active" : ""} onClick={() => setSurface("compose")}>开始一条内容</button><button className={surface === "series" ? "active" : ""} onClick={() => setSurface("series")}>连续系列</button><button className={surface === "materials" ? "active" : ""} onClick={() => setSurface("materials")}>我的素材</button></nav><p className="sidebar-label">最近成品</p><RecentList items={recent.data ?? []} loading={recent.isLoading} onOpen={open} /></aside>;
  if (surface !== "compose") return <section className="workbench content-workbench">{sidebar}<main className="admin-main">{surface === "series" ? <SeriesPanel /> : <MaterialsPanel />}</main></section>;
  return <section className="workbench content-workbench">
    {sidebar}
    <main className={`conversation-pane ${mobileView === "artifact" ? "mobile-hidden" : ""}`} id="compose">
      <div className="pane-heading"><p className="eyebrow">内容生产</p><h1>自然说清这次想完成什么。</h1><p>系统只会使用当前账号可代表的品牌与发布范围。</p></div>
      {context.generator_mode === "stub" && <p className="mode-note">本地确定性测试模式：不冒充真实模型调用。</p>}
      {notice && <Notice value={notice} onDismiss={() => setNotice(null)} />}
      <ContentComposer targets={context.targets ?? []} busy={create.isPending} onSubmit={(seed, target) => create.mutate({ seed, target })} />
      <section className="starter-prompts"><h2>可以这样开始</h2><button onClick={() => create.mutate({ seed: "请解释 ZX-C218 的双面不等于一件顶两件，讲清取舍。", target: "douyin_video" })}>把 ZX-C218 的两面和分量讲清楚</button><button onClick={() => create.mutate({ seed: "下午开完一个挺正式的会，转身就拎着电脑去接孩子。", target: "xiaohongshu_video" })}>从一个真实穿衣情境开始</button></section>
    </main>
    <ArtifactPane mobileView={mobileView} onShowConversation={() => setMobileView("conversation")} artifact={artifact} onArtifact={setArtifact} onNotice={setNotice} context={context} />
    <MobileTabs first="对话" second="成品" value={mobileView} onChange={setMobileView} />
  </section>;
}

function ContentComposer({ targets, busy, onSubmit }: { targets: Array<{ value: Target; label: string }>; busy: boolean; onSubmit: (seed: string, target: Target) => void }): JSX.Element {
  const [seed, setSeed] = useState("");
  const [target, setTarget] = useState<Target>(targets[0]?.value ?? "douyin_video");
  const submit = (event: FormEvent): void => { event.preventDefault(); if (seed.trim()) onSubmit(seed.trim(), target); };
  return <form className="composer" onSubmit={submit}><label>这次要做成<select value={target} onChange={event => setTarget(event.target.value as Target)}>{targets.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label><textarea value={seed} onChange={event => setSeed(event.target.value)} maxLength={1000} placeholder="例如：我想把一件衣服的取舍说清楚，别只讲卖点。" aria-label="内容需求" /><div className="composer-foot"><span>不需要填写表单；必要时只追问一个会改变成品的问题。</span><button className="primary" disabled={busy}>{busy ? "正在整理成品……" : "生成当前成品"}</button></div></form>;
}

function ArtifactPane({ artifact, onArtifact, onNotice, context, mobileView, onShowConversation }: { artifact: ContentVersion | null; onArtifact: (value: ContentVersion) => void; onNotice: (value: string) => void; context: Context; mobileView: "conversation" | "artifact"; onShowConversation: () => void }): JSX.Element {
  const client = useQueryClient();
  const [instruction, setInstruction] = useState("");
  const versions = useQuery({ queryKey: ["content-versions", artifact?.task_id ?? "none"], queryFn: () => api<ContentHistoryVersion[]>(`/api/v1/content/tasks/${artifact?.task_id}/versions`), enabled: artifact !== null });
  const revise = useMutation({
    mutationFn: () => { const target = artifact?.target_key ?? "douyin_video"; return api<ContentVersion>(`/api/v1/tasks/${artifact?.task_id}/revisions`, { method: "POST", body: JSON.stringify({ instruction, target, source_target: target }) }); },
    onSuccess: value => { onArtifact(value); setInstruction(""); client.invalidateQueries({ queryKey: ["content-recent"] }); client.invalidateQueries({ queryKey: ["content-versions", value.task_id] }); },
    onError: error => onNotice(error.message)
  });
  const copy = async (): Promise<void> => { if (!artifact) return; await navigator.clipboard.writeText(artifact.body).catch(() => undefined); onNotice("已复制当前成品全文。"); };
  const exportText = (): void => { if (!artifact) return; const blob = new Blob([artifact.body], { type: "text/plain;charset=utf-8" }); const url = URL.createObjectURL(blob); const anchor = document.createElement("a"); anchor.href = url; anchor.download = `笛语内容-V${artifact.version}.txt`; anchor.click(); URL.revokeObjectURL(url); };
  return <aside className={`artifact-pane ${mobileView === "conversation" ? "mobile-hidden" : ""}`} aria-live="polite">
    {!artifact ? <EmptyArtifact title="成品会出现在这里" detail="生成后可以完整阅读、继续修改、复制或导出。旧版本始终保留。" /> : <>
      <div className="artifact-header"><div><p className="eyebrow">当前成品 · V{artifact.version}</p><h2>{artifact.outline}</h2>{artifact.adapted_from && <p className="muted">{artifact.adapted_from}</p>}</div><div className="artifact-actions"><button onClick={copy}>复制</button><button onClick={exportText}>导出</button></div></div>
      <ArtifactText value={artifact.body} />
      <VersionRail versions={versions.data ?? []} currentVersion={artifact.version} onSelect={value => onArtifact({ ...value, kind: "content" })} />
      <form className="revision-form" onSubmit={event => { event.preventDefault(); if (instruction.trim()) revise.mutate(); }}><label>继续改，只说这次要变什么<textarea value={instruction} onChange={event => setInstruction(event.target.value)} placeholder="例如：把结尾改短一点，其他不动。" maxLength={1000} /></label><button className="primary" disabled={revise.isPending}>{revise.isPending ? "正在生成新版本……" : `生成 V${artifact.version + 1}`}</button></form>
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
    <main className={`conversation-pane ${mobileView === "artifact" ? "mobile-hidden" : ""}`} id="inventory"><div className="pane-heading"><p className="eyebrow">陈列搭配</p><h1>先把这组墙的库存说清楚。</h1><p>清单只用于本次方案，不会写回或核验库存账。</p></div>{notice && <Notice value={notice} onDismiss={() => setNotice(null)} />}<form className="composer" onSubmit={event => { event.preventDefault(); if (inventory.trim()) create.mutate(); }}><textarea value={inventory} onChange={event => setInventory(event.target.value)} placeholder="今天这组墙可用：ZX-C218 3 件、ZX-S104 3 件、ZX-K126 4 件……" aria-label="本次库存" /><div className="composer-foot"><span>DM01 只使用本次库存、当前规则和双层挂杆条件。</span><button className="primary" disabled={create.isPending}>{create.isPending ? "正在整理方案……" : "生成墙面方案"}</button></div></form></main>
    <aside className={`artifact-pane ${mobileView === "conversation" ? "mobile-hidden" : ""}`}>{!artifact ? <EmptyArtifact title="方案会出现在这里" detail="生成后可以完整阅读，再用自然反馈只改受影响的搭配组。" /> : <><div className="artifact-header"><div><p className="eyebrow">墙面方案 · V{artifact.version}</p><h2>本次双层挂杆执行方案</h2></div><button onClick={() => navigator.clipboard.writeText(artifact.body).then(() => setNotice("已复制当前方案。"))}>复制</button></div><ArtifactText value={artifact.body} /><VersionRail versions={versions.data ?? []} currentVersion={artifact.version} onSelect={setArtifact} /><form className="revision-form" onSubmit={event => { event.preventDefault(); if (feedback.trim()) revise.mutate(); }}><label>门店自然反馈<textarea value={feedback} onChange={event => setFeedback(event.target.value)} placeholder="例如：右侧两件外套太厚，挂不下。" /></label><button className="primary" disabled={revise.isPending}>{revise.isPending ? "正在生成新版……" : `生成 V${artifact.version + 1}`}</button></form><p className="artifact-boundary"><span>摆放示意与文字执行方案，不是门店实拍。</span></p></>}</aside>
    <MobileTabs first="对话" second="方案" value={mobileView} onChange={setMobileView} />
  </section>;
}

function AdminWorkspace({ context }: { context: Context }): JSX.Element {
  const [section, setSection] = useState<"readiness" | "operators">("readiness");
  return <section className="admin-workspace"><aside className="sidebar"><p className="sidebar-label">租户管理</p><nav><button className={section === "readiness" ? "active" : ""} onClick={() => setSection("readiness")}>入驻与就绪</button><button className={section === "operators" ? "active" : ""} onClick={() => setSection("operators")}>账号与操作人</button></nav></aside><main className="admin-main">{section === "readiness" && <ReadinessPanel />}{section === "operators" && <OperatorPanel formalRuntime={context.formal_runtime === true} />}</main></section>;
}

function OperatorPanel({ formalRuntime }: { formalRuntime: boolean }): JSX.Element {
  const client = useQueryClient();
  const operators = useQuery({ queryKey: ["operators"], queryFn: () => api<Operator[]>("/api/v1/tenant-management/operators") });
  const accounts = useQuery({ queryKey: ["publishing-accounts"], queryFn: () => api<PublishingAccount[]>("/api/v1/tenant-management/publishing-accounts") });
  const [newAccountName, setNewAccountName] = useState("");
  const [channel, setChannel] = useState<CreatePublishingAccount["channel"]>("抖音");
  const [contentRoleName, setContentRoleName] = useState("");
  const [voiceBoundary, setVoiceBoundary] = useState("");
  const [operatorId, setOperatorId] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [accountId, setAccountId] = useState("");
  const [formalName, setFormalName] = useState("");
  const [formalUsername, setFormalUsername] = useState("");
  const [formalAccountId, setFormalAccountId] = useState("");
  const [activationLink, setActivationLink] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const createAccount = useMutation({
    mutationFn: () => api<PublishingAccount>("/api/v1/tenant-management/publishing-accounts", {
      method: "POST",
      body: JSON.stringify({
        name: newAccountName,
        channel,
        content_role_name: contentRoleName,
        voice_boundary: voiceBoundary,
        operator_id: operatorId,
      }),
    }),
    onSuccess: () => {
      setNewAccountName("");
      setChannel("抖音");
      setContentRoleName("");
      setVoiceBoundary("");
      setOperatorId("");
      client.invalidateQueries({ queryKey: ["publishing-accounts"] });
      client.invalidateQueries({ queryKey: ["operators"] });
      client.invalidateQueries({ queryKey: ["readiness"] });
      setNotice("已建立企业发布账号和独立表达身份，并仅向所选自然人授予操作资格。未创建或共享密码。");
    },
    onError: error => setNotice(error.message),
  });
  const create = useMutation({ mutationFn: () => api<Operator>("/api/v1/tenant-management/operators", { method: "POST", body: JSON.stringify({ display_name: displayName, account_id: accountId }) }), onSuccess: () => { setDisplayName(""); setAccountId(""); client.invalidateQueries({ queryKey: ["operators"] }); setNotice("已创建最小自然人操作身份并授予指定企业发布账号。未创建或共享密码。"); }, onError: error => setNotice(error.message) });
  const createFormalUser = useMutation({ mutationFn: () => api<{ activation_link: string }>("/api/v1/tenant-management/users", { method: "POST", body: JSON.stringify({ display_name: formalName, username: formalUsername, account_id: formalAccountId || null }) }), onSuccess: value => { setFormalName(""); setFormalUsername(""); setFormalAccountId(""); setActivationLink(value.activation_link); client.invalidateQueries({ queryKey: ["operators"] }); setNotice("已建立独立自然人登录身份；请安全复制一次性激活链接交付本人。"); }, onError: error => setNotice(error.message) });
  return <>
    <header className="page-heading"><p className="eyebrow">账号与操作人</p><h1>企业发布账号不是登录账号。</h1><p>多人可以运营同一企业发布账号；每一位内部、临时或外部代运营操作者都必须是单独登记的自然人身份。</p></header>
    {notice && <Notice value={notice} onDismiss={() => setNotice(null)} />}
    <section className="account-grid">{accounts.data?.map(account => <article key={account.id} className="series-card"><p className="eyebrow">{account.channel}</p><h2>{account.name}</h2><p>企业表达身份：{account.content_role}</p><small>{account.voice_boundary}</small></article>)}</section>
    <form className="series-create" onSubmit={event => { event.preventDefault(); if (newAccountName.trim() && contentRoleName.trim() && voiceBoundary.trim() && operatorId) createAccount.mutate(); }}>
      <p>新建企业发布账号，同时建立独立表达身份，并授权一位已经登记的自然人操作者。</p>
      <input value={newAccountName} onChange={event => setNewAccountName(event.target.value)} placeholder="企业发布账号名称" maxLength={120} aria-label="企业发布账号名称" />
      <select value={channel} onChange={event => setChannel(event.target.value as CreatePublishingAccount["channel"])} aria-label="发布平台"><option value="抖音">抖音</option><option value="小红书">小红书</option><option value="微信视频号">微信视频号</option></select>
      <input value={contentRoleName} onChange={event => setContentRoleName(event.target.value)} placeholder="独立表达身份名称" maxLength={80} aria-label="独立表达身份名称" />
      <textarea value={voiceBoundary} onChange={event => setVoiceBoundary(event.target.value)} placeholder="这份企业表达身份在什么边界内成立？" maxLength={500} aria-label="企业表达身份成立边界" />
      <select value={operatorId} onChange={event => setOperatorId(event.target.value)} aria-label="已登记操作者"><option value="">选择已登记操作者</option>{operators.data?.map(operator => <option key={operator.id} value={operator.id}>{operator.display_name} · {operator.organization}</option>)}</select>
      <button className="primary" disabled={createAccount.isPending}>{createAccount.isPending ? "正在创建……" : "创建账号并授权操作者"}</button>
    </form>
    {formalRuntime ? <form className="series-create" onSubmit={event => { event.preventDefault(); if (formalName.trim() && formalUsername.trim()) createFormalUser.mutate(); }}><p>创建独立自然人登录身份。发布账号不是密码；每位内部或外部操作者都必须各自激活并登录。</p><input value={formalName} onChange={event => setFormalName(event.target.value)} placeholder="自然人姓名或工作名" maxLength={80} /><input value={formalUsername} onChange={event => setFormalUsername(event.target.value)} placeholder="全平台唯一登录用户名" minLength={3} maxLength={80} /><select value={formalAccountId} onChange={event => setFormalAccountId(event.target.value)}><option value="">暂不授予发布账号（可稍后配置）</option>{accounts.data?.map(account => <option key={account.id} value={account.id}>{account.name}</option>)}</select><button className="primary" disabled={createFormalUser.isPending}>{createFormalUser.isPending ? "正在创建……" : "创建并生成激活链接"}</button>{activationLink && <p className="notice">一次性激活链接：<code>{activationLink}</code></p>}</form> : <form className="series-create" onSubmit={event => { event.preventDefault(); if (displayName.trim() && accountId) create.mutate(); }}><p>登记一位实际操作者（不设置密码；生产开户与一次性激活在 M5-4）。</p><input value={displayName} onChange={event => setDisplayName(event.target.value)} placeholder="自然人姓名或工作名" maxLength={80} /><select value={accountId} onChange={event => setAccountId(event.target.value)}><option value="">授予哪个企业发布账号</option>{accounts.data?.map(account => <option key={account.id} value={account.id}>{account.name}</option>)}</select><button className="primary" disabled={create.isPending}>{create.isPending ? "正在登记……" : "登记并授权操作人"}</button></form>}
    <section className="readiness-list">{operators.data?.map(operator => <article className="readiness-card ready" key={operator.id}><div><p className="eyebrow">{operator.manages_tenant ? "具备租户管理资格" : "业务操作人"}</p><h2>{operator.display_name}</h2><p>{operator.organization} · {operator.publishing_accounts || "尚未授予发布账号"}</p><small>{operator.default_persona ? `本人默认表达人设：${operator.default_persona}` : "尚未设置本人默认表达人设"}</small></div></article>)}</section>
  </>;
}

function ReadinessPanel(): JSX.Element {
  const client = useQueryClient();
  const readiness = useQuery({ queryKey: ["readiness"], queryFn: () => api<Readiness>("/api/v1/admin/readiness") });
  const expression = useQuery({ queryKey: ["brand-expression"], queryFn: () => api<BrandExpression>("/api/v1/admin/brand-expression") });
  const [draft, setDraft] = useState("");
  const confirm = useMutation({ mutationFn: () => api<BrandExpression>("/api/v1/admin/brand-expression/confirm", { method: "POST", body: JSON.stringify({ draft: draft || expression.data?.draft || "" }) }), onSuccess: () => { client.invalidateQueries({ queryKey: ["readiness"] }); client.invalidateQueries({ queryKey: ["brand-expression"] }); } });
  return <><header className="page-heading"><p className="eyebrow">企业管理</p><h1>入驻与就绪</h1><p>只列出现在真的会影响哪项能力的事项，不使用统一完成度。</p></header><section className="readiness-list">{readiness.isLoading ? <Loading label="正在读取当前就绪条件……" /> : readiness.data?.items.map(item => <article className={`readiness-card ${item.state}`} key={item.id}><div><p className="eyebrow">{item.state === "ready" ? "已具备" : "需要处理"}</p><h2>{item.title}</h2><p>{item.detail}</p><small>完成后：{item.unlock}</small></div>{item.id === "brand_expression" && item.state === "needs_action" && <button className="primary" onClick={() => document.getElementById("brand-expression")?.scrollIntoView({ behavior: "smooth" })}>确认草案</button>}</article>)}</section><section id="brand-expression" className="expression-card"><div><p className="eyebrow">品牌表达草案</p><h2>先判断“像不像我们”。</h2><p>这份草案可修改；未确认前不会被当成正式表达基线。</p></div><textarea defaultValue={expression.data?.draft ?? ""} onChange={event => setDraft(event.target.value)} aria-label="品牌表达草案" /><div className="expression-foot"><span>{expression.data?.status === "confirmed" ? `已确认 V${expression.data.version}` : "等待确认"}</span><button className="primary" onClick={() => confirm.mutate()} disabled={confirm.isPending}>{confirm.isPending ? "正在确认……" : "确认这版表达"}</button></div></section></>;
}

function SeriesPanel(): JSX.Element {
  const client = useQueryClient();
  const series = useQuery({ queryKey: ["series"], queryFn: () => api<Series[]>("/api/v1/content/series") });
  const recent = useQuery({ queryKey: ["series-candidates"], queryFn: () => api<RecentItem[]>("/api/v1/content/tasks") });
  const [title, setTitle] = useState("");
  const [premise, setPremise] = useState("");
  const create = useMutation({ mutationFn: () => api<Series>("/api/v1/content/series", { method: "POST", body: JSON.stringify({ title, premise }) }), onSuccess: () => { setTitle(""); setPremise(""); client.invalidateQueries({ queryKey: ["series"] }); } });
  const add = useMutation({ mutationFn: ({ seriesId, taskId }: { seriesId: string; taskId: string }) => api<Series>(`/api/v1/content/series/${seriesId}/items`, { method: "POST", body: JSON.stringify({ task_id: taskId }) }), onSuccess: () => client.invalidateQueries({ queryKey: ["series"] }) });
  const reorder = useMutation({ mutationFn: ({ seriesId, taskIds }: { seriesId: string; taskIds: string[] }) => api<Series>(`/api/v1/content/series/${seriesId}/items`, { method: "PUT", body: JSON.stringify({ task_ids: taskIds }) }), onSuccess: () => client.invalidateQueries({ queryKey: ["series"] }) });
  const reset = useMutation({ mutationFn: (id: string) => api<Series>(`/api/v1/content/series/${id}/reset`, { method: "POST", body: JSON.stringify({}) }), onSuccess: () => client.invalidateQueries({ queryKey: ["series"] }) });
  return <><header className="page-heading"><p className="eyebrow">连续系列</p><h1>系列由你决定怎样继续。</h1><p>可以跳集、插集、改序；只有明确要求承接前情时才会把它带入下一次内容。</p></header><form className="series-create" onSubmit={event => { event.preventDefault(); if (title.trim()) create.mutate(); }}><input value={title} onChange={event => setTitle(event.target.value)} placeholder="系列名称" maxLength={100} /><textarea value={premise} onChange={event => setPremise(event.target.value)} placeholder="这组内容想持续谈什么？（可选）" maxLength={500} /><button className="primary">新建系列</button></form><section className="series-grid">{series.data?.map(item => <SeriesCard key={item.id} item={item} candidates={recent.data ?? []} onAdd={(taskId) => add.mutate({ seriesId: item.id, taskId })} onMove={(from, to) => { const next = [...item.items]; const [moved] = next.splice(from, 1); next.splice(to, 0, moved); reorder.mutate({ seriesId: item.id, taskIds: next.map(entry => entry.task_id) }); }} onReset={() => reset.mutate(item.id)} />)}</section></>;
}

function SeriesCard({ item, candidates, onAdd, onMove, onReset }: { item: Series; candidates: RecentItem[]; onAdd: (taskId: string) => void; onMove: (from: number, to: number) => void; onReset: () => void }): JSX.Element {
  const [taskId, setTaskId] = useState("");
  const available = candidates.filter(candidate => !item.items.some(entry => entry.task_id === candidate.task_id));
  return <article className="series-card"><p className="eyebrow">{item.items.length} 集已明确安排</p><h2>{item.title}</h2><p>{item.premise || "还没有预设前情；每一集仍从当前任务开始。"}</p><ol>{item.items.map((entry, index) => <li key={`${entry.task_id}-${entry.position}`}><span>{entry.title}</span><span className="series-order"><button disabled={index === 0} onClick={() => onMove(index, index - 1)}>上移</button><button disabled={index === item.items.length - 1} onClick={() => onMove(index, index + 1)}>下移</button></span></li>)}</ol>{available.length > 0 && <div className="series-add"><select value={taskId} onChange={event => setTaskId(event.target.value)}><option value="">把已有成品插入系列</option>{available.map(candidate => <option key={candidate.task_id} value={candidate.task_id}>{candidate.title}</option>)}</select><button onClick={() => { if (taskId) { onAdd(taskId); setTaskId(""); } }}>插入</button></div>}<div><button onClick={onReset}>重置编排</button><span>不会删除已有成品</span></div></article>;
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
  return <nav className="version-rail" aria-label="版本历史"><span>版本</span>{versions.map(item => <button key={item.version_id} className={item.version === currentVersion ? "current" : ""} onClick={() => onSelect(item)}>V{item.version}</button>)}</nav>;
}

function RecentList({ items, loading, onOpen }: { items: RecentItem[]; loading: boolean; onOpen: (item: RecentItem) => void }): JSX.Element { if (loading) return <p className="muted">正在读取……</p>; if (!items.length) return <p className="muted">第一份成品做好后会出现在这里。</p>; return <ul className="recent-list" id="recent">{items.map(item => <li key={item.version_id}><button onClick={() => onOpen(item)}><strong>{item.title}</strong><span>V{item.version} · {item.updated_at}</span></button></li>)}</ul>; }
function ArtifactText({ value }: { value: string }): JSX.Element { return <article className="artifact-text">{value.split("\n").filter(Boolean).map((paragraph, index) => paragraph.startsWith("#") ? <h3 key={`${paragraph}-${index}`}>{paragraph.replace(/^#+\s*/, "")}</h3> : <p key={`${paragraph}-${index}`}>{paragraph}</p>)}</article>; }
function EmptyArtifact({ title, detail }: { title: string; detail: string }): JSX.Element { return <div className="empty-artifact"><span>笛语</span><h2>{title}</h2><p>{detail}</p></div>; }
function Notice({ value, onDismiss }: { value: string; onDismiss: () => void }): JSX.Element { return <div className="notice" role="status"><span>{value}</span><button aria-label="关闭提示" onClick={onDismiss}>×</button></div>; }
function Loading({ label }: { label: string }): JSX.Element { return <div className="loading" role="status">{label}</div>; }
function MobileTabs({ first, second, value, onChange }: { first: string; second: string; value: "conversation" | "artifact"; onChange: (value: "conversation" | "artifact") => void }): JSX.Element { return <nav className="mobile-tabs" aria-label="移动端工作面"><button className={value === "conversation" ? "active" : ""} onClick={() => onChange("conversation")}>{first}</button><button className={value === "artifact" ? "active" : ""} onClick={() => onChange("artifact")}>{second}</button></nav>; }

function Root(): JSX.Element { return <App />; }

export default Root;
