import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import {
  advisorDrafts,
  draftScopeKey,
  type AdvisorDraftScopeV1
} from "./advisorDraft";

/**
 * Bind the creation workspace to a scope carried in the URL.
 *
 * Account, platform and format used to be fixed by the server bootstrap, and
 * changing any of them called `window.location.assign` — a full reload that
 * threw the page away and rescued the composer text through sessionStorage.
 * Here the scope lives in the query string instead, so switching is a normal
 * in-app navigation, the back button works, and each scope keeps its own draft.
 *
 * Three rules make that safe:
 *
 *   - the URL is normalised against what the bootstrap actually grants, so an
 *     account you cannot use, or a format that account does not publish, never
 *     survives in the address bar next to a workspace showing something else;
 *   - a user-initiated switch is a history push, so Back returns you to the
 *     account you came from. Only a correction replaces, and only for the four
 *     cases below, which are not journeys anyone would want to step back into;
 *   - every scope owns an AbortController. `begin()` hands out an immutable
 *     transaction, and a reply whose transaction is no longer `live()` is
 *     dropped — that is what stops one account's answer landing under another
 *     account's name.
 */

export const PUBLISHING_IDENTITY_PARAM = "publishing_identity_id";
export const TARGET_PARAM = "target";

/** One account, and the formats it is allowed to publish. */
export interface AdvisorScopeGrant {
  id: string;
  targets: readonly string[];
}

export interface AdvisorScopeIdentity {
  /** Stable operator id from the bootstrap projection. */
  operator: string;
  /** Stable tenant id from the bootstrap projection. */
  tenant: string;
  grants: readonly AdvisorScopeGrant[];
  /** The account the server chose, or "" when it named none. */
  bootstrapPublishingIdentityId: string;
  bootstrapTarget: string;
}

/**
 * A captured scope plus the abort signal that belongs to it.
 *
 * Immutable on purpose: the caller takes one at the top of an async path and
 * asks the same object afterwards, so a scope change mid-flight cannot be
 * missed by re-reading a value that has already moved.
 */
export interface AdvisorScopeTransaction {
  readonly scopeKey: string;
  readonly signal: AbortSignal;
  /** False once the workspace moved on, or the request was aborted. */
  live: () => boolean;
}

export interface AdvisorScopeApi {
  scope: AdvisorDraftScopeV1;
  scopeKey: string;
  publishingIdentityId: string;
  target: string;
  /** False when no account is chosen — the "请选择发布账号" state. */
  hasIdentity: boolean;
  draft: string;
  setDraft: (text: string) => void;
  begin: () => AdvisorScopeTransaction;
  isCurrent: (key: string) => boolean;
  /** In-app scope change (history push); carries `draft` into the destination. */
  switchTo: (
    next: { publishingIdentityId?: string; target?: string },
    draft?: string
  ) => void;
}

interface NormalScope {
  publishingIdentityId: string;
  target: string;
  /** True when the URL says something the bootstrap does not support. */
  corrected: boolean;
}

/**
 * Resolve the URL against the bootstrap's grants.
 *
 * The four cases that justify replacing rather than pushing all appear here:
 * a format the account cannot publish, an account that is not granted, a
 * missing parameter whose default the server alone decides, and a value that
 * is simply not one of the allowed strings. None of them is a place the Back
 * button should be able to return to.
 */
export function normalizeAdvisorScope(
  fromUrl: { identity: string | null; target: string | null },
  identity: AdvisorScopeIdentity
): NormalScope {
  const granted = fromUrl.identity
    ? identity.grants.find(grant => grant.id === fromUrl.identity)
    : undefined;
  // An unknown account is dropped, never swapped for someone else's: showing
  // a different account than the URL names is how drafts cross accounts.
  const publishingIdentityId =
    fromUrl.identity === null
      ? identity.bootstrapPublishingIdentityId
      : (granted?.id ?? "");
  const allowed =
    identity.grants.find(grant => grant.id === publishingIdentityId)?.targets ?? [];
  let target = "";
  if (fromUrl.target !== null && allowed.includes(fromUrl.target)) {
    target = fromUrl.target;
  } else if (allowed.includes(identity.bootstrapTarget)) {
    target = identity.bootstrapTarget;
  } else {
    target = allowed[0] ?? "";
  }
  const corrected =
    publishingIdentityId !== (fromUrl.identity ?? "") ||
    target !== (fromUrl.target ?? "");
  return { publishingIdentityId, target, corrected };
}

