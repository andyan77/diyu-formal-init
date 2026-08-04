import { useEffect, useState } from "react";
import type { JSX } from "react";
import { BrandMark } from "../components/Brand";
import { api } from "../services/api";
import "../styles/ops.css";

type PublicState = "available" | "degraded" | "unavailable" | "unknown";

type PublicStatus = {
  contract_version: "public-service-status-v1";
  checked_at: string;
  provider_freshness_seconds: number;
  core: { state: "available" | "unavailable" };
  content_generation: {
    state: PublicState;
    observed_at: string | null;
    fresh_until: string | null;
  };
  text_display: { state: "available" | "unavailable" };
};

const labels: Record<PublicState, string> = {
  available: "可以使用",
  degraded: "暂时受影响",
  unavailable: "暂时不可用",
  unknown: "近期状态尚无法确认"
};

export default function StatusPage(): JSX.Element {
  const [status, setStatus] = useState<PublicStatus | null>(null);
  const [error, setError] = useState(false);

  async function check(): Promise<void> {
    setError(false);
    try {
      setStatus(await api<PublicStatus>("/api/v1/status", { cache: "no-store" }));
    } catch {
      setStatus(null);
      setError(true);
    }
  }

  useEffect(() => {
    void check();
  }, []);

  const coreAvailable = status?.core.state === "available";
  const pendingLabel = error ? "当前状态暂无法确认" : "正在检查";
  const headline = error
    ? "当前状态暂无法确认，请稍后重新检查。"
    : status?.core.state === "unavailable"
      ? "笛语暂时无法接单，请稍后再试。"
      : status?.content_generation.state === "degraded" ||
        status?.content_generation.state === "unavailable"
      ? "内容生成暂时受影响；品牌管理和纯文字陈列参考方案仍可使用。"
      : status?.content_generation.state === "unknown"
        ? "主要功能可以使用；内容生成近期状态尚无法确认。"
        : status
          ? "主要功能可以使用。"
          : "正在检查服务。";

  return (
    <main className="status-page">
      <a href="/" aria-label="返回笛语首页"><BrandMark /></a>
      <section aria-live="polite">
        <p className="eyebrow">服务状态</p>
        <h1>{headline}</h1>
        <dl className="status-services">
          <div>
            <dt>核心服务</dt>
            <dd>{status ? labels[status.core.state] : pendingLabel}</dd>
          </div>
          <div>
            <dt>内容生成</dt>
            <dd>{status ? labels[status.content_generation.state] : pendingLabel}</dd>
          </div>
          <div>
            <dt>纯文字陈列参考方案</dt>
            <dd>{status ? labels[status.text_display.state] : pendingLabel}</dd>
          </div>
        </dl>
        {status && (
          <>
            <p className="status-checked-at">
              本页检查于 {new Date(status.checked_at).toLocaleString("zh-CN")}；页面检查不会发起内容生成。
              {status.content_generation.observed_at
                ? ` 最近一次模型服务观察为 ${new Date(status.content_generation.observed_at).toLocaleString("zh-CN")}，有效至 ${new Date(status.content_generation.fresh_until ?? status.content_generation.observed_at).toLocaleString("zh-CN")}。`
                : " 当前进程还没有新鲜的模型服务观察。"}
            </p>
            <details className="status-meanings">
              <summary>这些状态分别是什么意思</summary>
              <dl>
                <div><dt>近期状态尚无法确认</dt><dd>没有足够新鲜的模型调用观察；不等于服务已经停机。</dd></div>
                <div><dt>暂时受影响</dt><dd>最近观察到限流或部分可恢复异常；核心管理能力仍可使用。</dd></div>
                <div><dt>暂时不可用</dt><dd>核心依赖失败，或新鲜观察显示模型服务不可用。</dd></div>
              </dl>
            </details>
          </>
        )}
        <button className="primary" type="button" onClick={() => void check()}>
          重新检查
        </button>
        {coreAvailable && <a className="status-return" href="/">返回首页</a>}
      </section>
    </main>
  );
}
