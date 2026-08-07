#!/usr/bin/env python3
"""Assert the generated API contracts still match openapi.json.

Two independent checks, deliberately not sharing an implementation: the
generator re-runs itself in `--check` mode, and this script recomputes the
digests recorded in the manifest straight from the files on disk. If the
generator's own comparison were the only gate, a bug in it would hide exactly
the drift it exists to catch.

Usage:
    python3 scripts/exe01/assert_codegen_drift.py
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND = PROJECT_ROOT / "frontend"
GENERATOR = FRONTEND / "tools" / "generate-contracts.mjs"
MANIFEST = FRONTEND / "src" / "shared" / "contracts" / "manifest.json"
# UX-04R FE-02 lists these; none has an OpenAPI schema at this baseline, so the
# manifest must keep declaring them blocked rather than quietly dropping them.
REQUIRED_BLOCKED = {
    "context_selected",
    "BrandBasisItemV1",
    "OpportunityV2",
    "InteractionRequestV1",
    "IntentProjectionV1",
    "RouteDecisionV1",
    "InteractionResponseV1",
    "AdvisorDraftV1",
    "CreationProposalV1",
    "ContentProductionPackageV1",
    "DisplayExecutionPackageV1",
    "ContentDecisionProjectionV1",
    "brand_basis_feedback",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_generator_check() -> list[str]:
    if not (FRONTEND / "node_modules").exists():
        return ["frontend/node_modules is missing; run `npm --prefix frontend ci`"]
    result = subprocess.run(
        ["node", str(GENERATOR), "--check"],
        cwd=FRONTEND,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return [
            "generator --check failed: "
            + (result.stderr.strip() or result.stdout.strip() or "no output")
        ]
    return []


def check_manifest() -> list[str]:
    if not MANIFEST.exists():
        return [f"missing contract manifest at {MANIFEST}"]
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    failures: list[str] = []

    source = PROJECT_ROOT / str(manifest["source"]["path"])
    if sha256(source) != manifest["source"]["sha256"]:
        failures.append(
            "openapi.json changed since the contracts were generated; "
            "run `npm --prefix frontend run contracts:gen`"
        )

    generated = PROJECT_ROOT / str(manifest["generated"]["path"])
    if not generated.exists():
        failures.append(f"generated contracts missing at {generated}")
    elif sha256(generated) != manifest["generated"]["sha256"]:
        failures.append(
            "generated contracts were edited by hand; regenerate instead"
        )

    document = json.loads(source.read_text(encoding="utf-8"))
    schemas = set(document.get("components", {}).get("schemas", {}))
    allowlisted = set(manifest["allowlist"])
    if allowlisted != schemas:
        missing = sorted(schemas - allowlisted)
        extra = sorted(allowlisted - schemas)
        failures.append(
            f"allowlist does not match openapi schemas (missing={missing}, extra={extra})"
        )

    blocked = {entry["contract"] for entry in manifest["blocked"]}
    if not REQUIRED_BLOCKED <= blocked:
        failures.append(
            "manifest dropped blocked contracts: "
            + ", ".join(sorted(REQUIRED_BLOCKED - blocked))
        )
    resurrected = sorted(blocked & schemas)
    if resurrected:
        failures.append(
            "these contracts now exist in openapi.json and must leave the "
            f"blocked list: {resurrected}"
        )
    return failures


def main() -> int:
    failures = run_generator_check() + check_manifest()
    if failures:
        for failure in failures:
            print(f"FAIL {failure}", file=sys.stderr)
        return 1

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    print("PASS codegen matches openapi.json")
    print(
        "  source openapi.json paths={path_count} schemas={schema_count}".format(
            **manifest["source"]
        )
    )
    print(
        "  generated {path} lines={line_count}".format(**manifest["generated"])
    )
    print(
        f"  allowlisted={len(manifest['allowlist'])} "
        f"blocked_FE02_CONTRACT_SOURCE={len(manifest['blocked'])}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
