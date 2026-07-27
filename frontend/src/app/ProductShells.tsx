import type { JSX } from "react";
import { BrandMark } from "../components/Brand";
import type { BootstrapContext } from "./types";

export function UserHome({ context }: { context: BootstrapContext }): JSX.Element {
  const identity = context.identity ?? {};
  const capabilities = new Set(context.capabilities ?? ["content"]);
  const canCreateContent = capabilities.has("content");
  const canPlanDisplay = capabilities.has("display");
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
        <h1>{identity.operator ? `${identity.operator}，` : ""}今天想完成什么？</h1>
        <div className="user-task-choices">
          {canCreateContent && (
            <a className="button primary" href="/content">
              开始创作
            </a>
          )}
          {canPlanDisplay && (
            <a className={canCreateContent ? "button task-secondary" : "button primary"} href="/display">
              做陈列搭配
            </a>
          )}
        </div>
        {!canCreateContent && !canPlanDisplay && (
          <p className="user-home-recovery">
            当前账号还没有可用的工作入口，请联系品牌管理员调整资格。
          </p>
        )}
      </section>
    </main>
  );
}
