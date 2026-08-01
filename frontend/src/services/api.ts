export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export const SESSION_INVALID_EVENT = "diyu:session-invalid";

function signalInvalidSession(status: number): void {
  if (status !== 401 && status !== 403) return;
  window.dispatchEvent(
    new CustomEvent(SESSION_INVALID_EVENT, { detail: { status } })
  );
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
    signalInvalidSession(response.status);
    const payload: unknown = await response.json().catch(() => ({}));
    const detail =
      typeof payload === "object" && payload !== null && "detail" in payload
        ? String(payload.detail)
        : "当前操作没有完成，请稍后再试。";
    throw new ApiError(detail, response.status);
  }
  return response.json() as Promise<T>;
}

export async function* streamApi<T>(
  path: string,
  payload: object,
  signal?: AbortSignal
): AsyncGenerator<T> {
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
    signalInvalidSession(response.status);
    const failure: unknown = await response.json().catch(() => ({}));
    const detail =
      typeof failure === "object" && failure !== null && "detail" in failure
        ? String(failure.detail)
        : "当前操作没有完成，请稍后再试。";
    throw new ApiError(detail, response.status);
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
        if (line.trim()) yield JSON.parse(line) as T;
      }
      if (done) break;
    }
    if (buffer.trim()) yield JSON.parse(buffer) as T;
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
