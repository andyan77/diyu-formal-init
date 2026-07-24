from __future__ import annotations

import time
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from src.brain.content_service import ContentService
from src.brain.natural_entry import is_natural_chat
from src.gateway.api.app import create_app
from src.gateway.api.settings import Settings
from src.infrastructure.postgres_repository import PostgresContentRepository
from src.infrastructure.production_auth import (
    OpsSession,
    ProductionAuthRepository,
    TenantSession,
)
from src.infrastructure.workbench_repository import PostgresWorkbenchRepository
from src.shared.errors import DomainError
from src.shared.types import ContentProduct, RoutingInput, TrustedScope
from src.tool.llm_gateway.stub import DeterministicP1Generator


class ForcedProductTruthGenerator(DeterministicP1Generator):
    def route(self, request: RoutingInput) -> ContentProduct | None:
        del request
        return "product_truth"


class ForcedBrandLifeGenerator(DeterministicP1Generator):
    def route(self, request: RoutingInput) -> ContentProduct | None:
        del request
        return "brand_life_narrative"


def _settings(database_url: str) -> Settings:
    return Settings.model_validate(
        {
            "DIYU_RUNTIME_MODE": "production",
            "DIYU_APP_DATABASE_URL": database_url,
            "DIYU_SESSION_SECRET": "m6-1-production-test-session-secret",
            "DIYU_GENERATOR_MODE": "deepseek",
            "DEEPSEEK_API_BASE_URL": "https://example.invalid",
            "DEEPSEEK_API_KEY": "not-a-real-key",
            "DEEPSEEK_MODEL": "deepseek-v4-flash",
            "DIYU_S3_ENDPOINT_URL": "http://127.0.0.1:9000",
            "DIYU_S3_BUCKET": "diyu-test",
            "DIYU_S3_ACCESS_KEY_ID": "test-access-key",
            "DIYU_S3_SECRET_ACCESS_KEY": "test-secret-key",
        }
    )


def _clear_auth_state(database_url: str) -> None:
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("DELETE FROM ops_audit_events")
        cursor.execute("DELETE FROM tenant_sessions")
        cursor.execute("DELETE FROM user_activation_tokens")
        cursor.execute("DELETE FROM user_credentials")
        cursor.execute("DELETE FROM platform_sessions")
        cursor.execute("DELETE FROM platform_operators")


