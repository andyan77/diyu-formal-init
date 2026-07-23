from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any
from uuid import UUID

import psycopg
import pytest
from psycopg.rows import tuple_row

from src.infrastructure.seed_demo import TENANT_ID

BAIT_TENANT_ID = "00000000-0000-0000-0000-000000000002"
BAIT_BRAND_ID = "00000000-0000-0000-0000-000000000022"
SIBLING_USER_ID = UUID("00000000-0000-0000-0000-000000000012")
SIBLING_BRAND_ID = UUID("00000000-0000-0000-0000-000000000025")
SIBLING_ACCOUNT_ID = UUID("00000000-0000-0000-0000-000000000035")


@pytest.fixture(scope="session")
def app_database_url() -> str:
    return os.environ["DIYU_APP_DATABASE_URL"]


@pytest.fixture(scope="session")
def migrator_database_url() -> str:
    return os.environ["DIYU_MIGRATOR_DATABASE_URL"]


@pytest.fixture(scope="session", autouse=True)
def bait_tenant(migrator_database_url: str) -> Iterator[None]:
    with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO tenants (id, name) VALUES (%s, %s) ON CONFLICT (id) DO NOTHING",
            (BAIT_TENANT_ID, "隔离诱饵租户"),
        )
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (BAIT_TENANT_ID,))
        cursor.execute(
            """
            INSERT INTO brands (id, tenant_id, name, positioning, decision_order, tone)
            VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING
            """,
            (BAIT_BRAND_ID, BAIT_TENANT_ID, "诱饵品牌", "仅用于隔离反证", "不适用", "不适用"),
        )
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
        cursor.execute(
            """
            INSERT INTO users (id, tenant_id, organization_id, display_name)
            VALUES (%s, %s, '00000000-0000-0000-0000-000000000010', '总部内容运营乙')
            ON CONFLICT (id) DO NOTHING
            """,
            (SIBLING_USER_ID, str(TENANT_ID)),
        )
        cursor.execute(
            """
            INSERT INTO brands (id, tenant_id, name, positioning, decision_order, tone)
            VALUES (%s, %s, '同租户诱饵品牌', '仅用于作用域反证', '不适用', '不适用')
            ON CONFLICT (id) DO NOTHING
            """,
            (SIBLING_BRAND_ID, str(TENANT_ID)),
        )
        cursor.execute(
            """
            INSERT INTO content_accounts (id, tenant_id, brand_id, name, channel)
            VALUES (%s, %s, %s, '同租户诱饵账号', '抖音') ON CONFLICT (id) DO NOTHING
            """,
            (SIBLING_ACCOUNT_ID, str(TENANT_ID), SIBLING_BRAND_ID),
        )
        cursor.execute(
            """
            INSERT INTO auth_grants (id, tenant_id, user_id, account_id, role_name)
            VALUES ('00000000-0000-0000-0000-000000000045', %s, %s, %s, '诱饵操作权限')
            ON CONFLICT (id) DO NOTHING
            """,
            (str(TENANT_ID), SIBLING_USER_ID, SIBLING_ACCOUNT_ID),
        )
    yield


@pytest.fixture()
def app_connection(app_database_url: str) -> Iterator[psycopg.Connection[tuple[Any, ...]]]:
    with psycopg.connect(app_database_url, row_factory=tuple_row) as connection:
        yield connection


def set_tenant(cursor: psycopg.Cursor[tuple[Any, ...]], tenant_id: str = str(TENANT_ID)) -> None:
    cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))
