import type { JSX } from "react";
import { BrandMark } from "../components/Brand";
import type { BootstrapContext } from "./types";

const TITLES = {
  "tenant-user": "内容创作",
  "tenant-admin": "品牌管理",
  ops: "笛语运维"
} as const;

export function LoginPage({ context }: { context: BootstrapContext }): JSX.Element {
  const entry = context.entry ?? "tenant-user";
  const action =
    entry === "tenant-admin"
      ? "/tenant-admin/login"
      : entry === "ops"
        ? "/ops/login"
        : "/login";
  return (
    <main className="auth-page">
      <a className="auth-brand" href="/" aria-label="返回笛语首页">
        <BrandMark />
      </a>
      <section className="auth-panel">
        <p className="eyebrow">{TITLES[entry]}</p>
        <h1>登录笛语</h1>
        <form method="post" action={action}>
          <label>
            用户名
            <input name="username" autoComplete="username" required />
          </label>
          <label>
            密码
            <input
              type="password"
              name="password"
              autoComplete="current-password"
              required
            />
          </label>
          {entry === "ops" && (
            <label>
              验证码
              <input
                name="totp_code"
                inputMode="numeric"
                autoComplete="one-time-code"
                required
              />
            </label>
          )}
          {entry === "tenant-admin" &&
            new URLSearchParams(window.location.search).get("next") === "demo" && (
              <input type="hidden" name="next" value="demo" />
            )}
          <button className="primary" type="submit">
            登录
          </button>
        </form>
      </section>
    </main>
  );
}

export function ActivationPage(): JSX.Element {
  return (
    <main className="auth-page">
      <a className="auth-brand" href="/" aria-label="返回笛语首页">
        <BrandMark />
      </a>
      <section className="auth-panel">
        <p className="eyebrow">首次进入</p>
        <h1>设置你的密码</h1>
        <p className="field-help">请使用至少 12 个字符，只在这里输入新密码。</p>
        <form method="post" action={window.location.pathname}>
          <label>
            新密码
            <input
              type="password"
              name="password"
              minLength={12}
              autoComplete="new-password"
              required
            />
          </label>
          <button className="primary" type="submit">
            完成设置
          </button>
        </form>
      </section>
    </main>
  );
}
