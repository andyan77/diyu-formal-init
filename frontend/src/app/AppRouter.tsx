import { Suspense, lazy, useEffect, useState } from "react";
import type { JSX } from "react";
import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
  useLocation,
  useParams,
  useSearchParams
} from "react-router-dom";

import { BrandMark } from "../components/Brand";
import { PLANNED_ROUTES } from "../features/registry";
import { SESSION_INVALID_EVENT } from "../services/api";
import NotFoundPage from "./NotFoundPage";
import type { BootstrapContext } from "./types";

/**
 * The application's route table.
 *
 * Replaces the hand-written pathname ladder in Root.tsx, which statically
 * imported every business application — so opening the public home page
 * downloaded the tenant admin console, the ops console and the creation
 * workspace. Each application is now behind its own dynamic import, and the
 * bundle budget check reads those split points out of the build manifest.
 *
 * Every business app is lazy. Nothing here may import one at module scope.
 */

const PublicHome = lazy(() => import("./PublicHome"));
const StatusPage = lazy(() => import("./StatusPage"));
const CreatorApp = lazy(() => import("./CreatorApp"));
const DisplayApp = lazy(() => import("./DisplayApp"));
const OpsApp = lazy(() => import("./OpsApp"));
const TenantAdminApp = lazy(() => import("./TenantAdminApp"));
const OrganizationMaterialsApp = lazy(
  () => import("./OrganizationMaterialsApp")
);
const UserHome = lazy(() =>
  import("./ProductShells").then(module => ({ default: module.UserHome }))
);
const LoginPage = lazy(() =>
  import("./LoginPage").then(module => ({ default: module.LoginPage }))
);
const ActivationPage = lazy(() =>
  import("./LoginPage").then(module => ({ default: module.ActivationPage }))
);

function bootstrapContext(): BootstrapContext | null | undefined {
  return (
    window as typeof window & {
      __DIYU_BOOTSTRAP__?: BootstrapContext | null;
    }
  ).__DIYU_BOOTSTRAP__;
}

function LoadingPage(): JSX.Element {
  return (
    <main className="page-loading" aria-live="polite">
      <span />
      <p>正在进入你的工作空间……</p>
    </main>
  );
}

function SessionExpiredPage({ pathname }: { pathname: string }): JSX.Element {
  const loginPath = pathname.startsWith("/tenant-admin")
    ? "/tenant-admin/login"
    : pathname.startsWith("/ops")
      ? "/ops/login"
      : "/login";
  return (
    <main className="access-recovery" aria-live="assertive">
      <BrandMark />
      <h1>当前登录已经失效</h1>
      <p>页面中的旧资料已收起。请重新登录后继续。</p>
      <a className="button primary" href={loginPath}>
        重新登录
      </a>
    </main>
  );
}

function loginContext(
  bootstrap: BootstrapContext | null | undefined,
  pathname: string
): BootstrapContext {
  return (
    bootstrap ??
    ({
      application: "login",
      entry: pathname.startsWith("/tenant-admin")
        ? "tenant-admin"
        : pathname.startsWith("/ops")
          ? "ops"
          : "tenant-user"
    } satisfies BootstrapContext)
  );
}

/** Keep the query string when a legacy path moves to its new home. */
function RedirectPreservingQuery({ to }: { to: string }): JSX.Element {
  const { search } = useLocation();
  return <Navigate to={`${to}${search}`} replace />;
}

/**
 * `/content?task=T&version=V` is the address the server has been handing out
 * since before this package; it now resolves to the task's own route.
 */
function ContentRoute({ context }: { context: BootstrapContext }): JSX.Element {
  const [searchParams] = useSearchParams();
  const task = searchParams.get("task");
  if (task) {
    const rest = new URLSearchParams(searchParams);
    rest.delete("task");
    const query = rest.toString();
    return (
      <Navigate
        to={`/content/tasks/${encodeURIComponent(task)}${query ? `?${query}` : ""}`}
        replace
      />
    );
  }
  return <CreatorApp context={context} />;
}

function ContentTaskRoute({
  context
}: {
  context: BootstrapContext;
}): JSX.Element {
  // The task's own package page belongs to EXE-07. Until then the workspace
  // opens the task itself, so the address is something you can share and
  // return to rather than an id the page ignores.
  const { taskId } = useParams<{ taskId: string }>();
  const [searchParams] = useSearchParams();
  const raw = searchParams.get("version");
  const parsed = raw === null ? null : Number(raw);
  // A version that is not a positive integer is not a version. Falling back to
  // the latest is friendlier than an error page and cannot show the wrong one.
  const version =
    parsed !== null && Number.isInteger(parsed) && parsed >= 1 ? parsed : null;
  return <CreatorApp context={context} taskId={taskId} taskVersion={version} />;
}

function RoutedApp(): JSX.Element {
  const location = useLocation();
  const bootstrap = bootstrapContext();
  const [sessionInvalid, setSessionInvalid] = useState(false);

  useEffect(() => {
    const invalidate = (): void => setSessionInvalid(true);
    window.addEventListener(SESSION_INVALID_EVENT, invalidate);
    return () => window.removeEventListener(SESSION_INVALID_EVENT, invalidate);
  }, []);

  if (sessionInvalid) {
    return <SessionExpiredPage pathname={location.pathname} />;
  }

  const login = <LoginPage context={loginContext(bootstrap, location.pathname)} />;
  const activation = <ActivationPage context={bootstrap} />;

  // A protected route cannot render before the server has said who is asking.
  const guarded = (element: JSX.Element): JSX.Element =>
    bootstrap ? element : <LoadingPage />;

  return (
    <Suspense fallback={<LoadingPage />}>
      <Routes>
        <Route path="/" element={<PublicHome />} />
        <Route path="/status" element={<StatusPage />} />
        <Route path="/activate" element={activation} />
        <Route path="/activate/:activationToken" element={activation} />
        <Route path="/login" element={login} />
        <Route path="/tenant-admin/login" element={login} />
        <Route path="/ops/login" element={login} />

        <Route
          path="/user"
          element={guarded(<UserHome context={bootstrap as BootstrapContext} />)}
        />
        <Route
          path="/materials"
          element={guarded(
            <OrganizationMaterialsApp context={bootstrap as BootstrapContext} />
          )}
        />
        <Route
          path="/organization-materials"
          element={<RedirectPreservingQuery to="/materials" />}
        />
        <Route
          path="/content"
          element={guarded(
            <ContentRoute context={bootstrap as BootstrapContext} />
          )}
        />
        <Route
          path="/content/tasks/:taskId"
          element={guarded(
            <ContentTaskRoute context={bootstrap as BootstrapContext} />
          )}
        />
        <Route
          path="/display"
          element={guarded(
            <DisplayApp context={bootstrap as BootstrapContext} />
          )}
        />
        <Route
          path="/tenant-admin/*"
          element={guarded(
            <TenantAdminApp context={bootstrap as BootstrapContext} />
          )}
        />
        <Route
          path="/ops/*"
          element={guarded(<OpsApp context={bootstrap as BootstrapContext} />)}
        />

        {PLANNED_ROUTES.map(path => (
          <Route key={path} path={path} element={<NotFoundPage reason="planned" />} />
        ))}
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Suspense>
  );
}

export default function AppRouter(): JSX.Element {
  return (
    <BrowserRouter>
      <RoutedApp />
    </BrowserRouter>
  );
}
