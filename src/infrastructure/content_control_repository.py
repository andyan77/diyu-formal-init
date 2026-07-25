from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from src.ports.content_control_repository import ContentControlRepository
from src.shared.errors import DomainError
from src.shared.types import TenantManagementScope, TrustedScope

_SEGMENT_COLUMNS = (
    "identity_position",
    "authority_boundary",
    "audience_relationship",
    "content_territories",
    "default_production_conditions",
)


class PostgresContentControlRepository(ContentControlRepository):
    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    @contextmanager
    def _tenant_tx(self, tenant_id: UUID) -> Iterator[psycopg.Cursor[dict[str, object]]]:
        with (
            psycopg.connect(self._database_url, row_factory=dict_row) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),))
            yield cursor

    @contextmanager
    def _owner_tx(self, scope: TrustedScope) -> Iterator[psycopg.Cursor[dict[str, object]]]:
        """Private preferences need the acting person too; the tenant alone is not a scope."""
        with (
            psycopg.connect(self._database_url, row_factory=dict_row) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(scope.tenant_id),))
            cursor.execute("SELECT set_config('app.user_id', %s, true)", (str(scope.user_id),))
            yield cursor

    @staticmethod
    def _one(cursor: psycopg.Cursor[dict[str, object]], message: str) -> dict[str, object]:
        row = cursor.fetchone()
        if row is None:
            raise DomainError(message)
        return row

    @staticmethod
    def _integer(value: object) -> int:
        if not isinstance(value, int):
            raise DomainError("内容控制面版本数据无效")
        return value

    @staticmethod
    def _time(value: object) -> str:
        if not isinstance(value, datetime):
            raise DomainError("内容控制面时间数据无效")
        return value.isoformat()

    @staticmethod
    def _profile_value(row: dict[str, object]) -> dict[str, object]:
        return {
            "profile_id": str(row["id"]),
            "version": row["version"],
            "content_role": str(row["content_role"]),
            "identity_position": str(row["identity_position"]),
            "authority_boundary": str(row["authority_boundary"]),
            "audience_relationship": str(row["audience_relationship"]),
            "content_territories": str(row["content_territories"]),
            "default_production_conditions": str(row["default_production_conditions"]),
        }

    def expression_source(self, scope: TrustedScope) -> dict[str, str]:
        with self._tenant_tx(scope.tenant_id) as cursor:
            cursor.execute(
                """
                SELECT brand.name AS brand_name, brand.positioning, brand.tone,
                       account.name AS account_name, account.channel,
                       organization.name AS organization_name,
                       role.name AS content_role_name, role.voice_boundary,
                       audience.description AS audience_description,
                       COALESCE(baseline.draft, '') AS brand_draft,
                       COALESCE(baseline.status, 'draft') AS brand_draft_status,
                       COALESCE((
                           SELECT string_agg(product.sku, ',' ORDER BY product.sku)
                           FROM brand_products product
                           WHERE product.tenant_id = account.tenant_id
                             AND product.brand_id = account.brand_id
                       ), '') AS confirmed_product_skus
                FROM content_accounts account
                JOIN brands brand ON brand.id = account.brand_id AND brand.tenant_id = account.tenant_id
                JOIN account_content_roles account_role
                  ON account_role.account_id = account.id AND account_role.tenant_id = account.tenant_id
                JOIN content_roles role
                  ON role.id = account_role.content_role_id AND role.tenant_id = account_role.tenant_id
                LEFT JOIN organizations organization
                  ON organization.id = account.control_organization_id
                 AND organization.tenant_id = account.tenant_id
                LEFT JOIN brand_audiences audience
                  ON audience.brand_id = brand.id AND audience.tenant_id = brand.tenant_id
                LEFT JOIN brand_expression_baselines baseline
                  ON baseline.brand_id = brand.id AND baseline.tenant_id = brand.tenant_id
                WHERE account.tenant_id = %s AND account.id = %s AND account.brand_id = %s
                  AND account.enabled = true
                ORDER BY role.name LIMIT 1
                """,
                (scope.tenant_id, scope.account_id, scope.brand_id),
            )
            row = self._one(cursor, "找不到当前发布账号的表达来源")
        return {key: str(value if value is not None else "") for key, value in row.items()}

    def current_account_expression(
        self, tenant_id: UUID, account_id: UUID
    ) -> dict[str, object] | None:
        with self._tenant_tx(tenant_id) as cursor:
            cursor.execute(
                # Tenant, account and profile must all line up; a pointer that names another
                # account's profile resolves to nothing here and cannot be stored at all.
                """
                SELECT profile.id, profile.version, role.name AS content_role,
                       profile.identity_position, profile.authority_boundary,
                       profile.audience_relationship, profile.content_territories,
                       profile.default_production_conditions
                FROM content_accounts account
                JOIN account_expression_profile_versions profile
                  ON profile.id = account.current_expression_profile_id
                 AND profile.tenant_id = account.tenant_id
                 AND profile.account_id = account.id
                JOIN content_roles role
                  ON role.id = profile.content_role_id AND role.tenant_id = profile.tenant_id
                WHERE account.tenant_id = %s AND account.id = %s
                """,
                (tenant_id, account_id),
            )
            row = cursor.fetchone()
        return self._profile_value(row) if row is not None else None

    def account_expression_by_id(
        self, tenant_id: UUID, account_id: UUID, profile_id: UUID
    ) -> dict[str, object] | None:
        with self._tenant_tx(tenant_id) as cursor:
            cursor.execute(
                """
                SELECT profile.id, profile.version, role.name AS content_role,
                       profile.identity_position, profile.authority_boundary,
                       profile.audience_relationship, profile.content_territories,
                       profile.default_production_conditions
                FROM account_expression_profile_versions profile
                JOIN content_roles role
                  ON role.id = profile.content_role_id AND role.tenant_id = profile.tenant_id
                WHERE profile.tenant_id = %s AND profile.account_id = %s AND profile.id = %s
                """,
                (tenant_id, account_id, profile_id),
            )
            row = cursor.fetchone()
        return self._profile_value(row) if row is not None else None

    # One predicate, used both to decide what the interface may show and, inside the writing
    # transaction, to decide whether the version may be appended at all.  A control organization
    # that a migration merely inferred is not evidence and never satisfies it.
    _OPERATOR_MAINTENANCE = """
        SELECT EXISTS (
            SELECT 1
            FROM auth_grants grant_record
            JOIN users person
              ON person.id = grant_record.user_id AND person.tenant_id = grant_record.tenant_id
            JOIN content_accounts account
              ON account.id = grant_record.account_id
             AND account.tenant_id = grant_record.tenant_id
            WHERE grant_record.tenant_id = %s AND grant_record.user_id = %s
              AND grant_record.account_id = %s AND grant_record.enabled = true
              AND grant_record.can_maintain_expression_profile = true
              AND person.enabled = true AND account.enabled = true
              AND account.brand_id = %s
              AND account.control_organization_id IS NOT NULL
              AND account.control_organization_source = 'declared'
              AND account.control_organization_id = person.organization_id
        ) AS allowed
    """
    _MANAGER_MAINTENANCE = """
        SELECT EXISTS (
            SELECT 1
            FROM content_accounts account
            JOIN users manager
              ON manager.tenant_id = account.tenant_id AND manager.id = %s
             AND manager.enabled = true
            JOIN tenant_management_grants management_grant
              ON management_grant.tenant_id = manager.tenant_id
             AND management_grant.user_id = manager.id
             AND management_grant.enabled = true
            WHERE account.tenant_id = %s AND account.id = %s AND account.brand_id = %s
              AND account.enabled = true
              AND account.control_organization_id IS NOT NULL
              AND account.control_organization_source = 'declared'
              AND account.control_organization_id = manager.organization_id
        ) AS allowed
    """

    def can_maintain_account_expression(self, scope: TrustedScope) -> bool:
        with self._tenant_tx(scope.tenant_id) as cursor:
            cursor.execute(
                self._OPERATOR_MAINTENANCE,
                (scope.tenant_id, scope.user_id, scope.account_id, scope.brand_id),
            )
            return bool(self._one(cursor, "无法读取账号画像维护资格")["allowed"])

    def can_manage_account_expression(
        self, scope: TenantManagementScope, account_id: UUID
    ) -> bool:
        with self._tenant_tx(scope.tenant_id) as cursor:
            cursor.execute(
                self._MANAGER_MAINTENANCE,
                (scope.user_id, scope.tenant_id, account_id, scope.brand_id),
            )
            return bool(self._one(cursor, "无法读取账号画像管理资格")["allowed"])

    def save_account_expression_as_operator(
        self, scope: TrustedScope, segments: tuple[str, str, str, str, str]
    ) -> dict[str, object]:
        return self._append_version(
            scope.tenant_id,
            scope.account_id,
            scope.user_id,
            segments,
            self._OPERATOR_MAINTENANCE,
            (scope.tenant_id, scope.user_id, scope.account_id, scope.brand_id),
            "你现在只能查看这个账号的表达画像。维护资格由已声明的账号控制组织决定。",
        )

    def save_account_expression_as_manager(
        self,
        scope: TenantManagementScope,
        account_id: UUID,
        segments: tuple[str, str, str, str, str],
    ) -> dict[str, object]:
        return self._append_version(
            scope.tenant_id,
            account_id,
            scope.user_id,
            segments,
            self._MANAGER_MAINTENANCE,
            (scope.user_id, scope.tenant_id, account_id, scope.brand_id),
            "这个发布账号不属于你所在组织控制，或者控制组织还没有被明确声明。",
        )

    def declare_control_organization(
        self, scope: TenantManagementScope, account_id: UUID, organization_id: UUID
    ) -> dict[str, object]:
        with self._tenant_tx(scope.tenant_id) as cursor:
            cursor.execute(
                """
                SELECT 1 FROM tenant_management_grants management_grant
                JOIN users manager ON manager.id = management_grant.user_id
                 AND manager.tenant_id = management_grant.tenant_id AND manager.enabled = true
                WHERE management_grant.tenant_id = %s AND management_grant.user_id = %s
                  AND management_grant.enabled = true
                """,
                (scope.tenant_id, scope.user_id),
            )
            self._one(cursor, "只有当前租户的有权主体可以声明账号控制组织")
            cursor.execute(
                "SELECT id FROM organizations WHERE tenant_id = %s AND id = %s",
                (scope.tenant_id, organization_id),
            )
            self._one(cursor, "只能声明当前租户已有的组织")
            cursor.execute(
                "SELECT control_organization_source FROM content_accounts "
                "WHERE tenant_id = %s AND id = %s AND brand_id = %s AND enabled = true FOR UPDATE",
                (scope.tenant_id, account_id, scope.brand_id),
            )
            account = self._one(cursor, "找不到当前范围内的发布账号")
            if str(account["control_organization_source"]) == "declared":
                raise DomainError("这个账号的控制组织已经声明过，不在这里重复更改。")
            cursor.execute(
                "UPDATE content_accounts SET control_organization_id = %s, "
                "control_organization_source = 'declared' "
                "WHERE tenant_id = %s AND id = %s",
                (organization_id, scope.tenant_id, account_id),
            )
            cursor.execute(
                "INSERT INTO activity_events "
                "(id, tenant_id, actor_id, event_type, entity_type, entity_id, metadata) "
                "VALUES (%s, %s, %s, 'publishing_account.control_organization_declared', "
                "'content_account', %s, %s)",
                (
                    uuid4(),
                    scope.tenant_id,
                    scope.user_id,
                    account_id,
                    Jsonb({"organization_id": str(organization_id)}),
                ),
            )
            cursor.execute(
                "SELECT name FROM organizations WHERE tenant_id = %s AND id = %s",
                (scope.tenant_id, organization_id),
            )
            organization = self._one(cursor, "找不到已声明的控制组织")
        return {
            "account_id": str(account_id),
            "control_organization": str(organization["name"]),
            "control_organization_source": "declared",
        }

    def _append_version(
        self,
        tenant_id: UUID,
        account_id: UUID,
        created_by: UUID,
        segments: tuple[str, str, str, str, str],
        permission_sql: str,
        permission_params: tuple[object, ...],
        refusal: str,
    ) -> dict[str, object]:
        profile_id = uuid4()
        with self._tenant_tx(tenant_id) as cursor:
            cursor.execute(
                "SELECT id FROM content_accounts WHERE tenant_id = %s AND id = %s AND enabled = true FOR UPDATE",
                (tenant_id, account_id),
            )
            self._one(cursor, "找不到可维护的发布账号")
            cursor.execute(permission_sql, permission_params)
            if not bool(self._one(cursor, "无法读取账号画像维护资格")["allowed"]):
                raise DomainError(refusal)
            cursor.execute(
                """
                SELECT role.id, role.name FROM account_content_roles account_role
                JOIN content_roles role
                  ON role.id = account_role.content_role_id AND role.tenant_id = account_role.tenant_id
                WHERE account_role.tenant_id = %s AND account_role.account_id = %s
                ORDER BY role.name LIMIT 1
                """,
                (tenant_id, account_id),
            )
            role = self._one(cursor, "该发布账号还没有当前表达身份")
            cursor.execute(
                "SELECT COALESCE(max(version), 0) + 1 AS next_version "
                "FROM account_expression_profile_versions WHERE tenant_id = %s AND account_id = %s",
                (tenant_id, account_id),
            )
            next_version = self._integer(self._one(cursor, "无法确定画像版本")["next_version"])
            cursor.execute(
                "INSERT INTO account_expression_profile_versions "
                "(id, tenant_id, account_id, content_role_id, version, "
                + ", ".join(_SEGMENT_COLUMNS)
                + ", created_by) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "RETURNING id, version, created_at",
                (
                    profile_id,
                    tenant_id,
                    account_id,
                    role["id"],
                    next_version,
                    *segments,
                    created_by,
                ),
            )
            saved = self._one(cursor, "账号画像没有保存成功")
            cursor.execute(
                "UPDATE content_accounts SET current_expression_profile_id = %s "
                "WHERE tenant_id = %s AND id = %s",
                (profile_id, tenant_id, account_id),
            )
            cursor.execute(
                "INSERT INTO activity_events (id, tenant_id, actor_id, event_type, entity_type, entity_id, metadata) "
                "VALUES (%s, %s, %s, 'account_expression_profile.version_saved', "
                "'account_expression_profile', %s, %s)",
                (
                    uuid4(),
                    tenant_id,
                    created_by,
                    profile_id,
                    Jsonb({"account_id": str(account_id), "version": next_version}),
                ),
            )
        return {
            "profile_id": str(saved["id"]),
            "version": self._integer(saved["version"]),
            "content_role": str(role["name"]),
            "identity_position": segments[0],
            "authority_boundary": segments[1],
            "audience_relationship": segments[2],
            "content_territories": segments[3],
            "default_production_conditions": segments[4],
            "created_at": self._time(saved["created_at"]),
        }

    def management_accounts_with_expression(
        self, scope: TenantManagementScope
    ) -> list[dict[str, object]]:
        with self._tenant_tx(scope.tenant_id) as cursor:
            cursor.execute(
                """
                SELECT account.id, account.name, account.channel,
                       role.name AS content_role,
                       control_organization.name AS control_organization,
                       account.control_organization_source,
                       profile.version AS profile_version,
                       (account.control_organization_id IS NOT NULL
                        AND account.control_organization_source = 'declared'
                        AND account.control_organization_id = manager.organization_id) AS can_maintain,
                       (account.control_organization_source <> 'declared') AS can_declare
                FROM content_accounts account
                JOIN users manager ON manager.tenant_id = account.tenant_id AND manager.id = %s
                    AND manager.enabled = true
                JOIN account_content_roles account_role
                  ON account_role.account_id = account.id AND account_role.tenant_id = account.tenant_id
                JOIN content_roles role
                  ON role.id = account_role.content_role_id AND role.tenant_id = account_role.tenant_id
                LEFT JOIN organizations control_organization
                  ON control_organization.id = account.control_organization_id
                 AND control_organization.tenant_id = account.tenant_id
                LEFT JOIN account_expression_profile_versions profile
                  ON profile.id = account.current_expression_profile_id
                 AND profile.tenant_id = account.tenant_id
                 AND profile.account_id = account.id
                WHERE account.tenant_id = %s AND account.brand_id = %s AND account.enabled = true
                ORDER BY account.name
                """,
                (scope.user_id, scope.tenant_id, scope.brand_id),
            )
            rows = cursor.fetchall()
        return [
            {
                "id": str(row["id"]),
                "name": str(row["name"]),
                "channel": str(row["channel"]),
                "content_role": str(row["content_role"]),
                "control_organization": (
                    str(row["control_organization"]) if row["control_organization"] else ""
                ),
                "control_organization_source": str(row["control_organization_source"]),
                "profile_version": row["profile_version"],
                "can_maintain": bool(row["can_maintain"]),
                "can_declare": bool(row["can_declare"]),
            }
            for row in rows
        ]

    def management_organizations(self, scope: TenantManagementScope) -> list[dict[str, object]]:
        with self._tenant_tx(scope.tenant_id) as cursor:
            cursor.execute(
                "SELECT id, name FROM organizations WHERE tenant_id = %s ORDER BY name",
                (scope.tenant_id,),
            )
            rows = cursor.fetchall()
        return [{"id": str(row["id"]), "name": str(row["name"])} for row in rows]

    def creation_preference(self, scope: TrustedScope) -> dict[str, object] | None:
        with self._owner_tx(scope) as cursor:
            cursor.execute(
                "SELECT version, enabled, direction_defaults, collaboration_note, "
                "body_related_opt_in, updated_at FROM user_creation_preferences "
                "WHERE tenant_id = %s AND user_id = %s",
                (scope.tenant_id, scope.user_id),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        defaults = row["direction_defaults"]
        return {
            "version": self._integer(row["version"]),
            "enabled": bool(row["enabled"]),
            "direction_defaults": defaults if isinstance(defaults, dict) else {},
            "collaboration_note": str(row["collaboration_note"]),
            "body_related_opt_in": bool(row["body_related_opt_in"]),
            "updated_at": self._time(row["updated_at"]),
        }

    def save_creation_preference(
        self,
        scope: TrustedScope,
        enabled: bool,
        direction_defaults: dict[str, str],
        collaboration_note: str,
        body_related_opt_in: bool,
    ) -> dict[str, object]:
        with self._owner_tx(scope) as cursor:
            cursor.execute(
                """
                INSERT INTO user_creation_preferences
                    (id, tenant_id, user_id, enabled, direction_defaults, collaboration_note,
                     body_related_opt_in)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, user_id) DO UPDATE
                SET enabled = EXCLUDED.enabled,
                    direction_defaults = EXCLUDED.direction_defaults,
                    collaboration_note = EXCLUDED.collaboration_note,
                    body_related_opt_in = EXCLUDED.body_related_opt_in,
                    version = user_creation_preferences.version + 1,
                    updated_at = now()
                RETURNING version, enabled, direction_defaults, collaboration_note,
                          body_related_opt_in, updated_at
                """,
                (
                    uuid4(),
                    scope.tenant_id,
                    scope.user_id,
                    enabled,
                    Jsonb(direction_defaults),
                    collaboration_note,
                    body_related_opt_in,
                ),
            )
            row = self._one(cursor, "私人创作偏好没有保存成功")
        defaults = row["direction_defaults"]
        return {
            "version": self._integer(row["version"]),
            "enabled": bool(row["enabled"]),
            "direction_defaults": defaults if isinstance(defaults, dict) else {},
            "collaboration_note": str(row["collaboration_note"]),
            "body_related_opt_in": bool(row["body_related_opt_in"]),
            "updated_at": self._time(row["updated_at"]),
        }

    def delete_creation_preference(self, scope: TrustedScope) -> bool:
        with self._owner_tx(scope) as cursor:
            cursor.execute(
                "DELETE FROM user_creation_preferences WHERE tenant_id = %s AND user_id = %s",
                (scope.tenant_id, scope.user_id),
            )
            return cursor.rowcount == 1

    def selected_materials(
        self, scope: TrustedScope, asset_ids: tuple[UUID, ...]
    ) -> tuple[dict[str, object], ...]:
        if not asset_ids:
            return ()
        with self._tenant_tx(scope.tenant_id) as cursor:
            cursor.execute(
                """
                SELECT asset.id, asset.title, asset.media_type, asset.reference_version,
                       asset.reference_note, asset.object_key, asset.scope
                FROM material_assets asset
                WHERE asset.tenant_id = %s AND asset.brand_id = %s AND asset.status = 'active'
                  AND asset.id = ANY(%s)
                  AND (
                    (asset.scope = 'personal' AND asset.owner_user_id = %s)
                    OR (asset.scope = 'organization' AND asset.owner_organization_id = (
                        SELECT organization_id FROM users WHERE tenant_id = %s AND id = %s
                    ))
                  )
                ORDER BY asset.created_at
                """,
                (
                    scope.tenant_id,
                    scope.brand_id,
                    list(asset_ids),
                    scope.user_id,
                    scope.tenant_id,
                    scope.user_id,
                ),
            )
            rows = cursor.fetchall()
        if len(rows) != len(set(asset_ids)):
            raise DomainError("这次参考里有当前身份不能使用的素材。")
        return tuple(
            {
                "asset_id": str(row["id"]),
                "title": str(row["title"]),
                "media_type": str(row["media_type"]),
                "reference_version": self._integer(row["reference_version"]),
                "reference_note": str(row["reference_note"]),
                "object_key": str(row["object_key"]),
                "scope": str(row["scope"]),
            }
            for row in rows
        )

    def available_material_notes(self, scope: TrustedScope) -> tuple[dict[str, object], ...]:
        with self._tenant_tx(scope.tenant_id) as cursor:
            cursor.execute(
                """
                SELECT asset.id, asset.title, asset.media_type, asset.reference_note
                FROM material_assets asset
                WHERE asset.tenant_id = %s AND asset.brand_id = %s AND asset.status = 'active'
                  AND (
                    (asset.scope = 'personal' AND asset.owner_user_id = %s)
                    OR (asset.scope = 'organization' AND asset.owner_organization_id = (
                        SELECT organization_id FROM users WHERE tenant_id = %s AND id = %s
                    ))
                  )
                ORDER BY asset.created_at DESC LIMIT 20
                """,
                (scope.tenant_id, scope.brand_id, scope.user_id, scope.tenant_id, scope.user_id),
            )
            rows = cursor.fetchall()
        return tuple(
            {
                "asset_id": str(row["id"]),
                "title": str(row["title"]),
                "media_type": str(row["media_type"]),
                "reference_note": str(row["reference_note"]),
            }
            for row in rows
        )

    def plan(self, scope: TrustedScope) -> dict[str, object]:
        with self._tenant_tx(scope.tenant_id) as cursor:
            cursor.execute(
                "SELECT document, updated_at FROM content_plans "
                "WHERE tenant_id = %s AND account_id = %s AND created_by = %s",
                (scope.tenant_id, scope.account_id, scope.user_id),
            )
            row = cursor.fetchone()
        if row is None:
            return {"document": {"items": []}, "updated_at": None}
        document = row["document"]
        return {
            "document": document if isinstance(document, dict) else {"items": []},
            "updated_at": self._time(row["updated_at"]),
        }

    def save_plan(self, scope: TrustedScope, document: dict[str, object]) -> dict[str, object]:
        with self._tenant_tx(scope.tenant_id) as cursor:
            cursor.execute(
                """
                INSERT INTO content_plans (id, tenant_id, brand_id, account_id, created_by, document)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, account_id, created_by) DO UPDATE
                SET document = EXCLUDED.document, updated_at = now()
                RETURNING document, updated_at
                """,
                (
                    uuid4(),
                    scope.tenant_id,
                    scope.brand_id,
                    scope.account_id,
                    scope.user_id,
                    Jsonb(document),
                ),
            )
            row = self._one(cursor, "轻量计划没有保存成功")
        saved = row["document"]
        return {
            "document": saved if isinstance(saved, dict) else {"items": []},
            "updated_at": self._time(row["updated_at"]),
        }

    def create_unmet_request(
        self,
        scope: TrustedScope,
        request_text: str,
        catalog_version: str,
        direction_snapshot: dict[str, object],
    ) -> dict[str, object]:
        request_id = uuid4()
        stable_request_id = f"UCR-{request_id}"
        with self._tenant_tx(scope.tenant_id) as cursor:
            cursor.execute(
                """
                INSERT INTO unmet_capability_requests
                    (id, tenant_id, stable_request_id, brand_id, account_id, created_by,
                     request_text, catalog_version, direction_snapshot)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING stable_request_id, gap_type, status, created_at
                """,
                (
                    request_id,
                    scope.tenant_id,
                    stable_request_id,
                    scope.brand_id,
                    scope.account_id,
                    scope.user_id,
                    request_text,
                    catalog_version,
                    Jsonb(direction_snapshot),
                ),
            )
            row = self._one(cursor, "未满足需求没有登记成功")
        return {
            "stable_request_id": str(row["stable_request_id"]),
            "gap_type": str(row["gap_type"]),
            "status": str(row["status"]),
            "response_text": "",
            "created_at": self._time(row["created_at"]),
        }

    def list_unmet_requests(self, scope: TrustedScope) -> list[dict[str, object]]:
        with self._tenant_tx(scope.tenant_id) as cursor:
            cursor.execute(
                """
                SELECT stable_request_id, request_text, catalog_version, gap_type, status,
                       response_text, created_at, responded_at
                FROM unmet_capability_requests
                WHERE tenant_id = %s AND created_by = %s
                ORDER BY created_at DESC LIMIT 50
                """,
                (scope.tenant_id, scope.user_id),
            )
            rows = cursor.fetchall()
        return [
            {
                "stable_request_id": str(row["stable_request_id"]),
                "request_text": str(row["request_text"]),
                "catalog_version": str(row["catalog_version"]),
                "gap_type": str(row["gap_type"]),
                "status": str(row["status"]),
                "response_text": str(row["response_text"]),
                "created_at": self._time(row["created_at"]),
                "responded_at": (
                    self._time(row["responded_at"]) if row["responded_at"] is not None else None
                ),
            }
            for row in rows
        ]

    def ops_unmet_requests(self) -> list[dict[str, object]]:
        """Read across tenants only through the controlled function, exactly like the runtime
        summary does; there is no direct cross-tenant table access anywhere in the application."""
        with (
            psycopg.connect(self._database_url, row_factory=dict_row) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute("SELECT * FROM ops_unmet_capability_requests()")
            rows = cursor.fetchall()
        return [
            {
                "tenant_id": str(row["tenant_id"]),
                "stable_request_id": str(row["stable_request_id"]),
                "request_text": str(row["request_text"]),
                "catalog_version": str(row["catalog_version"]),
                "gap_type": str(row["gap_type"]),
                "status": str(row["status"]),
                "response_text": str(row["response_text"]),
                "created_at": self._time(row["created_at"]),
                "responded_at": (
                    self._time(row["responded_at"]) if row["responded_at"] is not None else None
                ),
            }
            for row in rows
        ]

    def ops_classify_unmet_request(
        self, stable_request_id: str, gap_type: str, status: str, response_text: str
    ) -> str | None:
        with (
            psycopg.connect(self._database_url, row_factory=dict_row) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                "SELECT ops_classify_unmet_capability_request(%s, %s, %s, %s) AS tenant_id",
                (stable_request_id, gap_type, status, response_text),
            )
            row = self._one(cursor, "未满足需求候选没有更新成功")
        return str(row["tenant_id"]) if row["tenant_id"] is not None else None

    def set_material_reference_note(
        self, scope: TrustedScope, asset_id: UUID, reference_note: str
    ) -> dict[str, object]:
        with self._tenant_tx(scope.tenant_id) as cursor:
            cursor.execute(
                """
                UPDATE material_assets asset
                   SET reference_note = %s, reference_version = asset.reference_version + 1
                 WHERE asset.tenant_id = %s AND asset.id = %s AND asset.brand_id = %s
                   AND asset.status = 'active'
                   AND (
                     (asset.scope = 'personal' AND asset.owner_user_id = %s)
                     OR (asset.scope = 'organization' AND EXISTS (
                        SELECT 1 FROM organization_material_maintainers maintainer
                        WHERE maintainer.tenant_id = asset.tenant_id
                          AND maintainer.user_id = %s
                          AND maintainer.organization_id = asset.owner_organization_id
                     ))
                   )
                RETURNING asset.id, asset.title, asset.media_type, asset.reference_note,
                          asset.reference_version
                """,
                (
                    reference_note,
                    scope.tenant_id,
                    asset_id,
                    scope.brand_id,
                    scope.user_id,
                    scope.user_id,
                ),
            )
            row = self._one(cursor, "找不到你可以补写说明的素材。")
        return {
            "id": str(row["id"]),
            "title": str(row["title"]),
            "media_type": str(row["media_type"]),
            "reference_note": str(row["reference_note"]),
            "reference_version": self._integer(row["reference_version"]),
        }
