import type { JSX } from "react";
import "../styles.css";
import "../styles/product.css";
import CreatorApp from "./CreatorApp";
import DisplayApp from "./DisplayApp";
import { ActivationPage, LoginPage } from "./LoginPage";
import OpsApp from "./OpsApp";
import { UserHome } from "./ProductShells";
import PublicHome from "./PublicHome";
import StatusPage from "./StatusPage";
import TenantAdminApp from "./TenantAdminApp";
import type { BootstrapContext } from "./types";

function bootstrapContext(): BootstrapContext | null | undefined {
  return (window as typeof window & {
    __DIYU_BOOTSTRAP__?: BootstrapContext | null;
  }).__DIYU_BOOTSTRAP__;
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
  if (pathname === "/status") return <StatusPage />;
  if (pathname === "/activate" || pathname.startsWith("/activate/")) {
    return <ActivationPage context={bootstrap} />;
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
    return <TenantAdminApp context={bootstrap} />;
  }
  if (pathname.startsWith("/ops")) return <OpsApp context={bootstrap} />;
  if (pathname.startsWith("/user")) return <UserHome context={bootstrap} />;
  if (pathname.startsWith("/content")) return <CreatorApp context={bootstrap} />;
  if (pathname.startsWith("/display")) return <DisplayApp context={bootstrap} />;
  return <PublicHome />;
}
