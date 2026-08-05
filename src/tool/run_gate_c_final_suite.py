from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any, cast
from urllib.request import ProxyHandler, build_opener
from uuid import UUID, uuid4

import psycopg
import uvicorn
from fastapi.testclient import TestClient

from src.brain.content_control_service import ContentControlService
from src.brain.content_service import ContentService
from src.brain.workbench_service import WorkbenchService
from src.gateway.api.app import create_app
from src.gateway.api.settings import Settings
from src.infrastructure.content_control_repository import (
    PostgresContentControlRepository,
)
from src.infrastructure.local_object_store import LocalObjectStore
from src.infrastructure.postgres_repository import PostgresContentRepository
from src.infrastructure.workbench_repository import PostgresWorkbenchRepository
from src.shared.narrative import visible_digest
from src.tool.gate_c_evidence import (
    GATE_C_FINAL_CARD_IDS,
    GATE_C_REVIEW_CRITERIA,
    ArtifactEvidenceInput,
    EvidenceRuntimeInput,
    HumanReviewInput,
    sha256_file,
    write_gate_c_evidence,
)
from src.tool.llm_gateway.deepseek import DeepSeekGenerator, ProviderRequestFailure
from src.tool.tenant01_evidence import failed_generation_gate_evaluation

_MODEL = "deepseek-v4-flash"
_SUITE_VERSION = "ux03-gate-c-formal-final-suite-v3"
_CARDS = ("P1", "P2", "P3", "P4", "P5", "series2", "series3")


def _loopback_status(url: str, *, timeout: float) -> int:
    """Read a local readiness URL without inheriting provider proxies."""

    opener = build_opener(ProxyHandler({}))
    with opener.open(url, timeout=timeout) as response:
        return int(response.status)


@dataclass(frozen=True)
class _CardSpec:
    card_id: str
    message: str
    publishing_identity_id: UUID
    target: str
    material_ids: tuple[UUID, ...] = ()
    series_position: int | None = None


@dataclass(frozen=True)
class _FormalJourney:
    tenant_id: UUID
    session_token: str
    headquarters_identity_id: UUID
    store_identity_id: UUID
    p5_material_ids: tuple[UUID, UUID]
    p5_product_names: tuple[str, str]
    p5_material_titles: tuple[str, str]

    @classmethod
    def from_file(cls, path: Path) -> _FormalJourney:
        document = _json_object(path)
        allowed = {
            "tenant_id",
            "session_token",
            "headquarters_identity_id",
            "store_identity_id",
            "p5_material_ids",
            "p5_product_names",
            "p5_material_titles",
        }
        if set(document) != allowed:
            raise ValueError("formal journey file fields drifted")
        raw_material_ids = document["p5_material_ids"]
        if not isinstance(raw_material_ids, list) or len(raw_material_ids) != 2:
            raise ValueError("formal journey needs exactly two selected materials")
        material_ids = tuple(UUID(str(item)) for item in raw_material_ids)
        if len(set(material_ids)) != 2:
            raise ValueError("formal journey materials must be distinct")
        product_names = _two_non_empty_strings(
            document["p5_product_names"],
            label="product names",
        )
        material_titles = _two_non_empty_strings(
            document["p5_material_titles"],
            label="material titles",
        )
        session_token = str(document["session_token"])
        if not session_token:
            raise ValueError("formal journey session is unavailable")
        return cls(
            tenant_id=UUID(str(document["tenant_id"])),
            session_token=session_token,
            headquarters_identity_id=UUID(str(document["headquarters_identity_id"])),
            store_identity_id=UUID(str(document["store_identity_id"])),
            p5_material_ids=cast(tuple[UUID, UUID], material_ids),
            p5_product_names=product_names,
            p5_material_titles=material_titles,
        )


