from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql

from src.gateway.api.app import create_app
from src.gateway.api.settings import Settings
from src.infrastructure.production_auth import OpsSession, ProductionAuthRepository, TenantSession
from src.infrastructure.s3_object_store import S3ObjectStore
from src.infrastructure.seed_demo import (
    ACCOUNT_ID,
    BRAND_ID,
    ORG_ID,
    STORE_CONTENT_ACCOUNT_ID,
    TENANT_ADMIN_USER_ID,
    TENANT_ID,
)
from tests.conftest import BAIT_BRAND_ID, BAIT_TENANT_ID


def _production_settings(database_url: str) -> Settings:
    return Settings.model_validate(
        {
            "DIYU_RUNTIME_MODE": "production",
            "DIYU_APP_DATABASE_URL": database_url,
            "DIYU_SESSION_SECRET": "ui04-full-product-test-session-secret",
            "DIYU_GENERATOR_MODE": "deepseek",
            "DEEPSEEK_API_BASE_URL": "https://example.invalid",
            "DEEPSEEK_API_KEY": "not-a-real-key",
            "DEEPSEEK_MODEL": "deepseek-v4-flash",
            "DIYU_S3_ENDPOINT_URL": "http://127.0.0.1:9000",
            "DIYU_S3_BUCKET": "diyu-test",
            "DIYU_S3_ACCESS_KEY_ID": "test-access-key",
            "DIYU_S3_SECRET_ACCESS_KEY": "test-secret-key",
            "DIYU_S3_REGION": "us-east-1",
        }
    )


def _grant_projection(database_url: str, user_id: UUID) -> tuple[bool, bool, bool, bool]:
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
        cursor.execute(
            """
            SELECT
              EXISTS (
                SELECT 1 FROM auth_grants
                WHERE tenant_id = %s AND user_id = %s AND account_id = %s
                  AND enabled = true AND can_maintain_expression_profile = true
              ),
              EXISTS (
                SELECT 1 FROM tenant_management_grants
                WHERE tenant_id = %s AND user_id = %s AND enabled = true
              ),
              EXISTS (
                SELECT 1 FROM organization_material_maintainers
                WHERE tenant_id = %s AND user_id = %s
              ),
              EXISTS (
                SELECT 1 FROM users WHERE tenant_id = %s AND id = %s AND enabled = true
              )
            """,
            (
                TENANT_ID,
                user_id,
                ACCOUNT_ID,
                TENANT_ID,
                user_id,
                TENANT_ID,
                user_id,
                TENANT_ID,
                user_id,
            ),
        )
        row = cursor.fetchone()
    assert row is not None
    return tuple(bool(value) for value in row)  # type: ignore[return-value]


def _enabled_root_accounts(database_url: str, user_id: UUID) -> tuple[UUID, ...]:
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
        cursor.execute(
            """
            SELECT account.id
            FROM auth_grants grant_record
            JOIN content_accounts account
              ON account.tenant_id = grant_record.tenant_id
             AND account.id = grant_record.account_id
            WHERE grant_record.tenant_id = %s
              AND grant_record.user_id = %s
              AND grant_record.enabled = true
              AND account.enabled = true
              AND account.carrier_of_account_id IS NULL
            ORDER BY account.id
            """,
            (TENANT_ID, user_id),
        )
        return tuple(UUID(str(row[0])) for row in cursor.fetchall())


def _user_enabled(database_url: str, user_id: UUID) -> bool:
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
        cursor.execute(
            "SELECT enabled FROM users WHERE tenant_id = %s AND id = %s",
            (TENANT_ID, user_id),
        )
        row = cursor.fetchone()
    assert row is not None
    return bool(row[0])


