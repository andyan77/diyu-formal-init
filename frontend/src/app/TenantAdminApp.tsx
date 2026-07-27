import { useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent, JSX, KeyboardEvent as ReactKeyboardEvent } from "react";
import { BrandMark } from "../components/Brand";
import { api } from "../services/api";
import "../styles/tenant-admin.css";
import type { BootstrapContext } from "./types";

type Section = "overview" | "members" | "accounts" | "brand" | "readiness";
type Notice = { tone: "success" | "error"; message: string } | null;

type ReadinessItem = { id: string; title: string; detail: string; unlock: string; state: "ready" | "needs_action" };
type Operator = {
  id: string;
  display_name: string;
  username: string;
  organization_id: string;
  organization: string;
  publishing_accounts: string;
  manages_tenant: boolean;
  maintains_organization_materials: boolean;
  account_grants: Array<{
    account_id: string;
    account_name: string;
    can_maintain_expression_profile: boolean;
  }>;
};
type Organization = { id: string; name: string; business_data_kind?: string };
type Account = {
  id: string;
  name: string;
  channel: string;
  content_role: string;
  voice_boundary: string;
  carrier_of_account_id: string | null;
  carrier_of_account: string | null;
  operators: Array<{ id: string; display_name: string }>;
};
type Product = {
  sku: string;
  display_name: string;
  facts: Record<string, unknown>;
  source_note: string;
  applicability: string;
  fact_version: number;
};
type Expression = { version: number; status: "draft" | "confirmed"; draft: string };
type OrganizationMaterial = {
  id: string;
  title: string;
  media_type: string;
  original_filename: string;
  byte_size: number;
  reference_note: string;
  organization_id: string;
  organization: string;
};
type Profile = {
  account: string;
  content_role: string;
  control_organization?: string | null;
  control_organization_source?: string;
  can_maintain?: boolean;
  can_declare?: boolean;
  current: {
    version: number;
    identity_position: string;
    authority_boundary: string;
    audience_relationship: string;
    content_territories: string;
    default_production_conditions: string;
  } | null;
  draft?: {
    identity_position: string;
    authority_boundary: string;
    audience_relationship: string;
    content_territories: string;
    default_production_conditions: string;
  } | null;
};

const sections: Array<{ id: Section; label: string }> = [
  { id: "overview", label: "概览与待处理" },
  { id: "members", label: "成员与权限" },
  { id: "accounts", label: "发布账号" },
  { id: "brand", label: "品牌、商品与组织素材" },
  { id: "readiness", label: "生产就绪与缺口" }
];

type RequestState<T> = {
  data: T | null;
  error: string | null;
  loading: boolean;
  refresh: () => Promise<void>;
};

function readableRequestError(error: unknown): string {
  return error instanceof Error ? error.message : "当前内容暂时无法读取。";
}

function useRequest<T>(path: string, enabled = true): RequestState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(enabled);
  const refresh = async (): Promise<void> => {
    if (!enabled) return;
    setLoading(true);
    setError(null);
    try {
      setData(await api<T>(path));
    } catch (caught) {
      setData(null);
      setError(readableRequestError(caught));
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { void refresh(); }, [path, enabled]); // eslint-disable-line react-hooks/exhaustive-deps
  return { data, error, refresh, loading };
}

async function filePayload(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("无法读取这份素材。"));
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1] ?? "");
    reader.readAsDataURL(file);
  });
}

function PageNotice({ notice, onDismiss }: { notice: Notice; onDismiss: () => void }): JSX.Element | null {
  if (!notice) return null;
  return <div className={`tenant-notice ${notice.tone}`} role="status"><span>{notice.message}</span><button type="button" onClick={onDismiss}>知道了</button></div>;
}

function RequestFailure({ message, onRetry }: { message: string; onRetry: () => Promise<void> }): JSX.Element {
  return <div className="tenant-request-failure" role="alert">
    <p>{message}</p>
    <button type="button" className="text-action" onClick={() => void onRetry()}>重新读取</button>
  </div>;
}