class _EvidenceDeepSeekGenerator(DeepSeekGenerator):
    """Persist every bounded provider stage used by one formal API card."""

    def __init__(
        self,
        *,
        evidence_root: Path,
        allowed_card_ids: frozenset[str] = GATE_C_FINAL_CARD_IDS,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._evidence_root = evidence_root
        self._allowed_card_ids = allowed_card_ids
        self._active_card: str | None = None
        self._request_count = 0
        self._responses: list[dict[str, object]] = []
        self._provider_attempts: list[dict[str, object]] = []

    def begin_card(self, card_id: str) -> None:
        if card_id not in self._allowed_card_ids:
            raise ValueError("unknown bounded final-suite card")
        self._active_card = card_id
        self._request_count = 0
        self._responses = []
        self._provider_attempts = []

    def end_card(self) -> None:
        card_id = self._active_card
        if card_id is None or not 2 <= self._request_count <= 3:
            raise RuntimeError(
                "each final card must include only intake, Writer, and optional affected-unit repair stages"
            )
        if any(item["transport_retries"] != 0 for item in self._responses) or any(
            item["transport_retries"] != 0 for item in self._provider_attempts
        ):
            raise RuntimeError("final card provider transport retry is forbidden")
        _write_private_json(
            self._evidence_root / f"{card_id}.raw.json",
            {
                "raw_bundle_version": "ux03-gate-c-provider-stages-v1",
                "card_id": card_id,
                "request_count": self._request_count,
                "responses": self._responses,
            },
        )
        self._active_card = None
        self._responses = []
        self._provider_attempts = []

    def abort_card(self, *, event_names: tuple[str, ...]) -> None:
        """Persist provider stages for a failed card without calling them success evidence."""

        card_id = self._active_card
        if card_id is None:
            raise RuntimeError("failed final card is not active")
        if any(item["transport_retries"] != 0 for item in self._responses) or any(
            item["transport_retries"] != 0 for item in self._provider_attempts
        ):
            raise RuntimeError("final card provider transport retry is forbidden")
        _write_private_json(
            self._evidence_root / f"{card_id}.failed.raw.json",
            {
                "raw_bundle_version": "ux03-gate-c-provider-failure-v1",
                "failure_trace_version": "tenant01-provider-failure-trace-v2",
                "card_id": card_id,
                "request_count": self._request_count,
                "event_names": list(event_names),
                "provider_attempts": self._provider_attempts,
                "responses": self._responses,
                "gate_evaluation": failed_generation_gate_evaluation(),
            },
        )
        self._active_card = None
        self._responses = []
        self._provider_attempts = []

    def _request(
        self,
        system: str,
        prompt: str,
        max_tokens: int,
        *,
        thinking_disabled: bool = True,
        timeout_seconds: float | None = None,
    ) -> tuple[dict[str, Any], int]:
        card_id = self._active_card
        if card_id is None:
            raise RuntimeError("provider call is not bound to one final card")
        request_index = len(self._provider_attempts) + 1
        stage = "intake" if request_index == 1 else "writer"
        request_payload: dict[str, object] = {
            "model": self.model_name,
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
        request_sha256 = hashlib.sha256(
            json.dumps(
                request_payload,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
        ).hexdigest()
        try:
            payload, retries = super()._request(
                system,
                prompt,
                max_tokens,
                thinking_disabled=thinking_disabled,
                timeout_seconds=timeout_seconds,
            )
        except ProviderRequestFailure as exc:
            self._provider_attempts.append(
                {
                    "request_index": request_index,
                    "transport_retries": exc.retry_count,
                    "stage": stage,
                    "model": self.model_name,
                    "request_sha256": request_sha256,
                    "response_received": exc.response_received,
                    "outcome": exc.kind,
                }
            )
            self._request_count += int(exc.response_received)
            raise
        self._request_count += 1
        self._provider_attempts.append(
            {
                "request_index": request_index,
                "transport_retries": retries,
                "stage": stage,
                "model": self.model_name,
                "request_sha256": request_sha256,
                "response_received": True,
                "outcome": "response_received",
            }
        )
        self._responses.append(
            {
                "request_index": self._request_count,
                "transport_retries": retries,
                "response": payload,
            }
        )
        return payload, retries


def _two_non_empty_strings(
    value: object,
    *,
    label: str,
) -> tuple[str, str]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"formal journey {label} must contain two values")
    values = tuple(str(item).strip() for item in value)
    if any(not item for item in values) or len(set(values)) != 2:
        raise ValueError(f"formal journey {label} must be distinct")
    return cast(tuple[str, str], values)


def _settings(
    *,
    database_url: str,
    object_store_root: Path,
) -> Settings:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    api_base_url = os.environ.get("DEEPSEEK_API_BASE_URL", "")
    session_secret = os.environ.get("DIYU_SESSION_SECRET", "")
    if not api_key or not api_base_url or not session_secret:
        raise RuntimeError("protected final-suite configuration is unavailable")
    return Settings.model_validate(
        {
            "DIYU_RUNTIME_MODE": "production",
            "DIYU_APP_DATABASE_URL": database_url,
            "DIYU_SESSION_SECRET": session_secret,
            "DIYU_PUBLIC_URL": "https://diyu.example",
            "DIYU_GENERATOR_MODE": "deepseek",
            "DEEPSEEK_API_BASE_URL": api_base_url,
            "DEEPSEEK_API_KEY": api_key,
            "DEEPSEEK_MODEL": _MODEL,
            "DIYU_MODEL_TIMEOUT_SECONDS": "120",
            "DIYU_MODEL_MAX_RETRIES": "0",
            "DIYU_MATERIAL_STORAGE_ROOT": str(object_store_root),
            "DIYU_S3_ENDPOINT_URL": "http://127.0.0.1:1",
            "DIYU_S3_BUCKET": "unused-local-final-suite",
            "DIYU_S3_ACCESS_KEY_ID": "unused-local-final-suite",
            "DIYU_S3_SECRET_ACCESS_KEY": "unused-local-final-suite",
        }
    )


def _run_formal_p5_browser(
    app: object,
    journey: _FormalJourney,
    *,
    evidence_root: Path,
) -> UUID:
    with socket.socket() as port_socket:
        port_socket.bind(("127.0.0.1", 0))
        port = int(port_socket.getsockname()[1])
    server = uvicorn.Server(
        uvicorn.Config(
            cast(Any, app),
            host="127.0.0.1",
            port=port,
            log_level="error",
        )
    )
    thread = threading.Thread(
        target=server.run,
        name="ux03-final-p5-browser-server",
        daemon=True,
    )
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            if not thread.is_alive():
                raise RuntimeError("formal P5 browser server exited early")
            try:
                if _loopback_status(
                    f"{base_url}/health/live",
                    timeout=0.2,
                ) == 200:
                    break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError("formal P5 browser server did not become ready")
        completed = subprocess.run(
            ["node", "frontend/test/ux03-product-media-browser.mjs"],
            cwd=Path(__file__).resolve().parents[2],
            env={
                **os.environ,
                "UX03_PRODUCT_MEDIA_BASE_URL": base_url,
                "UX03_PRODUCT_MEDIA_ADMIN_TOKEN": journey.session_token,
                "UX03_PRODUCT_MEDIA_CREATOR_TOKEN": journey.session_token,
                "UX03_PRODUCT_MEDIA_ACCOUNT_ID": str(journey.headquarters_identity_id),
                "UX03_PRODUCT_MEDIA_PRODUCT_1": journey.p5_product_names[0],
                "UX03_PRODUCT_MEDIA_PRODUCT_2": journey.p5_product_names[1],
                "UX03_PRODUCT_MEDIA_MATERIAL_1": (journey.p5_material_titles[0]),
                "UX03_PRODUCT_MEDIA_MATERIAL_2": (journey.p5_material_titles[1]),
                "UX03_PRODUCT_MEDIA_FORBIDDEN_MATERIAL": (
                    "__no-unrelated-headquarters-material__"
                ),
                "UX03_PRODUCT_MEDIA_SKIP_BINDING": "1",
            },
            capture_output=True,
            text=True,
            timeout=180,
        )
        if completed.returncode != 0:
            browser_result: dict[str, object] = {}
            try:
                parsed = json.loads(completed.stdout)
                if isinstance(parsed, dict):
                    browser_result = {
                        "task_id": parsed.get("task_id"),
                        "lifecycle_events": parsed.get("lifecycle_events"),
                        "failure_count": (
                            len(parsed.get("failures", []))
                            if isinstance(parsed.get("failures"), list)
                            else None
                        ),
                    }
            except (TypeError, ValueError):
                pass
            _write_private_json(
                evidence_root / "P5.browser.failed.json",
                {
                    "failure_contract": "ux03-gate-c-browser-failure-v1",
                    "returncode": completed.returncode,
                    "stdout_sha256": hashlib.sha256(
                        completed.stdout.encode("utf-8")
                    ).hexdigest(),
                    "stderr_sha256": hashlib.sha256(
                        completed.stderr.encode("utf-8")
                    ).hexdigest(),
                    **browser_result,
                },
            )
            raise RuntimeError("formal P5 browser journey failed")
        result = json.loads(completed.stdout)
        if not isinstance(result, dict) or result.get("failures") != [] or not result.get("task_id"):
            raise RuntimeError("formal P5 browser journey did not commit")
        return UUID(str(result["task_id"]))
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        if thread.is_alive():
            raise RuntimeError("formal P5 browser server did not stop")


def _card_specs(
    journey: _FormalJourney,
    *,
    series_id: UUID,
) -> tuple[_CardSpec, ...]:
    return (
        _CardSpec(
            "P1",
            "早上出门有点凉，中午又热，今天怎么穿更稳妥？",
            journey.headquarters_identity_id,
            "douyin_video",
        ),
        _CardSpec(
            "P2",
            "ZX-C218，帮我写一篇小红书，重点说清两面完整外观带来的选择。",
            journey.headquarters_identity_id,
            "xiaohongshu_graphic",
        ),
        _CardSpec(
            "P3",
            "今天喝了一直喝的蓝山咖啡，居然是甜的，帮我发一条。",
            journey.headquarters_identity_id,
            "xiaohongshu_graphic",
        ),
        _CardSpec(
            "P4",
            "今天店里有人只想自己看看。写一条回应这种状态的小红书。",
            journey.store_identity_id,
            "xiaohongshu_graphic",
            series_position=1,
        ),
        _CardSpec(
            "P5",
            "用本次明确选择的两件登记商品做一条视觉关系图文。",
            journey.headquarters_identity_id,
            "xiaohongshu_graphic",
            material_ids=journey.p5_material_ids,
        ),
        _CardSpec(
            "series2",
            "沿着第一篇的不打扰，继续写第二篇：怎样给出回应。",
            journey.store_identity_id,
            "xiaohongshu_graphic",
        ),
        _CardSpec(
            "series3",
            "继续第三篇：回应之后，怎样把选择留给对方。",
            journey.store_identity_id,
            "xiaohongshu_graphic",
        ),
    )


def _stream_card(
    client: TestClient,
    generator: _EvidenceDeepSeekGenerator,
    spec: _CardSpec,
    *,
    series_id: UUID,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "message": spec.message,
        "conversation": [],
        "publishing_identity_id": str(spec.publishing_identity_id),
        "target": spec.target,
        "material_ids": [str(item) for item in spec.material_ids],
        "interaction_mode": "generate",
        "direct_generate": True,
        "request_id": str(uuid4()),
        "series_id": str(series_id) if spec.card_id in {"P4", "series2", "series3"} else None,
        "series_position": spec.series_position,
    }
    generator.begin_card(spec.card_id)
    response = client.post("/api/v1/content/stream", json=payload)
    if response.status_code != 200:
        raise RuntimeError(f"{spec.card_id}: formal content API failed")
    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    completed = [item for item in events if item.get("event") == "completed"]
    if len(completed) != 1:
        generator.abort_card(
            event_names=tuple(str(item.get("event", "")) for item in events),
        )
        raise RuntimeError(f"{spec.card_id}: formal content API did not commit once")
    generator.end_card()
    result = completed[0].get("result")
    if not isinstance(result, dict):
        raise RuntimeError(f"{spec.card_id}: completed artifact is unavailable")
    return cast(dict[str, object], result)


def _task_snapshot(
    database_url: str,
    tenant_id: UUID,
    task_id: UUID,
) -> dict[str, object]:
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT set_config('app.tenant_id', %s, true)",
            (str(tenant_id),),
        )
        cursor.execute(
            """
            SELECT content_context_snapshot
            FROM business_tasks
            WHERE tenant_id = %s AND id = %s
            """,
            (tenant_id, task_id),
        )
        row = cursor.fetchone()
    if row is None or not isinstance(row[0], dict):
        raise RuntimeError("formal task snapshot is unavailable")
    return cast(dict[str, object], row[0])


def _persistence_ids(
    database_url: str,
    tenant_id: UUID,
    task_id: UUID,
    version: int,
) -> tuple[UUID, UUID]:
    """Return the authoritative run/version pair committed for one artifact."""

    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT set_config('app.tenant_id', %s, true)",
            (str(tenant_id),),
        )
        cursor.execute(
            """
            SELECT version.run_id, version.id
            FROM content_versions version
            JOIN generation_runs run
              ON run.tenant_id = version.tenant_id
             AND run.id = version.run_id
             AND run.task_id = version.task_id
             AND run.status = 'succeeded'
            WHERE version.tenant_id = %s
              AND version.task_id = %s
              AND version.version_number = %s
            """,
            (tenant_id, task_id, version),
        )
        row = cursor.fetchone()
    if row is None:
        raise RuntimeError("formal committed run/version identifiers are unavailable")
    return UUID(str(row[0])), UUID(str(row[1]))


