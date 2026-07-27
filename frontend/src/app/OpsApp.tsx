import { useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent, JSX } from "react";
import { BrandMark } from "../components/Brand";
import { api } from "../services/api";
import type { BootstrapContext } from "./types";
import "../styles/ops.css";

type RuntimeSummary = {
  enabled_tenants?: number;
  registered_tenants?: number;
  content_runs?: number;
  display_runs?: number;
};

/**
 * The tenant endpoint is intentionally only a small operations summary.  The matching
 * server contract must never include tenant content, people, private materials, or credentials.
 */
type OpsTenant = {
  tenant_id: string;
  tenant_name: string;
  enabled: boolean;
};

type UnmetRequest = {
  stable_request_id: string;
  tenant_id?: string;
  request_text: string;
  gap_type: string;
  status: "received" | "classified" | "answered";
  response_text: string;
  created_at?: string;
};

const GAP_TYPES = [
  ["unclassified", "暂不归类"],
  ["knowledge", "资料或知识"],
  ["generation_method", "创作方法"],
  ["media_tool", "媒体或工具"],
  ["product_scope", "商品或经营事实"],
  ["policy_conflict", "边界冲突"],
  ["source_gap", "来源缺口"]
] as const;

function formatDate(value?: string): string {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.valueOf())
    ? ""
    : new Intl.DateTimeFormat("zh-CN", { month: "numeric", day: "numeric" }).format(date);
}

function readableError(error: unknown): string {
  return error instanceof Error ? error.message : "这次没有完成，请稍后再试。";
}

function SummaryCard({ label, value }: { label: string; value: number | undefined }): JSX.Element {
  return (
    <div className="ops-metric">
      <dt>{label}</dt>
      <dd>{value ?? "—"}</dd>
    </div>
  );
}

function TenantProvisioning({
  onCreated,
  resetSignal
}: {
  onCreated: () => void;
  resetSignal: number;
}): JSX.Element {
  const [tenantName, setTenantName] = useState("");
  const [administratorName, setAdministratorName] = useState("");
  const [administratorUsername, setAdministratorUsername] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [activationLink, setActivationLink] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const details = useRef<HTMLDetailsElement>(null);

  useEffect(() => {
    setActivationLink(null);
    setNotice(null);
    if (details.current) details.current.open = false;
  }, [resetSignal]);

  async function submit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setPending(true);
    setNotice(null);
    try {
      const created = await api<{ tenant_id: string; activation_link?: string }>("/api/v1/ops/tenants", {
        method: "POST",
        body: JSON.stringify({
          tenant_name: tenantName.trim(),
          administrator_name: administratorName.trim(),
          administrator_username: administratorUsername.trim()
        })
      });
      setTenantName("");
      setAdministratorName("");
      setAdministratorUsername("");
      setActivationLink(created.activation_link ?? null);
      setNotice(
        created.activation_link
          ? "租户已开通。一次性激活链接只在当前页面暂时显示。"
          : "租户已开通。请按既有安全流程交付首次进入方式。"
      );
      onCreated();
    } catch (error) {
      setNotice(readableError(error));
    } finally {
      setPending(false);
    }
  }

  return (
    <details
      ref={details}
      className="ops-disclosure"
      onToggle={event => {
        if (!event.currentTarget.open) {
          setActivationLink(null);
          setNotice(null);
        }
      }}
    >
      <summary>开通租户</summary>
      <form className="ops-form" onSubmit={submit}>
        <label>
          租户名称
          <input value={tenantName} onChange={event => setTenantName(event.target.value)} maxLength={120} required />
        </label>
        <label>
          首位管理员称呼
          <input value={administratorName} onChange={event => setAdministratorName(event.target.value)} maxLength={80} required />
        </label>
        <label>
          登录用户名
          <input value={administratorUsername} onChange={event => setAdministratorUsername(event.target.value)} minLength={3} maxLength={80} required />
        </label>
        {notice && <p className="ops-notice" role="status">{notice}</p>}
        {activationLink && (
          <section className="ops-activation-link" aria-label="一次性激活链接">
            <p>请通过受保护的渠道交付。关闭这里、刷新或离开页面后，这条链接不会继续显示。</p>
            <div>
              <input readOnly value={activationLink} aria-label="一次性激活链接" />
              <button
                className="ops-outline-button"
                type="button"
                onClick={() => {
                  void navigator.clipboard.writeText(activationLink).then(
                    () => setNotice("已复制一次性激活链接。"),
                    () => setNotice("这次没有复制成功，请使用受保护的方式重新生成。")
                  );
                }}
              >
                复制链接
              </button>
            </div>
          </section>
        )}
        <button className="primary" type="submit" disabled={pending}>
          {pending ? "正在开通……" : "开通租户"}
        </button>
      </form>
    </details>
  );
}

