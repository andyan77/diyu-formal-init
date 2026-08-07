export class ApiError extends Error {
  readonly status: number;
  readonly errorCode: string;
  readonly failureStage: string;
  readonly retryable: boolean;
  readonly action: string;
  readonly traceId: string;
  readonly suggestions: string[];

  constructor(
    message: string,
    status: number,
    details?: {
      errorCode?: string;
      failureStage?: string;
      retryable?: boolean;
      action?: string;
      traceId?: string;
      suggestions?: string[];
    }
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.errorCode = details?.errorCode ?? "UNKNOWN_FAILURE";
    this.failureStage = details?.failureStage ?? "unknown";
    this.retryable = details?.retryable ?? status >= 500;
    this.action = details?.action ?? "请保留当前输入后再试。";
    this.traceId = details?.traceId ?? "";
    this.suggestions = details?.suggestions ?? [];
  }
}

export const SESSION_INVALID_EVENT = "diyu:session-invalid";

function signalInvalidSession(status: number, errorCode: string): void {
  if (errorCode !== "AUTH_REQUIRED" && errorCode !== "AUTH_EXPIRED") return;
  window.dispatchEvent(
    new CustomEvent(SESSION_INVALID_EVENT, { detail: { status, errorCode } })
  );
}

type FailurePayload = {
  detail?: unknown;
  error_code?: unknown;
  failure_stage?: unknown;
  retryable?: unknown;
  action?: unknown;
  trace_id?: unknown;
  suggestions?: unknown;
};

function parsedFailure(payload: unknown, status = 0): {
  message: string;
  errorCode: string;
  failureStage: string;
  retryable: boolean;
  action: string;
  traceId: string;
  suggestions: string[];
} {
  const value =
    typeof payload === "object" && payload !== null
      ? (payload as FailurePayload)
      : {};
  return {
    message:
      typeof value.detail === "string"
        ? value.detail
        : "当前操作没有完成，请稍后再试。",
    errorCode:
      typeof value.error_code === "string"
        ? value.error_code
        : "UNKNOWN_FAILURE",
    failureStage:
      typeof value.failure_stage === "string"
        ? value.failure_stage
        : "unknown",
    retryable:
      typeof value.retryable === "boolean" ? value.retryable : status >= 500,
    action:
      typeof value.action === "string"
        ? value.action
        : "请保留当前输入后再试。",
    traceId: typeof value.trace_id === "string" ? value.trace_id : "",
    suggestions: Array.isArray(value.suggestions)
      ? value.suggestions.filter(
          (item): item is string => typeof item === "string"
        )
      : []
  };
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    credentials: "same-origin",
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers
    }
  });
  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => ({}));
    const failure = parsedFailure(payload, response.status);
    signalInvalidSession(response.status, failure.errorCode);
    throw new ApiError(failure.message, response.status, {
      errorCode: failure.errorCode,
      failureStage: failure.failureStage,
      retryable: failure.retryable,
      action: failure.action,
      traceId: failure.traceId,
      suggestions: failure.suggestions
    });
  }
  return response.json() as Promise<T>;
}

/**
 * Decoded NDJSON lines, typed as `unknown` on purpose.
 *
 * Casting each parsed line to a caller-chosen type here would hand the reducer
 * a well-typed lie whenever the wire disagrees; validation belongs to
 * `guardContentStream`, which is the only thing that can actually check.
 */
export async function* streamApi(
  path: string,
  payload: object,
  signal?: AbortSignal
): AsyncGenerator<unknown> {
  const response = await fetch(path, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      Accept: "application/x-ndjson",
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload),
    signal
  });
  if (!response.ok) {
    const failure: unknown = await response.json().catch(() => ({}));
    const parsed = parsedFailure(failure, response.status);
    signalInvalidSession(response.status, parsed.errorCode);
    throw new ApiError(parsed.message, response.status, {
      errorCode: parsed.errorCode,
      failureStage: parsed.failureStage,
      retryable: parsed.retryable,
      action: parsed.action,
      traceId: parsed.traceId,
      suggestions: parsed.suggestions
    });
  }
  if (!response.body) {
    throw new ApiError("这次没有收到完整结果，请保留输入后再试。", 502);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      const lines = buffer.split(/\r?\n/);
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        if (line.trim()) yield JSON.parse(line);
      }
      if (done) break;
    }
    if (buffer.trim()) yield JSON.parse(buffer);
  } finally {
    reader.releaseLock();
  }
}

export function scopedContentPath(
  path: string,
  publishingIdentityId: string,
  target: string
): string {
  const url = new URL(path, "http://diyu.local");
  url.searchParams.set("publishing_identity_id", publishingIdentityId);
  url.searchParams.set("target", target);
  return `${url.pathname}${url.search}`;
}

export function transferredContent(value: {
  body: string;
  ai_generated: boolean;
  aigc_label?: string | null;
  aigc_release_reminder?: string | null;
  translation_notice?: string | null;
}): string {
  const sections = [];
  if (value.translation_notice) {
    sections.push(value.translation_notice);
  }
  sections.push(value.body);
  if (value.ai_generated && value.aigc_label && value.aigc_release_reminder) {
    sections.push(`${value.aigc_label}\n发布提醒：${value.aigc_release_reminder}`);
  }
  return sections.join("\n\n");
}
