#!/usr/bin/env python3
"""Function spans for one file, whatever language it is in.

Python goes through the standard library's ast; TypeScript, TSX and mjs go
through the compiler already in frontend/devDependencies. No new dependency
either way, and neither path counts braces.
"""

from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXTRACTOR = PROJECT_ROOT / "frontend/tools/function-spans.mjs"
SCRIPT_SUFFIXES = {".ts", ".tsx", ".mts", ".mjs", ".js", ".jsx"}


def python_spans(path: Path, source: str) -> list[dict[str, object]]:
    tree = ast.parse(source, filename=str(path))
    spans: list[dict[str, object]] = []

    def walk(node: ast.AST, trail: tuple[str, ...]) -> None:
        here = trail
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            here = (*trail, node.name)
            end = node.end_lineno or node.lineno
            spans.append(
                {
                    "file": str(path),
                    "path": " > ".join(here),
                    "start_line": node.lineno,
                    "end_line": end,
                    "lines": end - node.lineno + 1,
                }
            )
        elif isinstance(node, ast.ClassDef):
            here = (*trail, node.name)
        for child in ast.iter_child_nodes(node):
            walk(child, here)

    walk(tree, ())
    return spans


def script_spans(paths: list[Path]) -> list[dict[str, object]]:
    if not paths:
        return []
    result = subprocess.run(
        ["node", str(EXTRACTOR), *[str(item) for item in paths]],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return list(json.loads(result.stdout))


def spans_for(paths: list[Path], contents: dict[Path, str]) -> list[dict[str, object]]:
    """`contents` lets a caller measure a git blob without touching the tree."""
    collected: list[dict[str, object]] = []
    scripts: list[Path] = []
    for path in paths:
        if path.suffix == ".py":
            collected.extend(python_spans(path, contents[path]))
        elif path.suffix in SCRIPT_SUFFIXES:
            scripts.append(path)
    collected.extend(script_spans(scripts))
    return collected
