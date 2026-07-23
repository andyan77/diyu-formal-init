from __future__ import annotations

import os
import uuid
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
ORG_ID = UUID("00000000-0000-0000-0000-000000000010")
USER_ID = UUID("00000000-0000-0000-0000-000000000011")
BRAND_ID = UUID("00000000-0000-0000-0000-000000000021")
ACCOUNT_ID = UUID("00000000-0000-0000-0000-000000000031")
GRANT_ID = UUID("00000000-0000-0000-0000-000000000041")
ROLE_ID = UUID("00000000-0000-0000-0000-000000000051")
ACCOUNT_ROLE_ID = UUID("00000000-0000-0000-0000-000000000061")
AUDIENCE_ID = UUID("00000000-0000-0000-0000-000000000071")
STORE_ORG_ID = UUID("00000000-0000-0000-0000-000000000012")
STORE_USER_ID = UUID("00000000-0000-0000-0000-000000000013")
STORE_ID = UUID("00000000-0000-0000-0000-000000000081")
POLICY_ID = UUID("00000000-0000-0000-0000-000000000082")


def seed_demo() -> None:
    database_url = os.environ.get("DIYU_MIGRATOR_DATABASE_URL")
    if not database_url:
        raise RuntimeError("DIYU_MIGRATOR_DATABASE_URL is required to seed demo data")
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO tenants (id, name) VALUES (%s, %s) ON CONFLICT (id) DO NOTHING",
            (TENANT_ID, "折线之间演示租户"),
        )
        cursor.execute(
            "INSERT INTO organizations (id,tenant_id,name) VALUES (%s,%s,%s) ON CONFLICT (id) DO NOTHING",
            (STORE_ORG_ID, TENANT_ID, "折线之间·南城店"),
        )
        cursor.execute(
            "INSERT INTO users (id,tenant_id,organization_id,display_name) VALUES (%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING",
            (STORE_USER_ID, TENANT_ID, STORE_ORG_ID, "南城店陈列执行甲"),
        )
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
        cursor.execute(
            "INSERT INTO organizations (id, tenant_id, name) VALUES (%s, %s, %s) ON CONFLICT (id) DO NOTHING",
            (ORG_ID, TENANT_ID, "折线之间总部"),
        )
        cursor.execute(
            """
                INSERT INTO users (id, tenant_id, organization_id, display_name)
                VALUES (%s, %s, %s, %s) ON CONFLICT (id) DO NOTHING
                """,
            (USER_ID, TENANT_ID, ORG_ID, "总部内容运营甲"),
        )
        cursor.execute(
            """
                INSERT INTO brands (id, tenant_id, name, positioning, decision_order, tone)
                VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING
                """,
            (
                BRAND_ID,
                TENANT_ID,
                "折线之间",
                "为工作、家庭与生活切换中的都市女性保留从容、判断与表达。",
                "先看代价最高的场合，再验证自然活动，最后才看审美、趋势与购买。",
                "成熟、平等、具体、有生活温度与轻微幽默；不制造身体焦虑，不说教，不硬卖。",
            ),
        )
        cursor.execute(
            "UPDATE brands SET strategy_version = %s WHERE tenant_id = %s AND id = %s",
            ("V1.0-first-phase-data-ready", TENANT_ID, BRAND_ID),
        )
        cursor.execute(
            "INSERT INTO display_policies (id,tenant_id,brand_id,version,body) VALUES (%s,%s,%s,'1.0',%s) ON CONFLICT (id) DO NOTHING",
            (
                POLICY_ID,
                TENANT_ID,
                BRAND_ID,
                Jsonb({"focus": "left primary, right weaker response", "density": "do not fill"}),
            ),
        )
        cursor.execute(
            "INSERT INTO display_stores (id,tenant_id,brand_id,control_organization_id,execution_organization_id,name,profile_version,rail_profile) VALUES (%s,%s,%s,%s,%s,%s,'1.0',%s) ON CONFLICT (id) DO NOTHING",
            (
                STORE_ID,
                TENANT_ID,
                BRAND_ID,
                ORG_ID,
                STORE_ORG_ID,
                "折线之间·南城店",
                Jsonb({"upper_side_max": 6, "lower_max": 8, "approach": "left", "front_points": 2}),
            ),
        )
        for sku, facts in {
            "ZX-C218": {
                "category": "double-faced short coat",
                "colors": ["charcoal", "deep green plaid"],
            },
            "ZX-S104": {"category": "warm white shirt"},
            "ZX-K126": {"category": "oat thin knit"},
            "ZX-P211": {"category": "charcoal straight trousers"},
            "ZX-V113": {"category": "charcoal short vest"},
            "ZX-Q117": {"category": "deep olive skirt"},
        }.items():
            cursor.execute(
                "INSERT INTO display_products (id,tenant_id,brand_id,sku,facts) VALUES (%s,%s,%s,%s,%s) ON CONFLICT (tenant_id,brand_id,sku) DO NOTHING",
                (uuid.uuid5(uuid.NAMESPACE_URL, sku), TENANT_ID, BRAND_ID, sku, Jsonb(facts)),
            )
        cursor.execute(
            """
                INSERT INTO content_accounts (id, tenant_id, brand_id, name, channel)
                VALUES (%s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING
                """,
            (ACCOUNT_ID, TENANT_ID, BRAND_ID, "折线之间品牌母账号·抖音", "抖音"),
        )
        cursor.execute(
            """
                INSERT INTO auth_grants (id, tenant_id, user_id, account_id, role_name)
                VALUES (%s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING
                """,
            (GRANT_ID, TENANT_ID, USER_ID, ACCOUNT_ID, "总部零售/服务专家"),
        )
        cursor.execute(
            """
                INSERT INTO content_roles (id, tenant_id, brand_id, name, voice_boundary)
                VALUES (%s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING
                """,
            (
                ROLE_ID,
                TENANT_ID,
                BRAND_ID,
                "总部零售/服务专家",
                "从全国零售与服务方法解释选择，不冒充具体门店店长或顾客。",
            ),
        )
        cursor.execute(
            """
                INSERT INTO account_content_roles (id, tenant_id, account_id, content_role_id)
                VALUES (%s, %s, %s, %s) ON CONFLICT (id) DO NOTHING
                """,
            (ACCOUNT_ROLE_ID, TENANT_ID, ACCOUNT_ID, ROLE_ID),
        )
        cursor.execute(
            """
                INSERT INTO brand_audiences (id, tenant_id, brand_id, description)
                VALUES (%s, %s, %s, %s) ON CONFLICT (brand_id) DO NOTHING
                """,
            (
                AUDIENCE_ID,
                TENANT_ID,
                BRAND_ID,
                "约 30—45 岁、常在工作、家庭与个人生活之间切换的城市女性；任务时不假定个人事实。",
            ),
        )


if __name__ == "__main__":
    seed_demo()
