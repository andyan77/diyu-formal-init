from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

from src.tool.execution_acceptance import (
    GOVERNANCE_VERSION,
    AcceptanceLedgerError,
    begin_acceptance_run,
    complete_generation,
    pending_samples,
    record_human_review,
    record_sample_attempt,
    validate_acceptance_runs,
)

STATE_VERSION = "TENANT-01-EXECUTION-CONTROL-V1"
MILESTONE = "TENANT-01"
DEFAULT_RUNTIME_ROOT = Path("var/execution-control/TENANT-01")
DEFAULT_PROTECTED_PATH = Path("docs/项目记忆.md")

NORMAL_STATES = frozenset(
    {
        "BOOTSTRAP",
        "CONTRACT_FROZEN",
        "STRUCTURAL_IMPLEMENTATION",
        "DETERMINISTIC_GATE",
        "MODEL_READINESS",
        "MODEL_PREFLIGHT",
        "GENERALIZATION_EVAL",
        "INDEPENDENT_AUDIT",
        "AWAITING_CONTROLLER_AUDIT",
        "CANDIDATE_REVIEW",
        "CI_READY",
        "DEPLOY_READY",
        "REVIEW",
    }
)
EXCEPTION_STATES = frozenset(
    {
        "NEEDS_DIAGNOSIS",
        "NEEDS_ARCHITECTURE_REVIEW",
        "NEEDS_CONTROLLER_RULING",
        "ENVIRONMENT_RESTRICTED",
        "FAILED_SAFE",
    }
)
STATES = NORMAL_STATES | EXCEPTION_STATES
FAILURE_CLASSES = (
    "implementation_defect",
    "shared_contract_defect",
    "product_quality_variance",
    "environment_restriction",
    "product_contract_conflict",
    "provider_transport_failure",
    "provider_semantic_failure",
    "hard_semantic_boundary_failure",
    "security_or_isolation_failure",
)
_TRANSITIONS: Mapping[str, frozenset[str]] = {
    "BOOTSTRAP": frozenset({"CONTRACT_FROZEN", "FAILED_SAFE"}),
    "CONTRACT_FROZEN": frozenset({"STRUCTURAL_IMPLEMENTATION", "FAILED_SAFE"}),
    "STRUCTURAL_IMPLEMENTATION": frozenset(
        {"DETERMINISTIC_GATE", "NEEDS_DIAGNOSIS", "NEEDS_CONTROLLER_RULING", "FAILED_SAFE"}
    ),
    "DETERMINISTIC_GATE": frozenset(
        {
            "MODEL_READINESS",
            "MODEL_PREFLIGHT",
            "STRUCTURAL_IMPLEMENTATION",
            "NEEDS_DIAGNOSIS",
            "FAILED_SAFE",
        }
    ),
    "MODEL_READINESS": frozenset(
        {"GENERALIZATION_EVAL", "NEEDS_DIAGNOSIS", "ENVIRONMENT_RESTRICTED", "FAILED_SAFE"}
    ),
    "MODEL_PREFLIGHT": frozenset(
        {
            "GENERALIZATION_EVAL",
            "NEEDS_DIAGNOSIS",
            "NEEDS_ARCHITECTURE_REVIEW",
            "ENVIRONMENT_RESTRICTED",
            "FAILED_SAFE",
        }
    ),
    "GENERALIZATION_EVAL": frozenset(
        {
            "INDEPENDENT_AUDIT",
            "AWAITING_CONTROLLER_AUDIT",
            "NEEDS_DIAGNOSIS",
            "NEEDS_ARCHITECTURE_REVIEW",
            "NEEDS_CONTROLLER_RULING",
            "ENVIRONMENT_RESTRICTED",
            "FAILED_SAFE",
        }
    ),
    "INDEPENDENT_AUDIT": frozenset({"CANDIDATE_REVIEW", "NEEDS_DIAGNOSIS", "FAILED_SAFE"}),
    "AWAITING_CONTROLLER_AUDIT": frozenset({"CANDIDATE_REVIEW", "NEEDS_CONTROLLER_RULING", "FAILED_SAFE"}),
    "CANDIDATE_REVIEW": frozenset({"CI_READY", "NEEDS_DIAGNOSIS", "FAILED_SAFE"}),
    "CI_READY": frozenset({"DEPLOY_READY", "NEEDS_DIAGNOSIS", "FAILED_SAFE"}),
    "DEPLOY_READY": frozenset({"REVIEW", "ENVIRONMENT_RESTRICTED", "FAILED_SAFE"}),
    "NEEDS_DIAGNOSIS": frozenset({"STRUCTURAL_IMPLEMENTATION", "DETERMINISTIC_GATE", "FAILED_SAFE"}),
    "NEEDS_ARCHITECTURE_REVIEW": frozenset({"STRUCTURAL_IMPLEMENTATION", "NEEDS_CONTROLLER_RULING"}),
    "NEEDS_CONTROLLER_RULING": frozenset({"STRUCTURAL_IMPLEMENTATION", "FAILED_SAFE"}),
    "ENVIRONMENT_RESTRICTED": frozenset(
        {"MODEL_READINESS", "MODEL_PREFLIGHT", "GENERALIZATION_EVAL", "DEPLOY_READY", "FAILED_SAFE"}
    ),
    # A controller ruling may replace the contract that caused a safe stop.
    # The transition itself is performed only by ``adopt_ruling`` so ordinary
    # callers still cannot escape FAILED_SAFE through the generic CLI.
    "FAILED_SAFE": frozenset(),
    "REVIEW": frozenset(),
}
_STATE_FIELDS = frozenset(
    {
        "state_version",
        "milestone",
        "current_state",
        "previous_state",
        "objective_digest",
        "contract_digest",
        "controller_decision_digest",
        "head_sha",
        "origin_sha",
        "worktree_digest",
        "protected_user_change_digest",
        "active_gate",
        "completed_gates",
        "active_run_id",
        "active_command",
        "active_pid",
        "started_at",
        "heartbeat_at",
        "last_completed_at",
        "failure_class",
        "failure_count_by_class",
        "governance_version",
        "acceptance_runs",
        "evidence_paths",
        "approved_next_action",
        "executor_id",
        "event_count",
        "last_event_hash",
    }
)
_LEGACY_STATE_FIELDS = _STATE_FIELDS - {"governance_version", "acceptance_runs"}


