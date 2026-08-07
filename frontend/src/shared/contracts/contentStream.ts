import type { components } from "./gen/openapi";
import type { ContentStreamEvent, GenerationStage } from "../../app/types";

/**
 * Runtime guard for the `/api/v1/content/stream` NDJSON stream.
 *
 * `streamApi` casts each parsed line straight to the event type, so a truncated,
 * malformed or out-of-order stream currently reaches the reducer as a
 * well-typed lie and can leave the workspace half-updated. FE-02 requires the
 * opposite: anything that does not match the contract becomes one safe refusal
 * the caller can show while keeping the user's input.
 *
 * The stage vocabulary and ordering below are the server's, read from
 * `src/brain/content_service.py` (progress("received") at 883 through
 * progress("finalizing") at 2097). Stages may be skipped — the conversation
 * path never reaches `generating` — but never repeat or go backwards.
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

// Fails typecheck if the ordered runtime tuple and the declared union drift
// apart, so the two never become independent sources of truth.
type Exact<A, B> = [A] extends [B] ? ([B] extends [A] ? true : never) : never;
const _stagesCoverUnion: Exact<StageName, GenerationStage> = true;
void _stagesCoverUnion;

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

const hasText = (value: unknown): boolean =>
  typeof value === "string" && value.length > 0;

const stageIndex = (name: string): number =>
  (GENERATION_STAGES as readonly string[]).indexOf(name);

const isTerminal = (name: string): name is TerminalName =>
  (TERMINAL_EVENTS as readonly string[]).includes(name);

/** Only the fields the workspace reducer actually reads are required here. */
function checkTerminalShape(
  name: TerminalName,
  record: Record<string, unknown>
): StreamRejection | null {
  if (name === "completed") {
    const result = record.result;
    if (!isRecord(result)) {
      return reject("missing_field", "completed event without a result object");
    }
    for (const field of ["task_id", "version_id", "version", "body"]) {
      if (result[field] === undefined || result[field] === null) {
        return reject("missing_field", `completed result missing ${field}`);
      }
    }
    return null;
  }
  if (name === "conversation") {
    return hasText(record.message)
      ? null
      : reject("missing_field", "conversation event without a message");
  }
  if (name === "target_conflict") {
    return hasText(record.mentioned_target)
      ? null
      : reject("missing_field", "target_conflict without mentioned_target");
  }
  return hasText(record.detail) || hasText(record.message)
    ? null
    : reject("missing_field", "failed event without a readable reason");
}

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
    if (typeof name !== "string" || name.length === 0) {
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
      return { ok: true, event: raw as unknown as ContentStreamEvent };
    }

    if (!isTerminal(name)) {
      return reject("unknown_event", `unknown event ${name}`);
    }
    const shapeFailure = checkTerminalShape(name, raw);
    if (shapeFailure) return shapeFailure;
    terminated = true;
    sawAnything = true;
    return { ok: true, event: raw as unknown as ContentStreamEvent };
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

export async function* guardContentStream(
  source: AsyncIterable<unknown>
): AsyncGenerator<ContentStreamEvent> {
  const guard = createContentStreamGuard();
  for await (const raw of source) {
    const checked = guard.accept(raw);
    if (!checked.ok) throw new ContentStreamContractError(checked);
    yield checked.event;
  }
  const unfinished = guard.finish();
  if (unfinished) throw new ContentStreamContractError(unfinished);
}
