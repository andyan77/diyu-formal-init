import assert from "node:assert/strict";
import { closeSync, mkdirSync, mkdtempSync, openSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { resolveChromePath } from "./chrome-path.mjs";

const root = mkdtempSync(join(tmpdir(), "diyu-chrome-path-"));
try {
  const cached = join(root, "151.0.7922.71", "chrome-linux64", "chrome");
  mkdirSync(join(root, "151.0.7922.71", "chrome-linux64"), {
    recursive: true
  });
  closeSync(openSync(cached, "w"));
  assert.equal(resolveChromePath({ cacheRoot: root }), cached);

  const configured = join(root, "configured-chrome");
  closeSync(openSync(configured, "w"));
  assert.equal(resolveChromePath({ configured, cacheRoot: root }), configured);
} finally {
  rmSync(root, { recursive: true, force: true });
}
