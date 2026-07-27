import type { JSX } from "react";
import { BrandMark } from "../components/Brand";
import type { BootstrapContext } from "./types";

export function UserHome({ context }: { context: BootstrapContext }): JSX.Element {
  const identity = context.identity ?? {};
  return (
    <main className="user-home">
      <header>
        <BrandMark />
        <form method="post" action="/tenant-admin/logout?next=user">
          <button className="quiet" type="submit">
            退出
          </button>
        </form>
      </header>
      <section>
        <p className="eyebrow">{identity.account ?? identity.organization ?? "你的工作空间"}</p>
        <h1>{identity.operator ? `${identity.operator}，` : ""}今天想说什么？</h1>
        <a className="button primary" href="/content">
          开始创作
        </a>
      </section>
    </main>
  );
}

export function TenantAdminShell({
  context
}: {
  context: BootstrapContext;
}): JSX.Element {
  const identity = context.identity ?? {};
  return (
    <div className="control-space tenant-space">
      <aside>
        <BrandMark />
        <p className="space-name">品牌管理</p>
        <nav aria-label="品牌管理导航">
          <a aria-current="page" href="/tenant-admin">
            概览与待处理
          </a>
          <span>成员与权限</span>
          <span>发布账号</span>
          <span>品牌、商品与组织素材</span>
          <span>生产就绪与缺口</span>
        </nav>
      </aside>
      <main>
        <header className="control-topbar">
          <span>{identity.brand ?? "当前品牌"}</span>
          <form method="post" action="/tenant-admin/logout">
            <button className="quiet" type="submit">
              退出
            </button>
          </form>
        </header>
        <section className="control-overview">
          <p className="eyebrow">品牌管理</p>
          <h1>品牌与创作资料</h1>
          <p>在这里维护品牌、发布账号与创作资料。</p>
        </section>
      </main>
    </div>
  );
}

export function OpsShell({ context }: { context: BootstrapContext }): JSX.Element {
  const summary = context.runtime_summary ?? {};
  return (
    <div className="control-space ops-space">
      <aside>
        <BrandMark inverse />
        <p className="space-name">笛语运维</p>
        <nav aria-label="笛语运维导航">
          <a aria-current="page" href="/ops">
            运行概览
          </a>
          <span>租户</span>
          <span>需求反馈</span>
        </nav>
      </aside>
      <main>
        <header className="control-topbar">
          <span>平台运行</span>
        </header>
        <section className="ops-overview">
          <p className="eyebrow">运行概览</p>
          <h1>当前运行汇总</h1>
          <dl>
            <div>
              <dt>启用租户</dt>
              <dd>{summary.enabled_tenants ?? "—"}</dd>
            </div>
            <div>
              <dt>内容生成</dt>
              <dd>{summary.content_runs ?? "—"}</dd>
            </div>
            <div>
              <dt>待处理反馈</dt>
              <dd>{context.pending_requests ?? 0}</dd>
            </div>
          </dl>
        </section>
      </main>
    </div>
  );
}
