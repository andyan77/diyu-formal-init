from __future__ import annotations

from uuid import UUID, uuid4

import psycopg

from src.infrastructure.seed_demo import BRAND_ID, TENANT_ID, USER_ID

_BAIT_TENANT_ID = UUID("00000000-0000-0000-0000-000000000002")
_BAIT_BRAND_ID = UUID("00000000-0000-0000-0000-000000000022")


def _insert_version_chain(
    database_url: str,
    *,
    tenant_id: UUID,
    brand_id: UUID,
    user_id: UUID,
    version_count: int,
    business_data_kind: str = "synthetic_business_fixture",
) -> tuple[UUID, UUID, tuple[UUID, ...], tuple[UUID, ...]]:
    account_id = uuid4()
    task_id = uuid4()
    item_id = uuid4()
    run_ids = tuple(uuid4() for _ in range(version_count))
    version_ids = tuple(uuid4() for _ in range(version_count))
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),))
        cursor.execute(
            """
            INSERT INTO content_accounts
                (id, tenant_id, brand_id, name, channel, business_data_kind)
            VALUES (%s, %s, %s, %s, 'test', %s)
            """,
            (
                account_id,
                tenant_id,
                brand_id,
                f"UI12 append-only fixture {account_id}",
                business_data_kind,
            ),
        )
        cursor.execute(
            """
            INSERT INTO business_tasks
                (id, tenant_id, brand_id, account_id, logical_account_id,
                 created_by, weak_seed)
            VALUES (%s, %s, %s, %s, %s, %s, 'UI12 append-only fixture')
            """,
            (task_id, tenant_id, brand_id, account_id, account_id, user_id),
        )
        cursor.execute(
            """
            INSERT INTO content_items (id, tenant_id, task_id, current_version)
            VALUES (%s, %s, %s, %s)
            """,
            (item_id, tenant_id, task_id, version_count),
        )
        for number, (run_id, version_id) in enumerate(
            zip(run_ids, version_ids, strict=True),
            start=1,
        ):
            cursor.execute(
                """
                INSERT INTO generation_runs
                    (id, tenant_id, task_id, model, status, completed_at)
                VALUES (%s, %s, %s, 'fixture', 'succeeded', now())
                """,
                (run_id, tenant_id, task_id),
            )
            cursor.execute(
                """
                INSERT INTO content_versions
                    (id, tenant_id, item_id, task_id, run_id, version_number,
                     outline, body, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    version_id,
                    tenant_id,
                    item_id,
                    task_id,
                    run_id,
                    number,
                    f"fixture outline {number}",
                    f"fixture body {number}",
                    user_id,
                ),
            )
    return account_id, task_id, run_ids, version_ids


def _set_exact_maintenance_boundary(
    cursor: psycopg.Cursor[tuple[object, ...]],
    tenant_id: UUID,
    version_id: UUID,
) -> None:
    cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),))
    cursor.execute(
        "SELECT set_config('diyu.content_version_maintenance', "
        "'delete_synthetic_fixture', true)"
    )
    cursor.execute(
        "SELECT set_config("
        "'diyu.content_version_maintenance_transaction_id', "
        "pg_current_xact_id()::text, true)"
    )
    cursor.execute(
        "SELECT set_config('diyu.content_version_maintenance_tenant_id', %s, true)",
        (str(tenant_id),),
    )
    cursor.execute(
        "SELECT set_config('diyu.content_version_maintenance_version_id', %s, true)",
        (str(version_id),),
    )


def _delete_fixture_chain(
    database_url: str,
    *,
    tenant_id: UUID,
    account_id: UUID,
    task_id: UUID,
    run_ids: tuple[UUID, ...],
    version_ids: tuple[UUID, ...],
) -> None:
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        for version_id in version_ids:
            _set_exact_maintenance_boundary(cursor, tenant_id, version_id)
            cursor.execute(
                "DELETE FROM content_versions WHERE tenant_id = %s AND id = %s",
                (tenant_id, version_id),
            )
        cursor.execute(
            "DELETE FROM generation_runs WHERE tenant_id = %s AND id = ANY(%s)",
            (tenant_id, list(run_ids)),
        )
        cursor.execute(
            "DELETE FROM content_items WHERE tenant_id = %s AND task_id = %s",
            (tenant_id, task_id),
        )
        cursor.execute(
            "DELETE FROM business_tasks WHERE tenant_id = %s AND id = %s",
            (tenant_id, task_id),
        )
        cursor.execute(
            "DELETE FROM content_accounts WHERE tenant_id = %s AND id = %s",
            (tenant_id, account_id),
        )


def test_application_role_has_only_append_and_read_version_privileges(
    migrator_database_url: str,
) -> None:
    with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                has_table_privilege('diyu_app', 'content_versions', 'SELECT'),
                has_table_privilege('diyu_app', 'content_versions', 'INSERT'),
                has_table_privilege('diyu_app', 'content_versions', 'UPDATE'),
                has_table_privilege('diyu_app', 'content_versions', 'DELETE')
            """
        )
        assert cursor.fetchone() == (True, True, False, False)


