import assert from "node:assert/strict";

import {
  CONVERSATION_KINDS,
  ContentStreamContractError,
  GENERATION_STAGES,
  TARGETS,
  createContentStreamGuard,
  guardContentStream
} from "../src/shared/contracts/contentStream";

const completed = {
  event: "completed",
  result: {
    kind: "content",
    task_id: "t1",
    version_id: "v1",
    version: 1,
    outline: "标题",
    body: "正文",
    ai_generated: true
  }
};

const collect = async (lines: unknown[]): Promise<unknown[]> => {
  async function* source(): AsyncGenerator<unknown> {
    for (const line of lines) yield line;
  }
  const seen: unknown[] = [];
  for await (const event of guardContentStream(source())) seen.push(event);
  return seen;
};

const rejects = async (lines: unknown[]): Promise<ContentStreamContractError> => {
  try {
    await collect(lines);
  } catch (reason) {
    assert.ok(reason instanceof ContentStreamContractError);
    return reason;
  }
  throw new Error("expected the guard to reject this stream");
};

// The stage vocabulary is the server's; a silent divergence would make the
// ordering check meaningless.
assert.deepEqual(
  [...GENERATION_STAGES],
  ["received", "compiling_context", "generating", "validating", "finalizing"]
);

// A full, well-ordered generation passes through untouched.
const happy = await collect([
  { event: "received" },
  { event: "compiling_context" },
  { event: "generating" },
  { event: "validating" },
  { event: "finalizing" },
  completed
]);
assert.equal(happy.length, 6);
assert.deepEqual(happy[5], completed);

// Stages may be skipped: the conversation path never reaches `generating`.
const conversation = await collect([
  { event: "received" },
  { event: "compiling_context" },
  { event: "conversation", kind: "chat", message: "先聊聊方向" }
]);
assert.equal(conversation.length, 3);

// A terminal-only stream is legal — the idempotent replay path emits just one.
assert.equal((await collect([completed])).length, 1);

// Out-of-order and repeated stages are rejected rather than reordered.
const backwards = await rejects([
  { event: "generating" },
  { event: "received" }
]);
assert.equal(backwards.violation, "out_of_order");
const repeated = await rejects([
  { event: "received" },
  { event: "received" }
]);
assert.equal(repeated.violation, "out_of_order");

// Unknown events never reach the reducer.
assert.equal((await rejects([{ event: "teleported" }])).violation, "unknown_event");

// Missing required fields are caught per event kind.
assert.equal(
  (await rejects([{ event: "completed" }])).violation,
  "missing_field"
);
assert.equal(
  (await rejects([{ event: "completed", result: { task_id: "t1" } }])).violation,
  "missing_field"
);
assert.equal(
  (await rejects([{ event: "conversation", kind: "chat" }])).violation,
  "missing_field"
);
assert.equal(
  (await rejects([{ event: "failed" }])).violation,
  "missing_field"
);
assert.equal((await rejects([{ nope: 1 }])).violation, "missing_event");
assert.equal((await rejects(["not-an-object"])).violation, "not_an_object");

// Anything after a terminal event is refused instead of overwriting the result.
assert.equal(
  (await rejects([completed, { event: "finalizing" }])).violation,
  "after_terminal"
);

// A stream that stops before a terminal event is a truncation, not a success.
assert.equal(
  (await rejects([{ event: "received" }])).violation,
  "truncated"
);
assert.equal((await rejects([])).violation, "truncated");

// Every rejection carries a plain-language message and the keep-input promise,
// so the caller never has to invent copy or clear the composer.
const rejection = await rejects([{ event: "teleported" }]);
assert.equal(rejection.preservesInput, true);
assert.match(rejection.message, /输入仍然保留/);
assert.doesNotMatch(rejection.message, /teleported/);

// The stateful guard is usable directly for callers that need per-line control.
const guard = createContentStreamGuard();
assert.equal(guard.accept({ event: "received" }).ok, true);
assert.equal(guard.finish()?.violation, "truncated");

