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
  const passwordUpdated =
    entry === "tenant-admin" &&
    new URLSearchParams(window.location.search).get("password_updated") === "1";
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
        {passwordUpdated && (
          <p className="auth-notice" role="status">
            密码已更新，请重新登录。
          </p>
        )}
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
              身份验证器 6 位码
              <input
                name="totp_code"
                inputMode="numeric"
                autoComplete="one-time-code"
                minLength={6}
                maxLength={6}
                pattern="[0-9]{6}"
                required
              />
              <span className="auth-inline-help">来自已绑定的身份验证器。</span>
            </label>
          )}
          {entry === "tenant-admin" &&
            new URLSearchParams(window.location.search).get("next") === "demo" && (
              <input type="hidden" name="next" value="demo" />
            )}
          <button className="primary" type="submit">
            登录
          </button>
          {entry === "tenant-admin" && (
            <p className="auth-recovery">
              忘记密码？请联系另一名品牌管理员或笛语运维，获取一次性重设密码链接。
            </p>
          )}
        </form>
      </section>
    </main>
  );
}

export function ActivationPage({
  context
}: {
  context?: BootstrapContext | null;
}): JSX.Element {
  const resetting = context?.activation_purpose === "reset";
  return (
    <main className="auth-page">
      <a className="auth-brand" href="/" aria-label="返回笛语首页">
        <BrandMark />
      </a>
      <section className="auth-panel">
        <p className="eyebrow">{resetting ? "重设密码" : "首次进入"}</p>
        <h1>{resetting ? "重新设置密码" : "设置你的密码"}</h1>
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
            {resetting ? "更新密码" : "完成设置"}
          </button>
        </form>
      </section>
    </main>
  );
}
