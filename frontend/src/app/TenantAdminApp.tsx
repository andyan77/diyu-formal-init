import { useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent, JSX, KeyboardEvent as ReactKeyboardEvent } from "react";
import { BrandMark } from "../components/Brand";
import { ApiError, api } from "../services/api";
import "../styles/tenant-admin.css";
import type { BootstrapContext, Target } from "./types";

type Section =
  | "overview"
  | "usage"
  | "members"
  | "accounts"
  | "library"
  | "readiness";
type Notice = { tone: "success" | "error"; message: string } | null;
type EntryType = "tenant_admin" | "tenant_user";

type Organization = {
  id: string;
  name: string;
  level?: string;
  organization_level?: string;
};

type AccountGrant = {
  account_id: string;
  account_name: string;
  can_maintain_expression_profile: boolean;
};

type Operator = {
  id: string;
  display_name: string;
  username: string;
  organization_id: string;
  organization: string;
  entry_type: EntryType;
  enabled: boolean;
  capabilities:
    | Array<"content" | "display">
    | { content: boolean; display: boolean };
  manages_tenant: boolean;
  account_grants: AccountGrant[];
};

type ProfileSegments = {
  identity_position: string;
  authority_boundary: string;
  audience_relationship: string;
  content_territories: string;
  default_production_conditions: string;
};
type SpeakerKind = "institutional_account" | "personal_ip_account" | "unknown";

type PublishingAccount = {
  id: string;
  name: string;
  control_organization: {
    id: string;
    name: string;
    source: string;
  } | null;
  content_role: {
    name: string;
    authority_boundary: string;
    speaker_kind: SpeakerKind;
  };
  profile: {
    id: string;
    version: number;
    segments: ProfileSegments;
  } | null;
  operators: Array<{ id: string; display_name: string }>;
  platform_targets: Array<{
    account_id: string;
    target: Target;
    platform: string;
    media: string;
  }>;
  carrier_count: number;
};

type ManagementProfile = {
  can_maintain: boolean;
  can_declare: boolean;
  control_organization?: string | null;
  control_organization_source?: string | null;
  current: (ProfileSegments & { version: number }) | null;
  draft?: ProfileSegments | null;
};

type Usage = {
  window_days: 7 | 30;
  members: {
    registered: number;
    activated: number;
    enabled: number;
    disabled: number;
    active: number;
    items: Array<{
      id: string;
      display_name: string;
      entry_type: EntryType;
      enabled: boolean;
      last_used_at: string | null;
      content_attempts: number;
      display_attempts: number;
    }>;
  };
  activity: {
    content_attempts: number;
    content_successes: number;
    content_failures: number;
    revisions: number;
    series_continuations: number;
    display_attempts: number;
    display_successes: number;
    display_failures: number;
    rate_limited: number;
  };
  provider_usage: {
    label: string;
    total_tokens: number;
    is_complete_billing_total: false;
  };
  distribution: {
    publishing_identities: Array<{ id: string; name: string; attempts: number }>;
    platforms: Array<{ target: Target | "other"; attempts: number }>;
  };
};

type ReadinessItem = {
  id: string;
  title: string;
  status: "available" | "conditional" | "unavailable";
  evidence: string[];
  gaps: string[];
  impact: string;
  action: { label: string; section: Section };
  source: string;
  version: string;
  evaluated_at: string;
};

type LibraryScope = "brand_all" | "headquarters" | "organizations";
type LibraryEntry = {
  id: string;
  category: string;
  title: string;
  source_note: string;
  content: string;
  version: string;
  status: "candidate" | "active" | "retired";
  visibility_scope: LibraryScope;
  visibility_label: string;
  scope_organizations: Organization[];
  updated_by: string | null;
  updated_at: string;
  impact: string;
};

type ProductFact = {
  sku: string;
  display_name: string;
  facts?: {
    category?: string;
    colors?: string[];
    material_or_structure?: string;
    silhouette?: string;
    observable_features?: string;
  };
  category?: string;
  colors?: string[];
  material_or_structure?: string;
  silhouette?: string;
  observable_features?: string;
  source_note: string;
  applicability: string;
  fact_version?: number;
  visibility_scope?: LibraryScope;
  scope_organizations?: Organization[];
  updated_at?: string;
};

type ProductDraft = {
  sku: string;
  display_name: string;
  category: string;
  colors: string;
  material_or_structure: string;
  silhouette: string;
  observable_features: string;
  source_note: string;
  applicability: string;
};

type OrganizationMaterial = {
  id: string;
  title: string;
  original_filename: string;
  organization: string;
  reference_note: string;
  reference_version?: number;
  visibility_scope?: LibraryScope;
  scope_organizations?: Organization[];
  created_at?: string;
};

const sections: Array<{ id: Section; label: string }> = [
  { id: "overview", label: "概览与当前待办" },
  { id: "usage", label: "团队使用" },
  { id: "members", label: "成员与入口资格" },
  { id: "accounts", label: "发布账号与账号画像" },
  { id: "library", label: "品牌资料库" },
  { id: "readiness", label: "当前可用与待补" }
];

const scopeLabels: Record<LibraryScope, string> = {
  brand_all: "品牌全员",
  headquarters: "总部专用",
  organizations: "指定区域"
};

const targetLabels: Record<Target | "other", string> = {
  douyin_video: "抖音视频",
  xiaohongshu_graphic: "小红书图文",
  xiaohongshu_video: "小红书视频",
  wechat_channels_video: "微信视频号",
  other: "其他"
};

function hasCapability(
  operator: Operator,
  capability: "content" | "display"
): boolean {
  return Array.isArray(operator.capabilities)
    ? operator.capabilities.includes(capability)
    : operator.capabilities[capability];
}

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
  useEffect(() => {
    void refresh();
    // The requested tenant scope is resolved by the server session, never by a client id.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, enabled]);
  return { data, error, refresh, loading };
}

function PageNotice({
  notice,
  onDismiss
}: {
  notice: Notice;
  onDismiss: () => void;
}): JSX.Element | null {
  if (!notice) return null;
  return (
    <div className={`tenant-notice ${notice.tone}`} role="status">
      <span>{notice.message}</span>
      <button type="button" onClick={onDismiss}>
        知道了
      </button>
    </div>
  );
}

function RequestFailure({
  message,
  onRetry
}: {
  message: string;
  onRetry: () => Promise<void>;
}): JSX.Element {
  return (
    <div className="tenant-request-failure" role="alert">
      <p>{message}</p>
      <button type="button" className="text-action" onClick={() => void onRetry()}>
        重新读取
      </button>
    </div>
  );
}

function Drawer({
  title,
  children,
  onClose
}: {
  title: string;
  children: JSX.Element | JSX.Element[];
  onClose: () => void;
}): JSX.Element {
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
  return (
    <div className="tenant-drawer-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        ref={panel}
        className="tenant-drawer"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onMouseDown={event => event.stopPropagation()}
        onKeyDown={handleKeyDown}
      >
        <header>
          <h2>{title}</h2>
          <button ref={close} type="button" className="quiet" onClick={onClose}>
            关闭
          </button>
        </header>
        {children}
      </section>
    </div>
  );
}

function AccountSecurity({
  onClose,
  onPasswordUpdated
}: {
  onClose: () => void;
  onPasswordUpdated?: (path: string) => void;
}): JSX.Element {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const submit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault();
    setError("");
    if (newPassword.length < 12) {
      setError("新密码至少需要 12 个字符。");
      return;
    }
    if (newPassword !== confirmation) {
      setError("两次输入的新密码不一致，请重新确认。");
      return;
    }
    setSaving(true);
    try {
      await api<{ changed: boolean }>("/api/v1/auth/password", {
        method: "POST",
        body: JSON.stringify({
          current_password: currentPassword,
          password: newPassword
        })
      });
      setCurrentPassword("");
      setNewPassword("");
      setConfirmation("");
      const loginPath = "/tenant-admin/login?password_updated=1";
      if (onPasswordUpdated) {
        onPasswordUpdated(loginPath);
      } else {
        window.location.assign(loginPath);
      }
    } catch (caught) {
      setError(
        caught instanceof ApiError && caught.status === 401
          ? "当前密码不正确，请重新输入。"
          : "密码暂时没有更新，请稍后再试。"
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <Drawer title="账户安全" onClose={onClose}>
      <form className="tenant-form" onSubmit={event => void submit(event)}>
        <p className="tenant-security-note">修改后，所有已登录设备都需要重新登录。</p>
        <label>
          当前密码
          <input
            type="password"
            autoComplete="current-password"
            value={currentPassword}
            onChange={event => setCurrentPassword(event.target.value)}
            required
          />
        </label>
        <label>
          新密码
          <input
            type="password"
            autoComplete="new-password"
            minLength={12}
            value={newPassword}
            onChange={event => setNewPassword(event.target.value)}
            required
          />
        </label>
        <label>
          再次输入新密码
          <input
            type="password"
            autoComplete="new-password"
            minLength={12}
            value={confirmation}
            onChange={event => setConfirmation(event.target.value)}
            required
          />
        </label>
        {error && (
          <p className="tenant-form-error" role="alert">
            {error}
          </p>
        )}
        <button className="primary" type="submit" disabled={saving}>
          修改密码
        </button>
      </form>
    </Drawer>
  );
}

function humanDate(value: string | null): string {
  if (!value) return "尚无使用记录";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "尚无使用记录"
    : new Intl.DateTimeFormat("zh-CN", {
        month: "numeric",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit"
      }).format(date);
}

function readableScope(
  scope: LibraryScope | undefined,
  organizations: Organization[] | undefined
): string {
  const resolved = scope ?? "brand_all";
  const names = (organizations ?? []).map(item => item.name).filter(Boolean);
  if (resolved === "brand_all") return scopeLabels.brand_all;
  if (resolved === "headquarters") {
    return names.length
      ? `${scopeLabels.headquarters} · ${names.join("、")}`
      : scopeLabels.headquarters;
  }
  return names.length ? `${names.join("、")}可用` : scopeLabels.organizations;
}

async function filePayload(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("无法读取这份素材。"));
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1] ?? "");
    reader.readAsDataURL(file);
  });
}

