import { useEffect, useState } from "react";
import type { JSX } from "react";
import { BrandMark } from "../components/Brand";
import "../styles/ops.css";

type ServiceState = "checking" | "available" | "unavailable";

export default function StatusPage(): JSX.Element {
  const [state, setState] = useState<ServiceState>("checking");

  async function check(): Promise<void> {
    setState("checking");
    try {
      const response = await fetch("/health/ready", { credentials: "same-origin", cache: "no-store" });
      setState(response.ok ? "available" : "unavailable");
    } catch {
      setState("unavailable");
    }
  }

  useEffect(() => {
    void check();
  }, []);

  const copy = {
    checking: ["正在检查服务", "请稍等片刻。"],
    available: ["服务可以使用", "你可以继续进入笛语。"],
    unavailable: ["服务暂时不可用", "请稍后再试；如果持续发生，请联系你的笛语对接人。"]
  } as const;
  const [title, detail] = copy[state];

  return (
    <main className="status-page">
      <a href="/" aria-label="返回笛语首页"><BrandMark /></a>
      <section aria-live="polite">
        <span className={`status-dot ${state}`} aria-hidden="true" />
        <p className="eyebrow">服务状态</p>
        <h1>{title}</h1>
        <p>{detail}</p>
        {state === "unavailable" ? (
          <button className="primary" type="button" onClick={() => void check()}>重新检查</button>
        ) : (
          <a className="status-return" href="/">返回首页</a>
        )}
      </section>
    </main>
  );
}
