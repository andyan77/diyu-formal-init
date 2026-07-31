from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast
from uuid import UUID

from src.shared.creative_kernel import (
    KERNEL_VERSION,
    CreativeKernelUnit,
    KernelPurpose,
    normalize_writer_unit_text,
)
from src.shared.narrative import visible_digest
from src.shared.types import MediaFormat

GATE_C_REVIEW_CRITERIA: Final[tuple[str, ...]] = (
    "primary_value",
    "account_link",
    "platform_completeness",
    "natural_language",
    "media_non_repetition",
    "fact_and_resource_boundary",
    "production_executability",
    "series_continuity",
)
GATE_C_FINAL_CARD_IDS: Final[frozenset[str]] = frozenset({"P1", "P2", "P3", "P4", "P5", "series2", "series3"})


class EvidenceBindingError(ValueError):
    """Raised when a Gate C review cannot be reproduced from its exact files."""


@dataclass(frozen=True)
class ArtifactEvidenceInput:
    card_id: str
    artifact_file: str
    raw_response_file: str


@dataclass(frozen=True)
class HumanReviewInput:
    card_id: str
    artifact_file: str
    verdict: str
    criteria: dict[str, str]
    notes: str
    value_evidence: dict[str, object] | None = None


@dataclass(frozen=True)
class EvidenceRuntimeInput:
    database: bool
    formal_api: bool
    business_persistence: bool


@dataclass(frozen=True)
class NormalizationEvidenceInput:
    card_id: str
    unit_id: str
    purpose: KernelPurpose
    media_format: MediaFormat


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def artifact_visible_digest(path: Path) -> str:
    document = _json_object(path)
    outline = document.get("outline")
    body = document.get("body")
    if not isinstance(outline, str) or not outline.strip():
        raise EvidenceBindingError(f"{path.name}: artifact outline is unavailable")
    if not isinstance(body, str) or not body.strip():
        raise EvidenceBindingError(f"{path.name}: artifact body is unavailable")
    return visible_digest(outline, body)


