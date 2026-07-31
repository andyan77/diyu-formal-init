import { useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent, JSX, KeyboardEvent as ReactKeyboardEvent } from "react";
import { BrandMark } from "../components/Brand";
import { ApiError, api } from "../services/api";
import "../styles/tenant-admin.css";
import type { BootstrapContext, Target } from "./types";
import {
  publishingChannelForTarget,
  publishingPlatformChoices,
  publishingTargetContract
} from "./publishingTargets";

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
  parent_organization_id?: string | null;
};

type AccountGrant = {
  account_id: string;
  account_name: string;
  account_enabled: boolean;
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
  enabled: boolean;
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
    enabled: boolean;
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
type ProfileVersion = ProfileSegments & {
  profile_id: string;
  version: number;
};

type BrandExpressionBaseline = {
  version: number;
  status: "draft" | "confirmed";
  draft: string;
};

type OnboardingPrefill = {
  account_profile_candidate: ProfileSegments;
  account_profile_candidate_source: string;
};

type Usage = {
  window_days: 7 | 30;
  members: {
    registered: number;
    activated: number;
    enabled: number;
    disabled: number;
    active: number;
    logged_in: number;
    product_active: number;
    items: Array<{
      id: string;
      display_name: string;
      entry_type: EntryType;
      enabled: boolean;
      last_login_at: string | null;
      last_product_action_at: string | null;
      last_used_at: string | null;
      content_attempts: number;
      display_attempts: number;
    }>;
  };
  activity: {
    content_attempts: number;
    content_successes: number;
    content_failures: number;
    conversations: number;
    first_generations: number;
    revisions: number;
    series_continuations: number;
    dm01_plans: number;
    display_attempts: number;
    display_successes: number;
    display_failures: number;
    rate_limited: number;
    successful_runs: number;
    failed_runs: number;
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
  evidence_details?: Array<{
    source: string;
    resource_id?: string;
    version: string;
    version_id?: string | null;
    scope: string;
    updated_at: string | null;
    updated_at_label?: string;
  }>;
  gaps: string[];
  conflicts?: string[];
  impact: string;
  unaffected?: string[];
  action: { label: string; section: Section };
  source: string;
  version: string;
  contract_version?: string;
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
  current_version_id?: string | null;
  visibility_scope: LibraryScope;
  visibility_label: string;
  scope_organizations: Organization[];
  updated_by: string | null;
  updated_at: string;
  impact: string;
};

type ProductFact = {
  id: string;
  sku: string;
  display_name: string;
  facts?: {
    category?: string;
    colors?: string[];
    material_or_structure?: string;
    silhouette?: string;
    observable_features?: string;
    display_family?: "upper" | "lower";
    is_long?: boolean;
    accent?: boolean;
  };
  category?: string;
  colors?: string[];
  material_or_structure?: string;
  silhouette?: string;
  observable_features?: string;
  source_note: string;
  applicability: string;
  fact_version?: number;
  status?: "active" | "retired";
  current_version_id?: string | null;
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
  display_family: "" | "upper" | "lower";
  display_is_long: boolean;
  display_accent: boolean;
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
  status?: "active" | "inactive";
  current_version_id?: string | null;
  visibility_scope?: LibraryScope;
  scope_organizations?: Organization[];
  created_at?: string;
};

type ProductMediaBinding = {
  id: string;
  product_id: string;
  asset_id: string;
  usage_kind: "existing_product_media";
  status: "active" | "inactive";
  sku: string;
  product_name: string;
  product_status: "active" | "retired";
  product_version_id: string;
  product_version: number;
  created_at: string;
  updated_at: string;
};

type LibraryVersion = {
  id: string;
  version_number: number;
  version: string;
  title: string;
  source_note: string;
  content: string;
  visibility_scope: LibraryScope;
  organization_ids: string[];
  status: LibraryEntry["status"];
  is_current: boolean;
  created_at: string;
};

type ProductVersion = {
  id: string;
  fact_version: number;
  display_name: string;
  facts: NonNullable<ProductFact["facts"]>;
  source_note: string;
  applicability: string;
  visibility_scope: LibraryScope;
  organization_ids: string[];
  status: "active" | "retired";
  is_current: boolean;
  created_at: string;
};

type MaterialVersion = {
  id: string;
  version: number;
  title: string;
  reference_note: string;
  visibility_scope: LibraryScope;
  organization_ids: string[];
  status: "active" | "inactive";
  is_current: boolean;
  created_at: string;
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
  ...Object.fromEntries(
    Object.entries(publishingTargetContract).map(([key, value]) => [
      key,
      value.label
    ])
  ) as Record<Target, string>,
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

async function copyOneTimeLink(
  link: string,
  setNotice: (notice: Notice) => void
): Promise<void> {
  try {
    await navigator.clipboard.writeText(link);
    setNotice({ tone: "success", message: "链接已复制" });
  } catch {
    setNotice({
      tone: "error",
      message: "未能自动复制，请手动选择上方链接"
    });
  }
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

type ProductTextField = Exclude<
  keyof ProductDraft,
  "display_family" | "display_is_long" | "display_accent"
>;

function parseProductCsv(text: string): ProductDraft[] {
  const lines = text.split(/\r?\n/).filter(line => line.trim());
  if (lines.length < 2) return [];
  const headers = splitCsvLine(lines[0]).map(value => value.toLowerCase());
  const aliases: Record<ProductTextField, string[]> = {
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
  const column = (key: ProductTextField): number =>
    headers.findIndex(header => aliases[key].includes(header));
  return lines.slice(1).map(line => {
    const values = splitCsvLine(line);
    const read = (key: ProductTextField): string => {
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
      display_family: "",
      display_is_long: false,
      display_accent: false,
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
  display_family: "",
  display_is_long: false,
  display_accent: false,
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
              <dt>启用成员</dt>
              <dd>{data?.members.enabled ?? 0}</dd>
            </div>
            <div>
              <dt>有登录行为</dt>
              <dd>{data?.members.logged_in ?? 0}</dd>
            </div>
            <div>
              <dt>有实际产品动作</dt>
              <dd>{data?.members.product_active ?? 0}</dd>
            </div>
            <div>
              <dt>成功 / 失败运行</dt>
              <dd>
                {data?.activity.successful_runs ?? 0} /{" "}
                {data?.activity.failed_runs ?? 0}
              </dd>
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
                      <th>最近登录</th>
                      <th>最近产品动作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data?.members.items.map(member => (
                      <tr key={member.id}>
                        <td>{member.display_name}</td>
                        <td>
                          {member.entry_type === "tenant_admin" ? "租户管理员" : "租户用户"}
                        </td>
                        <td>{humanDate(member.last_login_at)}</td>
                        <td>{humanDate(member.last_product_action_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
            <section>
              <h2>产品动作</h2>
              <dl className="usage-action-breakdown">
                <div>
                  <dt>普通交流</dt>
                  <dd>{data?.activity.conversations ?? 0}</dd>
                </div>
                <div>
                  <dt>首次生成 / 内容修改</dt>
                  <dd>
                    {data?.activity.first_generations ?? 0} /{" "}
                    {data?.activity.revisions ?? 0}
                  </dd>
                </div>
                <div>
                  <dt>系列续写</dt>
                  <dd>{data?.activity.series_continuations ?? 0}</dd>
                </div>
                <div>
                  <dt>陈列参考方案</dt>
                  <dd>{data?.activity.dm01_plans ?? 0}</dd>
                </div>
                <div>
                  <dt>429</dt>
                  <dd>{data?.activity.rate_limited ?? 0}</dd>
                </div>
              </dl>
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
  const [copyFeedback, setCopyFeedback] = useState<Notice>(null);
  const [confirmingDisable, setConfirmingDisable] = useState(false);
  const [restoreDisableFocus, setRestoreDisableFocus] = useState(false);
  const disableTrigger = useRef<HTMLButtonElement>(null);
  const confirmDisableButton = useRef<HTMLButtonElement>(null);
  const disableInFlight = useRef(false);
  const [form, setForm] = useState({
    displayName: "",
    username: "",
    organizationId: "",
    entryType: "tenant_user" as EntryType,
    content: true,
    display: false,
    accountIds: [] as string[],
    maintenanceAccountIds: [] as string[]
  });
  const [edit, setEdit] = useState({
    displayName: "",
    organizationId: "",
    entryType: "tenant_user" as EntryType,
    content: false,
    display: false,
    accountIds: [] as string[],
    maintenanceAccountIds: [] as string[]
  });

  const refresh = async (): Promise<void> => {
    await Promise.all([operators.refresh(), accounts.refresh()]);
  };
  useEffect(() => {
    if (confirmingDisable) {
      confirmDisableButton.current?.focus();
    }
  }, [confirmingDisable]);
  useEffect(() => {
    if (!restoreDisableFocus || confirmingDisable) return;
    const trigger = disableTrigger.current;
    if (trigger?.isConnected) {
      trigger.focus();
      setRestoreDisableFocus(false);
    }
  }, [confirmingDisable, restoreDisableFocus]);

  const cancelDisable = (): void => {
    setConfirmingDisable(false);
    setRestoreDisableFocus(true);
  };
  const closeDrawer = (): void => {
    setDrawer(null);
    setActivationLink("");
    setCopyFeedback(null);
    setConfirmingDisable(false);
    setRestoreDisableFocus(false);
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
    setCopyFeedback(null);
    setConfirmingDisable(false);
    setRestoreDisableFocus(false);
    setForm({
      displayName: "",
      username: "",
      organizationId: "",
      entryType: "tenant_user",
      content: true,
      display: false,
      accountIds: [],
      maintenanceAccountIds: []
    });
    setDrawer("create");
  };
  const create = (event: FormEvent): void => {
    event.preventDefault();
    setCopyFeedback(null);
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
            expression_profile_maintenance_account_ids:
              form.entryType === "tenant_user"
                ? form.maintenanceAccountIds
                : [],
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
        : [...value.accountIds, accountId],
      maintenanceAccountIds: value.accountIds.includes(accountId)
        ? value.maintenanceAccountIds.filter(item => item !== accountId)
        : value.maintenanceAccountIds
    }));
  };
  const openMember = (member: Operator): void => {
    setActivationLink("");
    setCopyFeedback(null);
    setConfirmingDisable(false);
    setRestoreDisableFocus(false);
    setEdit({
      displayName: member.display_name,
      organizationId: member.organization_id,
      entryType: member.entry_type,
      content: hasCapability(member, "content"),
      display: hasCapability(member, "display"),
      accountIds: member.account_grants.map(item => item.account_id),
      maintenanceAccountIds: member.account_grants
        .filter(item => item.can_maintain_expression_profile)
        .map(item => item.account_id)
    });
    setDrawer(member);
  };
  const toggleEditAccount = (accountId: string): void => {
    setEdit(value => ({
      ...value,
      accountIds: value.accountIds.includes(accountId)
        ? value.accountIds.filter(item => item !== accountId)
        : [...value.accountIds, accountId],
      maintenanceAccountIds: value.accountIds.includes(accountId)
        ? value.maintenanceAccountIds.filter(item => item !== accountId)
        : value.maintenanceAccountIds
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
        <Drawer title="添加成员" onClose={closeDrawer}>
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
                      accountIds: [],
                      maintenanceAccountIds: []
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
                          accountIds: event.target.checked ? form.accountIds : [],
                          maintenanceAccountIds: event.target.checked
                            ? form.maintenanceAccountIds
                            : []
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
                  {accounts.data
                    ?.filter(account => account.enabled)
                    .map(account => (
                      <div key={account.id} className="account-grant-choice">
                        <label>
                          <input
                            type="checkbox"
                            disabled={!form.content}
                            checked={form.accountIds.includes(account.id)}
                            onChange={() => toggleAccount(account.id)}
                          />
                          使用 {account.name}
                        </label>
                        <label>
                          <input
                            type="checkbox"
                            disabled={!form.accountIds.includes(account.id)}
                            checked={form.maintenanceAccountIds.includes(
                              account.id
                            )}
                            onChange={event =>
                              setForm(value => ({
                                ...value,
                                maintenanceAccountIds: event.target.checked
                                  ? [
                                      ...value.maintenanceAccountIds,
                                      account.id
                                    ]
                                  : value.maintenanceAccountIds.filter(
                                      item => item !== account.id
                                    )
                              }))
                            }
                          />
                          可维护五段画像
                        </label>
                      </div>
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
                  onClick={() => void copyOneTimeLink(activationLink, setCopyFeedback)}
                >
                  复制链接
                </button>
                {copyFeedback && (
                  <p
                    className={`one-time-link-feedback ${copyFeedback.tone}`}
                    role="status"
                    aria-live="polite"
                  >
                    {copyFeedback.message}
                  </p>
                )}
              </div>
            )}
          </form>
        </Drawer>
      )}
      {drawer && drawer !== "create" && (
        <Drawer title={drawer.display_name} onClose={closeDrawer}>
          <div className="tenant-detail">
            <p>
              {drawer.organization} ·{" "}
              {drawer.entry_type === "tenant_admin" ? "租户管理员" : "租户用户"}
            </p>
            <fieldset
              className="member-grants"
              disabled={drawer.id === currentUserId}
            >
              <legend>自然人资料</legend>
              <label>
                姓名或工作名
                <input
                  value={edit.displayName}
                  onChange={event =>
                    setEdit({ ...edit, displayName: event.target.value })
                  }
                />
              </label>
              <label>
                所属组织
                <select
                  value={edit.organizationId}
                  onChange={event => {
                    const organizationId = event.target.value;
                    setEdit(value => ({
                      ...value,
                      organizationId,
                      maintenanceAccountIds:
                        value.maintenanceAccountIds.filter(accountId => {
                          const account = accounts.data?.find(
                            item => item.id === accountId
                          );
                          return (
                            account?.control_organization?.id ===
                            organizationId
                          );
                        })
                    }));
                  }}
                >
                  {organizations.data?.map(organization => (
                    <option key={organization.id} value={organization.id}>
                      {organization.name}
                    </option>
                  ))}
                </select>
              </label>
            </fieldset>
            <fieldset
              className="member-grants"
              disabled={drawer.id === currentUserId}
            >
              <legend>入口与工作资格</legend>
              <label>
                <input
                  type="radio"
                  name="edit-entry-type"
                  checked={edit.entryType === "tenant_admin"}
                  onChange={() =>
                    setEdit({
                      ...edit,
                      entryType: "tenant_admin",
                      content: false,
                      display: false,
                      accountIds: [],
                      maintenanceAccountIds: []
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
                          accountIds: event.target.checked ? edit.accountIds : [],
                          maintenanceAccountIds: event.target.checked
                            ? edit.maintenanceAccountIds
                            : []
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
                  {accounts.data?.map(account => {
                    const alreadyGranted =
                      drawer.account_grants.some(
                        item => item.account_id === account.id
                      );
                    const canSelectAccount =
                      account.enabled || alreadyGranted;
                    const canSelectMaintenance =
                      edit.accountIds.includes(account.id) &&
                      account.control_organization?.id ===
                        edit.organizationId &&
                      (account.enabled ||
                        edit.maintenanceAccountIds.includes(account.id));
                    return (
                      <div key={account.id} className="account-grant-choice">
                        <label>
                          <input
                            type="checkbox"
                            disabled={!edit.content || !canSelectAccount}
                            checked={edit.accountIds.includes(account.id)}
                            onChange={() => toggleEditAccount(account.id)}
                          />
                          使用 {account.name}
                          {!account.enabled && (
                            <small>已停用，不能用于新工作</small>
                          )}
                        </label>
                        <label>
                          <input
                            type="checkbox"
                            disabled={!canSelectMaintenance}
                            checked={edit.maintenanceAccountIds.includes(
                              account.id
                            )}
                            onChange={event =>
                              setEdit(value => ({
                                ...value,
                                maintenanceAccountIds: event.target.checked
                                  ? [
                                      ...value.maintenanceAccountIds,
                                      account.id
                                    ]
                                  : value.maintenanceAccountIds.filter(
                                      item => item !== account.id
                                    )
                              }))
                            }
                          />
                          可维护五段画像
                        </label>
                      </div>
                    );
                  })}
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
                  drawer.id === currentUserId ||
                  (edit.entryType === "tenant_user" &&
                    edit.content &&
                    edit.accountIds.length === 0)
                }
                onClick={() =>
                  void run(
                    async () => {
                      await api(
                        `/api/v1/tenant-management/users/${drawer.id}`,
                        {
                          method: "PATCH",
                          body: JSON.stringify({
                            display_name: edit.displayName,
                            organization_id: edit.organizationId
                          })
                        }
                      );
                      await api(`/api/v1/tenant-management/users/${drawer.id}/grants`, {
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
                          expression_profile_maintenance_account_ids:
                            edit.entryType === "tenant_user"
                              ? edit.maintenanceAccountIds
                              : []
                        })
                      });
                    },
                    "成员资格已更新；该成员需要重新登录。"
                  )
                }
              >
                保存入口资格
              </button>
              {drawer.id === currentUserId && (
                <p className="tenant-security-note">
                  当前登录管理员的身份和入口资格需要由另一名管理员维护。
                </p>
              )}
            </fieldset>
            {drawer.enabled ? (
              <button
                className="text-action"
                type="button"
                disabled={saving}
                onClick={() => {
                  setCopyFeedback(null);
                  void run(async () => {
                    const value = await api<{
                      reset_link: string;
                      reset_url: string;
                    }>(
                      `/api/v1/tenant-management/users/${drawer.id}/reset`,
                      { method: "POST" }
                    );
                    setActivationLink(value.reset_url);
                  }, "新的一次性重设密码链接已生成，此前未使用的重设链接已失效。");
                }}
              >
                生成一次性重设密码链接
              </button>
            ) : (
              <button
                className="primary"
                type="button"
                disabled={saving}
                onClick={() => {
                  setCopyFeedback(null);
                  void run(async () => {
                    const value = await api<{
                      activation_link: string;
                      activation_url: string;
                    }>(
                      `/api/v1/tenant-management/users/${drawer.id}/restore`,
                      { method: "POST" }
                    );
                    setActivationLink(value.activation_url);
                  }, "成员登录身份已恢复；请重新分配工作资格，并把新激活链接交给本人。");
                }}
              >
                恢复成员并生成激活链接
              </button>
            )}
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
                  onClick={() => void copyOneTimeLink(activationLink, setCopyFeedback)}
                >
                  复制重设链接
                </button>
                {copyFeedback && (
                  <p
                    className={`one-time-link-feedback ${copyFeedback.tone}`}
                    role="status"
                    aria-live="polite"
                  >
                    {copyFeedback.message}
                  </p>
                )}
              </div>
            )}
            {drawer.id !== currentUserId && drawer.enabled && !confirmingDisable && (
              <button
                ref={disableTrigger}
                className="text-action danger"
                type="button"
                disabled={saving}
                onClick={() => {
                  setRestoreDisableFocus(false);
                  setConfirmingDisable(true);
                }}
              >
                停用成员
              </button>
            )}
            {drawer.id !== currentUserId && drawer.enabled && confirmingDisable && (
              <section
                className="disable-confirmation"
                role="alertdialog"
                aria-labelledby="disable-member-title"
                aria-describedby="disable-member-description"
                onKeyDown={event => {
                  if (event.key === "Escape") {
                    event.preventDefault();
                    event.stopPropagation();
                    cancelDisable();
                  }
                }}
              >
                <h3 id="disable-member-title">确认停用这名成员？</h3>
                <p id="disable-member-description">
                  该成员将无法继续登录，当前会话和工作资格也会被撤销。
                </p>
                <div className="disable-confirmation-actions">
                  <button type="button" className="secondary" onClick={cancelDisable}>
                    取消
                  </button>
                  <button
                    ref={confirmDisableButton}
                    type="button"
                    className="danger-action"
                    disabled={saving}
                    onClick={() => {
                      if (disableInFlight.current) return;
                      disableInFlight.current = true;
                      void run(async () => {
                        await api(
                          `/api/v1/tenant-management/users/${drawer.id}/disable`,
                          { method: "POST" }
                        );
                        setConfirmingDisable(false);
                        setRestoreDisableFocus(false);
                        setCopyFeedback(null);
                        setDrawer(null);
                      }, "成员已停用，现有会话与工作资格已撤销。").finally(() => {
                        disableInFlight.current = false;
                      });
                    }}
                  >
                    确认停用
                  </button>
                </div>
              </section>
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
  const baseline = useRequest<BrandExpressionBaseline>(
    "/api/v1/admin/brand-expression"
  );
  const onboarding = useRequest<OnboardingPrefill>(
    "/api/v1/tenant-management/onboarding-prefill"
  );
  const operators = useRequest<Operator[]>("/api/v1/tenant-management/operators");
  const organizations = useRequest<Organization[]>(
    "/api/v1/tenant-management/control-organizations"
  );
  const [selected, setSelected] = useState<PublishingAccount | null>(null);
  const [drawer, setDrawer] = useState<
    "create" | "target" | "profile" | "settings" | null
  >(null);
  const [saving, setSaving] = useState(false);
  const [profile, setProfile] = useState<ProfileSegments>(emptyProfile);
  const [profileAccess, setProfileAccess] = useState<ManagementProfile | null>(null);
  const [profileVersions, setProfileVersions] = useState<ProfileVersion[]>([]);
  const [profileOrganizationId, setProfileOrganizationId] = useState("");
  const [baselineDraft, setBaselineDraft] = useState("");
  const [createForm, setCreateForm] = useState({
    name: "",
    role: "",
    speakerKind: "institutional_account" as SpeakerKind,
    organizationId: "",
    operatorId: "",
    target: "douyin_video" as Target,
    canMaintainProfile: false,
    profile: emptyProfile()
  });
  const [targetForm, setTargetForm] = useState({
    target: "xiaohongshu_graphic" as Target,
    operatorId: ""
  });
  const [settingsForm, setSettingsForm] = useState({
    name: "",
    organizationId: ""
  });
  useEffect(() => {
    if (baseline.data) setBaselineDraft(baseline.data.draft);
  }, [baseline.data]);
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
      const [access, versions] = await Promise.all([
        api<ManagementProfile>(
          `/api/v1/tenant-management/publishing-accounts/${account.id}/expression-profile`
        ),
        api<ProfileVersion[]>(
          `/api/v1/tenant-management/publishing-accounts/${account.id}/expression-profile/versions`
        )
      ]);
      setSelected(account);
      setProfileAccess(access);
      setProfileVersions(versions);
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
    if (createMaintenanceMismatch) return;
    void run(async () => {
      await api("/api/v1/tenant-management/publishing-accounts", {
        method: "POST",
        body: JSON.stringify({
          name: createForm.name,
          channel: publishingChannelForTarget(createForm.target),
          content_role_name: createForm.role,
          speaker_kind: createForm.speakerKind,
          initial_profile: createForm.profile,
          operator_id: createForm.operatorId,
          control_organization_id: createForm.organizationId,
          operator_can_maintain_expression_profile:
            createForm.canMaintainProfile,
          as_synthetic_business_fixture: false
        })
      });
      setDrawer(null);
    }, "发布账号已建立。平台载体和账号画像会继续归到同一个发布身份。");
  };
  const selectedCreateOperator = operators.data?.find(
    item => item.id === createForm.operatorId
  );
  const createMaintenanceMismatch =
    createForm.canMaintainProfile &&
    (createForm.organizationId.length === 0 ||
      !selectedCreateOperator ||
      selectedCreateOperator.organization_id !== createForm.organizationId);
  const platformCount = new Set(
    (accounts.data ?? []).flatMap(account =>
      account.platform_targets.map(target => target.account_id)
    )
  ).size;
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
              canMaintainProfile: false,
              profile:
                onboarding.data?.account_profile_candidate ?? emptyProfile()
            });
            setDrawer("create");
          }}
          disabled={
            baseline.data?.status !== "confirmed" || onboarding.data === null
          }
        >
          创建发布账号
        </button>
      </header>
      <article className="brand-expression-baseline">
        <div>
          <p className="eyebrow">品牌表达基线</p>
          <h2>
            {baseline.data?.status === "confirmed"
              ? `当前确认版本 V${baseline.data.version}`
              : "确认后才能创建正式发布账号"}
          </h2>
          <p>
            系统先给出可纠正草案；只有管理员确认后的版本才会成为账号冷启动边界。
          </p>
        </div>
        {baseline.error ? (
          <RequestFailure message={baseline.error} onRetry={baseline.refresh} />
        ) : (
          <form
            className="tenant-form"
            onSubmit={event => {
              event.preventDefault();
              setSaving(true);
              void api<BrandExpressionBaseline>(
                "/api/v1/admin/brand-expression/confirm",
                {
                  method: "POST",
                  body: JSON.stringify({ draft: baselineDraft })
                }
              )
                .then(async () => {
                  await baseline.refresh();
                  setNotice({
                    tone: "success",
                    message: "品牌表达基线已确认，可继续建立发布账号。"
                  });
                })
                .catch(error =>
                  setNotice({
                    tone: "error",
                    message: readableRequestError(error)
                  })
                )
                .finally(() => setSaving(false));
            }}
          >
            <label>
              可纠正的品牌表达草案
              <textarea
                required
                value={baselineDraft}
                onChange={event => setBaselineDraft(event.target.value)}
              />
            </label>
            <button
              className="primary"
              type="submit"
              disabled={saving || baselineDraft.trim().length === 0}
            >
              {baseline.data?.status === "confirmed"
                ? "确认修订为新版本"
                : "确认当前品牌表达"}
            </button>
          </form>
        )}
      </article>
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
                    {account.enabled ? "已启用" : "已停用"} ·{" "}
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
                      setSettingsForm({
                        name: account.name,
                        organizationId:
                          account.control_organization?.id ?? ""
                      });
                      setDrawer("settings");
                    }}
                  >
                    账号设置
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
                    disabled={!account.enabled}
                  >
                    添加平台
                  </button>
                  <button
                    type="button"
                    className="text-action"
                    disabled={saving}
                    onClick={() =>
                      void run(
                        () =>
                          api(
                            `/api/v1/tenant-management/publishing-accounts/${account.id}/enabled`,
                            {
                              method: "PUT",
                              body: JSON.stringify({
                                enabled: !account.enabled
                              })
                            }
                          ),
                        account.enabled
                          ? "发布账号已停用；历史引用保持不变。"
                          : "发布账号已恢复。"
                      )
                    }
                  >
                    {account.enabled ? "停用账号" : "恢复账号"}
                  </button>
                </div>
              </header>
              <div className="platform-targets">
                {Array.from(
                  account.platform_targets.reduce(
                    (result, target) => {
                      const current = result.get(target.account_id);
                      if (current) {
                        current.labels.push(targetLabels[target.target]);
                      } else {
                        result.set(target.account_id, {
                          id: target.account_id,
                          platform: target.platform,
                          enabled: target.enabled,
                          labels: [targetLabels[target.target]]
                        });
                      }
                      return result;
                    },
                    new Map<
                      string,
                      {
                        id: string;
                        platform: string;
                        enabled: boolean;
                        labels: string[];
                      }
                    >()
                  ).values()
                ).map(target => (
                  <span key={target.id}>
                    {target.labels.join("、")} ·{" "}
                    {target.enabled ? "可选" : "已停用"}
                    <button
                      type="button"
                      className="text-action"
                      disabled={saving}
                      onClick={() =>
                        void run(
                          () =>
                            api(
                              `/api/v1/tenant-management/platform-carriers/${target.id}/enabled`,
                              {
                                method: "PUT",
                                body: JSON.stringify({
                                  enabled: !target.enabled
                                })
                              }
                            ),
                          target.enabled
                            ? `${target.platform}已停用；历史引用保持不变。`
                            : `${target.platform}已恢复。`
                        )
                      }
                    >
                      {target.enabled ? "停用" : "恢复"}
                    </button>
                  </span>
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
                onChange={event => {
                  const organizationId = event.target.value;
                  setCreateForm(value => ({
                    ...value,
                    organizationId,
                    canMaintainProfile:
                      value.organizationId === organizationId
                        ? value.canMaintainProfile
                        : false
                  }));
                }}
              >
                <option value="">请选择负责团队</option>
                {organizations.data?.map(item => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              <input
                type="checkbox"
                checked={createForm.canMaintainProfile}
                aria-describedby="create-profile-maintenance-rule"
                onChange={event =>
                  setCreateForm({
                    ...createForm,
                    canMaintainProfile: event.target.checked
                  })
                }
              />
              允许这名首位使用者维护五段账号画像
            </label>
            <p
              id="create-profile-maintenance-rule"
              className={createMaintenanceMismatch ? "inline-error" : "tenant-security-note"}
            >
              维护五段画像的成员必须属于账号负责团队；仅使用账号可以跨团队分配。
            </p>
            <label>
              首位使用者
              <select
                required
                value={createForm.operatorId}
                onChange={event => {
                  const operatorId = event.target.value;
                  setCreateForm(value => ({
                    ...value,
                    operatorId,
                    canMaintainProfile:
                      value.operatorId === operatorId
                        ? value.canMaintainProfile
                        : false
                  }));
                }}
              >
                <option value="">请选择租户用户</option>
                {operators.data
                  ?.filter(
                    item => item.entry_type === "tenant_user" && item.enabled
                  )
                  .map(item => (
                    <option key={item.id} value={item.id}>
                      {item.display_name}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              首个平台
              <select
                value={createForm.target}
                onChange={event =>
                  setCreateForm({
                    ...createForm,
                    target: event.target.value as Target
                  })
                }
              >
                {publishingPlatformChoices.map(choice => (
                    <option key={choice.value} value={choice.value}>
                      {choice.label}
                    </option>
                  ))}
              </select>
            </label>
            <fieldset>
              <legend>账号画像</legend>
              <p>
                {onboarding.data?.account_profile_candidate_source ??
                  "这是待纠正候选，保存后才形成 V1。"}
              </p>
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
            <button
              className="primary"
              type="submit"
              disabled={saving || createMaintenanceMismatch}
            >
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
                    channel: publishingChannelForTarget(targetForm.target),
                    operator_id: targetForm.operatorId,
                    confirm_internal_carrier: true
                  })
                });
                setDrawer(null);
              }, "平台载体已加入这个发布账号；账号画像没有复制或改变。");
            }}
          >
            <label>
              平台及其可用形式
              <select
                value={targetForm.target}
                onChange={event =>
                  setTargetForm({
                    ...targetForm,
                    target: event.target.value as Target
                  })
                }
              >
                {publishingPlatformChoices
                  .filter(
                    choice =>
                      !selected.platform_targets.some(target =>
                        choice.targets.includes(target.target)
                      )
                  )
                  .map(choice => (
                    <option key={choice.value} value={choice.value}>
                      {choice.label}
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
                {selected.operators.map(item => (
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
      {drawer === "settings" && selected && (
        <Drawer title={`${selected.name}的账号设置`} onClose={() => setDrawer(null)}>
          <form
            className="tenant-form"
            onSubmit={event => {
              event.preventDefault();
              void run(async () => {
                await api(
                  `/api/v1/tenant-management/publishing-accounts/${selected.id}`,
                  {
                    method: "PATCH",
                    body: JSON.stringify({
                      name: settingsForm.name,
                      control_organization_id:
                        settingsForm.organizationId
                    })
                  }
                );
                setDrawer(null);
              }, "发布账号名称和负责团队已更新；历史内容仍引用原冻结版本。");
            }}
          >
            <label>
              发布账号名称
              <input
                required
                value={settingsForm.name}
                onChange={event =>
                  setSettingsForm({
                    ...settingsForm,
                    name: event.target.value
                  })
                }
              />
            </label>
            <label>
              负责团队
              <select
                required
                value={settingsForm.organizationId}
                onChange={event =>
                  setSettingsForm({
                    ...settingsForm,
                    organizationId: event.target.value
                  })
                }
              >
                <option value="">请选择</option>
                {organizations.data?.map(organization => (
                  <option key={organization.id} value={organization.id}>
                    {organization.name}
                  </option>
                ))}
              </select>
            </label>
            <button className="primary" type="submit" disabled={saving}>
              保存账号设置
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
              {profileVersions.length > 0 && (
                <section className="profile-history">
                  <h3>画像历史</h3>
                  <ol>
                    {profileVersions.map(version => (
                      <li key={version.profile_id}>
                        <strong>V{version.version}</strong>
                        <span>{version.identity_position}</span>
                      </li>
                    ))}
                  </ol>
                </section>
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
    | "reference"
    | "reference-preview"
    | "reference-detail"
    | "product"
    | "product-detail"
    | "material"
    | "material-detail"
    | "organization"
    | null
  >(null);
  const [saving, setSaving] = useState(false);
  const [referencePreview, setReferencePreview] = useState(false);
  const [selectedEntry, setSelectedEntry] = useState<LibraryEntry | null>(null);
  const [entryVersions, setEntryVersions] = useState<LibraryVersion[]>([]);
  const [selectedProduct, setSelectedProduct] = useState<ProductFact | null>(null);
  const [productVersions, setProductVersions] = useState<ProductVersion[]>([]);
  const [selectedMaterial, setSelectedMaterial] =
    useState<OrganizationMaterial | null>(null);
  const [materialVersions, setMaterialVersions] = useState<MaterialVersion[]>([]);
  const [materialBindings, setMaterialBindings] = useState<
    ProductMediaBinding[]
  >([]);
  const [bindingProductId, setBindingProductId] = useState("");
  const [productPreviewSignature, setProductPreviewSignature] =
    useState<string | null>(null);
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
    level: "unspecified",
    parentOrganizationId: ""
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
  const referencePayload = (): Record<string, unknown> => ({
    category: form.category,
    title: form.title,
    source_note: form.sourceNote,
    content: form.content,
    version: form.version,
    visibility_scope: form.visibilityScope,
    organization_ids:
      form.visibilityScope === "brand_all" ? [] : form.organizationIds
  });
  const previewReference = (event: FormEvent): void => {
    event.preventDefault();
    setSaving(true);
    void api("/api/v1/tenant-management/brand-library/preview", {
      method: "POST",
      body: JSON.stringify(referencePayload())
    })
      .then(() => {
        setReferencePreview(true);
        setDrawer("reference-preview");
        setNotice({
          tone: "success",
          message: "已形成导入预览；确认前不会保存为正式资料。"
        });
      })
      .catch(error =>
        setNotice({ tone: "error", message: readableRequestError(error) })
      )
      .finally(() => setSaving(false));
  };
  const confirmReference = (): void => {
    if (!referencePreview) return;
    setSaving(true);
    void api("/api/v1/tenant-management/brand-library", {
      method: "POST",
      body: JSON.stringify({
        ...referencePayload(),
        status: "active",
        confirm_as_current: true
      })
    })
      .then(async () => {
        await entries.refresh();
        setReferencePreview(false);
        setDrawer(null);
        setNotice({
          tone: "success",
          message: "资料已确认保存，当前版本、来源和可用范围已保留。"
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
    if (validRows.length !== productRows.length) return;
    const signature = JSON.stringify(productRows);
    if (productPreviewSignature !== signature) {
      const header = [
        "sku",
        "display_name",
        "category",
        "material_or_structure",
        "silhouette",
        "observable_features"
      ];
      const content = [
        header.join("\t"),
        ...productRows.map(item =>
          header
            .map(key =>
              String(item[key as keyof ProductDraft] ?? "")
                .replaceAll("\t", " ")
                .replaceAll("\n", " ")
            )
            .join("\t")
        )
      ].join("\n");
      setSaving(true);
      void api("/api/v1/tenant-management/brand-products/preview", {
        method: "POST",
        body: JSON.stringify({ source_format: "table", content })
      })
      .then(() => {
        setProductPreviewSignature(signature);
        setConfirmProducts(false);
        setNotice({
            tone: "success",
            message: "字段预览已通过；请核对来源与范围后明确确认保存。"
          });
        })
        .catch(error =>
          setNotice({ tone: "error", message: readableRequestError(error) })
        )
        .finally(() => setSaving(false));
      return;
    }
    if (!confirmProducts) return;
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
            display_family: item.display_family || null,
            display_is_long: item.display_is_long,
            display_accent: item.display_accent,
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
        parent_organization_id: organizationForm.parentOrganizationId || null,
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
  const openEntry = (entry: LibraryEntry): void => {
    setSelectedEntry(entry);
    setForm({
      category: entry.category,
      title: entry.title,
      sourceNote: entry.source_note,
      content: entry.content,
      version: `V${Math.max(2, Number.parseInt(entry.version.replace(/\D/g, ""), 10) + 1 || 2)}`,
      visibilityScope: entry.visibility_scope,
      organizationIds: entry.scope_organizations.map(item => item.id)
    });
    setDrawer("reference-detail");
    void api<LibraryVersion[]>(
      `/api/v1/tenant-management/brand-library/${entry.id}/versions`
    )
      .then(setEntryVersions)
      .catch(error =>
        setNotice({ tone: "error", message: readableRequestError(error) })
      );
  };
  const saveEntryVersion = (event: FormEvent): void => {
    event.preventDefault();
    if (!selectedEntry) return;
    setSaving(true);
    void api(
      `/api/v1/tenant-management/brand-library/${selectedEntry.id}/versions`,
      {
        method: "POST",
        body: JSON.stringify({
          title: form.title,
          source_note: form.sourceNote,
          content: form.content,
          version: form.version,
          visibility_scope: form.visibilityScope,
          organization_ids:
            form.visibilityScope === "brand_all" ? [] : form.organizationIds
        })
      }
    )
      .then(async () => {
        const [updatedEntries, versions] = await Promise.all([
          entries.refresh(),
          api<LibraryVersion[]>(
            `/api/v1/tenant-management/brand-library/${selectedEntry.id}/versions`
          )
        ]);
        void updatedEntries;
        setEntryVersions(versions);
        setSelectedEntry(current =>
          current
            ? {
                ...current,
                title: form.title,
                source_note: form.sourceNote,
                content: form.content,
                version: form.version,
                visibility_scope: form.visibilityScope,
                status: "active"
              }
            : current
        );
        setNotice({ tone: "success", message: "已保存新版本，旧版本仍可回读。" });
      })
      .catch(error =>
        setNotice({ tone: "error", message: readableRequestError(error) })
      )
      .finally(() => setSaving(false));
  };
  const setEntryEnabled = (enabled: boolean): void => {
    if (!selectedEntry) return;
    setSaving(true);
    void api(
      `/api/v1/tenant-management/brand-library/${selectedEntry.id}/enabled`,
      { method: "PUT", body: JSON.stringify({ enabled }) }
    )
      .then(async () => {
        await entries.refresh();
        setSelectedEntry({ ...selectedEntry, status: enabled ? "active" : "retired" });
        setNotice({
          tone: "success",
          message: enabled ? "资料已恢复使用。" : "资料已停用，不会进入新任务。"
        });
      })
      .catch(error =>
        setNotice({ tone: "error", message: readableRequestError(error) })
      )
      .finally(() => setSaving(false));
  };
  const openProduct = (product: ProductFact): void => {
    const facts: NonNullable<ProductFact["facts"]> = product.facts ?? {
      category: product.category,
      colors: product.colors,
      material_or_structure: product.material_or_structure,
      silhouette: product.silhouette,
      observable_features: product.observable_features
    };
    setSelectedProduct(product);
    setProductRows([
      {
        sku: product.sku,
        display_name: product.display_name,
        category: String(facts.category ?? ""),
        colors: Array.isArray(facts.colors) ? facts.colors.join("，") : "",
        material_or_structure: String(facts.material_or_structure ?? ""),
        silhouette: String(facts.silhouette ?? ""),
        observable_features: String(facts.observable_features ?? ""),
        display_family:
          facts.display_family === "upper" || facts.display_family === "lower"
            ? facts.display_family
            : "",
        display_is_long: facts.is_long === true,
        display_accent: facts.accent === true,
        source_note: product.source_note,
        applicability: product.applicability
      }
    ]);
    setProductScope(product.visibility_scope ?? "brand_all");
    setProductOrganizationIds(
      (product.scope_organizations ?? []).map(item => item.id)
    );
    setConfirmProducts(false);
    setProductPreviewSignature(null);
    setDrawer("product-detail");
    void api<ProductVersion[]>(
      `/api/v1/tenant-management/brand-products/${encodeURIComponent(product.sku)}/versions`
    )
      .then(setProductVersions)
      .catch(error =>
        setNotice({ tone: "error", message: readableRequestError(error) })
      );
  };
  const setProductEnabled = (enabled: boolean): void => {
    if (!selectedProduct) return;
    setSaving(true);
    void api(
      `/api/v1/tenant-management/brand-products/${encodeURIComponent(selectedProduct.sku)}/enabled`,
      { method: "PUT", body: JSON.stringify({ enabled }) }
    )
      .then(async () => {
        await products.refresh();
        setSelectedProduct({
          ...selectedProduct,
          status: enabled ? "active" : "retired"
        });
        setNotice({
          tone: "success",
          message: enabled ? "商品事实已恢复使用。" : "商品事实已停用，不会进入新任务。"
        });
      })
      .catch(error =>
        setNotice({ tone: "error", message: readableRequestError(error) })
      )
      .finally(() => setSaving(false));
  };
  const openMaterial = (material: OrganizationMaterial): void => {
    setSelectedMaterial(material);
    setMaterialForm({
      organizationId: "",
      title: material.title,
      note: material.reference_note,
      file: null,
      visibilityScope: material.visibility_scope ?? "brand_all",
      scopeOrganizationIds: (material.scope_organizations ?? []).map(
        item => item.id
      )
    });
    setDrawer("material-detail");
    setBindingProductId("");
    void Promise.all([
      api<MaterialVersion[]>(
        `/api/v1/tenant-management/organization-materials/${material.id}/versions`
      ),
      api<ProductMediaBinding[]>(
        `/api/v1/tenant-management/organization-materials/${material.id}/product-bindings`
      )
    ])
      .then(([versions, bindings]) => {
        setMaterialVersions(versions);
        setMaterialBindings(bindings);
      })
      .catch(error =>
        setNotice({ tone: "error", message: readableRequestError(error) })
      );
  };
  const createProductMediaBinding = (): void => {
    if (!selectedMaterial || !bindingProductId) return;
    setSaving(true);
    void api<ProductMediaBinding>(
      `/api/v1/tenant-management/organization-materials/${selectedMaterial.id}/product-bindings`,
      {
        method: "POST",
        body: JSON.stringify({ product_id: bindingProductId })
      }
    )
      .then(async () => {
        const bindings = await api<ProductMediaBinding[]>(
          `/api/v1/tenant-management/organization-materials/${selectedMaterial.id}/product-bindings`
        );
        setMaterialBindings(bindings);
        setBindingProductId("");
        setNotice({
          tone: "success",
          message: "商品与这份官方素材已经建立明确关联。"
        });
      })
      .catch(error =>
        setNotice({ tone: "error", message: readableRequestError(error) })
      )
      .finally(() => setSaving(false));
  };
  const setProductMediaBindingEnabled = (
    binding: ProductMediaBinding,
    enabled: boolean
  ): void => {
    if (!selectedMaterial) return;
    setSaving(true);
    void api(
      `/api/v1/tenant-management/organization-materials/${selectedMaterial.id}/product-bindings/${binding.id}/enabled`,
      { method: "PUT", body: JSON.stringify({ enabled }) }
    )
      .then(async () => {
        const bindings = await api<ProductMediaBinding[]>(
          `/api/v1/tenant-management/organization-materials/${selectedMaterial.id}/product-bindings`
        );
        setMaterialBindings(bindings);
        setNotice({
          tone: "success",
          message: enabled ? "商品素材关联已恢复。" : "商品素材关联已停用。"
        });
      })
      .catch(error =>
        setNotice({ tone: "error", message: readableRequestError(error) })
      )
      .finally(() => setSaving(false));
  };
  const saveMaterialVersion = (event: FormEvent): void => {
    event.preventDefault();
    if (!selectedMaterial) return;
    setSaving(true);
    void api(
      `/api/v1/tenant-management/organization-materials/${selectedMaterial.id}/versions`,
      {
        method: "POST",
        body: JSON.stringify({
          title: materialForm.title,
          reference_note: materialForm.note,
          visibility_scope: materialForm.visibilityScope,
          organization_ids:
            materialForm.visibilityScope === "brand_all"
              ? []
              : materialForm.scopeOrganizationIds
        })
      }
    )
      .then(async () => {
        const versions = await api<MaterialVersion[]>(
          `/api/v1/tenant-management/organization-materials/${selectedMaterial.id}/versions`
        );
        await materials.refresh();
        setMaterialVersions(versions);
        setNotice({ tone: "success", message: "素材说明与范围已保存为新版本。" });
      })
      .catch(error =>
        setNotice({ tone: "error", message: readableRequestError(error) })
      )
      .finally(() => setSaving(false));
  };
  const setMaterialEnabled = (enabled: boolean): void => {
    if (!selectedMaterial) return;
    setSaving(true);
    void api(
      `/api/v1/tenant-management/organization-materials/${selectedMaterial.id}/enabled`,
      { method: "PUT", body: JSON.stringify({ enabled }) }
    )
      .then(async () => {
        await materials.refresh();
        setSelectedMaterial({
          ...selectedMaterial,
          status: enabled ? "active" : "inactive"
        });
        setNotice({
          tone: "success",
          message: enabled ? "组织素材已恢复使用。" : "组织素材已停用，不会进入新任务。"
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
            setReferencePreview(false);
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
            setProductPreviewSignature(null);
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
                    <span>
                      {entry.version} · {entry.status === "active" ? "使用中" : "已停用"}
                    </span>
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
                  <button
                    type="button"
                    className="text-action"
                    onClick={() => openEntry(entry)}
                  >
                    查看版本与维护
                  </button>
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
                      <span>
                        V{item.fact_version ?? 1} ·{" "}
                        {item.status === "retired" ? "已停用" : "使用中"}
                      </span>
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
                      <button
                        type="button"
                        className="text-action"
                        onClick={() => openProduct(item)}
                      >
                        查看版本与维护
                      </button>
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
                          {item.original_filename} · V{item.reference_version ?? 1} ·{" "}
                          {item.status === "inactive" ? "已停用" : "使用中"}
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
                      <button
                        type="button"
                        className="text-action"
                        onClick={() => openMaterial(item)}
                      >
                        查看版本与维护
                      </button>
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
          <form className="tenant-form" onSubmit={previewReference}>
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
                    setOrganizationForm({
                      name: "",
                      level: "unspecified",
                      parentOrganizationId: ""
                    });
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
              查看导入预览
            </button>
          </form>
        </Drawer>
      )}
      {drawer === "reference-preview" && (
        <Drawer
          title="确认品牌资料"
          onClose={() => setDrawer("reference")}
        >
          <section className="tenant-form library-confirmation">
            <p>以下内容尚未保存。请核对来源、版本和可用范围。</p>
            <dl>
              <div>
                <dt>资料名称</dt>
                <dd>{form.title}</dd>
              </div>
              <div>
                <dt>来源</dt>
                <dd>{form.sourceNote}</dd>
              </div>
              <div>
                <dt>版本</dt>
                <dd>{form.version}</dd>
              </div>
              <div>
                <dt>可用范围</dt>
                <dd>
                  {readableScope(
                    form.visibilityScope,
                    (organizations.data ?? []).filter(item =>
                      form.organizationIds.includes(item.id)
                    )
                  )}
                </dd>
              </div>
            </dl>
            <details>
              <summary>查看文字内容</summary>
              <p className="preserve-lines">{form.content}</p>
            </details>
            <button
              className="primary"
              type="button"
              disabled={saving}
              onClick={confirmReference}
            >
              确认保存为当前版本
            </button>
          </section>
        </Drawer>
      )}
      {drawer === "reference-detail" && selectedEntry && (
        <Drawer
          title="资料版本与使用状态"
          onClose={() => setDrawer(null)}
        >
          <form className="tenant-form" onSubmit={saveEntryVersion}>
            <p>
              当前状态：
              {selectedEntry.status === "active" ? "使用中" : "已停用"}
            </p>
            <label>
              资料名称
              <input
                required
                value={form.title}
                onChange={event => setForm({ ...form, title: event.target.value })}
              />
            </label>
            <label>
              文字内容
              <textarea
                required
                value={form.content}
                onChange={event => setForm({ ...form, content: event.target.value })}
              />
            </label>
            <label>
              来源说明
              <textarea
                required
                value={form.sourceNote}
                onChange={event =>
                  setForm({ ...form, sourceNote: event.target.value })
                }
              />
            </label>
            <label>
              新版本标记
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
                <legend>选择可用组织</legend>
                {organizations.data
                  ?.filter(item =>
                    form.visibilityScope === "headquarters"
                      ? (item.level ?? item.organization_level) === "company"
                      : (item.level ?? item.organization_level) === "region"
                  )
                  .map(item => (
                    <label key={item.id}>
                      <input
                        type={
                          form.visibilityScope === "headquarters"
                            ? "radio"
                            : "checkbox"
                        }
                        checked={form.organizationIds.includes(item.id)}
                        onChange={() => selectScopeOrganization(item.id)}
                      />
                      {item.name}
                    </label>
                  ))}
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
              保存新版本
            </button>
            <button
              type="button"
              className="text-action"
              disabled={saving}
              onClick={() => setEntryEnabled(selectedEntry.status !== "active")}
            >
              {selectedEntry.status === "active" ? "停用资料" : "恢复资料"}
            </button>
            <section className="version-history">
              <h3>历史版本</h3>
              <ol>
                {entryVersions.map(version => (
                  <li key={version.id}>
                    <strong>
                      {version.version}
                      {version.is_current ? " · 当前版本" : ""}
                    </strong>
                    <span>
                      {version.title} · {humanDate(version.created_at)}
                    </span>
                  </li>
                ))}
              </ol>
            </section>
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
            <label>
              上级组织
              <select
                value={organizationForm.parentOrganizationId}
                onChange={event =>
                  setOrganizationForm({
                    ...organizationForm,
                    parentOrganizationId: event.target.value
                  })
                }
              >
                <option value="">没有上级组织</option>
                {organizations.data?.map(item => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </label>
            <p>组织层级由你明确选择；系统不会根据名称猜测。</p>
            <button className="primary" type="submit" disabled={saving}>
              建立组织
            </button>
          </form>
        </Drawer>
      )}
      {(drawer === "product" || drawer === "product-detail") && (
        <Drawer
          title={drawer === "product" ? "维护商品事实" : "商品事实版本与状态"}
          onClose={() => setDrawer(null)}
        >
          <form className="tenant-form" onSubmit={saveProducts}>
            {drawer === "product-detail" && selectedProduct && (
              <>
                <p>
                  当前状态：
                  {selectedProduct.status === "retired" ? "已停用" : "使用中"}
                </p>
                <section className="version-history">
                  <h3>历史版本</h3>
                  <ol>
                    {productVersions.map(version => (
                      <li key={version.id}>
                        <strong>
                          V{version.fact_version}
                          {version.is_current ? " · 当前版本" : ""}
                        </strong>
                        <span>
                          {version.display_name} · {humanDate(version.created_at)}
                        </span>
                      </li>
                    ))}
                  </ol>
                </section>
              </>
            )}
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
                    if (rows.length) {
                      setProductRows(rows);
                      setProductPreviewSignature(null);
                      setConfirmProducts(false);
                    }
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
                      value={productRows[0][key as ProductTextField]}
                      onChange={event =>
                        setProductRows([{ ...productRows[0], [key]: event.target.value }])
                      }
                    />
                  </label>
                ))}
                <label>
                  陈列位置（可选）
                  <select
                    value={productRows[0].display_family}
                    onChange={event =>
                      setProductRows([{
                        ...productRows[0],
                        display_family: event.target.value as ProductDraft["display_family"],
                        display_is_long:
                          event.target.value === "upper" && productRows[0].display_is_long,
                        display_accent:
                          event.target.value === "upper" && productRows[0].display_accent
                      }])
                    }
                  >
                    <option value="">只做库存对账，暂不上墙</option>
                    <option value="upper">上杆</option>
                    <option value="lower">下杆</option>
                  </select>
                </label>
                {productRows[0].display_family === "upper" && (
                  <fieldset>
                    <legend>上杆陈列属性</legend>
                    <label>
                      <input
                        type="checkbox"
                        checked={productRows[0].display_is_long}
                        onChange={event =>
                          setProductRows([{
                            ...productRows[0],
                            display_is_long: event.target.checked
                          }])
                        }
                      />
                      长款，需避免遮挡下杆
                    </label>
                    <label>
                      <input
                        type="checkbox"
                        checked={productRows[0].display_accent}
                        onChange={event =>
                          setProductRows([{
                            ...productRows[0],
                            display_accent: event.target.checked
                          }])
                        }
                      />
                      强调款，默认少量上墙
                    </label>
                  </fieldset>
                )}
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
                      value={productRows[0][key as ProductTextField]}
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
                saving ||
                productRows.some(
                  item =>
                    !item.sku.trim() ||
                    !item.display_name.trim() ||
                    !item.source_note.trim() ||
                    !item.applicability.trim()
                ) ||
                (productPreviewSignature === JSON.stringify(productRows) &&
                  !confirmProducts) ||
                (productScope !== "brand_all" &&
                  productOrganizationIds.length === 0)
              }
            >
              {productPreviewSignature === JSON.stringify(productRows)
                ? drawer === "product-detail"
                  ? "保存新版本"
                  : "保存商品事实"
                : "查看字段预览"}
            </button>
            {drawer === "product-detail" && selectedProduct && (
              <button
                type="button"
                className="text-action"
                disabled={saving}
                onClick={() =>
                  setProductEnabled(selectedProduct.status === "retired")
                }
              >
                {selectedProduct.status === "retired"
                  ? "恢复商品事实"
                  : "停用商品事实"}
              </button>
            )}
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
      {drawer === "material-detail" && selectedMaterial && (
        <Drawer title="组织素材版本与状态" onClose={() => setDrawer(null)}>
          <form className="tenant-form" onSubmit={saveMaterialVersion}>
            <p>
              原件：{selectedMaterial.original_filename} · 当前状态：
              {selectedMaterial.status === "inactive" ? "已停用" : "使用中"}
            </p>
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
              人工说明
              <textarea
                required
                value={materialForm.note}
                onChange={event =>
                  setMaterialForm({ ...materialForm, note: event.target.value })
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
                <legend>选择可用组织</legend>
                {organizations.data
                  ?.filter(item =>
                    materialForm.visibilityScope === "headquarters"
                      ? (item.level ?? item.organization_level) === "company"
                      : (item.level ?? item.organization_level) === "region"
                  )
                  .map(item => (
                    <label key={item.id}>
                      <input
                        type={
                          materialForm.visibilityScope === "headquarters"
                            ? "radio"
                            : "checkbox"
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
            <button
              className="primary"
              type="submit"
              disabled={
                saving ||
                (materialForm.visibilityScope !== "brand_all" &&
                  materialForm.scopeOrganizationIds.length === 0)
              }
            >
              保存新版本
            </button>
            <button
              type="button"
              className="text-action"
              disabled={saving}
              onClick={() =>
                setMaterialEnabled(selectedMaterial.status === "inactive")
              }
            >
              {selectedMaterial.status === "inactive" ? "恢复素材" : "停用素材"}
            </button>
            <section className="version-history" aria-labelledby="product-media-title">
              <h3 id="product-media-title">关联商品</h3>
              <p>
                只有这里明确关联、且创作时再次选择的官方图片或视频，才能用于商品画面。
              </p>
              {materialBindings.length === 0 ? (
                <p>这份素材还没有关联商品。</p>
              ) : (
                <ol>
                  {materialBindings.map(binding => (
                    <li key={binding.id}>
                      <strong>
                        {binding.product_name} · {binding.sku}
                      </strong>
                      <span>
                        商品 V{binding.product_version} ·{" "}
                        {binding.status === "active" ? "使用中" : "已停用"}
                      </span>
                      <button
                        type="button"
                        className="text-action"
                        disabled={saving}
                        onClick={() =>
                          setProductMediaBindingEnabled(
                            binding,
                            binding.status !== "active"
                          )
                        }
                      >
                        {binding.status === "active" ? "停用关联" : "恢复关联"}
                      </button>
                    </li>
                  ))}
                </ol>
              )}
              <label>
                选择已确认商品
                <select
                  value={bindingProductId}
                  onChange={event => setBindingProductId(event.target.value)}
                  disabled={saving || selectedMaterial.status === "inactive"}
                >
                  <option value="">请选择商品</option>
                  {(products.data ?? [])
                    .filter(
                      product =>
                        product.status !== "retired" &&
                        product.current_version_id &&
                        !materialBindings.some(
                          binding => binding.product_id === product.id
                        )
                    )
                    .map(product => (
                      <option key={product.id} value={product.id}>
                        {product.display_name} · {product.sku}
                      </option>
                    ))}
                </select>
              </label>
              <button
                type="button"
                className="text-action"
                disabled={
                  saving ||
                  selectedMaterial.status === "inactive" ||
                  !bindingProductId
                }
                onClick={createProductMediaBinding}
              >
                建立商品关联
              </button>
            </section>
            <section className="version-history">
              <h3>历史版本</h3>
              <ol>
                {materialVersions.map(version => (
                  <li key={version.id}>
                    <strong>
                      V{version.version}
                      {version.is_current ? " · 当前版本" : ""}
                    </strong>
                    <span>
                      {version.title} · {humanDate(version.created_at)}
                    </span>
                  </li>
                ))}
              </ol>
            </section>
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
                {(item.evidence_details ?? []).map(detail => (
                  <div key={`${detail.source}-${detail.version}-${detail.scope}`}>
                    <dt>{detail.source}</dt>
                    <dd>
                      {detail.version} · {detail.scope}
                      {detail.updated_at
                        ? ` · 更新于 ${humanDate(detail.updated_at)}`
                        : detail.updated_at_label
                          ? ` · ${detail.updated_at_label}`
                          : ""}
                    </dd>
                  </div>
                ))}
                <div>
                  <dt>缺少资料</dt>
                  <dd>{item.gaps.join("；") || "没有当前缺口"}</dd>
                </div>
                <div>
                  <dt>明确冲突</dt>
                  <dd>
                    {(item.conflicts ?? []).join("；") || "没有结构化依据表明存在冲突"}
                  </dd>
                </div>
                <div>
                  <dt>影响</dt>
                  <dd>{item.impact}</dd>
                </div>
                <div>
                  <dt>不受影响</dt>
                  <dd>{(item.unaffected ?? []).join("；") || "暂无可单独排除的工作"}</dd>
                </div>
                <div>
                  <dt>判断时间</dt>
                  <dd>
                    {humanDate(item.evaluated_at)}
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
