from __future__ import annotations

from typing import Any

import psycopg
import pytest

from src.infrastructure.seed_demo import TENANT_ID
from tests.conftest import BAIT_BRAND_ID, BAIT_TENANT_ID, set_tenant


def test_rls_hides_bait_when_application_query_omits_tenant_filter(
    app_connection: psycopg.Connection[tuple[Any, ...]],
) -> None:
    with app_connection.cursor() as cursor:
        set_tenant(cursor)
        cursor.execute("SELECT id FROM brands ORDER BY name")  # Deliberately omits tenant_id.
        visible_ids = {str(row[0]) for row in cursor.fetchall()}
    assert str(BAIT_BRAND_ID) not in visible_ids


def test_rls_rejects_a_context_writing_b_tenant_id(
    app_connection: psycopg.Connection[tuple[Any, ...]],
) -> None:
    with app_connection.cursor() as cursor:
        set_tenant(cursor)
        with pytest.raises(psycopg.Error):
            cursor.execute(
                """
                INSERT INTO brands (id, tenant_id, name, positioning, decision_order, tone)
                VALUES ('00000000-0000-0000-0000-000000000023', %s, '越权品牌', 'x', 'x', 'x')
                """,
                (BAIT_TENANT_ID,),
            )


def test_rls_fails_closed_without_tenant_context(
    app_connection: psycopg.Connection[tuple[Any, ...]],
) -> None:
    with app_connection.cursor() as cursor, pytest.raises(psycopg.Error):
        cursor.execute("SELECT id FROM brands")
    app_connection.rollback()
    with app_connection.cursor() as cursor, pytest.raises(psycopg.Error):
        cursor.execute(
            """
                INSERT INTO brands (id, tenant_id, name, positioning, decision_order, tone)
                VALUES ('00000000-0000-0000-0000-000000000024', %s, '无上下文写入', 'x', 'x', 'x')
                """,
            (str(TENANT_ID),),
        )


def test_pooled_connection_does_not_leak_previous_tenant_context(
    app_connection: psycopg.Connection[tuple[Any, ...]],
) -> None:
    with app_connection.transaction(), app_connection.cursor() as cursor:
        set_tenant(cursor, str(TENANT_ID))
        cursor.execute("SELECT name FROM brands")
        assert {row[0] for row in cursor.fetchall()} == {"折线之间", "同租户诱饵品牌"}
    with app_connection.transaction(), app_connection.cursor() as cursor:
        set_tenant(cursor, BAIT_TENANT_ID)
        cursor.execute("SELECT name FROM brands")
        assert {row[0] for row in cursor.fetchall()} == {"诱饵品牌"}
