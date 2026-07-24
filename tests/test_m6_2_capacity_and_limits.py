from __future__ import annotations

import time
from collections.abc import Iterator
from concurrent.futures import CancelledError, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from threading import Condition, Event
from typing import Any
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.gateway.api.app as api_app
from src.brain.content_service import ContentService
from src.brain.workbench_service import WorkbenchService
from src.gateway.api.settings import Settings
from src.infrastructure.local_object_store import LocalObjectStore
from src.infrastructure.postgres_repository import PostgresContentRepository
from src.infrastructure.production_auth import OpsSession, ProductionAuthRepository, TenantSession
from src.infrastructure.workbench_repository import PostgresWorkbenchRepository
from src.shared.errors import DomainError, GenerationFailed
from src.shared.types import (
    ContentProduct,
    GeneratedArtifact,
    GenerationInput,
    RoutingInput,
    TenantManagementScope,
    TrustedScope,
)
from src.tool.llm_gateway.stub import DeterministicP1Generator


@dataclass(frozen=True)
class CapacityTenant:
    tenant_id: UUID
    brand_id: UUID
    administrator_id: UUID
    account_id: UUID
    user_ids: tuple[UUID, ...]


@dataclass(frozen=True)
class CapacityFixture:
    tenants: tuple[CapacityTenant, ...]
    elapsed_seconds: float


class RequestCancelled(BaseException):
    """Controlled request cancellation used to prove slot and run cleanup."""


class ControlledGenerator(DeterministicP1Generator):
    def __init__(self) -> None:
        self.release = Event()
        self._entered = 0
        self._condition = Condition()

    def route(self, request: RoutingInput) -> ContentProduct | None:
        del request
        return "brand_life_narrative"

    def generate(self, request: GenerationInput) -> GeneratedArtifact:
        if request.weak_seed.startswith("阻塞"):
            with self._condition:
                self._entered += 1
                self._condition.notify_all()
            if not self.release.wait(timeout=10):
                raise GenerationFailed("受控阻塞生成器等待超时")
        if request.weak_seed.startswith("失败"):
            raise GenerationFailed("受控模型失败")
        if request.weak_seed.startswith("取消"):
            raise RequestCancelled
        return super().generate(request)

    def wait_until_entered(self, count: int) -> bool:
        with self._condition:
            return self._condition.wait_for(lambda: self._entered >= count, timeout=10)


