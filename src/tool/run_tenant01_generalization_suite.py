from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from src.brain.content_control_service import ContentControlService
from src.brain.content_service import ContentService
from src.brain.workbench_service import WorkbenchService
from src.gateway.api.app import create_app
from src.infrastructure.content_control_repository import (
    PostgresContentControlRepository,
)
from src.infrastructure.local_object_store import LocalObjectStore
from src.infrastructure.postgres_repository import PostgresContentRepository
from src.infrastructure.workbench_repository import PostgresWorkbenchRepository
from src.tool.execution_control import ExecutionControl, verify_runtime_action
from src.tool.llm_gateway.deepseek import DeepSeekGenerator
from src.tool.run_gate_c_final_suite import (
    _current_head,
    _git_status,
    _persistence_ids,
    _settings,
    _task_snapshot,
    _write_private_json,
)
from src.tool.run_tenant01_golden_suite import (
    _artifact,
    _canonical_digest,
    _Card,
    _has_disallowed_worktree_change,
    _is_sha256,
    _persistence_counts,
)
from src.tool.tenant01_evidence import (
    TENANT01_GENERALIZATION_CASE_IDS,
    TENANT01_GENERALIZATION_CONFIG_SHA256,
    TENANT01_PROVIDER_MODEL,
    sha256_file,
)

_SUITE_VERSION = "TENANT-01-FROZEN-GENERALIZATION-V1"
_ACCEPTANCE_SUITE_ID = "tenant01-generalization-15-v1"
_BASELINE_REVISION_MESSAGE = (
    "今天临时改变了原来的安排，计划没有继续。请写成一条完整的小红书。"
)


@dataclass(frozen=True)
class _Journey:
    tenant_id: UUID
    session_token: str
    publishing_identity_id: UUID
    confirmed_sku: str
    insufficient_sku: str
    registered_media_asset_ids: tuple[UUID, UUID]
    secondary_tenant_id: UUID
    secondary_session_token: str
    secondary_publishing_identity_id: UUID

    @classmethod
    def from_file(cls, path: Path) -> _Journey:
        document = _json_object(path)
        required = {
            "tenant_id",
            "session_token",
            "publishing_identity_id",
            "confirmed_sku",
            "insufficient_sku",
            "registered_media_asset_ids",
            "secondary_tenant_id",
            "secondary_session_token",
            "secondary_publishing_identity_id",
        }
        raw_media = document.get("registered_media_asset_ids")
        if set(document) != required or not isinstance(raw_media, list) or len(raw_media) != 2:
            raise ValueError("TENANT-01 generalization journey fields drifted")
        media_ids = tuple(UUID(str(value)) for value in raw_media)
        confirmed_sku = str(document["confirmed_sku"]).strip()
        insufficient_sku = str(document["insufficient_sku"]).strip()
        session_token = str(document["session_token"])
        secondary_session_token = str(document["secondary_session_token"])
        if (
            not confirmed_sku
            or not insufficient_sku
            or confirmed_sku == insufficient_sku
            or not session_token
            or not secondary_session_token
            or len(set(media_ids)) != 2
        ):
            raise ValueError("TENANT-01 generalization journey is incomplete")
        return cls(
            tenant_id=UUID(str(document["tenant_id"])),
            session_token=session_token,
            publishing_identity_id=UUID(str(document["publishing_identity_id"])),
            confirmed_sku=confirmed_sku,
            insufficient_sku=insufficient_sku,
            registered_media_asset_ids=cast(tuple[UUID, UUID], media_ids),
            secondary_tenant_id=UUID(str(document["secondary_tenant_id"])),
            secondary_session_token=secondary_session_token,
            secondary_publishing_identity_id=UUID(
                str(document["secondary_publishing_identity_id"])
            ),
        )


@dataclass(frozen=True)
class _Case:
    case_id: str
    journey: str
    message: str
    targets: tuple[str, ...]
    expected: str


