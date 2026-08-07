import type { FeatureDescriptor } from "../types";

export { advisorDrafts, createAdvisorDraftStore, draftScopeKey, sameDraftScope } from "./advisorDraft";
export type { AdvisorDraftScopeV1, AdvisorDraftStoreV1 } from "./advisorDraft";
export { useAdvisorScope } from "./useAdvisorScope";
export type { AdvisorScopeApi } from "./useAdvisorScope";

/** `/content`. EXE-05 rebuilds the workspace inside these same routes. */
export const feature: FeatureDescriptor = {
  id: "advisor",
  title: "创作参谋",
  owner: "EXE-05",
  status: "delivered",
  routes: ["/content", "/content/tasks/:taskId"]
};
