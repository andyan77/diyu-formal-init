from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit
from urllib.request import urlopen
from uuid import UUID, uuid4

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient
from httpx import Response
from psycopg import sql

from src.brain.display_contract import assert_display_complete
from src.brain.display_service import DisplayService
from src.brain.dm01_display_compiler import (
    DM01DisplayCompiler,
    parse_hard_requirements,
    parse_revision_target,
)
from src.gateway.api.app import create_app
from src.gateway.api.contracts import CreateDisplayRequest
from src.gateway.api.settings import Settings
from src.infrastructure.display_repository import PostgresDisplayRepository
from src.infrastructure.dm01_store_seed import DM01StoreSeedWriter
from src.infrastructure.production_auth import ProductionAuthRepository
from src.infrastructure.seed_demo import BRAND_ID as DEMO_BRAND_ID
from src.infrastructure.seed_demo import TENANT_ID as DEMO_TENANT_ID
from src.shared.display_integrity import (
    assert_display_artifact_integrity,
    attach_display_artifact_audit,
)
from src.shared.dm01_rules import DM01RuleBundleV1
from src.shared.errors import DomainError, GenerationFailed
from src.shared.service_status import (
    ProviderObservation,
    ProviderStatusTracker,
    public_service_status,
)
from src.shared.types import DisplayContext, DisplayGenerationInput, DisplayScope
from src.tool.llm_gateway.deepseek import DeepSeekGenerator


def test_demo_seed_materializes_current_product_versions_after_migrations(
    migrator_database_url: str,
) -> None:
    expected_skus = {
        "ZX-C218",
        "ZX-S104",
        "ZX-K126",
        "ZX-P211",
        "ZX-V113",
        "ZX-Q117",
    }
    with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(DEMO_TENANT_ID),))
        cursor.execute(
            """
            SELECT product.sku, product.current_version_id, version.id,
                   product.display_name = version.display_name,
                   product.facts = version.facts,
                   product.fact_version = version.version_number
              FROM brand_products product
              LEFT JOIN brand_product_versions version
                ON version.tenant_id = product.tenant_id
               AND version.product_id = product.id
               AND version.id = product.current_version_id
             WHERE product.tenant_id = %s AND product.brand_id = %s
               AND product.sku = ANY(%s)
            """,
            (DEMO_TENANT_ID, DEMO_BRAND_ID, sorted(expected_skus)),
        )
        rows = cursor.fetchall()
    assert {str(row[0]) for row in rows} == expected_skus
    assert all(row[1] is not None and row[1] == row[2] for row in rows)
    assert all(bool(row[3]) and bool(row[4]) and bool(row[5]) for row in rows)


def _production_settings(database_url: str, material_root: Path) -> Settings:
    return Settings.model_validate(
        {
            "DIYU_RUNTIME_MODE": "production",
            "DIYU_APP_DATABASE_URL": database_url,
            "DIYU_SESSION_SECRET": "ux03-gate-d-local-session-secret",
            "DIYU_PUBLIC_URL": "https://diyu.example",
            "DIYU_GENERATOR_MODE": "deepseek",
            "DEEPSEEK_API_BASE_URL": "https://example.invalid",
            "DEEPSEEK_API_KEY": "local-test-placeholder",
            "DEEPSEEK_MODEL": "deepseek-v4-flash",
            "DIYU_MATERIAL_STORAGE_ROOT": str(material_root),
            "DIYU_S3_ENDPOINT_URL": "http://127.0.0.1:9000",
            "DIYU_S3_BUCKET": "diyu-test",
            "DIYU_S3_ACCESS_KEY_ID": "local-test-placeholder",
            "DIYU_S3_SECRET_ACCESS_KEY": "local-test-placeholder",
        }
    )


def _activate(client: TestClient, url: str, password: str) -> None:
    response = client.post(
        urlsplit(url).path,
        content=f"password={password}&password_confirm={password}",
        follow_redirects=False,
    )
    assert response.status_code == 303


def _login(client: TestClient, username: str, password: str, path: str) -> None:
    response = client.post(
        path,
        content=f"username={username}&password={password}",
        follow_redirects=False,
    )
    assert response.status_code == 303


def _create_test_operator(
    database_url: str,
    repository: ProductionAuthRepository,
    username: str,
    password: str,
) -> tuple[UUID, str]:
    operator_id = uuid4()
    secret = repository._totp_secret()
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO platform_operators (id, username, password_hash, totp_secret) VALUES (%s,%s,%s,%s)",
            (operator_id, username, repository._password_hash(password), secret),
        )
    return operator_id, secret


def _run_gate_d_browser(
    app_database_url: str,
    material_root: Path,
    username: str,
    password: str,
) -> subprocess.CompletedProcess[str]:
    with socket.socket() as port_socket:
        port_socket.bind(("127.0.0.1", 0))
        port = int(port_socket.getsockname()[1])
    base_url = f"http://127.0.0.1:{port}"
    environment = {
        **os.environ,
        "DIYU_RUNTIME_MODE": "production",
        "DIYU_APP_DATABASE_URL": app_database_url,
        "DIYU_SESSION_SECRET": "ux03-gate-d-browser-session-secret",
        "DIYU_PUBLIC_URL": "https://diyu.example",
        "DIYU_GENERATOR_MODE": "deepseek",
        "DEEPSEEK_API_BASE_URL": "https://example.invalid",
        "DEEPSEEK_API_KEY": "local-browser-placeholder",
        "DEEPSEEK_MODEL": "deepseek-v4-flash",
        "DIYU_MATERIAL_STORAGE_ROOT": str(material_root),
        "DIYU_S3_ENDPOINT_URL": "http://127.0.0.1:9000",
        "DIYU_S3_BUCKET": "diyu-test",
        "DIYU_S3_ACCESS_KEY_ID": "local-browser-placeholder",
        "DIYU_S3_SECRET_ACCESS_KEY": "local-browser-placeholder",
    }
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "src.gateway.api.app:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(100):
            if server.poll() is not None:
                raise AssertionError("Gate D browser API server exited early")
            try:
                with urlopen(f"{base_url}/status", timeout=0.2) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(0.1)
        else:
            raise AssertionError("Gate D browser API server did not become ready")
        return subprocess.run(
            ["node", "frontend/test/ux03-gate-d-browser.mjs"],
            cwd=Path(__file__).resolve().parents[1],
            env={
                **os.environ,
                "UX03_GATE_D_BASE_URL": base_url,
                "UX03_GATE_D_USERNAME": username,
                "UX03_GATE_D_PASSWORD": password,
            },
            capture_output=True,
            text=True,
            timeout=180,
        )
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)


