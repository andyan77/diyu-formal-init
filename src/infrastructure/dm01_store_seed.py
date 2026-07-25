from __future__ import annotations

from dataclasses import dataclass
from typing import cast
from uuid import NAMESPACE_URL, UUID, uuid5

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from src.shared.errors import DomainError


@dataclass(frozen=True)
class DM01StoreSeed:
    store_id: UUID
    store_name: str
    structure_version: str
    task_input_version: str
    product_count: int


class DM01StoreSeedWriter:
    """Idempotently configure one wall structure and the default seed for its next task.

    This is configuration only. It never selects a natural person, never builds a DisplayScope and
    never creates a task, run or version: a real plan is always started by an authenticated display
    user through the ordinary API. Nothing here records a confirmation, an approval or a proxy
    submitter, and no long-term brand product fact or brand display policy is created.
    """

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def seed(self, record: dict[str, object]) -> DM01StoreSeed:
        tenant_name = _text(record, "tenant_name")
        brand_name = _text(record, "brand_name")
        control_name = _text(record, "control_organization_name")
        execution_name = _text(record, "execution_organization_name")
        store_name = _text(record, "store_name")
        record_id = _text(record, "record_id")
        structure_version = _text(record, "structure_version")
        rail_profile = _object(record, "rail_profile")
        task_input = _object(record, "task_input")
        products = _objects(task_input, "products")

        with psycopg.connect(self._database_url, row_factory=dict_row) as connection:  # noqa: SIM117
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id FROM tenants WHERE name=%s",
                    (tenant_name,),
                )
                tenant = cursor.fetchone()
                if tenant is None:
                    raise DomainError("找不到该真实租户")
                tenant_id = UUID(str(tenant["id"]))
                cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),))
                cursor.execute(
                    "SELECT id FROM brands WHERE tenant_id=%s AND name=%s",
                    (tenant_id, brand_name),
                )
                brand = cursor.fetchone()
                if brand is None:
                    raise DomainError("找不到该真实品牌")
                brand_id = UUID(str(brand["id"]))
                cursor.execute(
                    "SELECT id FROM organizations WHERE tenant_id=%s AND name=%s",
                    (tenant_id, control_name),
                )
                control_organization = cursor.fetchone()
                if control_organization is None:
                    raise DomainError("找不到该租户的管理组织")
                control_organization_id = UUID(str(control_organization["id"]))
                cursor.execute(
                    """
                    INSERT INTO organizations (id,tenant_id,name)
                    VALUES (%s,%s,%s)
                    ON CONFLICT (tenant_id,name) DO UPDATE SET name=EXCLUDED.name
                    RETURNING id
                    """,
                    (
                        uuid5(NAMESPACE_URL, f"diyu:{tenant_id}:organization:{execution_name}"),
                        tenant_id,
                        execution_name,
                    ),
                )
                organization = cursor.fetchone()
                if organization is None:
                    raise DomainError("无法建立门店执行组织")
                execution_organization_id = UUID(str(organization["id"]))

                task_input_version = _text(task_input, "version")
                stored_task_input = {
                    "version": task_input_version,
                    "source": "user_task_snapshot",
                    "record_id": record_id,
                    "expression": _object(task_input, "expression"),
                    "products": products,
                    "default_inventory_text": _inventory_text(products),
                }
                store_id = uuid5(NAMESPACE_URL, f"diyu:{tenant_id}:display-store:{record_id}")
                cursor.execute(
                    """
                    INSERT INTO display_stores
                        (id,tenant_id,brand_id,control_organization_id,execution_organization_id,
                         name,profile_version,rail_profile,current_task_input)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (tenant_id,brand_id,execution_organization_id)
                    DO UPDATE SET control_organization_id=EXCLUDED.control_organization_id,
                                  name=EXCLUDED.name,
                                  profile_version=EXCLUDED.profile_version,
                                  rail_profile=EXCLUDED.rail_profile,
                                  current_task_input=EXCLUDED.current_task_input
                    RETURNING id
                    """,
                    (
                        store_id,
                        tenant_id,
                        brand_id,
                        control_organization_id,
                        execution_organization_id,
                        store_name,
                        structure_version,
                        Jsonb(rail_profile),
                        Jsonb(stored_task_input),
                    ),
                )
                stored = cursor.fetchone()
                if stored is None:
                    raise DomainError("无法建立门店挂杆结构")
                seeded_store_id = UUID(str(stored["id"]))

        return DM01StoreSeed(
            seeded_store_id,
            store_name,
            structure_version,
            task_input_version,
            len(products),
        )


def _object(record: dict[str, object], key: str) -> dict[str, object]:
    value = record.get(key)
    if not isinstance(value, dict):
        raise DomainError(f"任务输入缺少 {key}")
    return cast(dict[str, object], value)


def _objects(record: dict[str, object], key: str) -> list[dict[str, object]]:
    value = record.get(key)
    if not isinstance(value, list) or not value or any(not isinstance(item, dict) for item in value):
        raise DomainError(f"任务输入缺少 {key}")
    return cast(list[dict[str, object]], value)


def _text(record: dict[str, object], key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise DomainError(f"任务输入缺少 {key}")
    return value.strip()


def _quantity(item: dict[str, object]) -> int:
    value = item.get("quantity")
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise DomainError("任务输入商品数量无效")
    return value


def _inventory_text(products: list[dict[str, object]]) -> str:
    """A prefilled default for the next task; the display user still submits it themselves."""
    return "本次任务可用：" + "、".join(f"{_text(item, 'sku')} {_quantity(item)} 件" for item in products) + "。"