def write_gate_c_evidence(
    root: Path,
    *,
    implementation_sha: str,
    model: str,
    temperature: int,
    max_retries: int,
    artifacts: tuple[ArtifactEvidenceInput, ...],
    reviews: tuple[HumanReviewInput, ...],
    normalizations: tuple[NormalizationEvidenceInput, ...] = (),
    runtime: EvidenceRuntimeInput | None = None,
) -> None:
    """Write one private, reproducible manifest for an already completed suite."""

    _assert_sha(implementation_sha, label="implementation SHA")
    runtime = runtime or EvidenceRuntimeInput(
        database=False,
        formal_api=False,
        business_persistence=False,
    )
    if not model.strip() or temperature != 0 or max_retries != 0:
        raise EvidenceBindingError("final suite model configuration drifted")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    root.chmod(0o700)
    if any((root / filename).exists() for filename in ("manifest.json", "human-review.json", "SHA256SUMS")):
        raise EvidenceBindingError("final suite evidence outputs already exist")
    if {item.card_id for item in artifacts} != GATE_C_FINAL_CARD_IDS:
        raise EvidenceBindingError("final suite card coverage drifted")
    if len({item.card_id for item in artifacts}) != len(artifacts):
        raise EvidenceBindingError("final suite card IDs are duplicated")

    review_by_card = {review.card_id: review for review in reviews}
    if len(review_by_card) != len(reviews) or set(review_by_card) != {item.card_id for item in artifacts}:
        raise EvidenceBindingError("human review coverage does not match artifacts")

    artifact_records: list[dict[str, str]] = []
    review_records: list[dict[str, object]] = []
    raw_path_by_card: dict[str, Path] = {}
    for item in artifacts:
        artifact_path = _private_child(root, item.artifact_file)
        raw_path = _private_child(root, item.raw_response_file)
        artifact_sha = sha256_file(artifact_path)
        visible = artifact_visible_digest(artifact_path)
        raw_sha = sha256_file(raw_path)
        artifact_document = _json_object(artifact_path)
        persistence_ids = {
            identifier: _required_uuid_text(
                artifact_document.get(identifier),
                label=f"{item.card_id}: formal {identifier}",
            )
            for identifier in ("task_id", "run_id", "version_id")
        }
        raw_path_by_card[item.card_id] = raw_path
        review = review_by_card[item.card_id]
        if review.artifact_file != item.artifact_file:
            raise EvidenceBindingError(f"{item.card_id}: review references another artifact")
        if review.verdict != "PASS":
            raise EvidenceBindingError(f"{item.card_id}: human review did not pass")
        if set(review.criteria) != set(GATE_C_REVIEW_CRITERIA) or any(
            review.criteria[criterion] != "PASS" for criterion in GATE_C_REVIEW_CRITERIA
        ):
            raise EvidenceBindingError(f"{item.card_id}: human review criteria are incomplete")
        value_evidence = _assert_value_evidence(
            item.card_id,
            artifact_path=artifact_path,
            value=review.value_evidence,
        )
        artifact_records.append(
            {
                "card_id": item.card_id,
                "artifact_file": item.artifact_file,
                "artifact_sha256": artifact_sha,
                "visible_digest": visible,
                "raw_response_file": item.raw_response_file,
                "raw_response_sha256": raw_sha,
                **persistence_ids,
            }
        )
        review_records.append(
            {
                "card_id": item.card_id,
                "artifact_file": item.artifact_file,
                "artifact_sha256": artifact_sha,
                "visible_digest": visible,
                "verdict": review.verdict,
                "criteria": {criterion: review.criteria[criterion] for criterion in GATE_C_REVIEW_CRITERIA},
                "notes": review.notes,
                "value_evidence": value_evidence,
            }
        )

    normalization_records = [
        _normalization_record(
            item,
            raw_path=raw_path_by_card.get(item.card_id),
        )
        for item in normalizations
    ]
    normalization_keys = {(str(record["card_id"]), str(record["unit_id"])) for record in normalization_records}
    if len(normalization_keys) != len(normalization_records):
        raise EvidenceBindingError("writer wrapper normalization records are duplicated")

    _write_private_json(
        root / "human-review.json",
        {
            "review_contract": "ux03-gate-c-human-review-v2",
            "digest_algorithm": "src.shared.narrative.visible_digest(outline, body)",
            "reviews": review_records,
        },
    )
    _write_private_json(
        root / "manifest.json",
        {
            "manifest_version": "ux03-gate-c-evidence-v2",
            "implementation_sha": implementation_sha,
            "provider_config": {
                "model": model,
                "temperature": temperature,
                "max_retries": max_retries,
                "database": runtime.database,
                "redis": False,
                "formal_api": runtime.formal_api,
                "business_persistence": runtime.business_persistence,
            },
            "artifacts": artifact_records,
            "writer_wrapper_normalizations": normalization_records,
        },
    )
    checksummed = sorted(path for path in root.iterdir() if path.is_file() and path.name != "SHA256SUMS")
    lines = "".join(f"{sha256_file(path)}  {path.name}\n" for path in checksummed)
    _write_private(root / "SHA256SUMS", lines.encode())
    verify_gate_c_evidence(root)