def _counts(database_url: str, tenant_id: UUID) -> tuple[int, int, int, int, int]:
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),))
        cursor.execute(
            """
            SELECT
              (SELECT count(*) FROM display_tasks WHERE tenant_id=%s),
              (SELECT count(*) FROM display_generation_runs WHERE tenant_id=%s),
              (SELECT count(*) FROM display_artifact_versions WHERE tenant_id=%s),
              (SELECT count(*) FROM display_generation_runs WHERE tenant_id=%s AND status='failed'),
              (SELECT count(*) FROM display_generation_runs WHERE tenant_id=%s AND status='running')
            """,
            (tenant_id, tenant_id, tenant_id, tenant_id, tenant_id),
        )
        row = cursor.fetchone()
    assert row is not None
    return tuple(int(item) for item in row)  # type: ignore[return-value]


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _write_evidence(document: dict[str, object]) -> None:
    raw_directory = os.environ.get("DIYU_UX03_GATE_D_EVIDENCE_DIR")
    if raw_directory is None:
        return
    directory = Path(raw_directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = directory / "formal-dm01-journey.json"
    path.write_text(
        json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def _cleanup(database_url: str, tenant_id: UUID, operator_id: UUID) -> None:
    tenant_tables = (
        "activity_events",
        "account_expression_profile_versions",
        "account_content_roles",
        "auth_grants",
        "tenant_management_grants",
        "display_access_grants",
        "organization_material_maintainers",
        "content_accounts",
        "content_roles",
        "brand_expression_baselines",
        "tenant_sessions",
        "user_activation_tokens",
        "user_credentials",
        "brand_product_scope_organizations",
        "brand_product_versions",
        "brand_products",
        "users",
        "brand_audiences",
        "brands",
        "organizations",
    )
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT id FROM display_artifact_versions WHERE tenant_id=%s ORDER BY id",
            (tenant_id,),
        )
        for (version_id,) in cursor.fetchall():
            cursor.execute("SELECT set_config('diyu.display_version_maintenance', 'delete_synthetic_fixture', true)")
            cursor.execute(
                "SELECT set_config('diyu.display_version_maintenance_transaction_id', pg_current_xact_id()::text, true)"
            )
            cursor.execute(
                "SELECT set_config('diyu.display_version_maintenance_tenant_id', %s, true)",
                (str(tenant_id),),
            )
            cursor.execute(
                "SELECT set_config('diyu.display_version_maintenance_version_id', %s, true)",
                (str(version_id),),
            )
            cursor.execute(
                "DELETE FROM display_artifact_versions WHERE tenant_id=%s AND id=%s",
                (tenant_id, version_id),
            )
        for table in (
            "display_artifacts",
            "display_generation_runs",
            "display_tasks",
            "display_policies",
            "display_stores",
        ):
            cursor.execute(f"DELETE FROM {table} WHERE tenant_id=%s", (tenant_id,))  # noqa: S608
        cursor.execute("UPDATE brand_products SET current_version_id=NULL WHERE tenant_id=%s", (tenant_id,))
        for table in tenant_tables:
            trigger = "brand_product_versions_immutable" if table == "brand_product_versions" else None
            if trigger is not None:
                cursor.execute(f"ALTER TABLE {table} DISABLE TRIGGER {trigger}")  # noqa: S608
            try:
                cursor.execute(f"DELETE FROM {table} WHERE tenant_id=%s", (tenant_id,))  # noqa: S608
            finally:
                if trigger is not None:
                    cursor.execute(f"ALTER TABLE {table} ENABLE TRIGGER {trigger}")  # noqa: S608
        cursor.execute("DELETE FROM ops_tenant_registry WHERE tenant_id=%s", (tenant_id,))
        cursor.execute("DELETE FROM tenants WHERE id=%s", (tenant_id,))
        cursor.execute("DELETE FROM platform_sessions WHERE operator_id=%s", (operator_id,))
        cursor.execute("DELETE FROM ops_audit_events WHERE operator_id=%s", (operator_id,))
        cursor.execute("DELETE FROM platform_operators WHERE id=%s", (operator_id,))
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        for table in (
            "display_artifact_versions",
            "display_artifacts",
            "display_generation_runs",
            "display_tasks",
            "display_policies",
            "display_stores",
            *tenant_tables,
        ):
            cursor.execute(f"SELECT count(*) FROM {table} WHERE tenant_id=%s", (tenant_id,))  # noqa: S608
            assert cursor.fetchone() == (0,), table
        cursor.execute("SELECT count(*) FROM ops_tenant_registry WHERE tenant_id=%s", (tenant_id,))
        assert cursor.fetchone() == (0,)
        cursor.execute("SELECT count(*) FROM tenants WHERE id=%s", (tenant_id,))
        assert cursor.fetchone() == (0,)
        cursor.execute("SELECT count(*) FROM platform_sessions WHERE operator_id=%s", (operator_id,))
        assert cursor.fetchone() == (0,)
        cursor.execute("SELECT count(*) FROM ops_audit_events WHERE operator_id=%s", (operator_id,))
        assert cursor.fetchone() == (0,)
        cursor.execute("SELECT count(*) FROM platform_operators WHERE id=%s", (operator_id,))
        assert cursor.fetchone() == (0,)


@contextmanager
def _without_rule_activation(database_url: str, asset_id: str) -> Iterator[None]:
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            "DELETE FROM system_asset_activations WHERE asset_id=%s RETURNING consumer,applicability",
            (asset_id,),
        )
        row = cursor.fetchone()
        assert row is not None
    try:
        yield
    finally:
        with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO system_asset_activations (asset_id,consumer,applicability) VALUES (%s,%s,%s)",
                (asset_id, row[0], row[1]),
            )


@contextmanager
def _reject_display_finalize(database_url: str, failure: str) -> Iterator[None]:
    suffix = uuid4().hex
    function_name = f"ux03_gate_d_fail_{suffix}"
    trigger_name = f"ux03_gate_d_trigger_{suffix}"
    if failure == "version_insert":
        table = "display_artifact_versions"
        trigger_clause = sql.SQL("BEFORE INSERT")
        defer_clause = sql.SQL("")
    elif failure == "artifact_pointer":
        table = "display_artifacts"
        trigger_clause = sql.SQL("BEFORE UPDATE OF current_version")
        defer_clause = sql.SQL("")
    elif failure == "commit":
        table = "display_artifact_versions"
        trigger_clause = sql.SQL("AFTER INSERT")
        defer_clause = sql.SQL("DEFERRABLE INITIALLY DEFERRED")
    else:
        raise ValueError("unknown display finalize failure")
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            sql.SQL(
                "CREATE FUNCTION {}() RETURNS trigger LANGUAGE plpgsql "
                "AS 'BEGIN RAISE EXCEPTION ''synthetic display finalize failure''; END'"
            ).format(sql.Identifier(function_name))
        )
        constraint = sql.SQL("CONSTRAINT ") if failure == "commit" else sql.SQL("")
        cursor.execute(
            sql.SQL("CREATE {}TRIGGER {} {} ON {} {} FOR EACH ROW EXECUTE FUNCTION {}()").format(
                constraint,
                sql.Identifier(trigger_name),
                trigger_clause,
                sql.Identifier(table),
                defer_clause,
                sql.Identifier(function_name),
            )
        )
    try:
        yield
    finally:
        with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("DROP TRIGGER IF EXISTS {} ON {}").format(
                    sql.Identifier(trigger_name),
                    sql.Identifier(table),
                )
            )
            cursor.execute(sql.SQL("DROP FUNCTION IF EXISTS {}()").format(sql.Identifier(function_name)))


def test_public_status_requires_a_fresh_real_provider_observation() -> None:
    now = datetime(2026, 7, 31, 12, tzinfo=timezone.utc)
    unknown = public_service_status(core_ready=True, provider_observation=None, now=now)
    assert unknown["content_generation"] == {
        "state": "unknown",
        "observed_at": None,
        "fresh_until": None,
    }
    assert unknown["text_display"] == {"state": "available"}

    recent = public_service_status(
        core_ready=True,
        provider_observation=ProviderObservation("available", now - timedelta(minutes=2)),
        now=now,
    )
    assert recent["content_generation"]["state"] == "available"  # type: ignore[index]
    stale = public_service_status(
        core_ready=True,
        provider_observation=ProviderObservation("available", now - timedelta(minutes=16)),
        now=now,
    )
    assert stale["content_generation"]["state"] == "unknown"  # type: ignore[index]
    degraded = public_service_status(
        core_ready=True,
        provider_observation=ProviderObservation("degraded", now),
        now=now,
    )
    assert degraded["core"] == {"state": "available"}
    assert degraded["content_generation"]["state"] == "degraded"  # type: ignore[index]
    assert degraded["text_display"] == {"state": "available"}

    core_failure = public_service_status(
        core_ready=False,
        provider_observation=ProviderObservation("available", now),
        now=now,
    )
    assert core_failure["core"] == {"state": "unavailable"}
    assert core_failure["content_generation"]["state"] == "unavailable"  # type: ignore[index]
    assert core_failure["text_display"] == {"state": "unavailable"}

    future = public_service_status(
        core_ready=True,
        provider_observation=ProviderObservation("available", now + timedelta(seconds=1)),
        now=now,
    )
    assert future["content_generation"]["state"] == "unknown"  # type: ignore[index]