def _artifact_document(
    card_id: str,
    result: Mapping[str, object],
    snapshot: Mapping[str, object],
    *,
    task_id: UUID | None = None,
    run_id: UUID | None = None,
    version_id: UUID | None = None,
) -> dict[str, object]:
    outline = result.get("outline")
    body = result.get("body")
    if not isinstance(outline, str) or not isinstance(body, str):
        raise RuntimeError(f"{card_id}: formal visible artifact is unavailable")
    envelope = snapshot.get("media_capability_envelope")
    program = snapshot.get("media_program")
    if not isinstance(envelope, dict) or not isinstance(program, dict):
        raise RuntimeError(f"{card_id}: formal media snapshot is unavailable")
    resolved_task_id = task_id or UUID(str(result.get("task_id")))
    resolved_run_id = run_id or UUID(str(result.get("run_id")))
    resolved_version_id = version_id or UUID(str(result.get("version_id")))
    if result.get("task_id") is not None and UUID(str(result["task_id"])) != resolved_task_id:
        raise RuntimeError(f"{card_id}: task identifier drifted")
    return {
        "suite_version": _SUITE_VERSION,
        "card_id": card_id,
        "task_id": str(resolved_task_id),
        "run_id": str(resolved_run_id),
        "version_id": str(resolved_version_id),
        "version": result.get("version"),
        "outline": outline,
        "body": body,
        "visible_digest": visible_digest(outline, body),
        "production": result.get("production"),
        "ai_generated": result.get("ai_generated"),
        "aigc_label": result.get("aigc_label"),
        "aigc_release_reminder": result.get("aigc_release_reminder"),
        "formal_snapshot": {
            "media_capability_envelope": envelope,
            "media_program": program,
            "product_value_contract": snapshot.get(
                "product_value_contract"
            ),
            "creative_direction": snapshot.get("creative_direction"),
            "series_context": snapshot.get("series_context"),
        },
    }


