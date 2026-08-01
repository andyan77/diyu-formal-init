from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Literal, cast
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row

from src.shared.errors import DomainError

TenantDataKind = Literal["synthetic_business_fixture", "legacy_hidden"]
TENANT_LIFECYCLE_CONTRACT_VERSION = "tenant-lifecycle-exact-preimage-v1"

_TABLES_WITH_BRAND = frozenset(
    {
        "content_accounts",
        "brand_products",
        "material_assets",
        "display_stores",
        "brand_library_entries",
        "business_tasks",
        "display_tasks",
        "content_series",
    }
)
_TABLES_WITH_ENABLED = frozenset({"users", "content_accounts", "display_stores"})
_ALLOWED_TABLES = _TABLES_WITH_BRAND | {"organizations", "users"}


@dataclass(frozen=True)
class TenantLifecycleObject:
    table: str
    object_id: UUID
    target_kind: TenantDataKind


@dataclass(frozen=True)
class TenantLifecyclePlan:
    contract_version: str
    tenant_id: UUID
    brand_id: UUID
    actor_user_id: UUID
    objects: tuple[TenantLifecycleObject, ...]
    plan_digest: str

    @classmethod
    def from_file(cls, path: Path) -> TenantLifecyclePlan:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise DomainError("租户生命周期计划必须是一个对象。")
        if set(value) != {
            "contract_version",
            "tenant_id",
            "brand_id",
            "actor_user_id",
            "objects",
        }:
            raise DomainError("租户生命周期计划字段不完整。")
        if value["contract_version"] != TENANT_LIFECYCLE_CONTRACT_VERSION:
            raise DomainError("租户生命周期计划版本不受支持。")
        raw_objects = value["objects"]
        if not isinstance(raw_objects, list) or not raw_objects:
            raise DomainError("租户生命周期计划没有待处理对象。")
        objects: list[TenantLifecycleObject] = []
        seen: set[tuple[str, UUID]] = set()
        for raw in raw_objects:
            if not isinstance(raw, dict) or set(raw) != {
                "table",
                "object_id",
                "target_kind",
            }:
                raise DomainError("租户生命周期对象字段不完整。")
            table = str(raw["table"])
            target_kind = str(raw["target_kind"])
            if table not in _ALLOWED_TABLES:
                raise DomainError("租户生命周期计划包含未授权对象类型。")
            if target_kind not in {"synthetic_business_fixture", "legacy_hidden"}:
                raise DomainError("租户生命周期目标分类不受支持。")
            object_id = UUID(str(raw["object_id"]))
            identity = (table, object_id)
            if identity in seen:
                raise DomainError("租户生命周期计划包含重复对象。")
            seen.add(identity)
            objects.append(
                TenantLifecycleObject(
                    table=table,
                    object_id=object_id,
                    target_kind=cast(TenantDataKind, target_kind),
                )
            )
        canonical = {
            "contract_version": TENANT_LIFECYCLE_CONTRACT_VERSION,
            "tenant_id": str(value["tenant_id"]),
            "brand_id": str(value["brand_id"]),
            "actor_user_id": str(value["actor_user_id"]),
            "objects": [
                {
                    "table": item.table,
                    "object_id": str(item.object_id),
                    "target_kind": item.target_kind,
                }
                for item in sorted(objects, key=lambda item: (item.table, str(item.object_id)))
            ],
        }
        digest = sha256(
            json.dumps(
                canonical,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
        ).hexdigest()
        return cls(
            contract_version=TENANT_LIFECYCLE_CONTRACT_VERSION,
            tenant_id=UUID(str(value["tenant_id"])),
            brand_id=UUID(str(value["brand_id"])),
            actor_user_id=UUID(str(value["actor_user_id"])),
            objects=tuple(objects),
            plan_digest=digest,
        )

    def public_manifest(self) -> dict[str, object]:
        counts: dict[str, int] = {}
        for item in self.objects:
            key = f"{item.table}:{item.target_kind}"
            counts[key] = counts.get(key, 0) + 1
        return {
            "contract_version": self.contract_version,
            "tenant_id": str(self.tenant_id),
            "brand_id": str(self.brand_id),
            "plan_digest": self.plan_digest,
            "object_count": len(self.objects),
            "counts": dict(sorted(counts.items())),
        }


class TenantLifecycleClassifier:
    """Apply one reviewed UUID preimage without guessing names or deleting history."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    @contextmanager
    def _tx(self, tenant_id: UUID) -> Iterator[psycopg.Cursor[dict[str, object]]]:
        with (
            psycopg.connect(self._database_url, row_factory=dict_row) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),))
            yield cursor

    def apply(self, plan: TenantLifecyclePlan) -> dict[str, object]:
        with self._tx(plan.tenant_id) as cursor:
            self._assert_actor(cursor, plan)
            changed = 0
            affected_users: list[UUID] = []
            for item in plan.objects:
                current_kind = self._lock_object(cursor, plan, item)
                if current_kind == item.target_kind:
                    continue
                if current_kind != "formal_business_data":
                    raise DomainError("生命周期对象已经属于另一种受保护分类，拒绝覆盖。")
                self._classify(cursor, plan, item)
                changed += 1
                if item.table == "users":
                    affected_users.append(item.object_id)
            if affected_users:
                self._revoke_user_access(cursor, plan.tenant_id, tuple(affected_users))
            if changed:
                cursor.execute(
                    "INSERT INTO activity_events "
                    "(id, tenant_id, actor_id, event_type, entity_type, entity_id) "
                    "VALUES (%s, %s, %s, 'tenant_lifecycle.preimage_applied', 'brand', %s)",
                    (uuid4(), plan.tenant_id, plan.actor_user_id, plan.brand_id),
                )
        return {
            **plan.public_manifest(),
            "changed": changed,
            "already_classified": len(plan.objects) - changed,
        }

    @staticmethod
    def _assert_actor(
        cursor: psycopg.Cursor[dict[str, object]],
        plan: TenantLifecyclePlan,
    ) -> None:
        cursor.execute(
            "SELECT 1 FROM users actor "
            "JOIN tenant_management_grants manager "
            "  ON manager.tenant_id = actor.tenant_id "
            " AND manager.user_id = actor.id AND manager.enabled = true "
            "WHERE actor.tenant_id = %s AND actor.id = %s "
            "  AND actor.entry_kind = 'tenant_admin' AND actor.enabled = true "
            "  AND actor.business_data_kind = 'formal_business_data'",
            (plan.tenant_id, plan.actor_user_id),
        )
        if cursor.fetchone() is None:
            raise DomainError("当前自然人没有执行租户生命周期计划的资格。")

    @staticmethod
    def _lock_object(
        cursor: psycopg.Cursor[dict[str, object]],
        plan: TenantLifecyclePlan,
        item: TenantLifecycleObject,
    ) -> str:
        brand_clause = " AND brand_id = %s" if item.table in _TABLES_WITH_BRAND else ""
        parameters: tuple[object, ...] = (
            (plan.tenant_id, item.object_id, plan.brand_id)
            if item.table in _TABLES_WITH_BRAND
            else (plan.tenant_id, item.object_id)
        )
        cursor.execute(
            f"SELECT business_data_kind FROM {item.table} "  # noqa: S608
            f"WHERE tenant_id = %s AND id = %s{brand_clause} FOR UPDATE",
            parameters,
        )
        row = cursor.fetchone()
        if row is None:
            raise DomainError("生命周期计划中的对象不存在或不属于目标租户品牌。")
        return str(row["business_data_kind"])

    @staticmethod
    def _classify(
        cursor: psycopg.Cursor[dict[str, object]],
        plan: TenantLifecyclePlan,
        item: TenantLifecycleObject,
    ) -> None:
        assignments = ["business_data_kind = %s"]
        parameters: list[object] = [item.target_kind]
        if item.table in _TABLES_WITH_ENABLED and item.target_kind == "synthetic_business_fixture":
            assignments.append("enabled = false")
        if item.table == "content_accounts" and item.target_kind == "synthetic_business_fixture":
            assignments.append("platform_enabled = false")
        parameters.extend((plan.tenant_id, item.object_id))
        cursor.execute(
            f"UPDATE {item.table} SET {', '.join(assignments)} "  # noqa: S608
            "WHERE tenant_id = %s AND id = %s",
            tuple(parameters),
        )

    @staticmethod
    def _revoke_user_access(
        cursor: psycopg.Cursor[dict[str, object]],
        tenant_id: UUID,
        user_ids: tuple[UUID, ...],
    ) -> None:
        cursor.execute(
            "UPDATE tenant_sessions SET revoked_at = COALESCE(revoked_at, now()) "
            "WHERE tenant_id = %s AND user_id = ANY(%s)",
            (tenant_id, list(user_ids)),
        )
        cursor.execute(
            "UPDATE user_activation_tokens SET used_at = COALESCE(used_at, now()) "
            "WHERE tenant_id = %s AND user_id = ANY(%s)",
            (tenant_id, list(user_ids)),
        )
        for table in ("auth_grants", "display_access_grants", "display_store_access_grants"):
            cursor.execute(
                f"UPDATE {table} SET enabled = false "  # noqa: S608
                "WHERE tenant_id = %s AND user_id = ANY(%s) AND enabled = true",
                (tenant_id, list(user_ids)),
            )
