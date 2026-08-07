import { feature as adminBrandFeedback } from "./admin-brand-feedback";
import { feature as advisor } from "./advisor";
import { feature as brandBasis } from "./brand-basis";
import { feature as decisions } from "./decisions";
import { feature as production } from "./production";
import { feature as proposal } from "./proposal";
import { feature as today } from "./today";
import type { FeatureDescriptor } from "./types";

export type { FeatureDescriptor, FeatureStatus } from "./types";

export const FEATURES: readonly FeatureDescriptor[] = [
  today,
  advisor,
  proposal,
  production,
  brandBasis,
  decisions,
  adminBrandFeedback
];

/**
 * Routes a feature has claimed but not built yet.
 *
 * The router sends these to the recovery page rather than the public home, so
 * a planned URL reads as "not here yet" instead of silently dumping a signed-in
 * person on the marketing page.
 */
export const PLANNED_ROUTES: readonly string[] = FEATURES.filter(
  entry => entry.status === "planned"
).flatMap(entry => entry.routes);

export function featureOwning(route: string): FeatureDescriptor | undefined {
  return FEATURES.find(entry => entry.routes.includes(route));
}
