/**
 * What a feature directory declares about itself.
 *
 * EXE-01 opens seven feature directories but only two of them have a page
 * today; the rest are delivered by later packages. Rather than leave that
 * knowledge in a comment, each directory states it, and the router reads it.
 * That is what keeps UX-04R's rule enforceable — a route that is planned but
 * not built must not appear in navigation and must not quietly render the
 * public home page when someone types its URL.
 */

export type FeatureStatus = "delivered" | "planned";

export interface FeatureDescriptor {
  /** Directory name under src/features. */
  readonly id: string;
  /** Plain-language name; interface copy never uses internal contract names. */
  readonly title: string;
  /** Execution package that delivers this surface. */
  readonly owner: string;
  readonly status: FeatureStatus;
  /** Route patterns this feature owns. Empty when it contributes a panel. */
  readonly routes: readonly string[];
  /** Why it is not built yet; required for planned features. */
  readonly note?: string;
}
