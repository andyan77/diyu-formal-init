from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest

from src.tool.execution_control import (
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


def test_hard_semantic_and_contract_failures_are_the_only_controller_or_safe_stops(
    control_fixture: _ControlFixture,
) -> None:
    _reach_model_preflight(control_fixture)
    implementation = control_fixture.control.classify(
        _failure("implementation_defect", "NEEDS_DIAGNOSIS")
    )
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