function Drawer({ title, children, onClose }: { title: string; children: JSX.Element | JSX.Element[]; onClose: () => void }): JSX.Element {
  const panel = useRef<HTMLElement>(null);
  const close = useRef<HTMLButtonElement>(null);
  const returnFocus = useRef<HTMLElement | null>(
    document.activeElement instanceof HTMLElement ? document.activeElement : null
  );
  useEffect(() => {
    close.current?.focus();
    return () => returnFocus.current?.focus();
  }, []);
  const handleKeyDown = (event: ReactKeyboardEvent<HTMLElement>): void => {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
      return;
    }
    if (event.key !== "Tab") return;
    const focusable = Array.from(
      panel.current?.querySelectorAll<HTMLElement>(
        "button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled)"
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
  return <div className="tenant-drawer-backdrop" role="presentation" onMouseDown={onClose}>
    <section ref={panel} className="tenant-drawer" role="dialog" aria-modal="true" aria-label={title} onMouseDown={event => event.stopPropagation()} onKeyDown={handleKeyDown}>
      <header><h2>{title}</h2><button ref={close} type="button" className="quiet" onClick={onClose}>关闭</button></header>
      {children}
    </section>
  </div>;
}

function NeedList({ items, compact = false }: { items: ReadinessItem[]; compact?: boolean }): JSX.Element {
  if (items.length === 0) return <p className="tenant-empty">当前没有需要处理的资料。</p>;
  return <div className={compact ? "need-list compact" : "need-list"}>{items.map(item => <article key={item.id}>
    <div><p className="tenant-kicker">需要处理</p><h2>{item.title}</h2><p>{item.detail}</p></div>
    {!compact && <small>完成后可：{item.unlock}</small>}
  </article>)}</div>;
}

function Overview({ onSection }: { onSection: (section: Section) => void }): JSX.Element {
  const readiness = useRequest<{ items: ReadinessItem[] }>("/api/v1/admin/readiness");
  const missing = (readiness.data?.items ?? []).filter(item => item.state === "needs_action").slice(0, 3);
  return <section className="tenant-page"><header className="tenant-heading"><p className="eyebrow">品牌管理</p><h1>先处理眼前需要补的资料</h1><p>成员、账号和资料都在当前品牌范围内维护。</p></header>
    {readiness.loading ? <p className="tenant-loading">正在读取当前资料……</p> : readiness.error ? <RequestFailure message={readiness.error} onRetry={readiness.refresh} /> : <NeedList items={missing} />}
    <div className="tenant-next"><div><h2>从哪里开始？</h2><p>先看缺什么，再决定要补哪一项。</p></div><button className="primary" type="button" onClick={() => onSection("readiness")}>查看全部缺口</button></div>
  </section>;
}

function Members({ setNotice, currentUserId }: { setNotice: (notice: Notice) => void; currentUserId: string }): JSX.Element {
  const operators = useRequest<Operator[]>("/api/v1/tenant-management/operators");
  const organizations = useRequest<Organization[]>("/api/v1/tenant-management/organizations");
  const accounts = useRequest<Account[]>("/api/v1/tenant-management/publishing-accounts");
  const [drawer, setDrawer] = useState<"create" | Operator | null>(null);
  const [activationLink, setActivationLink] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [name, setName] = useState("");
  const [username, setUsername] = useState("");
  const [organizationId, setOrganizationId] = useState("");
  const [accountId, setAccountId] = useState("");
  const [grantsManagement, setGrantsManagement] = useState(false);
  const [grantsMaterials, setGrantsMaterials] = useState(false);
  const [grantsProfile, setGrantsProfile] = useState(false);
  const [grantAccountId, setGrantAccountId] = useState("");
  const [grantAccess, setGrantAccess] = useState(false);
  const refresh = async (): Promise<void> => { await Promise.all([operators.refresh(), accounts.refresh()]); };
  const requestError = operators.error ?? organizations.error ?? accounts.error;
  const requestLoading = operators.loading || organizations.loading || accounts.loading;
  const retryDependencies = async (): Promise<void> => {
    await Promise.all([operators.refresh(), organizations.refresh(), accounts.refresh()]);
  };
  const run = async (action: () => Promise<void>, message: string): Promise<void> => {
    setSaving(true);
    try { await action(); await refresh(); setNotice({ tone: "success", message }); } catch (error) { setNotice({ tone: "error", message: error instanceof Error ? error.message : "当前操作没有完成。" }); } finally { setSaving(false); }
  };
  const submit = (event: FormEvent): void => {
    event.preventDefault();
    void run(async () => {
      const created = await api<{ activation_link: string }>("/api/v1/tenant-management/users", { method: "POST", body: JSON.stringify({
        display_name: name, username, organization_id: organizationId || null, account_id: accountId || null,
        grants_tenant_management: grantsManagement, grants_material_maintenance: grantsMaterials,
        grants_expression_profile_maintenance: grantsProfile
      }) });
      setActivationLink(created.activation_link);
      setName(""); setUsername(""); setOrganizationId(""); setAccountId(""); setGrantsManagement(false); setGrantsMaterials(false); setGrantsProfile(false);
    }, "成员已建立。请只通过本次显示的体验链接交给本人。");
  };
  const openMember = (member: Operator): void => {
    const firstGrant = member.account_grants[0];
    setActivationLink(null);
    setGrantAccountId(firstGrant?.account_id ?? "");
    setGrantAccess(Boolean(firstGrant));
    setGrantsProfile(Boolean(firstGrant?.can_maintain_expression_profile));
    setGrantsManagement(member.manages_tenant);
    setGrantsMaterials(member.maintains_organization_materials);
    setDrawer(member);
  };
  const chooseAccountGrant = (member: Operator, nextAccountId: string): void => {
    const existing = member.account_grants.find(grant => grant.account_id === nextAccountId);
    setGrantAccountId(nextAccountId);
    setGrantAccess(Boolean(existing));
    setGrantsProfile(Boolean(existing?.can_maintain_expression_profile));
  };
  const memberAccessSummary = (member: Operator): string => {
    const access: string[] = [];
    if (member.account_grants.length > 0) access.push(`可使用 ${member.account_grants.length} 个发布账号`);
    if (member.manages_tenant) access.push("可进入品牌管理");
    if (member.maintains_organization_materials) access.push("可维护组织素材");
    return access.join(" · ") || "尚未分配工作资格";
  };
  return <section className="tenant-page"><header className="tenant-heading split"><div><p className="eyebrow">成员与权限</p><h1>谁能在这里工作</h1><p>每位成员使用自己的登录身份；发布账号不是登录账号。</p></div><button className="primary" type="button" disabled={requestLoading || Boolean(requestError)} onClick={() => { setActivationLink(null); setAccountId(""); setGrantsManagement(false); setGrantsMaterials(false); setGrantsProfile(false); setDrawer("create"); }}>添加成员</button></header>
    {requestLoading ? <p className="tenant-loading">正在读取成员……</p> : requestError ? <RequestFailure message={requestError} onRetry={retryDependencies} /> : <div className="tenant-list">{operators.data?.map(member => <article key={member.id}><div><h2>{member.display_name}</h2><p>{member.organization}{member.publishing_accounts ? ` · ${member.publishing_accounts}` : " · 尚未分配发布账号"}</p><small>{memberAccessSummary(member)}{member.username ? ` · ${member.username}` : ""}</small></div><button type="button" className="text-action" onClick={() => openMember(member)}>查看与处理</button></article>)}</div>}
    {drawer === "create" && <Drawer title="添加成员" onClose={() => setDrawer(null)}><form className="tenant-form" onSubmit={submit}><label>姓名或工作名<input required value={name} onChange={event => setName(event.target.value)} maxLength={80} /></label><label>登录用户名<input required value={username} onChange={event => setUsername(event.target.value)} minLength={3} maxLength={80} /></label><label>所属组织<select value={organizationId} onChange={event => setOrganizationId(event.target.value)}><option value="">使用当前管理组织</option>{organizations.data?.map(org => <option key={org.id} value={org.id}>{org.name}</option>)}</select></label><label>发布账号（可稍后分配）<select value={accountId} onChange={event => { setAccountId(event.target.value); if (!event.target.value) setGrantsProfile(false); }}><option value="">暂不分配</option>{accounts.data?.filter(account => !account.carrier_of_account_id).map(account => <option key={account.id} value={account.id}>{account.name}</option>)}</select></label><fieldset><legend>额外资格</legend><label><input type="checkbox" checked={grantsManagement} onChange={event => setGrantsManagement(event.target.checked)} />可进入品牌管理</label><label><input type="checkbox" checked={grantsMaterials} onChange={event => setGrantsMaterials(event.target.checked)} />可维护所属组织素材</label><label><input type="checkbox" checked={grantsProfile} disabled={!accountId} onChange={event => setGrantsProfile(event.target.checked)} />可维护所选账号定位</label></fieldset><button className="primary" disabled={saving} type="submit">创建并生成体验链接</button>{activationLink && <OneTimeLink link={activationLink} />}</form></Drawer>}
    {drawer && drawer !== "create" && <Drawer title={drawer.display_name} onClose={() => setDrawer(null)}><div className="tenant-detail"><p>{drawer.organization} · {drawer.publishing_accounts || "尚未分配发布账号"}</p>{drawer.username && <button className="text-action" type="button" disabled={saving} onClick={() => void run(async () => { const value = await api<{ reset_link: string }>(`/api/v1/tenant-management/users/${drawer.id}/reset`, { method: "POST" }); setActivationLink(value.reset_link); }, "已生成新的体验链接；此前未使用的链接已失效。")}>生成新的体验链接</button>}{activationLink && <OneTimeLink link={activationLink} />}<hr /><fieldset className="member-grants"><legend>成员资格</legend><label>发布账号<select value={grantAccountId} onChange={event => chooseAccountGrant(drawer, event.target.value)}><option value="">暂不分配发布账号</option>{accounts.data?.filter(account => !account.carrier_of_account_id).map(account => <option key={account.id} value={account.id}>{account.name}</option>)}</select></label><label><input type="checkbox" checked={grantAccess} disabled={!grantAccountId} onChange={event => { setGrantAccess(event.target.checked); if (!event.target.checked) setGrantsProfile(false); }} />可使用所选发布账号</label><label><input type="checkbox" checked={grantsProfile} disabled={!grantAccountId || !grantAccess} onChange={event => setGrantsProfile(event.target.checked)} />可维护所选账号定位</label><label><input type="checkbox" checked={grantsManagement} onChange={event => setGrantsManagement(event.target.checked)} />可进入品牌管理</label><label><input type="checkbox" checked={grantsMaterials} onChange={event => setGrantsMaterials(event.target.checked)} />可维护所属组织素材</label><button className="primary" type="button" disabled={saving} onClick={() => void run(() => api(`/api/v1/tenant-management/users/${drawer.id}/grants`, { method: "PATCH", body: JSON.stringify({ account_id: grantAccountId || null, grants_account_access: grantAccess, grants_tenant_management: grantsManagement, grants_material_maintenance: grantsMaterials, grants_expression_profile_maintenance: grantsProfile }) }), "成员资格已更新；该成员需要重新登录后继续工作。")}>保存成员资格</button></fieldset>{drawer.id !== currentUserId && <><hr /><button className="text-action danger" type="button" disabled={saving} onClick={() => void run(() => api(`/api/v1/tenant-management/users/${drawer.id}/disable`, { method: "POST" }), "该成员已停用，现有会话与工作资格已同时撤销。")}>停用成员</button></>}</div></Drawer>}
  </section>;
}

function OneTimeLink({ link }: { link: string }): JSX.Element {
  const [copied, setCopied] = useState(false);
  return <div className="one-time-link"><p>这是一次性体验链接。请现在安全转交给本人；关闭此处后不会再显示。</p><code>{link}</code><button type="button" className="text-action" onClick={() => { void navigator.clipboard?.writeText(link); setCopied(true); }}>{copied ? "已复制" : "复制链接"}</button></div>;
}

function Accounts({ setNotice }: { setNotice: (notice: Notice) => void }): JSX.Element {
  const accounts = useRequest<Account[]>("/api/v1/tenant-management/publishing-accounts");
  const operators = useRequest<Operator[]>("/api/v1/tenant-management/operators");
  const organizations = useRequest<Organization[]>("/api/v1/tenant-management/control-organizations");
  const [selected, setSelected] = useState<Account | null>(null);
  const [drawer, setDrawer] = useState<"create" | "carrier" | "profile" | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [saving, setSaving] = useState(false);
  const [accountForm, setAccountForm] = useState({ name: "", channel: "抖音", role: "", boundary: "", operatorId: "", organizationId: "", profileGrant: false });
  const [segments, setSegments] = useState<Record<string, string>>({ identity_position: "", authority_boundary: "", audience_relationship: "", content_territories: "", default_production_conditions: "" });
  const [carrier, setCarrier] = useState({ name: "", channel: "小红书", operatorId: "" });
  const requestError = accounts.error ?? operators.error ?? organizations.error;
  const requestLoading = accounts.loading || operators.loading || organizations.loading;
  const retryDependencies = async (): Promise<void> => {
    await Promise.all([accounts.refresh(), operators.refresh(), organizations.refresh()]);
  };
  const showProfile = async (account: Account): Promise<void> => {
    setSelected(account); setProfile(null);
    try {
      const value = await api<Profile>(`/api/v1/tenant-management/publishing-accounts/${account.id}/expression-profile`);
      setProfile(value);
      const source = value.current ?? value.draft;
      if (source) setSegments({
        identity_position: source.identity_position,
        authority_boundary: source.authority_boundary,
        audience_relationship: source.audience_relationship,
        content_territories: source.content_territories,
        default_production_conditions: source.default_production_conditions
      });
    } catch (error) { setNotice({ tone: "error", message: error instanceof Error ? error.message : "暂时无法读取账号定位。" }); }
  };
  const run = async (action: () => Promise<void>, message: string): Promise<void> => { setSaving(true); try { await action(); await accounts.refresh(); if (selected) await showProfile(selected); setNotice({ tone: "success", message }); } catch (error) { setNotice({ tone: "error", message: error instanceof Error ? error.message : "当前操作没有完成。" }); } finally { setSaving(false); } };
  const openProfile = async (account: Account): Promise<void> => { await showProfile(account); setDrawer("profile"); };
  return <section className="tenant-page"><header className="tenant-heading split"><div><p className="eyebrow">发布账号</p><h1>让每个账号说自己的话</h1><p>账号、表达身份和实际使用者分开维护。</p></div><button className="primary" type="button" disabled={requestLoading || Boolean(requestError)} onClick={() => setDrawer("create")}>创建发布账号</button></header>
    {requestLoading ? <p className="tenant-loading">正在读取发布账号……</p> : requestError ? <RequestFailure message={requestError} onRetry={retryDependencies} /> : <div className="account-list">{accounts.data?.filter(account => !account.carrier_of_account_id).map(account => <article key={account.id}><div><p className="tenant-kicker">{account.channel}</p><h2>{account.name}</h2><p>{account.content_role}</p><small>{account.operators.map(operator => operator.display_name).join("、") || "尚未分配实际使用者"}</small></div><div className="account-actions"><button type="button" className="text-action" onClick={() => void openProfile(account)}>查看账号定位</button><button type="button" className="text-action" onClick={() => { setSelected(account); setCarrier({ name: `${account.name}·小红书`, channel: "小红书", operatorId: account.operators[0]?.id ?? "" }); setDrawer("carrier"); }}>添加平台版本</button></div></article>)}</div>}
    {drawer === "create" && <Drawer title="创建发布账号" onClose={() => setDrawer(null)}><form className="tenant-form" onSubmit={event => { event.preventDefault(); void run(async () => { await api("/api/v1/tenant-management/publishing-accounts", { method: "POST", body: JSON.stringify({ name: accountForm.name, channel: accountForm.channel, content_role_name: accountForm.role, voice_boundary: accountForm.boundary, operator_id: accountForm.operatorId, control_organization_id: accountForm.organizationId || null, operator_can_maintain_expression_profile: accountForm.profileGrant }) }); setDrawer(null); }, "发布账号已建立。接下来可补充账号定位。"); }}><label>账号名称<input required value={accountForm.name} onChange={event => setAccountForm({ ...accountForm, name: event.target.value })} /></label><label>主要平台<select value={accountForm.channel} onChange={event => setAccountForm({ ...accountForm, channel: event.target.value })}><option>抖音</option><option>小红书</option><option>微信视频号</option></select></label><label>表达身份<input required value={accountForm.role} onChange={event => setAccountForm({ ...accountForm, role: event.target.value })} placeholder="例如：品牌官方" /></label><label>表达边界<textarea required value={accountForm.boundary} onChange={event => setAccountForm({ ...accountForm, boundary: event.target.value })} /></label><label>实际使用者<select required value={accountForm.operatorId} onChange={event => setAccountForm({ ...accountForm, operatorId: event.target.value })}><option value="">请选择成员</option>{operators.data?.map(operator => <option key={operator.id} value={operator.id}>{operator.display_name}</option>)}</select></label><label>负责团队（可稍后声明）<select value={accountForm.organizationId} onChange={event => setAccountForm({ ...accountForm, organizationId: event.target.value })}><option value="">暂不声明</option>{organizations.data?.map(org => <option key={org.id} value={org.id}>{org.name}</option>)}</select></label><label><input type="checkbox" checked={accountForm.profileGrant} onChange={event => setAccountForm({ ...accountForm, profileGrant: event.target.checked })} />允许所选成员维护账号定位</label><button className="primary" type="submit" disabled={saving}>创建发布账号</button></form></Drawer>}
    {drawer === "carrier" && selected && <Drawer title="添加平台版本" onClose={() => setDrawer(null)}><form className="tenant-form" onSubmit={event => { event.preventDefault(); void run(async () => { await api("/api/v1/tenant-management/platform-carriers", { method: "POST", body: JSON.stringify({ source_account_id: selected.id, name: carrier.name, channel: carrier.channel, operator_id: carrier.operatorId, confirm_internal_carrier: true }) }); setDrawer(null); }, "平台版本已建立；没有连接任何平台账号。"); }}><p>平台版本沿用当前账号的表达身份，只用于整理不同平台的内容版本。</p><label>名称<input required value={carrier.name} onChange={event => setCarrier({ ...carrier, name: event.target.value })} /></label><label>目标平台<select value={carrier.channel} onChange={event => setCarrier({ ...carrier, channel: event.target.value })}><option>抖音</option><option>小红书</option><option>微信视频号</option></select></label><label>实际使用者<select required value={carrier.operatorId} onChange={event => setCarrier({ ...carrier, operatorId: event.target.value })}><option value="">请选择成员</option>{operators.data?.map(operator => <option key={operator.id} value={operator.id}>{operator.display_name}</option>)}</select></label><button className="primary" type="submit" disabled={saving}>添加平台版本</button></form></Drawer>}
    {drawer === "profile" && selected && <Drawer title={`${selected.name}的账号定位`} onClose={() => setDrawer(null)}><div className="tenant-form">{profile?.current ? <><p>当前为第 {profile.current.version} 版。</p><ProfileFields values={profile.current} onChange={() => undefined} readOnly /></> : <p>还没有保存账号定位；可以从这份草案开始修改。</p>}{profile?.can_declare && <label>负责团队<select onChange={event => { const organizationId = event.target.value; if (organizationId) void run(() => api(`/api/v1/tenant-management/publishing-accounts/${selected.id}/control-organization`, { method: "POST", body: JSON.stringify({ organization_id: organizationId }) }), "已声明负责团队。现在可以维护账号定位。"); }} defaultValue=""><option value="">选择负责团队</option>{organizations.data?.map(org => <option key={org.id} value={org.id}>{org.name}</option>)}</select></label>}{profile?.can_maintain && <><hr /><p>新版本会保留旧版本，不会改写已经完成的内容。</p><ProfileFields values={segments} onChange={(key, value) => setSegments({ ...segments, [key]: value })} /><button className="primary" type="button" disabled={saving} onClick={() => void run(async () => { await api(`/api/v1/tenant-management/publishing-accounts/${selected.id}/expression-profile/versions`, { method: "POST", body: JSON.stringify(segments) }); setDrawer(null); }, "账号定位已保存为新版本。")}>保存新的账号定位</button></>}</div></Drawer>}
  </section>;
}

function ProfileFields({ values, onChange, readOnly = false }: { values: Record<string, string | number>; onChange: (key: string, value: string) => void; readOnly?: boolean }): JSX.Element {
  const labels: Array<[string, string]> = [["identity_position", "表达身份"], ["authority_boundary", "能代表什么"], ["audience_relationship", "和谁说话"], ["content_territories", "主要讲什么"], ["default_production_conditions", "长期制作条件"]];
  return <>{labels.map(([key, label]) => <label key={key}>{label}{readOnly ? <p className="profile-read">{String(values[key] ?? "")}</p> : <textarea required value={String(values[key] ?? "")} onChange={event => onChange(key, event.target.value)} />}</label>)}</>;
}

function Brand({ setNotice }: { setNotice: (notice: Notice) => void }): JSX.Element {
  const expression = useRequest<Expression>("/api/v1/admin/brand-expression");
  const products = useRequest<Product[]>("/api/v1/tenant-management/brand-products");
  const organizations = useRequest<Organization[]>("/api/v1/tenant-management/organizations");
  const materials = useRequest<OrganizationMaterial[]>("/api/v1/tenant-management/organization-materials");
  const [draft, setDraft] = useState("");
  const [drawer, setDrawer] = useState<"product" | "material" | "organization" | null>(null);
  const [saving, setSaving] = useState(false);
  const [product, setProduct] = useState({ sku: "", display_name: "", category: "", colors: "", material_or_structure: "", silhouette: "", observable_features: "", source_note: "", applicability: "" });
  const [materialOrganizationId, setMaterialOrganizationId] = useState("");
  const [materialTitle, setMaterialTitle] = useState("");
  const [materialNote, setMaterialNote] = useState("");
  const [materialFile, setMaterialFile] = useState<File | null>(null);
  const [materialMinor, setMaterialMinor] = useState(false);
  const [organizationName, setOrganizationName] = useState("");
  useEffect(() => { if (expression.data) setDraft(expression.data.draft); }, [expression.data]);
  const run = async (action: () => Promise<void>, message: string): Promise<void> => { setSaving(true); try { await action(); await Promise.all([expression.refresh(), products.refresh(), materials.refresh(), organizations.refresh()]); setNotice({ tone: "success", message }); } catch (error) { setNotice({ tone: "error", message: error instanceof Error ? error.message : "当前操作没有完成。" }); } finally { setSaving(false); } };
  const requestError = expression.error ?? products.error ?? organizations.error ?? materials.error;
  return <section className="tenant-page"><header className="tenant-heading"><p className="eyebrow">品牌与资料</p><h1>把当前能确认的资料留在这里</h1><p>商品资料只记录本轮真正需要的可观察事实。</p></header>{requestError ? <RequestFailure message={requestError} onRetry={async () => { await Promise.all([expression.refresh(), products.refresh(), organizations.refresh(), materials.refresh()]); }} /> : <div className="brand-layout"><section className="tenant-subsection"><header><h2>品牌表达</h2><span>{expression.data?.status === "confirmed" ? `当前第 ${expression.data.version} 版` : "等待确认"}</span></header><textarea aria-label="品牌表达" value={draft} onChange={event => setDraft(event.target.value)} /><button className="primary" type="button" disabled={saving || draft.trim().length < 8} onClick={() => void run(() => api("/api/v1/admin/brand-expression/confirm", { method: "POST", body: JSON.stringify({ draft }) }), "品牌表达已保存为当前版本。")}>确认这版表达</button></section><section className="tenant-subsection"><header><h2>商品资料</h2><button type="button" className="text-action" onClick={() => setDrawer("product")}>添加商品</button></header>{products.data?.length ? <div className="product-list">{products.data.map(item => <article key={item.sku}><strong>{item.display_name}</strong><span>{item.sku} · 第 {item.fact_version} 版</span><p>{item.applicability}</p></article>)}</div> : <p className="tenant-empty">还没有可确认的商品资料。</p>}</section><section className="tenant-subsection material-guidance"><header><h2>团队与组织素材</h2><div className="tenant-header-actions"><button type="button" className="text-action" onClick={() => { setOrganizationName(""); setDrawer("organization"); }}>添加团队</button><button type="button" className="text-action" onClick={() => { setMaterialFile(null); setMaterialTitle(""); setMaterialNote(""); setMaterialMinor(false); setDrawer("material"); }}>添加组织素材</button></div></header><p>这里只管理归属团队的参考素材；成员的私人素材不会在这里出现。</p>{materials.data?.length ? <div className="material-list">{materials.data.map(item => <article key={item.id}><div><strong>{item.title}</strong><span>{item.organization} · {item.original_filename}</span>{item.reference_note && <p>说明：{item.reference_note}</p>}</div><button className="text-action danger" type="button" disabled={saving} onClick={() => void run(() => api(`/api/v1/tenant-management/organization-materials/${item.id}`, { method: "DELETE" }), "组织素材已移除。")}>移除</button></article>)}</div> : <p className="tenant-empty">还没有组织素材。</p>}</section></div>}{drawer === "product" && <Drawer title="添加商品资料" onClose={() => setDrawer(null)}><form className="tenant-form" onSubmit={event => { event.preventDefault(); void run(async () => { await api("/api/v1/tenant-management/brand-products", { method: "PUT", body: JSON.stringify({ ...product, colors: product.colors.split(/[，,]/).map(value => value.trim()).filter(Boolean), confirm_as_current_brand_fact: true }) }); setDrawer(null); }, "商品资料已保存为当前版本。"); }}><label>商品编号<input required value={product.sku} onChange={event => setProduct({ ...product, sku: event.target.value })} /></label><label>商品名称<input required value={product.display_name} onChange={event => setProduct({ ...product, display_name: event.target.value })} /></label><label>品类<input value={product.category} onChange={event => setProduct({ ...product, category: event.target.value })} /></label><label>颜色（用逗号分隔）<input value={product.colors} onChange={event => setProduct({ ...product, colors: event.target.value })} /></label><label>材质或结构<textarea value={product.material_or_structure} onChange={event => setProduct({ ...product, material_or_structure: event.target.value })} /></label><label>轮廓<input value={product.silhouette} onChange={event => setProduct({ ...product, silhouette: event.target.value })} /></label><label>肉眼可见特征<textarea value={product.observable_features} onChange={event => setProduct({ ...product, observable_features: event.target.value })} /></label><label>资料来源说明<textarea required value={product.source_note} onChange={event => setProduct({ ...product, source_note: event.target.value })} /></label><label>适用范围<textarea required value={product.applicability} onChange={event => setProduct({ ...product, applicability: event.target.value })} /></label><button className="primary" type="submit" disabled={saving}>保存商品资料</button></form></Drawer>}{drawer === "material" && <Drawer title="添加组织素材" onClose={() => setDrawer(null)}><form className="tenant-form" onSubmit={event => { event.preventDefault(); if (!materialFile) return; void run(async () => { await api("/api/v1/tenant-management/organization-materials", { method: "POST", body: JSON.stringify({ organization_id: materialOrganizationId, title: materialTitle, filename: materialFile.name, content_type: materialFile.type || "application/octet-stream", content_base64: await filePayload(materialFile), declares_identifiable_minor: materialMinor, reference_note: materialNote }) }); setDrawer(null); }, "组织素材已保存。只有创作时明确选择，才会被参考。"); }}><label>归属团队<select required value={materialOrganizationId} onChange={event => setMaterialOrganizationId(event.target.value)}><option value="">选择团队</option>{organizations.data?.map(org => <option key={org.id} value={org.id}>{org.name}</option>)}</select></label><label>素材名称<input required value={materialTitle} onChange={event => setMaterialTitle(event.target.value)} /></label><label>选择原件<input required type="file" onChange={event => setMaterialFile(event.target.files?.[0] ?? null)} /></label><label>人工说明（图片、视频或声音需要）<textarea value={materialNote} onChange={event => setMaterialNote(event.target.value)} placeholder="说明这份素材在本次创作中可参考什么。" /></label><label><input type="checkbox" checked={materialMinor} onChange={event => setMaterialMinor(event.target.checked)} />原件中有可识别的真人未成年人</label><button className="primary" type="submit" disabled={saving || !materialFile}>保存组织素材</button></form></Drawer>}{drawer === "organization" && <Drawer title="添加团队" onClose={() => setDrawer(null)}><form className="tenant-form" onSubmit={event => { event.preventDefault(); void run(async () => { await api("/api/v1/tenant-management/organizations", { method: "POST", body: JSON.stringify({ name: organizationName, as_synthetic_business_fixture: false }) }); setDrawer(null); }, "团队已添加，现在可以为成员分配团队或保存组织素材。"); }}><p>只添加当前品牌实际需要的团队或门店。</p><label>团队名称<input required value={organizationName} onChange={event => setOrganizationName(event.target.value)} maxLength={120} /></label><button className="primary" type="submit" disabled={saving}>添加团队</button></form></Drawer>}</section>;
}

function Readiness(): JSX.Element {
  const readiness = useRequest<{ items: ReadinessItem[] }>("/api/v1/admin/readiness");
  const missing = (readiness.data?.items ?? []).filter(item => item.state === "needs_action");
  const available = (readiness.data?.items ?? []).filter(item => item.state === "ready");
  return <section className="tenant-page"><header className="tenant-heading"><p className="eyebrow">生产就绪与缺口</p><h1>只看会影响当前工作的资料</h1><p>不同工作需要的资料不同；缺少一项不代表其他工作不能继续。</p></header>{readiness.loading ? <p className="tenant-loading">正在读取资料……</p> : readiness.error ? <RequestFailure message={readiness.error} onRetry={readiness.refresh} /> : <><NeedList items={missing} />{available.length > 0 && <details className="available-details"><summary>已具备的资料（{available.length}）</summary><ul>{available.map(item => <li key={item.id}><strong>{item.title}</strong><span>{item.detail}</span></li>)}</ul></details>}</>}</section>;
}

export default function TenantAdminApp({ context }: { context: BootstrapContext }): JSX.Element {
  const [section, setSection] = useState<Section>("overview");
  const [notice, setNotice] = useState<Notice>(null);
  const identity = context.identity ?? {};
  const title = useMemo(() => identity.brand ?? "品牌管理", [identity.brand]);
  return <div className="tenant-admin-app"><aside className="tenant-nav"><a href="/tenant-admin" aria-label="回到品牌管理首页"><BrandMark /></a><p className="tenant-nav-title">品牌管理</p><nav aria-label="品牌管理导航">{sections.map(item => <button type="button" key={item.id} className={section === item.id ? "active" : ""} aria-current={section === item.id ? "page" : undefined} onClick={() => { setNotice(null); setSection(item.id); }}>{item.label}</button>)}</nav><form method="post" action="/tenant-admin/logout"><button type="submit" className="quiet">退出</button></form></aside><main><header className="tenant-topbar"><span>{title}</span><span>{identity.operator ?? ""}</span></header><PageNotice notice={notice} onDismiss={() => setNotice(null)} />{section === "overview" && <Overview onSection={setSection} />}{section === "members" && <Members setNotice={setNotice} currentUserId={identity.operator_id ?? ""} />}{section === "accounts" && <Accounts setNotice={setNotice} />}{section === "brand" && <Brand setNotice={setNotice} />}{section === "readiness" && <Readiness />}</main></div>;
}
