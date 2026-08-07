import { Suspense, lazy, useState } from "react";
import type { JSX } from "react";
import { BrandMark } from "../components/Brand";
import type { BootstrapContext } from "./types";

// The capability matrix is the technical diagnostic surface — runtime SHA,
// schema revision, the formal support inventory. It sits inside a collapsed
// disclosure, so there is no reason for /user to download it before someone
// asks for it, and the bundle budget requires that it does not.
const CapabilityGuide = lazy(() => import("../components/CapabilityGuide"));

export function UserHome({ context }: { context: BootstrapContext }): JSX.Element {
  const [helpOpen, setHelpOpen] = useState(false);
  const identity = context.identity ?? {};
  const capabilities = new Set(context.capabilities ?? ["content"]);
  const canCreateContent = capabilities.has("content");
  const canPlanDisplay = capabilities.has("display");
  const canMaintainMaterials = capabilities.has("materials");
  const displayStores = context.display_stores ?? [];
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
        {identity.organization && (
          <p className="user-home-scope">
            所属团队：{identity.organization}
          </p>
        )}
        <div className="user-task-choices">
          {canCreateContent && (
            <a className="button primary" href="/content">
              开始创作
            </a>
          )}
          {canPlanDisplay && displayStores.length <= 1 && (
            <a className={canCreateContent ? "button task-secondary" : "button primary"} href="/display">
              做陈列搭配
            </a>
          )}
          {canMaintainMaterials && (
            <a
              className={canCreateContent || canPlanDisplay ? "button task-secondary" : "button primary"}
              href="/materials"
            >
              维护组织官方素材
            </a>
          )}
        </div>
        {canPlanDisplay && displayStores.length > 1 && (
          <section aria-labelledby="display-store-choice">
            <h2 id="display-store-choice">选择本次陈列门店</h2>
            <div className="user-task-choices">
              {displayStores.map(store => (
                <a
                  key={store.id}
                  className="button task-secondary"
                  href={`/display?store_id=${encodeURIComponent(store.id)}`}
                >
                  {store.name}
                </a>
              ))}
            </div>
          </section>
        )}
        {!canCreateContent && !canPlanDisplay && !canMaintainMaterials && (
          <p className="user-home-recovery">
            当前账号还没有可用的工作入口，请联系品牌管理员调整资格。
          </p>
        )}
        {context.usage_guide && context.capability_matrix && (
          <details
            className="user-help"
            onToggle={event => setHelpOpen(event.currentTarget.open)}
          >
            <summary>使用说明 / 当前可用与待补</summary>
            {helpOpen && (
              <Suspense fallback={<p className="subtle-status">正在打开使用说明……</p>}>
                <CapabilityGuide
                  guide={context.usage_guide}
                  matrix={context.capability_matrix}
                />
              </Suspense>
            )}
          </details>
        )}
      </section>
    </main>
  );
}