def verify_gate_c_evidence(root: Path) -> None:
    manifest = _json_object(root / "manifest.json")
    review_document = _json_object(root / "human-review.json")
    if (
        manifest.get("manifest_version") != "ux03-gate-c-evidence-v2"
        or review_document.get("review_contract")
        != "ux03-gate-c-human-review-v2"
    ):
        raise EvidenceBindingError("Gate C evidence contract version drifted")
    implementation_sha = manifest.get("implementation_sha")
    if not isinstance(implementation_sha, str):
        raise EvidenceBindingError("manifest implementation SHA is unavailable")
    _assert_sha(implementation_sha, label="manifest implementation SHA")
    artifacts = manifest.get("artifacts")
    normalizations = manifest.get("writer_wrapper_normalizations")
    reviews = review_document.get("reviews")
    if not isinstance(artifacts, list) or not isinstance(normalizations, list) or not isinstance(reviews, list):
        raise EvidenceBindingError("manifest or review record list is unavailable")
    artifact_card_ids = {str(record.get("card_id")) for record in artifacts if isinstance(record, dict)}
    if len(artifact_card_ids) != len(artifacts) or artifact_card_ids != GATE_C_FINAL_CARD_IDS:
        raise EvidenceBindingError("final suite card coverage drifted")
    reviews_by_card = {str(review.get("card_id")): review for review in reviews if isinstance(review, dict)}
    if len(reviews_by_card) != len(reviews):
        raise EvidenceBindingError("human review card IDs are duplicated")
    raw_path_by_card: dict[str, Path] = {}
    for record in artifacts:
        if not isinstance(record, dict):
            raise EvidenceBindingError("artifact record is invalid")
        card_id = str(record.get("card_id"))
        artifact_file = str(record.get("artifact_file"))
        raw_response_file = str(record.get("raw_response_file"))
        artifact_path = _private_child(root, artifact_file)
        raw_path = _private_child(root, raw_response_file)
        raw_path_by_card[card_id] = raw_path
        artifact_document = _json_object(artifact_path)
        for identifier in ("task_id", "run_id", "version_id"):
            persisted = _required_uuid_text(
                artifact_document.get(identifier),
                label=f"{card_id}: formal {identifier}",
            )
            if record.get(identifier) != persisted:
                raise EvidenceBindingError(
                    f"{card_id}: manifest {identifier} does not match artifact"
                )
        artifact_sha = sha256_file(artifact_path)
        visible = artifact_visible_digest(artifact_path)
        raw_sha = sha256_file(raw_path)
        if record.get("artifact_sha256") != artifact_sha:
            raise EvidenceBindingError(f"{card_id}: artifact file SHA does not match")
        if record.get("visible_digest") != visible:
            raise EvidenceBindingError(f"{card_id}: visible digest does not match")
        if record.get("raw_response_sha256") != raw_sha:
            raise EvidenceBindingError(f"{card_id}: raw response SHA does not match")
        review = reviews_by_card.get(card_id)
        if review is None:
            raise EvidenceBindingError(f"{card_id}: human review is unavailable")
        if (
            review.get("artifact_file") != artifact_file
            or review.get("artifact_sha256") != artifact_sha
            or review.get("visible_digest") != visible
            or review.get("verdict") != "PASS"
        ):
            raise EvidenceBindingError(f"{card_id}: human review is bound to another artifact")
        criteria = review.get("criteria")
        if (
            not isinstance(criteria, dict)
            or set(criteria) != set(GATE_C_REVIEW_CRITERIA)
            or any(criteria.get(criterion) != "PASS" for criterion in GATE_C_REVIEW_CRITERIA)
        ):
            raise EvidenceBindingError(f"{card_id}: human review criteria are incomplete")
        _assert_value_evidence(
            card_id,
            artifact_path=artifact_path,
            value=review.get("value_evidence"),
        )
    if set(reviews_by_card) != {str(record.get("card_id")) for record in artifacts if isinstance(record, dict)}:
        raise EvidenceBindingError("human review contains an unrelated card")
    normalization_keys: set[tuple[str, str]] = set()
    for record in normalizations:
        if not isinstance(record, dict):
            raise EvidenceBindingError("writer wrapper normalization record is invalid")
        card_id = str(record.get("card_id"))
        unit_id = str(record.get("unit_id"))
        key = (card_id, unit_id)
        if key in normalization_keys:
            raise EvidenceBindingError("writer wrapper normalization records are duplicated")
        normalization_keys.add(key)
        purpose = record.get("purpose")
        media_format = record.get("media_format")
        if purpose != "media_opening" or media_format != "graphic":
            raise EvidenceBindingError(f"{card_id}: writer wrapper normalization scope is invalid")
        expected = _normalization_record(
            NormalizationEvidenceInput(
                card_id=card_id,
                unit_id=unit_id,
                purpose=cast(KernelPurpose, purpose),
                media_format=cast(MediaFormat, media_format),
            ),
            raw_path=raw_path_by_card.get(card_id),
        )
        if record != expected:
            raise EvidenceBindingError(f"{card_id}: writer wrapper normalization evidence does not match raw response")
    _verify_sha256sums(root)


