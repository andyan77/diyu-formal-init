// Bundle and run the content-stream contract checks.
//
// The guard is plain TypeScript with no DOM dependency, so unlike the other
// suites this runner needs no jsdom or fetch stub — only the same esbuild step
// the repository already uses to execute TypeScript tests under Node.

import { build } from "esbuild";
import { rm } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const workdir = fileURLToPath(
  new URL("../node_modules/.diyu-contract-stream/", import.meta.url)
);
const outfile = `${workdir}contract-stream.mjs`;

try {
  await build({
    entryPoints: [
      fileURLToPath(new URL("./contract_stream.test.ts", import.meta.url))
    ],
    outfile,
    bundle: true,
    platform: "node",
    format: "esm",
    target: "node20",
    logLevel: "warning"
  });
  await import(new URL(outfile, import.meta.url).href);
} finally {
  await rm(workdir, { recursive: true, force: true });
}