def _operator(repository: ProductionAuthRepository, migrator_database_url: str) -> OpsSession:
    with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT id FROM platform_operators WHERE enabled = true ORDER BY id LIMIT 1")
        existing = cursor.fetchone()
    if existing is not None:
        return OpsSession(UUID(str(existing[0])))
    _, provisioning_uri = repository.bootstrap_operator(
        f"m6-2-ops-{uuid4().hex[:8]}",
        "m6-2-isolated-operator-password",
    )
    secret = parse_qs(urlsplit(provisioning_uri).query)["secret"][0]
    with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT username FROM platform_operators ORDER BY id LIMIT 1")
        username_row = cursor.fetchone()
    assert username_row is not None
    operator = repository.authenticate_operator(
        str(username_row[0]),
        "m6-2-isolated-operator-password",
        repository._totp_code(secret, int(time.time() // 30)),
    )
    assert operator is not None
    return operator


def _remove_capacity_tenants(migrator_database_url: str, tenant_ids: tuple[UUID, ...]) -> None:
    with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
        try:
            cursor.execute("SET session_replication_role = replica")
            cursor.execute(
                """
                SELECT DISTINCT table_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND column_name = 'tenant_id' AND table_name <> 'tenants'
                ORDER BY table_name
                """
            )
            for (table_name,) in cursor.fetchall():
                cursor.execute(
                    psycopg.sql.SQL("DELETE FROM {} WHERE tenant_id = ANY(%s)").format(
                        psycopg.sql.Identifier(str(table_name))
                    ),
                    (list(tenant_ids),),
                )
            cursor.execute("DELETE FROM tenants WHERE id = ANY(%s)", (list(tenant_ids),))
        finally:
            cursor.execute("SET session_replication_role = origin")


@pytest.fixture(scope="module")
def capacity_fixture(
    app_database_url: str,
    migrator_database_url: str,
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[CapacityFixture]:
    repository = ProductionAuthRepository(app_database_url)
    workbench = WorkbenchService(
        PostgresWorkbenchRepository(app_database_url),
        LocalObjectStore(str(tmp_path_factory.mktemp("m6-2-capacity-objects"))),
    )
    operator = _operator(repository, migrator_database_url)
    suffix = uuid4().hex[:10]
    started = time.perf_counter()
    capacity_tenants: list[CapacityTenant] = []
    try:
        for tenant_index in range(5):
            tenant_name = f"M6-2隔离容量租户-{suffix}-{tenant_index}"
            username = f"m62-admin-{suffix}-{tenant_index}"
            created = repository.provision_tenant(
                operator,
                tenant_name,
                f"容量管理员-{tenant_index}",
                username,
            )
            retried = repository.provision_tenant(
                operator,
                tenant_name,
                f"容量管理员-{tenant_index}",
                username,
            )
            assert retried["tenant_id"] == created["tenant_id"]
            tenant_id = UUID(created["tenant_id"])
            brand_id = UUID(created["brand_id"])
            administrator_id = UUID(created["administrator_id"])
            management_scope = TenantManagementScope(tenant_id, administrator_id, brand_id)
            draft = workbench.brand_expression(management_scope)["draft"]
            assert isinstance(draft, str)
            workbench.confirm_brand_expression(management_scope, draft)
            account = workbench.create_publishing_account(
                management_scope,
                f"容量发布账号-{tenant_index}",
                "抖音",
                f"容量内容角色-{tenant_index}",
                "只在当前隔离租户的已确认品牌边界内表达。",
                administrator_id,
            )
            account_id = UUID(str(account["id"]))
            user_ids = [administrator_id]
            for user_index in range(1, 40):
                user = repository.create_tenant_user(
                    TenantSession(tenant_id, administrator_id, "tenant-admin"),
                    f"容量自然人-{tenant_index}-{user_index}-{suffix}",
                    f"m62-user-{suffix}-{tenant_index}-{user_index}",
                    None,
                    account_id,
                    grants_tenant_management=False,
                    grants_material_maintenance=False,
                )
                user_ids.append(UUID(user["user_id"]))
            capacity_tenants.append(
                CapacityTenant(
                    tenant_id,
                    brand_id,
                    administrator_id,
                    account_id,
                    tuple(user_ids),
                )
            )

        yield CapacityFixture(tuple(capacity_tenants), time.perf_counter() - started)
    finally:
        _remove_capacity_tenants(
            migrator_database_url,
            tuple(tenant.tenant_id for tenant in capacity_tenants),
        )


def _production_settings(
    database_url: str,
    *,
    global_concurrency: int = 2,
    tenant_concurrency: int = 1,
    tenant_rate: int = 120,
) -> Settings:
    return Settings.model_validate(
        {
            "DIYU_RUNTIME_MODE": "production",
            "DIYU_APP_DATABASE_URL": database_url,
            "DIYU_SESSION_SECRET": "m6-2-production-test-session-secret",
            "DIYU_GENERATOR_MODE": "deepseek",
            "DEEPSEEK_API_BASE_URL": "https://example.invalid",
            "DEEPSEEK_API_KEY": "not-a-real-key",
            "DEEPSEEK_MODEL": "deepseek-v4-flash",
            "DIYU_S3_ENDPOINT_URL": "http://127.0.0.1:9000",
            "DIYU_S3_BUCKET": "diyu-test",
            "DIYU_S3_ACCESS_KEY_ID": "test-access-key",
            "DIYU_S3_SECRET_ACCESS_KEY": "test-secret-key",
            "DIYU_MODEL_GLOBAL_CONCURRENCY": global_concurrency,
            "DIYU_MODEL_TENANT_CONCURRENCY": tenant_concurrency,
            "DIYU_MODEL_TENANT_RATE_PER_MINUTE": tenant_rate,
        }
    )


def _controlled_app(
    app_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
    generator: ControlledGenerator,
    *,
    global_concurrency: int = 2,
    tenant_concurrency: int = 1,
    tenant_rate: int = 120,
) -> FastAPI:
    service = ContentService(
        PostgresContentRepository(app_database_url, None, ()),
        generator,
    )
    monkeypatch.setattr(api_app, "build_content_service", lambda _: service)
    return api_app.create_app(
        _production_settings(
            app_database_url,
            global_concurrency=global_concurrency,
            tenant_concurrency=tenant_concurrency,
            tenant_rate=tenant_rate,
        )
    )


def _session_token(
    repository: ProductionAuthRepository,
    tenant: CapacityTenant,
    user_id: UUID,
) -> str:
    return repository.create_tenant_session(TenantSession(tenant.tenant_id, user_id, "tenant-user"))


def _post_content(app: FastAPI, token: str, weak_seed: str) -> Any:
    with TestClient(app, base_url="https://diyuai.cc") as client:
        client.cookies.set("diyu_session", token, domain="diyuai.cc", path="/")
        return client.post(
            "/api/v1/content",
            json={"weak_seed": weak_seed, "target": "douyin_video"},
        )


def _content_counts(
    migrator_database_url: str,
    tenant_ids: tuple[UUID, ...],
) -> tuple[int, int, int]:
    with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
              (SELECT count(*) FROM business_tasks WHERE tenant_id = ANY(%s)),
              (SELECT count(*) FROM generation_runs WHERE tenant_id = ANY(%s)),
              (SELECT count(*) FROM content_versions WHERE tenant_id = ANY(%s))
            """,
            (list(tenant_ids), list(tenant_ids), list(tenant_ids)),
        )
        row = cursor.fetchone()
    assert row is not None
    return int(row[0]), int(row[1]), int(row[2])


def test_capacity_fixture_has_five_tenants_two_hundred_enabled_linked_users_and_isolation(
    capacity_fixture: CapacityFixture,
    app_database_url: str,
    migrator_database_url: str,
) -> None:
    assert len(capacity_fixture.tenants) == 5
    assert capacity_fixture.elapsed_seconds > 0
    workbench_repository = PostgresWorkbenchRepository(app_database_url)
    tenant_user_sets: list[set[UUID]] = []
    for tenant in capacity_fixture.tenants:
        assert len(tenant.user_ids) == 40
        visible_users = workbench_repository.management_operators(
            TenantManagementScope(tenant.tenant_id, tenant.administrator_id, tenant.brand_id)
        )
        visible_ids = {UUID(str(user["id"])) for user in visible_users}
        assert visible_ids == set(tenant.user_ids)
        tenant_user_sets.append(visible_ids)
        for user_id in tenant.user_ids:
            identity = workbench_repository.content_identity(
                TrustedScope(tenant.tenant_id, user_id, tenant.brand_id, tenant.account_id)
            )
            assert identity["content_role"].startswith("容量内容角色-")

    assert sum(len(users) for users in tenant_user_sets) == 200
    assert all(left.isdisjoint(right) for index, left in enumerate(tenant_user_sets) for right in tenant_user_sets[index + 1 :])
    with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM users WHERE tenant_id = ANY(%s) AND enabled = true",
            ([tenant.tenant_id for tenant in capacity_fixture.tenants],),
        )
        assert cursor.fetchone() == (200,)

    first, second = capacity_fixture.tenants[:2]
    with pytest.raises(DomainError):
        workbench_repository.content_identity(
            TrustedScope(second.tenant_id, first.user_ids[0], second.brand_id, second.account_id)
        )
    with pytest.raises(DomainError):
        workbench_repository.content_identity(
            TrustedScope(first.tenant_id, first.user_ids[0], uuid4(), first.account_id)
        )
    with pytest.raises(DomainError):
        workbench_repository.content_identity(
            TrustedScope(first.tenant_id, first.user_ids[0], first.brand_id, uuid4())
        )

    auth_repository = ProductionAuthRepository(app_database_url)
    unauthorized = auth_repository.create_tenant_user(
        TenantSession(first.tenant_id, first.administrator_id, "tenant-admin"),
        f"容量未授权自然人-{uuid4().hex[:8]}",
        f"m62-ungranted-{uuid4().hex[:12]}",
        None,
        None,
        grants_tenant_management=False,
        grants_material_maintenance=False,
    )
    unauthorized_id = UUID(unauthorized["user_id"])
    with pytest.raises(DomainError):
        workbench_repository.content_identity(
            TrustedScope(first.tenant_id, unauthorized_id, first.brand_id, first.account_id)
        )
    auth_repository.disable_tenant_user(
        TenantSession(first.tenant_id, first.administrator_id, "tenant-admin"),
        unauthorized_id,
    )


def test_formal_content_api_enforces_global_tenant_user_rate_limits_and_releases_slots(
    capacity_fixture: CapacityFixture,
    app_database_url: str,
    migrator_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenants = capacity_fixture.tenants
    tenant_ids = tuple(tenant.tenant_id for tenant in tenants)
    repository = ProductionAuthRepository(app_database_url)
    generator = ControlledGenerator()
    app = _controlled_app(app_database_url, monkeypatch, generator)
    tokens = {
        (tenant_index, user_index): _session_token(repository, tenants[tenant_index], tenants[tenant_index].user_ids[user_index])
        for tenant_index in range(3)
        for user_index in range(8)
    }
    before = _content_counts(migrator_database_url, tenant_ids)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(_post_content, app, tokens[(0, 0)], "阻塞-租户一")
        second = executor.submit(_post_content, app, tokens[(1, 0)], "阻塞-租户二")
        assert generator.wait_until_entered(2)

        started = time.perf_counter()
        tenant_rejected = _post_content(app, tokens[(0, 1)], "同租户超限")
        tenant_reject_seconds = time.perf_counter() - started
        global_rejected = _post_content(app, tokens[(2, 0)], "全局超限")
        assert tenant_rejected.status_code == 429
        assert global_rejected.status_code == 429
        assert tenant_reject_seconds < 2
        while_blocked = _content_counts(migrator_database_url, tenant_ids)
        assert while_blocked == (before[0] + 2, before[1] + 2, before[2])

        generator.release.set()
        assert first.result(timeout=10).status_code == 200
        assert second.result(timeout=10).status_code == 200

    after_blocking = _content_counts(migrator_database_url, tenant_ids)
    assert after_blocking == (before[0] + 2, before[1] + 2, before[2] + 2)

    failed = _post_content(app, tokens[(0, 2)], "失败-供应商最终失败")
    assert failed.status_code == 422
    after_failure = _content_counts(migrator_database_url, tenant_ids)
    assert after_failure == (after_blocking[0] + 1, after_blocking[1] + 1, after_blocking[2])
    recovered = _post_content(app, tokens[(0, 3)], "恢复-失败后可以继续")
    assert recovered.status_code == 200

    # Starlette may replace a BaseException raised by a sync worker with its
    # stopped-portal RuntimeError while closing that one test client.
    with pytest.raises((RequestCancelled, RuntimeError, CancelledError)):
        _post_content(app, tokens[(1, 1)], "取消-调用被取消")
    after_cancel = _content_counts(migrator_database_url, tenant_ids)
    assert after_cancel[2] == after_failure[2] + 1
    with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT status FROM generation_runs WHERE tenant_id = %s ORDER BY started_at DESC LIMIT 1",
            (tenants[1].tenant_id,),
        )
        assert cursor.fetchone() == ("failed",)
    assert _post_content(app, tokens[(1, 2)], "恢复-取消后可以继续").status_code == 200

    dedup_app = _controlled_app(
        app_database_url,
        monkeypatch,
        generator,
        global_concurrency=4,
        tenant_concurrency=4,
    )
    assert _post_content(dedup_app, tokens[(0, 4)], "单用户第一次").status_code == 200
    dedup_before = _content_counts(migrator_database_url, tenant_ids)
    assert _post_content(dedup_app, tokens[(0, 4)], "单用户两秒内重复").status_code == 429
    assert _content_counts(migrator_database_url, tenant_ids) == dedup_before

    rate_app = _controlled_app(
        app_database_url,
        monkeypatch,
        generator,
        global_concurrency=4,
        tenant_concurrency=4,
        tenant_rate=2,
    )
    assert _post_content(rate_app, tokens[(2, 1)], "租户速率一").status_code == 200
    assert _post_content(rate_app, tokens[(2, 2)], "租户速率二").status_code == 200
    rate_before = _content_counts(migrator_database_url, tenant_ids)
    assert _post_content(rate_app, tokens[(2, 3)], "租户速率三").status_code == 429
    assert _content_counts(migrator_database_url, tenant_ids) == rate_before


def test_backup_restore_scripts_use_snapshot_manifest_and_a_real_application_role() -> None:
    backup = Path("deploy/backup.sh").read_text(encoding="utf-8")
    restore = Path("deploy/restore_verify.sh").read_text(encoding="utf-8")
    assert "manifest.json" in backup
    assert '"complete_content_chains"' in backup
    assert 'sha256sum "$snapshot/manifest.json"' in backup
    assert '"41"' not in restore
    assert "NOBYPASSRLS" in restore
    assert "complete_content_chain_count < 1" in restore