// EXE-01R R3 — the guard now checks every field the workspace reads, not just
// that a key is present. Each case below is a shape the old guard waved through.

const completedWith = (result: Record<string, unknown>): unknown => ({
  event: "completed",
  result: { ...completed.result, ...result }
});
const completedWithout = (field: string): unknown => {
  const result: Record<string, unknown> = { ...completed.result };
  delete result[field];
  return { event: "completed", result };
};

// 1. A result without an outline reaches the artifact header as `undefined`.
assert.equal((await rejects([completedWithout("outline")])).violation, "missing_field");

// 2. Without ai_generated the AIGC disclosure silently disappears.
assert.equal(
  (await rejects([completedWithout("ai_generated")])).violation,
  "missing_field"
);

// 3. Enum members, because targetOf feeds these straight into the address bar.
assert.equal(
  (await rejects([completedWith({ target_key: "weibo_post" })])).violation,
  "illegal_value"
);
assert.equal(
  (await rejects([completedWith({ target: "" })])).violation,
  "illegal_value"
);
assert.equal(
  (await rejects([
    { event: "target_conflict", mentioned_target: "weibo_post", label: "微博" }
  ])).violation,
  "illegal_value"
);
assert.equal(
  (await rejects([{ event: "conversation", kind: "greeting", message: "你好" }]))
    .violation,
  "illegal_value"
);

// 4. Types, not just presence: a string version or a numeric body would render.
assert.equal(
  (await rejects([completedWith({ version: "one" })])).violation,
  "illegal_value"
);
assert.equal(
  (await rejects([completedWith({ body: 123 })])).violation,
  "illegal_value"
);
assert.equal(
  (await rejects([completedWith({ version: 0 })])).violation,
  "illegal_value"
);
assert.equal(
  (await rejects([completedWith({ ai_generated: "true" })])).violation,
  "illegal_value"
);
assert.equal(
  (await rejects([completedWith({ kind: "display" })])).violation,
  "illegal_value"
);
assert.equal(
  (await rejects([{ event: "failed", detail: "坏了", retryable: "yes" }])).violation,
  "illegal_value"
);

// context_basis is optional, but a present one is read field by field.
assert.equal(
  (await rejects([completedWith({ context_basis: { account: "总部" } })])).violation,
  "missing_field"
);
assert.equal(
  (await rejects([
    completedWith({ context_basis: { ...completed.result, account: 1 } })
  ])).violation,
  "illegal_value"
);

// 5. The terminal event is withheld until the stream closes cleanly, so an
// after-terminal violation leaves the consumer with nothing to commit.
const held = await collect([{ event: "received" }, completed]);
assert.deepEqual(held[0], { event: "received" });
assert.deepEqual(held[1], completed);
const late = await (async () => {
  const seen: unknown[] = [];
  async function* source(): AsyncGenerator<unknown> {
    yield { event: "received" };
    yield completed;
    yield { event: "finalizing" };
  }
  try {
    for await (const event of guardContentStream(source())) seen.push(event);
  } catch (reason) {
    assert.ok(reason instanceof ContentStreamContractError);
    return seen;
  }
  throw new Error("expected the guard to reject this stream");
})();
assert.deepEqual(
  late,
  [{ event: "received" }],
  "违约前不得把 completed 交给消费方"
);

// Validated events are rebuilt, so an unvalidated key cannot ride along.
const rebuilt = await collect([completedWith({ smuggled: "payload" })]);
assert.deepEqual(rebuilt, [completed]);

// The enums stay the declared truth source rather than drifting into prose.
assert.deepEqual(
  [...TARGETS],
  ["douyin_video", "xiaohongshu_video", "xiaohongshu_graphic", "wechat_channels_video"]
);
assert.deepEqual([...CONVERSATION_KINDS], ["chat", "question"]);

console.log("content stream contract guard checks passed");
