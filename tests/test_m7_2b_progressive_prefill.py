from __future__ import annotations

from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient

from src.brain.onboarding_prefill import (
    account_profile_prefill,
    load_brand_prefill,
    product_prefills,
)
from src.brain.workbench_service import WorkbenchService
from src.gateway.api.app import create_app
from src.gateway.api.settings import Settings
from src.infrastructure.seed_demo import TENANT_ID


def test_diyu_prefill_is_editable_candidate_data_not_runtime_fact() -> None:
    document = load_brand_prefill("笛语服饰")
    assert document is not None
    assert document["status"] == "review_candidate"
    assert load_brand_prefill("折线之间") is None

    profile = account_profile_prefill(
        "笛语服饰",
        "笛语服饰品牌官方账号",
        "品牌官方 / 品牌定义者",
    )
    assert profile is not None
    draft, source_summary = profile
    assert draft["is_draft"] is True
    assert "不是创始人、研发人员、门店店员或顾客本人" in str(draft["identity_position"])
    assert "不构成商品或账号事实" in source_summary

    products, metadata = product_prefills("笛语服饰")
    assert metadata["status"] == "review_candidate"
    assert [item["sku"] for item in products] == [
        "DIYU-CSPU-001",
        "DIYU-CSPU-006",
        "DIYU-CSPU-009",
    ]
    assert all("price" not in item and "inventory" not in item for item in products)
    assert all(item["silhouette"] == "" for item in products)
    assert products[2]["material_or_structure"] == "牛角扣、学院外套结构"


def test_platform_carrier_prefill_freezes_explicit_source_and_operator() -> None:
    accounts: list[dict[str, object]] = [
        {
            "id": "source-account",
            "name": "品牌官方账号",
            "channel": "抖音",
            "carrier_of_account_id": None,
            "operators": [{"id": "operator-1", "display_name": "现有使用者"}],
        },
        {
            "id": "existing-carrier",
            "name": "品牌官方账号",
            "channel": "小红书",
            "carrier_of_account_id": "source-account",
            "operators": [{"id": "operator-1", "display_name": "现有使用者"}],
        },
    ]
    drafts = WorkbenchService._platform_carrier_prefills(accounts)
    assert drafts == [
        {
            "source_account_id": "source-account",
            "source_account_name": "品牌官方账号",
            "name": "品牌官方账号",
            "channel": "微信视频号",
            "operator_id": "operator-1",
            "operator_name": "现有使用者",
        }
    ]


def test_candidate_product_cannot_be_saved_without_explicit_brand_confirmation(
    app_database_url: str,
) -> None:
    sku = f"UNCONFIRMED-{uuid4().hex[:8]}"
    with TestClient(create_app(Settings.model_validate({}))) as manager:
        manager.get("/ui/select/admin")
        refused = manager.put(
            "/api/v1/tenant-management/brand-products",
            json={
                "sku": sku,
                "display_name": "仍是候选的商品",
                "category": "短袖上衣",
                "colors": ["黄色"],
                "source_note": "候选资料预填",
                "applicability": "当前品牌",
            },
        )
        assert refused.status_code == 422

    with psycopg.connect(app_database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
        cursor.execute(
            "SELECT count(*) FROM brand_products WHERE tenant_id = %s AND sku = %s",
            (TENANT_ID, sku),
        )
        assert cursor.fetchone() == (0,)
