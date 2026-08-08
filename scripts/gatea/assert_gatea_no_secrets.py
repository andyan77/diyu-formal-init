"""Fail-closed privacy, frozen-source, and zero-copy audit for Gate A."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2]
EXPECTED_BASE_SHA = "ae4290e4eb7fab7a34f5393b850f759fc0a698ce"
CONTRACT_PATH = ROOT / "docs/BRAND-MATRIX-01/GateA-素材合同/import-contract.json"
V0_ROOT = ROOT / "docs/BRAND-MATRIX-01/素材草案-v0"
REFERENCE_ROOT = ROOT / "docs/品牌入驻候选/笛语服饰"


def sha256_file(path: Path) -> str:
    """Return a file SHA-256 without loading it all into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_git(*args: str) -> str:
    """Run Git and return stdout."""
    completed = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def load_contract() -> dict[str, Any]:
    """Load the Gate A source contract."""
    with CONTRACT_PATH.open(encoding="utf-8") as handle:
        value: Any = json.load(handle)
    if not isinstance(value, dict):
        raise AssertionError("Gate A contract must be a JSON object")
    return value


def assert_inventory(root: Path, expected: dict[str, str], exact_markdown_count: int | None = None) -> None:
    """Compare a directory's expected files to frozen SHA-256 values."""
    if exact_markdown_count is not None:
        markdown_files = sorted(path for path in root.iterdir() if path.is_file() and path.suffix == ".md")
        if len(markdown_files) != exact_markdown_count:
            raise AssertionError(f"expected {exact_markdown_count} Markdown files under supplied source root")
        if {path.name for path in markdown_files} != set(expected):
            raise AssertionError("source-root filenames differ from the frozen 21-file inventory")
    for filename, expected_digest in expected.items():
        path = root / filename
        if not path.is_file() or sha256_file(path) != expected_digest:
            raise AssertionError(f"frozen file differs: {filename}")


def candidate_paths() -> list[Path]:
    """Return tracked and untracked candidate files, excluding ignored files."""
    output = run_git("ls-files", "-co", "--exclude-standard", "-z")
    paths = [ROOT / relative for relative in output.split("\0") if relative]
    return [path for path in paths if path.is_file()]


def added_candidate_text() -> str:
    """Return only new write-surface content for privacy-pattern scanning."""
    untracked = set(run_git("ls-files", "--others", "--exclude-standard").splitlines())
    chunks: list[str] = []
    for relative in sorted(untracked):
        path = ROOT / relative
        if path.is_file():
            try:
                chunks.append(path.read_text(encoding="utf-8"))
            except UnicodeDecodeError:
                raise AssertionError(f"binary file is forbidden in Gate A write surface: {relative}") from None
    diff = run_git("diff", "--unified=0", EXPECTED_BASE_SHA, "--")
    chunks.extend(line[1:] for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++"))
    return "\n".join(chunks)


def assert_no_sensitive_patterns(text: str) -> None:
    """Reject common credential material and host-private absolute evidence paths."""
    private_key_marker = "-----BEGIN " + "PRIVATE KEY-----"
    patterns = {
        "OpenAI-style token": re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}"),
        "GitHub token": re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
        "AWS access key": re.compile(r"AKIA[0-9A-Z]{16}"),
        "private key": re.compile(re.escape(private_key_marker)),
        "private absolute user path": re.compile(r"/(?:home|mnt/[a-zA-Z]/Users)/[^/\s]+/"),
    }
    matches = [label for label, pattern in patterns.items() if pattern.search(text)]
    if matches:
        raise AssertionError(f"sensitive patterns found in Gate A write surface: {matches}")


def main() -> None:
    """Assert live source integrity, repository zero-copy, and secret-free additions."""
    contract = load_contract()
    inventory = contract.get("integrity_inventory")
    if not isinstance(inventory, dict):
        raise AssertionError("integrity inventory is missing")

    source_root_value = os.environ.get("GATEA_SOURCE_ROOT")
    if not source_root_value:
        raise AssertionError("GATEA_SOURCE_ROOT must be supplied explicitly; .env discovery is forbidden")
    source_root = Path(source_root_value)
    if not source_root.is_dir():
        raise AssertionError("supplied Gate A source root is not a directory")

    windows_rows = [row for row in contract["source_documents"] if row.get("source_kind") == "windows_readonly"]
    windows_inventory = {row["relative_filename"]: row["sha256"] for row in windows_rows}
    assert_inventory(source_root, windows_inventory, exact_markdown_count=21)
    assert_inventory(V0_ROOT, inventory["frozen_v0"])
    assert_inventory(REFERENCE_ROOT, inventory["repository_references"])

    run_git("diff", "--quiet", EXPECTED_BASE_SHA, "--", str(V0_ROOT.relative_to(ROOT)))
    run_git("diff", "--quiet", EXPECTED_BASE_SHA, "--", str(REFERENCE_ROOT.relative_to(ROOT)))

    source_hashes = set(windows_inventory.values())
    candidate_hashes = {sha256_file(path): path for path in candidate_paths()}
    intersection = source_hashes & candidate_hashes.keys()
    if intersection:
        paths = [str(candidate_hashes[digest].relative_to(ROOT)) for digest in sorted(intersection)]
        raise AssertionError(f"complete Windows source blobs entered candidate tree: {paths}")

    assert_no_sensitive_patterns(added_candidate_text())
    LOGGER.info("Gate A privacy PASS: 21 source blobs absent; secrets and private paths found=0")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()
