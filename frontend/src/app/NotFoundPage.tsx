import type { JSX } from "react";
import { BrandMark } from "../components/Brand";

/**
 * Where an unrecognised path lands.
 *
 * The manual router used to fall through to `<PublicHome />`, so a signed-in
 * person who mistyped a URL — or opened a link to a page a later package will
 * deliver — silently got the marketing page and no way to tell that anything
 * had gone wrong. A protected path that does not resolve has to say so.
 */
export default function NotFoundPage({
  reason = "unknown"
}: {
  reason?: "unknown" | "planned";
}): JSX.Element {
  const planned = reason === "planned";
  return (
    <main className="entry-page" aria-live="polite">
      <header className="entry-brand">
        <BrandMark />
      </header>
      <section className="entry-copy">
        <p className="eyebrow">找不到这个页面</p>
        <h1>{planned ? "这个页面还没有开放。" : "这个地址没有对应的页面。"}</h1>
        <p>
          {planned
            ? "这项能力正在建设中，还没有可用的界面。你当前的登录和资料都没有变化。"
            : "地址可能输错了，或者这个页面已经换了位置。你当前的登录和资料都没有变化。"}
        </p>
      </section>
      <section className="entry-choices" aria-label="可选操作">
        <a className="entry-choice" href="/user">
          <span>继续工作</span>
          <strong>返回你的工作台</strong>
          <small>回到今天可以做的事情。</small>
        </a>
        <a className="entry-choice" href="/">
          <span>暂时离开</span>
          <strong>返回笛语首页</strong>
          <small>不会改变任何账号或入口资格。</small>
        </a>
      </section>
    </main>
  );
}