class _GeneralizationGenerator(DeepSeekGenerator):
    """Bind every provider call to one immutable generalization output."""

    def __init__(
        self,
        *,
        evidence_root: Path,
        allowed_run_ids: frozenset[str],
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._evidence_root = evidence_root
        self._allowed_run_ids = allowed_run_ids
        self._active_run_id: str | None = None
        self._responses: list[dict[str, object]] = []

    def begin(self, run_id: str) -> None:
        if self._active_run_id is not None or run_id not in self._allowed_run_ids:
            raise RuntimeError("generalization provider run ownership drifted")
        self._active_run_id = run_id
        self._responses = []

    def finish(self, *, allow_preflight: bool = False) -> str:
        run_id = self._active_run_id
        if run_id is None:
            raise RuntimeError("generalization provider run is not active")
        stages = tuple(str(item["stage"]) for item in self._responses)
        valid_stages = (
            stages in {("intake", "writer"), ("writer",)}
            if not allow_preflight
            else stages in {(), ("intake",)}
        )
        if not valid_stages or any(item["transport_retries"] != 0 for item in self._responses):
            raise RuntimeError("generalization provider stages drifted")
        filename = f"generalization-{run_id}.raw.json"
        _write_private_json(
            self._evidence_root / filename,
            {
                "raw_bundle_version": "tenant01-generalization-provider-stages-v1",
                "run_id": run_id,
                "request_count": len(self._responses),
                "responses": self._responses,
            },
        )
        self._active_run_id = None
        self._responses = []
        return filename

    def _request(
        self,
        system: str,
        prompt: str,
        max_tokens: int,
        *,
        thinking_disabled: bool = True,
        timeout_seconds: float | None = None,
    ) -> tuple[dict[str, Any], int]:
        run_id = self._active_run_id
        if run_id is None:
            raise RuntimeError("provider call is not bound to a generalization run")
        payload, retries = super()._request(
            system,
            prompt,
            max_tokens,
            thinking_disabled=thinking_disabled,
            timeout_seconds=timeout_seconds,
        )
        stage = "writer" if "你是笛语 Writer" in system else "intake"
        request_payload: dict[str, object] = {
            "model": TENANT01_PROVIDER_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.0,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        if thinking_disabled:
            request_payload["thinking"] = {"type": "disabled"}
        self._responses.append(
            {
                "request_index": len(self._responses) + 1,
                "transport_retries": retries,
                "stage": stage,
                "model": TENANT01_PROVIDER_MODEL,
                "request_sha256": _canonical_digest(request_payload),
                "response_sha256": _canonical_digest(payload),
                "response": payload,
            }
        )
        return payload, retries


def _config(path: Path, journey: _Journey) -> tuple[_Case, ...]:
    if sha256_file(path) != TENANT01_GENERALIZATION_CONFIG_SHA256:
        raise ValueError("frozen generalization regression set drifted")
    raw_document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw_document, dict):
        raise ValueError("generalization configuration is invalid")
    document = cast(dict[str, object], raw_document)
    if document.get("suite_version") != "TENANT-01-SEMANTIC-HOLDOUT-V1":
        raise ValueError("generalization configuration version drifted")
    raw_cases = document.get("cases")
    if not isinstance(raw_cases, list):
        raise ValueError("generalization cases are unavailable")
    cases: list[_Case] = []
    for raw in raw_cases:
        if not isinstance(raw, dict):
            raise ValueError("generalization case is invalid")
        case_id = str(raw.get("case_id", ""))
        message = (
            str(raw.get("message", ""))
            .replace("{holdout_confirmed_sku}", journey.confirmed_sku)
            .replace("{holdout_insufficient_sku}", journey.insufficient_sku)
        )
        raw_targets = raw.get("targets")
        target = raw.get("target")
        targets = (
            tuple(str(value) for value in raw_targets)
            if isinstance(raw_targets, list)
            else (str(target),)
        )
        if not case_id or not message or not all(targets):
            raise ValueError("generalization case is incomplete")
        cases.append(
            _Case(
                case_id=case_id,
                journey=str(raw.get("journey", "")),
                message=message,
                targets=targets,
                expected=str(raw.get("expected", "")),
            )
        )
    if {case.case_id for case in cases} != TENANT01_GENERALIZATION_CASE_IDS:
        raise ValueError("generalization case coverage drifted")
    return tuple(cases)


def _run_ids(cases: tuple[_Case, ...]) -> frozenset[str]:
    values: set[str] = set()
    for case in cases:
        if case.journey == "revision":
            values.update({f"{case.case_id}--v1", f"{case.case_id}--v2"})
        elif case.journey == "three_episode_series":
            values.update(f"{case.case_id}--series{index}" for index in range(1, 4))
        elif case.journey == "cross_platform_pair":
            values.update(
                {f"{case.case_id}--xiaohongshu", f"{case.case_id}--douyin"}
            )
        elif case.journey == "cross_brand_synthetic_pair":
            values.update({f"{case.case_id}--primary", f"{case.case_id}--secondary"})
        else:
            values.add(case.case_id)
    return frozenset(values)


def _completed(events: list[dict[str, object]]) -> dict[str, object] | None:
    completed = [event for event in events if event.get("event") == "completed"]
    if not completed:
        return None
    if len(completed) != 1 or not isinstance(completed[0].get("result"), dict):
        raise RuntimeError("generalization stream completion drifted")
    return cast(dict[str, object], completed[0]["result"])


def _artifact_outcome(
    root: Path,
    database_url: str,
    tenant_id: UUID,
    run_id: str,
    card: _Card,
    result: dict[str, object],
    raw_file: str,
) -> dict[str, object]:
    task_id = UUID(str(result["task_id"]))
    version = int(cast(int, result["version"]))
    run_uuid, version_id = _persistence_ids(
        database_url,
        tenant_id,
        task_id,
        version,
    )
    snapshot = _task_snapshot(database_url, tenant_id, task_id)
    artifact = _artifact(
        card,
        result,
        snapshot,
        run_id=run_uuid,
        version_id=version_id,
    )
    artifact_file = f"generalization-{run_id}.artifact.json"
    _write_private_json(root / artifact_file, artifact)
    return {
        "kind": "artifact",
        "run_id": run_id,
        "artifact_file": artifact_file,
        "artifact_sha256": sha256_file(root / artifact_file),
        "raw_file": raw_file,
        "raw_sha256": sha256_file(root / raw_file),
        "task_id": str(task_id),
        "generation_run_id": str(run_uuid),
        "version_id": str(version_id),
        "version": version,
        "visible_digest": artifact["visible_digest"],
        "visible": {
            "title": artifact["outline"],
            "body": artifact["body"],
            "production": artifact["production"],
        },
    }


def _stream(
    client: TestClient,
    generator: _GeneralizationGenerator,
    *,
    root: Path,
    database_url: str,
    tenant_id: UUID,
    run_id: str,
    message: str,
    target: str,
    publishing_identity_id: UUID,
    material_ids: tuple[UUID, ...] = (),
    product_media_intent: bool = False,
    series_id: UUID | None = None,
    series_position: int | None = None,
    expect_preflight: bool = False,
) -> dict[str, object]:
    before = _persistence_counts(database_url, tenant_id)
    generator.begin(run_id)
    response = client.post(
        "/api/v1/content/stream",
        json={
            "message": message,
            "conversation": [],
            "publishing_identity_id": str(publishing_identity_id),
            "target": target,
            "material_ids": [str(value) for value in material_ids],
            "product_media_intent": product_media_intent,
            "interaction_mode": "generate",
            "direct_generate": True,
            "request_id": str(uuid4()),
            "series_id": str(series_id) if series_id is not None else None,
            "series_position": series_position,
        },
    )
    if response.status_code != 200:
        raise RuntimeError(f"{run_id}: formal content API failed")
    events = [
        cast(dict[str, object], json.loads(line))
        for line in response.text.splitlines()
        if line.strip()
    ]
    result = _completed(events)
    if expect_preflight:
        if result is not None:
            raise RuntimeError(f"{run_id}: preflight unexpectedly committed")
        raw_file = generator.finish(allow_preflight=True)
        after = _persistence_counts(database_url, tenant_id)
        questions = [
            str(event.get("message", ""))
            for event in events
            if event.get("kind") == "question"
        ]
        if before != after or not any(question.strip() for question in questions):
            raise RuntimeError(f"{run_id}: preflight did not fail atomically")
        return {
            "kind": "preflight",
            "run_id": run_id,
            "raw_file": raw_file,
            "raw_sha256": sha256_file(root / raw_file),
            "persistence_delta": [0, 0, 0],
            "visible": {"question": next(question for question in questions if question.strip())},
        }
    if result is None:
        raise RuntimeError(f"{run_id}: formal content API did not commit")
    raw_file = generator.finish()
    return _artifact_outcome(
        root,
        database_url,
        tenant_id,
        run_id,
        _Card(run_id, message, target, series_position),
        result,
        raw_file,
    )


def _revision(
    client: TestClient,
    generator: _GeneralizationGenerator,
    *,
    root: Path,
    database_url: str,
    journey: _Journey,
    case: _Case,
) -> list[dict[str, object]]:
    baseline = _stream(
        client,
        generator,
        root=root,
        database_url=database_url,
        tenant_id=journey.tenant_id,
        run_id=f"{case.case_id}--v1",
        message=_BASELINE_REVISION_MESSAGE,
        target=case.targets[0],
        publishing_identity_id=journey.publishing_identity_id,
    )
    task_id = UUID(str(baseline["task_id"]))
    generator.begin(f"{case.case_id}--v2")
    response = client.post(
        f"/api/v1/tasks/{task_id}/revisions",
        json={
            "instruction": case.message,
            "target": case.targets[0],
            "source_target": case.targets[0],
            "publishing_identity_id": str(journey.publishing_identity_id),
            "request_id": str(uuid4()),
        },
    )
    if response.status_code != 201 or not isinstance(response.json(), dict):
        raise RuntimeError(f"{case.case_id}: formal revision failed")
    raw_file = generator.finish()
    revised = _artifact_outcome(
        root,
        database_url,
        journey.tenant_id,
        f"{case.case_id}--v2",
        _Card(f"{case.case_id}--v2", _BASELINE_REVISION_MESSAGE, case.targets[0]),
        cast(dict[str, object], response.json()),
        raw_file,
    )
    if revised["task_id"] != baseline["task_id"] or revised["version"] != 2:
        raise RuntimeError(f"{case.case_id}: V2 append-only lifecycle drifted")
    return [baseline, revised]


def _series(
    client: TestClient,
    generator: _GeneralizationGenerator,
    *,
    root: Path,
    database_url: str,
    journey: _Journey,
    case: _Case,
) -> list[dict[str, object]]:
    response = client.post(
        "/api/v1/content/series",
        params={
            "target": case.targets[0],
            "publishing_identity_id": str(journey.publishing_identity_id),
        },
        json={
            "title": f"冻结泛化系列 · {uuid4()}",
            "premise": case.message,
        },
    )
    if response.status_code != 201:
        raise RuntimeError(f"{case.case_id}: formal series could not be created")
    series_id = UUID(str(response.json()["id"]))
    return [
        _stream(
            client,
            generator,
            root=root,
            database_url=database_url,
            tenant_id=journey.tenant_id,
            run_id=f"{case.case_id}--series{position}",
            message=case.message,
            target=case.targets[0],
            publishing_identity_id=journey.publishing_identity_id,
            series_id=series_id,
            series_position=position,
        )
        for position in range(1, 4)
    ]


def _case_outcomes(
    primary: TestClient,
    secondary: TestClient,
    generator: _GeneralizationGenerator,
    *,
    root: Path,
    database_url: str,
    journey: _Journey,
    case: _Case,
) -> list[dict[str, object]]:
    if case.journey == "revision":
        return _revision(
            primary,
            generator,
            root=root,
            database_url=database_url,
            journey=journey,
            case=case,
        )
    if case.journey == "three_episode_series":
        return _series(
            primary,
            generator,
            root=root,
            database_url=database_url,
            journey=journey,
            case=case,
        )
    if case.journey == "cross_platform_pair":
        labels = ("xiaohongshu", "douyin")
        return [
            _stream(
                primary,
                generator,
                root=root,
                database_url=database_url,
                tenant_id=journey.tenant_id,
                run_id=f"{case.case_id}--{label}",
                message=case.message,
                target=target,
                publishing_identity_id=journey.publishing_identity_id,
            )
            for label, target in zip(labels, case.targets, strict=True)
        ]
    if case.journey == "cross_brand_synthetic_pair":
        return [
            _stream(
                client,
                generator,
                root=root,
                database_url=database_url,
                tenant_id=tenant_id,
                run_id=f"{case.case_id}--{label}",
                message=case.message,
                target=case.targets[0],
                publishing_identity_id=identity_id,
            )
            for client, tenant_id, identity_id, label in (
                (
                    primary,
                    journey.tenant_id,
                    journey.publishing_identity_id,
                    "primary",
                ),
                (
                    secondary,
                    journey.secondary_tenant_id,
                    journey.secondary_publishing_identity_id,
                    "secondary",
                ),
            )
        ]
    expect_preflight = case.expected == "preflight_clarification_0_0_0"
    media_ids = (
        journey.registered_media_asset_ids
        if case.journey == "content_with_synthetic_registered_media"
        else ()
    )
    return [
        _stream(
            primary,
            generator,
            root=root,
            database_url=database_url,
            tenant_id=journey.tenant_id,
            run_id=case.case_id,
            message=case.message,
            target=case.targets[0],
            publishing_identity_id=journey.publishing_identity_id,
            material_ids=media_ids,
            product_media_intent=("P5" in case.expected or "p5" in case.case_id),
            expect_preflight=expect_preflight,
        )
    ]


def _assert_result_shape(case: _Case, outcomes: list[dict[str, object]]) -> None:
    if not outcomes:
        raise RuntimeError(f"{case.case_id}: no frozen result")
    for outcome in outcomes:
        if outcome.get("kind") == "artifact":
            visible = outcome.get("visible")
            if (
                not isinstance(visible, dict)
                or not str(visible.get("title", "")).strip()
                or not str(visible.get("body", "")).strip()
                or not isinstance(visible.get("production"), dict)
                or not _is_sha256(outcome.get("artifact_sha256"))
                or not _is_sha256(outcome.get("visible_digest"))
            ):
                raise RuntimeError(f"{case.case_id}: artifact structure drifted")
        elif outcome.get("kind") == "preflight":
            visible = outcome.get("visible")
            if (
                not isinstance(visible, dict)
                or not str(visible.get("question", "")).strip()
                or outcome.get("persistence_delta") != [0, 0, 0]
            ):
                raise RuntimeError(f"{case.case_id}: preflight structure drifted")
        else:
            raise RuntimeError(f"{case.case_id}: unknown result kind")


def _raw_evidence_files(value: object) -> tuple[str, ...]:
    files: list[str] = []
    if isinstance(value, dict):
        raw_file = value.get("raw_file")
        if isinstance(raw_file, str):
            files.append(raw_file)
        for nested in value.values():
            files.extend(_raw_evidence_files(nested))
    elif isinstance(value, list):
        for nested in value:
            files.extend(_raw_evidence_files(nested))
    return tuple(dict.fromkeys(files))


def _provider_request_count(root: Path, outcomes: list[dict[str, object]]) -> int:
    total = 0
    for filename in _raw_evidence_files(outcomes):
        document = _json_object(root / filename)
        total += int(cast(int, document.get("request_count", 0)))
    return total


def _run(args: argparse.Namespace) -> None:
    os.umask(0o077)
    root = Path(args.evidence_root).resolve()
    if not root.is_dir() or root.stat().st_mode & 0o077:
        raise RuntimeError("generalization evidence root must already be private")
    implementation_sha = _current_head()
    if implementation_sha != args.implementation_sha:
        raise RuntimeError("current HEAD is not the frozen implementation SHA")
    if _has_disallowed_worktree_change(_git_status()):
        raise RuntimeError("generalization suite requires the frozen worktree")
    journey = _Journey.from_file(Path(args.journey_file).resolve())
    cases = _config(Path(args.config).resolve(), journey)
    control = ExecutionControl(Path.cwd())
    control.begin_acceptance_suite(
        candidate_sha=implementation_sha,
        suite_id=_ACCEPTANCE_SUITE_ID,
        acceptance_run_id=str(args.acceptance_run_id),
        config_digest=sha256_file(Path(args.config).resolve()),
        sample_ids=tuple(case.case_id for case in cases),
        allow_resume=bool(args.resume_unreceived),
    )
    pending = set(
        control.acceptance_pending_samples(
            candidate_sha=implementation_sha,
            suite_id=_ACCEPTANCE_SUITE_ID,
            acceptance_run_id=str(args.acceptance_run_id),
        )
    )
    database_url = os.environ.get("DIYU_APP_DATABASE_URL", "")
    if not database_url:
        raise RuntimeError("formal application database is unavailable")
    object_store = LocalObjectStore(str(root / "generalization-object-store"))
    settings = _settings(
        database_url=database_url,
        object_store_root=root / "generalization-object-store",
    )
    control_service = ContentControlService(
        PostgresContentControlRepository(database_url),
        object_store,
    )
    generator = _GeneralizationGenerator(
        evidence_root=root,
        allowed_run_ids=_run_ids(cases),
        api_base_url=cast(str, settings.deepseek_api_base_url),
        api_key=cast(Any, settings.deepseek_api_key).get_secret_value(),
        model=TENANT01_PROVIDER_MODEL,
        reviewer_provider=None,
        timeout_seconds=120.0,
        max_retries=0,
    )
    content_service = ContentService(
        PostgresContentRepository(database_url),
        generator,
        control_service,
    )
    api_runtime = cast(Any, import_module("src.gateway.api.app"))
    api_runtime.build_content_control_service = lambda _: control_service
    api_runtime.build_content_service = lambda _: content_service
    api_runtime.build_workbench_service = lambda _: WorkbenchService(
        PostgresWorkbenchRepository(database_url),
        object_store,
    )
    app = create_app(settings)
    with (
        TestClient(app, base_url="https://diyu.example") as primary,
        TestClient(app, base_url="https://diyu.example") as secondary,
    ):
        primary.cookies.set("diyu_session", journey.session_token)
        secondary.cookies.set("diyu_session", journey.secondary_session_token)
        for case in cases:
            if case.case_id not in pending:
                continue
            before_raw = set(root.glob(f"generalization-{case.case_id}*.raw.json"))
            try:
                outcomes = _case_outcomes(
                    primary,
                    secondary,
                    generator,
                    root=root,
                    database_url=database_url,
                    journey=journey,
                    case=case,
                )
            except (KeyError, RuntimeError, TypeError, ValueError):
                after_raw = set(root.glob(f"generalization-{case.case_id}*.raw.json"))
                new_raw = sorted(after_raw - before_raw)
                request_count = sum(
                    int(cast(int, _json_object(path).get("request_count", 0)))
                    for path in new_raw
                )
                control.record_acceptance_sample(
                    candidate_sha=implementation_sha,
                    suite_id=_ACCEPTANCE_SUITE_ID,
                    acceptance_run_id=str(args.acceptance_run_id),
                    sample_id=case.case_id,
                    provider_response_received=request_count > 0,
                    request_count=request_count,
                    artifact_digest=(
                        _canonical_digest([sha256_file(path) for path in new_raw])
                        if new_raw
                        else None
                    ),
                    final_status=(
                        "transport_failed_no_response" if request_count == 0 else "delivery_uncertain"
                    ),
                )
                raise
            _assert_result_shape(case, outcomes)
            result_path = root / f"generalization-{case.case_id}.result.json"
            _write_private_json(
                result_path,
                {
                    "suite_version": _SUITE_VERSION,
                    "case_id": case.case_id,
                    "expected": case.expected,
                    "machine_hard_gate": "PASS",
                    "structure_gate": "PASS",
                    "outcomes": outcomes,
                },
            )
            request_count = _provider_request_count(root, outcomes)
            control.record_acceptance_sample(
                candidate_sha=implementation_sha,
                suite_id=_ACCEPTANCE_SUITE_ID,
                acceptance_run_id=str(args.acceptance_run_id),
                sample_id=case.case_id,
                provider_response_received=request_count > 0,
                request_count=request_count,
                artifact_digest=sha256_file(result_path),
                final_status=(
                    "artifact_ready" if request_count > 0 else "deterministic_preflight_pass"
                ),
            )
    _write_private_json(
        root / "generalization-suite-config.json",
        {
            "suite_version": _SUITE_VERSION,
            "implementation_sha": implementation_sha,
            "acceptance_run_id": args.acceptance_run_id,
            "source_config": {
                "file": "config/tenant01/semantic-holdout-v1.json",
                "sha256": TENANT01_GENERALIZATION_CONFIG_SHA256,
                "set_kind": "frozen_generalization_regression",
            },
            "provider_config": {
                "model": TENANT01_PROVIDER_MODEL,
                "temperature": 0,
                "max_retries": 0,
            },
            "cases": [case.case_id for case in cases],
        },
    )
    control.complete_acceptance_suite(
        candidate_sha=implementation_sha,
        suite_id=_ACCEPTANCE_SUITE_ID,
        acceptance_run_id=str(args.acceptance_run_id),
    )


def _json_object(path: Path) -> dict[str, object]:
    if not path.is_file() or path.stat().st_mode & 0o077:
        raise ValueError(f"{path.name} must be a private JSON file")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain one JSON object")
    return cast(dict[str, object], value)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the frozen TENANT-01 generalization regression set once."
    )
    parser.add_argument("--implementation-sha", required=True)
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--journey-file", required=True)
    parser.add_argument("--acceptance-run-id", required=True)
    parser.add_argument("--resume-unreceived", action="store_true")
    parser.add_argument(
        "--config",
        default="config/tenant01/semantic-holdout-v1.json",
    )
    arguments = parser.parse_args()
    verify_runtime_action("acceptance_runner")
    _run(arguments)


if __name__ == "__main__":
    main()
