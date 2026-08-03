from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import cast

GOVERNANCE_VERSION = "candidate-scoped-acceptance-v2"
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_SUCCESS_STATUSES = frozenset({"artifact_ready", "deterministic_preflight_pass"})
_RETRYABLE_STATUS = "transport_failed_no_response"
_TERMINAL_FAILURE_STATUSES = frozenset(
    {"delivery_uncertain", "hard_boundary_failed", "structure_failed"}
)
_REVIEW_STATUSES = frozenset({"PASS", "FAIL"})
_SAMPLE_FINAL_STATUSES = (
    _SUCCESS_STATUSES
    | _TERMINAL_FAILURE_STATUSES
    | {_RETRYABLE_STATUS, "PENDING", "HARD_FAIL", "PRODUCT_QUALITY_VARIANCE", "PASS"}
)


class AcceptanceLedgerError(RuntimeError):
    """The candidate-scoped acceptance ledger failed closed."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _identifier(value: str, label: str) -> str:
    if not _IDENTIFIER.fullmatch(value):
        raise AcceptanceLedgerError(f"{label} is invalid")
    return value


def _sha256(value: str, label: str) -> str:
    if not _SHA256.fullmatch(value):
        raise AcceptanceLedgerError(f"{label} is invalid")
    return value


def acceptance_key(candidate_sha: str, suite_id: str) -> str:
    if not _GIT_SHA.fullmatch(candidate_sha):
        raise AcceptanceLedgerError("candidate SHA is invalid")
    return f"{candidate_sha}:{_identifier(suite_id, 'suite ID')}"


def validate_acceptance_runs(value: object) -> dict[str, dict[str, object]]:
    if not isinstance(value, dict):
        raise AcceptanceLedgerError("acceptance runs are invalid")
    runs = cast(dict[str, object], value)
    validated: dict[str, dict[str, object]] = {}
    for key, raw_run in runs.items():
        if not isinstance(key, str) or not isinstance(raw_run, dict):
            raise AcceptanceLedgerError("acceptance run entry is invalid")
        run = cast(dict[str, object], raw_run)
        required = {
            "candidate_sha",
            "suite_id",
            "acceptance_run_id",
            "config_digest",
            "status",
            "started_at",
            "completed_at",
            "samples",
            "failure_count_by_class",
        }
        if set(run) != required:
            raise AcceptanceLedgerError("acceptance run fields drifted")
        if acceptance_key(str(run["candidate_sha"]), str(run["suite_id"])) != key:
            raise AcceptanceLedgerError("acceptance run key drifted")
        _identifier(str(run["acceptance_run_id"]), "acceptance run ID")
        _sha256(str(run["config_digest"]), "acceptance config digest")
        if run["status"] not in {"RUNNING", "GENERATED", "REVIEWED", "FAILED"}:
            raise AcceptanceLedgerError("acceptance run status is invalid")
        if not isinstance(run["started_at"], str) or (
            run["completed_at"] is not None and not isinstance(run["completed_at"], str)
        ):
            raise AcceptanceLedgerError("acceptance run timestamps are invalid")
        samples = run["samples"]
        if not isinstance(samples, dict) or not samples:
            raise AcceptanceLedgerError("acceptance samples are invalid")
        for sample_id, raw_sample in cast(dict[str, object], samples).items():
            _identifier(sample_id, "sample ID")
            if not isinstance(raw_sample, dict):
                raise AcceptanceLedgerError("acceptance sample is invalid")
            sample = cast(dict[str, object], raw_sample)
            if set(sample) != {"attempts", "human_review", "final_status"}:
                raise AcceptanceLedgerError("acceptance sample fields drifted")
            if (
                not isinstance(sample["attempts"], list)
                or not isinstance(sample["human_review"], dict)
                or sample["final_status"] not in _SAMPLE_FINAL_STATUSES
            ):
                raise AcceptanceLedgerError("acceptance sample history is invalid")
            attempts = cast(list[object], sample["attempts"])
            for raw_attempt in attempts:
                if not isinstance(raw_attempt, dict) or set(raw_attempt) != {
                    "recorded_at",
                    "provider_response_received",
                    "request_count",
                    "artifact_digest",
                    "final_status",
                }:
                    raise AcceptanceLedgerError("acceptance sample attempt fields drifted")
                attempt = cast(dict[str, object], raw_attempt)
                response_received = attempt["provider_response_received"]
                request_count = attempt["request_count"]
                artifact_digest = attempt["artifact_digest"]
                final_status = attempt["final_status"]
                if (
                    not isinstance(attempt["recorded_at"], str)
                    or type(response_received) is not bool
                    or type(request_count) is not int
                    or request_count < 0
                    or final_status not in _SUCCESS_STATUSES | _TERMINAL_FAILURE_STATUSES | {_RETRYABLE_STATUS}
                    or (artifact_digest is not None and not isinstance(artifact_digest, str))
                ):
                    raise AcceptanceLedgerError("acceptance sample attempt is invalid")
                if artifact_digest is not None:
                    _sha256(artifact_digest, "artifact digest")
                if response_received and (request_count < 1 or artifact_digest is None):
                    raise AcceptanceLedgerError("received provider response evidence is incomplete")
                if not response_received and request_count != 0:
                    raise AcceptanceLedgerError("no-response attempt count is invalid")
                if final_status in _SUCCESS_STATUSES and artifact_digest is None:
                    raise AcceptanceLedgerError("successful sample evidence is incomplete")
                if final_status == _RETRYABLE_STATUS and response_received:
                    raise AcceptanceLedgerError("received provider response cannot be retryable")
            review = cast(dict[str, object], sample["human_review"])
            if review:
                if set(review) != {
                    "hard_boundary",
                    "structure_complete",
                    "product_usable",
                    "review_digest",
                    "reviewed_at",
                }:
                    raise AcceptanceLedgerError("acceptance review fields drifted")
                if (
                    review["hard_boundary"] not in _REVIEW_STATUSES
                    or review["structure_complete"] not in _REVIEW_STATUSES
                    or review["product_usable"] not in _REVIEW_STATUSES
                    or not isinstance(review["reviewed_at"], str)
                ):
                    raise AcceptanceLedgerError("acceptance review verdict is invalid")
                _sha256(str(review["review_digest"]), "review digest")
        if not isinstance(run["failure_count_by_class"], dict):
            raise AcceptanceLedgerError("acceptance failure counts are invalid")
        validated[key] = run
    return validated


def begin_acceptance_run(
    runs: Mapping[str, dict[str, object]],
    *,
    candidate_sha: str,
    suite_id: str,
    acceptance_run_id: str,
    config_digest: str,
    sample_ids: Sequence[str],
    allow_resume: bool = False,
) -> tuple[dict[str, dict[str, object]], bool]:
    key = acceptance_key(candidate_sha, suite_id)
    run_id = _identifier(acceptance_run_id, "acceptance run ID")
    digest = _sha256(config_digest, "acceptance config digest")
    normalized_samples = tuple(_identifier(value, "sample ID") for value in sample_ids)
    if not normalized_samples or len(normalized_samples) != len(set(normalized_samples)):
        raise AcceptanceLedgerError("acceptance sample coverage is empty or duplicated")
    current = dict(runs)
    existing = current.get(key)
    if existing is not None:
        existing_samples = cast(dict[str, dict[str, object]], existing["samples"])
        if (
            existing["acceptance_run_id"] != run_id
            or existing["config_digest"] != digest
            or set(existing_samples) != set(normalized_samples)
        ):
            raise AcceptanceLedgerError("candidate suite already belongs to another acceptance run")
        if existing["status"] != "RUNNING" or not allow_resume:
            raise AcceptanceLedgerError("candidate suite formal acceptance already started")
        if not any(sample["final_status"] == _RETRYABLE_STATUS for sample in existing_samples.values()):
            raise AcceptanceLedgerError("candidate suite has no unreceived transport failure to resume")
        return current, True
    for run in current.values():
        if run["candidate_sha"] == candidate_sha and run["acceptance_run_id"] != run_id:
            raise AcceptanceLedgerError("candidate acceptance run ID drifted across suite partitions")
    current[key] = {
        "candidate_sha": candidate_sha,
        "suite_id": suite_id,
        "acceptance_run_id": run_id,
        "config_digest": digest,
        "status": "RUNNING",
        "started_at": _now(),
        "completed_at": None,
        "samples": {
            sample_id: {"attempts": [], "human_review": {}, "final_status": "PENDING"}
            for sample_id in normalized_samples
        },
        "failure_count_by_class": {},
    }
    return current, False


def record_sample_attempt(
    runs: Mapping[str, dict[str, object]],
    *,
    candidate_sha: str,
    suite_id: str,
    acceptance_run_id: str,
    sample_id: str,
    provider_response_received: bool,
    request_count: int,
    artifact_digest: str | None,
    final_status: str,
) -> dict[str, dict[str, object]]:
    key = acceptance_key(candidate_sha, suite_id)
    current = dict(runs)
    run = dict(current.get(key) or {})
    if not run or run.get("acceptance_run_id") != acceptance_run_id or run.get("status") != "RUNNING":
        raise AcceptanceLedgerError("acceptance run is unavailable")
    samples = dict(cast(dict[str, object], run["samples"]))
    raw_sample = samples.get(_identifier(sample_id, "sample ID"))
    if not isinstance(raw_sample, dict):
        raise AcceptanceLedgerError("acceptance sample is outside the frozen suite")
    sample = dict(cast(dict[str, object], raw_sample))
    attempts = list(cast(list[object], sample["attempts"]))
    if attempts:
        previous = cast(dict[str, object], attempts[-1])
        if previous.get("final_status") != _RETRYABLE_STATUS:
            raise AcceptanceLedgerError("acceptance sample already received a terminal result")
    allowed_statuses = _SUCCESS_STATUSES | _TERMINAL_FAILURE_STATUSES | {_RETRYABLE_STATUS}
    if final_status not in allowed_statuses:
        raise AcceptanceLedgerError("acceptance sample final status is invalid")
    if artifact_digest is not None:
        _sha256(artifact_digest, "artifact digest")
    if provider_response_received:
        if request_count < 1 or artifact_digest is None:
            raise AcceptanceLedgerError("provider response evidence is incomplete")
        if final_status == _RETRYABLE_STATUS:
            raise AcceptanceLedgerError("a received provider response cannot be retried")
    elif request_count != 0:
        raise AcceptanceLedgerError("no-response attempts must have request_count=0")
    if final_status in _SUCCESS_STATUSES and artifact_digest is None:
        raise AcceptanceLedgerError("successful sample evidence needs an artifact digest")
    attempts.append(
        {
            "recorded_at": _now(),
            "provider_response_received": provider_response_received,
            "request_count": request_count,
            "artifact_digest": artifact_digest,
            "final_status": final_status,
        }
    )
    sample["attempts"] = attempts
    sample["final_status"] = final_status
    samples[sample_id] = sample
    run["samples"] = samples
    if final_status in _TERMINAL_FAILURE_STATUSES:
        run["status"] = "FAILED"
    current[key] = run
    return current


def complete_generation(
    runs: Mapping[str, dict[str, object]],
    *,
    candidate_sha: str,
    suite_id: str,
    acceptance_run_id: str,
) -> dict[str, dict[str, object]]:
    key = acceptance_key(candidate_sha, suite_id)
    current = dict(runs)
    run = dict(current.get(key) or {})
    if not run or run.get("acceptance_run_id") != acceptance_run_id or run.get("status") != "RUNNING":
        raise AcceptanceLedgerError("acceptance run cannot be completed")
    samples = cast(dict[str, dict[str, object]], run["samples"])
    if any(sample["final_status"] not in _SUCCESS_STATUSES for sample in samples.values()):
        raise AcceptanceLedgerError("acceptance generation is incomplete")
    run["status"] = "GENERATED"
    run["completed_at"] = _now()
    current[key] = run
    return current


def record_human_review(
    runs: Mapping[str, dict[str, object]],
    *,
    candidate_sha: str,
    suite_id: str,
    acceptance_run_id: str,
    sample_id: str,
    hard_boundary: str,
    structure_complete: str,
    product_usable: str,
    review_digest: str,
) -> dict[str, dict[str, object]]:
    key = acceptance_key(candidate_sha, suite_id)
    current = dict(runs)
    run = dict(current.get(key) or {})
    if not run or run.get("acceptance_run_id") != acceptance_run_id or run.get("status") not in {
        "GENERATED",
        "REVIEWED",
    }:
        raise AcceptanceLedgerError("acceptance review run is unavailable")
    values = {hard_boundary, structure_complete, product_usable}
    if not values <= _REVIEW_STATUSES:
        raise AcceptanceLedgerError("acceptance review verdict is invalid")
    _sha256(review_digest, "review digest")
    samples = dict(cast(dict[str, object], run["samples"]))
    raw_sample = samples.get(_identifier(sample_id, "sample ID"))
    if not isinstance(raw_sample, dict):
        raise AcceptanceLedgerError("acceptance review sample is outside the frozen suite")
    sample = dict(cast(dict[str, object], raw_sample))
    if cast(dict[str, object], sample["human_review"]):
        raise AcceptanceLedgerError("acceptance sample was already reviewed")
    sample["human_review"] = {
        "hard_boundary": hard_boundary,
        "structure_complete": structure_complete,
        "product_usable": product_usable,
        "review_digest": review_digest,
        "reviewed_at": _now(),
    }
    if hard_boundary == "FAIL" or structure_complete == "FAIL":
        sample["final_status"] = "HARD_FAIL"
        run["status"] = "FAILED"
    elif product_usable == "FAIL":
        sample["final_status"] = "PRODUCT_QUALITY_VARIANCE"
    else:
        sample["final_status"] = "PASS"
    samples[sample_id] = sample
    run["samples"] = samples
    if run["status"] != "FAILED" and all(
        bool(cast(dict[str, object], item)["human_review"])
        for item in samples.values()
    ):
        run["status"] = "REVIEWED"
    current[key] = run
    return current


def pending_samples(
    runs: Mapping[str, dict[str, object]],
    *,
    candidate_sha: str,
    suite_id: str,
    acceptance_run_id: str,
) -> tuple[str, ...]:
    run = runs.get(acceptance_key(candidate_sha, suite_id))
    if run is None or run.get("acceptance_run_id") != acceptance_run_id:
        raise AcceptanceLedgerError("acceptance run is unavailable")
    samples = cast(dict[str, dict[str, object]], run["samples"])
    return tuple(
        sample_id
        for sample_id, sample in samples.items()
        if sample["final_status"] in {"PENDING", _RETRYABLE_STATUS}
    )
