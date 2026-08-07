import type { components } from "./gen/openapi";
import type {
  ContentStreamEvent,
  ContentVersion,
  ConversationKind,
  GenerationStage,
  Target
} from "../../app/types";

/**
 * Runtime guard for the `/api/v1/content/stream` NDJSON stream.
 *
 * `streamApi` yields whatever the wire produced, so a truncated, malformed or
 * out-of-order stream would otherwise reach the reducer as a well-typed lie and
 * leave the workspace half-updated. Everything the UI reads is checked here —
 * presence, type, and for the two fields that end up in the address bar,
 * membership of the target enum — and a valid event is *rebuilt* field by field
 * rather than cast, so nothing unvalidated can ride along.
 *
 * Two rules make the refusal safe rather than merely loud:
 *   - a violation raises {@link ContentStreamContractError}, which the caller
 *     shows while keeping the composer contents;
 *   - the terminal event is withheld until the stream closes cleanly, so a
 *     stream that keeps talking after its own ending commits nothing.
 *
 * The stage vocabulary and ordering are the server's, read from
 * `src/brain/content_service.py` (progress("received") through
 * progress("finalizing")). Stages may be skipped — the conversation path never
 * reaches `generating` — but never repeat or go backwards.
 */

/** The completed payload is a real OpenAPI schema, so its type is generated. */
export type ContentVersionPayload =
  components["schemas"]["ContentVersionResponse"];

export const GENERATION_STAGES = [
  "received",
  "compiling_context",
  "generating",
  "validating",
  "finalizing"
] as const;

type StageName = (typeof GENERATION_STAGES)[number];

// Fails typecheck if an ordered runtime tuple and its declared union drift
// apart, so the two never become independent sources of truth.
type Exact<A, B> = [A] extends [B] ? ([B] extends [A] ? true : never) : never;
const _stagesCoverUnion: Exact<StageName, GenerationStage> = true;
void _stagesCoverUnion;

/**
 * Targets that may be written into the URL.
 *
 * `target_key` and `mentioned_target` both reach `switchScope`, which puts them
 * in the query string; an unrecognised string there produces an address that
 * resolves to nothing. The list is the OpenAPI enum for `target_key`.
 */
export const TARGETS = [
  "douyin_video",
  "xiaohongshu_video",
  "xiaohongshu_graphic",
  "wechat_channels_video"
] as const;
const _targetsCoverUnion: Exact<(typeof TARGETS)[number], Target> = true;
void _targetsCoverUnion;

export const CONVERSATION_KINDS = ["chat", "question"] as const;
const _kindsCoverUnion: Exact<(typeof CONVERSATION_KINDS)[number], ConversationKind> =
  true;
void _kindsCoverUnion;

export const TERMINAL_EVENTS = [
  "completed",
  "conversation",
  "target_conflict",
  "failed"
] as const;

type TerminalName = (typeof TERMINAL_EVENTS)[number];

export type StreamViolation =
  | "not_an_object"
  | "missing_event"
  | "unknown_event"
  | "missing_field"
  | "illegal_value"
  | "out_of_order"
  | "after_terminal"
  | "truncated";

export interface StreamRejection {
  ok: false;
  violation: StreamViolation;
  /** Plain-language, already safe to render; never echoes server internals. */
  message: string;
  detail: string;
}

export type StreamCheck =
  | { ok: true; event: ContentStreamEvent }
  | StreamRejection;

const SAFE_MESSAGE =
  "这次的返回内容不完整，已经停在安全状态。你的输入仍然保留，可以直接重试。";

const reject = (violation: StreamViolation, detail: string): StreamRejection => ({
  ok: false,
  violation,
  message: SAFE_MESSAGE,
  detail
});

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const isString = (value: unknown): value is string => typeof value === "string";
const isBoolean = (value: unknown): value is boolean => typeof value === "boolean";
const isVersionNumber = (value: unknown): value is number =>
  typeof value === "number" && Number.isInteger(value) && value >= 1;

/**
 * Carries the first problem found while reading one event.
 *
 * The readers below hand back `undefined` for a field they could not accept,
 * which lets the caller keep destructuring; `probe.failure` holds the reason.
 * Absent-but-required is a `missing_field`; present-but-wrong is an
 * `illegal_value`, so a rejection says which of the two actually happened.
 */
interface Probe {
  what: string;
  failure: StreamRejection | null;
}

const newProbe = (what: string): Probe => ({ what, failure: null });

