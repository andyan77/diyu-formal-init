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
 * The other half of the contract is that a slow reply for the account you just
 * left must not land in the account you switched to: every scope gets its own
 * AbortController, and `isCurrent` lets a caller drop a response that resolved
 * after the switch.
 */

export const PUBLISHING_IDENTITY_PARAM = "publishing_identity_id";
export const TARGET_PARAM = "target";

export interface AdvisorScopeApi {
  scope: AdvisorDraftScopeV1;
  scopeKey: string;
  publishingIdentityId: string;
  target: string;
  draft: string;
  setDraft: (text: string) => void;
  /** Aborted the moment the scope changes. */
  signal: AbortSignal;
  /** False once the workspace has moved on from `key`. */
  isCurrent: (key: string) => boolean;
  /** In-app scope change; carries `draft` into the destination when given. */
  switchTo: (
    next: { publishingIdentityId?: string; target?: string },
    draft?: string
  ) => void;
}

export interface AdvisorScopeIdentity {
  operator: string;
  tenant: string;
  fallbackPublishingIdentityId: string;
  fallbackTarget: string;
}

export function useAdvisorScope(identity: AdvisorScopeIdentity): AdvisorScopeApi {
  const [searchParams, setSearchParams] = useSearchParams();

  const publishingIdentityId =
    searchParams.get(PUBLISHING_IDENTITY_PARAM) ??
    identity.fallbackPublishingIdentityId;
  const target = searchParams.get(TARGET_PARAM) ?? identity.fallbackTarget;

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

  const [draft, setDraftState] = useState(() => advisorDrafts.read(scope));
  const currentKey = useRef(scopeKey);
  const controller = useRef<AbortController>(new AbortController());

  // On a scope change, abandon the previous scope's requests and show the
  // draft that belongs to the new scope — never the one left on screen.
  useEffect(() => {
    if (currentKey.current === scopeKey) return;
    controller.current.abort();
    controller.current = new AbortController();
    currentKey.current = scopeKey;
    setDraftState(advisorDrafts.read(scope));
  }, [scope, scopeKey]);

  useEffect(() => {
    const inFlight = controller.current;
    return () => inFlight.abort();
  }, []);

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
      const params = new URLSearchParams(searchParams);
      params.set(PUBLISHING_IDENTITY_PARAM, destination.publishingIdentityId);
      params.set(TARGET_PARAM, destination.target);
      setSearchParams(params);
    },
    [scope, searchParams, setSearchParams]
  );

  const isCurrent = useCallback((key: string) => currentKey.current === key, []);

  return {
    scope,
    scopeKey,
    publishingIdentityId,
    target,
    draft,
    setDraft,
    signal: controller.current.signal,
    isCurrent,
    switchTo
  };
}