function writeScopeParams(
  params: URLSearchParams,
  next: { publishingIdentityId: string; target: string }
): URLSearchParams {
  const written = new URLSearchParams(params);
  for (const [key, value] of [
    [PUBLISHING_IDENTITY_PARAM, next.publishingIdentityId],
    [TARGET_PARAM, next.target]
  ] as const) {
    if (value) written.set(key, value);
    else written.delete(key);
  }
  return written;
}

/**
 * Give each scope its own AbortController, and hand out transactions against
 * whichever scope was current when the work started.
 *
 * Kept apart from `useAdvisorScope` because it is the whole of the
 * cross-account safety story: leaving a scope aborts its requests, and a reply
 * still holding an aborted — or simply outdated — transaction is dropped.
 */
function useScopeTransactions(scopeKey: string): {
  begin: () => AdvisorScopeTransaction;
  isCurrent: (key: string) => boolean;
} {
  const latestKey = useRef(scopeKey);
  latestKey.current = scopeKey;
  const pool = useRef(new Map<string, AbortController>());

  // Leaving a scope abandons its requests. Whatever they were about to say is
  // about an account that is no longer on screen.
  useEffect(() => {
    const controllers = pool.current;
    for (const [key, controller] of controllers) {
      if (key === scopeKey) continue;
      controller.abort();
      controllers.delete(key);
    }
  }, [scopeKey]);

  useEffect(() => {
    const controllers = pool.current;
    return () => {
      for (const controller of controllers.values()) controller.abort();
      controllers.clear();
    };
  }, []);

  const isCurrent = useCallback((key: string) => latestKey.current === key, []);

  const begin = useCallback((): AdvisorScopeTransaction => {
    const key = latestKey.current;
    const existing = pool.current.get(key);
    const controller = existing ?? new AbortController();
    if (!existing) pool.current.set(key, controller);
    const { signal } = controller;
    return {
      scopeKey: key,
      signal,
      live: () => !signal.aborted && latestKey.current === key
    };
  }, []);

  return { begin, isCurrent };
}

export function useAdvisorScope(identity: AdvisorScopeIdentity): AdvisorScopeApi {
  const [searchParams, setSearchParams] = useSearchParams();
  const fromUrl = {
    identity: searchParams.get(PUBLISHING_IDENTITY_PARAM),
    target: searchParams.get(TARGET_PARAM)
  };
  const normal = normalizeAdvisorScope(fromUrl, identity);
  const { publishingIdentityId, target } = normal;

  const scope = useMemo<AdvisorDraftScopeV1>(
    () => ({
      operator: identity.operator,
      tenant: identity.tenant,
      publishingIdentityId,
      target
    }),
    [identity.operator, identity.tenant, publishingIdentityId, target]
  );
  const scopeKey = draftScopeKey(scope);

  // Correcting an address the user never typed is not a journey; replace so
  // Back does not walk into the illegal URL we just left.
  useEffect(() => {
    if (!normal.corrected) return;
    setSearchParams(writeScopeParams(searchParams, normal), { replace: true });
  }, [normal, searchParams, setSearchParams]);

  const { begin, isCurrent } = useScopeTransactions(scopeKey);

  // Adjusting state during render rather than in an effect, so the new scope's
  // first paint already shows its own draft instead of the previous account's.
  const [draftScope, setDraftScope] = useState(scopeKey);
  const [draft, setDraftState] = useState(() => advisorDrafts.read(scope));
  if (draftScope !== scopeKey) {
    setDraftScope(scopeKey);
    setDraftState(advisorDrafts.read(scope));
  }

  const setDraft = useCallback(
    (text: string) => {
      advisorDrafts.write(scope, text);
      setDraftState(text);
    },
    [scope]
  );

  const switchTo = useCallback<AdvisorScopeApi["switchTo"]>(
    (next, carried) => {
      const destination: AdvisorDraftScopeV1 = {
        ...scope,
        publishingIdentityId:
          next.publishingIdentityId ?? scope.publishingIdentityId,
        target: next.target ?? scope.target
      };
      if (carried !== undefined) advisorDrafts.write(destination, carried);
      setSearchParams(writeScopeParams(searchParams, destination));
    },
    [scope, searchParams, setSearchParams]
  );

  return {
    scope,
    scopeKey,
    publishingIdentityId,
    target,
    hasIdentity: publishingIdentityId !== "",
    draft,
    setDraft,
    begin,
    isCurrent,
    switchTo
  };
}
