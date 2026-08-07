#!/usr/bin/env python3
"""Measure the built frontend bundle deterministically.

EXE-01 freezes a pre-change size baseline and later proves route-level code
splitting. Both sides must read the same numbers, so this module is the single
measurement implementation: byte sizes from disk, gzip sizes from a fixed
compression level with a zeroed mtime, and the import graph from Vite's own
build manifest rather than a hand-maintained list.

Usage:
    python3 scripts/exe01/bundle_report.py                # print JSON report
    python3 scripts/exe01/bundle_report.py --out PATH     # also write it
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DIST = PROJECT_ROOT / "frontend" / "dist"
MANIFEST = DIST / ".vite" / "manifest.json"
SCHEMA = "exe01.bundle_report.v1"
GZIP_LEVEL = 9


def gzip_size(payload: bytes) -> int:
    """Compress with a zeroed mtime so repeated runs agree byte for byte."""
    return len(gzip.compress(payload, compresslevel=GZIP_LEVEL, mtime=0))


def measure(path: Path) -> dict[str, object]:
    payload = path.read_bytes()
    return {
        "file": path.relative_to(DIST).as_posix(),
        "raw": len(payload),
        "gzip": gzip_size(payload),
    }


def load_manifest() -> dict[str, object]:
    if not MANIFEST.exists():
        return {}
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def entry_names(manifest: dict[str, object]) -> set[str]:
    files: set[str] = set()
    for record in manifest.values():
        if isinstance(record, dict) and record.get("isEntry"):
            file = record.get("file")
            if isinstance(file, str):
                files.add(file)
    return files


def build_graph(manifest: dict[str, object]) -> dict[str, object]:
    """Keep only the fields EXE-01 asserts on, sorted for stable diffs."""
    graph: dict[str, object] = {}
    for source, record in sorted(manifest.items()):
        if not isinstance(record, dict):
            continue
        graph[source] = {
            "file": record.get("file"),
            "isEntry": bool(record.get("isEntry")),
            "isDynamicEntry": bool(record.get("isDynamicEntry")),
            "imports": sorted(record.get("imports") or []),
            "dynamicImports": sorted(record.get("dynamicImports") or []),
            "css": sorted(record.get("css") or []),
        }
    return graph


def collect() -> dict[str, object]:
    if not DIST.exists():
        raise SystemExit(
            "frontend/dist is missing; run `npm --prefix frontend run build` first."
        )
    manifest = load_manifest()
    entries = entry_names(manifest)

    js_files = sorted(DIST.glob("assets/*.js"), key=lambda p: p.name)
    css_files = sorted(DIST.glob("assets/*.css"), key=lambda p: p.name)

    entry_measurements = []
    chunk_measurements = []
    for path in js_files:
        relative = path.relative_to(DIST).as_posix()
        record = measure(path)
        if relative in entries or (not entries and path.name == "index.js"):
            entry_measurements.append(record)
        else:
            chunk_measurements.append(record)

    css_measurements = [measure(path) for path in css_files]
    return {
        "schema": SCHEMA,
        "entries": entry_measurements,
        "chunks": chunk_measurements,
        "css": css_measurements,
        "totals": {
            "entry_js_raw": sum(int(r["raw"]) for r in entry_measurements),
            "entry_js_gzip": sum(int(r["gzip"]) for r in entry_measurements),
            "chunk_js_raw": sum(int(r["raw"]) for r in chunk_measurements),
            "chunk_js_gzip": sum(int(r["gzip"]) for r in chunk_measurements),
            "css_raw": sum(int(r["raw"]) for r in css_measurements),
            "css_gzip": sum(int(r["gzip"]) for r in css_measurements),
            "chunk_count": len(chunk_measurements),
        },
        "graph": build_graph(manifest),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, help="write the report to this path")
    args = parser.parse_args()

    report = collect()
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=False)
    if args.out:
        args.out.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    sys.exit(main())