def _assert_value_evidence(
    card_id: str,
    *,
    artifact_path: Path,
    value: object,
) -> dict[str, object] | None:
    """Bind the two product cards to concrete, reviewable value evidence.

    PASS flags remain human judgements.  This deterministic layer only prevents
    an all-PASS form from standing in for the product-specific proposition that
    was actually read in the bound artifact.
    """

    if card_id not in {"P2", "P5"}:
        if value is not None:
            raise EvidenceBindingError(f"{card_id}: unrelated product value evidence")
        return None
    if not isinstance(value, dict):
        raise EvidenceBindingError(f"{card_id}: product value evidence is unavailable")
    artifact = _json_object(artifact_path)
    body = artifact.get("body")
    snapshot = artifact.get("formal_snapshot")
    if not isinstance(body, str) or not isinstance(snapshot, dict):
        raise EvidenceBindingError(f"{card_id}: product value artifact is incomplete")
    contract = snapshot.get("product_value_contract")
    if not isinstance(contract, dict):
        raise EvidenceBindingError(f"{card_id}: frozen product value contract is unavailable")
    if card_id == "P2":
        expected_keys = {
            "product_specific_understanding",
            "tradeoff_or_limit",
            "validity_condition",
        }
        contract_keys = {
            "product_specific_understanding": "product_insight",
            "tradeoff_or_limit": "tradeoff_or_limit",
            "validity_condition": "validity_condition",
        }
        if set(value) != expected_keys:
            raise EvidenceBindingError("P2: product value evidence fields drifted")
        for evidence_key, contract_key in contract_keys.items():
            text = value.get(evidence_key)
            if (
                not isinstance(text, str)
                or not text.strip()
                or text != contract.get(contract_key)
                or text not in body
            ):
                raise EvidenceBindingError(
                    f"P2: {evidence_key} is not bound to the visible artifact"
                )
        return dict(value)
    expected_keys = {"concrete_visual_proposition", "resource_refs"}
    if set(value) != expected_keys:
        raise EvidenceBindingError("P5: product value evidence fields drifted")
    proposition = value.get("concrete_visual_proposition")
    refs = value.get("resource_refs")
    if (
        not isinstance(proposition, str)
        or not proposition.strip()
        or proposition != contract.get("visible_styling_proposition")
        or proposition not in body
        or not isinstance(refs, list)
        or len(refs) != 2
        or any(not isinstance(item, str) or not item for item in refs)
        or len(set(refs)) != 2
        or refs != contract.get("resource_refs")
    ):
        raise EvidenceBindingError("P5: visual proposition or resource refs are not bound")
    envelope = snapshot.get("media_capability_envelope")
    resources = envelope.get("resources") if isinstance(envelope, dict) else None
    registered_refs = (
        {
            str(resource.get("resource_id"))
            for resource in resources
            if isinstance(resource, dict)
            and resource.get("capability_id")
            == "registered_product_display"
        }
        if isinstance(resources, list)
        else set()
    )
    if set(refs) != registered_refs:
        raise EvidenceBindingError("P5: review resource refs do not match the frozen envelope")
    return dict(value)