function splitCsvLine(line: string): string[] {
  const values: string[] = [];
  let value = "";
  let quoted = false;
  for (let index = 0; index < line.length; index += 1) {
    const character = line[index];
    if (character === '"') {
      if (quoted && line[index + 1] === '"') {
        value += '"';
        index += 1;
      } else {
        quoted = !quoted;
      }
    } else if (character === "," && !quoted) {
      values.push(value.trim());
      value = "";
    } else {
      value += character;
    }
  }
  values.push(value.trim());
  return values;
}

function parseProductCsv(text: string): ProductDraft[] {
  const lines = text.split(/\r?\n/).filter(line => line.trim());
  if (lines.length < 2) return [];
  const headers = splitCsvLine(lines[0]).map(value => value.toLowerCase());
  const aliases: Record<keyof ProductDraft, string[]> = {
    sku: ["sku", "商品编号"],
    display_name: ["display_name", "商品名称"],
    category: ["category", "品类"],
    colors: ["colors", "颜色"],
    material_or_structure: ["material_or_structure", "材质或结构"],
    silhouette: ["silhouette", "轮廓"],
    observable_features: ["observable_features", "肉眼可见特征"],
    source_note: ["source_note", "资料来源说明"],
    applicability: ["applicability", "适用范围"]
  };
  const column = (key: keyof ProductDraft): number =>
    headers.findIndex(header => aliases[key].includes(header));
  return lines.slice(1).map(line => {
    const values = splitCsvLine(line);
    const read = (key: keyof ProductDraft): string => {
      const index = column(key);
      return index >= 0 ? values[index] ?? "" : "";
    };
    return {
      sku: read("sku"),
      display_name: read("display_name"),
      category: read("category"),
      colors: read("colors"),
      material_or_structure: read("material_or_structure"),
      silhouette: read("silhouette"),
      observable_features: read("observable_features"),
      source_note: read("source_note"),
      applicability: read("applicability")
    };
  });
}

const emptyProduct = (): ProductDraft => ({
  sku: "",
  display_name: "",
  category: "",
  colors: "",
  material_or_structure: "",
  silhouette: "",
  observable_features: "",
  source_note: "",
  applicability: ""
});

function StatusPill({ status }: { status: ReadinessItem["status"] }): JSX.Element {
  const label =
    status === "available"
      ? "可用"
      : status === "conditional"
        ? "有条件可用"
        : "暂不可用";
  return <span className={`readiness-status ${status}`}>{label}</span>;
}

function Overview({ onSection }: { onSection: (section: Section) => void }): JSX.Element {
  const usage = useRequest<Usage>("/api/v1/tenant-management/team-usage?window_days=7");
  const readiness = useRequest<{ items: ReadinessItem[] }>("/api/v1/admin/readiness");
  const actions = (readiness.data?.items ?? [])
    .filter(item => item.status !== "available")
    .slice(0, 3);
  const error = usage.error ?? readiness.error;
  if (error) {
    return (
      <section className="tenant-page">
        <RequestFailure
          message={error}
          onRetry={async () => {
            await Promise.all([usage.refresh(), readiness.refresh()]);
          }}
        />
      </section>
    );
  }
  return (
    <section className="tenant-page">
      <header className="tenant-heading">
        <p className="eyebrow">品牌管理</p>
        <h1>今天需要处理什么</h1>
      </header>
      <dl className="management-summary" aria-label="当前管理概览">
        <div>
          <dt>已启用成员</dt>
          <dd>{usage.data?.members.enabled ?? "—"}</dd>
        </div>
        <div>
          <dt>近 7 日活跃</dt>
          <dd>{usage.data?.members.active ?? "—"}</dd>
        </div>
        <div>
          <dt>内容尝试</dt>
          <dd>{usage.data?.activity.content_attempts ?? "—"}</dd>
        </div>
        <div>
          <dt>陈列尝试</dt>
          <dd>{usage.data?.activity.display_attempts ?? "—"}</dd>
        </div>
      </dl>
      <section className="tenant-worklist">
        <header>
          <h2>当前待办</h2>
          <button type="button" className="text-action" onClick={() => onSection("readiness")}>
            查看全部
          </button>
        </header>
        {usage.loading || readiness.loading ? (
          <p className="tenant-loading">正在读取当前情况……</p>
        ) : actions.length ? (
          actions.map(item => (
            <article key={item.id}>
              <div>
                <StatusPill status={item.status} />
                <h3>{item.title}</h3>
                <p>{item.gaps[0] ?? item.impact}</p>
              </div>
              <button
                type="button"
                className="text-action"
                onClick={() => onSection(item.action.section)}
              >
                {item.action.label}
              </button>
            </article>
          ))
        ) : (
          <p className="tenant-empty">当前没有需要立即处理的资料。</p>
        )}
      </section>
    </section>
  );
}