function TenantList({
  tenants,
  onChanged,
  resetSignal
}: {
  tenants: OpsTenant[];
  onChanged: () => void;
  resetSignal: number;
}): JSX.Element {
  const [notice, setNotice] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  async function changeEnabled(tenant: OpsTenant): Promise<void> {
    setBusyId(tenant.tenant_id);
    setNotice(null);
    try {
      await api<{ enabled: boolean }>(
        `/api/v1/ops/tenants/${tenant.tenant_id}/${tenant.enabled ? "disable" : "enable"}`,
        { method: "POST" }
      );
      onChanged();
    } catch (error) {
      setNotice(readableError(error));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section className="ops-section" aria-labelledby="ops-tenants-heading">
      <div className="ops-section-heading">
        <div>
          <p className="eyebrow">租户</p>
          <h2 id="ops-tenants-heading">当前租户</h2>
        </div>
        <TenantProvisioning onCreated={onChanged} resetSignal={resetSignal} />
      </div>
      {notice && <p className="ops-notice" role="status">{notice}</p>}
      {tenants.length === 0 ? (
        <p className="ops-empty">暂时没有可显示的租户摘要。</p>
      ) : (
        <ul className="ops-list">
          {tenants.map(tenant => (
            <li key={tenant.tenant_id}>
              <div>
                <strong>{tenant.tenant_name}</strong>
                <span>{tenant.enabled ? "可使用" : "已停用"}</span>
              </div>
              <button
                className="ops-outline-button"
                type="button"
                disabled={busyId === tenant.tenant_id}
                onClick={() => void changeEnabled(tenant)}
              >
                {busyId === tenant.tenant_id ? "正在更新……" : tenant.enabled ? "停用" : "恢复使用"}
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function FeedbackList({ requests, onChanged }: { requests: UnmetRequest[]; onChanged: () => void }): JSX.Element {
  const [editing, setEditing] = useState<string | null>(null);
  const [gapType, setGapType] = useState("unclassified");
  const [status, setStatus] = useState<UnmetRequest["status"]>("classified");
  const [reply, setReply] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  function begin(item: UnmetRequest): void {
    setEditing(item.stable_request_id);
    setGapType(item.gap_type || "unclassified");
    setStatus(item.status === "answered" ? "answered" : "classified");
    setReply(item.response_text);
    setNotice(null);
  }

  async function save(event: FormEvent<HTMLFormElement>, item: UnmetRequest): Promise<void> {
    event.preventDefault();
    setPending(true);
    setNotice(null);
    try {
      await api<UnmetRequest>(`/api/v1/ops/unmet-capability-requests/${encodeURIComponent(item.stable_request_id)}`, {
        method: "POST",
        body: JSON.stringify({ gap_type: gapType, status, response_text: reply.trim() })
      });
      setEditing(null);
      onChanged();
    } catch (error) {
      setNotice(readableError(error));
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="ops-section" aria-labelledby="ops-feedback-heading">
      <div className="ops-section-heading">
        <div>
          <p className="eyebrow">需求反馈</p>
          <h2 id="ops-feedback-heading">用户还想完成什么</h2>
        </div>
      </div>
      {notice && <p className="ops-notice" role="status">{notice}</p>}
      {requests.length === 0 ? (
        <p className="ops-empty">暂时没有待处理的需求反馈。</p>
      ) : (
        <ul className="ops-feedback-list">
          {requests.map(item => (
            <li key={item.stable_request_id}>
              <div className="ops-feedback-copy">
                <p>{item.request_text}</p>
                <span>{item.status === "answered" ? "已回告" : "待处理"}{formatDate(item.created_at) ? ` · ${formatDate(item.created_at)}` : ""}</span>
              </div>
              {editing === item.stable_request_id ? (
                <form className="ops-feedback-form" onSubmit={event => void save(event, item)}>
                  <label>
                    归类
                    <select value={gapType} onChange={event => setGapType(event.target.value)}>
                      {GAP_TYPES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                    </select>
                  </label>
                  <label>
                    处理结果
                    <select value={status} onChange={event => setStatus(event.target.value as UnmetRequest["status"])}>
                      <option value="classified">已归类</option>
                      <option value="answered">回告用户</option>
                    </select>
                  </label>
                  <label>
                    给用户的回复
                    <textarea value={reply} onChange={event => setReply(event.target.value)} maxLength={1000} required={status === "answered"} />
                  </label>
                  <div className="ops-inline-actions">
                    <button className="ops-outline-button" type="button" onClick={() => setEditing(null)}>取消</button>
                    <button className="ops-outline-button" type="submit" disabled={pending}>
                      {pending ? "正在保存……" : "保存处理结果"}
                    </button>
                  </div>
                </form>
              ) : (
                <button className="ops-outline-button" type="button" onClick={() => begin(item)}>
                  {item.status === "answered" ? "查看处理结果" : "处理反馈"}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export default function OpsApp({ context }: { context: BootstrapContext }): JSX.Element {
  const [summary, setSummary] = useState<RuntimeSummary>(context.runtime_summary ?? {});
  const [tenants, setTenants] = useState<OpsTenant[]>([]);
  const [requests, setRequests] = useState<UnmetRequest[] | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [provisioningResetSignal, setProvisioningResetSignal] = useState(0);

  const pendingCount = useMemo(
    () => requests?.filter(item => item.status !== "answered").length ?? context.pending_requests ?? 0,
    [requests]
  );

  async function refresh(clearProvisioningLink = false): Promise<void> {
    setNotice(null);
    if (clearProvisioningLink) setProvisioningResetSignal(value => value + 1);
    try {
      const [nextSummary, nextTenants, nextRequests] = await Promise.all([
        api<RuntimeSummary>("/api/v1/ops/runtime-summary"),
        api<OpsTenant[]>("/api/v1/ops/tenants"),
        api<UnmetRequest[]>("/api/v1/ops/unmet-capability-requests")
      ]);
      setSummary(nextSummary);
      setTenants(nextTenants);
      setRequests(nextRequests);
    } catch (error) {
      setNotice(readableError(error));
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  return (
    <main className="ops-app">
      <header className="ops-topbar">
        <a href="/ops" aria-label="笛语运维首页"><BrandMark inverse /></a>
        <span>笛语运维</span>
        <form method="post" action="/ops/logout">
          <button className="ops-text-button" type="submit">退出</button>
        </form>
      </header>
      <div className="ops-content">
        <header className="ops-heading">
          <p className="eyebrow">运行概览</p>
          <h1>今天需要处理什么？</h1>
          <button className="ops-text-button" type="button" onClick={() => void refresh(true)}>刷新</button>
        </header>
        {notice && <p className="ops-notice" role="status">{notice}</p>}
        <dl className="ops-metrics" aria-label="当前运行汇总">
          <SummaryCard label="启用租户" value={summary.enabled_tenants} />
          <SummaryCard label="内容任务" value={summary.content_runs} />
          <SummaryCard label="待处理反馈" value={pendingCount} />
        </dl>
        <TenantList
          tenants={tenants}
          onChanged={() => void refresh()}
          resetSignal={provisioningResetSignal}
        />
        <FeedbackList requests={requests ?? []} onChanged={() => void refresh()} />
      </div>
    </main>
  );
}