def _normalization_record(
    item: NormalizationEvidenceInput,
    *,
    raw_path: Path | None,
) -> dict[str, str]:
    if raw_path is None:
        raise EvidenceBindingError(f"{item.card_id}: normalization references an unknown card")
    document = _json_object(raw_path)
    try:
        choices = document["choices"]
        if not isinstance(choices, list) or len(choices) != 1:
            raise TypeError
        choice = choices[0]
        if not isinstance(choice, dict):
            raise TypeError
        message = choice["message"]
        if not isinstance(message, dict):
            raise TypeError
        content = message["content"]
        if not isinstance(content, str):
            raise TypeError
        payload = json.loads(content)
        if not isinstance(payload, dict):
            raise TypeError
        units = payload["units"]
        if not isinstance(units, list):
            raise TypeError
        matches = [unit for unit in units if isinstance(unit, dict) and unit.get("unit_id") == item.unit_id]
        if len(matches) != 1 or not isinstance(matches[0].get("text"), str):
            raise TypeError
        raw_text = str(matches[0]["text"])
        unit = CreativeKernelUnit(
            unit_id=item.unit_id,
            purpose=item.purpose,
            allowed_observation_types=("abstract_principle",),
            fact_refs=(),
            constraint_refs=(),
            visible_order=0,
            text="",
        )
        _, receipt = normalize_writer_unit_text(
            raw_text,
            unit=unit,
            kernel_version=KERNEL_VERSION,
            media_format=item.media_format,
        )
    except (
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        raise EvidenceBindingError(f"{item.card_id}: normalization raw response is invalid") from exc
    if receipt is None:
        raise EvidenceBindingError(f"{item.card_id}: normalization did not remove an approved wrapper")
    return {
        "card_id": item.card_id,
        "unit_id": receipt.unit_id,
        "purpose": receipt.purpose,
        "media_format": item.media_format,
        "removed_prefix": receipt.removed_prefix,
        "raw_text_sha256": receipt.raw_text_sha256,
        "normalized_text_sha256": receipt.normalized_text_sha256,
        "normalization_contract_version": receipt.contract_version,
    }


def _verify_sha256sums(root: Path) -> None:
    sums_path = root / "SHA256SUMS"
    if not sums_path.is_file():
        raise EvidenceBindingError("SHA256SUMS is unavailable")
    expected: dict[str, str] = {}
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        digest, separator, filename = line.partition("  ")
        if separator != "  " or not filename or filename in expected:
            raise EvidenceBindingError("SHA256SUMS contains an invalid record")
        _assert_sha(digest, label="file SHA")
        expected[filename] = digest
    observed_files = {path.name for path in root.iterdir() if path.is_file() and path.name != "SHA256SUMS"}
    if set(expected) != observed_files:
        raise EvidenceBindingError("SHA256SUMS file coverage drifted")
    for filename, digest in expected.items():
        if sha256_file(_private_child(root, filename)) != digest:
            raise EvidenceBindingError(f"{filename}: SHA256SUMS does not match")


def _json_object(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceBindingError(f"{path.name}: JSON is unavailable") from exc
    if not isinstance(value, dict):
        raise EvidenceBindingError(f"{path.name}: JSON root must be an object")
    return value


def _private_child(root: Path, filename: str) -> Path:
    if not filename or Path(filename).name != filename:
        raise EvidenceBindingError("evidence filename must be a direct child")
    path = root / filename
    if not path.is_file():
        raise EvidenceBindingError(f"{filename}: evidence file is unavailable")
    return path


def _write_private_json(path: Path, value: object) -> None:
    _write_private(
        path,
        (
            json.dumps(
                value,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode(),
    )


def _write_private(path: Path, content: bytes) -> None:
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
        0o600,
    )
    try:
        remaining = memoryview(content)
        while remaining:
            written = os.write(descriptor, remaining)
            remaining = remaining[written:]
    finally:
        os.close(descriptor)
    path.chmod(0o600)


def _assert_sha(value: str, *, label: str) -> None:
    if len(value) != 64 and len(value) != 40:
        raise EvidenceBindingError(f"{label} has an invalid length")
    if any(character not in "0123456789abcdef" for character in value):
        raise EvidenceBindingError(f"{label} is not lowercase hexadecimal")


def _required_uuid_text(value: object, *, label: str) -> str:
    try:
        parsed = UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise EvidenceBindingError(f"{label} is unavailable") from exc
    return str(parsed)
