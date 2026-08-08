from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any, cast

PROCESSING_VERSION = "gate-d-media-master-v1"
AUTHORIZATION_REF = "DIYU-MEDIA-AUTH-DECISION-v2/D13"
FONT_PATH = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
TEN_GATE_ORDER = (
    "source_checksum_verified",
    "technical_master_valid",
    "brand_identifier_present",
    "commercial_use_decision",
    "secondary_edit_decision",
    "ai_recreation_decision",
    "person_rights_evidence",
    "child_rights_evidence",
    "third_party_elements_evidence",
    "platform_scope_and_validity_evidence",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_contract(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Gate A import contract must be an object")
    return cast(dict[str, Any], value)


def _declared_checksums(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        digest, separator, filename = line.partition("  ")
        if separator != "  " or len(digest) != 64 or not filename:
            raise ValueError("SHA256SUMS contains a malformed line")
        if filename in result:
            raise ValueError("SHA256SUMS contains a duplicate filename")
        result[filename] = digest
    return result


def _probe(path: Path) -> dict[str, object]:
    completed = subprocess.run(
        (
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration,size:stream=index,codec_type,codec_name,width,height,avg_frame_rate",
            "-of",
            "json",
            os.fspath(path),
        ),
        check=True,
        capture_output=True,
        text=True,
    )
    value = json.loads(completed.stdout)
    if not isinstance(value, dict):
        raise ValueError(f"ffprobe returned an invalid document for {path.name}")
    return cast(dict[str, object], value)


def _duration(probe: dict[str, object]) -> float:
    raw_format = probe.get("format")
    if not isinstance(raw_format, dict):
        raise ValueError("ffprobe omitted format information")
    value = float(str(raw_format.get("duration") or "0"))
    if value <= 0:
        raise ValueError("source video duration must be positive")
    return value


def _render(source: Path, target: Path, duration: float) -> None:
    escaped_font = os.fspath(FONT_PATH).replace("'", "\\'")
    end_at = f"{duration:.6f}"
    filters = ",".join(
        (
            (
                f"drawtext=fontfile='{escaped_font}':text='笛语/DIYU':"
                "fontcolor=white:fontsize=h/24:box=1:boxcolor=black@0.45:"
                "boxborderw=8:x=w-tw-24:y=24"
            ),
            "tpad=stop_mode=clone:stop_duration=1.5",
            f"drawbox=enable='gte(t,{end_at})':x=0:y=0:w=iw:h=ih:color=black:t=fill",
            (
                f"drawtext=fontfile='{escaped_font}':text='笛语/DIYU':"
                "fontcolor=white:fontsize=h/10:x=(w-tw)/2:y=(h-th)/2:"
                f"enable='gte(t,{end_at})'"
            ),
        )
    )
    temporary = target.with_suffix(".partial.mp4")
    if temporary.exists():
        temporary.unlink()
    subprocess.run(
        (
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            os.fspath(source),
            "-map_metadata",
            "-1",
            "-vf",
            filters,
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-threads",
            "1",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            os.fspath(temporary),
        ),
        check=True,
    )
    temporary.replace(target)


def _gate_results() -> list[dict[str, str]]:
    statuses = {
        "source_checksum_verified": ("PASS", "SHA256SUMS independent verification"),
        "technical_master_valid": ("PASS", "ffprobe completed after rendering"),
        "brand_identifier_present": ("PASS", PROCESSING_VERSION),
        "commercial_use_decision": ("PASS", AUTHORIZATION_REF),
        "secondary_edit_decision": ("PASS", AUTHORIZATION_REF),
        "ai_recreation_decision": ("PASS", AUTHORIZATION_REF),
        "person_rights_evidence": ("QUARANTINED", "per-person evidence not supplied"),
        "child_rights_evidence": ("QUARANTINED", "guardian evidence not supplied"),
        "third_party_elements_evidence": ("QUARANTINED", "per-file review evidence not supplied"),
        "platform_scope_and_validity_evidence": (
            "QUARANTINED",
            "per-file platform and validity evidence not supplied",
        ),
    }
    return [
        {"gate": gate, "status": statuses[gate][0], "evidence": statuses[gate][1]}
        for gate in TEN_GATE_ORDER
    ]


def process(source_root: Path, output_root: Path, contract_path: Path) -> dict[str, object]:
    if not FONT_PATH.is_file():
        raise ValueError("required CJK font is unavailable")
    contract = _load_contract(contract_path)
    registry = contract.get("media_registry")
    if not isinstance(registry, list) or len(registry) != 26:
        raise ValueError("Gate A media registry must contain exactly 26 items")
    checksums = _declared_checksums(source_root / "SHA256SUMS")
    expected_names = {str(item["source_filename_raw"]) for item in registry}
    if set(checksums) != expected_names:
        raise ValueError("media filenames differ from SHA256SUMS or Gate A registry")
    output_root.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    for raw in registry:
        item = cast(dict[str, Any], raw)
        source_name = str(item["source_filename_raw"])
        source = source_root / source_name
        source_sha = _sha256(source)
        if source_sha != checksums[source_name]:
            raise ValueError(f"source checksum mismatch: {source_name}")
        source_probe = _probe(source)
        target_name = f"{item['target_master_name']}.mp4"
        target = output_root / target_name
        _render(source, target, _duration(source_probe))
        master_probe = _probe(target)
        gates = _gate_results()
        overall = "PASS" if all(gate["status"] == "PASS" for gate in gates) else "QUARANTINED"
        records.append(
            {
                "media_id": item["media_id"],
                "source_filename_raw": source_name,
                "declared_identifier": item["declared_identifier"],
                "source_sha256": source_sha,
                "source_probe": source_probe,
                "master_filename": target_name,
                "master_sha256": _sha256(target),
                "master_probe": master_probe,
                "identifier_position": "upper_right_safe_area_and_1.5s_end_slate",
                "processing_version": PROCESSING_VERSION,
                "founder_authorization_ref": AUTHORIZATION_REF,
                "product_bindings": item["product_bindings"],
                "target_account_ids": item["target_account_ids"],
                "ten_release_gates": gates,
                "release_status": overall,
                "original_p5_eligible": False,
                "master_p5_eligible": overall == "PASS" and bool(item["product_bindings"]),
            }
        )
        print(f"rendered {item['media_id']} ({len(records)}/26)", flush=True)
    document: dict[str, object] = {
        "schema_version": PROCESSING_VERSION,
        "source_count": len(records),
        "master_count": len(records),
        "pass_count": sum(record["release_status"] == "PASS" for record in records),
        "fail_count": sum(record["release_status"] == "FAIL" for record in records),
        "quarantined_count": sum(record["release_status"] == "QUARANTINED" for record in records),
        "original_p5_eligible_count": 0,
        "master_p5_eligible_count": sum(bool(record["master_p5_eligible"]) for record in records),
        "records": records,
    }
    serialized = json.dumps(document, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    document["manifest_digest"] = hashlib.sha256(serialized).hexdigest()
    return document


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--manifest-output", type=Path, required=True)
    arguments = parser.parse_args()
    document = process(arguments.source_root, arguments.output_root, arguments.contract)
    arguments.manifest_output.parent.mkdir(parents=True, exist_ok=True)
    arguments.manifest_output.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {key: document[key] for key in (
                "manifest_digest",
                "master_count",
                "pass_count",
                "fail_count",
                "quarantined_count",
                "master_p5_eligible_count",
            )},
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