function TeamUsage(): JSX.Element {
  const [windowDays, setWindowDays] = useState<7 | 30>(7);
  const usage = useRequest<Usage>(
    `/api/v1/tenant-management/team-usage?window_days=${windowDays}`
  );
  if (usage.error) {
    return (
      <section className="tenant-page">
        <RequestFailure message={usage.error} onRetry={usage.refresh} />
      </section>
    );
  }
  const data = usage.data;
  return (
    <section className="tenant-page">
      <header className="tenant-heading split">
        <div>
          <p className="eyebrow">团队使用</p>
          <h1>谁在使用，使用到哪里</h1>
        </div>
        <div className="period-switch" role="group" aria-label="统计时间">
          {[7, 30].map(value => (
            <button
              key={value}
              type="button"
              className={windowDays === value ? "active" : ""}
              aria-pressed={windowDays === value}
              onClick={() => setWindowDays(value as 7 | 30)}
            >
              近 {value} 日
            </button>
          ))}
        </div>
      </header>
      {usage.loading ? (
        <p className="tenant-loading">正在读取使用情况……</p>
      ) : (
        <>
          <dl className="management-summary usage-summary">
            <div>
              <dt>活跃成员</dt>
              <dd>{data?.members.active ?? 0}</dd>
            </div>
            <div>
              <dt>内容成功 / 失败</dt>
              <dd>
                {data?.activity.content_successes ?? 0} /{" "}
                {data?.activity.content_failures ?? 0}
              </dd>
            </div>
            <div>
              <dt>陈列成功 / 失败</dt>
              <dd>
                {data?.activity.display_successes ?? 0} /{" "}
                {data?.activity.display_failures ?? 0}
              </dd>
            </div>
            <div>
              <dt>限流</dt>
              <dd>{data?.activity.rate_limited ?? 0}</dd>
            </div>
            <div>
              <dt>{data?.provider_usage.label ?? "已记录模型用量"}</dt>
              <dd>{data?.provider_usage.total_tokens ?? 0}</dd>
              <small>仅为已有运行记录，不等同于账单。</small>
            </div>
          </dl>
          <div className="usage-grid">
            <section>
              <h2>成员最近使用</h2>
              <div className="tenant-table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>成员</th>
                      <th>入口</th>
                      <th>最近使用</th>
                      <th>内容 / 陈列</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data?.members.items.map(member => (
                      <tr key={member.id}>
                        <td>{member.display_name}</td>
                        <td>
                          {member.entry_type === "tenant_admin" ? "租户管理员" : "租户用户"}
                        </td>
                        <td>{humanDate(member.last_used_at)}</td>
                        <td>
                          {member.content_attempts} / {member.display_attempts}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
            <section>
              <h2>发布账号与平台</h2>
              <ul className="usage-distribution">
                {data?.distribution.publishing_identities.map(item => (
                  <li key={item.id}>
                    <span>{item.name}</span>
                    <strong>{item.attempts}</strong>
                  </li>
                ))}
                {data?.distribution.platforms.map(item => (
                  <li key={item.target}>
                    <span>{targetLabels[item.target]}</span>
                    <strong>{item.attempts}</strong>
                  </li>
                ))}
              </ul>
            </section>
          </div>
        </>
      )}
    </section>
  );
}

function Members({
  setNotice,
  currentUserId
}: {
  setNotice: (notice: Notice) => void;
  currentUserId: string;
}): JSX.Element {
  const operators = useRequest<Operator[]>("/api/v1/tenant-management/operators");
  const organizations = useRequest<Organization[]>("/api/v1/tenant-management/organizations");
  const accounts = useRequest<PublishingAccount[]>(
    "/api/v1/tenant-management/publishing-accounts"
  );
  const [drawer, setDrawer] = useState<"create" | Operator | null>(null);
  const [saving, setSaving] = useState(false);
  const [activationLink, setActivationLink] = useState("");
  const [form, setForm] = useState({
    displayName: "",
    username: "",
    organizationId: "",
    entryType: "tenant_user" as EntryType,
    content: true,
    display: false,
    accountIds: [] as string[]
  });
  const [edit, setEdit] = useState({
    entryType: "tenant_user" as EntryType,
    content: false,
    display: false,
    accountIds: [] as string[]
  });

  const refresh = async (): Promise<void> => {
    await Promise.all([operators.refresh(), accounts.refresh()]);
  };
  const run = async (action: () => Promise<void>, message: string): Promise<void> => {
    setSaving(true);
    try {
      await action();
      await refresh();
      setNotice({ tone: "success", message });
    } catch (error) {
      setNotice({ tone: "error", message: readableRequestError(error) });
    } finally {
      setSaving(false);
    }
  };
  const openCreate = (): void => {
    setActivationLink("");
    setForm({
      displayName: "",
      username: "",
      organizationId: "",
      entryType: "tenant_user",
      content: true,
      display: false,
      accountIds: []
    });
    setDrawer("create");
  };
  const create = (event: FormEvent): void => {
    event.preventDefault();
    void run(async () => {
      const created = await api<{
        activation_link: string;
        activation_url: string;
      }>(
        "/api/v1/tenant-management/users",
        {
          method: "POST",
          body: JSON.stringify({
            display_name: form.displayName,
            username: form.username,
            organization_id: form.organizationId || null,
            entry_type: form.entryType,
            capabilities:
              form.entryType === "tenant_user"
                ? [
                    ...(form.content ? (["content"] as const) : []),
                    ...(form.display ? (["display"] as const) : [])
                  ]
                : [],
            publishing_identity_ids:
              form.entryType === "tenant_user" ? form.accountIds : [],
            grants_tenant_management: form.entryType === "tenant_admin",
            grants_material_maintenance: false,
            grants_expression_profile_maintenance: false
          })
        }
      );
      setActivationLink(created.activation_url);
    }, "成员已建立。请把本次一次性激活链接安全交给本人。");
  };
  const toggleAccount = (accountId: string): void => {
    setForm(value => ({
      ...value,
      accountIds: value.accountIds.includes(accountId)
        ? value.accountIds.filter(item => item !== accountId)
        : [...value.accountIds, accountId]
    }));
  };
  const openMember = (member: Operator): void => {
    setActivationLink("");
    setEdit({
      entryType: member.entry_type,
      content: hasCapability(member, "content"),
      display: hasCapability(member, "display"),
      accountIds: member.account_grants.map(item => item.account_id)
    });
    setDrawer(member);
  };
  const toggleEditAccount = (accountId: string): void => {
    setEdit(value => ({
      ...value,
      accountIds: value.accountIds.includes(accountId)
        ? value.accountIds.filter(item => item !== accountId)
        : [...value.accountIds, accountId]
    }));
  };
  const requestError = operators.error ?? organizations.error ?? accounts.error;
  return (
    <section className="tenant-page">
      <header className="tenant-heading split">
        <div>
          <p className="eyebrow">成员与入口资格</p>
          <h1>一个账号，只承担一种入口职责</h1>
        </div>
        <button className="primary" type="button" onClick={openCreate}>
          添加成员
        </button>
      </header>
      {requestError ? (
        <RequestFailure
          message={requestError}
          onRetry={async () => {
            await Promise.all([
              operators.refresh(),
              organizations.refresh(),
              accounts.refresh()
            ]);
          }}
        />
      ) : (
        <div className="tenant-list">
          {operators.data?.map(member => (
            <article key={member.id}>
              <div>
                <h2>{member.display_name}</h2>
                <p>
                  {member.organization} ·{" "}
                  {member.entry_type === "tenant_admin" ? "租户管理员" : "租户用户"}
                </p>
                <small>
                  {member.enabled ? "已启用" : "已停用"}
                  {member.entry_type === "tenant_user" &&
                    ` · ${member.account_grants.length} 个发布账号`}
                </small>
              </div>
              <button type="button" className="text-action" onClick={() => openMember(member)}>
                查看与处理
              </button>
            </article>
          ))}
        </div>
      )}
      {drawer === "create" && (
        <Drawer title="添加成员" onClose={() => setDrawer(null)}>
          <form className="tenant-form" onSubmit={create}>
            <label>
              姓名或工作名
              <input
                required
                value={form.displayName}
                onChange={event => setForm({ ...form, displayName: event.target.value })}
              />
            </label>
            <label>
              登录用户名
              <input
                required
                minLength={3}
                value={form.username}
                onChange={event => setForm({ ...form, username: event.target.value })}
              />
            </label>
            <label>
              所属组织
              <select
                required
                value={form.organizationId}
                onChange={event => setForm({ ...form, organizationId: event.target.value })}
              >
                <option value="">请选择</option>
                {organizations.data?.map(item => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </label>
            <fieldset className="entry-type-choice">
              <legend>入口类型</legend>
              <label>
                <input
                  type="radio"
                  name="entry-type"
                  checked={form.entryType === "tenant_admin"}
                  onChange={() =>
                    setForm({
                      ...form,
                      entryType: "tenant_admin",
                      content: false,
                      display: false,
                      accountIds: []
                    })
                  }
                />
                <span>
                  租户管理员
                  <small>只进入品牌管理</small>
                </span>
              </label>
              <label>
                <input
                  type="radio"
                  name="entry-type"
                  checked={form.entryType === "tenant_user"}
                  onChange={() =>
                    setForm({ ...form, entryType: "tenant_user", content: true })
                  }
                />
                <span>
                  租户用户
                  <small>按资格进入内容创作和陈列搭配</small>
                </span>
              </label>
            </fieldset>
            {form.entryType === "tenant_user" && (
              <>
                <fieldset>
                  <legend>业务资格</legend>
                  <label>
                    <input
                      type="checkbox"
                      checked={form.content}
                      onChange={event =>
                        setForm({
                          ...form,
                          content: event.target.checked,
                          accountIds: event.target.checked ? form.accountIds : []
                        })
                      }
                    />
                    内容创作
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      checked={form.display}
                      onChange={event =>
                        setForm({ ...form, display: event.target.checked })
                      }
                    />
                    陈列搭配
                  </label>
                </fieldset>
                <fieldset>
                  <legend>获准操作的发布账号</legend>
                  {accounts.data?.map(account => (
                    <label key={account.id}>
                      <input
                        type="checkbox"
                        disabled={!form.content}
                        checked={form.accountIds.includes(account.id)}
                        onChange={() => toggleAccount(account.id)}
                      />
                      {account.name}
                    </label>
                  ))}
                </fieldset>
              </>
            )}
            {form.entryType === "tenant_user" &&
              form.content &&
              form.accountIds.length === 0 && (
                <p className="tenant-security-note">
                  选择内容创作时，请至少分配一个发布账号。
                </p>
              )}
            <button
              className="primary"
              type="submit"
              disabled={
                saving ||
                (form.entryType === "tenant_user" &&
                  form.content &&
                  form.accountIds.length === 0)
              }
            >
              创建并生成一次性激活链接
            </button>
            {activationLink && (
              <div className="one-time-link">
                <p>一次性激活链接只显示这一次，请安全交给本人。</p>
                <code>{activationLink}</code>
                <a
                  className="text-action"
                  href={activationLink}
                  target="_blank"
                  rel="noreferrer"
                >
                  打开激活页
                </a>
                <button
                  type="button"
                  className="text-action"
                  onClick={() => void navigator.clipboard.writeText(activationLink)}
                >
                  复制链接
                </button>
              </div>
            )}
          </form>
        </Drawer>
      )}
      {drawer && drawer !== "create" && (
        <Drawer title={drawer.display_name} onClose={() => setDrawer(null)}>
          <div className="tenant-detail">
            <p>
              {drawer.organization} ·{" "}
              {drawer.entry_type === "tenant_admin" ? "租户管理员" : "租户用户"}
            </p>
            <fieldset className="member-grants">
              <legend>入口与工作资格</legend>
              <label>
                <input
                  type="radio"
                  name="edit-entry-type"
                  checked={edit.entryType === "tenant_admin"}
                  onChange={() =>
                    setEdit({
                      entryType: "tenant_admin",
                      content: false,
                      display: false,
                      accountIds: []
                    })
                  }
                />
                租户管理员
              </label>
              <label>
                <input
                  type="radio"
                  name="edit-entry-type"
                  checked={edit.entryType === "tenant_user"}
                  onChange={() =>
                    setEdit(value => ({
                      ...value,
                      entryType: "tenant_user",
                      content: true
                    }))
                  }
                />
                租户用户
              </label>
              {edit.entryType === "tenant_user" && (
                <>
                  <label>
                    <input
                      type="checkbox"
                      checked={edit.content}
                      onChange={event =>
                        setEdit({
                          ...edit,
                          content: event.target.checked,
                          accountIds: event.target.checked ? edit.accountIds : []
                        })
                      }
                    />
                    内容创作
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      checked={edit.display}
                      onChange={event =>
                        setEdit({ ...edit, display: event.target.checked })
                      }
                    />
                    陈列搭配
                  </label>
                  {accounts.data?.map(account => (
                    <label key={account.id}>
                      <input
                        type="checkbox"
                        disabled={!edit.content}
                        checked={edit.accountIds.includes(account.id)}
                        onChange={() => toggleEditAccount(account.id)}
                      />
                      {account.name}
                    </label>
                  ))}
                </>
              )}
              {edit.entryType === "tenant_user" &&
                edit.content &&
                edit.accountIds.length === 0 && (
                  <p className="tenant-security-note">
                    内容创作资格必须保留至少一个发布账号。
                  </p>
                )}
              <button
                type="button"
                className="primary"
                disabled={
                  saving ||
                  (edit.entryType === "tenant_user" &&
                    edit.content &&
                    edit.accountIds.length === 0)
                }
                onClick={() =>
                  void run(
                    () =>
                      api(`/api/v1/tenant-management/users/${drawer.id}/grants`, {
                        method: "PATCH",
                        body: JSON.stringify({
                          entry_type: edit.entryType,
                          capabilities:
                            edit.entryType === "tenant_user"
                              ? [
                                  ...(edit.content ? (["content"] as const) : []),
                                  ...(edit.display ? (["display"] as const) : [])
                                ]
                              : [],
                          publishing_identity_ids:
                            edit.entryType === "tenant_user" ? edit.accountIds : [],
                          grants_tenant_management: edit.entryType === "tenant_admin",
                          grants_material_maintenance: false,
                          grants_expression_profile_maintenance: false
                        })
                      }),
                    "成员资格已更新；该成员需要重新登录。"
                  )
                }
              >
                保存入口资格
              </button>
            </fieldset>
            <button
              className="text-action"
              type="button"
              disabled={saving}
              onClick={() =>
                void run(async () => {
                  const value = await api<{
                    reset_link: string;
                    reset_url: string;
                  }>(
                    `/api/v1/tenant-management/users/${drawer.id}/reset`,
                    { method: "POST" }
                  );
                  setActivationLink(value.reset_url);
                }, "新的一次性重设密码链接已生成，此前未使用的重设链接已失效。")
              }
            >
              生成一次性重设密码链接
            </button>
            {activationLink && (
              <div className="one-time-link">
                <code className="reset-link">{activationLink}</code>
                <a
                  className="text-action"
                  href={activationLink}
                  target="_blank"
                  rel="noreferrer"
                >
                  打开重设页
                </a>
                <button
                  type="button"
                  className="text-action"
                  onClick={() => void navigator.clipboard.writeText(activationLink)}
                >
                  复制重设链接
                </button>
              </div>
            )}
            {drawer.id !== currentUserId && drawer.enabled && (
              <button
                className="text-action danger"
                type="button"
                disabled={saving}
                onClick={() =>
                  void run(
                    () =>
                      api(`/api/v1/tenant-management/users/${drawer.id}/disable`, {
                        method: "POST"
                      }),
                    "成员已停用，现有会话与工作资格已撤销。"
                  )
                }
              >
                停用成员
              </button>
            )}
          </div>
        </Drawer>
      )}
    </section>
  );
}

const emptyProfile = (): ProfileSegments => ({
  identity_position: "",
  authority_boundary: "",
  audience_relationship: "",
  content_territories: "",
  default_production_conditions: ""
});

function ProfileFields({
  values,
  onChange,
  readOnly = false
}: {
  values: ProfileSegments;
  onChange: (key: keyof ProfileSegments, value: string) => void;
  readOnly?: boolean;
}): JSX.Element {
  const labels: Array<[keyof ProfileSegments, string]> = [
    ["identity_position", "表达身份"],
    ["authority_boundary", "权威边界"],
    ["audience_relationship", "受众关系"],
    ["content_territories", "内容领地"],
    ["default_production_conditions", "长期制作条件"]
  ];
  return (
    <>
      {labels.map(([key, label]) => (
        <label key={key}>
          {label}
          {readOnly ? (
            <p className="profile-read">{values[key]}</p>
          ) : (
            <textarea
              required
              value={values[key]}
              onChange={event => onChange(key, event.target.value)}
            />
          )}
        </label>
      ))}
    </>
  );
}

function Accounts({ setNotice }: { setNotice: (notice: Notice) => void }): JSX.Element {
  const accounts = useRequest<PublishingAccount[]>(
    "/api/v1/tenant-management/publishing-accounts"
  );
  const operators = useRequest<Operator[]>("/api/v1/tenant-management/operators");
  const organizations = useRequest<Organization[]>(
    "/api/v1/tenant-management/control-organizations"
  );
  const [selected, setSelected] = useState<PublishingAccount | null>(null);
  const [drawer, setDrawer] = useState<"create" | "target" | "profile" | null>(null);
  const [saving, setSaving] = useState(false);
  const [profile, setProfile] = useState<ProfileSegments>(emptyProfile);
  const [profileAccess, setProfileAccess] = useState<ManagementProfile | null>(null);
  const [profileOrganizationId, setProfileOrganizationId] = useState("");
  const [createForm, setCreateForm] = useState({
    name: "",
    role: "",
    speakerKind: "institutional_account" as SpeakerKind,
    organizationId: "",
    operatorId: "",
    target: "douyin_video" as Target,
    profile: emptyProfile()
  });
  const [targetForm, setTargetForm] = useState({
    target: "xiaohongshu_graphic" as Target,
    operatorId: ""
  });
  const run = async (action: () => Promise<void>, message: string): Promise<void> => {
    setSaving(true);
    try {
      await action();
      await accounts.refresh();
      setNotice({ tone: "success", message });
    } catch (error) {
      setNotice({ tone: "error", message: readableRequestError(error) });
    } finally {
      setSaving(false);
    }
  };
  const profileFor = async (account: PublishingAccount): Promise<void> => {
    try {
      const access = await api<ManagementProfile>(
        `/api/v1/tenant-management/publishing-accounts/${account.id}/expression-profile`
      );
      setSelected(account);
      setProfileAccess(access);
      setProfile(
        access.current
          ? {
              identity_position: access.current.identity_position,
              authority_boundary: access.current.authority_boundary,
              audience_relationship: access.current.audience_relationship,
              content_territories: access.current.content_territories,
              default_production_conditions:
                access.current.default_production_conditions
            }
          : access.draft ?? emptyProfile()
      );
      setProfileOrganizationId("");
      setDrawer("profile");
    } catch (error) {
      setNotice({ tone: "error", message: readableRequestError(error) });
    }
  };
  const createAccount = (event: FormEvent): void => {
    event.preventDefault();
    void run(async () => {
      await api("/api/v1/tenant-management/publishing-accounts", {
        method: "POST",
        body: JSON.stringify({
          name: createForm.name,
          target: createForm.target,
          channel: targetLabels[createForm.target].replace(/图文|视频/g, ""),
          content_role_name: createForm.role,
          speaker_kind: createForm.speakerKind,
          initial_profile: createForm.profile,
          operator_id: createForm.operatorId,
          control_organization_id: createForm.organizationId,
          operator_can_maintain_expression_profile: true,
          as_synthetic_business_fixture: false
        })
      });
      setDrawer(null);
    }, "发布账号已建立。平台载体和账号画像会继续归到同一个发布身份。");
  };
  const platformCount = (accounts.data ?? []).reduce(
    (total, account) => total + account.platform_targets.length,
    0
  );
  return (
    <section className="tenant-page">
      <header className="tenant-heading split">
        <div>
          <p className="eyebrow">发布账号与账号画像</p>
          <h1>
            {accounts.data?.length ?? 0} 个发布账号，{platformCount} 个平台载体
          </h1>
        </div>
        <button
          className="primary"
          type="button"
          onClick={() => {
            setCreateForm({
              name: "",
              role: "",
              speakerKind: "institutional_account",
              organizationId: "",
              operatorId: "",
              target: "douyin_video",
              profile: emptyProfile()
            });
            setDrawer("create");
          }}
        >
          创建发布账号
        </button>
      </header>
      {accounts.error ? (
        <RequestFailure message={accounts.error} onRetry={accounts.refresh} />
      ) : (
        <div className="publishing-account-list">
          {accounts.data?.map(account => (
            <article key={account.id}>
              <header>
                <div>
                  <h2>{account.name}</h2>
                  <p>
                    {account.content_role.name} ·{" "}
                    {account.content_role.speaker_kind === "personal_ip_account"
                      ? "个人 IP"
                      : account.content_role.speaker_kind === "institutional_account"
                        ? "机构账号"
                        : "说话者类型待声明"}{" "}
                    ·{" "}
                    {account.control_organization?.name ?? "尚未声明负责团队"}
                  </p>
                </div>
                <div className="account-actions">
                  <label>
                    表达主体
                    <select
                      aria-label={`${account.name}表达主体`}
                      disabled={saving}
                      value={account.content_role.speaker_kind}
                      onChange={event => {
                        const speakerKind = event.target.value as SpeakerKind;
                        void run(async () => {
                          await api(
                            `/api/v1/tenant-management/publishing-accounts/${account.id}/speaker-kind`,
                            {
                              method: "PATCH",
                              body: JSON.stringify({ speaker_kind: speakerKind })
                            }
                          );
                        }, "账号表达主体已更新；新任务会冻结这项结构化边界。");
                      }}
                    >
                      <option value="unknown">待声明</option>
                      <option value="institutional_account">机构账号</option>
                      <option value="personal_ip_account">个人 IP</option>
                    </select>
                  </label>
                  <button
                    type="button"
                    className="text-action"
                    onClick={() => void profileFor(account)}
                  >
                    账号画像
                  </button>
                  <button
                    type="button"
                    className="text-action"
                    onClick={() => {
                      setSelected(account);
                      setTargetForm({
                        target: "xiaohongshu_graphic",
                        operatorId: account.operators[0]?.id ?? ""
                      });
                      setDrawer("target");
                    }}
                  >
                    添加平台
                  </button>
                </div>
              </header>
              <div className="platform-targets">
                {account.platform_targets.map(target => (
                  <span key={target.account_id}>{targetLabels[target.target]}</span>
                ))}
              </div>
              <p className="account-profile-line">
                {account.profile
                  ? `账号画像 V${account.profile.version} · ${account.profile.segments.identity_position}`
                  : "还没有账号画像"}
              </p>
            </article>
          ))}
        </div>
      )}
      {drawer === "create" && (
        <Drawer title="创建发布账号" onClose={() => setDrawer(null)}>
          <form className="tenant-form" onSubmit={createAccount}>
            <label>
              发布账号名称
              <input
                required
                value={createForm.name}
                onChange={event => setCreateForm({ ...createForm, name: event.target.value })}
              />
            </label>
            <label>
              账号类型短标签
              <input
                required
                value={createForm.role}
                onChange={event => setCreateForm({ ...createForm, role: event.target.value })}
              />
            </label>
            <label>
              当前账号以谁的身份表达
              <select
                value={createForm.speakerKind}
                onChange={event =>
                  setCreateForm({
                    ...createForm,
                    speakerKind: event.target.value as SpeakerKind
                  })
                }
              >
                <option value="institutional_account">品牌、公司或门店等机构</option>
                <option value="personal_ip_account">明确的个人 IP</option>
              </select>
            </label>
            <label>
              负责团队
              <select
                required
                value={createForm.organizationId}
                onChange={event =>
                  setCreateForm({ ...createForm, organizationId: event.target.value })
                }
              >
                <option value="">请选择公司级组织</option>
                {organizations.data
                  ?.filter(
                    item => (item.level ?? item.organization_level) === "company"
                  )
                  .map(item => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              首位使用者
              <select
                required
                value={createForm.operatorId}
                onChange={event =>
                  setCreateForm({ ...createForm, operatorId: event.target.value })
                }
              >
                <option value="">请选择租户用户</option>
                {operators.data
                  ?.filter(item => item.entry_type === "tenant_user")
                  .map(item => (
                    <option key={item.id} value={item.id}>
                      {item.display_name}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              首个平台与形式
              <select
                value={createForm.target}
                onChange={event =>
                  setCreateForm({
                    ...createForm,
                    target: event.target.value as Target
                  })
                }
              >
                {Object.entries(targetLabels)
                  .filter(([key]) => key !== "other")
                  .map(([key, label]) => (
                    <option key={key} value={key}>
                      {label}
                    </option>
                ))}
              </select>
            </label>
            <fieldset>
              <legend>账号画像</legend>
              <ProfileFields
                values={createForm.profile}
                onChange={(key, value) =>
                  setCreateForm({
                    ...createForm,
                    profile: { ...createForm.profile, [key]: value }
                  })
                }
              />
            </fieldset>
            <button className="primary" type="submit" disabled={saving}>
              创建发布账号
            </button>
          </form>
        </Drawer>
      )}
      {drawer === "target" && selected && (
        <Drawer title={`为${selected.name}添加平台`} onClose={() => setDrawer(null)}>
          <form
            className="tenant-form"
            onSubmit={event => {
              event.preventDefault();
              void run(async () => {
                await api("/api/v1/tenant-management/platform-carriers", {
                  method: "POST",
                  body: JSON.stringify({
                    source_account_id: selected.id,
                    name: `${selected.name} · ${targetLabels[targetForm.target]}`,
                    target: targetForm.target,
                    channel: targetLabels[targetForm.target].replace(/图文|视频/g, ""),
                    operator_id: targetForm.operatorId,
                    confirm_internal_carrier: true
                  })
                });
                setDrawer(null);
              }, "平台载体已加入这个发布账号；账号画像没有复制或改变。");
            }}
          >
            <label>
              平台与形式
              <select
                value={targetForm.target}
                onChange={event =>
                  setTargetForm({
                    ...targetForm,
                    target: event.target.value as Target
                  })
                }
              >
                {Object.entries(targetLabels)
                  .filter(
                    ([key]) =>
                      key !== "other" &&
                      !selected.platform_targets.some(target => target.target === key)
                  )
                  .map(([key, label]) => (
                    <option key={key} value={key}>
                      {label}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              使用者
              <select
                required
                value={targetForm.operatorId}
                onChange={event =>
                  setTargetForm({ ...targetForm, operatorId: event.target.value })
                }
              >
                <option value="">请选择</option>
                {operators.data
                  ?.filter(item => item.entry_type === "tenant_user")
                  .map(item => (
                    <option key={item.id} value={item.id}>
                      {item.display_name}
                    </option>
                  ))}
              </select>
            </label>
            <button className="primary" type="submit" disabled={saving}>
              添加平台
            </button>
          </form>
        </Drawer>
      )}
      {drawer === "profile" && selected && (
        <Drawer title={`${selected.name}的账号画像`} onClose={() => setDrawer(null)}>
          {!profileAccess ? (
            <p>正在读取账号画像权限……</p>
          ) : (
            <>
              {profileAccess.can_declare && (
                <form
                  className="tenant-form"
                  onSubmit={event => {
                    event.preventDefault();
                    void run(async () => {
                      await api(
                        `/api/v1/tenant-management/publishing-accounts/${selected.id}/control-organization`,
                        {
                          method: "POST",
                          body: JSON.stringify({ organization_id: profileOrganizationId })
                        }
                      );
                      await profileFor(selected);
                    }, "负责团队已经明确。是否可以维护画像，仍由该团队的实际资格决定。");
                  }}
                >
                  <p>
                    这个账号的负责团队还没有经过明确声明。迁移或推断出的组织不会自动授予画像维护资格。
                  </p>
                  <label>
                    负责团队
                    <select
                      required
                      value={profileOrganizationId}
                      onChange={event => setProfileOrganizationId(event.target.value)}
                    >
                      <option value="">请选择公司级组织</option>
                      {organizations.data
                        ?.filter(
                          organization =>
                            (organization.level ?? organization.organization_level) === "company"
                        )
                        .map(organization => (
                          <option key={organization.id} value={organization.id}>
                            {organization.name}
                          </option>
                        ))}
                    </select>
                  </label>
                  <button className="primary" type="submit" disabled={saving}>
                    明确负责团队
                  </button>
                </form>
              )}
              {!profileAccess.can_declare && profileAccess.can_maintain && (
                <form
                  className="tenant-form"
                  onSubmit={event => {
                    event.preventDefault();
                    void run(async () => {
                      await api(
                        `/api/v1/tenant-management/publishing-accounts/${selected.id}/expression-profile/versions`,
                        { method: "POST", body: JSON.stringify(profile) }
                      );
                      setDrawer(null);
                    }, "账号画像已保存为新版本；旧任务仍保留原来的版本。");
                  }}
                >
                  {profileAccess.current && (
                    <p>当前为 V{profileAccess.current.version}，保存会形成新版本。</p>
                  )}
                  <ProfileFields
                    values={profile}
                    onChange={(key, value) => setProfile({ ...profile, [key]: value })}
                  />
                  <button className="primary" type="submit" disabled={saving}>
                    保存新版本
                  </button>
                </form>
              )}
              {!profileAccess.can_declare && !profileAccess.can_maintain && (
                <div className="tenant-form">
                  <p>
                    账号画像由“{profileAccess.control_organization || "负责团队"}”维护。当前登录账号可以查看，但不能修改。
                  </p>
                  {profileAccess.current ? (
                    <>
                      <p>当前版本 V{profileAccess.current.version}</p>
                      <ProfileFields values={profile} onChange={() => undefined} readOnly />
                    </>
                  ) : (
                    <p>负责团队尚未建立账号画像。</p>
                  )}
                </div>
              )}
            </>
          )}
        </Drawer>
      )}
    </section>
  );
}

function BrandLibrary({ setNotice }: { setNotice: (notice: Notice) => void }): JSX.Element {
  const entries = useRequest<LibraryEntry[]>("/api/v1/tenant-management/brand-library");
  const organizations = useRequest<Organization[]>("/api/v1/tenant-management/organizations");
  const products = useRequest<ProductFact[]>("/api/v1/tenant-management/brand-products");
  const materials = useRequest<OrganizationMaterial[]>(
    "/api/v1/tenant-management/organization-materials"
  );
  const [filter, setFilter] = useState<"all" | LibraryScope>("all");
  const [drawer, setDrawer] = useState<
    "reference" | "product" | "material" | "organization" | null
  >(null);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    category: "brand_expression",
    title: "",
    sourceNote: "",
    content: "",
    version: "V1",
    visibilityScope: "brand_all" as LibraryScope,
    organizationIds: [] as string[]
  });
  const [productRows, setProductRows] = useState<ProductDraft[]>([emptyProduct()]);
  const [confirmProducts, setConfirmProducts] = useState(false);
  const [productScope, setProductScope] = useState<LibraryScope>("brand_all");
  const [productOrganizationIds, setProductOrganizationIds] = useState<string[]>([]);
  const [materialForm, setMaterialForm] = useState({
    organizationId: "",
    title: "",
    note: "",
    file: null as File | null,
    visibilityScope: "brand_all" as LibraryScope,
    scopeOrganizationIds: [] as string[]
  });
  const [organizationForm, setOrganizationForm] = useState({
    name: "",
    level: "unspecified"
  });
  const visible = (entries.data ?? []).filter(
    entry => filter === "all" || entry.visibility_scope === filter
  );
  const visibleProducts = (products.data ?? []).filter(
    item => filter === "all" || (item.visibility_scope ?? "brand_all") === filter
  );
  const visibleMaterials = (materials.data ?? []).filter(
    item => filter === "all" || (item.visibility_scope ?? "brand_all") === filter
  );
  const save = (event: FormEvent): void => {
    event.preventDefault();
    setSaving(true);
    void api("/api/v1/tenant-management/brand-library", {
      method: "POST",
      body: JSON.stringify({
        category: form.category,
        title: form.title,
        source_note: form.sourceNote,
        content: form.content,
        version: form.version,
        status: "candidate",
        visibility_scope: form.visibilityScope,
        organization_ids:
          form.visibilityScope === "brand_all" ? [] : form.organizationIds
      })
    })
      .then(async () => {
        await entries.refresh();
        setDrawer(null);
        setNotice({
          tone: "success",
          message: "资料已保存并保留来源与范围；候选资料不会自动变成全局知识。"
        });
      })
      .catch(error =>
        setNotice({ tone: "error", message: readableRequestError(error) })
      )
      .finally(() => setSaving(false));
  };
  const selectScopeOrganization = (id: string): void => {
    if (form.visibilityScope === "headquarters") {
      setForm({ ...form, organizationIds: [id] });
      return;
    }
    setForm(value => ({
      ...value,
      organizationIds: value.organizationIds.includes(id)
        ? value.organizationIds.filter(item => item !== id)
        : [...value.organizationIds, id]
    }));
  };
  const saveProducts = (event: FormEvent): void => {
    event.preventDefault();
    const validRows = productRows.filter(
      item =>
        item.sku.trim() &&
        item.display_name.trim() &&
        item.source_note.trim() &&
        item.applicability.trim()
    );
    if (!confirmProducts || validRows.length !== productRows.length) return;
    setSaving(true);
    void Promise.all(
      validRows.map(item =>
        api("/api/v1/tenant-management/brand-products", {
          method: "PUT",
          body: JSON.stringify({
            ...item,
            colors: item.colors
              .split(/[，,]/)
              .map(value => value.trim())
              .filter(Boolean),
            confirm_as_current_brand_fact: true,
            as_synthetic_business_fixture: false,
            visibility_scope: productScope,
            organization_ids:
              productScope === "brand_all" ? [] : productOrganizationIds
          })
        })
      )
    )
      .then(async () => {
        await products.refresh();
        setDrawer(null);
        setNotice({
          tone: "success",
          message: `${validRows.length} 条商品事实已保存；来源和适用范围会随当前版本保留。`
        });
      })
      .catch(error =>
        setNotice({ tone: "error", message: readableRequestError(error) })
      )
      .finally(() => setSaving(false));
  };
  const saveMaterial = (event: FormEvent): void => {
    event.preventDefault();
    if (!materialForm.file) return;
    setSaving(true);
    void filePayload(materialForm.file)
      .then(contentBase64 =>
        api("/api/v1/tenant-management/organization-materials", {
          method: "POST",
          body: JSON.stringify({
            organization_id: materialForm.organizationId,
            title: materialForm.title,
            filename: materialForm.file?.name,
            content_type:
              materialForm.file?.type || "application/octet-stream",
            content_base64: contentBase64,
            declares_identifiable_minor: false,
            reference_note: materialForm.note,
            visibility_scope: materialForm.visibilityScope,
            organization_ids:
              materialForm.visibilityScope === "brand_all"
                ? []
                : materialForm.scopeOrganizationIds
          })
        })
      )
      .then(async () => {
        await materials.refresh();
        setDrawer(null);
        setNotice({
          tone: "success",
          message: "组织官方素材已保存；只有创作时明确选择，才会被参考。"
        });
      })
      .catch(error =>
        setNotice({ tone: "error", message: readableRequestError(error) })
      )
      .finally(() => setSaving(false));
  };
  const saveOrganization = (event: FormEvent): void => {
    event.preventDefault();
    setSaving(true);
    void api("/api/v1/tenant-management/organizations", {
      method: "POST",
      body: JSON.stringify({
        name: organizationForm.name,
        organization_level: organizationForm.level,
        as_synthetic_business_fixture: false
      })
    })
      .then(async () => {
        await organizations.refresh();
        setDrawer("reference");
        setNotice({
          tone: "success",
          message: "组织已建立。它的层级来自你的明确选择，不会按名称推断。"
        });
      })
      .catch(error =>
        setNotice({ tone: "error", message: readableRequestError(error) })
      )
      .finally(() => setSaving(false));
  };
  return (
    <section className="tenant-page">
      <header className="tenant-heading split">
        <div>
          <p className="eyebrow">品牌资料库</p>
          <h1>资料来自哪里，谁可以使用</h1>
        </div>
        <button
          type="button"
          className="primary"
          onClick={() => {
            setForm({
              category: "brand_expression",
              title: "",
              sourceNote: "",
              content: "",
              version: "V1",
              visibilityScope: "brand_all",
              organizationIds: []
            });
            setDrawer("reference");
          }}
        >
          新增资料
        </button>
      </header>
      <div className="library-filters" role="group" aria-label="资料可用范围">
        {[
          ["all", "全部"],
          ["brand_all", "品牌全员"],
          ["headquarters", "总部专用"],
          ["organizations", "指定区域"]
        ].map(([value, label]) => (
          <button
            key={value}
            type="button"
            className={filter === value ? "active" : ""}
            aria-pressed={filter === value}
            onClick={() => setFilter(value as "all" | LibraryScope)}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="library-secondary-actions" aria-label="业务资料快捷入口">
        <button
          type="button"
          className="text-action"
          onClick={() => {
            setProductRows([emptyProduct()]);
            setConfirmProducts(false);
            setProductScope("brand_all");
            setProductOrganizationIds([]);
            setDrawer("product");
          }}
        >
          维护商品事实
        </button>
        <button
          type="button"
          className="text-action"
          onClick={() => {
            setMaterialForm({
              organizationId: "",
              title: "",
              note: "",
              file: null,
              visibilityScope: "brand_all",
              scopeOrganizationIds: []
            });
            setDrawer("material");
          }}
        >
          添加组织官方素材
        </button>
      </div>
      {entries.error ? (
        <RequestFailure message={entries.error} onRetry={entries.refresh} />
      ) : (
        <>
          <section className="tenant-subsection">
            <header>
              <h2>品牌表达与参考资料</h2>
              <span>{visible.length} 份</span>
            </header>
            <div className="library-list">
              {visible.map(entry => (
                <article key={entry.id}>
                  <header>
                    <div>
                      <span className={`scope-label ${entry.visibility_scope}`}>
                        {readableScope(
                          entry.visibility_scope,
                          entry.scope_organizations
                        )}
                      </span>
                      <h2>{entry.title}</h2>
                    </div>
                    <span>{entry.version}</span>
                  </header>
                  <p>{entry.source_note}</p>
                  <dl>
                    <div>
                      <dt>谁可用</dt>
                      <dd>
                        {readableScope(
                          entry.visibility_scope,
                          entry.scope_organizations
                        )}
                      </dd>
                    </div>
                    <div>
                      <dt>更新时间</dt>
                      <dd>{humanDate(entry.updated_at)}</dd>
                    </div>
                    <div>
                      <dt>影响</dt>
                      <dd>{entry.impact || "供当前品牌的创作工作参考"}</dd>
                    </div>
                  </dl>
                </article>
              ))}
              {!entries.loading && visible.length === 0 && (
                <p className="tenant-empty">这个范围还没有品牌表达或参考资料。</p>
              )}
            </div>
          </section>
          <section className="tenant-subsection">
            <header>
              <h2>商品事实</h2>
              <span>{visibleProducts.length} 件</span>
            </header>
            {products.error ? (
              <RequestFailure message={products.error} onRetry={products.refresh} />
            ) : (
              <div className="product-list">
                {visibleProducts.map(item => {
                  const facts = item.facts ?? {};
                  const category = facts.category ?? item.category ?? "未填写品类";
                  const features =
                    facts.observable_features ??
                    item.observable_features ??
                    "尚无肉眼可见特征说明";
                  return (
                    <article key={item.sku}>
                      <div>
                        <strong>{item.display_name}</strong>
                        <span>
                          {item.sku} · {category}
                        </span>
                      </div>
                      <span>V{item.fact_version ?? 1}</span>
                      <p>{features}</p>
                      <p>
                        来源：{item.source_note} · 谁可用：
                        {readableScope(
                          item.visibility_scope,
                          item.scope_organizations
                        )}
                        {item.updated_at
                          ? ` · 更新于 ${humanDate(item.updated_at)}`
                          : ""}
                      </p>
                    </article>
                  );
                })}
                {!products.loading && visibleProducts.length === 0 && (
                  <p className="tenant-empty">这个范围还没有商品事实。</p>
                )}
              </div>
            )}
          </section>
          <section className="tenant-subsection">
            <header>
              <h2>组织官方素材</h2>
              <span>{visibleMaterials.length} 份</span>
            </header>
            {materials.error ? (
              <RequestFailure message={materials.error} onRetry={materials.refresh} />
            ) : (
              <div className="material-list">
                {visibleMaterials.map(item => (
                  <article key={item.id}>
                    <div>
                      <strong>{item.title}</strong>
                      <span>
                        {item.original_filename} · V{item.reference_version ?? 1}
                      </span>
                      <p>
                        来源：{item.organization}
                        {item.reference_note ? ` · ${item.reference_note}` : ""}
                      </p>
                      <p>
                        谁可用：
                        {readableScope(
                          item.visibility_scope,
                          item.scope_organizations
                        )}
                        {item.created_at
                          ? ` · 更新于 ${humanDate(item.created_at)}`
                          : ""}
                      </p>
                    </div>
                  </article>
                ))}
                {!materials.loading && visibleMaterials.length === 0 && (
                  <p className="tenant-empty">这个范围还没有组织官方素材。</p>
                )}
              </div>
            )}
          </section>
        </>
      )}
      {drawer === "reference" && (
        <Drawer title="新增品牌资料" onClose={() => setDrawer(null)}>
          <form className="tenant-form" onSubmit={save}>
            <label>
              资料分类
              <select
                value={form.category}
                onChange={event => setForm({ ...form, category: event.target.value })}
              >
                <option value="brand_expression">品牌战略与表达资料</option>
                <option value="product">商品候选资料（非商品事实）</option>
                <option value="organization_fact">组织、区域与门店事实</option>
                <option value="reference">品牌知识与参考资料</option>
                <option value="official_material">组织官方素材说明（非原件）</option>
              </select>
            </label>
            <label>
              资料名称
              <input
                required
                value={form.title}
                onChange={event => setForm({ ...form, title: event.target.value })}
              />
            </label>
            <label>
              粘贴文字资料
              <textarea
                required
                value={form.content}
                onChange={event => setForm({ ...form, content: event.target.value })}
              />
            </label>
            <label>
              或读取文本文件
              <input
                type="file"
                accept=".txt,.md,.csv,text/plain,text/csv"
                onChange={event => {
                  const file = event.target.files?.[0];
                  if (file) void file.text().then(content => setForm(value => ({ ...value, content })));
                }}
              />
            </label>
            <label>
              自然来源说明
              <textarea
                required
                value={form.sourceNote}
                onChange={event =>
                  setForm({ ...form, sourceNote: event.target.value })
                }
              />
            </label>
            <label>
              版本
              <input
                required
                value={form.version}
                onChange={event => setForm({ ...form, version: event.target.value })}
              />
            </label>
            <label>
              可用范围
              <select
                value={form.visibilityScope}
                onChange={event =>
                  setForm({
                    ...form,
                    visibilityScope: event.target.value as LibraryScope,
                    organizationIds: []
                  })
                }
              >
                <option value="brand_all">品牌全员</option>
                <option value="headquarters">总部专用</option>
                <option value="organizations">指定区域</option>
              </select>
            </label>
            {form.visibilityScope !== "brand_all" && (
              <fieldset>
                <legend>
                  {form.visibilityScope === "headquarters"
                    ? "明确选择公司级组织"
                    : "选择可用区域"}
                </legend>
                {organizations.data
                  ?.filter(item => {
                    const level = item.level ?? item.organization_level;
                    return form.visibilityScope === "headquarters"
                      ? level === "company"
                      : level === "region";
                  })
                  .map(item => (
                    <label key={item.id}>
                      <input
                        type={
                          form.visibilityScope === "headquarters"
                            ? "radio"
                            : "checkbox"
                        }
                        name={
                          form.visibilityScope === "headquarters"
                            ? "headquarters-organization"
                            : undefined
                        }
                        checked={form.organizationIds.includes(item.id)}
                        onChange={() => selectScopeOrganization(item.id)}
                      />
                      {item.name}
                    </label>
                  ))}
                <small>未选择的其他区域默认不可使用这份资料。</small>
                <button
                  type="button"
                  className="text-action"
                  onClick={() => {
                    setOrganizationForm({ name: "", level: "unspecified" });
                    setDrawer("organization");
                  }}
                >
                  需要新的组织？先明确建立
                </button>
              </fieldset>
            )}
            <button
              className="primary"
              type="submit"
              disabled={
                saving ||
                (form.visibilityScope !== "brand_all" &&
                  form.organizationIds.length === 0)
              }
            >
              保存资料
            </button>
          </form>
        </Drawer>
      )}
      {drawer === "organization" && (
        <Drawer title="建立组织" onClose={() => setDrawer("reference")}>
          <form className="tenant-form" onSubmit={saveOrganization}>
            <label>
              组织名称
              <input
                required
                value={organizationForm.name}
                onChange={event =>
                  setOrganizationForm({
                    ...organizationForm,
                    name: event.target.value
                  })
                }
              />
            </label>
            <label>
              组织层级
              <select
                value={organizationForm.level}
                onChange={event =>
                  setOrganizationForm({
                    ...organizationForm,
                    level: event.target.value
                  })
                }
              >
                <option value="company">公司 / 总部</option>
                <option value="region">区域</option>
                <option value="operating_unit">经营单位 / 门店</option>
                <option value="unspecified">暂未分类</option>
              </select>
            </label>
            <p>组织层级由你明确选择；系统不会根据名称猜测。</p>
            <button className="primary" type="submit" disabled={saving}>
              建立组织
            </button>
          </form>
        </Drawer>
      )}
      {drawer === "product" && (
        <Drawer title="维护商品事实" onClose={() => setDrawer(null)}>
          <form className="tenant-form" onSubmit={saveProducts}>
            <p>
              可以手工填写一件，或导入 CSV 后先预览。只有明确确认后，才会保存为当前商品事实。
            </p>
            <label>
              导入 CSV（可选）
              <input
                type="file"
                accept=".csv,text/csv"
                onChange={event => {
                  const file = event.target.files?.[0];
                  if (!file) return;
                  void file.text().then(text => {
                    const rows = parseProductCsv(text);
                    if (rows.length) setProductRows(rows);
                    else
                      setNotice({
                        tone: "error",
                        message: "没有读到商品数据，请检查表头和内容。"
                      });
                  });
                }}
              />
            </label>
            {productRows.length === 1 ? (
              <>
                {[
                  ["sku", "商品编号"],
                  ["display_name", "商品名称"],
                  ["category", "品类"],
                  ["colors", "颜色（逗号分隔）"],
                  ["silhouette", "轮廓"]
                ].map(([key, label]) => (
                  <label key={key}>
                    {label}
                    <input
                      required={["sku", "display_name"].includes(key)}
                      value={productRows[0][key as keyof ProductDraft]}
                      onChange={event =>
                        setProductRows([{ ...productRows[0], [key]: event.target.value }])
                      }
                    />
                  </label>
                ))}
                {[
                  ["material_or_structure", "材质或结构"],
                  ["observable_features", "肉眼可见特征"],
                  ["source_note", "资料来源说明"],
                  ["applicability", "适用范围"]
                ].map(([key, label]) => (
                  <label key={key}>
                    {label}
                    <textarea
                      required={["source_note", "applicability"].includes(key)}
                      value={productRows[0][key as keyof ProductDraft]}
                      onChange={event =>
                        setProductRows([{ ...productRows[0], [key]: event.target.value }])
                      }
                    />
                  </label>
                ))}
              </>
            ) : (
              <div className="product-import-preview">
                <p>将保存 {productRows.length} 条商品事实，先核对关键字段：</p>
                <div className="tenant-table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>编号</th>
                        <th>名称</th>
                        <th>来源</th>
                        <th>适用范围</th>
                      </tr>
                    </thead>
                    <tbody>
                      {productRows.slice(0, 8).map((item, index) => (
                        <tr key={`${item.sku}-${index}`}>
                          <td>{item.sku || "缺少"}</td>
                          <td>{item.display_name || "缺少"}</td>
                          <td>{item.source_note || "缺少"}</td>
                          <td>{item.applicability || "缺少"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
            <label>
              商品事实可用范围
              <select
                value={productScope}
                onChange={event => {
                  setProductScope(event.target.value as LibraryScope);
                  setProductOrganizationIds([]);
                }}
              >
                <option value="brand_all">品牌全员</option>
                <option value="headquarters">总部专用</option>
                <option value="organizations">指定区域</option>
              </select>
            </label>
            {productScope !== "brand_all" && (
              <fieldset>
                <legend>
                  {productScope === "headquarters"
                    ? "选择公司级组织"
                    : "选择可用区域"}
                </legend>
                {organizations.data
                  ?.filter(item => {
                    const level = item.level ?? item.organization_level;
                    return productScope === "headquarters"
                      ? level === "company"
                      : level === "region";
                  })
                  .map(item => (
                    <label key={item.id}>
                      <input
                        type={productScope === "headquarters" ? "radio" : "checkbox"}
                        name={
                          productScope === "headquarters"
                            ? "product-headquarters"
                            : undefined
                        }
                        checked={productOrganizationIds.includes(item.id)}
                        onChange={() =>
                          setProductOrganizationIds(value =>
                            productScope === "headquarters"
                              ? [item.id]
                              : value.includes(item.id)
                                ? value.filter(id => id !== item.id)
                                : [...value, item.id]
                          )
                        }
                      />
                      {item.name}
                    </label>
                  ))}
              </fieldset>
            )}
            <label className="fact-confirmation">
              <input
                type="checkbox"
                checked={confirmProducts}
                onChange={event => setConfirmProducts(event.target.checked)}
              />
              我确认这些是当前品牌可负责的商品事实，不是候选推断。
            </label>
            <button
              className="primary"
              type="submit"
              disabled={
                !confirmProducts ||
                saving ||
                (productScope !== "brand_all" &&
                  productOrganizationIds.length === 0)
              }
            >
              保存商品事实
            </button>
          </form>
        </Drawer>
      )}
      {drawer === "material" && (
        <Drawer title="添加组织官方素材" onClose={() => setDrawer(null)}>
          <form className="tenant-form" onSubmit={saveMaterial}>
            <label>
              归属组织
              <select
                required
                value={materialForm.organizationId}
                onChange={event =>
                  setMaterialForm({
                    ...materialForm,
                    organizationId: event.target.value
                  })
                }
              >
                <option value="">请选择</option>
                {organizations.data?.map(item => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              素材名称
              <input
                required
                value={materialForm.title}
                onChange={event =>
                  setMaterialForm({ ...materialForm, title: event.target.value })
                }
              />
            </label>
            <label>
              可用范围
              <select
                value={materialForm.visibilityScope}
                onChange={event =>
                  setMaterialForm({
                    ...materialForm,
                    visibilityScope: event.target.value as LibraryScope,
                    scopeOrganizationIds: []
                  })
                }
              >
                <option value="brand_all">品牌全员</option>
                <option value="headquarters">总部专用</option>
                <option value="organizations">指定区域</option>
              </select>
            </label>
            {materialForm.visibilityScope !== "brand_all" && (
              <fieldset>
                <legend>
                  {materialForm.visibilityScope === "headquarters"
                    ? "选择公司级组织"
                    : "选择可用区域"}
                </legend>
                {organizations.data
                  ?.filter(item => {
                    const level = item.level ?? item.organization_level;
                    return materialForm.visibilityScope === "headquarters"
                      ? level === "company"
                      : level === "region";
                  })
                  .map(item => (
                    <label key={item.id}>
                      <input
                        type={
                          materialForm.visibilityScope === "headquarters"
                            ? "radio"
                            : "checkbox"
                        }
                        name={
                          materialForm.visibilityScope === "headquarters"
                            ? "material-headquarters"
                            : undefined
                        }
                        checked={materialForm.scopeOrganizationIds.includes(item.id)}
                        onChange={() =>
                          setMaterialForm(value => ({
                            ...value,
                            scopeOrganizationIds:
                              value.visibilityScope === "headquarters"
                                ? [item.id]
                                : value.scopeOrganizationIds.includes(item.id)
                                  ? value.scopeOrganizationIds.filter(
                                      id => id !== item.id
                                    )
                                  : [...value.scopeOrganizationIds, item.id]
                          }))
                        }
                      />
                      {item.name}
                    </label>
                  ))}
              </fieldset>
            )}
            <label>
              选择原件
              <input
                required
                type="file"
                onChange={event =>
                  setMaterialForm({
                    ...materialForm,
                    file: event.target.files?.[0] ?? null
                  })
                }
              />
            </label>
            <label>
              人工说明
              <textarea
                required
                value={materialForm.note}
                onChange={event =>
                  setMaterialForm({ ...materialForm, note: event.target.value })
                }
                placeholder="说明创作时可以参考什么；系统不会读取或加工原件内容。"
              />
            </label>
            <button
              className="primary"
              type="submit"
              disabled={
                saving ||
                !materialForm.file ||
                (materialForm.visibilityScope !== "brand_all" &&
                  materialForm.scopeOrganizationIds.length === 0)
              }
            >
              保存组织素材
            </button>
          </form>
        </Drawer>
      )}
    </section>
  );
}

function Readiness({ onSection }: { onSection: (section: Section) => void }): JSX.Element {
  const readiness = useRequest<{ items: ReadinessItem[] }>("/api/v1/admin/readiness");
  return (
    <section className="tenant-page">
      <header className="tenant-heading">
        <p className="eyebrow">当前可用与待补</p>
        <h1>缺什么，会影响哪项工作</h1>
      </header>
      {readiness.loading ? (
        <p className="tenant-loading">正在读取当前依据……</p>
      ) : readiness.error ? (
        <RequestFailure message={readiness.error} onRetry={readiness.refresh} />
      ) : (
        <div className="readiness-list">
          {readiness.data?.items.map(item => (
            <article key={item.id}>
              <header>
                <h2>{item.title}</h2>
                <StatusPill status={item.status} />
              </header>
              <dl>
                <div>
                  <dt>判断依据</dt>
                  <dd>{item.evidence.join("；") || "当前还没有足够依据"}</dd>
                </div>
                <div>
                  <dt>缺少资料</dt>
                  <dd>{item.gaps.join("；") || "没有当前缺口"}</dd>
                </div>
                <div>
                  <dt>影响</dt>
                  <dd>{item.impact}</dd>
                </div>
                <div>
                  <dt>来源与时间</dt>
                  <dd>
                    {item.source} · {item.version} · {humanDate(item.evaluated_at)}
                  </dd>
                </div>
              </dl>
              {item.status !== "available" && (
                <button
                  type="button"
                  className="text-action"
                  onClick={() => onSection(item.action.section)}
                >
                  {item.action.label}
                </button>
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

export default function TenantAdminApp({
  context,
  onPasswordUpdated
}: {
  context: BootstrapContext;
  onPasswordUpdated?: (path: string) => void;
}): JSX.Element {
  const [section, setSection] = useState<Section>("overview");
  const [notice, setNotice] = useState<Notice>(null);
  const [securityOpen, setSecurityOpen] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const mobileMenuTrigger = useRef<HTMLButtonElement>(null);
  const firstNavigationItem = useRef<HTMLButtonElement>(null);
  const identity = context.identity ?? {};
  const title = useMemo(() => identity.brand ?? "品牌管理", [identity.brand]);
  useEffect(() => {
    if (mobileMenuOpen) firstNavigationItem.current?.focus();
  }, [mobileMenuOpen]);
  return (
    <div className="tenant-admin-app">
      {mobileMenuOpen && (
        <button
          className="tenant-nav-backdrop"
          type="button"
          aria-label="关闭品牌管理菜单"
          onClick={() => {
            setMobileMenuOpen(false);
            mobileMenuTrigger.current?.focus();
          }}
        />
      )}
      <aside
        className={`tenant-nav ${mobileMenuOpen ? "mobile-open" : ""}`}
        onKeyDown={event => {
          if (event.key === "Escape") {
            setMobileMenuOpen(false);
            mobileMenuTrigger.current?.focus();
          }
        }}
      >
        <a href="/tenant-admin" aria-label="回到品牌管理首页">
          <BrandMark />
        </a>
        <p className="tenant-nav-title">品牌管理</p>
        <nav aria-label="品牌管理导航">
          {sections.map((item, index) => (
            <button
              ref={index === 0 ? firstNavigationItem : undefined}
              type="button"
              key={item.id}
              className={section === item.id ? "active" : ""}
              aria-current={section === item.id ? "page" : undefined}
              onClick={() => {
                setNotice(null);
                setSection(item.id);
                setMobileMenuOpen(false);
              }}
            >
              {item.label}
            </button>
          ))}
          <button
            type="button"
            onClick={() => {
              setMobileMenuOpen(false);
              setSecurityOpen(true);
            }}
          >
            账户安全
          </button>
        </nav>
      </aside>
      <main>
        <header className="tenant-topbar">
          <button
            ref={mobileMenuTrigger}
            className="tenant-mobile-menu"
            type="button"
            aria-expanded={mobileMenuOpen}
            onClick={() => setMobileMenuOpen(value => !value)}
          >
            菜单
          </button>
          <span>{title}</span>
          <details className="tenant-account-menu">
            <summary>
              <span>{identity.operator ?? "个人菜单"}</span>
            </summary>
            <div>
              <button
                type="button"
                onClick={event => {
                  setSecurityOpen(true);
                  event.currentTarget.closest("details")?.removeAttribute("open");
                }}
              >
                账户安全
              </button>
              <form method="post" action="/tenant-admin/logout">
                <button type="submit">退出登录</button>
              </form>
            </div>
          </details>
        </header>
        <PageNotice notice={notice} onDismiss={() => setNotice(null)} />
        {section === "overview" && <Overview onSection={setSection} />}
        {section === "usage" && <TeamUsage />}
        {section === "members" && (
          <Members setNotice={setNotice} currentUserId={identity.operator_id ?? ""} />
        )}
        {section === "accounts" && <Accounts setNotice={setNotice} />}
        {section === "library" && <BrandLibrary setNotice={setNotice} />}
        {section === "readiness" && <Readiness onSection={setSection} />}
      </main>
      {securityOpen && (
        <AccountSecurity
          onClose={() => setSecurityOpen(false)}
          onPasswordUpdated={onPasswordUpdated}
        />
      )}
    </div>
  );
}