const fault = (
  probe: Probe,
  field: string,
  violation: StreamViolation,
  why: string
): undefined => {
  probe.failure ??= reject(violation, `${probe.what} ${field} ${why}`);
  return undefined;
};

const absent = (value: unknown): boolean => value === undefined || value === null;

function readText(
  probe: Probe,
  record: Record<string, unknown>,
  field: string,
  required: boolean
): string | undefined {
  const value = record[field];
  if (absent(value)) {
    return required ? fault(probe, field, "missing_field", "缺失") : undefined;
  }
  return isString(value) ? value : fault(probe, field, "illegal_value", "不是字符串");
}

function readVersionNumber(
  probe: Probe,
  record: Record<string, unknown>,
  field: string
): number | undefined {
  const value = record[field];
  if (absent(value)) return fault(probe, field, "missing_field", "缺失");
  return isVersionNumber(value)
    ? value
    : fault(probe, field, "illegal_value", "不是 ≥1 的整数");
}

function readFlag(
  probe: Probe,
  record: Record<string, unknown>,
  field: string,
  required: boolean
): boolean | undefined {
  const value = record[field];
  if (absent(value)) {
    return required ? fault(probe, field, "missing_field", "缺失") : undefined;
  }
  return isBoolean(value) ? value : fault(probe, field, "illegal_value", "不是布尔值");
}

function readCount(
  probe: Probe,
  record: Record<string, unknown>,
  field: string
): number | undefined {
  const value = record[field];
  if (absent(value)) return fault(probe, field, "missing_field", "缺失");
  return typeof value === "number" && Number.isFinite(value)
    ? value
    : fault(probe, field, "illegal_value", "不是数字");
}

function readChoice<T extends string>(
  probe: Probe,
  record: Record<string, unknown>,
  field: string,
  allowed: readonly T[],
  required: boolean
): T | undefined {
  const value = record[field];
  if (absent(value)) {
    return required ? fault(probe, field, "missing_field", "缺失") : undefined;
  }
  const match = (allowed as readonly string[]).find(item => item === value);
  return match === undefined
    ? fault(probe, field, "illegal_value", "不在允许的取值内")
    : (match as T);
}

function readTextList(
  probe: Probe,
  record: Record<string, unknown>,
  field: string
): string[] | undefined {
  const value = record[field];
  if (absent(value)) return undefined;
  return Array.isArray(value) && value.every(isString)
    ? [...value]
    : fault(probe, field, "illegal_value", "不是字符串数组");
}

type ContextBasis = NonNullable<ContentVersion["context_basis"]>;

function readContextBasis(
  probe: Probe,
  record: Record<string, unknown>
): ContextBasis | undefined {
  const value = record.context_basis;
  if (absent(value)) return undefined;
  if (!isRecord(value)) {
    return fault(probe, "context_basis", "illegal_value", "不是对象");
  }
  const nested = newProbe(`${probe.what} context_basis`);
  const account = readText(nested, value, "account", true);
  const platform = readText(nested, value, "platform_and_format", true);
  const categories = readTextList(nested, value, "brand_material_categories");
  const facts = readFlag(nested, value, "has_product_facts", true);
  const count = readCount(nested, value, "selected_material_count");
  const gaps = readTextList(nested, value, "gaps");
  if (nested.failure) {
    probe.failure ??= nested.failure;
    return undefined;
  }
  if (
    account === undefined ||
    platform === undefined ||
    facts === undefined ||
    count === undefined
  ) {
    return fault(probe, "context_basis", "missing_field", "不完整");
  }
  return {
    account,
    platform_and_format: platform,
    brand_material_categories: categories ?? [],
    has_product_facts: facts,
    selected_material_count: count,
    gaps: gaps ?? []
  };
}

/** Required fields are the OpenAPI `ContentVersionResponse` required set. */
function readVersionCore(
  probe: Probe,
  record: Record<string, unknown>
): ContentVersion | undefined {
  const kind = readChoice(probe, record, "kind", ["content"] as const, true);
  const taskId = readText(probe, record, "task_id", true);
  const versionId = readText(probe, record, "version_id", true);
  const version = readVersionNumber(probe, record, "version");
  const outline = readText(probe, record, "outline", true);
  const body = readText(probe, record, "body", true);
  const aiGenerated = readFlag(probe, record, "ai_generated", true);
  if (probe.failure) return undefined;
  if (
    kind === undefined ||
    taskId === undefined ||
    versionId === undefined ||
    version === undefined ||
    outline === undefined ||
    body === undefined ||
    aiGenerated === undefined
  ) {
    return fault(probe, "result", "missing_field", "不完整");
  }
  return {
    kind,
    task_id: taskId,
    version_id: versionId,
    version,
    outline,
    body,
    ai_generated: aiGenerated
  };
}

