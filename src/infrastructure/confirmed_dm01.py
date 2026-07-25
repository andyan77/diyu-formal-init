from __future__ import annotations

from dataclasses import dataclass
from typing import cast
from uuid import NAMESPACE_URL, UUID, uuid5

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from src.shared.errors import DomainError
from src.shared.types import DisplayScope


@dataclass(frozen=True)
class ConfirmedDM01Activation:
    scope: DisplayScope
    inventory_text: str
    existing_version: dict[str, object] | None


class ConfirmedDM01Provisioner:
    """Persist one user-confirmed DM01 input without creating long-term brand product facts."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def activate(self, record: dict[str, object]) -> ConfirmedDM01Activation:
        tenant_name = _text(record, "tenant_name")
        brand_name = _text(record, "brand_name")
        control_name = _text(record, "control_organization_name")
        execution_name = _text(record, "execution_organization_name")
        store_name = _text(record, "store_name")
        record_id = _text(record, "record_id")
        record_version = _text(record, "record_version")
        inventory = _objects(record, "inventory")
        policy = _object(record, "policy")
        rail_profile = _object(record, "rail_profile")

        with psycopg.connect(self._database_url, row_factory=dict_row) as connection:  # noqa: SIM117
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id FROM tenants WHERE name=%s",
                    (tenant_name,),
                )
                tenant = cursor.fetchone()
                if tenant is None:
                    raise DomainError("找不到已确认的真实租户")
                tenant_id = UUID(str(tenant["id"]))
                cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),))
                cursor.execute(
                    "SELECT id FROM brands WHERE tenant_id=%s AND name=%s",
                    (tenant_id, brand_name),
                )
                brand = cursor.fetchone()
                if brand is None:
                    raise DomainError("找不到已确认的真实品牌")
                brand_id = UUID(str(brand["id"]))
                cursor.execute(
                    """
                    SELECT u.id, u.display_name, u.organization_id
                    FROM users u
                    JOIN tenant_management_grants g
                      ON g.tenant_id=u.tenant_id AND g.user_id=u.id AND g.enabled=true
                    JOIN organizations o
                      ON o.tenant_id=u.tenant_id AND o.id=u.organization_id
                    WHERE u.tenant_id=%s AND u.enabled=true AND o.name=%s
                    ORDER BY u.display_name
                    LIMIT 1
                    """,
                    (tenant_id, control_name),
                )
                manager = cursor.fetchone()
                if manager is None:
                    raise DomainError("找不到可追溯的当前租户管理员代录人")
                manager_id = UUID(str(manager["id"]))
                control_organization_id = UUID(str(manager["organization_id"]))
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
                    raise DomainError("无法建立真实门店执行组织")
                execution_organization_id = UUID(str(organization["id"]))

                stored_profile = {
                    **rail_profile,
                    "confirmation": {
                        "confirmed_by": _text(record, "field_executor"),
                        "confirmed_at": _text(record, "confirmed_at"),
                        "source": _text(record, "confirmation_source"),
                        "system_submitted_by": str(manager["display_name"]),
                    },
                    "inventory_snapshot": {
                        "record_id": record_id,
                        "record_version": record_version,
                        "enforce_exact": True,
                        "items": inventory,
                    },
                }
                policy_id = uuid5(NAMESPACE_URL, f"diyu:{tenant_id}:dm01-policy:{record_version}")
                cursor.execute(
                    """
                    INSERT INTO display_policies (id,tenant_id,brand_id,version,body)
                    VALUES (%s,%s,%s,%s,%s)
                    ON CONFLICT (tenant_id,brand_id,version) DO UPDATE SET body=EXCLUDED.body
                    """,
                    (policy_id, tenant_id, brand_id, record_version, Jsonb(policy)),
                )
                store_id = uuid5(NAMESPACE_URL, f"diyu:{tenant_id}:display-store:{record_id}")
                cursor.execute(
                    """
                    INSERT INTO display_stores
                        (id,tenant_id,brand_id,control_organization_id,execution_organization_id,
                         name,profile_version,rail_profile)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (tenant_id,brand_id,execution_organization_id)
                    DO UPDATE SET control_organization_id=EXCLUDED.control_organization_id,
                                  name=EXCLUDED.name,
                                  profile_version=EXCLUDED.profile_version,
                                  rail_profile=EXCLUDED.rail_profile
                    RETURNING id
                    """,
                    (
                        store_id,
                        tenant_id,
                        brand_id,
                        control_organization_id,
                        execution_organization_id,
                        store_name,
                        record_version,
                        Jsonb(stored_profile),
                    ),
                )
                stored = cursor.fetchone()
                if stored is None:
                    raise DomainError("无法建立真实门店挂杆档案")
                actual_store_id = UUID(str(stored["id"]))
                existing = self._existing_version(cursor, tenant_id, actual_store_id, record_version)

        inventory_text = (
            "本次现场确认可用：" + "、".join(f"{_text(item, 'sku')} {_quantity(item)} 件" for item in inventory) + "。"
        )
        return ConfirmedDM01Activation(
            DisplayScope(
                tenant_id,
                manager_id,
                brand_id,
                execution_organization_id,
                control_organization_id,
            ),
            inventory_text,
            existing,
        )

    @staticmethod
    def _existing_version(
        cursor: psycopg.Cursor[dict[str, object]],
        tenant_id: UUID,
        store_id: UUID,
        profile_version: str,
    ) -> dict[str, object] | None:
        cursor.execute(
            """
            SELECT v.task_id, v.id version_id, v.version_number, v.body, r.model
            FROM display_artifact_versions v
            JOIN display_tasks t ON t.tenant_id=v.tenant_id AND t.id=v.task_id
            JOIN display_generation_runs r ON r.tenant_id=v.tenant_id AND r.id=v.run_id
            WHERE v.tenant_id=%s AND t.store_id=%s
              AND r.input_receipt->>'store_profile_version'=%s
            ORDER BY v.created_at
            LIMIT 1
            """,
            (tenant_id, store_id, profile_version),
        )
        row = cursor.fetchone()
        if row is not None:
            return {
                "kind": "display",
                "task_id": str(row["task_id"]),
                "version_id": str(row["version_id"]),
                "version": int(str(row["version_number"])),
                "body": str(row["body"]),
                "model": str(row["model"]),
            }
        cursor.execute(
            """
            SELECT count(*)
            FROM display_tasks t
            JOIN display_generation_runs r ON r.tenant_id=t.tenant_id AND r.task_id=t.id
            WHERE t.tenant_id=%s AND t.store_id=%s
              AND r.input_receipt->>'store_profile_version'=%s
            """,
            (tenant_id, store_id, profile_version),
        )
        dangling = cursor.fetchone()
        if dangling is not None and int(str(dangling["count"])) > 0:
            raise DomainError("该确认快照已有未完成运行；拒绝重复生成真实 V1")
        return None


def _object(record: dict[str, object], key: str) -> dict[str, object]:
    value = record.get(key)
    if not isinstance(value, dict):
        raise DomainError(f"确认档案缺少 {key}")
    return cast(dict[str, object], value)


def _objects(record: dict[str, object], key: str) -> list[dict[str, object]]:
    value = record.get(key)
    if not isinstance(value, list) or not value or any(not isinstance(item, dict) for item in value):
        raise DomainError(f"确认档案缺少 {key}")
    return cast(list[dict[str, object]], value)


def _text(record: dict[str, object], key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise DomainError(f"确认档案缺少 {key}")
    return value.strip()


def _quantity(item: dict[str, object]) -> int:
    value = item.get("confirmed_quantity")
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise DomainError("确认档案商品数量无效")
    return value
