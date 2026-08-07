import assert from "node:assert/strict";

import {
  ContentStreamContractError,
  GENERATION_STAGES,
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

console.log("content stream contract guard checks passed");
