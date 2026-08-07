// Bundle one TypeScript test file with esbuild and run it under Node.
//
//   node test/run-ts.mjs test/contract_stream.test.ts
//
// The DOM suites each need their own jsdom and fetch stub, so they keep their
// bespoke runners. Tests of plain modules need none of that, and they should
// not each carry a copy of this boilerplate.

import { build } from "esbuild";
import { rm } from "node:fs/promises";
import { basename } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const entry = process.argv[2];
if (!entry) throw new Error("用法：node test/run-ts.mjs <测试文件>");

const name = basename(entry).replace(/\.[^.]+$/, "");
const workdir = fileURLToPath(
  new URL(`../node_modules/.diyu-${name}/`, import.meta.url)
);
const outfile = `${workdir}${name}.mjs`;

try {
  await build({
    entryPoints: [entry],
    outfile,
    bundle: true,
    platform: "node",
    format: "esm",
    target: "node20",
    logLevel: "warning"
  });
  await import(pathToFileURL(outfile).href);
} finally {
  await rm(workdir, { recursive: true, force: true });
}
