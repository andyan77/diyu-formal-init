export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
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
    const detail =
      typeof payload === "object" && payload !== null && "detail" in payload
        ? String(payload.detail)
        : "当前操作没有完成，请稍后再试。";
    throw new ApiError(detail, response.status);
  }
  return response.json() as Promise<T>;
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
