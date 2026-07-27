import type { JSX } from "react";
import "../styles.css";
import "../styles/product.css";
import CreatorApp from "./CreatorApp";
import { ActivationPage, LoginPage } from "./LoginPage";
import { OpsShell, TenantAdminShell, UserHome } from "./ProductShells";
import PublicHome from "./PublicHome";
import type { BootstrapContext } from "./types";

function bootstrapContext(): BootstrapContext | null | undefined {
  return window.__DIYU_BOOTSTRAP__ as BootstrapContext | null | undefined;
}

function LoadingPage(): JSX.Element {
  return (
    <main className="page-loading" aria-live="polite">
      <span />
      <p>正在进入你的工作空间……</p>
    </main>
  );
}

export default function Root(): JSX.Element {
  const pathname = window.location.pathname;
  const bootstrap = bootstrapContext();

  if (pathname === "/") return <PublicHome />;
  if (pathname === "/activate" || pathname.startsWith("/activate/")) {
    return <ActivationPage />;
  }
  if (
    pathname === "/login" ||
    pathname === "/tenant-admin/login" ||
    pathname === "/ops/login"
  ) {
    const context: BootstrapContext =
      bootstrap ??
      ({
        application: "login",
        entry: pathname.startsWith("/tenant-admin")
          ? "tenant-admin"
          : pathname.startsWith("/ops")
            ? "ops"
            : "tenant-user"
      } satisfies BootstrapContext);
    return <LoginPage context={context} />;
  }
  if (!bootstrap) return <LoadingPage />;
  if (pathname.startsWith("/tenant-admin")) {
    return <TenantAdminShell context={bootstrap} />;
  }
  if (pathname.startsWith("/ops")) return <OpsShell context={bootstrap} />;
  if (pathname.startsWith("/user")) return <UserHome context={bootstrap} />;
  if (pathname.startsWith("/content")) return <CreatorApp context={bootstrap} />;
  return <PublicHome />;
}