def test_display_request_accepts_structured_current_product_versions() -> None:
    first_version, second_version = uuid4(), uuid4()
    request = CreateDisplayRequest.model_validate(
        {
            "inventory_text": "本次按已选商品生成。",
            "products": [
                {"product_version_id": str(first_version), "quantity": 2},
                {"product_version_id": str(second_version), "quantity": 1},
            ],
        }
    )
    assert [(item.product_version_id, item.quantity) for item in request.products] == [
        (first_version, 2),
        (second_version, 1),
    ]


def test_provider_tracker_starts_unknown_and_never_carries_sensitive_details() -> None:
    tracker = ProviderStatusTracker()
    assert tracker.snapshot() is None
    tracker.record("unavailable", datetime.now(timezone.utc))
    document = public_service_status(core_ready=True, provider_observation=tracker.snapshot())
    serialized = str(document).casefold()
    assert document["content_generation"]["state"] == "unavailable"  # type: ignore[index]
    assert all(word not in serialized for word in ("deepseek", "api_key", "prompt", "database", "s3"))


def test_public_status_api_is_observational_and_does_not_probe_a_model(
    app_database_url: str,
) -> None:
    zero = "00000000-0000-0000-0000-000000000000"
    settings = Settings.model_validate(
        {
            "DIYU_RUNTIME_MODE": "test",
            "DIYU_APP_DATABASE_URL": app_database_url,
            "DIYU_SESSION_SECRET": "ux03-gate-d-status-secret",
            "DIYU_DEMO_TENANT_ID": zero,
            "DIYU_DEMO_USER_ID": zero,
            "DIYU_DEMO_BRAND_ID": zero,
            "DIYU_DEMO_ACCOUNT_ID": zero,
        }
    )
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.get("/api/v1/status")
        page = client.get("/status")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["core"] == {"state": "available"}
    assert response.json()["content_generation"]["state"] == "unknown"
    assert response.json()["text_display"] == {"state": "available"}
    assert page.headers["cache-control"] == "no-store"
    assert "核心服务" in page.text and "内容生成" in page.text and "纯文字陈列参考方案" in page.text
    assert "笛语当前可以使用" not in page.text


def test_core_failure_dominates_api_and_no_script_status_projection(
    app_database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("src.gateway.api.app.S3ObjectStore.is_ready", lambda _: False)
    app = create_app(_production_settings(app_database_url, tmp_path / "unavailable-status"))
    app.state.provider_status.record("available")
    with TestClient(app) as client:
        contract = client.get("/api/v1/status")
        page = client.get("/status")
    assert contract.json()["core"] == {"state": "unavailable"}
    assert contract.json()["content_generation"]["state"] == "unavailable"
    assert contract.json()["text_display"] == {"state": "unavailable"}
    assert page.headers["cache-control"] == "no-store"
    assert "笛语暂时无法接单" in page.text
    assert page.text.count("暂时不可用") >= 3


def test_provider_429_is_degraded_without_affecting_core_readiness(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *args: object) -> None:
            del args

        def post(self, *args: object, **kwargs: object) -> Response:
            del args, kwargs
            return Response(429, json={"error": {"message": "rate limited"}})

    monkeypatch.setattr("src.tool.llm_gateway.deepseek.httpx.Client", FakeClient)
    tracker = ProviderStatusTracker()
    generator = DeepSeekGenerator(
        "https://example.invalid",
        "test-placeholder",
        "test-model",
        max_retries=0,
        status_tracker=tracker,
    )
    with pytest.raises(GenerationFailed):
        generator._request("system", "prompt", 20)
    status = public_service_status(core_ready=True, provider_observation=tracker.snapshot())
    assert status["core"] == {"state": "available"}
    assert status["content_generation"]["state"] == "degraded"  # type: ignore[index]
    assert status["text_display"] == {"state": "available"}


@pytest.mark.parametrize(
    ("status_code", "error_code", "error_type"),
    (
        (400, "content_filter", "invalid_request_error"),
        (403, "content_filter", "invalid_request_error"),
        (400, "context_length_exceeded", "invalid_request_error"),
        (400, "input_length", "invalid_request_error"),
        (400, "invalid_max_tokens", "invalid_request_error"),
        (403, "invalid_parameter", "invalid_request_error"),
        (404, "invalid_response_format", "invalid_request_error"),
        (403, "", "content_filter"),
        (404, "provider_specific_request_code", "invalid_response_format"),
    ),
)
def test_request_scoped_provider_4xx_does_not_pollute_global_observation(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    error_code: str,
    error_type: str,
) -> None:
    class FakeClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *args: object) -> None:
            del args

        def post(self, *args: object, **kwargs: object) -> Response:
            del args, kwargs
            return Response(
                status_code,
                json={
                    "error": {
                        "code": error_code,
                        "type": error_type,
                        "message": "request rejected",
                    }
                },
            )

    monkeypatch.setattr("src.tool.llm_gateway.deepseek.httpx.Client", FakeClient)
    tracker = ProviderStatusTracker()
    generator = DeepSeekGenerator(
        "https://example.invalid",
        "test-placeholder",
        "test-model",
        max_retries=0,
        status_tracker=tracker,
    )
    with pytest.raises(GenerationFailed):
        generator._request("system", "prompt", 20)
    assert tracker.snapshot() is None

    tracker.record("available")
    before = tracker.snapshot()
    with pytest.raises(GenerationFailed):
        generator._request("system", "prompt", 20)
    assert tracker.snapshot() == before


@pytest.mark.parametrize(
    ("status_code", "error_code", "expected"),
    (
        (401, "invalid_api_key", "unavailable"),
        (403, "permission_denied", "unavailable"),
        (404, "model_not_found", "unavailable"),
        (429, "rate_limit_exceeded", "degraded"),
        (503, "provider_unavailable", "unavailable"),
    ),
)
def test_provider_availability_errors_update_only_the_normalized_state(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    error_code: str,
    expected: str,
) -> None:
    class FakeClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *args: object) -> None:
            del args

        def post(self, *args: object, **kwargs: object) -> Response:
            del args, kwargs
            return Response(
                status_code,
                json={"error": {"code": error_code, "type": "provider_error"}},
            )

    monkeypatch.setattr("src.tool.llm_gateway.deepseek.httpx.Client", FakeClient)
    tracker = ProviderStatusTracker()
    generator = DeepSeekGenerator(
        "https://example.invalid",
        "test-placeholder",
        "test-model",
        max_retries=0,
        status_tracker=tracker,
    )
    with pytest.raises(GenerationFailed):
        generator._request("system", "prompt", 20)
    observation = tracker.snapshot()
    assert observation is not None and observation.state == expected


def test_provider_transport_failure_and_success_update_availability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class TransportFailureClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

        def __enter__(self) -> TransportFailureClient:
            return self

        def __exit__(self, *args: object) -> None:
            del args

        def post(self, *args: object, **kwargs: object) -> Response:
            del args, kwargs
            raise httpx.ConnectError("synthetic transport failure")

    tracker = ProviderStatusTracker()
    generator = DeepSeekGenerator(
        "https://example.invalid",
        "test-placeholder",
        "test-model",
        max_retries=0,
        status_tracker=tracker,
    )
    monkeypatch.setattr("src.tool.llm_gateway.deepseek.httpx.Client", TransportFailureClient)
    with pytest.raises(GenerationFailed):
        generator._request("system", "prompt", 20)
    failed = tracker.snapshot()
    assert failed is not None and failed.state == "unavailable"

    class SuccessfulClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

        def __enter__(self) -> SuccessfulClient:
            return self

        def __exit__(self, *args: object) -> None:
            del args

        def post(self, *args: object, **kwargs: object) -> Response:
            del args, kwargs
            return Response(200, json={"choices": []})

    monkeypatch.setattr("src.tool.llm_gateway.deepseek.httpx.Client", SuccessfulClient)
    generator._request("system", "prompt", 20)
    succeeded = tracker.snapshot()
    assert succeeded is not None and succeeded.state == "available"