def test_delete_requires_exact_transaction_local_synthetic_maintenance_boundary(
    app_database_url: str,
    migrator_database_url: str,
) -> None:
    main_chain = _insert_version_chain(
        migrator_database_url,
        tenant_id=TENANT_ID,
        brand_id=BRAND_ID,
        user_id=USER_ID,
        version_count=2,
    )
    bait_user_id = uuid4()
    bait_organization_id = uuid4()
    with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(_BAIT_TENANT_ID),))
        cursor.execute(
            """
            INSERT INTO organizations
                (id, tenant_id, name, organization_level, business_data_kind)
            VALUES (%s, %s, %s, 'company', 'synthetic_business_fixture')
            """,
            (bait_organization_id, _BAIT_TENANT_ID, f"UI12 bait org {bait_organization_id}"),
        )
        cursor.execute(
            """
            INSERT INTO users (id, tenant_id, organization_id, display_name)
            VALUES (%s, %s, %s, 'UI12 bait user')
            """,
            (bait_user_id, _BAIT_TENANT_ID, bait_organization_id),
        )
    bait_chain = _insert_version_chain(
        migrator_database_url,
        tenant_id=_BAIT_TENANT_ID,
        brand_id=_BAIT_BRAND_ID,
        user_id=bait_user_id,
        version_count=1,
    )
    main_account, main_task, main_runs, main_versions = main_chain
    bait_account, bait_task, bait_runs, bait_versions = bait_chain
    formal_chain = _insert_version_chain(
        migrator_database_url,
        tenant_id=TENANT_ID,
        brand_id=BRAND_ID,
        user_id=USER_ID,
        version_count=1,
        business_data_kind="formal_business_data",
    )
    formal_account, formal_task, formal_runs, formal_versions = formal_chain
    try:
        for tenant_id, version_id in (
            (TENANT_ID, main_versions[0]),
            (_BAIT_TENANT_ID, bait_versions[0]),
        ):
            with (
                psycopg.connect(app_database_url) as connection,
                connection.cursor() as cursor,
            ):
                cursor.execute(
                    "SELECT set_config('app.tenant_id', %s, true)",
                    (str(TENANT_ID),),
                )
                cursor.execute(
                    "SELECT set_config('diyu.content_version_maintenance', "
                    "'delete_synthetic_fixture', true)"
                )
                cursor.execute(
                    "SELECT set_config('diyu.content_version_maintenance_tenant_id', %s, true)",
                    (str(tenant_id),),
                )
                cursor.execute(
                    "SELECT set_config('diyu.content_version_maintenance_version_id', %s, true)",
                    (str(version_id),),
                )
                try:
                    cursor.execute(
                        "DELETE FROM content_versions WHERE tenant_id = %s AND id = %s",
                        (tenant_id, version_id),
                    )
                except psycopg.errors.InsufficientPrivilege:
                    pass
                else:
                    raise AssertionError("diyu_app unexpectedly deleted an append-only version")

        with (
            psycopg.connect(migrator_database_url) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
            try:
                cursor.execute(
                    "DELETE FROM content_versions WHERE tenant_id = %s AND id = %s",
                    (TENANT_ID, main_versions[0]),
                )
            except psycopg.errors.RaiseException as error:
                assert "exact transaction-local maintenance boundary" in str(error)
            else:
                raise AssertionError("migrator unexpectedly deleted without maintenance boundary")

        with (
            psycopg.connect(migrator_database_url) as connection,
            connection.cursor() as cursor,
        ):
            _set_exact_maintenance_boundary(cursor, TENANT_ID, main_versions[0])
            try:
                cursor.execute(
                    "DELETE FROM content_versions WHERE tenant_id = %s AND id = ANY(%s)",
                    (TENANT_ID, list(main_versions)),
                )
            except psycopg.errors.RaiseException as error:
                assert "exact transaction-local maintenance boundary" in str(error)
            else:
                raise AssertionError("a broad maintenance delete unexpectedly succeeded")

        with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
            cursor.execute(
                "SELECT count(*) FROM content_versions WHERE tenant_id = %s AND id = ANY(%s)",
                (TENANT_ID, list(main_versions)),
            )
            assert cursor.fetchone() == (2,)

        with (
            psycopg.connect(migrator_database_url) as connection,
            connection.cursor() as cursor,
        ):
            _set_exact_maintenance_boundary(cursor, TENANT_ID, main_versions[0])
            cursor.execute(
                "DELETE FROM content_versions WHERE tenant_id = %s AND id = %s",
                (TENANT_ID, main_versions[0]),
            )

        with (
            psycopg.connect(migrator_database_url) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
            try:
                cursor.execute(
                    "DELETE FROM content_versions WHERE tenant_id = %s AND id = %s",
                    (TENANT_ID, main_versions[1]),
                )
            except psycopg.errors.RaiseException:
                pass
            else:
                raise AssertionError("transaction-local maintenance boundary leaked")

        with (
            psycopg.connect(migrator_database_url) as connection,
            connection.cursor() as cursor,
        ):
            _set_exact_maintenance_boundary(cursor, TENANT_ID, formal_versions[0])
            try:
                cursor.execute(
                    "DELETE FROM content_versions WHERE tenant_id = %s AND id = %s",
                    (TENANT_ID, formal_versions[0]),
                )
            except psycopg.errors.RaiseException as error:
                assert "only a synthetic fixture version" in str(error)
            else:
                raise AssertionError("maintenance deleted a non-synthetic version")

        main_versions = (main_versions[1],)
    finally:
        _delete_fixture_chain(
            migrator_database_url,
            tenant_id=TENANT_ID,
            account_id=main_account,
            task_id=main_task,
            run_ids=main_runs,
            version_ids=main_versions,
        )
        _delete_fixture_chain(
            migrator_database_url,
            tenant_id=_BAIT_TENANT_ID,
            account_id=bait_account,
            task_id=bait_task,
            run_ids=bait_runs,
            version_ids=bait_versions,
        )
        with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
            cursor.execute(
                """
                UPDATE content_accounts
                   SET business_data_kind = 'synthetic_business_fixture'
                 WHERE tenant_id = %s AND id = %s
                """,
                (TENANT_ID, formal_account),
            )
        _delete_fixture_chain(
            migrator_database_url,
            tenant_id=TENANT_ID,
            account_id=formal_account,
            task_id=formal_task,
            run_ids=formal_runs,
            version_ids=formal_versions,
        )
        with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT set_config('app.tenant_id', %s, true)",
                (str(_BAIT_TENANT_ID),),
            )
            cursor.execute(
                "DELETE FROM users WHERE tenant_id = %s AND id = %s",
                (_BAIT_TENANT_ID, bait_user_id),
            )
            cursor.execute(
                "DELETE FROM organizations WHERE tenant_id = %s AND id = %s",
                (_BAIT_TENANT_ID, bait_organization_id),
            )
