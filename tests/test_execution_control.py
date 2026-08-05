from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest

from src.tool.execution_control import (
    ACCEPTANCE_CHECKPOINT_VERSION,
    FORMAL_USABILITY_REWORK_ID,
    ExecutionControl,
    ExecutionControlError,
    run_controlled_command,
)


@dataclass(frozen=True)
class _ControlFixture:
    repository: Path
    runtime_root: Path
    control: ExecutionControl
    initial_head: str
    contract_digest: str


def _git(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        ("git", *arguments),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _write_private_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    path.chmod(0o600)


@pytest.fixture()
def control_fixture(tmp_path: Path) -> _ControlFixture:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init", "-b", "main")
    _git(repository, "config", "user.name", "Execution Control Test")
    _git(repository, "config", "user.email", "execution-control@example.invalid")
    protected = repository / "docs" / "项目记忆.md"
    protected.parent.mkdir()
    protected.write_text("已提交项目记忆\n", encoding="utf-8")
    (repository / ".gitignore").write_text("var/execution-control/\n", encoding="utf-8")
    _git(repository, "add", ".gitignore", "docs/项目记忆.md")
    _git(repository, "commit", "-m", "fixture")
    initial_head = _git(repository, "rev-parse", "HEAD")
    _git(repository, "update-ref", "refs/remotes/origin/main", initial_head)
    protected.write_text("已提交项目记忆\n用户受保护修改\n", encoding="utf-8")
    decision_source = tmp_path / "decision-source.json"
    decision = {
        "decision_version": "tenant01-controller-decision-v1",
        "milestone": "TENANT-01",
        "objective": {"name": "首租户生产就绪", "result": "进入主控抽检"},
        "contract": {
            "machine_hard_gate": "26/26",
            "structure_gate": "26/26",
            "first_draft_usable_minimum": "23/26",
            "generalization_set_kind": "frozen_regression",
        },
        "audit": {"status": "PENDING"},
    }
    _write_private_json(decision_source, decision)
    runtime_root = tmp_path / "execution-control"
    control = ExecutionControl(repository, runtime_root)
    state = control.initialize(decision_source, "test-executor")
    return _ControlFixture(
        repository=repository,
        runtime_root=runtime_root,
        control=control,
        initial_head=initial_head,
        contract_digest=str(state["contract_digest"]),
    )


def _transition(fixture: _ControlFixture, expected: str, target: str) -> dict[str, object]:
    state = fixture.control.status()
    assert state["current_state"] == expected
    return fixture.control.transition(expected, str(state["head_sha"]), fixture.contract_digest, target)


def _reach_model_preflight(fixture: _ControlFixture) -> None:
    _transition(fixture, "BOOTSTRAP", "CONTRACT_FROZEN")
    _transition(fixture, "CONTRACT_FROZEN", "STRUCTURAL_IMPLEMENTATION")
    _transition(fixture, "STRUCTURAL_IMPLEMENTATION", "DETERMINISTIC_GATE")
    _transition(fixture, "DETERMINISTIC_GATE", "MODEL_PREFLIGHT")


def _reach_generalization(fixture: _ControlFixture) -> None:
    _transition(fixture, "BOOTSTRAP", "CONTRACT_FROZEN")
    _transition(fixture, "CONTRACT_FROZEN", "STRUCTURAL_IMPLEMENTATION")
    _transition(fixture, "STRUCTURAL_IMPLEMENTATION", "DETERMINISTIC_GATE")
    _transition(fixture, "DETERMINISTIC_GATE", "MODEL_READINESS")
    _transition(fixture, "MODEL_READINESS", "GENERALIZATION_EVAL")


def _reach_review(fixture: _ControlFixture) -> None:
    _reach_generalization(fixture)
    _transition(fixture, "GENERALIZATION_EVAL", "INDEPENDENT_AUDIT")
    for gate in ("acceptance_finalized", "product_review", "engineering_review"):
        fixture.control.begin(gate, f"complete {gate}", None, os.getpid())
        fixture.control.complete(gate, f"evidence/{gate}.json")
    _transition(fixture, "INDEPENDENT_AUDIT", "CANDIDATE_REVIEW")
    _transition(fixture, "CANDIDATE_REVIEW", "CI_READY")
    fixture.control.begin("ci_success", "authoritative CI", None, os.getpid())
    fixture.control.complete("ci_success", "evidence/ci.json")
    _transition(fixture, "CI_READY", "DEPLOY_READY")
    for gate in (
        "backup_restore",
        "production_deploy",
        "rollback_roundtrip",
        "synthetic_cleanup",
    ):
        fixture.control.begin(gate, f"complete {gate}", None, os.getpid())
        fixture.control.complete(gate, f"evidence/{gate}.json")
    _transition(fixture, "DEPLOY_READY", "REVIEW")


def _failure(failure_class: str, allowed_next_state: str) -> dict[str, object]:
    return {
        "failure_class": failure_class,
        "expected_invariant": "冻结合同保持",
        "observed_evidence": "合成反证",
        "affected_scope": "execution-control-test",
        "owning_component": "execution_control",
        "shared_or_case_specific": "shared",
        "product_contract_change_required": False,
        "why_not_case_patch": "验证共享执行门",
        "allowed_next_state": allowed_next_state,
    }


def _acceptance_checkpoint(
    fixture: _ControlFixture,
    *,
    candidate_sha: str,
    suite_id: str,
    acceptance_run_id: str,
    config_digest: str,
    sample_ids: tuple[str, ...],
) -> Path:
    root = fixture.runtime_root.parent / "private-evidence"
    root.mkdir(mode=0o700)
    root.chmod(0o700)
    checkpoint = root / "acceptance-checkpoint.json"
    _write_private_json(
        checkpoint,
        {
            "checkpoint_version": ACCEPTANCE_CHECKPOINT_VERSION,
            "candidate_sha": candidate_sha,
            "suite_id": suite_id,
            "acceptance_run_id": acceptance_run_id,
            "config_digest": config_digest,
            "sample_ids": list(sample_ids),
            "series_id": "adfd1032-6d2f-4bb1-b966-2bd04bff1271",
        },
    )
    return checkpoint


def _start_interrupted_acceptance(
    fixture: _ControlFixture,
    *,
    pid: int = 999_999_999,
) -> tuple[str, str, str, tuple[str, ...], Path]:
    _reach_generalization(fixture)
    candidate = fixture.initial_head
    suite_id = "tenant01-golden-11-v1"
    acceptance_run_id = "acceptance-interrupted"
    config_digest = "b" * 64
    sample_ids = ("P1", "P2")
    fixture.control.begin(
        "acceptance-golden-11",
        "generate the frozen acceptance suite once",
        acceptance_run_id,
        pid,
    )
    fixture.control.begin_acceptance_suite(
        candidate_sha=candidate,
        suite_id=suite_id,
        acceptance_run_id=acceptance_run_id,
        config_digest=config_digest,
        sample_ids=sample_ids,
    )
    checkpoint = _acceptance_checkpoint(
        fixture,
        candidate_sha=candidate,
        suite_id=suite_id,
        acceptance_run_id=acceptance_run_id,
        config_digest=config_digest,
        sample_ids=sample_ids,
    )
    return candidate, suite_id, acceptance_run_id, sample_ids, checkpoint


def test_execution_control_initializes_private_non_pass_projection(control_fixture: _ControlFixture) -> None:
    state = control_fixture.control.status()
    status = json.loads((control_fixture.runtime_root / "status.json").read_text(encoding="utf-8"))
    decision = json.loads((control_fixture.runtime_root / "controller-decision.json").read_text(encoding="utf-8"))
    assert state["current_state"] == "BOOTSTRAP"
    assert state["completed_gates"] == []
    assert status["current_state"] == "BOOTSTRAP"
    assert decision["audit"] == {"status": "PENDING"}
    assert (control_fixture.runtime_root.stat().st_mode & 0o777) == 0o700
    for name in ("state.json", "status.json", "controller-decision.json", "events.jsonl"):
        assert ((control_fixture.runtime_root / name).stat().st_mode & 0o777) == 0o600


def test_historical_diagnostics_are_recorded_without_attempt_count(control_fixture: _ControlFixture) -> None:
    summary_path = control_fixture.runtime_root / "historical-diagnostics.json"
    _write_private_json(
        summary_path,
        {
            "summary_version": "tenant01-historical-diagnostics-v1",
            "counts_as_current_attempt": False,
            "diagnostic_candidates": ["0fa0636", "e546602"],
            "golden_diagnostic": {"passed": 752, "failed": 9, "skipped": 2},
        },
    )
    state = control_fixture.control.record_history(summary_path)
    counts = cast(dict[str, int], state["failure_count_by_class"])
    assert counts and all(value == 0 for value in counts.values())
    assert str(summary_path) in cast(list[str], state["evidence_paths"])


def test_model_runner_refuses_wrong_state_and_accepts_model_preflight(control_fixture: _ControlFixture) -> None:
    with pytest.raises(ExecutionControlError, match="not allowed"):
        control_fixture.control.verify("model_runner")
    _reach_model_preflight(control_fixture)
    assert control_fixture.control.verify("model_runner")["current_state"] == "MODEL_PREFLIGHT"


def test_verify_refuses_head_contract_and_protected_change_drift(
    control_fixture: _ControlFixture,
) -> None:
    _reach_model_preflight(control_fixture)
    (control_fixture.repository / "head-change.txt").write_text("head changed\n", encoding="utf-8")
    _git(control_fixture.repository, "add", "head-change.txt")
    _git(control_fixture.repository, "commit", "-m", "head drift")
    with pytest.raises(ExecutionControlError, match="HEAD differs"):
        control_fixture.control.verify("model_runner")

    second = control_fixture.runtime_root.parent / "second-control"
    decision_source = control_fixture.runtime_root / "controller-decision.json"
    fresh = ExecutionControl(control_fixture.repository, second)
    fresh.initialize(decision_source, "test-executor")
    fixture = _ControlFixture(
        control_fixture.repository,
        second,
        fresh,
        _git(control_fixture.repository, "rev-parse", "HEAD"),
        str(fresh.status()["contract_digest"]),
    )
    _reach_model_preflight(fixture)
    decision = json.loads((second / "controller-decision.json").read_text(encoding="utf-8"))
    decision["contract"]["first_draft_usable_minimum"] = "22/26"
    _write_private_json(second / "controller-decision.json", decision)
    with pytest.raises(ExecutionControlError, match="contract digest drifted"):
        fresh.verify("model_runner")

    third = control_fixture.runtime_root.parent / "third-control"
    source = control_fixture.runtime_root / "controller-decision.json"
    protected = ExecutionControl(control_fixture.repository, third)
    protected.initialize(source, "test-executor")
    third_fixture = _ControlFixture(
        control_fixture.repository,
        third,
        protected,
        _git(control_fixture.repository, "rev-parse", "HEAD"),
        str(protected.status()["contract_digest"]),
    )
    _reach_model_preflight(third_fixture)
    with (control_fixture.repository / "docs" / "项目记忆.md").open("a", encoding="utf-8") as handle:
        handle.write("unexpected protected drift\n")
    with pytest.raises(ExecutionControlError, match="protected user change digest drifted"):
        protected.verify("model_runner")


def test_quality_variance_and_historical_provider_semantics_do_not_block_acceptance(
    control_fixture: _ControlFixture,
) -> None:
    _reach_model_preflight(control_fixture)
    first = control_fixture.control.classify(_failure("provider_semantic_failure", "MODEL_PREFLIGHT"))
    assert first["current_state"] == "MODEL_PREFLIGHT"
    second = control_fixture.control.classify(_failure("provider_semantic_failure", "MODEL_PREFLIGHT"))
    assert second["current_state"] == "MODEL_PREFLIGHT"
    first_quality = control_fixture.control.classify(_failure("product_quality_variance", "MODEL_PREFLIGHT"))
    second_quality = control_fixture.control.classify(_failure("product_quality_variance", "MODEL_PREFLIGHT"))
    counts = cast(dict[str, int], second_quality["failure_count_by_class"])
    assert counts["provider_semantic_failure"] == 2
    assert counts["product_quality_variance"] == 2
    assert first_quality["current_state"] == "MODEL_PREFLIGHT"
    assert control_fixture.control.verify("model_runner")["current_state"] == "MODEL_PREFLIGHT"


def test_candidate_scoped_acceptance_starts_once_and_ignores_historical_diagnostics(
    control_fixture: _ControlFixture,
) -> None:
    summary_path = control_fixture.runtime_root / "historical-diagnostics.json"
    _write_private_json(
        summary_path,
        {
            "summary_version": "tenant01-historical-diagnostics-v1",
            "counts_as_current_attempt": False,
            "diagnostic_candidates": ["old-tricard-1", "old-tricard-2"],
            "golden_diagnostic": {"provider_semantic_failure": 2},
        },
    )
    control_fixture.control.record_history(summary_path)
    _reach_generalization(control_fixture)
    candidate = control_fixture.initial_head
    started = control_fixture.control.begin_acceptance_suite(
        candidate_sha=candidate,
        suite_id="tenant01-final-26",
        acceptance_run_id="acceptance-20260803-final",
        config_digest="a" * 64,
        sample_ids=("P1", "P2", "daily_complaint"),
    )
    runs = cast(dict[str, dict[str, object]], started["acceptance_runs"])
    assert len(runs) == 1
    with pytest.raises(ExecutionControlError, match="already started"):
        control_fixture.control.begin_acceptance_suite(
            candidate_sha=candidate,
            suite_id="tenant01-final-26",
            acceptance_run_id="acceptance-20260803-final",
            config_digest="a" * 64,
            sample_ids=("P1", "P2", "daily_complaint"),
        )


def test_acceptance_only_resumes_unreceived_transport_samples(control_fixture: _ControlFixture) -> None:
    _reach_generalization(control_fixture)
    candidate = control_fixture.initial_head
    control_fixture.control.begin_acceptance_suite(
        candidate_sha=candidate,
        suite_id="tenant01-golden-11",
        acceptance_run_id="acceptance-final",
        config_digest="b" * 64,
        # Deliberately non-lexical: private JSON is serialized with sorted keys,
        # while suite identity is exact membership rather than object key order.
        sample_ids=("P2", "P1"),
    )
    control_fixture.control.record_acceptance_sample(
        candidate_sha=candidate,
        suite_id="tenant01-golden-11",
        acceptance_run_id="acceptance-final",
        sample_id="P1",
        provider_response_received=False,
        request_count=0,
        artifact_digest=None,
        final_status="transport_failed_no_response",
    )
    resumed = control_fixture.control.begin_acceptance_suite(
        candidate_sha=candidate,
        suite_id="tenant01-golden-11",
        acceptance_run_id="acceptance-final",
        config_digest="b" * 64,
        sample_ids=("P2", "P1"),
        allow_resume=True,
    )
    assert resumed["current_state"] == "GENERALIZATION_EVAL"
    control_fixture.control.record_acceptance_sample(
        candidate_sha=candidate,
        suite_id="tenant01-golden-11",
        acceptance_run_id="acceptance-final",
        sample_id="P1",
        provider_response_received=True,
        request_count=2,
        artifact_digest="c" * 64,
        final_status="artifact_ready",
    )
    with pytest.raises(ExecutionControlError, match="terminal result"):
        control_fixture.control.record_acceptance_sample(
            candidate_sha=candidate,
            suite_id="tenant01-golden-11",
            acceptance_run_id="acceptance-final",
            sample_id="P1",
            provider_response_received=True,
            request_count=2,
            artifact_digest="c" * 64,
            final_status="artifact_ready",
        )


def test_interrupted_pristine_acceptance_recovery_is_bound_and_consumed_once(
    control_fixture: _ControlFixture,
) -> None:
    candidate, suite_id, run_id, sample_ids, checkpoint = _start_interrupted_acceptance(control_fixture)
    before = (control_fixture.runtime_root / "events.jsonl").read_bytes()
    ledger_before = cast(
        dict[str, object],
        control_fixture.control.status()["acceptance_runs"],
    )

    recovered = control_fixture.control.recover_interrupted_acceptance(
        candidate_sha=candidate,
        suite_id=suite_id,
        acceptance_run_id=run_id,
        config_digest="b" * 64,
        sample_ids=sample_ids,
        checkpoint_path=checkpoint,
        expected_pid=999_999_999,
        expected_gate="acceptance-golden-11",
    )

    assert recovered["active_pid"] is None
    assert recovered["active_command"] is None
    assert recovered["acceptance_runs"] == ledger_before
    assert (control_fixture.runtime_root / "events.jsonl").read_bytes().startswith(before)
    resumed = control_fixture.control.begin_acceptance_suite(
        candidate_sha=candidate,
        suite_id=suite_id,
        acceptance_run_id=run_id,
        config_digest="b" * 64,
        sample_ids=sample_ids,
        allow_resume=True,
        resume_checkpoint_path=checkpoint,
    )
    assert (
        control_fixture.control.acceptance_pending_samples(
            candidate_sha=candidate,
            suite_id=suite_id,
            acceptance_run_id=run_id,
        )
        == sample_ids
    )
    events = (control_fixture.runtime_root / "events.jsonl").read_text(encoding="utf-8")
    assert '"provider_attempt_fabricated":false' in events
    assert '"history_rewritten":false' in events
    assert resumed["acceptance_runs"] == ledger_before
    with pytest.raises(ExecutionControlError, match="no unreceived transport failure"):
        control_fixture.control.begin_acceptance_suite(
            candidate_sha=candidate,
            suite_id=suite_id,
            acceptance_run_id=run_id,
            config_digest="b" * 64,
            sample_ids=sample_ids,
            allow_resume=True,
            resume_checkpoint_path=checkpoint,
        )


def test_checkpoint_alone_cannot_resume_all_pending_acceptance(
    control_fixture: _ControlFixture,
) -> None:
    candidate, suite_id, run_id, sample_ids, checkpoint = _start_interrupted_acceptance(control_fixture)
    with pytest.raises(ExecutionControlError, match="no unreceived transport failure"):
        control_fixture.control.begin_acceptance_suite(
            candidate_sha=candidate,
            suite_id=suite_id,
            acceptance_run_id=run_id,
            config_digest="b" * 64,
            sample_ids=sample_ids,
            allow_resume=True,
            resume_checkpoint_path=checkpoint,
        )


def test_interrupted_acceptance_recovery_refuses_live_pid(control_fixture: _ControlFixture) -> None:
    candidate, suite_id, run_id, sample_ids, checkpoint = _start_interrupted_acceptance(
        control_fixture,
        pid=os.getpid(),
    )
    with pytest.raises(ExecutionControlError, match="still alive"):
        control_fixture.control.recover_interrupted_acceptance(
            candidate_sha=candidate,
            suite_id=suite_id,
            acceptance_run_id=run_id,
            config_digest="b" * 64,
            sample_ids=sample_ids,
            checkpoint_path=checkpoint,
            expected_pid=os.getpid(),
            expected_gate="acceptance-golden-11",
        )


@pytest.mark.parametrize(
    "mutation",
    ("candidate", "run", "config", "checkpoint", "duplicate_sample"),
)
def test_interrupted_acceptance_recovery_mutations_fail_closed(
    control_fixture: _ControlFixture,
    mutation: str,
) -> None:
    candidate, suite_id, run_id, sample_ids, checkpoint = _start_interrupted_acceptance(control_fixture)
    arguments: dict[str, object] = {
        "candidate_sha": candidate,
        "suite_id": suite_id,
        "acceptance_run_id": run_id,
        "config_digest": "b" * 64,
        "sample_ids": sample_ids,
        "checkpoint_path": checkpoint,
        "expected_pid": 999_999_999,
        "expected_gate": "acceptance-golden-11",
    }
    if mutation == "candidate":
        arguments["candidate_sha"] = "f" * 40
    elif mutation == "run":
        arguments["acceptance_run_id"] = "another-acceptance-run"
    elif mutation == "config":
        arguments["config_digest"] = "c" * 64
    elif mutation == "checkpoint":
        document = json.loads(checkpoint.read_text(encoding="utf-8"))
        document["unexpected"] = "tampered"
        _write_private_json(checkpoint, document)
    elif mutation == "duplicate_sample":
        arguments["sample_ids"] = ("P1", "P1")
    with pytest.raises(ExecutionControlError):
        control_fixture.control.recover_interrupted_acceptance(**arguments)  # type: ignore[arg-type]
    state = control_fixture.control.status()
    assert state["active_pid"] == 999_999_999
    assert state["active_gate"] == "acceptance-golden-11"


def test_recovered_pending_samples_never_replay_terminal_provider_responses(
    control_fixture: _ControlFixture,
) -> None:
    candidate, suite_id, run_id, sample_ids, checkpoint = _start_interrupted_acceptance(control_fixture)
    control_fixture.control.record_acceptance_sample(
        candidate_sha=candidate,
        suite_id=suite_id,
        acceptance_run_id=run_id,
        sample_id="P1",
        provider_response_received=True,
        request_count=1,
        artifact_digest="c" * 64,
        final_status="artifact_ready",
    )
    control_fixture.control.recover_interrupted_acceptance(
        candidate_sha=candidate,
        suite_id=suite_id,
        acceptance_run_id=run_id,
        config_digest="b" * 64,
        sample_ids=sample_ids,
        checkpoint_path=checkpoint,
        expected_pid=999_999_999,
        expected_gate="acceptance-golden-11",
    )
    control_fixture.control.begin_acceptance_suite(
        candidate_sha=candidate,
        suite_id=suite_id,
        acceptance_run_id=run_id,
        config_digest="b" * 64,
        sample_ids=sample_ids,
        allow_resume=True,
        resume_checkpoint_path=checkpoint,
    )
    assert control_fixture.control.acceptance_pending_samples(
        candidate_sha=candidate,
        suite_id=suite_id,
        acceptance_run_id=run_id,
    ) == ("P2",)
    with pytest.raises(ExecutionControlError, match="terminal result"):
        control_fixture.control.record_acceptance_sample(
            candidate_sha=candidate,
            suite_id=suite_id,
            acceptance_run_id=run_id,
            sample_id="P1",
            provider_response_received=True,
            request_count=1,
            artifact_digest="d" * 64,
            final_status="artifact_ready",
        )


def test_hard_semantic_and_contract_failures_are_the_only_controller_or_safe_stops(
    control_fixture: _ControlFixture,
) -> None:
    _reach_model_preflight(control_fixture)
    implementation = control_fixture.control.classify(_failure("implementation_defect", "NEEDS_DIAGNOSIS"))
    assert implementation["current_state"] == "NEEDS_DIAGNOSIS"

    second_root = control_fixture.runtime_root.parent / "hard-boundary-control"
    hard = ExecutionControl(control_fixture.repository, second_root)
    hard.initialize(control_fixture.runtime_root / "controller-decision.json", "test-executor")
    hard_fixture = _ControlFixture(
        control_fixture.repository,
        second_root,
        hard,
        control_fixture.initial_head,
        str(hard.status()["contract_digest"]),
    )
    _reach_model_preflight(hard_fixture)
    failed = hard.classify(_failure("hard_semantic_boundary_failure", "FAILED_SAFE"))
    assert failed["current_state"] == "FAILED_SAFE"

    third_root = control_fixture.runtime_root.parent / "contract-control"
    contract = ExecutionControl(control_fixture.repository, third_root)
    contract.initialize(control_fixture.runtime_root / "controller-decision.json", "test-executor")
    contract_fixture = _ControlFixture(
        control_fixture.repository,
        third_root,
        contract,
        control_fixture.initial_head,
        str(contract.status()["contract_digest"]),
    )
    _reach_model_preflight(contract_fixture)
    ruling = contract.classify(_failure("product_contract_conflict", "NEEDS_CONTROLLER_RULING"))
    assert ruling["current_state"] == "NEEDS_CONTROLLER_RULING"


def test_ci_and_deploy_require_controller_audit_and_recorded_gates(control_fixture: _ControlFixture) -> None:
    _reach_model_preflight(control_fixture)
    _transition(control_fixture, "MODEL_PREFLIGHT", "GENERALIZATION_EVAL")
    _transition(control_fixture, "GENERALIZATION_EVAL", "AWAITING_CONTROLLER_AUDIT")
    with pytest.raises(ExecutionControlError, match="CI is not authorized"):
        control_fixture.control.verify("ci")

    decision_path = control_fixture.runtime_root / "controller-decision.json"
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    decision["audit"] = {"status": "PASS", "evidence_digest": "a" * 64}
    _write_private_json(decision_path, decision)
    approved = control_fixture.control.approve()
    assert approved["approved_next_action"] == "candidate_review"
    _transition(control_fixture, "AWAITING_CONTROLLER_AUDIT", "CANDIDATE_REVIEW")
    for gate in ("acceptance_finalized", "product_review", "engineering_review"):
        control_fixture.control.begin(gate, f"review {gate}", None, os.getpid())
        control_fixture.control.complete(gate, f"evidence/{gate}.json")
    _transition(control_fixture, "CANDIDATE_REVIEW", "CI_READY")
    assert control_fixture.control.verify("ci")["current_state"] == "CI_READY"
    with pytest.raises(ExecutionControlError, match="deployment is not authorized"):
        control_fixture.control.verify("deploy")


def test_deleted_or_rewritten_event_history_fails_closed(control_fixture: _ControlFixture) -> None:
    events_path = control_fixture.runtime_root / "events.jsonl"
    events = events_path.read_text(encoding="utf-8").splitlines()
    assert len(events) == 1
    events_path.write_text("", encoding="utf-8")
    events_path.chmod(0o600)
    with pytest.raises(ExecutionControlError, match="deleted or rewritten"):
        control_fixture.control.status()


def test_controlled_command_freezes_current_wip_and_records_heartbeats(
    control_fixture: _ControlFixture,
) -> None:
    (control_fixture.repository / "wip.txt").write_text("forward WIP\n", encoding="utf-8")
    exit_code = run_controlled_command(
        control_fixture.control,
        gate="targeted-tests",
        command=["sh", "-c", "sleep 0.15"],
        run_id="targeted-tests-1",
        evidence_path="evidence/targeted-tests.txt",
        heartbeat_seconds=0.01,
    )
    assert exit_code == 0
    state = control_fixture.control.status()
    assert "targeted-tests" in cast(list[str], state["completed_gates"])
    events = (control_fixture.runtime_root / "events.jsonl").read_text(encoding="utf-8")
    assert '"event_type":"heartbeat"' in events


def test_failed_controlled_command_requires_explicit_classification(
    control_fixture: _ControlFixture,
) -> None:
    exit_code = run_controlled_command(
        control_fixture.control,
        gate="failing-test",
        command=["sh", "-c", "exit 7"],
        run_id=None,
        evidence_path=None,
    )
    assert exit_code == 7
    state = control_fixture.control.status()
    assert state["active_gate"] == "failing-test"
    events = (control_fixture.runtime_root / "events.jsonl").read_text(encoding="utf-8")
    assert '"classification_required":true' in events
    with pytest.raises(ExecutionControlError, match="must use fail"):
        control_fixture.control.classify(_failure("implementation_defect", "NEEDS_DIAGNOSIS"))
    classified = control_fixture.control.classify(
        _failure("implementation_defect", "NEEDS_DIAGNOSIS"),
        clear_active=True,
    )
    assert classified["current_state"] == "NEEDS_DIAGNOSIS"
    assert classified["active_command"] is None


def test_structural_environment_restriction_recovers_without_rewriting_history(
    control_fixture: _ControlFixture,
) -> None:
    _transition(control_fixture, "BOOTSTRAP", "CONTRACT_FROZEN")
    _transition(control_fixture, "CONTRACT_FROZEN", "STRUCTURAL_IMPLEMENTATION")
    restricted = control_fixture.control.classify(_failure("environment_restriction", "ENVIRONMENT_RESTRICTED"))
    assert restricted["current_state"] == "ENVIRONMENT_RESTRICTED"
    assert restricted["previous_state"] == "STRUCTURAL_IMPLEMENTATION"
    before = (control_fixture.runtime_root / "events.jsonl").read_bytes()

    with pytest.raises(ExecutionControlError, match="is not allowed"):
        control_fixture.control.transition(
            "ENVIRONMENT_RESTRICTED",
            str(restricted["head_sha"]),
            control_fixture.contract_digest,
            "REVIEW",
        )

    recovered = _transition(control_fixture, "ENVIRONMENT_RESTRICTED", "STRUCTURAL_IMPLEMENTATION")
    assert recovered["previous_state"] == "ENVIRONMENT_RESTRICTED"
    assert recovered["failure_class"] is None
    assert (control_fixture.runtime_root / "events.jsonl").read_bytes().startswith(before)


def test_final_controller_ruling_updates_contract_without_rewriting_history(
    control_fixture: _ControlFixture,
) -> None:
    _transition(control_fixture, "BOOTSTRAP", "CONTRACT_FROZEN")
    _transition(control_fixture, "CONTRACT_FROZEN", "STRUCTURAL_IMPLEMENTATION")
    before = (control_fixture.runtime_root / "events.jsonl").read_bytes()
    source = control_fixture.runtime_root / "final-ruling.json"
    _write_private_json(
        source,
        {
            "decision_version": "TENANT01-CONTROLLER-RULING-20260803-FINAL",
            "milestone": "TENANT-01",
            "objective": {"terminal_state": "REVIEW"},
            "contract": {
                "ruling_id": "TENANT01-CONTROLLER-RULING-20260803-FINAL",
                "machine_hard_gate": "26/26",
                "structure_complete": "26/26",
                "human_high_risk_boundary_gate": "26/26",
                "first_draft_product_usable_minimum": "23/26",
            },
            "audit": {"status": "PREAUTHORIZED"},
        },
    )
    adopted = control_fixture.control.adopt_ruling(source)
    assert adopted["governance_version"] == "candidate-scoped-acceptance-v2"
    assert adopted["contract_digest"] != control_fixture.contract_digest
    assert (control_fixture.runtime_root / "events.jsonl").read_bytes().startswith(before)
    assert adopted["event_count"] == len(before.splitlines()) + 1


def test_controller_ruling_recovers_failed_safe_without_erasing_acceptance_history(
    control_fixture: _ControlFixture,
) -> None:
    _reach_model_preflight(control_fixture)
    failed = control_fixture.control.classify(_failure("hard_semantic_boundary_failure", "FAILED_SAFE"))
    assert failed["current_state"] == "FAILED_SAFE"
    historical_key = f"{control_fixture.initial_head}:tenant01-golden-11-v1"
    failed["acceptance_runs"] = {
        historical_key: {
            "candidate_sha": control_fixture.initial_head,
            "suite_id": "tenant01-golden-11-v1",
            "acceptance_run_id": "historical-run",
            "config_digest": "a" * 64,
            "status": "FAILED",
            "started_at": "2026-08-03T00:00:00Z",
            "completed_at": "2026-08-03T00:01:00Z",
            "samples": {
                "coffee": {
                    "attempts": [],
                    "human_review": {},
                    "final_status": "HARD_FAIL",
                }
            },
            "failure_count_by_class": {},
        }
    }
    _write_private_json(control_fixture.runtime_root / "state.json", failed)
    source = control_fixture.runtime_root / "replacement-ruling.json"
    _write_private_json(
        source,
        {
            "decision_version": "TENANT01-CONTROLLER-RULING-20260803-FINAL",
            "milestone": "TENANT-01",
            "objective": {"terminal_state": "REVIEW"},
            "contract": {
                "ruling_id": "TENANT01-CONTROLLER-RULING-20260803-FINAL",
                "user_actuality_expression_policy": "user-actuality-natural-expression-v2",
            },
            "audit": {"status": "PREAUTHORIZED"},
        },
    )

    adopted = control_fixture.control.adopt_ruling(source)

    assert adopted["current_state"] == "STRUCTURAL_IMPLEMENTATION"
    assert adopted["previous_state"] == "FAILED_SAFE"
    assert historical_key in cast(dict[str, object], adopted["acceptance_runs"])
    events = (control_fixture.runtime_root / "events.jsonl").read_text(encoding="utf-8")
    assert "controller_ruling_adopted" in events


def test_domain_elaboration_ruling_recovers_to_shared_repair_and_invalidates_old_gates(
    control_fixture: _ControlFixture,
) -> None:
    _reach_model_preflight(control_fixture)
    control_fixture.control.begin("old_candidate_gate", "old candidate proof", None, os.getpid())
    control_fixture.control.complete("old_candidate_gate", "evidence/old-candidate.json")
    failed = control_fixture.control.classify(
        _failure("hard_semantic_boundary_failure", "FAILED_SAFE")
    )
    assert failed["current_state"] == "FAILED_SAFE"
    failure_before = (control_fixture.runtime_root / "failure.json").read_bytes()
    events_before = (control_fixture.runtime_root / "events.jsonl").read_bytes()
    source = control_fixture.runtime_root / "domain-elaboration-ruling.json"
    _write_private_json(
        source,
        {
            "decision_version": "TENANT01-CONTROLLER-RULING-20260804-DOMAIN-ELABORATION",
            "milestone": "TENANT-01",
            "objective": {"terminal_state": "REVIEW"},
            "contract": {
                "ruling_id": "TENANT01-CONTROLLER-RULING-20260804-DOMAIN-ELABORATION",
                "writer_output_identity": "unverified-creative-expression",
                "common_sense_domain_elaboration": "allowed-without-trusted-fact-promotion",
            },
            "audit": {"status": "PREAUTHORIZED"},
        },
    )

    adopted = control_fixture.control.adopt_ruling(source)

    assert adopted["current_state"] == "SHARED_ROOT_CAUSE_REPAIR"
    assert adopted["previous_state"] == "FAILED_SAFE"
    assert adopted["completed_gates"] == []
    assert adopted["failure_class"] is None
    assert (control_fixture.runtime_root / "failure.json").read_bytes() == failure_before
    assert (control_fixture.runtime_root / "events.jsonl").read_bytes().startswith(events_before)
    final_event = json.loads(
        (control_fixture.runtime_root / "events.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()[-1]
    )
    assert final_event["data"]["ruling_id"] == (
        "TENANT01-CONTROLLER-RULING-20260804-DOMAIN-ELABORATION"
    )
    assert final_event["data"]["historical_failure_evidence_retained"] is True


def test_state_schema_lists_candidate_scoped_governance_fields() -> None:
    schema = json.loads(Path("config/execution-control-v1.schema.json").read_text(encoding="utf-8"))
    required = set(cast(list[str], schema["required"]))
    properties = cast(dict[str, object], schema["properties"])
    assert {"governance_version", "acceptance_runs"} <= required
    assert {"governance_version", "acceptance_runs"} <= set(properties)


def test_head_change_invalidates_completed_gates_without_rewriting_events(
    control_fixture: _ControlFixture,
) -> None:
    _transition(control_fixture, "BOOTSTRAP", "CONTRACT_FROZEN")
    _transition(control_fixture, "CONTRACT_FROZEN", "STRUCTURAL_IMPLEMENTATION")
    control_fixture.control.begin("old_sha_gate", "true", None, os.getpid())
    control_fixture.control.complete("old_sha_gate", "evidence/old-sha.json")
    before = (control_fixture.runtime_root / "events.jsonl").read_bytes()

    marker = control_fixture.repository / "implementation.txt"
    marker.write_text("new candidate\n", encoding="utf-8")
    _git(control_fixture.repository, "add", "implementation.txt")
    _git(control_fixture.repository, "commit", "-m", "new candidate")
    state = control_fixture.control.status()
    transitioned = control_fixture.control.transition(
        "STRUCTURAL_IMPLEMENTATION",
        str(state["head_sha"]),
        control_fixture.contract_digest,
        "DETERMINISTIC_GATE",
    )

    assert transitioned["head_sha"] != control_fixture.initial_head
    assert transitioned["completed_gates"] == []
    assert (control_fixture.runtime_root / "events.jsonl").read_bytes().startswith(before)


def test_review_rework_is_append_only_same_milestone_and_invalidates_old_gates(
    control_fixture: _ControlFixture,
) -> None:
    _reach_review(control_fixture)
    delivered = control_fixture.control.status()
    delivered_head = str(delivered["head_sha"])
    delivered_acceptance = delivered["acceptance_runs"]
    delivered_evidence = tuple(cast(list[str], delivered["evidence_paths"]))
    before = (control_fixture.runtime_root / "events.jsonl").read_bytes()

    with pytest.raises(ExecutionControlError, match="not allowed"):
        control_fixture.control.transition(
            "REVIEW",
            delivered_head,
            control_fixture.contract_digest,
            "CURRENT_TRUTH_RECONCILIATION",
        )

    marker = control_fixture.repository / "formal-usability-rework.txt"
    marker.write_text("authorized bounded rework\n", encoding="utf-8")
    _git(control_fixture.repository, "add", marker.name)
    _git(control_fixture.repository, "commit", "-m", "bounded review rework")

    with pytest.raises(ExecutionControlError, match="authorization is unknown"):
        control_fixture.control.reopen_review(
            expected_runtime_head=delivered_head,
            rework_id="TENANT-02",
        )

    scratch = control_fixture.repository / "untracked.txt"
    scratch.write_text("must fail closed\n", encoding="utf-8")
    with pytest.raises(ExecutionControlError, match="clean staging area"):
        control_fixture.control.reopen_review(
            expected_runtime_head=delivered_head,
            rework_id=FORMAL_USABILITY_REWORK_ID,
        )
    scratch.unlink()

    protected = control_fixture.repository / "docs" / "项目记忆.md"
    protected.write_text("已提交项目记忆\n用户受保护修改\n漂移\n", encoding="utf-8")
    with pytest.raises(ExecutionControlError, match="protected user change digest drifted"):
        control_fixture.control.reopen_review(
            expected_runtime_head=delivered_head,
            rework_id=FORMAL_USABILITY_REWORK_ID,
        )
    protected.write_text("已提交项目记忆\n用户受保护修改\n", encoding="utf-8")

    reopened = control_fixture.control.reopen_review(
        expected_runtime_head=delivered_head,
        rework_id=FORMAL_USABILITY_REWORK_ID,
    )

    assert reopened["current_state"] == "CURRENT_TRUTH_RECONCILIATION"
    assert reopened["previous_state"] == "REVIEW"
    assert reopened["head_sha"] != delivered_head
    assert reopened["completed_gates"] == []
    assert reopened["acceptance_runs"] == delivered_acceptance
    assert tuple(cast(list[str], reopened["evidence_paths"])) == delivered_evidence
    events = (control_fixture.runtime_root / "events.jsonl").read_bytes()
    assert events.startswith(before)
    assert b'"event_type":"review_rework_reopened"' in events

    with pytest.raises(ExecutionControlError, match="current_truth_snapshot"):
        control_fixture.control.transition(
            "CURRENT_TRUTH_RECONCILIATION",
            str(reopened["head_sha"]),
            control_fixture.contract_digest,
            "SUPPORTED_SURFACE_AUDIT",
        )
    control_fixture.control.begin(
        "current_truth_snapshot",
        "record dated production truth",
        None,
        os.getpid(),
    )
    control_fixture.control.complete(
        "current_truth_snapshot",
        "evidence/current-truth.json",
    )
    advanced = control_fixture.control.transition(
        "CURRENT_TRUTH_RECONCILIATION",
        str(reopened["head_sha"]),
        control_fixture.contract_digest,
        "SUPPORTED_SURFACE_AUDIT",
    )
    assert advanced["current_state"] == "SUPPORTED_SURFACE_AUDIT"

    control_fixture.control.begin(
        "supported_surface_audit",
        "audit supported surface",
        None,
        os.getpid(),
    )
    control_fixture.control.complete(
        "supported_surface_audit",
        "evidence/supported-surface.json",
    )
    repaired = control_fixture.control.transition(
        "SUPPORTED_SURFACE_AUDIT",
        str(reopened["head_sha"]),
        control_fixture.contract_digest,
        "SHARED_ROOT_CAUSE_REPAIR",
    )
    assert repaired["current_state"] == "SHARED_ROOT_CAUSE_REPAIR"
    forward = control_fixture.repository / "formal-usability-forward.py"
    forward.write_text("# committed repair\n", encoding="utf-8")
    _git(control_fixture.repository, "add", forward.name)
    _git(control_fixture.repository, "commit", "-m", "commit shared repair")
    dirty = control_fixture.repository / "uncommitted-repair.py"
    dirty.write_text("# uncommitted repair\n", encoding="utf-8")
    before_failed_sync = control_fixture.control.status()
    with pytest.raises(
        ExecutionControlError,
        match="requires committed implementation and only the protected change",
    ):
        control_fixture.control.begin(
            "shared_root_cause_repair",
            "must reject uncommitted repair",
            None,
            os.getpid(),
        )
    assert control_fixture.control.status()["event_count"] == before_failed_sync["event_count"]
    dirty.unlink()
    synchronized = control_fixture.control.begin(
        "shared_root_cause_repair",
        "verify shared repairs",
        None,
        os.getpid(),
    )
    assert synchronized["head_sha"] != repaired["head_sha"]
    assert synchronized["completed_gates"] == []
    control_fixture.control.complete(
        "shared_root_cause_repair",
        "evidence/shared-repair.json",
    )
    with pytest.raises(ExecutionControlError, match="formal_publication_projection_ready"):
        control_fixture.control.transition(
            "SHARED_ROOT_CAUSE_REPAIR",
            str(synchronized["head_sha"]),
            control_fixture.contract_digest,
            "FORMAL_LOCAL_VERTICAL_ACCEPTANCE",
        )
    control_fixture.control.begin(
        "formal_publication_projection_ready",
        "verify source-bound publication projection",
        None,
        os.getpid(),
    )
    control_fixture.control.complete(
        "formal_publication_projection_ready",
        "evidence/formal-publication-projection.json",
    )
    local_acceptance = control_fixture.control.transition(
        "SHARED_ROOT_CAUSE_REPAIR",
        str(synchronized["head_sha"]),
        control_fixture.contract_digest,
        "FORMAL_LOCAL_VERTICAL_ACCEPTANCE",
    )
    assert local_acceptance["current_state"] == "FORMAL_LOCAL_VERTICAL_ACCEPTANCE"
    for gate in (
        "deterministic_engineering",
        "formal_local_vertical",
        "explicit_browser",
        "mutation_proof",
    ):
        control_fixture.control.begin(gate, f"verify {gate}", None, os.getpid())
        control_fixture.control.complete(gate, f"evidence/{gate}.json")
    with pytest.raises(ExecutionControlError, match="formal_context_consumption_proven"):
        control_fixture.control.transition(
            "FORMAL_LOCAL_VERTICAL_ACCEPTANCE",
            str(synchronized["head_sha"]),
            control_fixture.contract_digest,
            "UNIQUE_PRODUCTION_CANDIDATE",
        )
    control_fixture.control.begin(
        "formal_context_consumption_proven",
        "verify formal context consumption",
        None,
        os.getpid(),
    )
    control_fixture.control.complete(
        "formal_context_consumption_proven",
        "evidence/formal-context-consumption.json",
    )
    candidate = control_fixture.control.transition(
        "FORMAL_LOCAL_VERTICAL_ACCEPTANCE",
        str(synchronized["head_sha"]),
        control_fixture.contract_digest,
        "UNIQUE_PRODUCTION_CANDIDATE",
    )
    assert candidate["current_state"] == "UNIQUE_PRODUCTION_CANDIDATE"
    with pytest.raises(ExecutionControlError, match="CI is not authorized"):
        control_fixture.control.verify("ci")
    for gate in (
        "candidate_frozen",
        "model_sample_acceptance",
        "product_review",
        "engineering_review",
        "build_once",
    ):
        control_fixture.control.begin(gate, f"verify {gate}", None, os.getpid())
        control_fixture.control.complete(gate, f"evidence/{gate}.json")
    assert control_fixture.control.verify("ci")["current_state"] == "UNIQUE_PRODUCTION_CANDIDATE"
    with pytest.raises(ExecutionControlError, match="production backup is not authorized"):
        control_fixture.control.verify("backup")
    control_fixture.control.begin("ci_success", "authoritative CI", None, os.getpid())
    control_fixture.control.complete("ci_success", "evidence/ci.json")
    assert control_fixture.control.verify("production_readonly")["current_state"] == (
        "UNIQUE_PRODUCTION_CANDIDATE"
    )
    assert control_fixture.control.verify("backup")["current_state"] == "UNIQUE_PRODUCTION_CANDIDATE"
    with pytest.raises(ExecutionControlError, match="deployment is not authorized"):
        control_fixture.control.verify("deploy")
    control_fixture.control.begin("backup_restore", "backup and isolated restore", None, os.getpid())
    control_fixture.control.complete("backup_restore", "evidence/backup-restore.json")
    live = control_fixture.control.transition(
        "UNIQUE_PRODUCTION_CANDIDATE",
        str(synchronized["head_sha"]),
        control_fixture.contract_digest,
        "LIVE_TENANT_ACCEPTANCE_AND_GUIDE",
    )
    assert live["current_state"] == "LIVE_TENANT_ACCEPTANCE_AND_GUIDE"
    assert control_fixture.control.verify("deploy")["current_state"] == (
        "LIVE_TENANT_ACCEPTANCE_AND_GUIDE"
    )
    with pytest.raises(ExecutionControlError, match="production rollback is not authorized"):
        control_fixture.control.verify("rollback")
    for gate in ("production_deploy", "live_tenant_acceptance"):
        control_fixture.control.begin(gate, f"verify {gate}", None, os.getpid())
        control_fixture.control.complete(gate, f"evidence/{gate}.json")
    assert control_fixture.control.verify("rollback")["current_state"] == (
        "LIVE_TENANT_ACCEPTANCE_AND_GUIDE"
    )
    with pytest.raises(ExecutionControlError, match="production cleanup is not authorized"):
        control_fixture.control.verify("cleanup")
    control_fixture.control.begin("rollback_roundtrip", "rollback and return", None, os.getpid())
    control_fixture.control.complete("rollback_roundtrip", "evidence/rollback.json")
    assert control_fixture.control.verify("cleanup")["current_state"] == (
        "LIVE_TENANT_ACCEPTANCE_AND_GUIDE"
    )
    control_fixture.control.begin(
        "late_implementation_defect",
        "observe ordinary post-freeze implementation defect",
        None,
        os.getpid(),
    )
    control_fixture.control.observe_command_exit(2)
    returned_to_repair = control_fixture.control.classify(
        _failure("implementation_defect", "SHARED_ROOT_CAUSE_REPAIR"),
        clear_active=True,
    )
    assert returned_to_repair["current_state"] == "SHARED_ROOT_CAUSE_REPAIR"
    assert returned_to_repair["active_command"] is None
