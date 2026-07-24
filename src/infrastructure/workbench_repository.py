from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row

from src.ports.workbench_repository import WorkbenchRepository
from src.shared.content_origin import aigc_disclosure, is_ai_generated_content
from src.shared.errors import DomainError
from src.shared.types import DisplayScope, TenantManagementScope, TrustedScope


class PostgresWorkbenchRepository(WorkbenchRepository):
    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    @contextmanager
    def _content_tx(self, scope: TrustedScope) -> Iterator[psycopg.Cursor[dict[str, object]]]:
        with (
            psycopg.connect(self._database_url, row_factory=dict_row) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(scope.tenant_id),))
            yield cursor

    @contextmanager
    def _management_tx(self, scope: TenantManagementScope) -> Iterator[psycopg.Cursor[dict[str, object]]]:
        with (
            psycopg.connect(self._database_url, row_factory=dict_row) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(scope.tenant_id),))
            yield cursor

    @contextmanager
    def _display_tx(self, scope: DisplayScope) -> Iterator[psycopg.Cursor[dict[str, object]]]:
        with (
            psycopg.connect(self._database_url, row_factory=dict_row) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(scope.tenant_id),))
            yield cursor

    @staticmethod
    def _one(cursor: psycopg.Cursor[dict[str, object]], message: str) -> dict[str, object]:
        row = cursor.fetchone()
        if row is None:
            raise DomainError(message)
        return row

    def content_identity(self, scope: TrustedScope) -> dict[str, str]:
        with self._content_tx(scope) as cursor:
            cursor.execute(
                """
                SELECT b.name AS brand, u.display_name AS operator, o.name AS organization,
                       a.name AS account, r.name AS content_role
                FROM users u
                JOIN organizations o ON o.id = u.organization_id AND o.tenant_id = u.tenant_id
                JOIN brands b ON b.id = %s AND b.tenant_id = u.tenant_id
                JOIN content_accounts a ON a.id = %s AND a.tenant_id = u.tenant_id
                JOIN auth_grants assignment ON assignment.tenant_id = u.tenant_id AND assignment.user_id = u.id
                    AND assignment.account_id = a.id AND assignment.enabled = true
                JOIN account_content_roles acr ON acr.account_id = a.id AND acr.tenant_id = a.tenant_id
                JOIN content_roles r ON r.id = acr.content_role_id AND r.tenant_id = acr.tenant_id
                WHERE u.tenant_id = %s AND u.id = %s AND u.enabled = true AND a.enabled = true
                ORDER BY r.name LIMIT 1
                """,
                (scope.brand_id, scope.account_id, scope.tenant_id, scope.user_id),
            )
            row = self._one(cursor, "找不到当前可信内容身份")
        return {key: str(value) for key, value in row.items()}

    def user_portal_identity(self, scope: TrustedScope) -> dict[str, str]:
        with self._content_tx(scope) as cursor:
            cursor.execute(
                """
                SELECT b.name AS brand, u.display_name AS operator, o.name AS organization,
                       COALESCE(persona.name, '尚未设置') AS default_persona,
                       COALESCE(persona.boundary, '可维护一份本人默认表达人设；企业账号表达身份另行管理。') AS persona_boundary
                FROM users u
                JOIN organizations o ON o.id = u.organization_id AND o.tenant_id = u.tenant_id
                JOIN brands b ON b.id = %s AND b.tenant_id = u.tenant_id
                LEFT JOIN user_default_personas persona ON persona.tenant_id = u.tenant_id
                    AND persona.user_id = u.id
                WHERE u.tenant_id = %s AND u.id = %s AND u.enabled = true
                """,
                (scope.brand_id, scope.tenant_id, scope.user_id),
            )
            row = self._one(cursor, "找不到当前可信自然人身份")
        return {key: str(value) for key, value in row.items()}

    def management_identity(self, scope: TenantManagementScope) -> dict[str, str]:
        with self._management_tx(scope) as cursor:
            cursor.execute(
                """
                SELECT brand.name AS brand, user_record.display_name AS operator,
                       organization.name AS organization
                FROM users user_record
                JOIN organizations organization
                  ON organization.id = user_record.organization_id
                 AND organization.tenant_id = user_record.tenant_id
                JOIN brands brand
                  ON brand.id = %s
                 AND brand.tenant_id = user_record.tenant_id
                WHERE user_record.tenant_id = %s
                  AND user_record.id = %s
                  AND user_record.enabled = true
                """,
                (scope.brand_id, scope.tenant_id, scope.user_id),
            )
            row = self._one(cursor, "找不到当前可信租户管理身份")
        return {key: str(value) for key, value in row.items()}

    def is_content_operator(self, scope: TrustedScope) -> bool:
        with self._content_tx(scope) as cursor:
            cursor.execute(
                """
                SELECT EXISTS (
                    SELECT 1 FROM auth_grants assignment
                    JOIN users u ON u.id = assignment.user_id AND u.tenant_id = assignment.tenant_id
                    JOIN content_accounts a ON a.id = assignment.account_id AND a.tenant_id = assignment.tenant_id
                    WHERE assignment.tenant_id = %s AND assignment.user_id = %s AND assignment.account_id = %s
                      AND assignment.enabled = true AND u.enabled = true AND a.enabled = true
                ) AS allowed
                """,
                (scope.tenant_id, scope.user_id, scope.account_id),
            )
            return bool(self._one(cursor, "无法读取内容工作资格")["allowed"])

    def is_tenant_manager(self, scope: TenantManagementScope) -> bool:
        with self._management_tx(scope) as cursor:
            cursor.execute(
                """
                SELECT EXISTS (
                    SELECT 1 FROM tenant_management_grants management_grant
                    JOIN users u ON u.id = management_grant.user_id AND u.tenant_id = management_grant.tenant_id
                    WHERE management_grant.tenant_id = %s AND management_grant.user_id = %s
                      AND management_grant.enabled = true AND u.enabled = true
                ) AS allowed
                """,
                (scope.tenant_id, scope.user_id),
            )
            return bool(self._one(cursor, "无法读取租户管理资格")["allowed"])

    def management_operators(self, scope: TenantManagementScope) -> list[dict[str, object]]:
        with self._management_tx(scope) as cursor:
            cursor.execute(
                """
                SELECT u.id, u.display_name, o.name AS organization,
                       COALESCE(string_agg(DISTINCT a.name, '、'), '') AS publishing_accounts,
                       COALESCE(persona.name, '') AS default_persona,
                       EXISTS (
                         SELECT 1 FROM tenant_management_grants manager
                         WHERE manager.tenant_id = u.tenant_id AND manager.user_id = u.id
                           AND manager.enabled = true
                       ) AS manages_tenant
                FROM users u
                JOIN organizations o ON o.id = u.organization_id AND o.tenant_id = u.tenant_id
                LEFT JOIN auth_grants assignment ON assignment.tenant_id = u.tenant_id AND assignment.user_id = u.id
                    AND assignment.enabled = true
                LEFT JOIN content_accounts a ON a.id = assignment.account_id AND a.tenant_id = assignment.tenant_id
                LEFT JOIN user_default_personas persona ON persona.tenant_id = u.tenant_id
                    AND persona.user_id = u.id
                WHERE u.tenant_id = %s AND u.enabled = true
                GROUP BY u.id, u.display_name, o.name, persona.name, u.tenant_id
                ORDER BY u.display_name
                """,
                (scope.tenant_id,),
            )
            rows = cursor.fetchall()
        return [
            {
                "id": str(row["id"]),
                "display_name": str(row["display_name"]),
                "organization": str(row["organization"]),
                "publishing_accounts": str(row["publishing_accounts"]),
                "default_persona": str(row["default_persona"]),
                "manages_tenant": bool(row["manages_tenant"]),
            }
            for row in rows
        ]

    def management_accounts(self, scope: TenantManagementScope) -> list[dict[str, object]]:
        with self._management_tx(scope) as cursor:
            cursor.execute(
                """
                SELECT a.id, a.name, a.channel, r.name AS content_role, r.voice_boundary
                FROM content_accounts a
                JOIN account_content_roles account_role ON account_role.tenant_id = a.tenant_id
                    AND account_role.account_id = a.id
                JOIN content_roles r ON r.id = account_role.content_role_id
                    AND r.tenant_id = account_role.tenant_id
                WHERE a.tenant_id = %s AND a.brand_id = %s AND a.enabled = true
                ORDER BY a.name
                """,
                (scope.tenant_id, scope.brand_id),
            )
            rows = cursor.fetchall()
        return [
            {
                "id": str(row["id"]),
                "name": str(row["name"]),
                "channel": str(row["channel"]),
                "content_role": str(row["content_role"]),
                "voice_boundary": str(row["voice_boundary"]),
            }
            for row in rows
        ]

    def create_publishing_account(
        self,
        scope: TenantManagementScope,
        name: str,
        channel: str,
        content_role_name: str,
        voice_boundary: str,
        operator_id: UUID,
    ) -> dict[str, object]:
        account_id = uuid4()
        content_role_id = uuid4()
        with self._management_tx(scope) as cursor:
            cursor.execute(
                """
                SELECT 1
                FROM brand_expression_baselines
                WHERE tenant_id = %s AND brand_id = %s AND status = 'confirmed'
                """,
                (scope.tenant_id, scope.brand_id),
            )
            self._one(cursor, "请先由品牌方确认当前品牌表达草案，再创建正式发布账号")
            cursor.execute(
                "SELECT id FROM users WHERE tenant_id = %s AND id = %s AND enabled = true",
                (scope.tenant_id, operator_id),
            )
            self._one(cursor, "只能向当前租户已登记且启用的自然人授权发布账号")
            cursor.execute(
                """
                SELECT account.id, account.channel, role.name AS content_role,
                       role.voice_boundary,
                       EXISTS (
                           SELECT 1
                           FROM auth_grants grant_record
                           WHERE grant_record.tenant_id = account.tenant_id
                             AND grant_record.account_id = account.id
                             AND grant_record.user_id = %s
                             AND grant_record.enabled = true
                       ) AS has_operator
                FROM content_accounts account
                JOIN account_content_roles account_role
                  ON account_role.tenant_id = account.tenant_id
                 AND account_role.account_id = account.id
                JOIN content_roles role
                  ON role.tenant_id = account_role.tenant_id
                 AND role.id = account_role.content_role_id
                 AND role.brand_id = account.brand_id
                WHERE account.tenant_id = %s
                  AND account.brand_id = %s
                  AND account.name = %s
                  AND account.enabled = true
                """,
                (operator_id, scope.tenant_id, scope.brand_id, name),
            )
            existing = cursor.fetchone()
            if existing is not None:
                if (
                    str(existing["channel"]) != channel
                    or str(existing["content_role"]) != content_role_name
                    or str(existing["voice_boundary"]) != voice_boundary
                    or not bool(existing["has_operator"])
                ):
                    raise DomainError("当前品牌已有同名发布账号，但平台、表达身份或操作者不同。")
                return {
                    "id": str(existing["id"]),
                    "name": name,
                    "channel": channel,
                    "content_role": content_role_name,
                    "voice_boundary": voice_boundary,
                    "operator_id": str(operator_id),
                    "shared_password": False,
                }
            cursor.execute(
                "SELECT 1 FROM content_roles WHERE tenant_id = %s AND brand_id = %s AND name = %s",
                (scope.tenant_id, scope.brand_id, content_role_name),
            )
            if cursor.fetchone() is not None:
                raise DomainError("当前品牌已有同名企业表达人设。")
            cursor.execute(
                "INSERT INTO content_accounts (id, tenant_id, brand_id, name, channel) VALUES (%s, %s, %s, %s, %s)",
                (account_id, scope.tenant_id, scope.brand_id, name, channel),
            )
            cursor.execute(
                "INSERT INTO content_roles (id, tenant_id, brand_id, name, voice_boundary) VALUES (%s, %s, %s, %s, %s)",
                (
                    content_role_id,
                    scope.tenant_id,
                    scope.brand_id,
                    content_role_name,
                    voice_boundary,
                ),
            )
            cursor.execute(
                "INSERT INTO account_content_roles (id, tenant_id, account_id, content_role_id) VALUES (%s, %s, %s, %s)",
                (uuid4(), scope.tenant_id, account_id, content_role_id),
            )
            cursor.execute(
                "INSERT INTO auth_grants (id, tenant_id, user_id, account_id, role_name) VALUES (%s, %s, %s, %s, %s)",
                (uuid4(), scope.tenant_id, operator_id, account_id, "发布账号操作资格"),
            )
            self._event(cursor, scope, "publishing_account.created", "content_account", account_id)
        return {
            "id": str(account_id),
            "name": name,
            "channel": channel,
            "content_role": content_role_name,
            "voice_boundary": voice_boundary,
            "operator_id": str(operator_id),
            "shared_password": False,
        }

    def create_operator(
        self,
        scope: TenantManagementScope,
        display_name: str,
        account_id: UUID,
        default_persona_name: str,
        default_persona_boundary: str,
    ) -> dict[str, object]:
        operator_id = uuid4()
        grant_id = uuid4()
        with self._management_tx(scope) as cursor:
            cursor.execute(
                "SELECT id FROM content_accounts WHERE tenant_id = %s AND brand_id = %s AND id = %s AND enabled = true",
                (scope.tenant_id, scope.brand_id, account_id),
            )
            self._one(cursor, "只能授权当前品牌已有的发布账号")
            cursor.execute(
                "SELECT organization_id FROM users WHERE tenant_id = %s AND id = %s AND enabled = true",
                (scope.tenant_id, scope.user_id),
            )
            organization_id = UUID(str(self._one(cursor, "找不到当前租户管理员")["organization_id"]))
            cursor.execute(
                "SELECT EXISTS (SELECT 1 FROM users WHERE tenant_id = %s AND display_name = %s) AS exists",
                (scope.tenant_id, display_name),
            )
            if bool(self._one(cursor, "无法检查自然人身份")["exists"]):
                raise DomainError("当前租户已经有同名自然人身份。")
            cursor.execute(
                "INSERT INTO users (id, tenant_id, organization_id, display_name) VALUES (%s, %s, %s, %s)",
                (operator_id, scope.tenant_id, organization_id, display_name),
            )
            cursor.execute(
                "INSERT INTO auth_grants (id, tenant_id, user_id, account_id, role_name) VALUES (%s, %s, %s, %s, %s)",
                (grant_id, scope.tenant_id, operator_id, account_id, "发布账号操作资格"),
            )
            if default_persona_name and default_persona_boundary:
                cursor.execute(
                    "INSERT INTO user_default_personas (id, tenant_id, user_id, name, boundary) VALUES (%s, %s, %s, %s, %s)",
                    (
                        uuid4(),
                        scope.tenant_id,
                        operator_id,
                        default_persona_name,
                        default_persona_boundary,
                    ),
                )
            self._event(cursor, scope, "tenant_operator.created", "user", operator_id)
        return {
            "id": str(operator_id),
            "display_name": display_name,
            "account_id": str(account_id),
            "shared_password": False,
        }

    def update_default_persona(self, scope: TrustedScope, name: str, boundary: str) -> dict[str, object]:
        with self._content_tx(scope) as cursor:
            cursor.execute(
                """
                INSERT INTO user_default_personas (id, tenant_id, user_id, name, boundary)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, user_id) DO UPDATE
                SET name = EXCLUDED.name, boundary = EXCLUDED.boundary,
                    version = user_default_personas.version + 1, updated_at = now()
                RETURNING id, name, boundary, version
                """,
                (uuid4(), scope.tenant_id, scope.user_id, name, boundary),
            )
            row = self._one(cursor, "本人默认表达人设没有保存成功")
            self._event(
                cursor,
                scope,
                "user_default_persona.updated",
                "user_default_persona",
                UUID(str(row["id"])),
            )
        return {
            "id": str(row["id"]),
            "name": str(row["name"]),
            "boundary": str(row["boundary"]),
            "version": self._integer(row["version"]),
        }

    def display_identity(self, scope: DisplayScope) -> dict[str, str]:
        with self._display_tx(scope) as cursor:
            cursor.execute(
                """
                SELECT b.name AS brand, u.display_name AS operator, o.name AS organization, s.name AS store
                FROM users u
                JOIN organizations o ON o.id = u.organization_id AND o.tenant_id = u.tenant_id
                JOIN brands b ON b.id = %s AND b.tenant_id = u.tenant_id
                JOIN display_stores s ON s.execution_organization_id = %s AND s.brand_id = b.id
                    AND s.tenant_id = b.tenant_id
                WHERE u.tenant_id = %s AND u.id = %s
                """,
                (scope.brand_id, scope.organization_id, scope.tenant_id, scope.user_id),
            )
            row = self._one(cursor, "找不到当前可信陈列身份")
        return {key: str(value) for key, value in row.items()}

    def recent_content(self, scope: TrustedScope) -> list[dict[str, object]]:
        with self._content_tx(scope) as cursor:
            cursor.execute(
                """
                SELECT t.id AS task_id, cv.id AS version_id, cv.version_number, cv.outline, cv.created_at,
                       CASE
                         WHEN a.channel = '抖音' AND t.media_format = 'video' THEN 'douyin_video'
                         WHEN a.channel = '小红书' AND t.media_format = 'video' THEN 'xiaohongshu_video'
                         WHEN a.channel = '小红书' AND t.media_format = 'graphic' THEN 'xiaohongshu_graphic'
                         WHEN a.channel = '微信视频号' AND t.media_format = 'video' THEN 'wechat_channels_video'
                         ELSE 'douyin_video'
                       END AS target
                FROM content_items item
                JOIN business_tasks t ON t.id = item.task_id AND t.tenant_id = item.tenant_id
                JOIN content_versions cv ON cv.task_id = t.id AND cv.tenant_id = t.tenant_id
                    AND cv.version_number = item.current_version
                JOIN content_accounts a ON a.id = t.account_id AND a.tenant_id = t.tenant_id
                WHERE t.tenant_id = %s AND t.brand_id = %s AND t.account_id = %s AND t.created_by = %s
                ORDER BY cv.created_at DESC LIMIT 20
                """,
                (scope.tenant_id, scope.brand_id, scope.account_id, scope.user_id),
            )
            rows = cursor.fetchall()
        return [
            {
                "task_id": str(row["task_id"]),
                "version_id": str(row["version_id"]),
                "version": self._integer(row["version_number"]),
                "title": str(row["outline"]),
                "target": str(row["target"]),
                "updated_at": self._time(row["created_at"]),
                "status": "已有成品",
            }
            for row in rows
        ]

    def content_versions(self, scope: TrustedScope, task_id: UUID) -> list[dict[str, object]]:
        with self._content_tx(scope) as cursor:
            cursor.execute(
                """
                SELECT cv.id AS version_id, cv.version_number, cv.outline, cv.body, cv.created_at, gr.model,
                       CASE
                         WHEN a.channel = '抖音' AND t.media_format = 'video' THEN 'douyin_video'
                         WHEN a.channel = '小红书' AND t.media_format = 'video' THEN 'xiaohongshu_video'
                         WHEN a.channel = '小红书' AND t.media_format = 'graphic' THEN 'xiaohongshu_graphic'
                         WHEN a.channel = '微信视频号' AND t.media_format = 'video' THEN 'wechat_channels_video'
                         ELSE 'douyin_video'
                       END AS target_key
                FROM content_versions cv
                JOIN generation_runs gr ON gr.id = cv.run_id AND gr.tenant_id = cv.tenant_id
                JOIN business_tasks t ON t.id = cv.task_id AND t.tenant_id = cv.tenant_id
                JOIN content_accounts a ON a.id = t.account_id AND a.tenant_id = t.tenant_id
                WHERE cv.tenant_id = %s AND cv.task_id = %s AND t.brand_id = %s
                  AND t.account_id = %s AND t.created_by = %s
                ORDER BY cv.version_number DESC
                """,
                (scope.tenant_id, task_id, scope.brand_id, scope.account_id, scope.user_id),
            )
            rows = cursor.fetchall()
        return [
            {
                "task_id": str(task_id),
                "version_id": str(row["version_id"]),
                "version": self._integer(row["version_number"]),
                "outline": str(row["outline"]),
                "body": str(row["body"]),
                "target_key": str(row["target_key"]),
                "ai_generated": is_ai_generated_content(row["model"]),
                "aigc_label": aigc_disclosure(row["model"])[0],
                "aigc_release_reminder": aigc_disclosure(row["model"])[1],
                "created_at": self._time(row["created_at"]),
            }
            for row in rows
        ]

    def recent_display(self, scope: DisplayScope) -> list[dict[str, object]]:
        with self._display_tx(scope) as cursor:
            cursor.execute(
                """
                SELECT t.id AS task_id, v.id AS version_id, v.version_number, v.body, v.created_at
                FROM display_artifacts artifact
                JOIN display_tasks t ON t.id = artifact.task_id AND t.tenant_id = artifact.tenant_id
                JOIN display_artifact_versions v ON v.task_id = t.id AND v.tenant_id = t.tenant_id
                    AND v.version_number = artifact.current_version
                WHERE t.tenant_id = %s AND t.brand_id = %s AND t.organization_id = %s AND t.created_by = %s
                ORDER BY v.created_at DESC LIMIT 20
                """,
                (scope.tenant_id, scope.brand_id, scope.organization_id, scope.user_id),
            )
            rows = cursor.fetchall()
        return [
            {
                "task_id": str(row["task_id"]),
                "version_id": str(row["version_id"]),
                "version": self._integer(row["version_number"]),
                "title": self._display_title(str(row["body"])),
                "updated_at": self._time(row["created_at"]),
                "status": "已有方案",
            }
            for row in rows
        ]

    def display_versions(self, scope: DisplayScope, task_id: UUID) -> list[dict[str, object]]:
        with self._display_tx(scope) as cursor:
            cursor.execute(
                """
                SELECT v.id AS version_id, v.version_number, v.body, v.created_at
                FROM display_artifact_versions v
                JOIN display_tasks t ON t.id = v.task_id AND t.tenant_id = v.tenant_id
                WHERE v.tenant_id = %s AND v.task_id = %s AND t.brand_id = %s
                  AND t.organization_id = %s AND t.created_by = %s
                ORDER BY v.version_number DESC
                """,
                (scope.tenant_id, task_id, scope.brand_id, scope.organization_id, scope.user_id),
            )
            rows = cursor.fetchall()
        return [
            {
                "task_id": str(task_id),
                "version_id": str(row["version_id"]),
                "version": self._integer(row["version_number"]),
                "body": str(row["body"]),
                "created_at": self._time(row["created_at"]),
            }
            for row in rows
        ]

    def readiness(self, scope: TenantManagementScope) -> list[dict[str, str]]:
        expression = self.brand_expression(scope)
        with self._management_tx(scope) as cursor:
            cursor.execute(
                """
                SELECT
                    EXISTS (
                        SELECT 1
                        FROM content_accounts account
                        JOIN account_content_roles account_role
                          ON account_role.tenant_id = account.tenant_id
                         AND account_role.account_id = account.id
                        JOIN content_roles role
                          ON role.tenant_id = account_role.tenant_id
                         AND role.id = account_role.content_role_id
                         AND role.brand_id = account.brand_id
                        JOIN auth_grants grant_record
                          ON grant_record.tenant_id = account.tenant_id
                         AND grant_record.account_id = account.id
                         AND grant_record.user_id = %s
                         AND grant_record.enabled = true
                        WHERE account.tenant_id = %s
                          AND account.brand_id = %s
                          AND account.enabled = true
                    ) AS has_account_role,
                    EXISTS (
                        SELECT 1
                        FROM brand_products product
                        WHERE product.tenant_id = %s
                          AND product.brand_id = %s
                    ) AS has_confirmed_products,
                    EXISTS (
                        SELECT 1
                        FROM display_stores store
                        WHERE store.tenant_id = %s
                          AND store.brand_id = %s
                    ) AS has_dm01_profile
                """,
                (
                    scope.user_id,
                    scope.tenant_id,
                    scope.brand_id,
                    scope.tenant_id,
                    scope.brand_id,
                    scope.tenant_id,
                    scope.brand_id,
                ),
            )
            state = self._one(cursor, "无法读取当前入驻条件")
        has_account_role = bool(state["has_account_role"])
        has_confirmed_products = bool(state["has_confirmed_products"])
        has_dm01_profile = bool(state["has_dm01_profile"])
        return [
            {
                "id": "brand_expression",
                "title": "确认品牌表达草案",
                "detail": "当前草案等待确认。确认前仍可继续讨论，但不会成为正式表达基线。"
                if expression["status"] == "draft"
                else "当前品牌表达基线已经确认，可在需要时再更新。",
                "unlock": "内容生产会使用已确认的表达边界。",
                "state": "needs_action" if expression["status"] == "draft" else "ready",
            },
            {
                "id": "account_role",
                "title": "发布账号、表达身份与操作者",
                "detail": "当前品牌已有一个发布账号、独立表达身份和获授权自然人。"
                if has_account_role
                else "还需要确认一个实际使用的发布账号、独立表达身份，并授权当前自然人。",
                "unlock": "以服务端可信的品牌、账号和自然人身份生产内容。",
                "state": "ready" if has_account_role else "needs_action",
            },
            {
                "id": "product_facts",
                "title": "已确认商品资料",
                "detail": "已有可供商品承重内容使用的已确认资料。"
                if has_confirmed_products
                else "具体商品和价格仍未确认；P3/P4 可以使用，商品承重的 P1/P2/P5 暂不启用。",
                "unlock": "启用需要具体商品硬事实的内容能力。",
                "state": "ready" if has_confirmed_products else "needs_action",
            },
            {
                "id": "dm01_profile",
                "title": "真实双层挂杆条件",
                "detail": "已有当前品牌可执行的真实门店挂杆档案。"
                if has_dm01_profile
                else "真实门店双层挂杆条件尚未确认；只限制 DM01，不影响内容生产。",
                "unlock": "在真实门店范围内启用 DM01 执行方案。",
                "state": "ready" if has_dm01_profile else "needs_action",
            },
        ]

    def brand_expression(self, scope: TenantManagementScope) -> dict[str, object]:
        with self._management_tx(scope) as cursor:
            cursor.execute(
                """
                SELECT version, status, draft FROM brand_expression_baselines
                WHERE tenant_id = %s AND brand_id = %s
                """,
                (scope.tenant_id, scope.brand_id),
            )
            row = self._one(cursor, "当前品牌尚无表达草案")
        return {
            "version": self._integer(row["version"]),
            "status": str(row["status"]),
            "draft": str(row["draft"]),
        }

    def confirm_brand_expression(self, scope: TenantManagementScope, draft: str) -> dict[str, object]:
        with self._management_tx(scope) as cursor:
            cursor.execute(
                """
                SELECT version, status, draft
                FROM brand_expression_baselines
                WHERE tenant_id = %s AND brand_id = %s
                """,
                (scope.tenant_id, scope.brand_id),
            )
            current = self._one(cursor, "当前品牌尚无表达草案")
            if str(current["status"]) == "confirmed" and str(current["draft"]) == draft:
                return {
                    "version": self._integer(current["version"]),
                    "status": "confirmed",
                    "draft": draft,
                }
            version = self._integer(current["version"])
            if str(current["status"]) == "confirmed":
                version += 1
            cursor.execute(
                """
                UPDATE brand_expression_baselines
                SET draft = %s, version = %s, status = 'confirmed',
                    confirmed_by = %s, confirmed_at = now(), updated_at = now()
                WHERE tenant_id = %s AND brand_id = %s
                RETURNING version, status, draft
                """,
                (
                    draft,
                    version,
                    scope.user_id,
                    scope.tenant_id,
                    scope.brand_id,
                ),
            )
            row = self._one(cursor, "当前品牌表达草案没有确认成功")
            cursor.execute(
                """
                UPDATE brands
                SET positioning = %s,
                    tone = '以当前已确认品牌表达版本为准。',
                    strategy_version = %s
                WHERE tenant_id = %s AND id = %s
                """,
                (
                    draft,
                    f"brand-expression-v{version}",
                    scope.tenant_id,
                    scope.brand_id,
                ),
            )
            self._event(
                cursor,
                scope,
                "brand_expression.confirmed",
                "brand_expression_baseline",
                scope.brand_id,
            )
        return {
            "version": self._integer(row["version"]),
            "status": str(row["status"]),
            "draft": str(row["draft"]),
        }

    def list_series(self, scope: TrustedScope) -> list[dict[str, object]]:
        with self._content_tx(scope) as cursor:
            cursor.execute(
                """
                SELECT id, title, premise FROM content_series
                WHERE tenant_id = %s AND brand_id = %s AND created_by = %s AND account_id = %s
                ORDER BY created_at DESC
                """,
                (scope.tenant_id, scope.brand_id, scope.user_id, scope.account_id),
            )
            series_rows = cursor.fetchall()
            result: list[dict[str, object]] = []
            for series in series_rows:
                cursor.execute(
                    """
                    SELECT item.task_id, item.position, cv.outline
                    FROM content_series_items item
                    JOIN business_tasks task ON task.id = item.task_id
                        AND task.tenant_id = item.tenant_id
                    JOIN content_items content_item ON content_item.task_id = item.task_id
                        AND content_item.tenant_id = item.tenant_id
                    JOIN content_versions cv ON cv.task_id = item.task_id AND cv.tenant_id = item.tenant_id
                        AND cv.version_number = content_item.current_version
                    WHERE item.tenant_id = %s AND item.series_id = %s AND task.account_id = %s
                    ORDER BY item.position
                    """,
                    (scope.tenant_id, series["id"], scope.account_id),
                )
                result.append(
                    {
                        "id": str(series["id"]),
                        "title": str(series["title"]),
                        "premise": str(series["premise"]),
                        "items": [
                            {
                                "task_id": str(item["task_id"]),
                                "position": self._integer(item["position"]),
                                "title": str(item["outline"]),
                            }
                            for item in cursor.fetchall()
                        ],
                    }
                )
        return result

    def create_series(self, scope: TrustedScope, title: str, premise: str) -> dict[str, object]:
        series_id = uuid4()
        with self._content_tx(scope) as cursor:
            cursor.execute(
                """
                INSERT INTO content_series (id, tenant_id, brand_id, account_id, created_by, title, premise)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    series_id,
                    scope.tenant_id,
                    scope.brand_id,
                    scope.account_id,
                    scope.user_id,
                    title,
                    premise,
                ),
            )
            self._event(cursor, scope, "content_series.created", "content_series", series_id)
        return {"id": str(series_id), "title": title, "premise": premise, "items": []}

    def add_series_item(
        self, scope: TrustedScope, series_id: UUID, task_id: UUID, position: int | None
    ) -> dict[str, object]:
        with self._content_tx(scope) as cursor:
            existing = self._series_task_ids(cursor, scope, series_id)
            cursor.execute(
                """
                SELECT id FROM business_tasks
                WHERE tenant_id = %s AND id = %s AND brand_id = %s AND created_by = %s AND account_id = %s
                """,
                (scope.tenant_id, task_id, scope.brand_id, scope.user_id, scope.account_id),
            )
            self._one(cursor, "只能把当前发布账号的内容纳入系列")
            if task_id in existing:
                raise DomainError("这份内容已在当前系列中。")
            insert_at = len(existing) if position is None else position - 1
            if not 0 <= insert_at <= len(existing):
                raise DomainError("系列插入位置无效。")
            existing.insert(insert_at, task_id)
            self._replace_series_items(cursor, scope, series_id, existing)
            self._event(cursor, scope, "content_series.item_added", "content_series", series_id)
        return self._series_value(scope, series_id)

    def reorder_series(self, scope: TrustedScope, series_id: UUID, task_ids: tuple[UUID, ...]) -> dict[str, object]:
        with self._content_tx(scope) as cursor:
            existing = self._series_task_ids(cursor, scope, series_id)
            if len(task_ids) != len(existing) or set(task_ids) != set(existing):
                raise DomainError("只能重排当前系列已有的内容。")
            self._replace_series_items(cursor, scope, series_id, list(task_ids))
            self._event(cursor, scope, "content_series.reordered", "content_series", series_id)
        return self._series_value(scope, series_id)

    def reset_series(self, scope: TrustedScope, series_id: UUID) -> dict[str, object]:
        with self._content_tx(scope) as cursor:
            self._series_task_ids(cursor, scope, series_id)
            cursor.execute(
                "DELETE FROM content_series_items WHERE tenant_id = %s AND series_id = %s",
                (scope.tenant_id, series_id),
            )
            self._event(cursor, scope, "content_series.reset", "content_series", series_id)
        return self._series_value(scope, series_id)

    def list_materials(self, scope: TrustedScope) -> list[dict[str, object]]:
        with self._content_tx(scope) as cursor:
            cursor.execute(
                """
                SELECT m.id, m.title, m.media_type, m.scope, m.created_at, m.status,
                       m.original_filename, m.byte_size, m.checksum_sha256, m.reference_version
                FROM material_assets m
                WHERE m.tenant_id = %s AND m.brand_id = %s AND m.status = 'active'
                  AND (
                    (m.scope = 'personal' AND m.owner_user_id = %s)
                    OR (m.scope = 'organization' AND m.owner_organization_id = (
                        SELECT organization_id FROM users WHERE tenant_id = %s AND id = %s
                    ))
                  )
                ORDER BY m.created_at DESC
                """,
                (scope.tenant_id, scope.brand_id, scope.user_id, scope.tenant_id, scope.user_id),
            )
            rows = cursor.fetchall()
        return [
            {
                "id": str(row["id"]),
                "title": str(row["title"]),
                "media_type": str(row["media_type"]),
                "scope": str(row["scope"]),
                "created_at": self._time(row["created_at"]),
                "status": str(row["status"]),
                "original_filename": str(row["original_filename"]),
                "byte_size": self._integer(row["byte_size"]),
                "checksum_sha256": str(row["checksum_sha256"]),
                "reference_version": self._integer(row["reference_version"]),
            }
            for row in rows
        ]

    def is_material_maintainer(self, scope: TrustedScope) -> bool:
        with self._content_tx(scope) as cursor:
            cursor.execute(
                """
                SELECT EXISTS (
                    SELECT 1 FROM organization_material_maintainers maintainer
                    JOIN users u ON u.organization_id = maintainer.organization_id
                        AND u.tenant_id = maintainer.tenant_id
                    WHERE maintainer.tenant_id = %s AND maintainer.user_id = %s AND u.id = %s
                ) AS allowed
                """,
                (scope.tenant_id, scope.user_id, scope.user_id),
            )
            return bool(self._one(cursor, "无法读取素材维护资格")["allowed"])

    def create_material(
        self,
        scope: TrustedScope,
        asset_id: UUID,
        title: str,
        media_type: str,
        asset_scope: str,
        object_key: str,
        byte_size: int,
        original_filename: str,
        checksum_sha256: str,
    ) -> dict[str, object]:
        with self._content_tx(scope) as cursor:
            owner_user_id: UUID | None = scope.user_id if asset_scope == "personal" else None
            owner_organization_id: UUID | None = None
            if asset_scope == "organization":
                cursor.execute(
                    "SELECT organization_id FROM users WHERE tenant_id = %s AND id = %s",
                    (scope.tenant_id, scope.user_id),
                )
                owner_organization_id = UUID(str(self._one(cursor, "找不到当前组织")["organization_id"]))
            cursor.execute(
                """
                INSERT INTO material_assets
                    (id, tenant_id, brand_id, scope, owner_user_id, owner_organization_id, title, media_type, object_key, byte_size, original_filename, checksum_sha256)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, title, media_type, scope, created_at, status, original_filename, byte_size, checksum_sha256, reference_version
                """,
                (
                    asset_id,
                    scope.tenant_id,
                    scope.brand_id,
                    asset_scope,
                    owner_user_id,
                    owner_organization_id,
                    title,
                    media_type,
                    object_key,
                    byte_size,
                    original_filename,
                    checksum_sha256,
                ),
            )
            row = self._one(cursor, "素材元数据没有保存成功")
            self._event(cursor, scope, "material.created", "material_asset", asset_id)
        return {
            "id": str(row["id"]),
            "title": str(row["title"]),
            "media_type": str(row["media_type"]),
            "scope": str(row["scope"]),
            "created_at": self._time(row["created_at"]),
            "status": str(row["status"]),
            "original_filename": str(row["original_filename"]),
            "byte_size": self._integer(row["byte_size"]),
            "checksum_sha256": str(row["checksum_sha256"]),
            "reference_version": self._integer(row["reference_version"]),
        }

    def request_material_deletion(self, scope: TrustedScope, asset_id: UUID) -> str:
        with self._content_tx(scope) as cursor:
            cursor.execute(
                """
                SELECT m.object_key, m.scope, m.owner_organization_id
                FROM material_assets m
                WHERE m.tenant_id = %s AND m.id = %s AND m.brand_id = %s
                  AND m.status IN ('active', 'deletion_pending')
                  AND (m.owner_user_id = %s OR (m.scope = 'organization' AND EXISTS (
                    SELECT 1 FROM organization_material_maintainers maintainer
                    JOIN users u ON u.organization_id = maintainer.organization_id AND u.tenant_id = maintainer.tenant_id
                    WHERE maintainer.tenant_id = m.tenant_id AND maintainer.user_id = %s AND u.id = %s
                      AND maintainer.organization_id = m.owner_organization_id
                  )))
                """,
                (
                    scope.tenant_id,
                    asset_id,
                    scope.brand_id,
                    scope.user_id,
                    scope.user_id,
                    scope.user_id,
                ),
            )
            row = self._one(cursor, "找不到可删除的素材")
            cursor.execute(
                "UPDATE material_assets SET status = 'deletion_pending' WHERE tenant_id = %s AND id = %s",
                (scope.tenant_id, asset_id),
            )
            self._event(cursor, scope, "material.deletion_requested", "material_asset", asset_id)
        return str(row["object_key"])

    def finalize_material_deletion(self, scope: TrustedScope, asset_id: UUID) -> None:
        with self._content_tx(scope) as cursor:
            cursor.execute(
                "DELETE FROM material_assets WHERE tenant_id = %s AND id = %s AND status = 'deletion_pending'",
                (scope.tenant_id, asset_id),
            )
            if cursor.rowcount != 1:
                raise DomainError("素材删除状态已变化，请刷新后重试。")
            self._event(cursor, scope, "material.deleted", "material_asset", asset_id)

    def _series_task_ids(
        self, cursor: psycopg.Cursor[dict[str, object]], scope: TrustedScope, series_id: UUID
    ) -> list[UUID]:
        cursor.execute(
            """
            SELECT series.id FROM content_series series
            WHERE series.tenant_id = %s AND series.id = %s AND series.brand_id = %s
              AND series.created_by = %s AND series.account_id = %s
            """,
            (scope.tenant_id, series_id, scope.brand_id, scope.user_id, scope.account_id),
        )
        self._one(cursor, "找不到当前内容系列")
        cursor.execute(
            """
            SELECT item.task_id FROM content_series_items item
            JOIN business_tasks task ON task.id = item.task_id AND task.tenant_id = item.tenant_id
            WHERE item.tenant_id = %s AND item.series_id = %s AND task.account_id = %s
            ORDER BY item.position
            """,
            (scope.tenant_id, series_id, scope.account_id),
        )
        return [UUID(str(row["task_id"])) for row in cursor.fetchall()]

    def _replace_series_items(
        self,
        cursor: psycopg.Cursor[dict[str, object]],
        scope: TrustedScope,
        series_id: UUID,
        task_ids: list[UUID],
    ) -> None:
        cursor.execute(
            "DELETE FROM content_series_items WHERE tenant_id = %s AND series_id = %s",
            (scope.tenant_id, series_id),
        )
        for position, task_id in enumerate(task_ids, start=1):
            cursor.execute(
                "INSERT INTO content_series_items (id, tenant_id, series_id, task_id, position) VALUES (%s, %s, %s, %s, %s)",
                (uuid4(), scope.tenant_id, series_id, task_id, position),
            )

    def _series_value(self, scope: TrustedScope, series_id: UUID) -> dict[str, object]:
        values = self.list_series(scope)
        for value in values:
            if value["id"] == str(series_id):
                return value
        raise DomainError("找不到当前内容系列")

    def _event(
        self,
        cursor: psycopg.Cursor[dict[str, object]],
        scope: TenantManagementScope | TrustedScope,
        event_type: str,
        entity_type: str,
        entity_id: UUID,
    ) -> None:
        cursor.execute(
            "INSERT INTO activity_events (id, tenant_id, actor_id, event_type, entity_type, entity_id) VALUES (%s, %s, %s, %s, %s, %s)",
            (uuid4(), scope.tenant_id, scope.user_id, event_type, entity_type, entity_id),
        )

    @staticmethod
    def _integer(value: object) -> int:
        if not isinstance(value, int):
            raise DomainError("工作台版本数据无效")
        return value

    @staticmethod
    def _time(value: object) -> str:
        if not isinstance(value, datetime):
            raise DomainError("工作台时间数据无效")
        return value.isoformat()

    @staticmethod
    def _display_title(body: str) -> str:
        lines = [line.strip("# ") for line in body.splitlines() if line.strip()]
        return lines[0] if lines else "墙面双层挂杆方案"