def _operator(repository: ProductionAuthRepository) -> OpsSession:
    _, provisioning_uri = repository.bootstrap_operator(
        "m6-1-ops",
        "m6-1-ops-password-is-long",
    )
    secret = parse_qs(urlsplit(provisioning_uri).query)["secret"][0]
    operator = repository.authenticate_operator(
        "m6-1-ops",
        "m6-1-ops-password-is-long",
        repository._totp_code(secret, int(time.time() // 30)),
    )
    assert operator is not None
    return operator


def test_real_tenant_onboarding_is_atomic_account_independent_and_idempotent(
    app_database_url: str,
    migrator_database_url: str,
) -> None:
    _clear_auth_state(migrator_database_url)
    repository = ProductionAuthRepository(app_database_url)
    operator = _operator(repository)
    suffix = uuid4().hex[:10]
    tenant_name = f"笛语服饰-入驻测试-{suffix}"
    username = f"diyu-brand-admin-{suffix}"

    created = repository.provision_tenant(
        operator,
        tenant_name,
        "笛语服饰负责人",
        username,
    )
    retried = repository.provision_tenant(
        operator,
        tenant_name,
        "笛语服饰负责人",
        username,
    )
    assert retried["tenant_id"] == created["tenant_id"]
    assert retried["administrator_id"] == created["administrator_id"]
    assert retried["brand_id"] == created["brand_id"]
    assert retried["activation_token"] != created["activation_token"]

    conflicting_tenant = f"用户名冲突反证-{suffix}"
    with pytest.raises(DomainError, match="租户名称或管理员用户名"):
        repository.provision_tenant(
            operator,
            conflicting_tenant,
            "另一位负责人",
            username,
        )

    tenant_id = UUID(created["tenant_id"])
    administrator_id = UUID(created["administrator_id"])
    brand_id = UUID(created["brand_id"])
    with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                (SELECT count(*) FROM organizations WHERE tenant_id = %s),
                (SELECT count(*) FROM users WHERE tenant_id = %s),
                (SELECT count(*) FROM brands WHERE tenant_id = %s),
                (SELECT count(*) FROM brand_expression_baselines WHERE tenant_id = %s),
                (SELECT count(*) FROM content_accounts WHERE tenant_id = %s),
                (SELECT count(*) FROM content_roles WHERE tenant_id = %s),
                (SELECT count(*) FROM brand_products WHERE tenant_id = %s),
                (SELECT count(*) FROM display_stores WHERE tenant_id = %s)
            """,
            (tenant_id,) * 8,
        )
        assert cursor.fetchone() == (1, 1, 1, 1, 0, 0, 0, 0)
        cursor.execute(
            """
            SELECT baseline.status, baseline.version, baseline.draft,
                   count(token.id) FILTER (WHERE token.used_at IS NULL)
            FROM brand_expression_baselines baseline
            JOIN user_activation_tokens token
              ON token.tenant_id = baseline.tenant_id
             AND token.user_id = %s
            WHERE baseline.tenant_id = %s AND baseline.brand_id = %s
            GROUP BY baseline.status, baseline.version, baseline.draft
            """,
            (administrator_id, tenant_id, brand_id),
        )
        baseline_row = cursor.fetchone()
        assert baseline_row is not None
        status, version, draft, active_tokens = baseline_row
        assert (status, version, active_tokens) == ("draft", 1, 1)
        assert "家庭成员各自成立、自然呼应" in str(draft)
        cursor.execute("SELECT count(*) FROM tenants WHERE name = %s", (conflicting_tenant,))
        assert cursor.fetchone() == (0,)

    app = create_app(_settings(app_database_url))
    password = "m6-1-brand-password-is-long"
    with TestClient(app, base_url="https://diyuai.cc") as client:
        activated = client.post(
            f"/activate/{retried['activation_token']}",
            content=f"password={password}",
            follow_redirects=False,
        )
        assert activated.status_code == 303
        assert activated.headers["location"] == "/tenant-admin/login"
        with pytest.raises(DomainError, match="租户名称或管理员用户名"):
            repository.provision_tenant(
                operator,
                tenant_name,
                "笛语服饰负责人",
                username,
            )
        signed_in = client.post(
            "/tenant-admin/login",
            content=f"username={username}&password={password}",
            follow_redirects=False,
        )
        assert signed_in.status_code == 303
        assert client.get("/tenant-admin").status_code == 200
        context = client.get("/api/v1/session/context").json()
        assert context["application"] == "tenant_management"
        assert context["identity"]["brand"] == tenant_name
        assert "account" not in context["identity"]

        readiness = client.get("/api/v1/admin/readiness").json()["items"]
        states = {item["id"]: item["state"] for item in readiness}
        assert states == {
            "brand_expression": "needs_action",
            "account_role": "needs_action",
            "product_facts": "needs_action",
            "dm01_profile": "needs_action",
        }
        operators = client.get("/api/v1/tenant-management/operators").json()
        assert operators == [
            {
                "id": str(administrator_id),
                "display_name": "笛语服饰负责人",
                "organization": f"{tenant_name}管理组织",
                "publishing_accounts": "",
                "default_persona": "",
                "manages_tenant": True,
            }
        ]
        account_payload = {
            "name": "笛语服饰品牌官方账号",
            "channel": "抖音",
            "content_role_name": "品牌官方 / 品牌定义者",
            "voice_boundary": (
                "代表品牌讲已确认的品牌立场、生活关系和内容方向；不冒充创始人、研发、门店或顾客，"
                "不讲未确认商品和经营事实。"
            ),
            "operator_id": str(administrator_id),
        }
        before_confirmation = client.post(
            "/api/v1/tenant-management/publishing-accounts",
            json=account_payload,
        )
        assert before_confirmation.status_code == 422

        baseline = client.get("/api/v1/admin/brand-expression").json()
        confirmed = client.post(
            "/api/v1/admin/brand-expression/confirm",
            json={"draft": baseline["draft"]},
        )
        repeated_confirmation = client.post(
            "/api/v1/admin/brand-expression/confirm",
            json={"draft": baseline["draft"]},
        )
        assert confirmed.json()["version"] == 1
        assert repeated_confirmation.json()["version"] == 1

        wrong_operator_payload = {**account_payload, "operator_id": str(uuid4())}
        wrong_operator = client.post(
            "/api/v1/tenant-management/publishing-accounts",
            json=wrong_operator_payload,
        )
        assert wrong_operator.status_code == 422

        account = client.post(
            "/api/v1/tenant-management/publishing-accounts",
            json=account_payload,
        )
        retried_account = client.post(
            "/api/v1/tenant-management/publishing-accounts",
            json=account_payload,
        )
        assert account.status_code == 201
        assert retried_account.status_code == 201
        assert retried_account.json()["id"] == account.json()["id"]

    with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                (SELECT count(*) FROM content_accounts WHERE tenant_id = %s),
                (SELECT count(*) FROM content_roles WHERE tenant_id = %s),
                (SELECT count(*) FROM auth_grants WHERE tenant_id = %s),
                (SELECT count(*) FROM activity_events
                  WHERE tenant_id = %s AND event_type = 'brand_expression.confirmed')
            """,
            (tenant_id,) * 4,
        )
        assert cursor.fetchone() == (1, 1, 1, 1)


def test_real_brand_non_product_p3_has_no_demo_tenant_context(
    app_database_url: str,
    migrator_database_url: str,
) -> None:
    _clear_auth_state(migrator_database_url)
    repository = ProductionAuthRepository(app_database_url)
    operator = _operator(repository)
    suffix = uuid4().hex[:10]
    tenant_name = f"笛语服饰-内容隔离测试-{suffix}"
    username = f"diyu-content-admin-{suffix}"
    created = repository.provision_tenant(
        operator,
        tenant_name,
        "笛语服饰负责人",
        username,
    )
    tenant_id = UUID(created["tenant_id"])
    user_id = UUID(created["administrator_id"])
    manager = TenantSession(tenant_id, user_id, "tenant-admin")
    repository.complete_activation(
        created["activation_token"],
        "m6-1-content-password-is-long",
    )

    management_scope = repository.manager_scope(manager)
    workbench = PostgresWorkbenchRepository(app_database_url)
    baseline = workbench.brand_expression(management_scope)
    workbench.confirm_brand_expression(management_scope, str(baseline["draft"]))
    account = workbench.create_publishing_account(
        management_scope,
        "笛语服饰品牌官方账号",
        "抖音",
        "品牌官方 / 品牌定义者",
        "只讲已确认品牌立场和生活关系；不讲未确认商品、门店或经营事实。",
        user_id,
    )
    scope = repository.content_scope(TenantSession(tenant_id, user_id, "tenant-user"))
    assert str(scope.account_id) == account["id"]

    guarded_service = ContentService(
        PostgresContentRepository(app_database_url),
        ForcedProductTruthGenerator(),
    )
    guarded = guarded_service.create_from_weak_seed(
        scope,
        "请解释这件没有确认资料的商品。",
    )
    assert guarded == {
        "kind": "question",
        "message": "这条商品解释要以哪件当前品牌已确认商品为依据？",
    }

    service = ContentService(
        PostgresContentRepository(app_database_url),
        DeterministicP1Generator(),
    )
    result = service.create_from_weak_seed(
        scope,
        "请写一条内容，讲一家人可以自然呼应，也可以各自成立。",
    )
    assert result["kind"] == "content"
    body = str(result["body"])
    assert tenant_name in service.identity_summary(scope)["brand"]
    assert "一家人，可以自然呼应" in body
    for forbidden in ("折线之间", "南城店", "ZX-C218", "炭灰", "深绿细格纹"):
        assert forbidden not in body
    assert not is_natural_chat(
        "品牌官方账号能不能聊聊：走进门店只想自己看看，这种沉默是不是也应该被尊重？"
    )
    relationship_service = ContentService(
        PostgresContentRepository(app_database_url),
        ForcedBrandLifeGenerator(),
    )
    relationship_result = relationship_service.create_from_weak_seed(
        scope,
        "品牌官方账号能不能聊聊：走进门店只想自己看看，这种沉默是不是也应该被尊重？",
    )
    assert relationship_result["kind"] == "content"

    with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                (SELECT count(*) FROM business_tasks WHERE tenant_id = %s),
                (SELECT count(*) FROM generation_runs WHERE tenant_id = %s),
                (SELECT count(*) FROM content_versions WHERE tenant_id = %s)
            """,
            (tenant_id, tenant_id, tenant_id),
        )
        before_product_gate = cursor.fetchone()
    product_gate = service.create_from_weak_seed(
        scope,
        "请讲一件当前品牌现在最值得买的外套，并说明面料、价格和适合谁。",
    )
    assert product_gate == {
        "kind": "question",
        "message": "要讲当前品牌的具体商品，请先指定一件已经确认资料的商品。",
    }
    with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                (SELECT count(*) FROM business_tasks WHERE tenant_id = %s),
                (SELECT count(*) FROM generation_runs WHERE tenant_id = %s),
                (SELECT count(*) FROM content_versions WHERE tenant_id = %s)
            """,
            (tenant_id, tenant_id, tenant_id),
        )
        assert cursor.fetchone() == before_product_gate
    task_id = UUID(str(result["task_id"]))
    with pytest.raises(DomainError):
        service.fetch_version(
            TrustedScope(
                UUID("00000000-0000-0000-0000-000000000002"),
                user_id,
                UUID(created["brand_id"]),
                scope.account_id,
            ),
            task_id,
            1,
        )
    with pytest.raises(DomainError):
        service.fetch_version(
            TrustedScope(tenant_id, user_id, UUID(created["brand_id"]), uuid4()),
            task_id,
            1,
        )

    with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                (SELECT count(*) FROM business_tasks
                  WHERE tenant_id = %s AND product_refs <> '[]'::jsonb),
                (SELECT count(*) FROM display_stores WHERE tenant_id = %s),
                (SELECT count(*) FROM content_versions version
                  JOIN business_tasks task
                    ON task.id = version.task_id AND task.tenant_id = version.tenant_id
                  WHERE version.tenant_id = %s AND task.brand_id = %s)
            """,
            (tenant_id, tenant_id, tenant_id, UUID(created["brand_id"])),
        )
        assert cursor.fetchone() == (0, 0, 2)