def _generate(args: argparse.Namespace) -> None:
    evidence_root = Path(args.evidence_root).resolve()
    journey_file = Path(args.journey_file).resolve()
    implementation_sha = _current_head()
    if implementation_sha != args.implementation_sha:
        raise RuntimeError("current HEAD is not the frozen implementation SHA")
    if _git_status():
        raise RuntimeError("final suite requires a clean worktree")
    if evidence_root.exists():
        raise RuntimeError("final suite evidence directory already exists")
    journey = _FormalJourney.from_file(journey_file)
    database_url = os.environ.get("DIYU_APP_DATABASE_URL", "")
    if not database_url:
        raise RuntimeError("formal application database is unavailable")
    evidence_root.mkdir(mode=0o700, parents=True)
    evidence_root.chmod(0o700)
    object_store_root = evidence_root / "object-store"
    settings = _settings(
        database_url=database_url,
        object_store_root=object_store_root,
    )
    object_store = LocalObjectStore(str(object_store_root))
    control_service = ContentControlService(
        PostgresContentControlRepository(database_url),
        object_store,
    )
    generator = _EvidenceDeepSeekGenerator(
        evidence_root=evidence_root,
        api_base_url=cast(str, settings.deepseek_api_base_url),
        api_key=cast(Any, settings.deepseek_api_key).get_secret_value(),
        model=_MODEL,
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
    # The formal P5 browser owns an independent ASGI lifespan.  Reusing the
    # TestClient application below would start the same FastAPI instance a
    # second time while its first lifespan is still active, so its loopback
    # readiness could never become authoritative.
    p5_browser_app = create_app(settings)
    _write_private_json(
        evidence_root / "suite-config.json",
        {
            "suite_version": _SUITE_VERSION,
            "implementation_sha": implementation_sha,
            "provider_config": {
                "model": _MODEL,
                "temperature": 0,
                "max_retries": 0,
                "database": True,
                "formal_api": True,
                "business_persistence": True,
            },
            "cards": list(_CARDS),
        },
    )
    summaries: list[dict[str, object]] = []
    with TestClient(app, base_url="https://diyu.example") as client:
        client.cookies.set("diyu_session", journey.session_token)
        series_response = client.post(
            "/api/v1/content/series",
            params={
                "target": "xiaohongshu_graphic",
                "publishing_identity_id": str(journey.store_identity_id),
            },
            json={
                "title": (
                    "把选择留给人的三篇门店观察 · "
                    f"{implementation_sha[:12]}"
                ),
                "premise": "从不打扰，推进到回应，再推进到留出选择。",
            },
        )
        if series_response.status_code != 201:
            raise RuntimeError("formal series could not be created")
        series_id = UUID(str(series_response.json()["id"]))
        for index, spec in enumerate(_card_specs(journey, series_id=series_id)):
            if index:
                time.sleep(2.05)
            if spec.card_id == "P5":
                generator.begin_card("P5")
                try:
                    task_id = _run_formal_p5_browser(
                        p5_browser_app,
                        journey,
                        evidence_root=evidence_root,
                    )
                except Exception:
                    generator.abort_card(
                        event_names=("formal_p5_browser_failed",),
                    )
                    raise
                else:
                    generator.end_card()
                version_response = client.get(
                    f"/api/v1/tasks/{task_id}/versions/1",
                    params={
                        "target": spec.target,
                        "publishing_identity_id": str(spec.publishing_identity_id),
                    },
                )
                if version_response.status_code != 200:
                    raise RuntimeError("P5 formal browser artifact is unavailable")
                result = cast(
                    dict[str, object],
                    version_response.json(),
                )
            else:
                result = _stream_card(
                    client,
                    generator,
                    spec,
                    series_id=series_id,
                )
                task_id = UUID(str(result["task_id"]))
            snapshot = _task_snapshot(
                database_url,
                journey.tenant_id,
                task_id,
            )
            raw_version = result.get("version")
            if not isinstance(raw_version, int) or raw_version < 1:
                raise RuntimeError("formal artifact version is unavailable")
            version_number = raw_version
            run_id, version_id = _persistence_ids(
                database_url,
                journey.tenant_id,
                task_id,
                version_number,
            )
            artifact = _artifact_document(
                spec.card_id,
                result,
                snapshot,
                task_id=task_id,
                run_id=run_id,
                version_id=version_id,
            )
            _write_private_json(
                evidence_root / f"{spec.card_id}.artifact.json",
                artifact,
            )
            summaries.append(
                {
                    "card_id": spec.card_id,
                    "task_id": str(task_id),
                    "run_id": str(run_id),
                    "version_id": str(version_id),
                    "version": version_number,
                    "visible_digest": artifact["visible_digest"],
                    "program_id": cast(
                        Mapping[str, object],
                        cast(
                            Mapping[str, object],
                            artifact["formal_snapshot"],
                        )["media_program"],
                    ).get("program_id"),
                }
            )
    _write_private_json(
        evidence_root / "generation-summary.json",
        {
            "suite_version": _SUITE_VERSION,
            "implementation_sha": implementation_sha,
            "formal_api": True,
            "database": True,
            "card_count": len(summaries),
            "cards": summaries,
        },
    )


def _reviews_from_file(path: Path) -> tuple[HumanReviewInput, ...]:
    document = _json_object(path)
    if set(document) != {"review_contract", "reviews"}:
        raise ValueError("human review document fields drifted")
    if document["review_contract"] != "ux03-gate-c-human-review-v3":
        raise ValueError("human review contract version drifted")
    raw_reviews = document["reviews"]
    if not isinstance(raw_reviews, list):
        raise ValueError("human review list is unavailable")
    reviews: list[HumanReviewInput] = []
    for raw in raw_reviews:
        if not isinstance(raw, dict):
            raise ValueError("human review record is invalid")
        if set(raw) != {
            "card_id",
            "artifact_file",
            "verdict",
            "criteria",
            "notes",
            "value_evidence",
        }:
            raise ValueError("human review record fields drifted")
        criteria = raw["criteria"]
        if not isinstance(criteria, dict) or set(criteria) != set(GATE_C_REVIEW_CRITERIA):
            raise ValueError("human review criteria coverage drifted")
        verdict = str(raw["verdict"])
        criterion_values = {criterion: str(criteria[criterion]) for criterion in GATE_C_REVIEW_CRITERIA}
        notes = str(raw["notes"]).strip()
        if verdict not in {"PASS", "FAIL"} or any(value not in {"PASS", "FAIL"} for value in criterion_values.values()):
            raise ValueError("human review verdict is invalid")
        if not notes:
            raise ValueError("human review note is unavailable")
        reviews.append(
            HumanReviewInput(
                card_id=str(raw["card_id"]),
                artifact_file=str(raw["artifact_file"]),
                verdict=verdict,
                criteria=criterion_values,
                notes=notes,
                value_evidence=(
                    cast(dict[str, object], raw["value_evidence"])
                    if isinstance(raw["value_evidence"], dict)
                    else None
                ),
            )
        )
    if {review.card_id for review in reviews} != GATE_C_FINAL_CARD_IDS or len(reviews) != len(GATE_C_FINAL_CARD_IDS):
        raise ValueError("human review does not cover the seven final cards")
    return tuple(reviews)


def _finalize(args: argparse.Namespace) -> None:
    evidence_root = Path(args.evidence_root).resolve()
    implementation_sha = _current_head()
    if implementation_sha != args.implementation_sha:
        raise RuntimeError("current HEAD is not the frozen implementation SHA")
    artifacts = tuple(
        ArtifactEvidenceInput(
            card_id=card_id,
            artifact_file=f"{card_id}.artifact.json",
            raw_response_file=f"{card_id}.raw.json",
        )
        for card_id in _CARDS
    )
    reviews = _reviews_from_file(Path(args.review_file).resolve())
    write_gate_c_evidence(
        evidence_root,
        implementation_sha=implementation_sha,
        model=_MODEL,
        temperature=0,
        max_retries=0,
        artifacts=artifacts,
        reviews=reviews,
        runtime=EvidenceRuntimeInput(
            database=True,
            formal_api=True,
            business_persistence=True,
        ),
    )
    _write_evidence_projection(
        evidence_root,
        Path(args.evidence_projection).resolve(),
    )
    print(
        json.dumps(
            {
                "evidence": "verified",
                "card_count": len(artifacts),
                "implementation_sha": implementation_sha,
            },
            sort_keys=True,
        )
    )


def _write_evidence_projection(source: Path, destination: Path) -> None:
    if destination.exists():
        raise RuntimeError("evidence projection already exists")
    destination.mkdir(mode=0o700, parents=True)
    destination.chmod(0o700)
    for filename in ("manifest.json", "human-review.json"):
        target = destination / filename
        shutil.copyfile(source / filename, target)
        target.chmod(0o600)
    _write_private_json(
        destination / "EVIDENCE_INDEX.json",
        {
            "projection_contract": "ux03-gate-c-evidence-index-v1",
            "projection_kind": "index",
            "private_evidence_root": str(source),
            "private_sha256sums_sha256": sha256_file(
                source / "SHA256SUMS"
            ),
            "note": (
                "此目录是可复算索引；原始响应和完整成品保留在上方私有目录。"
            ),
        },
    )
    projected_files = sorted(
        path
        for path in destination.iterdir()
        if path.is_file() and path.name != "SHA256SUMS"
    )
    checksum_lines = "".join(
        f"{sha256_file(path)}  {path.name}\n"
        for path in projected_files
    )
    checksum_path = destination / "SHA256SUMS"
    checksum_path.write_text(checksum_lines, encoding="utf-8")
    checksum_path.chmod(0o600)


def _json_object(path: Path) -> dict[str, object]:
    if path.stat().st_mode & 0o077:
        raise ValueError(f"{path.name} must be private")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain one JSON object")
    return cast(dict[str, object], value)


def _write_private_json(path: Path, value: object) -> None:
    content = (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            default=str,
        )
        + "\n"
    ).encode()
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
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


def _current_head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _git_status() -> str:
    return subprocess.run(
        ["git", "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.rstrip("\r\n")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run and bind the formal UX-03 Gate C final suite.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate = subparsers.add_parser("generate")
    generate.add_argument("--implementation-sha", required=True)
    generate.add_argument("--evidence-root", required=True)
    generate.add_argument("--journey-file", required=True)
    generate.set_defaults(action=_generate)
    finalize = subparsers.add_parser("finalize")
    finalize.add_argument("--implementation-sha", required=True)
    finalize.add_argument("--evidence-root", required=True)
    finalize.add_argument("--review-file", required=True)
    finalize.add_argument("--evidence-projection", required=True)
    finalize.set_defaults(action=_finalize)
    return parser


def main() -> None:
    os.umask(0o077)
    args = _parser().parse_args()
    action = cast(Any, args.action)
    action(args)


if __name__ == "__main__":
    main()
