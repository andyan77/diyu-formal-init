import { useRef, useState } from "react";
import type { FormEvent, JSX } from "react";
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
  const [password, setPassword] = useState("");
  const [passwordConfirmation, setPasswordConfirmation] = useState("");
  const [error, setError] = useState(context?.activation_error ?? "");
  const passwordInput = useRef<HTMLInputElement>(null);
  const confirmationInput = useRef<HTMLInputElement>(null);

  const validatePasswords = (event: FormEvent<HTMLFormElement>): void => {
    setError("");
    if (password.length < 12) {
      event.preventDefault();
      setError("新密码至少需要 12 个字符。");
      passwordInput.current?.focus();
      return;
    }
    if (passwordConfirmation.length < 12) {
      event.preventDefault();
      setError("请再次输入至少 12 个字符的新密码。");
      confirmationInput.current?.focus();
      return;
    }
    if (password !== passwordConfirmation) {
      event.preventDefault();
      setError("两次输入的密码不一致，请重新确认。");
      confirmationInput.current?.focus();
    }
  };

  return (
    <main className="auth-page">
      <a className="auth-brand" href="/" aria-label="返回笛语首页">
        <BrandMark />
      </a>
      <section className="auth-panel">
        <p className="eyebrow">{resetting ? "重设密码" : "首次进入"}</p>
        <h1>{resetting ? "重新设置密码" : "设置你的密码"}</h1>
        <p className="field-help">请使用至少 12 个字符，只在这里输入新密码。</p>
        {error && (
          <p className="auth-error" id="activation-password-error" role="alert">
            {error}
          </p>
        )}
        <form method="post" action={window.location.pathname} onSubmit={validatePasswords}>
          <label>
            新密码
            <input
              ref={passwordInput}
              type="password"
              name="password"
              minLength={12}
              autoComplete="new-password"
              value={password}
              aria-invalid={Boolean(error)}
              aria-describedby={error ? "activation-password-error" : undefined}
              onChange={event => setPassword(event.target.value)}
              required
            />
          </label>
          <label>
            再次输入新密码
            <input
              ref={confirmationInput}
              type="password"
              name="password_confirm"
              minLength={12}
              autoComplete="new-password"
              value={passwordConfirmation}
              aria-invalid={Boolean(error)}
              aria-describedby={error ? "activation-password-error" : undefined}
              onChange={event => setPasswordConfirmation(event.target.value)}
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