/**
 * Copy the optional fields the artifact pane reads.
 *
 * `target` and `target_key` are enum-checked because `targetOf` feeds them to
 * `switchScope`, which writes them into the query string.
 */
function readVersionExtras(
  probe: Probe,
  record: Record<string, unknown>,
  version: ContentVersion
): void {
  const label = readText(probe, record, "aigc_label", false);
  if (label !== undefined) version.aigc_label = label;
  const reminder = readText(probe, record, "aigc_release_reminder", false);
  if (reminder !== undefined) version.aigc_release_reminder = reminder;
  const target = readChoice(probe, record, "target", TARGETS, false);
  if (target !== undefined) version.target = target;
  const targetKey = readChoice(probe, record, "target_key", TARGETS, false);
  if (targetKey !== undefined) version.target_key = targetKey;
  const adapted = readText(probe, record, "adapted_from", false);
  if (adapted !== undefined) version.adapted_from = adapted;
  const notice = readText(probe, record, "translation_notice", false);
  if (notice !== undefined) version.translation_notice = notice;
  const created = readText(probe, record, "created_at", false);
  if (created !== undefined) version.created_at = created;
  const direction = readTextList(probe, record, "applied_direction");
  if (direction !== undefined) version.applied_direction = direction;
  const basis = readContextBasis(probe, record);
  if (basis !== undefined) version.context_basis = basis;
}

function readCompleted(record: Record<string, unknown>): StreamCheck {
  const result = record.result;
  if (!isRecord(result)) {
    return reject("missing_field", "completed event without a result object");
  }
  const probe = newProbe("completed result");
  const version = readVersionCore(probe, result);
  if (version !== undefined) readVersionExtras(probe, result, version);
  const conversationId = readText(probe, record, "conversation_id", false);
  if (probe.failure) return probe.failure;
  if (version === undefined) {
    return reject("missing_field", "completed result is incomplete");
  }
  const event: ContentStreamEvent = { event: "completed", result: version };
  if (conversationId !== undefined) event.conversation_id = conversationId;
  return { ok: true, event };
}

function readConversation(record: Record<string, unknown>): StreamCheck {
  const probe = newProbe("conversation");
  const kind = readChoice(probe, record, "kind", CONVERSATION_KINDS, true);
  const message = readText(probe, record, "message", true);
  const offer = readFlag(probe, record, "direct_generation_available", false);
  const conversationId = readText(probe, record, "conversation_id", false);
  if (probe.failure) return probe.failure;
  if (kind === undefined || message === undefined) {
    return reject("missing_field", "conversation event is incomplete");
  }
  const event: ContentStreamEvent = { event: "conversation", kind, message };
  if (offer !== undefined) event.direct_generation_available = offer;
  if (conversationId !== undefined) event.conversation_id = conversationId;
  return { ok: true, event };
}

function readTargetConflict(record: Record<string, unknown>): StreamCheck {
  const probe = newProbe("target_conflict");
  const mentioned = readChoice(probe, record, "mentioned_target", TARGETS, true);
  const label = readText(probe, record, "label", true);
  const message = readText(probe, record, "message", false);
  if (probe.failure) return probe.failure;
  if (mentioned === undefined || label === undefined) {
    return reject("missing_field", "target_conflict event is incomplete");
  }
  const event: ContentStreamEvent = {
    event: "target_conflict",
    mentioned_target: mentioned,
    label
  };
  if (message !== undefined) event.message = message;
  return { ok: true, event };
}

/** The UI needs a readable reason; everything else is optional but typed. */
function readFailed(record: Record<string, unknown>): StreamCheck {
  const probe = newProbe("failed");
  const detail = readText(probe, record, "detail", false);
  const message = readText(probe, record, "message", false);
  const retryable = readFlag(probe, record, "retryable", false);
  const code = readText(probe, record, "error_code", false);
  const stage = readText(probe, record, "failure_stage", false);
  const action = readText(probe, record, "action", false);
  const trace = readText(probe, record, "trace_id", false);
  const suggestions = readTextList(probe, record, "suggestions");
  if (probe.failure) return probe.failure;
  if (detail === undefined && message === undefined) {
    return reject("missing_field", "failed event without a readable reason");
  }
  const event: ContentStreamEvent = { event: "failed" };
  if (detail !== undefined) event.detail = detail;
  if (message !== undefined) event.message = message;
  if (retryable !== undefined) event.retryable = retryable;
  if (code !== undefined) event.error_code = code;
  if (stage !== undefined) event.failure_stage = stage;
  if (action !== undefined) event.action = action;
  if (trace !== undefined) event.trace_id = trace;
  if (suggestions !== undefined) event.suggestions = suggestions;
  return { ok: true, event };
}

