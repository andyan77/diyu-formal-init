import assert from "node:assert/strict";

import {
  createAdvisorDraftStore,
  draftScopeKey,
  sameDraftScope,
  type AdvisorDraftScopeV1
} from "../src/features/advisor/advisorDraft";

/**
 * The AdvisorDraftV1 contract, asserted clause by clause.
 *
 * The bug this replaces was specific: the retired sessionStorage key was
 * `operator:brand:publishingIdentity` with no target, so changing platform
 * carried the text across, and changing account restored the previous
 * account's words on the next page load. Each clause below pins one of those
 * failures shut.
 */

const base: AdvisorDraftScopeV1 = {
  operator: "user-hq",
  tenant: "笛语服饰",
  publishingIdentityId: "identity-hq",
  target: "xiaohongshu_graphic"
};
const otherAccount: AdvisorDraftScopeV1 = {
  ...base,
  publishingIdentityId: "identity-store"
};
const otherTarget: AdvisorDraftScopeV1 = { ...base, target: "douyin_video" };
const otherOperator: AdvisorDraftScopeV1 = { ...base, operator: "user-store" };
const otherTenant: AdvisorDraftScopeV1 = { ...base, tenant: "另一个品牌" };

// The scope is all four fields — dropping any one is how drafts leaked.
for (const variant of [otherAccount, otherTarget, otherOperator, otherTenant]) {
  assert.notEqual(draftScopeKey(base), draftScopeKey(variant));
  assert.equal(sameDraftScope(base, variant), false);
}
assert.equal(sameDraftScope(base, { ...base }), true);
assert.equal(draftScopeKey(base), draftScopeKey({ ...base }));

const store = createAdvisorDraftStore();

// A draft is readable in the scope that wrote it.
store.write(base, "今天店里忙了一天。");
assert.equal(store.read(base), "今天店里忙了一天。");

// Switching account must not show the previous account's text.
assert.equal(store.read(otherAccount), "");
// Nor must switching platform or format.
assert.equal(store.read(otherTarget), "");

// Each scope keeps its own, and switching back restores what was left there.
store.write(otherAccount, "门店号今天的说法不一样。");
assert.equal(store.read(base), "今天店里忙了一天。");
assert.equal(store.read(otherAccount), "门店号今天的说法不一样。");
assert.equal(store.size(), 2);

// Emptying the composer discards the draft rather than storing "".
store.write(base, "");
assert.equal(store.read(base), "");
assert.equal(store.size(), 1);
assert.equal(store.read(otherAccount), "门店号今天的说法不一样。");

store.clear(otherAccount);
assert.equal(store.size(), 0);
assert.equal(store.read(otherAccount), "");

// Stores are independent; nothing is shared through module state by accident.
const second = createAdvisorDraftStore();
store.write(base, "第一份");
assert.equal(second.read(base), "");

// The contract does not promise refresh survival, and must not quietly grow
// one: no storage API may appear behind the store.
assert.equal(typeof (globalThis as { sessionStorage?: unknown }).sessionStorage, "undefined");

console.log("AdvisorDraftV1 contract checks passed");
