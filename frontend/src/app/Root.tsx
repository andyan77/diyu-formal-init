import type { JSX } from "react";
import "../styles.css";
import "../styles/product.css";
import AppRouter from "./AppRouter";

/**
 * The application shell.
 *
 * Root used to be the router: it statically imported every business
 * application and matched `window.location.pathname` by hand, so the entry
 * bundle contained the tenant admin console and the ops console no matter
 * which page you opened. Routing now lives in AppRouter behind dynamic
 * imports, and Root's only remaining job is to bring in the stylesheets.
 *
 * Do not import a business application here — that would defeat the split and
 * fail the bundle budget check.
 */
export default function Root(): JSX.Element {
  return <AppRouter />;
}