const TERMINAL_READERS: Record<
  TerminalName,
  (record: Record<string, unknown>) => StreamCheck
> = {
  completed: readCompleted,
  conversation: readConversation,
  target_conflict: readTargetConflict,
  failed: readFailed
};

const stageIndex = (name: string): number =>
  (GENERATION_STAGES as readonly string[]).indexOf(name);

const isTerminal = (name: string): name is TerminalName =>
  (TERMINAL_EVENTS as readonly string[]).includes(name);

/** Narrowing helper so consumers never cast an event name to a stage. */
export const isStageEvent = (
  event: ContentStreamEvent
): event is { event: GenerationStage } => stageIndex(event.event) >= 0;

export const isTerminalEvent = (event: ContentStreamEvent): boolean =>
  isTerminal(event.event);

export interface ContentStreamGuard {
  /** Validate one decoded NDJSON line against the contract and the sequence. */
  accept(raw: unknown): StreamCheck;
  /** Call once the stream closes; rejects a stream that never terminated. */
  finish(): StreamRejection | null;
}

export function createContentStreamGuard(): ContentStreamGuard {
  let lastStage = -1;
  let terminated = false;
  let sawAnything = false;

  const accept = (raw: unknown): StreamCheck => {
    if (terminated) {
      return reject("after_terminal", "event arrived after the stream ended");
    }
    if (!isRecord(raw)) {
      return reject("not_an_object", "stream line is not a JSON object");
    }
    const name = raw.event;
    if (!isString(name) || name.length === 0) {
      return reject("missing_event", "stream line has no event name");
    }
    const stage = stageIndex(name);
    if (stage >= 0) {
      if (stage <= lastStage) {
        return reject(
          "out_of_order",
          `stage ${name} arrived after ${GENERATION_STAGES[lastStage]}`
        );
      }
      lastStage = stage;
      sawAnything = true;
      return { ok: true, event: { event: GENERATION_STAGES[stage] } };
    }
    if (!isTerminal(name)) {
      return reject("unknown_event", `unknown event ${name}`);
    }
    const checked = TERMINAL_READERS[name](raw);
    if (!checked.ok) return checked;
    terminated = true;
    sawAnything = true;
    return checked;
  };

  const finish = (): StreamRejection | null => {
    if (terminated) return null;
    return reject(
      "truncated",
      sawAnything
        ? "stream ended after progress events but before a result"
        : "stream closed without sending anything"
    );
  };

  return { accept, finish };
}

/**
 * Wrap a raw event stream so consumers only ever see contract-valid events.
 * Throws {@link ContentStreamContractError} on the first violation, which the
 * caller reports without discarding the composer contents.
 */
export class ContentStreamContractError extends Error {
  readonly violation: StreamViolation;
  readonly detail: string;
  /** Always true: a rejected stream must never mutate the workspace. */
  readonly preservesInput = true;

  constructor(rejection: StreamRejection) {
    super(rejection.message);
    this.name = "ContentStreamContractError";
    this.violation = rejection.violation;
    this.detail = rejection.detail;
  }
}

/**
 * Progress stages are forwarded as they arrive; the terminal event is not.
 *
 * Releasing the result the moment it appears would let a stream that carries on
 * afterwards leave the finished artifact on screen next to the failure banner it
 * just earned. Holding it until a clean EOF makes the commit atomic: either the
 * consumer sees the whole stream and then the result, or it sees a rejection and
 * nothing to commit.
 */
export async function* guardContentStream(
  source: AsyncIterable<unknown>
): AsyncGenerator<ContentStreamEvent> {
  const guard = createContentStreamGuard();
  let held: ContentStreamEvent | null = null;
  for await (const raw of source) {
    const checked = guard.accept(raw);
    if (!checked.ok) throw new ContentStreamContractError(checked);
    if (isTerminalEvent(checked.event)) {
      held = checked.event;
      continue;
    }
    yield checked.event;
  }
  const unfinished = guard.finish();
  if (unfinished) throw new ContentStreamContractError(unfinished);
  if (held) yield held;
}
