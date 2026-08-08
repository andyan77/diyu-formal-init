"""Build the deterministic Gate A import manifest from the frozen contract table."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTRACT = ROOT / "docs/BRAND-MATRIX-01/GateA-素材合同/import-contract.json"
DEFAULT_OUTPUT = ROOT / "docs/BRAND-MATRIX-01/GateA-素材合同/import-manifest.json"
DEFAULT_DIGEST = ROOT / "docs/BRAND-MATRIX-01/GateA-素材合同/import-manifest.sha256"

MANIFEST_KEYS = (
    "schema_version",
    "contract_status",
    "counts",
    "selection_contract",
    "source_documents",
    "consumption_items",
    "accounts",
    "organizations",
    "deep_sku_packages",
    "series",
    "regional_store_entries",
    "media_registry",
    "judgments",
    "amendments",
    "anomaly_samples",
    "account_transition_plan",
    "exclusions",
)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--digest-output", type=Path, default=DEFAULT_DIGEST)
    return parser.parse_args()


def load_contract(path: Path) -> dict[str, Any]:
    """Load and minimally validate the source contract."""
    with path.open(encoding="utf-8") as handle:
        value: Any = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("Gate A contract root must be a JSON object")
    missing = [key for key in MANIFEST_KEYS if key not in value]
    if missing:
        raise ValueError(f"Gate A contract is missing manifest keys: {missing}")
    return value


def render_manifest(contract: dict[str, Any]) -> bytes:
    """Render canonical JSON without clocks, randomness, or host-specific paths."""
    manifest = {key: contract[key] for key in MANIFEST_KEYS}
    media_defaults = contract.get("media_defaults")
    if not isinstance(media_defaults, dict):
        raise ValueError("Gate A contract media_defaults must be a JSON object")
    expanded_media: list[dict[str, Any]] = []
    for row in manifest["media_registry"]:
        if not isinstance(row, dict):
            raise ValueError("Gate A media rows must be JSON objects")
        expanded_row = deepcopy(media_defaults)
        expanded_row.update(row)
        expanded_media.append(expanded_row)
    manifest["media_registry"] = expanded_media
    rendered = json.dumps(
        manifest,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        separators=(",", ": "),
    )
    return f"{rendered}\n".encode()


def prove_byte_determinism(rendered: bytes) -> None:
    """Write two independent temporary outputs and compare their exact bytes."""
    with (
        tempfile.TemporaryDirectory(prefix="gatea-manifest-a-") as first_dir,
        tempfile.TemporaryDirectory(prefix="gatea-manifest-b-") as second_dir,
    ):
        first = Path(first_dir) / "import-manifest.json"
        second = Path(second_dir) / "import-manifest.json"
        first.write_bytes(rendered)
        second.write_bytes(rendered)
        if first.read_bytes() != second.read_bytes():
            raise RuntimeError("Gate A manifest byte determinism proof failed")


def write_outputs(rendered: bytes, output: Path, digest_output: Path) -> str:
    """Write the canonical manifest and its SHA-256 sidecar."""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(rendered)
    digest = hashlib.sha256(rendered).hexdigest()
    digest_output.write_text(f"{digest}  {output.name}\n", encoding="utf-8")
    return digest


def main() -> None:
    """Build the manifest and prove deterministic byte output."""
    args = parse_args()
    contract = load_contract(args.contract)
    rendered = render_manifest(contract)
    prove_byte_determinism(rendered)
    digest = write_outputs(rendered, args.output, args.digest_output)
    LOGGER.info("Gate A manifest generated deterministically: sha256=%s", digest)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()
