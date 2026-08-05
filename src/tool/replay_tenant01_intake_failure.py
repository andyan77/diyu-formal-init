from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import cast

from src.shared.intake_contract import replay_legacy_intake_role_projection
from src.shared.narrative import user_fact_candidates
from src.tool.tenant01_evidence import failed_generation_gate_evaluation

_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


def _head_sha() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"{path.name} is not one JSON object")
    return cast(dict[str, object], value)


def replay(
    *,
    raw_path: Path,
    config_path: Path,
    expected_raw_sha256: str,
    candidate_sha: str,
) -> dict[str, object]:
    if not _SHA_PATTERN.fullmatch(candidate_sha):
        raise RuntimeError("candidate SHA is invalid")
    before = _sha256(raw_path)
    if before != expected_raw_sha256:
        raise RuntimeError("legacy raw digest drifted")
    raw = _object(raw_path)
    responses = raw.get("responses")
    if raw.get("card_id") != "P1" or raw.get("request_count") != 1 or not isinstance(responses, list) or len(responses) != 1:
        raise RuntimeError("legacy P1 raw response binding drifted")
    response = responses[0]
    if not isinstance(response, dict) or response.get("stage") != "intake":
        raise RuntimeError("legacy P1 raw is not one intake response")
    provider = response.get("response")
    choices = provider.get("choices") if isinstance(provider, dict) else None
    first = choices[0] if isinstance(choices, list) and choices else None
    message = first.get("message") if isinstance(first, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str):
        raise RuntimeError("legacy P1 intake content is unavailable")
    document = json.loads(content)
    if not isinstance(document, dict):
        raise RuntimeError("legacy P1 intake content is not one object")

    config = _object(config_path)
    cards = config.get("cards")
    card = next(
        (
            item
            for item in cards
            if isinstance(item, dict) and item.get("card_id") == "P1"
        ),
        None,
    ) if isinstance(cards, list) else None
    user_message = card.get("message") if isinstance(card, dict) else None
    if not isinstance(user_message, str):
        raise RuntimeError("frozen P1 input is unavailable")
    candidates = user_fact_candidates((user_message,))
    projection = replay_legacy_intake_role_projection(document, candidates)
    after = _sha256(raw_path)
    if after != before:
        raise RuntimeError("legacy raw changed during replay")
    candidate_by_id = {candidate.source_id: candidate.exact_text for candidate in candidates}
    return {
        "replay_version": "tenant01-intake-legacy-replay-v1",
        "candidate_sha": candidate_sha,
        "execution_mode": "NO_MODEL_HISTORICAL_REPLAY",
        "source_raw": str(raw_path),
        "source_raw_sha256_before": before,
        "source_raw_sha256_after": after,
        "source_contract_version": projection.source_contract_version,
        "derived_contract_version": projection.contract_version,
        "frozen_config": str(config_path),
        "frozen_config_sha256": _sha256(config_path),
        "legacy_duplicate_field_present": "user_fact_sentence_ids" in document,
        "legacy_duplicate_field_authoritative": False,
        "roles": [
            {"sentence_id": source_id, "role": role}
            for source_id, role in projection.roles
        ],
        "derived_actuality_source_ids": list(projection.actuality_source_ids),
        "derived_actuality_texts": [
            candidate_by_id[source_id] for source_id in projection.actuality_source_ids
        ],
        "derived_instruction_source_ids": list(projection.instruction_source_ids),
        "writer_entry_role_projection_ready": True,
        "provider_request_count": 0,
        "historical_failure_classification": failed_generation_gate_evaluation(),
        "historical_artifact_present": False,
        "verdict": "PASS",
    }


def _write_private_json(path: Path, value: object) -> None:
    if path.exists():
        raise RuntimeError("legacy replay output already exists")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    payload = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay one legacy TENANT-01 intake response without a model call.")
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--expected-raw-sha256", required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    candidate_sha = str(args.candidate_sha)
    if _head_sha() != candidate_sha:
        raise RuntimeError("candidate SHA is not the current HEAD")
    result = replay(
        raw_path=args.raw.resolve(),
        config_path=args.config.resolve(),
        expected_raw_sha256=str(args.expected_raw_sha256),
        candidate_sha=candidate_sha,
    )
    _write_private_json(args.output.resolve(), result)
    print(json.dumps({"verdict": "PASS", "provider_request_count": 0}, sort_keys=True))


if __name__ == "__main__":
    main()