def _delete_test_records(
    database_url: str,
    user_id: UUID,
    operator_id: UUID,
    stable_request_id: str | None,
) -> None:
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
        if stable_request_id is not None:
            cursor.execute(
                "DELETE FROM unmet_capability_requests WHERE tenant_id = %s AND stable_request_id = %s",
                (TENANT_ID, stable_request_id),
            )
        cursor.execute("DELETE FROM tenant_sessions WHERE tenant_id = %s AND user_id = %s", (TENANT_ID, user_id))
        cursor.execute(
            "DELETE FROM organization_material_maintainers WHERE tenant_id = %s AND user_id = %s",
            (TENANT_ID, user_id),
        )
        cursor.execute(
            "DELETE FROM tenant_management_grants WHERE tenant_id = %s AND user_id = %s",
            (TENANT_ID, user_id),
        )
        cursor.execute("DELETE FROM auth_grants WHERE tenant_id = %s AND user_id = %s", (TENANT_ID, user_id))
        cursor.execute("DELETE FROM user_activation_tokens WHERE tenant_id = %s AND user_id = %s", (TENANT_ID, user_id))
        cursor.execute("DELETE FROM user_credentials WHERE tenant_id = %s AND user_id = %s", (TENANT_ID, user_id))
        cursor.execute("DELETE FROM users WHERE tenant_id = %s AND id = %s", (TENANT_ID, user_id))
        cursor.execute("DELETE FROM ops_audit_events WHERE operator_id = %s", (operator_id,))
        cursor.execute("DELETE FROM platform_sessions WHERE operator_id = %s", (operator_id,))
        cursor.execute("DELETE FROM platform_operators WHERE id = %s", (operator_id,))


