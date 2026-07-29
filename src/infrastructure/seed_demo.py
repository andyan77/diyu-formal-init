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
STORE_CONTENT_USER_ID = UUID("00000000-0000-0000-0000-000000000014")
TENANT_ADMIN_USER_ID = UUID("00000000-0000-0000-0000-000000000015")
DUAL_QUALIFIED_USER_ID = UUID("00000000-0000-0000-0000-000000000016")
EXTERNAL_OPERATOR_USER_ID = UUID("00000000-0000-0000-0000-000000000017")
EXTERNAL_OPERATOR_ORG_ID = UUID("00000000-0000-0000-0000-000000000018")
STORE_CONTENT_ACCOUNT_ID = UUID("00000000-0000-0000-0000-000000000032")
HEADQUARTERS_XIAOHONGSHU_ACCOUNT_ID = UUID("00000000-0000-0000-0000-000000000033")
HEADQUARTERS_WECHAT_CHANNELS_ACCOUNT_ID = UUID("00000000-0000-0000-0000-000000000034")
STORE_CONTENT_GRANT_ID = UUID("00000000-0000-0000-0000-000000000042")
HEADQUARTERS_XIAOHONGSHU_GRANT_ID = UUID("00000000-0000-0000-0000-000000000043")
HEADQUARTERS_WECHAT_CHANNELS_GRANT_ID = UUID("00000000-0000-0000-0000-000000000044")
DUAL_QUALIFIED_GRANT_ID = UUID("00000000-0000-0000-0000-000000000151")
EXTERNAL_OPERATOR_GRANT_ID = UUID("00000000-0000-0000-0000-000000000152")
STORE_CONTENT_ROLE_ID = UUID("00000000-0000-0000-0000-000000000053")
STORE_CONTENT_ACCOUNT_ROLE_ID = UUID("00000000-0000-0000-0000-000000000063")
HEADQUARTERS_XIAOHONGSHU_ACCOUNT_ROLE_ID = UUID("00000000-0000-0000-0000-000000000064")
HEADQUARTERS_WECHAT_CHANNELS_ACCOUNT_ROLE_ID = UUID("00000000-0000-0000-0000-000000000065")
STORE_ID = UUID("00000000-0000-0000-0000-000000000081")
POLICY_ID = UUID("00000000-0000-0000-0000-000000000082")
BRAND_EXPRESSION_BASELINE_ID = UUID("00000000-0000-0000-0000-000000000091")
MATERIAL_MAINTAINER_ID = UUID("00000000-0000-0000-0000-000000000092")
TENANT_ADMIN_GRANT_ID = UUID("00000000-0000-0000-0000-000000000093")
DUAL_TENANT_ADMIN_GRANT_ID = UUID("00000000-0000-0000-0000-000000000094")
USER_DEFAULT_PERSONA_ID = UUID("00000000-0000-0000-0000-000000000095")
DUAL_DEFAULT_PERSONA_ID = UUID("00000000-0000-0000-0000-000000000096")
EXTERNAL_DEFAULT_PERSONA_ID = UUID("00000000-0000-0000-0000-000000000097")
STORE_DISPLAY_ACCESS_GRANT_ID = UUID("00000000-0000-0000-0000-000000000098")


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
            "INSERT INTO ops_tenant_registry (tenant_id) VALUES (%s) ON CONFLICT (tenant_id) DO NOTHING",
            (TENANT_ID,),
        )
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
        cursor.execute(
            "INSERT INTO organizations (id,tenant_id,name,organization_level) "
            "VALUES (%s,%s,%s,'operating_unit') "
            "ON CONFLICT (id) DO UPDATE SET organization_level = EXCLUDED.organization_level",
            (STORE_ORG_ID, TENANT_ID, "折线之间·南城店"),
        )
        cursor.execute(
            "INSERT INTO users "
            "(id,tenant_id,organization_id,display_name,entry_kind) "
            "VALUES (%s,%s,%s,%s,'tenant_user') "
            "ON CONFLICT (id) DO UPDATE SET entry_kind = EXCLUDED.entry_kind",
            (STORE_USER_ID, TENANT_ID, STORE_ORG_ID, "南城店陈列执行甲"),
        )
        cursor.execute(
            "INSERT INTO users "
            "(id,tenant_id,organization_id,display_name,entry_kind) "
            "VALUES (%s,%s,%s,%s,'tenant_user') "
            "ON CONFLICT (id) DO UPDATE SET entry_kind = EXCLUDED.entry_kind",
            (STORE_CONTENT_USER_ID, TENANT_ID, STORE_ORG_ID, "南城店内容运营甲"),
        )
        cursor.execute(
            "INSERT INTO organizations "
            "(id, tenant_id, name, organization_level) "
            "VALUES (%s, %s, %s, 'company') "
            "ON CONFLICT (id) DO UPDATE SET organization_level = EXCLUDED.organization_level",
            (ORG_ID, TENANT_ID, "折线之间总部"),
        )
        cursor.execute(
            "INSERT INTO organizations "
            "(id, tenant_id, name, organization_level) "
            "VALUES (%s, %s, %s, 'operating_unit') "
            "ON CONFLICT (id) DO UPDATE SET organization_level = EXCLUDED.organization_level",
            (EXTERNAL_OPERATOR_ORG_ID, TENANT_ID, "折线之间外部代运营服务方"),
        )
        cursor.execute(
            """
                INSERT INTO users
                    (id, tenant_id, organization_id, display_name, entry_kind)
                VALUES (%s, %s, %s, %s, 'tenant_user')
                ON CONFLICT (id) DO UPDATE SET entry_kind = EXCLUDED.entry_kind
                """,
            (USER_ID, TENANT_ID, ORG_ID, "总部内容运营甲"),
        )
        for user_id, organization_id, display_name, entry_kind in (
            (TENANT_ADMIN_USER_ID, ORG_ID, "总部租户管理员甲", "tenant_admin"),
            (DUAL_QUALIFIED_USER_ID, ORG_ID, "总部租户管理员乙", "tenant_admin"),
            (
                EXTERNAL_OPERATOR_USER_ID,
                EXTERNAL_OPERATOR_ORG_ID,
                "外部代运营乙",
                "tenant_user",
            ),
        ):
            cursor.execute(
                "INSERT INTO users "
                "(id, tenant_id, organization_id, display_name, entry_kind) "
                "VALUES (%s, %s, %s, %s, %s) "
                "ON CONFLICT (id) DO UPDATE SET entry_kind = EXCLUDED.entry_kind",
                (user_id, TENANT_ID, organization_id, display_name, entry_kind),
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
            """
            INSERT INTO brand_expression_baselines (id, tenant_id, brand_id, version, draft, status)
            VALUES (%s, %s, %s, 1, %s, 'draft') ON CONFLICT (tenant_id, brand_id) DO NOTHING
            """,
            (
                BRAND_EXPRESSION_BASELINE_ID,
                TENANT_ID,
                BRAND_ID,
                "我们先把真实穿衣处境和商品取舍讲清楚：成熟、平等、具体，有生活温度，"
                "不利用身体、年龄或身份焦虑，也不把没有证据的故事说成事实。",
            ),
        )
        cursor.execute(
            "INSERT INTO display_policies (id,tenant_id,brand_id,version,body) VALUES (%s,%s,%s,'1.0',%s) "
            "ON CONFLICT (id) DO UPDATE SET body=EXCLUDED.body",
            (
                POLICY_ID,
                TENANT_ID,
                BRAND_ID,
                Jsonb(
                    {
                        "schema": "dm01-wall-double-rail-v1",
                        "theme": "双面短外套与低饱和上下装",
                        "density": "中低密度",
                        "primary_focus_skus": ["ZX-C218"],
                        "secondary_response_skus": ["ZX-C218"],
                        "secondary_required": False,
                    }
                ),
            ),
        )
        cursor.execute(
            "INSERT INTO display_stores (id,tenant_id,brand_id,control_organization_id,execution_organization_id,"
            "name,profile_version,rail_profile) VALUES (%s,%s,%s,%s,%s,%s,'1.0',%s) "
            "ON CONFLICT (id) DO UPDATE SET rail_profile=EXCLUDED.rail_profile",
            (
                STORE_ID,
                TENANT_ID,
                BRAND_ID,
                ORG_ID,
                STORE_ORG_ID,
                "折线之间·南城店",
                Jsonb(
                    {
                        "schema": "dm01-wall-double-rail-v1",
                        "upper_comfort_capacity": 8,
                        "lower_comfort_capacity": 8,
                        "primary_position": "left",
                        "secondary_position": "right",
                        "golden_sight": "上杆左侧主正挂与右侧较弱回应",
                        "approach": "left",
                        "lower_reserved_positions": [],
                        "avoid_long_upper_lower_overlap": True,
                        "constraints": ["保持两个固定正挂点", "不超过舒适容量", "不遮挡取放动线"],
                    }
                ),
            ),
        )
        for sku, facts in {
            "ZX-C218": {
                "name": "双面短外套",
                "entity_kind": "apparel_product",
                "category": "double-faced short coat",
                "colors": ["炭灰纯色", "深绿细格纹"],
                "display_family": "upper",
                "is_long": False,
                "both_sides_complete": True,
                "pockets_functional_both_sides": True,
                "sample_weight_m_grams": 960,
                "comparison_single_layer_short_coat_m_grams": 650,
                "weight_boundary": "only the current sample weight difference is known; do not attribute all difference to the double-faced structure",
            },
            "ZX-S104": {
                "name": "暖白衬衫",
                "entity_kind": "apparel_product",
                "category": "warm white shirt",
                "display_family": "upper",
                "is_long": False,
            },
            "ZX-K126": {
                "name": "燕麦薄针织",
                "entity_kind": "apparel_product",
                "category": "oat thin knit",
                "display_family": "upper",
                "is_long": False,
            },
            "ZX-P211": {
                "name": "炭灰直筒裤",
                "entity_kind": "apparel_product",
                "category": "charcoal straight trousers",
                "display_family": "lower",
                "is_long": False,
            },
            "ZX-V113": {
                "name": "炭灰短马甲",
                "entity_kind": "apparel_product",
                "category": "charcoal short vest",
                "display_family": "upper",
                "is_long": False,
            },
            "ZX-Q117": {
                "name": "深橄榄半裙",
                "entity_kind": "apparel_product",
                "category": "deep olive skirt",
                "display_family": "lower",
                "is_long": False,
            },
        }.items():
            cursor.execute(
                """
                INSERT INTO brand_products
                    (id, tenant_id, brand_id, sku, display_name, facts)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, brand_id, sku) DO UPDATE
                SET display_name = EXCLUDED.display_name,
                    facts = EXCLUDED.facts
                """,
                (
                    uuid.uuid5(uuid.NAMESPACE_URL, sku),
                    TENANT_ID,
                    BRAND_ID,
                    sku,
                    str(facts["name"]),
                    Jsonb(facts),
                ),
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
            "INSERT INTO auth_grants "
            "(id, tenant_id, user_id, account_id, role_name) "
            "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
            (
                EXTERNAL_OPERATOR_GRANT_ID,
                TENANT_ID,
                EXTERNAL_OPERATOR_USER_ID,
                ACCOUNT_ID,
                "受托代运营权限",
            ),
        )
        cursor.execute(
            """
                INSERT INTO content_roles
                    (id, tenant_id, brand_id, name, voice_boundary, speaker_kind)
                VALUES (%s, %s, %s, %s, %s, 'institutional_account')
                ON CONFLICT (id) DO UPDATE
                SET speaker_kind = EXCLUDED.speaker_kind
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
        for account_id, name, channel in (
            (
                HEADQUARTERS_XIAOHONGSHU_ACCOUNT_ID,
                "折线之间品牌母账号·小红书",
                "小红书",
            ),
            (
                HEADQUARTERS_WECHAT_CHANNELS_ACCOUNT_ID,
                "折线之间品牌母账号·微信视频号",
                "微信视频号",
            ),
        ):
            cursor.execute(
                "INSERT INTO content_accounts (id, tenant_id, brand_id, name, channel) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
                (account_id, TENANT_ID, BRAND_ID, name, channel),
            )
        cursor.execute(
            "INSERT INTO content_accounts (id,tenant_id,brand_id,name,channel) VALUES (%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING",
            (STORE_CONTENT_ACCOUNT_ID, TENANT_ID, BRAND_ID, "折线之间·南城店账号·抖音", "抖音"),
        )
        cursor.execute(
            "INSERT INTO auth_grants (id,tenant_id,user_id,account_id,role_name) VALUES (%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING",
            (
                STORE_CONTENT_GRANT_ID,
                TENANT_ID,
                STORE_CONTENT_USER_ID,
                STORE_CONTENT_ACCOUNT_ID,
                "南城店内容运营权限",
            ),
        )
        cursor.execute(
            "INSERT INTO content_roles "
            "(id,tenant_id,brand_id,name,voice_boundary,speaker_kind) "
            "VALUES (%s,%s,%s,%s,%s,'institutional_account') "
            "ON CONFLICT (id) DO UPDATE "
            "SET speaker_kind = EXCLUDED.speaker_kind",
            (
                STORE_CONTENT_ROLE_ID,
                TENANT_ID,
                BRAND_ID,
                "南城店店长/门店经营者",
                "只从南城店经营者的合法位置表达，不冒充总部、全国政策或真实顾客。",
            ),
        )
        cursor.execute(
            "INSERT INTO account_content_roles (id,tenant_id,account_id,content_role_id) VALUES (%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING",
            (
                STORE_CONTENT_ACCOUNT_ROLE_ID,
                TENANT_ID,
                STORE_CONTENT_ACCOUNT_ID,
                STORE_CONTENT_ROLE_ID,
            ),
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
        cursor.execute(
            """
            INSERT INTO organization_material_maintainers (id, tenant_id, organization_id, user_id)
            VALUES (%s, %s, %s, %s) ON CONFLICT (tenant_id, organization_id, user_id) DO NOTHING
            """,
            (MATERIAL_MAINTAINER_ID, TENANT_ID, ORG_ID, USER_ID),
        )
        for grant_id, user_id in (
            (TENANT_ADMIN_GRANT_ID, TENANT_ADMIN_USER_ID),
            (DUAL_TENANT_ADMIN_GRANT_ID, DUAL_QUALIFIED_USER_ID),
        ):
            cursor.execute(
                "INSERT INTO tenant_management_grants (id, tenant_id, user_id) VALUES (%s, %s, %s) ON CONFLICT (tenant_id, user_id) DO NOTHING",
                (grant_id, TENANT_ID, user_id),
            )
        # Which organization controls each publishing account, and who may maintain its
        # expression profile.  Account use never implies profile maintenance.  The demo seed
        # states these outright, which is what `declared` means; a value a migration inferred
        # from a creation event never gets that status.
        for account_id, control_organization_id in (
            (ACCOUNT_ID, ORG_ID),
            (HEADQUARTERS_XIAOHONGSHU_ACCOUNT_ID, ORG_ID),
            (HEADQUARTERS_WECHAT_CHANNELS_ACCOUNT_ID, ORG_ID),
            (STORE_CONTENT_ACCOUNT_ID, STORE_ORG_ID),
        ):
            cursor.execute(
                "UPDATE content_accounts SET control_organization_id = %s, "
                "control_organization_source = 'declared' "
                "WHERE tenant_id = %s AND id = %s",
                (control_organization_id, TENANT_ID, account_id),
            )
        for carrier_id in (
            HEADQUARTERS_XIAOHONGSHU_ACCOUNT_ID,
            HEADQUARTERS_WECHAT_CHANNELS_ACCOUNT_ID,
        ):
            cursor.execute(
                "UPDATE content_accounts SET carrier_of_account_id = %s WHERE tenant_id = %s AND id = %s",
                (ACCOUNT_ID, TENANT_ID, carrier_id),
            )
        for grant_id, can_maintain in (
            (GRANT_ID, True),
            (STORE_CONTENT_GRANT_ID, False),
            (EXTERNAL_OPERATOR_GRANT_ID, True),
        ):
            cursor.execute(
                "UPDATE auth_grants SET can_maintain_expression_profile = %s WHERE tenant_id = %s AND id = %s",
                (can_maintain, TENANT_ID, grant_id),
            )
        cursor.execute(
            "INSERT INTO display_access_grants "
            "(id, tenant_id, user_id, enabled) "
            "VALUES (%s, %s, %s, true) "
            "ON CONFLICT (tenant_id, user_id) DO UPDATE "
            "SET enabled = EXCLUDED.enabled",
            (STORE_DISPLAY_ACCESS_GRANT_ID, TENANT_ID, STORE_USER_ID),
        )
        for persona_id, user_id, name, boundary in (
            (
                USER_DEFAULT_PERSONA_ID,
                USER_ID,
                "总部内容运营的默认表达",
                "只说明本人可承担的内容协作位置，不替代企业发布账号的表达身份。",
            ),
            (
                DUAL_DEFAULT_PERSONA_ID,
                DUAL_QUALIFIED_USER_ID,
                "历史管理员默认表达",
                "该身份当前只保留租户管理入口；历史私人设置不授予内容创作资格。",
            ),
            (
                EXTERNAL_DEFAULT_PERSONA_ID,
                EXTERNAL_OPERATOR_USER_ID,
                "外部代运营的默认表达",
                "仅在受托发布账号授权范围内协作，不代表租户管理身份。",
            ),
        ):
            cursor.execute(
                "INSERT INTO user_default_personas (id, tenant_id, user_id, name, boundary) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (tenant_id, user_id) DO NOTHING",
                (persona_id, TENANT_ID, user_id, name, boundary),
            )


if __name__ == "__main__":
    seed_demo()