def test_health_ready_does_not_depend_on_provider_observation(
    app_database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("src.gateway.api.app.S3ObjectStore.is_ready", lambda _: True)
    app = create_app(_production_settings(app_database_url, tmp_path / "status-materials"))
    app.state.provider_status.record("unavailable")
    with TestClient(app) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").status_code == 200
        status = client.get("/api/v1/status").json()
    assert status["core"] == {"state": "available"}
    assert status["content_generation"]["state"] == "unavailable"
    assert status["text_display"] == {"state": "available"}


def test_rule_bundle_is_a_compiler_dependency(app_database_url: str) -> None:
    repository = PostgresDisplayRepository(app_database_url)
    bundle = repository.load_rule_bundle()
    assert len(bundle.generation_assets) == 11
    assert len(bundle.revision_assets) == 13
    with pytest.raises(GenerationFailed):
        DM01DisplayCompiler().generate(
            DisplayGenerationInput(
                uuid4(),
                uuid4(),
                (("UP-01", 1), ("LOW-01", 1)),
                # Removing a governed generation asset must fail before layout logic can run.
                _minimal_context(replace(bundle, generation_assets=bundle.generation_assets[:-1])),
                (),
            )
        )


def test_inventory_conservation_and_formal_rail_are_checked(app_database_url: str) -> None:
    bundle = PostgresDisplayRepository(app_database_url).load_rule_bundle()
    context = _minimal_context(bundle)
    inventory = (("UP-01", 2), ("LOW-01", 2))
    artifact = DM01DisplayCompiler().generate(DisplayGenerationInput(uuid4(), uuid4(), inventory, context, ()))
    assert_display_complete(artifact, inventory, product_facts=dict(context.products))

    missing_proof = deepcopy(artifact.plan)
    conservation = cast(dict[str, object], missing_proof["inventory_conservation"])
    conservation.pop("UP-01")
    with pytest.raises(GenerationFailed, match="逐商品库存守恒"):
        assert_display_complete(replace(artifact, plan=missing_proof), inventory, product_facts=dict(context.products))

    wrong_rail = deepcopy(artifact.plan)
    layout = cast(dict[str, object], wrong_rail["layout"])
    zones = cast(dict[str, dict[str, object]], layout["zones"])
    upper_slots = cast(list[dict[str, object]], zones["right"]["upper"])
    moved = upper_slots.pop(0)
    cast(list[dict[str, object]], zones["right"]["lower"]).append(moved)
    with pytest.raises(GenerationFailed, match="正式陈列属性"):
        assert_display_complete(replace(artifact, plan=wrong_rail), inventory, product_facts=dict(context.products))


def test_display_artifact_audit_binds_body_and_plan() -> None:
    body = "纯文字陈列参考方案。"
    plan: dict[str, object] = {"schema": "dm01-plan-v2", "inventory_conservation": {}}
    audited = attach_display_artifact_audit(body, plan)
    assert assert_display_artifact_integrity(body, audited) == audited
    with pytest.raises(DomainError, match="完整性校验失败"):
        assert_display_artifact_integrity(body + "被篡改", audited)
    tampered = deepcopy(audited)
    tampered["schema"] = "tampered"
    with pytest.raises(DomainError, match="完整性校验失败"):
        assert_display_artifact_integrity(body, tampered)


def _minimal_context(rule_bundle: DM01RuleBundleV1) -> DisplayContext:
    return DisplayContext(
        "测试品牌",
        "测试门店组织",
        "测试用户",
        "dm01-default-v1",
        {"schema": "dm01-wall-double-rail-v1"},
        "测试门店",
        "1.0",
        {
            "schema": "dm01-wall-double-rail-v1",
            "upper_comfort_capacity": 3,
            "lower_comfort_capacity": 3,
            "primary_position": "right",
            "secondary_position": "left",
            "approach": "right",
            "lower_reserved_positions": [],
            "avoid_long_upper_lower_overlap": False,
            "golden_sight": "视线中心",
            "constraints": ["保持通道"],
        },
        (
            ("UP-01", {"name": "上装", "display_family": "upper"}),
            ("LOW-01", {"name": "下装", "display_family": "lower"}),
        ),
        rule_bundle=rule_bundle,
    )


def _product_reference_context(rule_bundle: DM01RuleBundleV1) -> DisplayContext:
    return replace(
        _minimal_context(rule_bundle),
        products=(
            ("abc-123", {"name": "小写编号商品", "display_family": "upper"}),
            ("ABC123", {"name": "无连字符字母商品", "display_family": "lower"}),
            ("123456", {"name": "纯数字编号商品", "display_family": "upper"}),
            ("款号一", {"name": "中文编号商品", "display_family": "lower"}),
            ("GD-UP-01", {"name": "既有编号商品", "display_family": "upper"}),
            ("DUP-01", {"name": "重复名称", "display_family": "upper"}),
            ("DUP-02", {"name": "重复名称", "display_family": "lower"}),
        ),
    )


@pytest.mark.parametrize(
    ("reference", "expected_sku"),
    (
        ("abc-123", "abc-123"),
        ("ABC123", "ABC123"),
        ("123456", "123456"),
        ("款号一", "款号一"),
        ("GD-UP-01", "GD-UP-01"),
        ("中文编号商品", "款号一"),
    ),
)
def test_hard_requirements_resolve_only_frozen_product_identity(
    app_database_url: str,
    reference: str,
    expected_sku: str,
) -> None:
    context = _product_reference_context(PostgresDisplayRepository(app_database_url).load_rule_bundle())
    requirements, clarification = parse_hard_requirements(f"{reference} 必须保留。", context)
    assert clarification is None
    assert requirements == frozenset({expected_sku})


def test_hard_requirements_accept_multiple_explicit_products_and_close_ambiguity(
    app_database_url: str,
) -> None:
    context = _product_reference_context(PostgresDisplayRepository(app_database_url).load_rule_bundle())
    requirements, clarification = parse_hard_requirements(
        "abc-123 与 中文编号商品务必保留；GD-UP-01 不得更换。",
        context,
    )
    assert clarification is None
    assert requirements == frozenset({"abc-123", "款号一", "GD-UP-01"})

    for text in ("重复名称必须保留。", "未知商品必须保留。", "必须保留主推商品。"):
        requirements, clarification = parse_hard_requirements(text, context)
        assert requirements == frozenset()
        assert clarification is not None and "商品编号或完整商品名称" in clarification

    requirements, clarification = parse_hard_requirements("请不要把 abc-123 保留。", context)
    assert requirements == frozenset()
    assert clarification is None


@pytest.mark.parametrize(
    ("text", "expected_skus"),
    (
        ("abc-123 必须保留。", frozenset({"abc-123"})),
        ("abc-123必须保留。", frozenset({"abc-123"})),
        ("abc-123 必须留在主焦点。", frozenset({"abc-123"})),
        ("ABC123 必须保留。", frozenset({"ABC123"})),
        ("123456 必须保留。", frozenset({"123456"})),
        ("款号一必须保留。", frozenset({"款号一"})),
        ("GD-UP-01 不得更换。", frozenset({"GD-UP-01"})),
        ("请把 abc-123 保留。", frozenset({"abc-123"})),
        ("中文编号商品务必保留。", frozenset({"款号一"})),
        ("abc-123 与 中文编号商品务必保留。", frozenset({"abc-123", "款号一"})),
        ("abc-123、ABC123必须保留。", frozenset({"abc-123", "ABC123"})),
        ("abc-123与中文编号商品务必保留。", frozenset({"abc-123", "款号一"})),
        ("款号一及GD-UP-01必须保留。", frozenset({"款号一", "GD-UP-01"})),
        ("请把 abc-123 和 ABC123 保留。", frozenset({"abc-123", "ABC123"})),
        ("ABC-123 必须保留。", frozenset({"abc-123"})),
    ),
)
def test_hard_requirements_accept_complete_references_in_natural_sentences(
    app_database_url: str,
    text: str,
    expected_skus: frozenset[str],
) -> None:
    context = _product_reference_context(PostgresDisplayRepository(app_database_url).load_rule_bundle())
    requirements, clarification = parse_hard_requirements(text, context)
    assert clarification is None
    assert requirements == expected_skus


@pytest.mark.parametrize(
    "text",
    (
        "abc-1234 必须保留。",
        "Xabc-123 必须保留。",
        "ABC123X 必须保留。",
        "小写编号商品升级款必须保留。",
        "升级款小写编号商品必须保留。",
        "小写编号商品保留款必须保留。",
        "完全未知商品必须保留。",
        "必须保留主推商品。",
        "重复名称必须保留。",
    ),
)
def test_hard_requirements_reject_neighbouring_or_non_unique_references(
    app_database_url: str,
    text: str,
) -> None:
    context = _product_reference_context(PostgresDisplayRepository(app_database_url).load_rule_bundle())
    requirements, clarification = parse_hard_requirements(text, context)
    assert requirements == frozenset()
    assert clarification is not None and "商品编号或完整商品名称" in clarification


@pytest.mark.parametrize(
    "text",
    (
        "abc-123、完全未知商品必须保留。",
        "完全未知商品、abc-123必须保留。",
        "abc-123 与 重复名称必须保留。",
        "abc-123 与 ABC123X 必须保留。",
        "abc-123、中文编号商品升级款必须保留。",
    ),
)
def test_hard_requirements_reject_the_whole_mixed_reference_clause(
    app_database_url: str,
    text: str,
) -> None:
    context = _product_reference_context(PostgresDisplayRepository(app_database_url).load_rule_bundle())
    requirements, clarification = parse_hard_requirements(text, context)
    assert requirements == frozenset()
    assert clarification is not None and "商品编号或完整商品名称" in clarification


def test_revision_target_reuses_frozen_product_identity_without_sku_rules(
    app_database_url: str,
) -> None:
    context = _product_reference_context(PostgresDisplayRepository(app_database_url).load_rule_bundle())
    assert parse_revision_target("中间上杆 abc-123 太挤，请减少一件。", context) == (
        "abc-123",
        "center",
        "upper",
    )
    assert parse_revision_target("左侧下杆 中文编号商品太挤，请减少一件。", context) == (
        "款号一",
        "left",
        "lower",
    )
    assert parse_revision_target("请把中间上杆的 abc-123 减少一件。", context) == (
        "abc-123",
        "center",
        "upper",
    )
    assert parse_revision_target("左侧下杆 重复名称太挤，请减少一件。", context) is None
    for text in (
        "中间上杆 abc-1234 太挤，请减少一件。",
        "中间上杆 Xabc-123 太挤，请减少一件。",
        "中间上杆 ABC123X 太挤，请减少一件。",
        "中间上杆 小写编号商品升级款太挤，请减少一件。",
        "中间上杆 升级款小写编号商品太挤，请减少一件。",
        "中间上杆 小写编号商品保留款太挤，请减少一件。",
        "中间上杆 完全未知商品太挤，请减少一件。",
        "中间上杆 abc-123 和 完全未知商品太挤，请减少一件。",
        "中间上杆 完全未知商品 和 abc-123 太挤，请减少一件。",
        "中间上杆 abc-123 和 重复名称太挤，请减少一件。",
        "中间上杆 abc-123 和 ABC123 太挤，请减少一件。",
    ):
        assert parse_revision_target(text, context) is None


def test_formal_dm01_v1_v2_uses_product_versions_and_frozen_rules(
    app_database_url: str,
    migrator_database_url: str,
    tmp_path: Path,
) -> None:
    auth = ProductionAuthRepository(app_database_url)
    suffix = uuid4().hex[:10]
    ops_username = f"ux03-d-ops-{suffix}"
    ops_password = "ux03-gate-d-ops-password"
    tenant_name = f"UX03 Gate D synthetic {suffix}"
    operator_id, secret = _create_test_operator(migrator_database_url, auth, ops_username, ops_password)
    app = create_app(_production_settings(app_database_url, tmp_path / "materials"))
    tenant_id: UUID | None = None
    try:
        with TestClient(app, base_url="https://diyu.example") as ops:
            login = ops.post(
                "/ops/login",
                content=(
                    f"username={ops_username}&password={ops_password}"
                    f"&totp_code={auth._totp_code(secret, int(time.time() // 30))}"
                ),
                follow_redirects=False,
            )
            assert login.status_code == 303
            created = ops.post(
                "/api/v1/ops/tenants",
                json={
                    "tenant_name": tenant_name,
                    "administrator_name": "Gate D 管理员",
                    "administrator_username": f"ux03-d-admin-{suffix}",
                },
            )
            assert created.status_code == 201
            tenant = created.json()
            tenant_id = UUID(tenant["tenant_id"])
        with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT id FROM brands WHERE tenant_id=%s", (tenant_id,))
            brand_row = cursor.fetchone()
            assert brand_row is not None
            brand_id = UUID(str(brand_row[0]))

        with TestClient(app, base_url="https://diyu.example") as admin:
            admin_password = "ux03-gate-d-admin-password"
            _activate(admin, tenant["activation_url"], admin_password)
            _login(admin, tenant["username"], admin_password, "/tenant-admin/login")
            headquarters = admin.get("/api/v1/tenant-management/organizations").json()[0]
            region = admin.post(
                "/api/v1/tenant-management/organizations",
                json={
                    "name": "Gate D 区域",
                    "organization_level": "region",
                    "parent_organization_id": headquarters["id"],
                    "as_synthetic_business_fixture": True,
                },
            ).json()
            store = admin.post(
                "/api/v1/tenant-management/organizations",
                json={
                    "name": "Gate D 门店",
                    "organization_level": "operating_unit",
                    "parent_organization_id": region["id"],
                    "as_synthetic_business_fixture": True,
                },
            ).json()
            sibling_region = admin.post(
                "/api/v1/tenant-management/organizations",
                json={
                    "name": "Gate D 兄弟区域",
                    "organization_level": "region",
                    "parent_organization_id": headquarters["id"],
                    "as_synthetic_business_fixture": True,
                },
            ).json()
            member = admin.post(
                "/api/v1/tenant-management/users",
                json={
                    "display_name": "Gate D 陈列用户",
                    "username": f"ux03-d-user-{suffix}",
                    "organization_id": store["id"],
                    "entry_type": "tenant_user",
                    "capabilities": [],
                    "publishing_identity_ids": [],
                    "expression_profile_maintenance_account_ids": [],
                },
            )
            assert member.status_code == 201, member.text
            product_payloads = (
                ("abc-123", "小写编号商品", "upper", 2),
                ("ABC123", "无连字符字母商品", "lower", 2),
                ("123456", "纯数字编号商品", "upper", 1),
                ("款号一", "中文编号商品", "lower", 1),
                ("GD-UP-01", "既有编号商品", "upper", 2),
                ("GD-PENDING-01", "资料待补商品", None, 1),
                ("DUP-01", "重复名称", "upper", 1),
                ("DUP-02", "重复名称", "lower", 1),
            )
            for sku, name, family, _ in product_payloads:
                response = admin.put(
                    "/api/v1/tenant-management/brand-products",
                    json={
                        "sku": sku,
                        "display_name": name,
                        "category": "服装",
                        "colors": [],
                        "material_or_structure": "",
                        "silhouette": "",
                        "observable_features": "",
                        "display_family": family,
                        "source_note": "Gate D synthetic 管理员确认",
                        "applicability": "Gate D 门店陈列",
                        "confirm_as_current_brand_fact": True,
                        "as_synthetic_business_fixture": True,
                        "visibility_scope": "organizations",
                        "organization_ids": [region["id"]],
                    },
                )
                assert response.status_code == 200, response.text
            sibling_product = admin.put(
                "/api/v1/tenant-management/brand-products",
                json={
                    "sku": "GD-SIBLING-01",
                    "display_name": "兄弟区域诱饵",
                    "category": "服装",
                    "colors": [],
                    "material_or_structure": "",
                    "silhouette": "",
                    "observable_features": "",
                    "display_family": "upper",
                    "source_note": "Gate D synthetic 兄弟区域",
                    "applicability": "仅兄弟区域",
                    "confirm_as_current_brand_fact": True,
                    "as_synthetic_business_fixture": True,
                    "visibility_scope": "organizations",
                    "organization_ids": [sibling_region["id"]],
                },
            )
            assert sibling_product.status_code == 200
            inactive_product = admin.put(
                "/api/v1/tenant-management/brand-products",
                json={
                    "sku": "GD-INACTIVE-01",
                    "display_name": "停用商品诱饵",
                    "category": "服装",
                    "colors": [],
                    "material_or_structure": "",
                    "silhouette": "",
                    "observable_features": "",
                    "display_family": "upper",
                    "source_note": "Gate D synthetic 停用商品",
                    "applicability": "Gate D 门店",
                    "confirm_as_current_brand_fact": True,
                    "as_synthetic_business_fixture": True,
                    "visibility_scope": "organizations",
                    "organization_ids": [region["id"]],
                },
            )
            assert inactive_product.status_code == 200
            disabled = admin.put(
                "/api/v1/tenant-management/brand-products/GD-INACTIVE-01/enabled",
                json={"enabled": False},
            )
            assert disabled.status_code == 200

            record = {
                "record_id": f"UX03-GATE-D-{suffix}",
                "tenant_name": tenant_name,
                "brand_name": tenant_name,
                "control_organization_name": headquarters["name"],
                "execution_organization_name": store["name"],
                "store_name": "Gate D 双层挂杆",
                "structure_version": "gate-d-store-v1",
                "rail_profile": {
                    "schema": "dm01-wall-double-rail-v1",
                    "upper_comfort_capacity": 4,
                    "lower_comfort_capacity": 4,
                    "primary_position": "right",
                    "secondary_position": "left",
                    "approach": "right",
                    "lower_reserved_positions": [],
                    "avoid_long_upper_lower_overlap": False,
                    "golden_sight": "中间视线",
                    "constraints": ["保持通道"],
                },
                "task_input": {
                    "version": "legacy-input-only",
                    "expression": {"schema": "dm01-wall-double-rail-v1"},
                    "products": [{"sku": "LEGACY-BAIT", "name": "不得消费", "quantity": 1}],
                },
            }
            DM01StoreSeedWriter(migrator_database_url).seed(record)
            grant = admin.patch(
                f"/api/v1/tenant-management/users/{member.json()['user_id']}/grants",
                json={
                    "entry_type": "tenant_user",
                    "capabilities": ["display"],
                    "publishing_identity_ids": [],
                    "expression_profile_maintenance_account_ids": [],
                },
            )
            assert grant.status_code == 200, grant.text

            display_user_password = "ux03-gate-d-user-password"
            _activate(admin, member.json()["activation_url"], display_user_password)

        with TestClient(app, base_url="https://diyu.example") as user:
            _login(user, member.json()["username"], display_user_password, "/login")
            assert user.get("/display").status_code == 200
            visible = user.get("/api/v1/display/products")
            assert visible.status_code == 200
            assert {item["sku"] for item in visible.json()} == {sku for sku, _, _, _ in product_payloads}
            visible_by_sku = {str(item["sku"]): item for item in visible.json()}

            before = _counts(app_database_url, tenant_id)
            inactive = user.post(
                "/api/v1/display",
                json={
                    "products": [
                        {
                            "product_version_id": inactive_product.json()["current_version_id"],
                            "quantity": 1,
                        }
                    ]
                },
            )
            assert inactive.status_code == 422
            assert _counts(app_database_url, tenant_id) == before
            sibling = user.post(
                "/api/v1/display",
                json={
                    "products": [
                        {
                            "product_version_id": sibling_product.json()["current_version_id"],
                            "quantity": 1,
                        }
                    ]
                },
            )
            assert sibling.status_code == 422
            assert _counts(app_database_url, tenant_id) == before
            missing = user.post(
                "/api/v1/display",
                json={"products": [{"product_version_id": str(uuid4()), "quantity": 1}]},
            )
            assert missing.status_code == 422
            assert _counts(app_database_url, tenant_id) == before
            duplicate = user.post(
                "/api/v1/display",
                json={
                    "products": [
                        {
                            "product_version_id": visible_by_sku["abc-123"]["product_version_id"],
                            "quantity": 1,
                        },
                        {
                            "product_version_id": visible_by_sku["abc-123"]["product_version_id"],
                            "quantity": 2,
                        },
                    ]
                },
            )
            assert duplicate.status_code == 422
            zero_quantity = user.post(
                "/api/v1/display",
                json={
                    "products": [
                        {
                            "product_version_id": visible_by_sku["abc-123"]["product_version_id"],
                            "quantity": 0,
                        }
                    ]
                },
            )
            assert zero_quantity.status_code == 422
            assert _counts(app_database_url, tenant_id) == before

            structured_inventory = [
                {
                    "product_version_id": visible_by_sku[sku]["product_version_id"],
                    "quantity": quantity,
                }
                for sku, _, _, quantity in product_payloads
            ]
            inventory = "、".join(f"{sku} {quantity} 件" for sku, _, _, quantity in product_payloads) + "。"
            hard_requirement_text = "abc-123、ABC123、123456、款号一与 GD-UP-01 必须保留。"
            unclear_before = _counts(app_database_url, tenant_id)
            unclear = user.post(
                "/api/v1/display",
                json={
                    "inventory_text": "必须保留主推商品。",
                    "products": structured_inventory,
                },
            )
            assert unclear.status_code == 200
            assert unclear.json()["kind"] == "question"
            assert "商品编号或完整商品名称" in unclear.json()["message"]
            assert _counts(app_database_url, tenant_id) == unclear_before
            for invalid_reference in (
                "abc-1234 必须保留。",
                "Xabc-123 必须保留。",
                "ABC123X 必须保留。",
                "小写编号商品升级款必须保留。",
                "升级款小写编号商品必须保留。",
                "abc-123、完全未知商品必须保留。",
                "完全未知商品、abc-123必须保留。",
                "abc-123 与 重复名称必须保留。",
                "abc-123 与 ABC123X 必须保留。",
                "abc-123、中文编号商品升级款必须保留。",
            ):
                rejected = user.post(
                    "/api/v1/display",
                    json={"inventory_text": invalid_reference, "products": structured_inventory},
                )
                assert rejected.status_code == 200
                assert rejected.json()["kind"] == "question"
                assert "商品编号或完整商品名称" in rejected.json()["message"]
                assert "task_id" not in rejected.json() and "version_id" not in rejected.json()
                assert _counts(app_database_url, tenant_id) == unclear_before
            with _without_rule_activation(migrator_database_url, "G-TASK-003"):
                missing_rule = user.post(
                    "/api/v1/display",
                    json={"inventory_text": hard_requirement_text, "products": structured_inventory},
                )
                assert missing_rule.status_code == 422
                assert _counts(app_database_url, tenant_id) == before
            v1_response = user.post(
                "/api/v1/display",
                json={"inventory_text": hard_requirement_text, "products": structured_inventory},
            )
            assert v1_response.status_code == 200, v1_response.text
            v1 = v1_response.json()
            assert _counts(app_database_url, tenant_id)[:3] == (before[0] + 1, before[1] + 1, before[2] + 1)
            assert "资料待补商品" in v1["body"] and "只计入库存对账" in v1["body"]
            assert all(sku in v1["body"] for sku, _, _, _ in product_payloads)
            assert "本次明确要求保留" in v1["body"]
            assert "AIGC" not in v1["body"] and "示意图" not in v1["body"]

            with psycopg.connect(app_database_url) as connection, connection.cursor() as cursor:
                cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),))
                cursor.execute(
                    "SELECT id,input_receipt,used_assets,provider_usage,model "
                    "FROM display_generation_runs WHERE tenant_id=%s AND task_id=%s",
                    (tenant_id, v1["task_id"]),
                )
                run = cursor.fetchone()
                cursor.execute(
                    "SELECT plan FROM display_artifact_versions WHERE tenant_id=%s AND task_id=%s AND version_number=1",
                    (tenant_id, v1["task_id"]),
                )
                plan_row = cursor.fetchone()
                cursor.execute(
                    "SELECT context_snapshot FROM display_tasks WHERE tenant_id=%s AND id=%s",
                    (tenant_id, v1["task_id"]),
                )
                task_row = cursor.fetchone()
            assert run is not None and plan_row is not None and task_row is not None
            assert run[3] is None and run[4] == "dm01-rule-compiler-v1"
            assert len(run[2]) == 11
            assert len(run[1]["product_snapshots"]) == len(product_payloads)
            assert [item["sku"] for item in run[1]["product_snapshots"]] == [sku for sku, _, _, _ in product_payloads]
            assert len(run[1]["rule_bundle"]["revision_assets"]) == 13
            assert all(item["snapshot_digest"] for item in run[1]["product_snapshots"])
            expected_hard_requirements = {"abc-123", "ABC123", "123456", "款号一", "GD-UP-01"}
            assert set(run[1]["hard_requirements"]) == expected_hard_requirements
            assert set(task_row[0]["hard_requirements"]) == expected_hard_requirements
            assert set(plan_row[0]["hard_requirements"]) == expected_hard_requirements
            assert plan_row[0]["artifact_audit"]["artifact_digest"]
            frozen_v1_body = v1["body"]
            frozen_v1_plan = deepcopy(plan_row[0])
            frozen_task_snapshot = deepcopy(task_row[0])

            with TestClient(app, base_url="https://diyu.example") as current_admin:
                _login(current_admin, tenant["username"], admin_password, "/tenant-admin/login")
                changed_product = current_admin.put(
                    "/api/v1/tenant-management/brand-products",
                    json={
                        "sku": "abc-123",
                        "display_name": "后来改动的商品名称",
                        "category": "服装",
                        "colors": [],
                        "material_or_structure": "",
                        "silhouette": "",
                        "observable_features": "",
                        "display_family": "lower",
                        "source_note": "Gate D synthetic 后续版本",
                        "applicability": "后续新任务",
                        "confirm_as_current_brand_fact": True,
                        "as_synthetic_business_fixture": True,
                        "visibility_scope": "organizations",
                        "organization_ids": [region["id"]],
                    },
                )
                assert changed_product.status_code == 200

            old_version_before = _counts(app_database_url, tenant_id)
            old_version = user.post(
                "/api/v1/display",
                json={
                    "products": [
                        {
                            "product_version_id": visible_by_sku["abc-123"]["product_version_id"],
                            "quantity": 1,
                        }
                    ]
                },
            )
            assert old_version.status_code == 422
            assert _counts(app_database_url, tenant_id) == old_version_before

            vague_before = _counts(app_database_url, tenant_id)
            vague = user.post(
                f"/api/v1/display-tasks/{v1['task_id']}/revisions",
                json={"feedback": "中间看起来再轻一点。"},
            )
            assert vague.status_code == 201 and vague.json()["kind"] == "question"
            assert _counts(app_database_url, tenant_id) == vague_before

            for invalid_feedback in (
                "中间上杆 abc-1234 太挤，请减少一件。",
                "中间上杆 ABC123X 太挤，请减少一件。",
                "中间上杆 小写编号商品升级款太挤，请减少一件。",
                "中间上杆 abc-123 和 完全未知商品太挤，请减少一件。",
                "中间上杆 完全未知商品 和 abc-123 太挤，请减少一件。",
                "中间上杆 abc-123 和 重复名称太挤，请减少一件。",
                "中间上杆 abc-123 和 ABC123 太挤，请减少一件。",
            ):
                rejected_revision = user.post(
                    f"/api/v1/display-tasks/{v1['task_id']}/revisions",
                    json={"feedback": invalid_feedback},
                )
                assert _counts(app_database_url, tenant_id) == vague_before
                assert rejected_revision.status_code == 201
                assert rejected_revision.json()["kind"] == "question"
                assert "task_id" not in rejected_revision.json()
                assert user.get(f"/api/v1/display-tasks/{v1['task_id']}/versions/1").json()["body"] == frozen_v1_body
                with psycopg.connect(app_database_url) as connection, connection.cursor() as cursor:
                    cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),))
                    cursor.execute(
                        "SELECT plan FROM display_artifact_versions "
                        "WHERE tenant_id=%s AND task_id=%s AND version_number=1",
                        (tenant_id, v1["task_id"]),
                    )
                    unchanged_plan = cursor.fetchone()
                    cursor.execute(
                        "SELECT context_snapshot FROM display_tasks WHERE tenant_id=%s AND id=%s",
                        (tenant_id, v1["task_id"]),
                    )
                    unchanged_task = cursor.fetchone()
                assert unchanged_plan is not None and unchanged_plan[0] == frozen_v1_plan
                assert unchanged_task is not None and unchanged_task[0] == frozen_task_snapshot

            with _without_rule_activation(migrator_database_url, "G-REV-003"):
                v2_response = user.post(
                    f"/api/v1/display-tasks/{v1['task_id']}/revisions",
                    json={"feedback": "右侧上杆 abc-123 太挤，请减少一件；其他内容不变。"},
                )
            assert v2_response.status_code == 201, v2_response.text
            v2 = v2_response.json()
            assert v2["version"] == 2
            assert "减少 1 件" in v2["body"]
            assert "小写编号商品" in v2["body"] and "后来改动的商品名称" not in v2["body"]
            assert _counts(app_database_url, tenant_id)[:3] == (before[0] + 1, before[1] + 2, before[2] + 2)
            with psycopg.connect(app_database_url) as connection, connection.cursor() as cursor:
                cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),))
                cursor.execute(
                    "SELECT id,used_assets,input_receipt FROM display_generation_runs "
                    "WHERE tenant_id=%s AND task_id=%s ORDER BY started_at DESC LIMIT 1",
                    (tenant_id, v1["task_id"]),
                )
                revised_run = cursor.fetchone()
                cursor.execute(
                    "SELECT plan FROM display_artifact_versions WHERE tenant_id=%s AND task_id=%s AND version_number=2",
                    (tenant_id, v1["task_id"]),
                )
                v2_plan_row = cursor.fetchone()
            assert revised_run is not None and v2_plan_row is not None and len(revised_run[1]) == 13
            assert revised_run[2]["rule_bundle"] == run[1]["rule_bundle"]
            assert user.get(f"/api/v1/display-tasks/{v1['task_id']}/versions/1").json()["body"] == v1["body"]
            versions = user.get(f"/api/v1/display/tasks/{v1['task_id']}/versions").json()
            assert [item["version"] for item in versions] == [2, 1]
            assert versions[1]["body"] == v1["body"] and versions[0]["body"] == v2["body"]
            _write_evidence(
                {
                    "contract_version": "ux03-gate-d-local-evidence-v1",
                    "synthetic_only": True,
                    "task_id": v1["task_id"],
                    "runs": [str(run[0]), str(revised_run[0])],
                    "versions": [v1["version_id"], v2["version_id"]],
                    "database_delta": {"task": 1, "run": 2, "version": 2},
                    "model": "dm01-rule-compiler-v1",
                    "provider_usage": None,
                    "input_inventory_sha256": _sha256_text(inventory),
                    "store_profile_version": run[1]["store_profile_version"],
                    "product_snapshots": run[1]["product_snapshots"],
                    "rule_bundle": run[1]["rule_bundle"],
                    "versions_audit": [
                        {
                            "version": 1,
                            "body_sha256": _sha256_text(v1["body"]),
                            "artifact_audit": plan_row[0]["artifact_audit"],
                            "inventory_conservation": plan_row[0]["inventory_conservation"],
                        },
                        {
                            "version": 2,
                            "body_sha256": _sha256_text(v2["body"]),
                            "artifact_audit": v2_plan_row[0]["artifact_audit"],
                            "inventory_conservation": v2_plan_row[0]["inventory_conservation"],
                        },
                    ],
                    "checks": {
                        "v1_v2_v1_readback": True,
                        "frozen_product_versions_replayed": True,
                        "frozen_rule_bundle_replayed": True,
                        "per_sku_conservation": True,
                        "model_calls": 0,
                    },
                }
            )

            with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
                cursor.execute(
                    "SELECT has_table_privilege('diyu_app','display_artifact_versions','SELECT'),"
                    "has_table_privilege('diyu_app','display_artifact_versions','INSERT'),"
                    "has_table_privilege('diyu_app','display_artifact_versions','UPDATE'),"
                    "has_table_privilege('diyu_app','display_artifact_versions','DELETE')"
                )
                assert cursor.fetchone() == (True, True, False, False)
            with psycopg.connect(app_database_url) as connection, connection.cursor() as cursor:
                cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),))
                with pytest.raises(psycopg.Error):
                    cursor.execute(
                        "UPDATE display_artifact_versions SET body='tampered' WHERE tenant_id=%s AND id=%s",
                        (tenant_id, v1["version_id"]),
                    )
            with (
                psycopg.connect(migrator_database_url) as connection,
                connection.cursor() as cursor,
                pytest.raises(psycopg.Error),
            ):
                cursor.execute(
                    "DELETE FROM display_artifact_versions WHERE tenant_id=%s AND id=%s",
                    (tenant_id, v1["version_id"]),
                )

            with TestClient(app, base_url="https://diyu.example") as current_admin:
                _login(current_admin, tenant["username"], admin_password, "/tenant-admin/login")
                restored_product = current_admin.put(
                    "/api/v1/tenant-management/brand-products",
                    json={
                        "sku": "abc-123",
                        "display_name": "小写编号商品（当前新任务）",
                        "category": "服装",
                        "colors": [],
                        "material_or_structure": "",
                        "silhouette": "",
                        "observable_features": "",
                        "display_family": "upper",
                        "source_note": "Gate D synthetic 编译失败反证",
                        "applicability": "后续新任务",
                        "confirm_as_current_brand_fact": True,
                        "as_synthetic_business_fixture": True,
                        "visibility_scope": "organizations",
                        "organization_ids": [region["id"]],
                    },
                )
                assert restored_product.status_code == 200

            if os.environ.get("DIYU_RUN_UX03_GATE_D_BROWSER") == "1":
                browser = _run_gate_d_browser(
                    app_database_url,
                    tmp_path / "browser-materials",
                    member.json()["username"],
                    display_user_password,
                )
                assert browser.returncode == 0, (
                    f"formal Gate D Chrome journey failed:\n{browser.stdout}\n{browser.stderr}"
                )
                browser_result = json.loads(browser.stdout)
                assert browser_result["failures"] == []
                assert [item["name"] for item in browser_result["results"]] == [
                    "正式商品与规则生成 V1",
                    "V1→V2→V1→当前 V2 与复制",
                    "失败恢复",
                    "响应式、触控与键盘",
                    "公共状态页",
                    "浏览器边界",
                ]

            current_structured_inventory = tuple(
                (
                    UUID(
                        str(
                            restored_product.json()["current_version_id"]
                            if sku == "abc-123"
                            else visible_by_sku[sku]["product_version_id"]
                        )
                    ),
                    quantity,
                )
                for sku, _, _, quantity in product_payloads
            )
            display_scope = DisplayScope(
                tenant_id,
                UUID(str(member.json()["user_id"])),
                brand_id,
                UUID(str(store["id"])),
            )

            for finalize_failure in ("version_insert", "commit"):
                finalize_before = _counts(app_database_url, tenant_id)
                with (
                    _reject_display_finalize(migrator_database_url, finalize_failure),
                    pytest.raises(GenerationFailed, match="纯文字方案没有生成完成"),
                ):
                    DisplayService(
                        PostgresDisplayRepository(app_database_url),
                        DM01DisplayCompiler(),
                    ).create(display_scope, "", current_structured_inventory)
                finalize_after = _counts(app_database_url, tenant_id)
                assert finalize_after == (
                    finalize_before[0] + 1,
                    finalize_before[1] + 1,
                    finalize_before[2],
                    finalize_before[3] + 1,
                    0,
                )

            revision_service = DisplayService(
                PostgresDisplayRepository(app_database_url),
                DM01DisplayCompiler(),
            )
            revision_base = revision_service.create(
                display_scope,
                "",
                current_structured_inventory,
            )
            revision_failure_before = _counts(app_database_url, tenant_id)
            with (
                _reject_display_finalize(migrator_database_url, "artifact_pointer"),
                pytest.raises(GenerationFailed, match="纯文字方案没有生成完成"),
            ):
                revision_service.revise(
                    display_scope,
                    UUID(str(revision_base["task_id"])),
                    "右侧上杆 abc-123 太挤，请减少一件；其他内容不变。",
                )
            revision_failure_after = _counts(app_database_url, tenant_id)
            assert revision_failure_after == (
                revision_failure_before[0],
                revision_failure_before[1] + 1,
                revision_failure_before[2],
                revision_failure_before[3] + 1,
                0,
            )

            lost_repository = PostgresDisplayRepository(app_database_url)

            def lost_complete(*args: object, **kwargs: object) -> dict[str, object]:
                del args, kwargs
                raise psycopg.OperationalError("synthetic connection lost during finalize")

            def lost_fail(*args: object, **kwargs: object) -> None:
                del args, kwargs
                raise psycopg.OperationalError("synthetic connection unavailable")

            stale_before = _counts(app_database_url, tenant_id)
            with pytest.MonkeyPatch.context() as patcher:
                patcher.setattr(lost_repository, "complete_run", lost_complete)
                patcher.setattr(lost_repository, "fail_run", lost_fail)
                with pytest.raises(GenerationFailed, match="纯文字方案没有生成完成"):
                    DisplayService(lost_repository, DM01DisplayCompiler()).create(
                        display_scope,
                        "",
                        current_structured_inventory,
                    )
            stale_pending = _counts(app_database_url, tenant_id)
            assert stale_pending == (
                stale_before[0] + 1,
                stale_before[1] + 1,
                stale_before[2],
                stale_before[3],
                stale_before[4] + 1,
            )
            with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE display_generation_runs SET started_at=now()-interval '16 minutes' "
                    "WHERE tenant_id=%s AND status='running'",
                    (tenant_id,),
                )
                assert cursor.rowcount == 1
            assert PostgresDisplayRepository(app_database_url).recover_stale_runs(display_scope, 900) == 1
            stale_recovered = _counts(app_database_url, tenant_id)
            assert stale_recovered[2] == stale_before[2]
            assert stale_recovered[3] == stale_before[3] + 1
            assert stale_recovered[4] == 0

            class FailingCompiler(DM01DisplayCompiler):
                def generate(self, request: DisplayGenerationInput):  # type: ignore[no-untyped-def]
                    del request
                    raise GenerationFailed("Gate D synthetic 编译失败")

            failure_before = _counts(app_database_url, tenant_id)
            failing_service = DisplayService(
                PostgresDisplayRepository(app_database_url),
                FailingCompiler(),
            )
            with pytest.raises(GenerationFailed):
                failing_service.create(
                    display_scope,
                    "",
                    current_structured_inventory,
                )
            failure_after = _counts(app_database_url, tenant_id)
            assert failure_after == (
                failure_before[0] + 1,
                failure_before[1] + 1,
                failure_before[2],
                failure_before[3] + 1,
                0,
            )
    finally:
        if tenant_id is not None:
            _cleanup(migrator_database_url, tenant_id, operator_id)