def test_ui04_production_product_seams_are_human_scoped_and_atomic(
    app_database_url: str,
    migrator_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One production-mode seam test: product recovery stays human, APIs stay scoped."""
    monkeypatch.setattr(S3ObjectStore, "is_ready", lambda _: True)
    repository = ProductionAuthRepository(app_database_url)
    manager = TenantSession(TENANT_ID, TENANT_ADMIN_USER_ID, "tenant-admin")
    user_id = UUID(
        repository.create_tenant_user(
            manager,
            f"UI04 权限成员-{uuid4().hex[:8]}",
            f"ui04-member-{uuid4().hex[:12]}",
            ORG_ID,
            None,
            grants_tenant_management=False,
            grants_material_maintenance=False,
        )["user_id"]
    )
    operator_id = uuid4()
    with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO platform_operators (id, username, password_hash, totp_secret) VALUES (%s, %s, %s, %s)",
            (
                operator_id,
                f"ui04-ops-{uuid4().hex[:12]}",
                repository._password_hash("ui04-ops-password-is-long"),
                repository._totp_secret(),
            ),
        )

    stable_request_id: str | None = None
    demo_tenant_disabled = False
    app = create_app(_production_settings(app_database_url))
    manager_token = repository.create_tenant_session(manager)
    member_token = repository.create_tenant_session(TenantSession(TENANT_ID, user_id, "tenant-user"))
    ops_token = repository.create_operator_session(OpsSession(operator_id))
    root = Path(__file__).resolve().parents[1]
    catalog_before = (root / "config" / "content_expression" / "catalog-v1.json").read_bytes()
    inventory_before = (root / "config" / "content_expression" / "capability-inventory-v1.jsonl").read_bytes()

    try:
        with TestClient(app, base_url="https://diyuai.cc") as client:
            public_status = client.get("/status")
            assert public_status.status_code == 200
            assert public_status.headers["content-type"].startswith("text/html")
            assert '"application": "status"' in public_status.text
            assert "服务状态" in public_status.text
            assert all(word not in public_status.text for word in ("PostgreSQL", "S3", "数据库", "供应商"))

            invalid_activation = client.post(
                "/activate/this-is-not-a-real-token", content="password=long-enough-password"
            )
            assert invalid_activation.status_code == 422
            assert invalid_activation.headers["content-type"].startswith("text/html")
            assert "这个链接现在不能继续使用" in invalid_activation.text
            assert '{"detail":' not in invalid_activation.text

            client.cookies.set("diyu_session", manager_token)
            operators = client.get("/api/v1/tenant-management/operators")
            assert operators.status_code == 200
            assert operators.json()
            assert all("default_persona" not in item for item in operators.json())

            readiness = client.get("/api/v1/admin/readiness")
            assert readiness.status_code == 200, readiness.text
            assert next(item for item in readiness.json()["items"] if item["id"] == "account_role")["state"] == "ready"

            refused_self_disable = client.post(f"/api/v1/tenant-management/users/{TENANT_ADMIN_USER_ID}/disable")
            assert refused_self_disable.status_code == 422
            assert _user_enabled(migrator_database_url, TENANT_ADMIN_USER_ID)
            assert client.get("/api/v1/tenant-management/operators").status_code == 200

            updated = client.patch(
                f"/api/v1/tenant-management/users/{user_id}/grants",
                json={
                    "account_id": str(ACCOUNT_ID),
                    "grants_account_access": True,
                    "grants_tenant_management": False,
                    "grants_material_maintenance": True,
                    "grants_expression_profile_maintenance": True,
                },
            )
            assert updated.status_code == 200
            assert updated.json() == {
                "account_access": True,
                "tenant_management": False,
                "material_maintenance": True,
                "expression_profile_maintenance": True,
            }
            assert _grant_projection(migrator_database_url, user_id) == (True, False, True, True)
            assert _enabled_root_accounts(migrator_database_url, user_id) == (ACCOUNT_ID,)

            switched = client.patch(
                f"/api/v1/tenant-management/users/{user_id}/grants",
                json={
                    "account_id": str(STORE_CONTENT_ACCOUNT_ID),
                    "grants_account_access": True,
                    "grants_tenant_management": False,
                    "grants_material_maintenance": True,
                    "grants_expression_profile_maintenance": False,
                },
            )
            assert switched.status_code == 200
            assert _enabled_root_accounts(migrator_database_url, user_id) == (STORE_CONTENT_ACCOUNT_ID,)
            client.cookies.set("diyu_session", member_token)
            assert client.get("/content").status_code == 200

            client.cookies.set("diyu_session", manager_token)
            switched_back = client.patch(
                f"/api/v1/tenant-management/users/{user_id}/grants",
                json={
                    "account_id": str(ACCOUNT_ID),
                    "grants_account_access": True,
                    "grants_tenant_management": False,
                    "grants_material_maintenance": True,
                    "grants_expression_profile_maintenance": True,
                },
            )
            assert switched_back.status_code == 200
            assert _enabled_root_accounts(migrator_database_url, user_id) == (ACCOUNT_ID,)

            before_refusal = _grant_projection(migrator_database_url, user_id)
            client.cookies.set("diyu_session", member_token)
            refused = client.patch(
                f"/api/v1/tenant-management/users/{user_id}/grants",
                json={
                    "account_id": str(ACCOUNT_ID),
                    "grants_account_access": False,
                    "grants_tenant_management": True,
                    "grants_material_maintenance": False,
                    "grants_expression_profile_maintenance": False,
                },
            )
            assert refused.status_code == 403
            assert refused.headers["content-type"].startswith("application/json")
            assert _grant_projection(migrator_database_url, user_id) == before_refusal

            client.cookies.set("diyu_session", member_token)
            scoped_series = client.get("/api/v1/content/series?target=douyin_video")
            assert scoped_series.status_code == 200
            forbidden_series = client.get("/api/v1/content/series?target=xiaohongshu_graphic")
            assert forbidden_series.status_code == 422
            assert forbidden_series.headers["content-type"].startswith("application/json")
            assert "没有明确配置这个平台的发布载体" in forbidden_series.json()["detail"]

            submitted = client.post(
                "/api/v1/content/unmet-capability-requests",
                json={"request_text": f"我想按门店当天客流自动排内容，现在做不到。{uuid4().hex[:6]}"},
            )
            assert submitted.status_code == 201
            stable_request_id = str(submitted.json()["stable_request_id"])
            with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
                cursor.execute("SELECT count(*) FROM system_asset_activations")
                asset_row = cursor.fetchone()
                assert asset_row is not None
                assets_before = int(asset_row[0])

            client.cookies.set("diyu_ops_session", ops_token)
            listed = client.get("/api/v1/ops/tenants")
            assert listed.status_code == 200
            assert any(item["tenant_id"] == str(TENANT_ID) for item in listed.json())
            listed_requests = client.get("/api/v1/ops/unmet-capability-requests")
            assert listed_requests.status_code == 200
            listed_request = next(
                item for item in listed_requests.json() if item["stable_request_id"] == stable_request_id
            )
            assert listed_request["tenant_id"] == str(TENANT_ID)
            disabled = client.post(f"/api/v1/ops/tenants/{TENANT_ID}/disable")
            assert disabled.status_code == 200 and disabled.json() == {"disabled": True}
            demo_tenant_disabled = True
            assert any(
                item["tenant_id"] == str(TENANT_ID) and item["enabled"] is False
                for item in client.get("/api/v1/ops/tenants").json()
            )
            enabled = client.post(f"/api/v1/ops/tenants/{TENANT_ID}/enable")
            assert enabled.status_code == 200 and enabled.json() == {"enabled": True}
            demo_tenant_disabled = False

            classified = client.post(
                f"/api/v1/ops/unmet-capability-requests/{stable_request_id}",
                json={
                    "gap_type": "generation_method",
                    "status": "answered",
                    "response_text": "这条需求已登记为后续方向，当前不会自动改变你的创作资料。",
                },
            )
            assert classified.status_code == 200
            assert classified.json()["status"] == "answered"
            with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
                cursor.execute("SELECT count(*) FROM system_asset_activations")
                asset_row = cursor.fetchone()
                assert asset_row is not None
                assert int(asset_row[0]) == assets_before
            assert (root / "config" / "content_expression" / "catalog-v1.json").read_bytes() == catalog_before
            assert (
                root / "config" / "content_expression" / "capability-inventory-v1.jsonl"
            ).read_bytes() == inventory_before

            logged_out = client.post("/ops/logout", follow_redirects=False)
            assert logged_out.status_code == 303
            assert logged_out.headers["location"] == "/ops/login"
            after_logout = client.get("/api/v1/ops/tenants")
            assert after_logout.status_code == 401
            assert after_logout.headers["content-type"].startswith("application/json")
    finally:
        if demo_tenant_disabled:
            repository.set_tenant_enabled(OpsSession(operator_id), TENANT_ID, True)
        repository.revoke_tenant_session(manager_token)
        repository.revoke_tenant_session(member_token)
        repository.revoke_operator_session(ops_token)
        _delete_test_records(migrator_database_url, user_id, operator_id, stable_request_id)


def test_ops_gap_functions_set_rls_context_and_refuse_ambiguous_keys(
    app_database_url: str,
    migrator_database_url: str,
) -> None:
    """Exercise the installed function bodies under a production-like non-bypass owner."""
    stable_request_id = f"UI04-RLS-{uuid4().hex}"
    main_request_id = uuid4()
    bait_request_id = uuid4()
    bait_organization_id = uuid4()
    bait_user_id = uuid4()
    suffix = uuid4().hex[:16]
    owner_name = f"ui04_rls_owner_{suffix}"
    list_function = f"ui04_ops_list_{suffix}"
    classify_function = f"ui04_ops_classify_{suffix}"
    registry_before: tuple[bool, object] | None = None
    registry_read = False
    test_role_created = False
    try:
        with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT pg_get_functiondef('ops_unmet_capability_requests()'::regprocedure),
                       pg_get_functiondef(
                           'ops_classify_unmet_capability_request(text,text,text,text)'
                           ::regprocedure
                       ),
                       (
                           SELECT role.rolname
                             FROM pg_proc AS routine
                             JOIN pg_roles AS role ON role.oid = routine.proowner
                            WHERE routine.oid =
                                  'ops_unmet_capability_requests()'::regprocedure
                       ),
                       (
                           SELECT table_class.relforcerowsecurity
                             FROM pg_class AS table_class
                            WHERE table_class.oid = 'unmet_capability_requests'::regclass
                       ),
                       (
                           SELECT role.rolbypassrls
                             FROM pg_roles AS role
                            WHERE role.rolname = 'diyu_app'
                       )
                """
            )
            metadata = cursor.fetchone()
            assert metadata is not None
            list_definition = str(metadata[0])
            classify_definition = str(metadata[1])
            assert metadata[2:] == ("diyu_migrator", True, False)
            assert "set_config('app.tenant_id'" in list_definition
            assert "request.tenant_id = registry_row.tenant_id" in list_definition
            assert "set_config('app.tenant_id'" in classify_definition
            assert "match_count <> 1" in classify_definition
            cursor.execute(
                """
                SELECT routine.oid::regprocedure::text,
                       owner.rolname,
                       routine.prosecdef,
                       routine.proconfig,
                       has_function_privilege('diyu_app', routine.oid, 'EXECUTE'),
                       NOT EXISTS (
                           SELECT 1
                             FROM aclexplode(
                                 COALESCE(
                                     routine.proacl,
                                     acldefault('f', routine.proowner)
                                 )
                             ) AS grant_record
                            WHERE grant_record.grantee = 0
                              AND grant_record.privilege_type = 'EXECUTE'
                       )
                  FROM pg_proc AS routine
                  JOIN pg_roles AS owner ON owner.oid = routine.proowner
                 WHERE routine.oid IN (
                     'ops_unmet_capability_requests()'::regprocedure,
                     'ops_classify_unmet_capability_request(text,text,text,text)'
                     ::regprocedure
                 )
                 ORDER BY routine.oid::regprocedure::text
                """
            )
            actual_functions = cursor.fetchall()
            assert len(actual_functions) == 2
            assert all(row[1] == "diyu_migrator" for row in actual_functions)
            assert all(row[2] is True for row in actual_functions)
            assert all(row[3] == ["search_path=pg_catalog, public"] for row in actual_functions)
            assert all(row[4] is True and row[5] is True for row in actual_functions)

            cursor.execute(
                sql.SQL(
                    """
                    CREATE ROLE {} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
                    NOINHERIT NOBYPASSRLS
                    """
                ).format(sql.Identifier(owner_name))
            )
            test_role_created = True
            cursor.execute(
                list_definition.replace(
                    "public.ops_unmet_capability_requests()",
                    f"public.{list_function}()",
                    1,
                )
            )
            cursor.execute(
                classify_definition.replace(
                    "public.ops_classify_unmet_capability_request(",
                    f"public.{classify_function}(",
                    1,
                )
            )
            cursor.execute(
                sql.SQL("ALTER FUNCTION {}() OWNER TO {}").format(
                    sql.Identifier("public", list_function),
                    sql.Identifier(owner_name),
                )
            )
            cursor.execute(
                sql.SQL("ALTER FUNCTION {}(text, text, text, text) OWNER TO {}").format(
                    sql.Identifier("public", classify_function),
                    sql.Identifier(owner_name),
                )
            )
            cursor.execute(
                sql.SQL("GRANT SELECT ON TABLE public.ops_tenant_registry TO {}").format(
                    sql.Identifier(owner_name)
                )
            )
            cursor.execute(
                sql.SQL(
                    """
                    GRANT SELECT, UPDATE ON TABLE public.unmet_capability_requests TO {}
                    """
                ).format(sql.Identifier(owner_name))
            )
            cursor.execute(
                sql.SQL("REVOKE ALL ON FUNCTION {}() FROM PUBLIC").format(
                    sql.Identifier("public", list_function)
                )
            )
            cursor.execute(
                sql.SQL(
                    """
                    REVOKE ALL ON FUNCTION {}(text, text, text, text) FROM PUBLIC
                    """
                ).format(sql.Identifier("public", classify_function))
            )
            cursor.execute(
                sql.SQL("GRANT EXECUTE ON FUNCTION {}() TO diyu_app").format(
                    sql.Identifier("public", list_function)
                )
            )
            cursor.execute(
                sql.SQL(
                    """
                    GRANT EXECUTE ON FUNCTION {}(text, text, text, text) TO diyu_app
                    """
                ).format(sql.Identifier("public", classify_function))
            )

            cursor.execute(
                "SELECT enabled, disabled_at FROM ops_tenant_registry WHERE tenant_id = %s",
                (BAIT_TENANT_ID,),
            )
            registry_before = cursor.fetchone()
            registry_read = True
            cursor.execute(
                """
                INSERT INTO ops_tenant_registry (tenant_id, enabled, disabled_at)
                VALUES (%s, true, NULL)
                ON CONFLICT (tenant_id) DO UPDATE SET enabled = true, disabled_at = NULL
                """,
                (BAIT_TENANT_ID,),
            )
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
            cursor.execute(
                """
                INSERT INTO unmet_capability_requests (
                    id, tenant_id, stable_request_id, brand_id, account_id, created_by,
                    request_text, catalog_version
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'catalog-v1')
                """,
                (
                    main_request_id,
                    TENANT_ID,
                    stable_request_id,
                    BRAND_ID,
                    ACCOUNT_ID,
                    TENANT_ADMIN_USER_ID,
                    "生产式新连接租户上下文反证",
                ),
            )
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (BAIT_TENANT_ID,))
            cursor.execute(
                "INSERT INTO organizations (id, tenant_id, name) VALUES (%s, %s, %s)",
                (bait_organization_id, BAIT_TENANT_ID, f"UI04 诱饵组织 {uuid4().hex[:8]}"),
            )
            cursor.execute(
                """
                INSERT INTO users (id, tenant_id, organization_id, display_name)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    bait_user_id,
                    BAIT_TENANT_ID,
                    bait_organization_id,
                    f"UI04 诱饵成员 {uuid4().hex[:8]}",
                ),
            )
            cursor.execute(
                """
                INSERT INTO unmet_capability_requests (
                    id, tenant_id, stable_request_id, brand_id, created_by,
                    request_text, catalog_version
                ) VALUES (%s, %s, %s, %s, %s, %s, 'catalog-v1')
                """,
                (
                    bait_request_id,
                    BAIT_TENANT_ID,
                    stable_request_id,
                    BAIT_BRAND_ID,
                    bait_user_id,
                    "相邻租户同键反证",
                ),
            )

        with psycopg.connect(app_database_url) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT current_setting('app.tenant_id', true)")
            assert cursor.fetchone() == (None,)
            cursor.execute(
                """
                SELECT routine.proname,
                       routine.prosecdef,
                       routine.proconfig,
                       owner.rolbypassrls,
                       has_function_privilege('diyu_app', routine.oid, 'EXECUTE')
                  FROM pg_proc AS routine
                  JOIN pg_roles AS owner ON owner.oid = routine.proowner
                 WHERE routine.proname = ANY(%s)
                 ORDER BY routine.proname
                """,
                ([classify_function, list_function],),
            )
            test_functions = cursor.fetchall()
            assert {row[0] for row in test_functions} == {
                classify_function,
                list_function,
            }
            assert all(row[1] is True for row in test_functions)
            assert all(row[2] == ["search_path=pg_catalog, public"] for row in test_functions)
            assert all(row[3] is False and row[4] is True for row in test_functions)
            cursor.execute(
                sql.SQL(
                    """
                    SELECT tenant_id
                      FROM {}()
                     WHERE stable_request_id = %s
                     ORDER BY tenant_id
                    """
                ).format(sql.Identifier("public", list_function)),
                (stable_request_id,),
            )
            assert cursor.fetchall() == [(TENANT_ID,), (UUID(BAIT_TENANT_ID),)]
            cursor.execute(
                sql.SQL(
                    """
                    SELECT {}(%s, 'generation_method', 'answered', '不应写入')
                    """
                ).format(sql.Identifier("public", classify_function)),
                (stable_request_id,),
            )
            assert cursor.fetchone() == (None,)

        with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
            for tenant_id in (TENANT_ID, UUID(BAIT_TENANT_ID)):
                cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),))
                cursor.execute(
                    """
                    SELECT status, response_text
                      FROM unmet_capability_requests
                     WHERE tenant_id = %s AND stable_request_id = %s
                    """,
                    (tenant_id, stable_request_id),
                )
                assert cursor.fetchone() == ("received", "")
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (BAIT_TENANT_ID,))
            cursor.execute(
                """
                DELETE FROM unmet_capability_requests
                 WHERE tenant_id = %s AND stable_request_id = %s
                """,
                (BAIT_TENANT_ID, stable_request_id),
            )

        with psycopg.connect(app_database_url) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT current_setting('app.tenant_id', true)")
            assert cursor.fetchone() == (None,)
            cursor.execute(
                sql.SQL(
                    """
                    SELECT {}(%s, 'generation_method', 'answered', '已安全回告')
                    """
                ).format(sql.Identifier("public", classify_function)),
                (stable_request_id,),
            )
            assert cursor.fetchone() == (TENANT_ID,)

        with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
            cursor.execute(
                """
                SELECT status, response_text
                  FROM unmet_capability_requests
                 WHERE tenant_id = %s AND stable_request_id = %s
                """,
                (TENANT_ID, stable_request_id),
            )
            assert cursor.fetchone() == ("answered", "已安全回告")
    finally:
        with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("DROP FUNCTION IF EXISTS {}()").format(
                    sql.Identifier("public", list_function)
                )
            )
            cursor.execute(
                sql.SQL("DROP FUNCTION IF EXISTS {}(text, text, text, text)").format(
                    sql.Identifier("public", classify_function)
                )
            )
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
            cursor.execute(
                "DELETE FROM unmet_capability_requests WHERE tenant_id = %s AND id = %s",
                (TENANT_ID, main_request_id),
            )
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (BAIT_TENANT_ID,))
            cursor.execute(
                "DELETE FROM unmet_capability_requests WHERE tenant_id = %s AND id = %s",
                (BAIT_TENANT_ID, bait_request_id),
            )
            cursor.execute("DELETE FROM users WHERE tenant_id = %s AND id = %s", (BAIT_TENANT_ID, bait_user_id))
            cursor.execute(
                "DELETE FROM organizations WHERE tenant_id = %s AND id = %s",
                (BAIT_TENANT_ID, bait_organization_id),
            )
            if registry_read:
                if registry_before is None:
                    cursor.execute(
                        "DELETE FROM ops_tenant_registry WHERE tenant_id = %s",
                        (BAIT_TENANT_ID,),
                    )
                else:
                    cursor.execute(
                        """
                        UPDATE ops_tenant_registry
                           SET enabled = %s, disabled_at = %s
                         WHERE tenant_id = %s
                        """,
                        (registry_before[0], registry_before[1], BAIT_TENANT_ID),
                    )
            cursor.execute("SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = %s)", (owner_name,))
            role_still_exists = cursor.fetchone()
            if test_role_created and role_still_exists == (True,):
                cursor.execute(
                    sql.SQL("REVOKE ALL ON TABLE public.ops_tenant_registry FROM {}").format(
                        sql.Identifier(owner_name)
                    )
                )
                cursor.execute(
                    sql.SQL(
                        """
                        REVOKE ALL ON TABLE public.unmet_capability_requests FROM {}
                        """
                    ).format(sql.Identifier(owner_name))
                )
                cursor.execute(
                    sql.SQL("DROP ROLE {}").format(sql.Identifier(owner_name))
                )
