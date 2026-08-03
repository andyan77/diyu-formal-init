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


def test_second_provider_semantic_failure_blocks_third_model_attempt(control_fixture: _ControlFixture) -> None:
    _reach_model_preflight(control_fixture)
    first = control_fixture.control.classify(_failure("provider_semantic_failure", "MODEL_PREFLIGHT"))
    assert first["current_state"] == "MODEL_PREFLIGHT"
    second = control_fixture.control.classify(
        _failure("provider_semantic_failure", "NEEDS_ARCHITECTURE_REVIEW")
    )
    assert second["current_state"] == "NEEDS_ARCHITECTURE_REVIEW"
    with pytest.raises(ExecutionControlError, match="not allowed|third provider"):
        control_fixture.control.verify("model_runner")


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
    for gate in ("product_review", "engineering_review"):
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