class ExecutionControlError(RuntimeError):
    """The local execution-control gate failed closed."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(repository: Path, *arguments: str) -> bytes:
    completed = subprocess.run(
        ("git", *arguments),
        cwd=repository,
        check=True,
        capture_output=True,
    )
    return completed.stdout


def _git_sha(repository: Path, revision: str) -> str:
    return _git(repository, "rev-parse", "--verify", revision).decode("ascii").strip()


def _protected_digest(repository: Path, protected_path: Path) -> str:
    return hashlib.sha256(_git(repository, "diff", "--binary", "--", str(protected_path))).hexdigest()


def _worktree_digest(repository: Path) -> str:
    status = _git(repository, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    tracked_diff = _git(repository, "diff", "--binary", "HEAD", "--")
    staged_diff = _git(repository, "diff", "--binary", "--cached", "--")
    untracked_hashes: list[tuple[str, str]] = []
    for raw_entry in status.split(b"\0"):
        if not raw_entry or not raw_entry.startswith(b"?? "):
            continue
        relative = raw_entry[3:].decode("utf-8", errors="strict")
        path = repository / relative
        if path.is_file():
            untracked_hashes.append((relative, _file_digest(path)))
    return hashlib.sha256(
        status + b"\0" + tracked_diff + b"\0" + staged_diff + b"\0" + _canonical_bytes(untracked_hashes)
    ).hexdigest()


def _read_object(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise ExecutionControlError(f"missing execution-control file: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ExecutionControlError(f"execution-control file is not an object: {path}")
    return cast(dict[str, object], value)


def _atomic_private_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(_canonical_bytes(value) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary.exists():
            temporary.unlink()


class ExecutionControl:
    def __init__(
        self,
        repository: Path,
        runtime_root: Path = DEFAULT_RUNTIME_ROOT,
        protected_path: Path = DEFAULT_PROTECTED_PATH,
    ) -> None:
        self.repository = repository.resolve()
        self.root = runtime_root if runtime_root.is_absolute() else self.repository / runtime_root
        self.protected_path = protected_path
        self.state_path = self.root / "state.json"
        self.events_path = self.root / "events.jsonl"
        self.decision_path = self.root / "controller-decision.json"
        self.failure_path = self.root / "failure.json"
        self.status_path = self.root / "status.json"
        self.lock_path = self.root / ".lock"

    @contextmanager
    def _lock(self) -> Iterator[None]:
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root, 0o700)
        descriptor = os.open(self.lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def _state(self) -> dict[str, object]:
        state = _read_object(self.state_path)
        if set(state) == _LEGACY_STATE_FIELDS:
            state = {
                **state,
                "governance_version": "legacy-global-failure-count-v1",
                "acceptance_runs": {},
            }
        elif set(state) != _STATE_FIELDS:
            raise ExecutionControlError("execution-control state fields drifted")
        if state["state_version"] != STATE_VERSION or state["milestone"] != MILESTONE:
            raise ExecutionControlError("execution-control state identity drifted")
        if state["current_state"] not in STATES:
            raise ExecutionControlError("execution-control state is unknown")
        raw_counts = state["failure_count_by_class"]
        if not isinstance(raw_counts, dict) or not set(raw_counts) <= set(FAILURE_CLASSES):
            raise ExecutionControlError("execution-control failure counts drifted")
        typed_counts = cast(dict[str, object], raw_counts)
        if any(type(value) is not int or value < 0 for value in typed_counts.values()):
            raise ExecutionControlError("execution-control failure counts are invalid")
        state["failure_count_by_class"] = {
            name: cast(int, typed_counts.get(name, 0)) for name in FAILURE_CLASSES
        }
        try:
            validate_acceptance_runs(state["acceptance_runs"])
        except AcceptanceLedgerError as exc:
            raise ExecutionControlError(str(exc)) from exc
        return state

    def _verify_event_chain(self, state: Mapping[str, object]) -> None:
        if not self.events_path.is_file():
            raise ExecutionControlError("execution-control event history is missing")
        previous = "0" * 64
        count = 0
        for line in self.events_path.read_text(encoding="utf-8").splitlines():
            event = json.loads(line)
            if not isinstance(event, dict):
                raise ExecutionControlError("execution-control event is not an object")
            count += 1
            if event.get("event_index") != count or event.get("previous_event_hash") != previous:
                raise ExecutionControlError("execution-control event order or ancestry drifted")
            event_hash = event.get("event_hash")
            unsigned = {key: value for key, value in event.items() if key != "event_hash"}
            if not isinstance(event_hash, str) or event_hash != _digest(unsigned):
                raise ExecutionControlError("execution-control event hash drifted")
            previous = event_hash
        if state["event_count"] != count or state["last_event_hash"] != previous:
            raise ExecutionControlError("execution-control event history was deleted or rewritten")

    def _verify_decision(self, state: Mapping[str, object], *, permit_audit_update: bool = False) -> dict[str, object]:
        decision = _read_object(self.decision_path)
        if decision.get("milestone") != MILESTONE:
            raise ExecutionControlError("controller decision milestone drifted")
        if _digest(decision.get("contract")) != state["contract_digest"]:
            raise ExecutionControlError("execution contract digest drifted")
        if not permit_audit_update and _file_digest(self.decision_path) != state["controller_decision_digest"]:
            raise ExecutionControlError("controller decision digest drifted")
        return decision

    def _verify_static(self, state: Mapping[str, object], *, check_worktree: bool = True) -> None:
        self._verify_event_chain(state)
        self._verify_decision(state)
        if _git_sha(self.repository, "HEAD") != state["head_sha"]:
            raise ExecutionControlError("HEAD differs from execution-control state")
        if _protected_digest(self.repository, self.protected_path) != state["protected_user_change_digest"]:
            raise ExecutionControlError("protected user change digest drifted")
        if check_worktree and _worktree_digest(self.repository) != state["worktree_digest"]:
            raise ExecutionControlError("worktree differs from execution-control state")

    def _event(self, state: dict[str, object], event_type: str, data: Mapping[str, object]) -> dict[str, object]:
        index = cast(int, state["event_count"]) + 1
        unsigned: dict[str, object] = {
            "event_version": STATE_VERSION,
            "event_index": index,
            "recorded_at": _now(),
            "event_type": event_type,
            "previous_event_hash": state["last_event_hash"],
            "head_sha": _git_sha(self.repository, "HEAD"),
            "state": state["current_state"],
            "data": dict(data),
        }
        return {**unsigned, "event_hash": _digest(unsigned)}

    def _commit(self, state: dict[str, object], event_type: str, data: Mapping[str, object]) -> dict[str, object]:
        event = self._event(state, event_type, data)
        descriptor = os.open(self.events_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        with os.fdopen(descriptor, "ab") as handle:
            handle.write(_canonical_bytes(event) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        state["event_count"] = event["event_index"]
        state["last_event_hash"] = event["event_hash"]
        _atomic_private_json(self.state_path, state)
        self._write_status(state)
        return state

    def _write_status(self, state: Mapping[str, object]) -> None:
        status = {
            "state_version": state["state_version"],
            "milestone": state["milestone"],
            "current_state": state["current_state"],
            "head_sha": state["head_sha"],
            "active_gate": state["active_gate"],
            "active_run_id": state["active_run_id"],
            "active_command": state["active_command"],
            "active_pid": state["active_pid"],
            "heartbeat_at": state["heartbeat_at"],
            "failure_class": state["failure_class"],
            "governance_version": state["governance_version"],
            "acceptance_runs": state["acceptance_runs"],
            "completed_gates": state["completed_gates"],
            "approved_next_action": state["approved_next_action"],
            "evidence_paths": state["evidence_paths"],
        }
        _atomic_private_json(self.status_path, status)

    def initialize(self, decision_source: Path, executor_id: str) -> dict[str, object]:
        with self._lock():
            if self.state_path.exists() or self.events_path.exists():
                raise ExecutionControlError("execution-control state already exists")
            decision = _read_object(decision_source)
            if set(decision) != {"decision_version", "milestone", "objective", "contract", "audit"}:
                raise ExecutionControlError("controller decision fields drifted")
            if decision["milestone"] != MILESTONE or not isinstance(decision["contract"], dict):
                raise ExecutionControlError("controller decision is not for TENANT-01")
            _atomic_private_json(self.decision_path, decision)
            now = _now()
            head_sha = _git_sha(self.repository, "HEAD")
            state: dict[str, object] = {
                "state_version": STATE_VERSION,
                "milestone": MILESTONE,
                "current_state": "BOOTSTRAP",
                "previous_state": None,
                "objective_digest": _digest(decision["objective"]),
                "contract_digest": _digest(decision["contract"]),
                "controller_decision_digest": _file_digest(self.decision_path),
                "head_sha": head_sha,
                "origin_sha": _git_sha(self.repository, "origin/main"),
                "worktree_digest": _worktree_digest(self.repository),
                "protected_user_change_digest": _protected_digest(self.repository, self.protected_path),
                "active_gate": None,
                "completed_gates": [],
                "active_run_id": None,
                "active_command": None,
                "active_pid": None,
                "started_at": now,
                "heartbeat_at": now,
                "last_completed_at": None,
                "failure_class": None,
                "failure_count_by_class": {name: 0 for name in FAILURE_CLASSES},
                "governance_version": GOVERNANCE_VERSION,
                "acceptance_runs": {},
                "evidence_paths": [],
                "approved_next_action": "freeze_contract",
                "executor_id": executor_id,
                "event_count": 0,
                "last_event_hash": "0" * 64,
            }
            return self._commit(
                state,
                "initialized",
                {
                    "objective_digest": state["objective_digest"],
                    "contract_digest": state["contract_digest"],
                    "protected_user_change_digest": state["protected_user_change_digest"],
                },
            )

    def status(self) -> dict[str, object]:
        with self._lock():
            state = self._state()
            self._verify_event_chain(state)
            self._write_status(state)
            return state

    def record_history(self, summary_path: Path) -> dict[str, object]:
        summary = _read_object(summary_path)
        required = {"summary_version", "counts_as_current_attempt", "diagnostic_candidates", "golden_diagnostic"}
        if not required <= set(summary) or set(summary) - required != ({"model_diagnostics"} & set(summary)):
            raise ExecutionControlError("historical execution summary fields drifted")
        if summary["counts_as_current_attempt"] is not False:
            raise ExecutionControlError("historical attempts must not enter current attempt counters")
        model_diagnostics = summary.get("model_diagnostics", [])
        if not isinstance(model_diagnostics, list) or any(
            not isinstance(item, dict)
            or item.get("evidence_role") != "historical_diagnostic"
            or item.get("counts_as_current_acceptance_attempt") is not False
            for item in model_diagnostics
        ):
            raise ExecutionControlError("historical model diagnostic roles are invalid")
        with self._lock():
            state = self._state()
            self._verify_event_chain(state)
            evidence = list(cast(list[str], state["evidence_paths"]))
            relative = str(summary_path)
            if relative not in evidence:
                evidence.append(relative)
            state["evidence_paths"] = evidence
            return self._commit(
                state,
                "historical_diagnostics_recorded",
                {
                    "summary_digest": _file_digest(summary_path),
                    "diagnostic_candidate_count": len(cast(list[object], summary["diagnostic_candidates"])),
                    "model_diagnostic_count": len(model_diagnostics),
                    "counts_as_current_attempt": False,
                },
            )

    def adopt_ruling(self, decision_source: Path) -> dict[str, object]:
        """Replace the pending controller decision without rewriting event history."""
        decision = _read_object(decision_source)
        if set(decision) != {"decision_version", "milestone", "objective", "contract", "audit"}:
            raise ExecutionControlError("controller ruling fields drifted")
        contract = decision.get("contract")
        if (
            decision.get("milestone") != MILESTONE
            or not isinstance(contract, dict)
            or contract.get("ruling_id") != "TENANT01-CONTROLLER-RULING-20260803-FINAL"
        ):
            raise ExecutionControlError("final TENANT-01 controller ruling is invalid")
        with self._lock():
            state = self._state()
            self._verify_event_chain(state)
            self._verify_decision(state)
            previous_state = str(state["current_state"])
            if previous_state not in {
                "STRUCTURAL_IMPLEMENTATION",
                "NEEDS_CONTROLLER_RULING",
                "FAILED_SAFE",
            }:
                raise ExecutionControlError(
                    "controller ruling can only be adopted during structural implementation or a controller stop"
                )
            if _protected_digest(self.repository, self.protected_path) != state["protected_user_change_digest"]:
                raise ExecutionControlError("protected user change digest drifted")
            previous_contract_digest = str(state["contract_digest"])
            previous_head = str(state["head_sha"])
            next_head = _git_sha(self.repository, "HEAD")
            _atomic_private_json(self.decision_path, decision)
            state.update(
                {
                    "previous_state": previous_state,
                    "current_state": "STRUCTURAL_IMPLEMENTATION",
                    "objective_digest": _digest(decision["objective"]),
                    "contract_digest": _digest(contract),
                    "controller_decision_digest": _file_digest(self.decision_path),
                    "governance_version": GOVERNANCE_VERSION,
                    "head_sha": next_head,
                    "origin_sha": _git_sha(self.repository, "origin/main"),
                    "worktree_digest": _worktree_digest(self.repository),
                    "heartbeat_at": _now(),
                    "failure_class": None,
                    "active_gate": None,
                    "active_run_id": None,
                    "active_command": None,
                    "active_pid": None,
                    "approved_next_action": None,
                }
            )
            if next_head != previous_head:
                state["completed_gates"] = []
            return self._commit(
                state,
                "controller_ruling_adopted",
                {
                    "ruling_id": contract["ruling_id"],
                    "from_state": previous_state,
                    "to_state": "STRUCTURAL_IMPLEMENTATION",
                    "previous_head": previous_head,
                    "head_sha": next_head,
                    "previous_contract_digest": previous_contract_digest,
                    "contract_digest": state["contract_digest"],
                    "historical_failure_counts_retained": True,
                    "historical_counts_govern_current_acceptance": False,
                    "historical_acceptance_ledgers_retained": True,
                },
            )

    def begin_acceptance_suite(
        self,
        *,
        candidate_sha: str,
        suite_id: str,
        acceptance_run_id: str,
        config_digest: str,
        sample_ids: tuple[str, ...],
        allow_resume: bool = False,
    ) -> dict[str, object]:
        with self._lock():
            state = self._state()
            self._verify_static(state)
            if state["current_state"] != "GENERALIZATION_EVAL":
                raise ExecutionControlError("formal acceptance can only start in GENERALIZATION_EVAL")
            if candidate_sha != state["head_sha"]:
                raise ExecutionControlError("acceptance candidate SHA differs from the frozen state")
            try:
                runs, resumed = begin_acceptance_run(
                    validate_acceptance_runs(state["acceptance_runs"]),
                    candidate_sha=candidate_sha,
                    suite_id=suite_id,
                    acceptance_run_id=acceptance_run_id,
                    config_digest=config_digest,
                    sample_ids=sample_ids,
                    allow_resume=allow_resume,
                )
            except AcceptanceLedgerError as exc:
                raise ExecutionControlError(str(exc)) from exc
            state["acceptance_runs"] = runs
            state["heartbeat_at"] = _now()
            return self._commit(
                state,
                "acceptance_suite_resumed" if resumed else "acceptance_suite_started",
                {
                    "candidate_sha": candidate_sha,
                    "suite_id": suite_id,
                    "acceptance_run_id": acceptance_run_id,
                    "config_digest": config_digest,
                    "sample_count": len(sample_ids),
                },
            )

    def record_acceptance_sample(
        self,
        *,
        candidate_sha: str,
        suite_id: str,
        acceptance_run_id: str,
        sample_id: str,
        provider_response_received: bool,
        request_count: int,
        artifact_digest: str | None,
        final_status: str,
    ) -> dict[str, object]:
        with self._lock():
            state = self._state()
            self._verify_static(state)
            try:
                state["acceptance_runs"] = record_sample_attempt(
                    validate_acceptance_runs(state["acceptance_runs"]),
                    candidate_sha=candidate_sha,
                    suite_id=suite_id,
                    acceptance_run_id=acceptance_run_id,
                    sample_id=sample_id,
                    provider_response_received=provider_response_received,
                    request_count=request_count,
                    artifact_digest=artifact_digest,
                    final_status=final_status,
                )
            except AcceptanceLedgerError as exc:
                raise ExecutionControlError(str(exc)) from exc
            state["heartbeat_at"] = _now()
            return self._commit(
                state,
                "acceptance_sample_recorded",
                {
                    "candidate_sha": candidate_sha,
                    "suite_id": suite_id,
                    "acceptance_run_id": acceptance_run_id,
                    "sample_id": sample_id,
                    "provider_response_received": provider_response_received,
                    "request_count": request_count,
                    "artifact_digest": artifact_digest,
                    "final_status": final_status,
                },
            )

    def complete_acceptance_suite(
        self,
        *,
        candidate_sha: str,
        suite_id: str,
        acceptance_run_id: str,
    ) -> dict[str, object]:
        with self._lock():
            state = self._state()
            self._verify_static(state)
            try:
                state["acceptance_runs"] = complete_generation(
                    validate_acceptance_runs(state["acceptance_runs"]),
                    candidate_sha=candidate_sha,
                    suite_id=suite_id,
                    acceptance_run_id=acceptance_run_id,
                )
            except AcceptanceLedgerError as exc:
                raise ExecutionControlError(str(exc)) from exc
            state["heartbeat_at"] = _now()
            return self._commit(
                state,
                "acceptance_suite_generated",
                {
                    "candidate_sha": candidate_sha,
                    "suite_id": suite_id,
                    "acceptance_run_id": acceptance_run_id,
                },
            )

    def review_acceptance_sample(
        self,
        *,
        candidate_sha: str,
        suite_id: str,
        acceptance_run_id: str,
        sample_id: str,
        hard_boundary: str,
        structure_complete: str,
        product_usable: str,
        review_digest: str,
    ) -> dict[str, object]:
        with self._lock():
            state = self._state()
            self._verify_static(state)
            try:
                state["acceptance_runs"] = record_human_review(
                    validate_acceptance_runs(state["acceptance_runs"]),
                    candidate_sha=candidate_sha,
                    suite_id=suite_id,
                    acceptance_run_id=acceptance_run_id,
                    sample_id=sample_id,
                    hard_boundary=hard_boundary,
                    structure_complete=structure_complete,
                    product_usable=product_usable,
                    review_digest=review_digest,
                )
            except AcceptanceLedgerError as exc:
                raise ExecutionControlError(str(exc)) from exc
            state["heartbeat_at"] = _now()
            return self._commit(
                state,
                "acceptance_sample_reviewed",
                {
                    "candidate_sha": candidate_sha,
                    "suite_id": suite_id,
                    "acceptance_run_id": acceptance_run_id,
                    "sample_id": sample_id,
                    "hard_boundary": hard_boundary,
                    "structure_complete": structure_complete,
                    "product_usable": product_usable,
                    "review_digest": review_digest,
                },
            )

    def acceptance_pending_samples(
        self,
        *,
        candidate_sha: str,
        suite_id: str,
        acceptance_run_id: str,
    ) -> tuple[str, ...]:
        with self._lock():
            state = self._state()
            self._verify_static(state)
            try:
                return pending_samples(
                    validate_acceptance_runs(state["acceptance_runs"]),
                    candidate_sha=candidate_sha,
                    suite_id=suite_id,
                    acceptance_run_id=acceptance_run_id,
                )
            except AcceptanceLedgerError as exc:
                raise ExecutionControlError(str(exc)) from exc

    def transition(self, expected_state: str, expected_head: str, contract_digest: str, target: str) -> dict[str, object]:
        with self._lock():
            state = self._state()
            self._verify_event_chain(state)
            self._verify_decision(state)
            if state["current_state"] != expected_state or state["head_sha"] != expected_head:
                raise ExecutionControlError("execution-control compare-and-set state or HEAD mismatch")
            if state["contract_digest"] != contract_digest:
                raise ExecutionControlError("execution-control compare-and-set contract mismatch")
            if target not in _TRANSITIONS[expected_state]:
                raise ExecutionControlError(f"transition {expected_state} -> {target} is not allowed")
            if _protected_digest(self.repository, self.protected_path) != state["protected_user_change_digest"]:
                raise ExecutionControlError("protected user change digest drifted")
            if (
                target == "CANDIDATE_REVIEW"
                and expected_state == "AWAITING_CONTROLLER_AUDIT"
                and state["approved_next_action"] != "candidate_review"
            ):
                raise ExecutionControlError("legacy controller audit PASS is required before candidate review")
            completed = set(cast(list[str], state["completed_gates"]))
            review_gates = {"acceptance_finalized", "product_review", "engineering_review"}
            if target == "CANDIDATE_REVIEW" and expected_state == "INDEPENDENT_AUDIT" and not review_gates <= completed:
                raise ExecutionControlError("finalized acceptance and both bounded reviews are required")
            if target == "CI_READY" and not review_gates <= completed:
                raise ExecutionControlError("finalized acceptance and both bounded reviews are required before CI")
            if target == "DEPLOY_READY" and "ci_success" not in completed:
                raise ExecutionControlError("a successful authoritative CI is required before deployment")
            if target == "REVIEW" and not {
                "backup_restore",
                "production_deploy",
                "rollback_roundtrip",
                "synthetic_cleanup",
            } <= completed:
                raise ExecutionControlError("production proof and cleanup are required before REVIEW")
            previous = str(state["current_state"])
            previous_head = str(state["head_sha"])
            next_head = _git_sha(self.repository, "HEAD")
            state.update(
                {
                    "previous_state": previous,
                    "current_state": target,
                    "head_sha": next_head,
                    "origin_sha": _git_sha(self.repository, "origin/main"),
                    "worktree_digest": _worktree_digest(self.repository),
                    "heartbeat_at": _now(),
                    "approved_next_action": None,
                    "failure_class": None,
                }
            )
            gates_invalidated = next_head != previous_head
            if gates_invalidated:
                state["completed_gates"] = []
            return self._commit(
                state,
                "transitioned",
                {
                    "from": previous,
                    "to": target,
                    "previous_head": previous_head,
                    "head_sha": next_head,
                    "completed_gates_invalidated": gates_invalidated,
                },
            )

    def begin(self, gate: str, command: str, run_id: str | None, pid: int) -> dict[str, object]:
        with self._lock():
            state = self._state()
            # Implementation and deterministic states intentionally contain
            # forward WIP.  Freeze the exact tree at command start instead of
            # pretending the initialization tree remains current forever.
            self._verify_static(state, check_worktree=False)
            if state["active_command"] is not None:
                raise ExecutionControlError("another controlled command is already active")
            now = _now()
            state.update(
                {
                    "active_gate": gate,
                    "active_run_id": run_id,
                    "active_command": command,
                    "active_pid": pid,
                    "heartbeat_at": now,
                    "worktree_digest": _worktree_digest(self.repository),
                }
            )
            return self._commit(state, "command_started", {"gate": gate, "command": command, "run_id": run_id})

    def heartbeat(self) -> dict[str, object]:
        with self._lock():
            state = self._state()
            self._verify_event_chain(state)
            if state["active_command"] is None:
                raise ExecutionControlError("no controlled command is active")
            state["heartbeat_at"] = _now()
            return self._commit(state, "heartbeat", {"active_gate": state["active_gate"]})

    def complete(self, gate: str, evidence_path: str | None) -> dict[str, object]:
        with self._lock():
            state = self._state()
            self._verify_event_chain(state)
            if state["active_gate"] != gate:
                raise ExecutionControlError("completed gate does not match active gate")
            if _worktree_digest(self.repository) != state["worktree_digest"]:
                raise ExecutionControlError("worktree changed while the controlled command was running")
            completed = list(cast(list[str], state["completed_gates"]))
            if gate not in completed:
                completed.append(gate)
            evidence = list(cast(list[str], state["evidence_paths"]))
            if evidence_path is not None and evidence_path not in evidence:
                evidence.append(evidence_path)
            now = _now()
            state.update(
                {
                    "completed_gates": completed,
                    "evidence_paths": evidence,
                    "active_gate": None,
                    "active_run_id": None,
                    "active_command": None,
                    "active_pid": None,
                    "heartbeat_at": now,
                    "last_completed_at": now,
                }
            )
            return self._commit(state, "command_completed", {"gate": gate, "evidence_path": evidence_path})

    def observe_command_exit(self, exit_code: int) -> dict[str, object]:
        if exit_code == 0:
            raise ExecutionControlError("successful commands must use complete")
        with self._lock():
            state = self._state()
            self._verify_event_chain(state)
            if state["active_command"] is None:
                raise ExecutionControlError("no controlled command is active")
            state["heartbeat_at"] = _now()
            return self._commit(
                state,
                "command_exit_observed",
                {
                    "gate": state["active_gate"],
                    "command": state["active_command"],
                    "exit_code": exit_code,
                    "classification_required": True,
                },
            )

    def classify(self, failure_document: Mapping[str, object], *, clear_active: bool = False) -> dict[str, object]:
        required = {
            "failure_class",
            "expected_invariant",
            "observed_evidence",
            "affected_scope",
            "owning_component",
            "shared_or_case_specific",
            "product_contract_change_required",
            "why_not_case_patch",
            "allowed_next_state",
        }
        if set(failure_document) != required:
            raise ExecutionControlError("failure classification fields drifted")
        failure_class = str(failure_document["failure_class"])
        if failure_class not in FAILURE_CLASSES:
            raise ExecutionControlError("failure classification is unknown")
        with self._lock():
            state = self._state()
            self._verify_event_chain(state)
            if state["active_command"] is not None and not clear_active:
                raise ExecutionControlError("active command failures must use fail, not classify")
            counts = dict(cast(dict[str, int], state["failure_count_by_class"]))
            counts[failure_class] += 1
            target = str(state["current_state"])
            if failure_class == "shared_contract_defect":
                target = "STRUCTURAL_IMPLEMENTATION"
            elif failure_class == "product_contract_conflict":
                target = "NEEDS_CONTROLLER_RULING"
            elif failure_class == "environment_restriction":
                target = "ENVIRONMENT_RESTRICTED"
            elif failure_class in {"hard_semantic_boundary_failure", "security_or_isolation_failure"}:
                target = "FAILED_SAFE"
            elif failure_class == "implementation_defect":
                target = "NEEDS_DIAGNOSIS"
            if failure_document["allowed_next_state"] != target:
                raise ExecutionControlError("failure allowed_next_state does not match policy")
            _atomic_private_json(self.failure_path, failure_document)
            previous = str(state["current_state"])
            state.update(
                {
                    "previous_state": previous if target != previous else state["previous_state"],
                    "current_state": target,
                    "failure_class": failure_class,
                    "failure_count_by_class": counts,
                    "heartbeat_at": _now(),
                    "approved_next_action": None,
                }
            )
            if clear_active:
                state.update({"active_gate": None, "active_run_id": None, "active_command": None, "active_pid": None})
            return self._commit(
                state,
                "failure_classified",
                {
                    "failure_class": failure_class,
                    "owning_component": failure_document["owning_component"],
                    "shared_or_case_specific": failure_document["shared_or_case_specific"],
                    "target_state": target,
                },
            )

    def approve(self) -> dict[str, object]:
        with self._lock():
            state = self._state()
            self._verify_event_chain(state)
            decision = self._verify_decision(state, permit_audit_update=True)
            audit = decision.get("audit")
            if not isinstance(audit, dict) or audit.get("status") != "PASS":
                raise ExecutionControlError("controller audit PASS is absent")
            if state["current_state"] != "AWAITING_CONTROLLER_AUDIT":
                raise ExecutionControlError("controller audit can only be approved at the audit gate")
            completed = list(cast(list[str], state["completed_gates"]))
            if "controller_audit" not in completed:
                completed.append("controller_audit")
            state.update(
                {
                    "controller_decision_digest": _file_digest(self.decision_path),
                    "completed_gates": completed,
                    "approved_next_action": "candidate_review",
                    "heartbeat_at": _now(),
                }
            )
            return self._commit(state, "controller_audit_approved", {"audit_digest": _digest(audit)})

    def verify(self, action: str) -> dict[str, object]:
        with self._lock():
            state = self._state()
            self._verify_static(state)
            current = str(state["current_state"])
            completed = set(cast(list[str], state["completed_gates"]))
            if action == "model_runner":
                if current not in {"MODEL_READINESS", "MODEL_PREFLIGHT", "GENERALIZATION_EVAL"}:
                    raise ExecutionControlError("model runner is not allowed in the current state")
            elif action == "generalization_runner":
                if current != "GENERALIZATION_EVAL":
                    raise ExecutionControlError("generalization runner is not allowed in the current state")
            elif action == "acceptance_runner":
                if current != "GENERALIZATION_EVAL" or state["governance_version"] != GOVERNANCE_VERSION:
                    raise ExecutionControlError("formal acceptance runner is not authorized")
            elif action == "evidence_finalizer":
                if current not in {"GENERALIZATION_EVAL", "INDEPENDENT_AUDIT"}:
                    raise ExecutionControlError("evidence finalizer is not allowed in the current state")
            elif action == "ci":
                if current != "CI_READY" or not {
                    "acceptance_finalized",
                    "product_review",
                    "engineering_review",
                } <= completed:
                    raise ExecutionControlError("CI is not authorized")
            elif action == "deploy":
                if current != "DEPLOY_READY" or not {"ci_success", "backup_restore"} <= completed:
                    raise ExecutionControlError("deployment is not authorized")
            else:
                raise ExecutionControlError("unknown execution-control action")
            return state


def verify_runtime_action(
    action: str,
    *,
    repository: Path | None = None,
    runtime_root: Path = DEFAULT_RUNTIME_ROOT,
) -> dict[str, object]:
    return ExecutionControl(repository or Path.cwd(), runtime_root).verify(action)


def run_controlled_command(
    control: ExecutionControl,
    *,
    gate: str,
    command: list[str],
    run_id: str | None,
    evidence_path: str | None,
    heartbeat_seconds: float = 45.0,
) -> int:
    """Run one command with an append-only start/heartbeat/finish trail."""

    if not command:
        raise ExecutionControlError("controlled command is empty")
    process = subprocess.Popen(command, cwd=control.repository)
    control.begin(gate, " ".join(command), run_id, process.pid)
    try:
        while True:
            try:
                exit_code = process.wait(timeout=heartbeat_seconds)
                break
            except subprocess.TimeoutExpired:
                control.heartbeat()
    except BaseException:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        raise
    if exit_code == 0:
        control.complete(gate, evidence_path)
    else:
        control.observe_command_exit(exit_code)
    return exit_code


def _print_state(state: Mapping[str, object]) -> None:
    print(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Control TENANT-01 delivery execution gates.")
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT)
    parser.add_argument("--protected-path", type=Path, default=DEFAULT_PROTECTED_PATH)
    commands = parser.add_subparsers(dest="command", required=True)
    initialize = commands.add_parser("init")
    initialize.add_argument("--decision-source", type=Path, required=True)
    initialize.add_argument("--executor-id", required=True)
    commands.add_parser("status")
    history = commands.add_parser("record-history")
    history.add_argument("--summary-file", type=Path, required=True)
    ruling = commands.add_parser("adopt-ruling")
    ruling.add_argument("--decision-source", type=Path, required=True)
    begin = commands.add_parser("begin")
    begin.add_argument("--gate", required=True)
    begin.add_argument("--controlled-command", required=True)
    begin.add_argument("--run-id")
    begin.add_argument("--pid", type=int, default=os.getpid())
    commands.add_parser("heartbeat")
    complete = commands.add_parser("complete")
    complete.add_argument("--gate", required=True)
    complete.add_argument("--evidence-path")
    command_exit = commands.add_parser("command-exit")
    command_exit.add_argument("--exit-code", type=int, required=True)
    controlled = commands.add_parser("run")
    controlled.add_argument("--gate", required=True)
    controlled.add_argument("--run-id")
    controlled.add_argument("--evidence-path")
    controlled.add_argument("--heartbeat-seconds", type=float, default=45.0)
    controlled.add_argument("controlled_command", nargs=argparse.REMAINDER)
    for name in ("classify", "fail"):
        failure = commands.add_parser(name)
        failure.add_argument("--failure-file", type=Path, required=True)
    transition = commands.add_parser("transition")
    transition.add_argument("--expected-state", choices=sorted(STATES), required=True)
    transition.add_argument("--expected-head", required=True)
    transition.add_argument("--contract-digest", required=True)
    transition.add_argument("--to", choices=sorted(STATES), required=True)
    commands.add_parser("approve")
    acceptance_begin = commands.add_parser("acceptance-begin")
    acceptance_begin.add_argument("--candidate-sha", required=True)
    acceptance_begin.add_argument("--suite-id", required=True)
    acceptance_begin.add_argument("--acceptance-run-id", required=True)
    acceptance_begin.add_argument("--config-digest", required=True)
    acceptance_begin.add_argument("--sample-id", action="append", required=True)
    acceptance_begin.add_argument("--resume-unreceived", action="store_true")
    acceptance_record = commands.add_parser("acceptance-record")
    acceptance_record.add_argument("--candidate-sha", required=True)
    acceptance_record.add_argument("--suite-id", required=True)
    acceptance_record.add_argument("--acceptance-run-id", required=True)
    acceptance_record.add_argument("--sample-id", required=True)
    acceptance_record.add_argument("--provider-response-received", choices=("true", "false"), required=True)
    acceptance_record.add_argument("--request-count", type=int, required=True)
    acceptance_record.add_argument("--artifact-digest")
    acceptance_record.add_argument("--final-status", required=True)
    acceptance_complete = commands.add_parser("acceptance-complete")
    acceptance_complete.add_argument("--candidate-sha", required=True)
    acceptance_complete.add_argument("--suite-id", required=True)
    acceptance_complete.add_argument("--acceptance-run-id", required=True)
    acceptance_review = commands.add_parser("acceptance-review")
    acceptance_review.add_argument("--candidate-sha", required=True)
    acceptance_review.add_argument("--suite-id", required=True)
    acceptance_review.add_argument("--acceptance-run-id", required=True)
    acceptance_review.add_argument("--sample-id", required=True)
    acceptance_review.add_argument("--hard-boundary", choices=("PASS", "FAIL"), required=True)
    acceptance_review.add_argument("--structure-complete", choices=("PASS", "FAIL"), required=True)
    acceptance_review.add_argument("--product-usable", choices=("PASS", "FAIL"), required=True)
    acceptance_review.add_argument("--review-digest", required=True)
    verify = commands.add_parser("verify")
    verify.add_argument(
        "--action",
        choices=(
            "model_runner",
            "generalization_runner",
            "acceptance_runner",
            "evidence_finalizer",
            "ci",
            "deploy",
        ),
        required=True,
    )
    return parser


def main() -> None:
    os.umask(0o077)
    arguments = _parser().parse_args()
    control = ExecutionControl(arguments.repository, arguments.runtime_root, arguments.protected_path)
    command = str(arguments.command)
    if command == "init":
        state = control.initialize(arguments.decision_source, str(arguments.executor_id))
    elif command == "status":
        state = control.status()
    elif command == "record-history":
        state = control.record_history(arguments.summary_file)
    elif command == "adopt-ruling":
        state = control.adopt_ruling(arguments.decision_source)
    elif command == "begin":
        state = control.begin(str(arguments.gate), str(arguments.controlled_command), arguments.run_id, int(arguments.pid))
    elif command == "heartbeat":
        state = control.heartbeat()
    elif command == "complete":
        state = control.complete(str(arguments.gate), arguments.evidence_path)
    elif command == "command-exit":
        state = control.observe_command_exit(int(arguments.exit_code))
    elif command == "run":
        controlled_command = list(arguments.controlled_command)
        if controlled_command[:1] == ["--"]:
            controlled_command = controlled_command[1:]
        exit_code = run_controlled_command(
            control,
            gate=str(arguments.gate),
            command=controlled_command,
            run_id=arguments.run_id,
            evidence_path=arguments.evidence_path,
            heartbeat_seconds=float(arguments.heartbeat_seconds),
        )
        raise SystemExit(exit_code)
    elif command in {"classify", "fail"}:
        failure = _read_object(arguments.failure_file)
        state = control.classify(failure, clear_active=command == "fail")
    elif command == "transition":
        state = control.transition(
            str(arguments.expected_state),
            str(arguments.expected_head),
            str(arguments.contract_digest),
            str(arguments.to),
        )
    elif command == "approve":
        state = control.approve()
    elif command == "acceptance-begin":
        state = control.begin_acceptance_suite(
            candidate_sha=str(arguments.candidate_sha),
            suite_id=str(arguments.suite_id),
            acceptance_run_id=str(arguments.acceptance_run_id),
            config_digest=str(arguments.config_digest),
            sample_ids=tuple(str(value) for value in arguments.sample_id),
            allow_resume=bool(arguments.resume_unreceived),
        )
    elif command == "acceptance-record":
        state = control.record_acceptance_sample(
            candidate_sha=str(arguments.candidate_sha),
            suite_id=str(arguments.suite_id),
            acceptance_run_id=str(arguments.acceptance_run_id),
            sample_id=str(arguments.sample_id),
            provider_response_received=arguments.provider_response_received == "true",
            request_count=int(arguments.request_count),
            artifact_digest=arguments.artifact_digest,
            final_status=str(arguments.final_status),
        )
    elif command == "acceptance-complete":
        state = control.complete_acceptance_suite(
            candidate_sha=str(arguments.candidate_sha),
            suite_id=str(arguments.suite_id),
            acceptance_run_id=str(arguments.acceptance_run_id),
        )
    elif command == "acceptance-review":
        state = control.review_acceptance_sample(
            candidate_sha=str(arguments.candidate_sha),
            suite_id=str(arguments.suite_id),
            acceptance_run_id=str(arguments.acceptance_run_id),
            sample_id=str(arguments.sample_id),
            hard_boundary=str(arguments.hard_boundary),
            structure_complete=str(arguments.structure_complete),
            product_usable=str(arguments.product_usable),
            review_digest=str(arguments.review_digest),
        )
    elif command == "verify":
        state = control.verify(str(arguments.action))
    else:
        raise AssertionError("unreachable execution-control command")
    _print_state(state)


if __name__ == "__main__":
    try:
        main()
    except (ExecutionControlError, subprocess.CalledProcessError, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"execution-control refused: {error}", file=sys.stderr)
        raise SystemExit(2) from error
