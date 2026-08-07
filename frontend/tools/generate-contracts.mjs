// Generate frontend API types from the repository's OpenAPI document.
//
// FE-02 forbids hand-written API types for new contracts. The only accepted
// input is the committed `openapi.json` — planning documents are not a schema
// source — so this script has exactly one input and one output, and records
// both digests in the manifest that `assert_codegen_drift.py` re-checks.
//
//   npm --prefix frontend run contracts:gen         (write)
//   npm --prefix frontend run contracts:check       (verify)
//
// `--check` writes nothing and exits non-zero when the committed output no
// longer matches what the current OpenAPI document produces. The script lives
// under frontend/ so Node resolves openapi-typescript from frontend/node_modules.

import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

import openapiTS, { astToString } from "openapi-typescript";

const PROJECT_ROOT = join(
  dirname(fileURLToPath(import.meta.url)),
  "..",
  ".."
);
const SOURCE = join(PROJECT_ROOT, "openapi.json");
const OUTPUT = join(
  PROJECT_ROOT,
  "frontend/src/shared/contracts/gen/openapi.d.ts"
);
const MANIFEST = join(
  PROJECT_ROOT,
  "frontend/src/shared/contracts/manifest.json"
);
const COMMAND = "npm --prefix frontend run contracts:gen";

// Contracts UX-04R FE-02 lists that are absent from the OpenAPI document at
// this baseline. They are recorded, not invented: writing a placeholder schema
// from the planning text would create a second, unowned source of truth.
const BLOCKED_CONTRACTS = [
  { contract: "context_selected", owner: "EXE-02" },
  { contract: "BrandBasisItemV1", owner: "EXE-02" },
  { contract: "OpportunityV2", owner: "EXE-03" },
  { contract: "InteractionRequestV1", owner: "EXE-05" },
  { contract: "IntentProjectionV1", owner: "EXE-05" },
  { contract: "RouteDecisionV1", owner: "EXE-05" },
  { contract: "InteractionResponseV1", owner: "EXE-05" },
  {
    contract: "AdvisorDraftV1",
    owner: "EXE-05",
    note:
      "EXE-01 FE-01 delivers the client-side draft state contract of the same "
      + "name; the wire contract still has no OpenAPI schema."
  },
  { contract: "CreationProposalV1", owner: "EXE-06" },
  { contract: "ContentProductionPackageV1", owner: "EXE-07" },
  { contract: "DisplayExecutionPackageV1", owner: "EXE-07" },
  { contract: "ContentDecisionProjectionV1", owner: "EXE-08" },
  { contract: "brand_basis_feedback", owner: "EXE-04" }
];

const sha256 = value => createHash("sha256").update(value).digest("hex");

const header = sourceDigest =>
  [
    "/**",
    " * GENERATED FILE — DO NOT EDIT BY HAND.",
    " *",
    ` * Source:   openapi.json (sha256 ${sourceDigest})`,
    ` * Command:  ${COMMAND}`,
    " * Drift:    python3 scripts/exe01/assert_codegen_drift.py",
    " *",
    " * Regenerate instead of editing; the drift gate compares byte for byte.",
    " */",
    ""
  ].join("\n");

const build = async () => {
  const raw = readFileSync(SOURCE, "utf8");
  const document = JSON.parse(raw);
  const ast = await openapiTS(document, { alphabetize: true });
  const sourceDigest = sha256(raw);
  const body = `${header(sourceDigest)}${astToString(ast)}`;
  const schemas = Object.keys(document.components?.schemas ?? {}).sort();
  const manifest = {
    schema: "exe01.contract_manifest.v1",
    command: COMMAND,
    source: {
      path: relative(PROJECT_ROOT, SOURCE),
      sha256: sourceDigest,
      openapi: document.openapi,
      path_count: Object.keys(document.paths ?? {}).length,
      schema_count: schemas.length
    },
    generated: {
      path: relative(PROJECT_ROOT, OUTPUT),
      sha256: sha256(body),
      line_count: body.split("\n").length
    },
    // Every schema the document actually defines is generated; new frontend
    // code must import from here rather than declaring its own shape.
    allowlist: schemas,
    blocked: BLOCKED_CONTRACTS.map(entry => ({
      ...entry,
      status: "BLOCKED_FE02_CONTRACT_SOURCE",
      reason: "no schema in openapi.json at this baseline"
    }))
  };
  return { body, manifest: `${JSON.stringify(manifest, null, 2)}\n` };
};

const readOrNull = path => {
  try {
    return readFileSync(path, "utf8");
  } catch {
    return null;
  }
};

const main = async () => {
  const checkOnly = process.argv.includes("--check");
  const { body, manifest } = await build();
  const targets = [
    [OUTPUT, body],
    [MANIFEST, manifest]
  ];

  if (checkOnly) {
    const drifted = targets
      .filter(([path, expected]) => readOrNull(path) !== expected)
      .map(([path]) => relative(PROJECT_ROOT, path));
    if (drifted.length > 0) {
      console.error(`codegen drift in: ${drifted.join(", ")}`);
      console.error(`regenerate with: ${COMMAND}`);
      process.exit(1);
    }
    console.log("codegen up to date");
    return;
  }

  for (const [path, contents] of targets) {
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, contents, "utf8");
    console.log(`wrote ${relative(PROJECT_ROOT, path)}`);
  }
};

await main();
