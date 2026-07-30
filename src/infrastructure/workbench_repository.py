from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from src.infrastructure.readiness_paths import readiness_path_state
from src.ports.workbench_repository import WorkbenchRepository
from src.shared.content_origin import aigc_disclosure, is_ai_generated_content
from src.shared.content_snapshot import visible_direction
from src.shared.errors import DomainError
from src.shared.types import (
    DisplayScope,
    SpeakerKind,
    TenantManagementScope,
    TrustedScope,
)
from src.shared.version_integrity import validate_version_content


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
                SELECT b.name AS brand, u.display_name AS operator,
                       o.name AS organization,
                       root.name AS account, target.channel AS platform,
                       r.name AS content_role, root.business_data_kind,
                       control_organization.name AS control_organization,
                       profile.id AS profile_id,
                       profile.version AS profile_version
                FROM users u
                JOIN organizations o ON o.id = u.organization_id AND o.tenant_id = u.tenant_id
                JOIN brands b ON b.id = %s AND b.tenant_id = u.tenant_id
                JOIN content_accounts target ON target.id = %s AND target.tenant_id = u.tenant_id
                JOIN content_accounts root
                  ON root.tenant_id = target.tenant_id
                 AND root.id = COALESCE(target.carrier_of_account_id, target.id)
                JOIN auth_grants assignment ON assignment.tenant_id = u.tenant_id AND assignment.user_id = u.id
                    AND assignment.account_id = root.id AND assignment.enabled = true
                JOIN account_content_roles acr ON acr.account_id = root.id AND acr.tenant_id = root.tenant_id
                JOIN content_roles r ON r.id = acr.content_role_id AND r.tenant_id = acr.tenant_id
                LEFT JOIN organizations control_organization
                  ON control_organization.tenant_id = root.tenant_id
                 AND control_organization.id = root.control_organization_id
                LEFT JOIN account_expression_profile_versions profile
                  ON profile.tenant_id = root.tenant_id
                 AND profile.account_id = root.id
                 AND profile.id = root.current_expression_profile_id
                WHERE u.tenant_id = %s AND u.id = %s AND u.enabled = true
                  AND u.entry_kind = 'tenant_user'
                  AND target.enabled = true
                  AND target.platform_enabled = true
                  AND root.enabled = true
                ORDER BY r.name LIMIT 1
                """,
                (scope.brand_id, scope.account_id, scope.tenant_id, scope.user_id),
            )
            row = self._one(cursor, "找不到当前可信内容身份")
        return {
            key: (str(value) if value is not None else "")
            for key, value in row.items()
        }

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
                SELECT brand.name AS brand, user_record.id AS operator_id,
                       user_record.display_name AS operator,
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
                  AND user_record.entry_kind = 'tenant_admin'
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
                    JOIN content_accounts target
                      ON target.id = %s AND target.tenant_id = assignment.tenant_id
                    JOIN content_accounts root
                      ON root.tenant_id = target.tenant_id
                     AND root.id = COALESCE(target.carrier_of_account_id, target.id)
                     AND root.id = assignment.account_id
                    WHERE assignment.tenant_id = %s AND assignment.user_id = %s
                      AND assignment.enabled = true AND u.enabled = true
                      AND u.entry_kind = 'tenant_user'
                      AND target.enabled = true
                      AND target.platform_enabled = true
                      AND root.enabled = true
                ) AS allowed
                """,
                (scope.account_id, scope.tenant_id, scope.user_id),
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
                      AND u.entry_kind = 'tenant_admin'
                ) AS allowed
                """,
                (scope.tenant_id, scope.user_id),
            )
            return bool(self._one(cursor, "无法读取租户管理资格")["allowed"])

    def management_operators(self, scope: TenantManagementScope) -> list[dict[str, object]]:
        with self._management_tx(scope) as cursor:
            cursor.execute(
                """
                SELECT u.id, u.display_name, u.enabled, o.id AS organization_id,
                       o.name AS organization,
                       credential.username, u.entry_kind,
                       EXISTS (
                         SELECT 1 FROM tenant_management_grants manager
                         WHERE manager.tenant_id = u.tenant_id AND manager.user_id = u.id
                           AND manager.enabled = true
                       ) AS manages_tenant,
                       EXISTS (
                         SELECT 1 FROM display_access_grants display_grant
                         WHERE display_grant.tenant_id = u.tenant_id
                           AND display_grant.user_id = u.id
                           AND display_grant.enabled = true
                       ) AS can_use_display,
                       EXISTS (
                         SELECT 1 FROM organization_material_maintainers maintainer
                         WHERE maintainer.tenant_id = u.tenant_id
                           AND maintainer.organization_id = u.organization_id
                           AND maintainer.user_id = u.id
                       ) AS maintains_organization_materials,
                       COALESCE(
                         (
                           SELECT jsonb_agg(
                             jsonb_build_object(
                               'account_id', account_grant.account_id,
                               'account_name', granted_account.name,
                               'account_enabled', granted_account.enabled,
                               'can_maintain_expression_profile',
                                   account_grant.can_maintain_expression_profile
                             )
                             ORDER BY granted_account.name
                           )
                           FROM auth_grants account_grant
                           JOIN content_accounts granted_account
                             ON granted_account.tenant_id = account_grant.tenant_id
                            AND granted_account.id = account_grant.account_id
                           WHERE account_grant.tenant_id = u.tenant_id
                             AND account_grant.user_id = u.id
                             AND account_grant.enabled = true
                             AND granted_account.carrier_of_account_id IS NULL
                         ),
                         '[]'::jsonb
                       ) AS account_grants,
                       COALESCE(
                         (
                           SELECT string_agg(granted_account.name, '、'
                                             ORDER BY granted_account.name)
                           FROM auth_grants account_grant
                           JOIN content_accounts granted_account
                             ON granted_account.tenant_id = account_grant.tenant_id
                            AND granted_account.id = account_grant.account_id
                            AND granted_account.carrier_of_account_id IS NULL
                           WHERE account_grant.tenant_id = u.tenant_id
                             AND account_grant.user_id = u.id
                             AND account_grant.enabled = true
                         ),
                         ''
                       ) AS publishing_accounts
                FROM users u
                JOIN organizations o ON o.id = u.organization_id AND o.tenant_id = u.tenant_id
                LEFT JOIN user_credentials credential
                  ON credential.tenant_id = u.tenant_id AND credential.user_id = u.id
                WHERE u.tenant_id = %s
                ORDER BY u.display_name
                """,
                (scope.tenant_id,),
            )
            rows = cursor.fetchall()
        return [
            {
                "id": str(row["id"]),
                "display_name": str(row["display_name"]),
                "username": (str(row["username"]) if row["username"] is not None else ""),
                "organization": str(row["organization"]),
                "organization_id": str(row["organization_id"]),
                "publishing_accounts": str(row["publishing_accounts"]),
                "entry_type": str(row["entry_kind"]),
                "enabled": bool(row["enabled"]),
                "capabilities": {
                    "content": bool(row["account_grants"]),
                    "display": bool(row["can_use_display"]),
                },
                "manages_tenant": bool(row["manages_tenant"]),
                "maintains_organization_materials": bool(row["maintains_organization_materials"]),
                "account_grants": (row["account_grants"] if isinstance(row["account_grants"], list) else []),
            }
            for row in rows
        ]

    def management_accounts(self, scope: TenantManagementScope) -> list[dict[str, object]]:
        with self._management_tx(scope) as cursor:
            cursor.execute(
                """
                SELECT root.id, root.name, root.enabled, root.business_data_kind,
                       root.control_organization_source,
                       control_organization.id AS control_organization_id,
                       control_organization.name AS control_organization,
                       role.name AS content_role, role.voice_boundary,
                       role.speaker_kind,
                       profile.id AS profile_id, profile.version AS profile_version,
                       profile.identity_position, profile.authority_boundary,
                       profile.audience_relationship, profile.content_territories,
                       profile.default_production_conditions,
                       COALESCE(
                           (
                               SELECT jsonb_agg(
                                   jsonb_build_object(
                                       'id', operator.id,
                                       'display_name', operator.display_name
                                   )
                                   ORDER BY operator.display_name
                               )
                               FROM auth_grants operator_grant
                               JOIN users operator
                                 ON operator.id = operator_grant.user_id
                                AND operator.tenant_id = operator_grant.tenant_id
                                AND operator.enabled = true
                                AND operator.entry_kind = 'tenant_user'
                               WHERE operator_grant.tenant_id = root.tenant_id
                                 AND operator_grant.account_id = root.id
                                 AND operator_grant.enabled = true
                           ),
                           '[]'::jsonb
                       ) AS operators,
                       COALESCE(
                           (
                               SELECT jsonb_agg(
                                   jsonb_build_object(
                                       'id', physical.id,
                                       'name', physical.name,
                                       'channel', physical.channel,
                                       'enabled',
                                           physical.platform_enabled
                                           AND (
                                               physical.carrier_of_account_id
                                                   IS NULL
                                               OR physical.enabled
                                           )
                                   )
                                   ORDER BY
                                     CASE WHEN physical.id = root.id THEN 0 ELSE 1 END,
                                     physical.channel
                               )
                               FROM content_accounts physical
                               WHERE physical.tenant_id = root.tenant_id
                                 AND physical.brand_id = root.brand_id
                                 AND (
                                   physical.id = root.id
                                   OR physical.carrier_of_account_id = root.id
                                 )
                           ),
                           '[]'::jsonb
                       ) AS physical_targets,
                       (
                           SELECT count(*)
                           FROM content_accounts carrier
                           WHERE carrier.tenant_id = root.tenant_id
                             AND carrier.carrier_of_account_id = root.id
                             AND carrier.enabled = true
                             AND carrier.platform_enabled = true
                       ) AS carrier_count
                FROM content_accounts root
                JOIN account_content_roles account_role
                  ON account_role.tenant_id = root.tenant_id
                 AND account_role.account_id = root.id
                JOIN content_roles role
                  ON role.id = account_role.content_role_id
                 AND role.tenant_id = account_role.tenant_id
                LEFT JOIN organizations control_organization
                  ON control_organization.tenant_id = root.tenant_id
                 AND control_organization.id = root.control_organization_id
                LEFT JOIN account_expression_profile_versions profile
                  ON profile.tenant_id = root.tenant_id
                 AND profile.account_id = root.id
                 AND profile.id = root.current_expression_profile_id
                WHERE root.tenant_id = %s AND root.brand_id = %s
                  AND root.carrier_of_account_id IS NULL
                ORDER BY root.name
                """,
                (scope.tenant_id, scope.brand_id),
            )
            rows = cursor.fetchall()
        identities: list[dict[str, object]] = []
        for row in rows:
            raw_targets = row["physical_targets"]
            physical_targets = raw_targets if isinstance(raw_targets, list) else []
            profile = (
                {
                    "id": str(row["profile_id"]),
                    "version": self._integer(row["profile_version"]),
                    "segments": {
                        "identity_position": str(row["identity_position"]),
                        "authority_boundary": str(row["authority_boundary"]),
                        "audience_relationship": str(row["audience_relationship"]),
                        "content_territories": str(row["content_territories"]),
                        "default_production_conditions": str(row["default_production_conditions"]),
                    },
                }
                if row["profile_id"] is not None
                else None
            )
            identities.append(
                {
                    "id": str(row["id"]),
                    "name": str(row["name"]),
                    "enabled": bool(row["enabled"]),
                    "control_organization": (
                        {
                            "id": str(row["control_organization_id"]),
                            "name": str(row["control_organization"]),
                            "source": str(row["control_organization_source"]),
                        }
                        if row["control_organization_id"] is not None
                        else None
                    ),
                    "content_role": {
                        "name": str(row["content_role"]),
                        "authority_boundary": str(row["voice_boundary"]),
                        "speaker_kind": str(row["speaker_kind"]),
                    },
                    "profile": profile,
                    "operators": (row["operators"] if isinstance(row["operators"], list) else []),
                    "platform_targets": self._platform_targets(physical_targets),
                    "carrier_count": self._integer(row["carrier_count"]),
                    "business_data_kind": str(row["business_data_kind"]),
                }
            )
        return identities

    def team_usage(
        self,
        scope: TenantManagementScope,
        window_days: int,
    ) -> dict[str, object]:
        if window_days not in {7, 30}:
            raise DomainError("团队使用情况只支持查看近 7 日或近 30 日。")
        with self._management_tx(scope) as cursor:
            cursor.execute(
                """
                SELECT
                  count(*) AS registered,
                  count(*) FILTER (WHERE credential.password_hash IS NOT NULL) AS activated,
                  count(*) FILTER (WHERE user_record.enabled) AS enabled,
                  count(*) FILTER (WHERE NOT user_record.enabled) AS disabled,
                  count(*) FILTER (
                    WHERE login_usage.last_login_at >= now() - (%s * interval '1 day')
                  ) AS logged_in,
                  count(*) FILTER (
                    WHERE product_usage.last_product_action_at >=
                          now() - (%s * interval '1 day')
                  ) AS product_active
                FROM users user_record
                LEFT JOIN user_credentials credential
                  ON credential.tenant_id = user_record.tenant_id
                 AND credential.user_id = user_record.id
                LEFT JOIN LATERAL (
                  SELECT max(session_record.issued_at) AS last_login_at
                  FROM tenant_sessions session_record
                  WHERE session_record.tenant_id = user_record.tenant_id
                    AND session_record.user_id = user_record.id
                ) login_usage ON true
                LEFT JOIN LATERAL (
                  SELECT max(value.used_at) AS last_product_action_at
                  FROM (
                    SELECT max(task.created_at) AS used_at
                    FROM business_tasks task
                    WHERE task.tenant_id = user_record.tenant_id
                      AND task.created_by = user_record.id
                    UNION ALL
                    SELECT max(display_task.created_at)
                    FROM display_tasks display_task
                    WHERE display_task.tenant_id = user_record.tenant_id
                      AND display_task.created_by = user_record.id
                    UNION ALL
                    SELECT max(event.created_at)
                    FROM activity_events event
                    WHERE event.tenant_id = user_record.tenant_id
                      AND event.actor_id = user_record.id
                      AND event.event_type = 'content.conversation'
                  ) value
                ) product_usage ON true
                WHERE user_record.tenant_id = %s
                """,
                (window_days, window_days, scope.tenant_id),
            )
            membership = self._one(cursor, "无法读取团队成员汇总")
            cursor.execute(
                """
                SELECT user_record.id, user_record.display_name,
                       user_record.entry_kind, user_record.enabled,
                       login_usage.last_login_at,
                       product_usage.last_product_action_at,
                       COALESCE(content_usage.attempts, 0) AS content_attempts,
                       COALESCE(display_usage.attempts, 0) AS display_attempts
                FROM users user_record
                LEFT JOIN LATERAL (
                  SELECT max(session_record.issued_at) AS last_login_at
                  FROM tenant_sessions session_record
                  WHERE session_record.tenant_id = user_record.tenant_id
                    AND session_record.user_id = user_record.id
                ) login_usage ON true
                LEFT JOIN LATERAL (
                  SELECT max(value.used_at) AS last_product_action_at
                  FROM (
                    SELECT max(task.created_at) AS used_at
                    FROM business_tasks task
                    WHERE task.tenant_id = user_record.tenant_id
                      AND task.created_by = user_record.id
                    UNION ALL
                    SELECT max(display_task.created_at)
                    FROM display_tasks display_task
                    WHERE display_task.tenant_id = user_record.tenant_id
                      AND display_task.created_by = user_record.id
                    UNION ALL
                    SELECT max(event.created_at)
                    FROM activity_events event
                    WHERE event.tenant_id = user_record.tenant_id
                      AND event.actor_id = user_record.id
                      AND event.event_type = 'content.conversation'
                  ) value
                ) product_usage ON true
                LEFT JOIN LATERAL (
                  SELECT count(*) AS attempts
                  FROM business_tasks task
                  WHERE task.tenant_id = user_record.tenant_id
                    AND task.created_by = user_record.id
                    AND task.created_at >= now() - (%s * interval '1 day')
                ) content_usage ON true
                LEFT JOIN LATERAL (
                  SELECT count(*) AS attempts
                  FROM display_tasks task
                  WHERE task.tenant_id = user_record.tenant_id
                    AND task.created_by = user_record.id
                    AND task.created_at >= now() - (%s * interval '1 day')
                ) display_usage ON true
                WHERE user_record.tenant_id = %s
                ORDER BY product_usage.last_product_action_at DESC NULLS LAST,
                         login_usage.last_login_at DESC NULLS LAST,
                         user_record.display_name
                """,
                (window_days, window_days, scope.tenant_id),
            )
            member_rows = cursor.fetchall()
            cursor.execute(
                """
                SELECT
                  (SELECT count(*) FROM generation_runs run
                   WHERE run.tenant_id = %s
                     AND run.started_at >= now() - (%s * interval '1 day')) AS content_attempts,
                  (SELECT count(*) FROM generation_runs run
                   WHERE run.tenant_id = %s AND run.status = 'succeeded'
                     AND run.started_at >= now() - (%s * interval '1 day')) AS content_successes,
                  (SELECT count(*) FROM generation_runs run
                   WHERE run.tenant_id = %s AND run.status = 'failed'
                     AND run.started_at >= now() - (%s * interval '1 day')) AS content_failures,
                  (SELECT count(*) FROM content_versions version
                   WHERE version.tenant_id = %s AND version.version_number > 1
                     AND version.created_at >=
                         now() - (%s * interval '1 day')) AS revisions,
                  (SELECT count(*) FROM content_versions version
                   WHERE version.tenant_id = %s AND version.version_number = 1
                     AND version.created_at >=
                         now() - (%s * interval '1 day')) AS first_generations,
                  (SELECT count(*) FROM business_tasks task
                   WHERE task.tenant_id = %s AND task.series_position > 1
                     AND task.created_at >= now() - (%s * interval '1 day')) AS series_continuations,
                  (SELECT count(*) FROM display_generation_runs run
                   WHERE run.tenant_id = %s
                     AND run.started_at >= now() - (%s * interval '1 day')) AS display_attempts,
                  (SELECT count(*) FROM display_generation_runs run
                   WHERE run.tenant_id = %s AND run.status = 'succeeded'
                     AND run.started_at >= now() - (%s * interval '1 day')) AS display_successes,
                  (SELECT count(*) FROM display_generation_runs run
                   WHERE run.tenant_id = %s AND run.status = 'failed'
                     AND run.started_at >= now() - (%s * interval '1 day')) AS display_failures,
                  (SELECT count(*) FROM activity_events event
                   WHERE event.tenant_id = %s
                     AND event.event_type IN (
                       'content.rate_limited',
                       'display.rate_limited',
                       'request.rate_limited'
                     )
                     AND event.created_at >= now() - (%s * interval '1 day')) AS rate_limited,
                  (SELECT count(*) FROM activity_events event
                   WHERE event.tenant_id = %s
                     AND event.event_type = 'content.conversation'
                     AND event.created_at >= now() - (%s * interval '1 day')) AS conversations,
                  (SELECT count(*) FROM display_artifact_versions version
                   WHERE version.tenant_id = %s AND version.version_number = 1
                     AND version.created_at >= now() - (%s * interval '1 day')) AS dm01_plans,
                  (
                    SELECT COALESCE(sum(tokens), 0)::bigint
                    FROM (
                      SELECT CASE
                        WHEN run.provider_usage ->> 'total_tokens' ~ '^[0-9]+$'
                        THEN (run.provider_usage ->> 'total_tokens')::bigint
                        ELSE 0
                      END AS tokens
                      FROM generation_runs run
                      WHERE run.tenant_id = %s
                        AND run.started_at >= now() - (%s * interval '1 day')
                      UNION ALL
                      SELECT CASE
                        WHEN run.provider_usage ->> 'total_tokens' ~ '^[0-9]+$'
                        THEN (run.provider_usage ->> 'total_tokens')::bigint
                        ELSE 0
                      END
                      FROM display_generation_runs run
                      WHERE run.tenant_id = %s
                        AND run.started_at >= now() - (%s * interval '1 day')
                    ) recorded
                  ) AS recorded_tokens
                """,
                (
                    scope.tenant_id,
                    window_days,
                    scope.tenant_id,
                    window_days,
                    scope.tenant_id,
                    window_days,
                    scope.tenant_id,
                    window_days,
                    scope.tenant_id,
                    window_days,
                    scope.tenant_id,
                    window_days,
                    scope.tenant_id,
                    window_days,
                    scope.tenant_id,
                    window_days,
                    scope.tenant_id,
                    window_days,
                    scope.tenant_id,
                    window_days,
                    scope.tenant_id,
                    window_days,
                    scope.tenant_id,
                    window_days,
                    scope.tenant_id,
                    window_days,
                    scope.tenant_id,
                    window_days,
                ),
            )
            activity = self._one(cursor, "无法读取团队使用汇总")
            cursor.execute(
                """
                SELECT root.id, root.name, count(*) AS attempts
                FROM business_tasks task
                JOIN content_accounts root
                  ON root.tenant_id = task.tenant_id
                 AND root.id = task.logical_account_id
                WHERE task.tenant_id = %s
                  AND task.created_at >= now() - (%s * interval '1 day')
                GROUP BY root.id, root.name
                ORDER BY attempts DESC, root.name
                """,
                (scope.tenant_id, window_days),
            )
            account_rows = cursor.fetchall()
            cursor.execute(
                """
                SELECT
                  CASE
                    WHEN account.channel = '抖音' AND task.media_format = 'video'
                      THEN 'douyin_video'
                    WHEN account.channel = '小红书' AND task.media_format = 'graphic'
                      THEN 'xiaohongshu_graphic'
                    WHEN account.channel = '小红书' AND task.media_format = 'video'
                      THEN 'xiaohongshu_video'
                    WHEN account.channel = '微信视频号' AND task.media_format = 'video'
                      THEN 'wechat_channels_video'
                    ELSE 'other'
                  END AS target,
                  count(*) AS attempts
                FROM business_tasks task
                JOIN content_accounts account
                  ON account.tenant_id = task.tenant_id
                 AND account.id = task.account_id
                WHERE task.tenant_id = %s
                  AND task.created_at >= now() - (%s * interval '1 day')
                GROUP BY target
                ORDER BY attempts DESC, target
                """,
                (scope.tenant_id, window_days),
            )
            platform_rows = cursor.fetchall()
        return {
            "window_days": window_days,
            "members": {
                "registered": self._integer(membership["registered"]),
                "activated": self._integer(membership["activated"]),
                "enabled": self._integer(membership["enabled"]),
                "disabled": self._integer(membership["disabled"]),
                "logged_in": self._integer(membership["logged_in"]),
                "product_active": self._integer(membership["product_active"]),
                "active": self._integer(membership["product_active"]),
                "items": [
                    {
                        "id": str(row["id"]),
                        "display_name": str(row["display_name"]),
                        "entry_type": str(row["entry_kind"]),
                        "enabled": bool(row["enabled"]),
                        "last_login_at": (
                            self._time(row["last_login_at"])
                            if row["last_login_at"] is not None
                            else None
                        ),
                        "last_product_action_at": (
                            self._time(row["last_product_action_at"])
                            if row["last_product_action_at"] is not None
                            else None
                        ),
                        "last_used_at": (
                            self._time(row["last_product_action_at"])
                            if row["last_product_action_at"] is not None
                            else (
                                self._time(row["last_login_at"])
                                if row["last_login_at"] is not None
                                else None
                            )
                        ),
                        "content_attempts": self._integer(row["content_attempts"]),
                        "display_attempts": self._integer(row["display_attempts"]),
                    }
                    for row in member_rows
                ],
            },
            "activity": {
                key: self._integer(activity[key])
                for key in (
                    "content_attempts",
                    "content_successes",
                    "content_failures",
                    "conversations",
                    "first_generations",
                    "revisions",
                    "series_continuations",
                    "dm01_plans",
                    "display_attempts",
                    "display_successes",
                    "display_failures",
                    "rate_limited",
                )
            }
            | {
                "successful_runs": (
                    self._integer(activity["content_successes"])
                    + self._integer(activity["display_successes"])
                ),
                "failed_runs": (
                    self._integer(activity["content_failures"])
                    + self._integer(activity["display_failures"])
                ),
            },
            "provider_usage": {
                "label": "已记录模型用量",
                "total_tokens": self._integer(activity["recorded_tokens"]),
                "is_complete_billing_total": False,
            },
            "distribution": {
                "publishing_identities": [
                    {
                        "id": str(row["id"]),
                        "name": str(row["name"]),
                        "attempts": self._integer(row["attempts"]),
                    }
                    for row in account_rows
                ],
                "platforms": [
                    {
                        "target": str(row["target"]),
                        "attempts": self._integer(row["attempts"]),
                    }
                    for row in platform_rows
                ],
            },
        }

    def management_products(self, scope: TenantManagementScope) -> list[dict[str, object]]:
        with self._management_tx(scope) as cursor:
            cursor.execute(
                """
                SELECT product.id, product.sku, product.display_name, product.facts,
                       product.source_kind, product.source_note, product.fact_version,
                       product.applicability, product.status,
                       product.visibility_scope, product.current_version_id,
                       person.display_name AS updated_by, product.updated_at,
                       COALESCE(
                         (
                           SELECT jsonb_agg(
                             jsonb_build_object(
                               'id', organization.id,
                               'name', organization.name,
                               'level', organization.organization_level
                             )
                             ORDER BY organization.name
                           )
                           FROM brand_product_scope_organizations product_scope
                           JOIN organizations organization
                             ON organization.tenant_id = product_scope.tenant_id
                            AND organization.id = product_scope.organization_id
                           WHERE product_scope.tenant_id = product.tenant_id
                             AND product_scope.product_id = product.id
                         ),
                         '[]'::jsonb
                       ) AS scope_organizations
                FROM brand_products product
                LEFT JOIN users person
                  ON person.id = product.updated_by AND person.tenant_id = product.tenant_id
                WHERE product.tenant_id = %s AND product.brand_id = %s
                ORDER BY product.updated_at DESC, product.sku
                """,
                (scope.tenant_id, scope.brand_id),
            )
            rows = cursor.fetchall()
        return [
            {
                "id": str(row["id"]),
                "sku": str(row["sku"]),
                "display_name": str(row["display_name"]),
                "facts": row["facts"] if isinstance(row["facts"], dict) else {},
                "source_kind": str(row["source_kind"]),
                "source_note": str(row["source_note"]),
                "fact_version": self._integer(row["fact_version"]),
                "applicability": str(row["applicability"]),
                "status": str(row["status"]),
                "current_version_id": (
                    str(row["current_version_id"])
                    if row["current_version_id"] is not None
                    else None
                ),
                "visibility_scope": str(row["visibility_scope"]),
                "scope_organizations": (
                    row["scope_organizations"] if isinstance(row["scope_organizations"], list) else []
                ),
                "updated_by": (str(row["updated_by"]) if row["updated_by"] is not None else None),
                "updated_at": self._time(row["updated_at"]),
            }
            for row in rows
        ]

    def management_organization_materials(
        self,
        scope: TenantManagementScope,
    ) -> list[dict[str, object]]:
        with self._management_tx(scope) as cursor:
            cursor.execute(
                """
                SELECT material.id, material.title, material.media_type,
                       material.created_at, material.status,
                       material.original_filename, material.byte_size,
                       material.reference_note, material.reference_version,
                       material.visibility_scope, material.current_version_id,
                       organization.id AS organization_id,
                       organization.name AS organization,
                       COALESCE(
                         (
                           SELECT jsonb_agg(
                             jsonb_build_object(
                               'id', scoped_organization.id,
                               'name', scoped_organization.name,
                               'level', scoped_organization.organization_level
                             )
                             ORDER BY scoped_organization.name
                           )
                           FROM material_asset_scope_organizations material_scope
                           JOIN organizations scoped_organization
                             ON scoped_organization.tenant_id = material_scope.tenant_id
                            AND scoped_organization.id = material_scope.organization_id
                           WHERE material_scope.tenant_id = material.tenant_id
                             AND material_scope.asset_id = material.id
                         ),
                         '[]'::jsonb
                       ) AS scope_organizations
                FROM material_assets material
                JOIN organizations organization
                  ON organization.id = material.owner_organization_id
                 AND organization.tenant_id = material.tenant_id
                WHERE material.tenant_id = %s
                  AND material.brand_id = %s
                  AND material.scope = 'organization'
                ORDER BY material.created_at DESC
                """,
                (scope.tenant_id, scope.brand_id),
            )
            rows = cursor.fetchall()
        return [
            {
                "id": str(row["id"]),
                "title": str(row["title"]),
                "media_type": str(row["media_type"]),
                "created_at": self._time(row["created_at"]),
                "status": str(row["status"]),
                "current_version_id": (
                    str(row["current_version_id"])
                    if row["current_version_id"] is not None
                    else None
                ),
                "original_filename": str(row["original_filename"]),
                "byte_size": self._integer(row["byte_size"]),
                "reference_note": str(row["reference_note"]),
                "reference_version": self._integer(row["reference_version"]),
                "visibility_scope": str(row["visibility_scope"]),
                "scope_organizations": (
                    row["scope_organizations"] if isinstance(row["scope_organizations"], list) else []
                ),
                "organization_id": str(row["organization_id"]),
                "organization": str(row["organization"]),
            }
            for row in rows
        ]

    def brand_library_entries(
        self,
        scope: TenantManagementScope,
    ) -> list[dict[str, object]]:
        with self._management_tx(scope) as cursor:
            cursor.execute(
                """
                SELECT entry.id, entry.category, entry.title, entry.source_note,
                       entry.content, entry.version, entry.status,
                       entry.visibility_scope, entry.updated_at,
                       entry.current_version_id,
                       person.display_name AS updated_by,
                       COALESCE(
                         (
                           SELECT jsonb_agg(
                             jsonb_build_object(
                               'id', organization.id,
                               'name', organization.name,
                               'level', organization.organization_level
                             )
                             ORDER BY organization.name
                           )
                           FROM brand_library_entry_organizations entry_scope
                           JOIN organizations organization
                             ON organization.tenant_id = entry_scope.tenant_id
                            AND organization.id = entry_scope.organization_id
                           WHERE entry_scope.tenant_id = entry.tenant_id
                             AND entry_scope.entry_id = entry.id
                         ),
                         '[]'::jsonb
                       ) AS scope_organizations
                FROM brand_library_entries entry
                LEFT JOIN users person
                  ON person.tenant_id = entry.tenant_id
                 AND person.id = entry.updated_by
                WHERE entry.tenant_id = %s AND entry.brand_id = %s
                ORDER BY entry.updated_at DESC, entry.title
                """,
                (scope.tenant_id, scope.brand_id),
            )
            rows = cursor.fetchall()
        return [
            {
                "id": str(row["id"]),
                "category": str(row["category"]),
                "title": str(row["title"]),
                "source_note": str(row["source_note"]),
                "content": str(row["content"]),
                "version": str(row["version"]),
                "status": str(row["status"]),
                "current_version_id": (
                    str(row["current_version_id"])
                    if row["current_version_id"] is not None
                    else None
                ),
                "visibility_scope": str(row["visibility_scope"]),
                "visibility_label": self._visibility_label(
                    str(row["visibility_scope"]),
                    row["scope_organizations"],
                ),
                "scope_organizations": (
                    row["scope_organizations"] if isinstance(row["scope_organizations"], list) else []
                ),
                "updated_by": (str(row["updated_by"]) if row["updated_by"] is not None else None),
                "updated_at": self._time(row["updated_at"]),
                "impact": self._library_impact(str(row["category"])),
            }
            for row in rows
        ]

    def create_brand_library_entry(
        self,
        scope: TenantManagementScope,
        category: str,
        title: str,
        source_note: str,
        content: str,
        version: str,
        status: str,
        visibility_scope: str,
        organization_ids: tuple[UUID, ...],
    ) -> dict[str, object]:
        entry_id = uuid4()
        version_id = uuid4()
        with self._management_tx(scope) as cursor:
            organizations = self._validated_scope_organizations(
                cursor,
                scope.tenant_id,
                visibility_scope,
                organization_ids,
                "资料",
            )
            cursor.execute(
                """
                INSERT INTO brand_library_entries
                  (id, tenant_id, brand_id, category, title, source_note,
                   content, version, status, visibility_scope, updated_by, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                RETURNING updated_at
                """,
                (
                    entry_id,
                    scope.tenant_id,
                    scope.brand_id,
                    category,
                    title,
                    source_note,
                    content,
                    version,
                    status,
                    visibility_scope,
                    scope.user_id,
                ),
            )
            row = self._one(cursor, "品牌资料没有保存成功")
            for organization in organizations:
                cursor.execute(
                    """
                    INSERT INTO brand_library_entry_organizations
                      (id, entry_id, tenant_id, organization_id)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (uuid4(), entry_id, scope.tenant_id, organization["id"]),
                )
            cursor.execute(
                """
                INSERT INTO brand_library_entry_versions
                    (id, tenant_id, brand_id, entry_id, version_number,
                     version_label, category, title, source_note, content,
                     visibility_scope, scope_organization_ids, created_by)
                VALUES (%s, %s, %s, %s, 1, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    version_id,
                    scope.tenant_id,
                    scope.brand_id,
                    entry_id,
                    version,
                    category,
                    title,
                    source_note,
                    content,
                    visibility_scope,
                    list(organization_ids),
                    scope.user_id,
                ),
            )
            cursor.execute(
                """
                UPDATE brand_library_entries
                   SET current_version_id = %s
                 WHERE tenant_id = %s AND id = %s
                """,
                (version_id, scope.tenant_id, entry_id),
            )
            self._event(
                cursor,
                scope,
                "brand_library.entry_saved",
                "brand_library_entry",
                entry_id,
            )
        scope_organizations = [
            {
                "id": str(organization["id"]),
                "name": str(organization["name"]),
                "level": str(organization["organization_level"]),
            }
            for organization in organizations
        ]
        return {
            "id": str(entry_id),
            "category": category,
            "title": title,
            "source_note": source_note,
            "content": content,
            "version": version,
            "version_number": 1,
            "current_version_id": str(version_id),
            "status": status,
            "visibility_scope": visibility_scope,
            "visibility_label": self._visibility_label(
                visibility_scope,
                scope_organizations,
            ),
            "scope_organizations": scope_organizations,
            "updated_by": str(scope.user_id),
            "updated_at": self._time(row["updated_at"]),
            "impact": self._library_impact(category),
        }

    def brand_library_entry_versions(
        self,
        scope: TenantManagementScope,
        entry_id: UUID,
    ) -> list[dict[str, object]]:
        with self._management_tx(scope) as cursor:
            cursor.execute(
                """
                SELECT version.id, version.version_number, version.version_label,
                       version.category, version.title, version.source_note,
                       version.content, version.visibility_scope,
                       version.scope_organization_ids, version.created_at,
                       entry.status,
                       entry.current_version_id = version.id AS is_current
                FROM brand_library_entry_versions version
                JOIN brand_library_entries entry
                  ON entry.tenant_id = version.tenant_id
                 AND entry.id = version.entry_id
                WHERE version.tenant_id = %s
                  AND version.brand_id = %s
                  AND version.entry_id = %s
                ORDER BY version.version_number DESC
                """,
                (scope.tenant_id, scope.brand_id, entry_id),
            )
            rows = cursor.fetchall()
        if not rows:
            raise DomainError("找不到当前品牌的资料版本")
        return [
            {
                "id": str(row["id"]),
                "entry_id": str(entry_id),
                "version_number": self._integer(row["version_number"]),
                "version": str(row["version_label"]),
                "category": str(row["category"]),
                "title": str(row["title"]),
                "source_note": str(row["source_note"]),
                "content": str(row["content"]),
                "visibility_scope": str(row["visibility_scope"]),
                "organization_ids": [
                    str(item)
                    for item in (
                        row["scope_organization_ids"]
                        if isinstance(row["scope_organization_ids"], list)
                        else []
                    )
                ],
                "status": str(row["status"]),
                "is_current": bool(row["is_current"]),
                "created_at": self._time(row["created_at"]),
            }
            for row in rows
        ]

    def save_brand_library_entry_version(
        self,
        scope: TenantManagementScope,
        entry_id: UUID,
        title: str,
        source_note: str,
        content: str,
        version_label: str,
        visibility_scope: str,
        organization_ids: tuple[UUID, ...],
    ) -> dict[str, object]:
        version_id = uuid4()
        with self._management_tx(scope) as cursor:
            cursor.execute(
                """
                SELECT category
                FROM brand_library_entries
                WHERE tenant_id = %s AND brand_id = %s AND id = %s
                FOR UPDATE
                """,
                (scope.tenant_id, scope.brand_id, entry_id),
            )
            entry = self._one(cursor, "找不到当前品牌可更新的资料")
            organizations = self._validated_scope_organizations(
                cursor,
                scope.tenant_id,
                visibility_scope,
                organization_ids,
                "资料",
            )
            cursor.execute(
                """
                SELECT COALESCE(max(version_number), 0) + 1 AS next_version
                FROM brand_library_entry_versions
                WHERE tenant_id = %s AND entry_id = %s
                """,
                (scope.tenant_id, entry_id),
            )
            version_number = self._integer(
                self._one(cursor, "无法计算资料版本")["next_version"]
            )
            cursor.execute(
                """
                INSERT INTO brand_library_entry_versions
                    (id, tenant_id, brand_id, entry_id, version_number,
                     version_label, category, title, source_note, content,
                     visibility_scope, scope_organization_ids, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    version_id,
                    scope.tenant_id,
                    scope.brand_id,
                    entry_id,
                    version_number,
                    version_label,
                    entry["category"],
                    title,
                    source_note,
                    content,
                    visibility_scope,
                    list(organization_ids),
                    scope.user_id,
                ),
            )
            cursor.execute(
                """
                UPDATE brand_library_entries
                   SET title = %s, source_note = %s, content = %s,
                       version = %s, visibility_scope = %s,
                       status = 'active', updated_by = %s,
                       updated_at = now(), current_version_id = %s
                 WHERE tenant_id = %s AND brand_id = %s AND id = %s
                RETURNING updated_at
                """,
                (
                    title,
                    source_note,
                    content,
                    version_label,
                    visibility_scope,
                    scope.user_id,
                    version_id,
                    scope.tenant_id,
                    scope.brand_id,
                    entry_id,
                ),
            )
            saved = self._one(cursor, "品牌资料新版本没有保存成功")
            cursor.execute(
                """
                DELETE FROM brand_library_entry_organizations
                WHERE tenant_id = %s AND entry_id = %s
                """,
                (scope.tenant_id, entry_id),
            )
            for organization in organizations:
                cursor.execute(
                    """
                    INSERT INTO brand_library_entry_organizations
                        (id, entry_id, tenant_id, organization_id)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        uuid4(),
                        entry_id,
                        scope.tenant_id,
                        organization["id"],
                    ),
                )
            self._event(
                cursor,
                scope,
                "brand_library.version_saved",
                "brand_library_entry",
                entry_id,
            )
        return {
            "id": str(entry_id),
            "current_version_id": str(version_id),
            "version_number": version_number,
            "version": version_label,
            "title": title,
            "source_note": source_note,
            "content": content,
            "status": "active",
            "visibility_scope": visibility_scope,
            "scope_organizations": self._scope_projection(organizations),
            "updated_at": self._time(saved["updated_at"]),
        }

    def set_brand_library_entry_enabled(
        self,
        scope: TenantManagementScope,
        entry_id: UUID,
        enabled: bool,
    ) -> dict[str, object]:
        with self._management_tx(scope) as cursor:
            cursor.execute(
                """
                UPDATE brand_library_entries
                   SET status = %s, updated_by = %s, updated_at = now()
                 WHERE tenant_id = %s AND brand_id = %s AND id = %s
                RETURNING id, status, current_version_id, updated_at
                """,
                (
                    "active" if enabled else "retired",
                    scope.user_id,
                    scope.tenant_id,
                    scope.brand_id,
                    entry_id,
                ),
            )
            row = self._one(cursor, "找不到当前品牌可停用或恢复的资料")
            self._event(
                cursor,
                scope,
                "brand_library.restored" if enabled else "brand_library.retired",
                "brand_library_entry",
                entry_id,
            )
        return {
            "id": str(row["id"]),
            "status": str(row["status"]),
            "current_version_id": (
                str(row["current_version_id"])
                if row["current_version_id"] is not None
                else None
            ),
            "updated_at": self._time(row["updated_at"]),
        }

    def create_management_organization_material(
        self,
        scope: TenantManagementScope,
        organization_id: UUID,
        asset_id: UUID,
        title: str,
        media_type: str,
        object_key: str,
        byte_size: int,
        original_filename: str,
        checksum_sha256: str,
        reference_note: str,
        visibility_scope: str = "organizations",
        organization_ids: tuple[UUID, ...] = (),
    ) -> dict[str, object]:
        version_id = uuid4()
        with self._management_tx(scope) as cursor:
            cursor.execute(
                "SELECT name, organization_level FROM organizations WHERE tenant_id = %s AND id = %s",
                (scope.tenant_id, organization_id),
            )
            organization = self._one(cursor, "只能把组织素材保存到当前租户的团队")
            scoped_organizations = self._validated_scope_organizations(
                cursor,
                scope.tenant_id,
                visibility_scope,
                organization_ids,
                "素材",
            )
            cursor.execute(
                """
                INSERT INTO material_assets
                    (id, tenant_id, brand_id, scope, owner_user_id,
                     owner_organization_id, title, media_type, object_key,
                     byte_size, original_filename, checksum_sha256, reference_note,
                     visibility_scope)
                VALUES (%s, %s, %s, 'organization', NULL, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s)
                RETURNING id, title, media_type, created_at, status,
                          original_filename, byte_size, reference_note
                """,
                (
                    asset_id,
                    scope.tenant_id,
                    scope.brand_id,
                    organization_id,
                    title,
                    media_type,
                    object_key,
                    byte_size,
                    original_filename,
                    checksum_sha256,
                    reference_note,
                    visibility_scope,
                ),
            )
            row = self._one(cursor, "组织素材没有保存成功")
            for scoped_organization in scoped_organizations:
                cursor.execute(
                    """
                    INSERT INTO material_asset_scope_organizations
                      (id, asset_id, tenant_id, organization_id)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        uuid4(),
                        asset_id,
                        scope.tenant_id,
                        scoped_organization["id"],
                    ),
                )
            cursor.execute(
                """
                INSERT INTO material_asset_versions
                    (id, tenant_id, brand_id, asset_id, version_number,
                     title, reference_note, visibility_scope,
                     scope_organization_ids, source_filename,
                     source_checksum_sha256, created_by)
                VALUES (%s, %s, %s, %s, 1, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    version_id,
                    scope.tenant_id,
                    scope.brand_id,
                    asset_id,
                    title,
                    reference_note,
                    visibility_scope,
                    list(organization_ids),
                    original_filename,
                    checksum_sha256,
                    scope.user_id,
                ),
            )
            cursor.execute(
                """
                UPDATE material_assets
                   SET current_version_id = %s
                 WHERE tenant_id = %s AND id = %s
                """,
                (version_id, scope.tenant_id, asset_id),
            )
            cursor.execute(
                """
                INSERT INTO activity_events
                    (id, tenant_id, actor_id, event_type, entity_type, entity_id)
                VALUES (%s, %s, %s, 'organization_material.created',
                        'material_asset', %s)
                """,
                (uuid4(), scope.tenant_id, scope.user_id, asset_id),
            )
        return {
            "id": str(row["id"]),
            "title": str(row["title"]),
            "media_type": str(row["media_type"]),
            "created_at": self._time(row["created_at"]),
            "status": str(row["status"]),
            "current_version_id": str(version_id),
            "original_filename": str(row["original_filename"]),
            "byte_size": self._integer(row["byte_size"]),
            "reference_note": str(row["reference_note"]),
            "visibility_scope": visibility_scope,
            "visibility_label": self._visibility_label(
                visibility_scope,
                scoped_organizations,
            ),
            "scope_organizations": [
                {
                    "id": str(scoped_organization["id"]),
                    "name": str(scoped_organization["name"]),
                    "level": str(scoped_organization["organization_level"]),
                }
                for scoped_organization in scoped_organizations
            ],
            "organization_id": str(organization_id),
            "organization": str(organization["name"]),
        }

    def management_material_versions(
        self,
        scope: TenantManagementScope,
        asset_id: UUID,
    ) -> list[dict[str, object]]:
        with self._management_tx(scope) as cursor:
            cursor.execute(
                """
                SELECT version.id, version.version_number, version.title,
                       version.reference_note, version.visibility_scope,
                       version.scope_organization_ids, version.source_filename,
                       version.source_checksum_sha256, version.created_at,
                       asset.current_version_id = version.id AS is_current,
                       asset.status
                FROM material_asset_versions version
                JOIN material_assets asset
                  ON asset.tenant_id = version.tenant_id
                 AND asset.id = version.asset_id
                WHERE version.tenant_id = %s
                  AND version.brand_id = %s
                  AND version.asset_id = %s
                  AND asset.scope = 'organization'
                ORDER BY version.version_number DESC
                """,
                (scope.tenant_id, scope.brand_id, asset_id),
            )
            rows = cursor.fetchall()
        if not rows:
            raise DomainError("找不到当前品牌的组织素材版本")
        return [
            {
                "id": str(row["id"]),
                "asset_id": str(asset_id),
                "version": self._integer(row["version_number"]),
                "title": str(row["title"]),
                "reference_note": str(row["reference_note"]),
                "visibility_scope": str(row["visibility_scope"]),
                "organization_ids": [
                    str(item)
                    for item in (
                        row["scope_organization_ids"]
                        if isinstance(row["scope_organization_ids"], list)
                        else []
                    )
                ],
                "source_filename": str(row["source_filename"]),
                "source_checksum_sha256": str(row["source_checksum_sha256"]),
                "status": str(row["status"]),
                "is_current": bool(row["is_current"]),
                "created_at": self._time(row["created_at"]),
            }
            for row in rows
        ]

    def save_management_material_version(
        self,
        scope: TenantManagementScope,
        asset_id: UUID,
        title: str,
        reference_note: str,
        visibility_scope: str,
        organization_ids: tuple[UUID, ...],
    ) -> dict[str, object]:
        version_id = uuid4()
        with self._management_tx(scope) as cursor:
            cursor.execute(
                """
                SELECT original_filename, checksum_sha256
                FROM material_assets
                WHERE tenant_id = %s AND brand_id = %s AND id = %s
                  AND scope = 'organization'
                FOR UPDATE
                """,
                (scope.tenant_id, scope.brand_id, asset_id),
            )
            asset = self._one(cursor, "找不到当前品牌可更新的组织素材")
            organizations = self._validated_scope_organizations(
                cursor,
                scope.tenant_id,
                visibility_scope,
                organization_ids,
                "素材",
            )
            cursor.execute(
                """
                SELECT COALESCE(max(version_number), 0) + 1 AS next_version
                FROM material_asset_versions
                WHERE tenant_id = %s AND asset_id = %s
                """,
                (scope.tenant_id, asset_id),
            )
            version_number = self._integer(
                self._one(cursor, "无法计算素材版本")["next_version"]
            )
            cursor.execute(
                """
                INSERT INTO material_asset_versions
                    (id, tenant_id, brand_id, asset_id, version_number,
                     title, reference_note, visibility_scope,
                     scope_organization_ids, source_filename,
                     source_checksum_sha256, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    version_id,
                    scope.tenant_id,
                    scope.brand_id,
                    asset_id,
                    version_number,
                    title,
                    reference_note,
                    visibility_scope,
                    list(organization_ids),
                    asset["original_filename"],
                    asset["checksum_sha256"],
                    scope.user_id,
                ),
            )
            cursor.execute(
                """
                UPDATE material_assets
                   SET title = %s, reference_note = %s,
                       visibility_scope = %s, reference_version = %s,
                       current_version_id = %s, status = 'active'
                 WHERE tenant_id = %s AND brand_id = %s AND id = %s
                RETURNING created_at
                """,
                (
                    title,
                    reference_note,
                    visibility_scope,
                    version_number,
                    version_id,
                    scope.tenant_id,
                    scope.brand_id,
                    asset_id,
                ),
            )
            saved = self._one(cursor, "组织素材新版本没有保存成功")
            cursor.execute(
                """
                DELETE FROM material_asset_scope_organizations
                WHERE tenant_id = %s AND asset_id = %s
                """,
                (scope.tenant_id, asset_id),
            )
            for organization in organizations:
                cursor.execute(
                    """
                    INSERT INTO material_asset_scope_organizations
                        (id, asset_id, tenant_id, organization_id)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        uuid4(),
                        asset_id,
                        scope.tenant_id,
                        organization["id"],
                    ),
                )
            self._event(
                cursor,
                scope,
                "organization_material.version_saved",
                "material_asset",
                asset_id,
            )
        return {
            "id": str(asset_id),
            "current_version_id": str(version_id),
            "reference_version": version_number,
            "title": title,
            "reference_note": reference_note,
            "visibility_scope": visibility_scope,
            "scope_organizations": self._scope_projection(organizations),
            "status": "active",
            "created_at": self._time(saved["created_at"]),
        }

    def set_management_material_enabled(
        self,
        scope: TenantManagementScope,
        asset_id: UUID,
        enabled: bool,
    ) -> dict[str, object]:
        with self._management_tx(scope) as cursor:
            cursor.execute(
                """
                UPDATE material_assets
                   SET status = %s
                 WHERE tenant_id = %s AND brand_id = %s AND id = %s
                   AND scope = 'organization'
                   AND status IN ('active', 'inactive')
                RETURNING id, status, current_version_id, reference_version
                """,
                (
                    "active" if enabled else "inactive",
                    scope.tenant_id,
                    scope.brand_id,
                    asset_id,
                ),
            )
            row = self._one(cursor, "找不到当前品牌可停用或恢复的组织素材")
            self._event(
                cursor,
                scope,
                (
                    "organization_material.restored"
                    if enabled
                    else "organization_material.retired"
                ),
                "material_asset",
                asset_id,
            )
        return {
            "id": str(row["id"]),
            "status": str(row["status"]),
            "current_version_id": (
                str(row["current_version_id"])
                if row["current_version_id"] is not None
                else None
            ),
            "reference_version": self._integer(row["reference_version"]),
        }

    def request_management_material_deletion(
        self,
        scope: TenantManagementScope,
        asset_id: UUID,
    ) -> str:
        with self._management_tx(scope) as cursor:
            cursor.execute(
                """
                SELECT object_key FROM material_assets
                WHERE tenant_id = %s AND brand_id = %s AND id = %s
                  AND scope = 'organization'
                  AND status IN ('active', 'deletion_pending')
                """,
                (scope.tenant_id, scope.brand_id, asset_id),
            )
            row = self._one(cursor, "找不到当前品牌可移除的组织素材")
            cursor.execute(
                "UPDATE material_assets SET status = 'deletion_pending' WHERE tenant_id = %s AND id = %s",
                (scope.tenant_id, asset_id),
            )
            cursor.execute(
                """
                INSERT INTO activity_events
                    (id, tenant_id, actor_id, event_type, entity_type, entity_id)
                VALUES (%s, %s, %s, 'organization_material.deletion_requested',
                        'material_asset', %s)
                """,
                (uuid4(), scope.tenant_id, scope.user_id, asset_id),
            )
        return str(row["object_key"])

    def finalize_management_material_deletion(
        self,
        scope: TenantManagementScope,
        asset_id: UUID,
    ) -> None:
        with self._management_tx(scope) as cursor:
            cursor.execute(
                "DELETE FROM material_assets "
                "WHERE tenant_id = %s AND brand_id = %s AND id = %s "
                "AND scope = 'organization' AND status = 'deletion_pending'",
                (scope.tenant_id, scope.brand_id, asset_id),
            )
            if cursor.rowcount != 1:
                raise DomainError("素材删除状态已变化，请刷新后重试。")
            cursor.execute(
                """
                INSERT INTO activity_events
                    (id, tenant_id, actor_id, event_type, entity_type, entity_id)
                VALUES (%s, %s, %s, 'organization_material.deleted',
                        'material_asset', %s)
                """,
                (uuid4(), scope.tenant_id, scope.user_id, asset_id),
            )

    def management_demo_content_index(self, scope: TenantManagementScope) -> dict[str, object]:
        """Project the equal-depth fixture as a tenant-scoped, read-only acceptance index.

        This is deliberately a projection over the normal production objects.  It neither
        creates a milestone state store nor copies generated prose into a second persistence
        path.  FORCE RLS remains active for every query in the transaction.
        """
        with self._management_tx(scope) as cursor:
            cursor.execute(
                """
                SELECT account.id, account.name, account.channel,
                       role.name AS content_role, role.voice_boundary,
                       operator.id AS operator_id, operator.display_name AS operator_name,
                       credential.username,
                       profile.id AS profile_id, profile.version AS profile_version,
                       profile.identity_position, profile.authority_boundary,
                       profile.audience_relationship, profile.content_territories,
                       profile.default_production_conditions
                FROM content_accounts account
                JOIN account_content_roles account_role
                  ON account_role.tenant_id = account.tenant_id
                 AND account_role.account_id = account.id
                JOIN content_roles role
                  ON role.tenant_id = account_role.tenant_id
                 AND role.id = account_role.content_role_id
                LEFT JOIN account_expression_profile_versions profile
                  ON profile.tenant_id = account.tenant_id
                 AND profile.id = account.current_expression_profile_id
                JOIN LATERAL (
                    SELECT person.id, person.display_name
                    FROM auth_grants grant_record
                    JOIN users person
                      ON person.tenant_id = grant_record.tenant_id
                     AND person.id = grant_record.user_id
                     AND person.enabled = true
                    WHERE grant_record.tenant_id = account.tenant_id
                      AND grant_record.account_id = account.id
                      AND grant_record.enabled = true
                    ORDER BY person.id
                    LIMIT 1
                ) operator ON true
                LEFT JOIN user_credentials credential
                  ON credential.tenant_id = account.tenant_id
                 AND credential.user_id = operator.id
                WHERE account.tenant_id = %s
                  AND account.brand_id = %s
                  AND account.enabled = true
                  AND account.carrier_of_account_id IS NULL
                  AND account.business_data_kind = 'synthetic_business_fixture'
                ORDER BY account.name
                """,
                (scope.tenant_id, scope.brand_id),
            )
            identity_rows = cursor.fetchall()
            identities = [self._demo_identity_projection(cursor, scope, row) for row in identity_rows]

        return {
            "fixture_status": "ready" if len(identities) == 2 else "not_ready",
            "fixture_label": "等深模拟业务资料",
            "boundary": (
                "组织关系、账号画像、商品和内容均为演示资料；生产代码、正式数据库、"
                "租户隔离和模型调用路径按正式能力运行。它不代表真实员工、真实在售"
                "商品、真实门店经营、真实发布或市场结果。"
            ),
            "safe_entry": (
                "由租户管理员为对应演示操作者生成一次性重置链接；本人设置独立密码"
                "后进入内容工作台。系统不提供共享密码，也不连接任何内容平台。"
            ),
            "identities": identities,
        }

    def _demo_identity_projection(
        self,
        cursor: psycopg.Cursor[dict[str, object]],
        scope: TenantManagementScope,
        identity: dict[str, object],
    ) -> dict[str, object]:
        account_id = UUID(str(identity["id"]))
        cursor.execute(
            """
            SELECT series.id, series.title, series.premise, series.revision
            FROM content_series series
            WHERE series.tenant_id = %s
              AND series.brand_id = %s
              AND series.logical_account_id = %s
              AND series.title LIKE '%%M7-2B演示%%'
            ORDER BY series.created_at DESC
            LIMIT 1
            """,
            (scope.tenant_id, scope.brand_id, account_id),
        )
        series_row = cursor.fetchone()
        artifacts: list[dict[str, object]] = []
        series_code_prefix = "H" if str(identity["name"]) == "总部品牌内容运营演示账号" else "S"
        if series_row is not None:
            cursor.execute(
                """
                SELECT item.position, task.id AS task_id,
                       task.primary_content_product,
                       task.content_context_snapshot,
                       current_version.id AS current_version_id
                FROM content_series_items item
                JOIN business_tasks task
                  ON task.tenant_id = item.tenant_id
                 AND task.id = item.task_id
                JOIN content_items content_item
                  ON content_item.tenant_id = task.tenant_id
                 AND content_item.task_id = task.id
                JOIN content_versions current_version
                  ON current_version.tenant_id = content_item.tenant_id
                 AND current_version.task_id = content_item.task_id
                 AND current_version.version_number = content_item.current_version
                WHERE item.tenant_id = %s AND item.series_id = %s
                ORDER BY item.position
                """,
                (scope.tenant_id, series_row["id"]),
            )
            for artifact_row in cursor.fetchall():
                versions = self._demo_task_versions(cursor, scope, UUID(str(artifact_row["task_id"])))
                snapshot = artifact_row["content_context_snapshot"]
                prior_count = 0
                if isinstance(snapshot, dict):
                    series_context = snapshot.get("series_context")
                    if isinstance(series_context, dict):
                        prior_entries = series_context.get("prior_entries")
                        if isinstance(prior_entries, list):
                            prior_count = len(prior_entries)
                artifacts.append(
                    {
                        "position": self._integer(artifact_row["position"]),
                        "series_code": (f"{series_code_prefix}{self._integer(artifact_row['position'])}"),
                        "value": self._content_value_label(str(artifact_row["primary_content_product"])),
                        "prior_context_count": prior_count,
                        "current_version_id": str(artifact_row["current_version_id"]),
                        "versions": versions,
                    }
                )

        platform_versions = self._demo_platform_versions(cursor, scope, account_id, artifacts)
        profile = (
            {
                "version": self._integer(identity["profile_version"]),
                "segments": [
                    {"label": "表达身份", "body": str(identity["identity_position"])},
                    {"label": "权威边界", "body": str(identity["authority_boundary"])},
                    {
                        "label": "受众关系",
                        "body": str(identity["audience_relationship"]),
                    },
                    {"label": "内容领地", "body": str(identity["content_territories"])},
                    {
                        "label": "长期制作条件",
                        "body": str(identity["default_production_conditions"]),
                    },
                ],
            }
            if identity["profile_id"] is not None
            else None
        )
        return {
            "name": str(identity["name"]),
            "channel": str(identity["channel"]),
            "content_role": str(identity["content_role"]),
            "voice_boundary": str(identity["voice_boundary"]),
            "operator": {
                "id": str(identity["operator_id"]),
                "name": str(identity["operator_name"]),
                "username": (str(identity["username"]) if identity["username"] is not None else ""),
            },
            "profile": profile,
            "series": (
                {
                    "title": str(series_row["title"]),
                    "premise": str(series_row["premise"]),
                    "revision": self._integer(series_row["revision"]),
                    "artifacts": artifacts,
                }
                if series_row is not None
                else None
            ),
            "platform_versions": platform_versions,
        }

    def _demo_task_versions(
        self,
        cursor: psycopg.Cursor[dict[str, object]],
        scope: TenantManagementScope,
        task_id: UUID,
    ) -> list[dict[str, object]]:
        cursor.execute(
            """
            SELECT version.id, version.version_number, version.outline, version.body,
                   version.artifact_digest, version.version_audit_snapshot,
                   version.created_at, run.model, task.content_context_snapshot,
                   account.channel, task.media_format
            FROM content_versions version
            JOIN generation_runs run
              ON run.tenant_id = version.tenant_id AND run.id = version.run_id
            JOIN business_tasks task
              ON task.tenant_id = version.tenant_id AND task.id = version.task_id
            JOIN content_accounts account
              ON account.tenant_id = task.tenant_id AND account.id = task.account_id
            WHERE version.tenant_id = %s
              AND task.brand_id = %s
              AND version.task_id = %s
            ORDER BY version.version_number
            """,
            (scope.tenant_id, scope.brand_id, task_id),
        )
        return [self._demo_version(row) for row in cursor.fetchall()]

    def _demo_platform_versions(
        self,
        cursor: psycopg.Cursor[dict[str, object]],
        scope: TenantManagementScope,
        account_id: UUID,
        artifacts: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        source_versions: dict[str, tuple[dict[str, object], str]] = {}
        for artifact in artifacts:
            raw_versions = artifact.get("versions")
            if not isinstance(raw_versions, list):
                continue
            series_code = str(artifact.get("series_code") or "")
            for version in raw_versions:
                if isinstance(version, dict):
                    source_versions[str(version["version_id"])] = (
                        version,
                        series_code,
                    )
        if not source_versions:
            return []
        cursor.execute(
            """
            SELECT version.id, version.version_number, version.outline, version.body,
                   version.artifact_digest, version.version_audit_snapshot,
                   version.created_at, run.model, task.content_context_snapshot,
                   account.channel, task.media_format, task.parent_version_id
            FROM content_accounts account
            JOIN business_tasks task
              ON task.tenant_id = account.tenant_id AND task.account_id = account.id
            JOIN content_items item
              ON item.tenant_id = task.tenant_id AND item.task_id = task.id
            JOIN content_versions version
              ON version.tenant_id = item.tenant_id
             AND version.task_id = item.task_id
             AND version.version_number = item.current_version
            JOIN generation_runs run
              ON run.tenant_id = version.tenant_id AND run.id = version.run_id
            WHERE account.tenant_id = %s
              AND account.brand_id = %s
              AND account.carrier_of_account_id = %s
              AND task.parent_version_id IS NOT NULL
            ORDER BY version.created_at DESC
            """,
            (scope.tenant_id, scope.brand_id, account_id),
        )
        grouped: dict[str, list[dict[str, object]]] = {}
        for row in cursor.fetchall():
            source_version_id = str(row["parent_version_id"])
            if source_version_id not in source_versions:
                continue
            grouped.setdefault(source_version_id, []).append(row)
        complete = [
            (source_id, rows)
            for source_id, rows in grouped.items()
            if {"小红书", "微信视频号"} <= {str(row["channel"]) for row in rows}
        ]
        if not complete:
            return []
        source_id, rows = max(
            complete,
            key=lambda group: max(str(row["created_at"]) for row in group[1]),
        )
        source_version, source_code = source_versions[source_id]
        source = dict(source_version)
        source_label = f"{source_code} V{source['version']}".strip()
        source["platform"] = "抖音"
        source["media"] = "视频"
        source["adaptation"] = "系列源成品"
        source["source_label"] = source_label
        source["source_version_id"] = source_id
        source["parent_version_id"] = None
        projections = [source]
        newest_by_channel: dict[str, dict[str, object]] = {}
        for row in rows:
            newest_by_channel.setdefault(str(row["channel"]), row)
        for row in sorted(newest_by_channel.values(), key=lambda item: str(item["channel"])):
            projection = self._demo_version(row)
            projection["adaptation"] = "由所选源成品另做的平台版本"
            projection["source_label"] = source_label
            projection["source_version_id"] = source_id
            projection["parent_version_id"] = str(row["parent_version_id"])
            projections.append(projection)
        return projections

    @staticmethod
    def _content_value_label(value: str) -> str:
        return {
            "dressing_decision": "帮助受众按条件做选择",
            "product_truth": "解释商品事实与取舍边界",
            "brand_life_narrative": "建立品牌生活关系",
            "local_response": "从在地位置回应现实问题",
            "visual_styling_story": "让受众从画面看见新的穿着可能",
        }.get(value, "提供完整受众价值")

    def _demo_version(self, row: dict[str, object]) -> dict[str, object]:
        channel = str(row["channel"])
        media = str(row["media_format"])
        content = validate_version_content(row)
        translation_notice, applied_direction = visible_direction(row["content_context_snapshot"])
        disclosure, reminder = aigc_disclosure(row["model"])
        return {
            "version_id": str(row["id"]),
            "version": self._integer(row["version_number"]),
            "title": content.outline,
            "body": content.body,
            "platform": channel,
            "media": "图文" if media == "graphic" else "视频",
            "ai_generated": is_ai_generated_content(row["model"]),
            "aigc_label": disclosure,
            "aigc_release_reminder": reminder,
            "translation_notice": translation_notice,
            "applied_direction": applied_direction,
            "created_at": self._time(row["created_at"]),
        }

    def save_management_product(
        self,
        scope: TenantManagementScope,
        sku: str,
        display_name: str,
        facts: dict[str, object],
        source_kind: str,
        source_note: str,
        applicability: str,
        visibility_scope: str = "brand_all",
        organization_ids: tuple[UUID, ...] = (),
    ) -> dict[str, object]:
        proposed_product_id = uuid4()
        version_id = uuid4()
        with self._management_tx(scope) as cursor:
            organizations = self._validated_scope_organizations(
                cursor,
                scope.tenant_id,
                visibility_scope,
                organization_ids,
                "商品资料",
            )
            cursor.execute(
                """
                SELECT id, fact_version
                FROM brand_products
                WHERE tenant_id = %s AND brand_id = %s AND sku = %s
                FOR UPDATE
                """,
                (scope.tenant_id, scope.brand_id, sku),
            )
            existing = cursor.fetchone()
            if existing is None:
                product_id = proposed_product_id
                fact_version = 1
                cursor.execute(
                    """
                    INSERT INTO brand_products
                    (id, tenant_id, brand_id, sku, display_name, facts,
                     source_kind, source_note, fact_version, applicability,
                     status, updated_by, updated_at, visibility_scope,
                     current_version_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s,
                            %s, 1, %s, 'active', %s, now(), %s, NULL)
                    """,
                    (
                        product_id,
                        scope.tenant_id,
                        scope.brand_id,
                        sku,
                        display_name,
                        Jsonb(facts),
                        source_kind,
                        source_note,
                        applicability,
                        scope.user_id,
                        visibility_scope,
                    ),
                )
            else:
                product_id = UUID(str(existing["id"]))
                fact_version = self._integer(existing["fact_version"]) + 1
            cursor.execute(
                """
                INSERT INTO brand_product_versions
                    (id, tenant_id, brand_id, product_id, version_number,
                     display_name, facts, source_kind, source_note,
                     applicability, visibility_scope,
                     scope_organization_ids, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    version_id,
                    scope.tenant_id,
                    scope.brand_id,
                    product_id,
                    fact_version,
                    display_name,
                    Jsonb(facts),
                    source_kind,
                    source_note,
                    applicability,
                    visibility_scope,
                    list(organization_ids),
                    scope.user_id,
                ),
            )
            cursor.execute(
                """
                UPDATE brand_products
                   SET display_name = %s, facts = %s, source_kind = %s,
                       source_note = %s, fact_version = %s,
                       applicability = %s, status = 'active',
                       visibility_scope = %s, current_version_id = %s,
                       updated_by = %s, updated_at = now()
                 WHERE tenant_id = %s AND brand_id = %s AND id = %s
                RETURNING updated_at
                """,
                (
                    display_name,
                    Jsonb(facts),
                    source_kind,
                    source_note,
                    fact_version,
                    applicability,
                    visibility_scope,
                    version_id,
                    scope.user_id,
                    scope.tenant_id,
                    scope.brand_id,
                    product_id,
                ),
            )
            row = self._one(cursor, "商品资料保存失败")
            cursor.execute(
                "DELETE FROM brand_product_scope_organizations WHERE tenant_id = %s AND product_id = %s",
                (scope.tenant_id, product_id),
            )
            for organization in organizations:
                cursor.execute(
                    """
                    INSERT INTO brand_product_scope_organizations
                        (id, tenant_id, product_id, organization_id)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        uuid4(),
                        scope.tenant_id,
                        product_id,
                        organization["id"],
                    ),
                )
            self._event(
                cursor,
                scope,
                "brand_product.fact_version_saved",
                "brand_product",
                product_id,
            )
        return {
            "id": str(product_id),
            "sku": sku,
            "display_name": display_name,
            "facts": facts,
            "source_kind": source_kind,
            "source_note": source_note,
            "fact_version": fact_version,
            "current_version_id": str(version_id),
            "applicability": applicability,
            "status": "active",
            "visibility_scope": visibility_scope,
            "scope_organizations": [
                {
                    "id": str(organization["id"]),
                    "name": str(organization["name"]),
                    "level": str(organization["organization_level"]),
                }
                for organization in organizations
            ],
            "updated_at": row["updated_at"],
        }

    def management_product_versions(
        self,
        scope: TenantManagementScope,
        sku: str,
    ) -> list[dict[str, object]]:
        with self._management_tx(scope) as cursor:
            cursor.execute(
                """
                SELECT version.id, version.version_number, version.display_name,
                       version.facts, version.source_kind, version.source_note,
                       version.applicability, version.visibility_scope,
                       version.scope_organization_ids, version.created_at,
                       product.current_version_id = version.id AS is_current,
                       product.status
                FROM brand_product_versions version
                JOIN brand_products product
                  ON product.tenant_id = version.tenant_id
                 AND product.id = version.product_id
                WHERE version.tenant_id = %s
                  AND version.brand_id = %s
                  AND product.sku = %s
                ORDER BY version.version_number DESC
                """,
                (scope.tenant_id, scope.brand_id, sku),
            )
            rows = cursor.fetchall()
        if not rows:
            raise DomainError("找不到当前品牌的商品事实版本")
        return [
            {
                "id": str(row["id"]),
                "sku": sku,
                "fact_version": self._integer(row["version_number"]),
                "display_name": str(row["display_name"]),
                "facts": row["facts"] if isinstance(row["facts"], dict) else {},
                "source_kind": str(row["source_kind"]),
                "source_note": str(row["source_note"]),
                "applicability": str(row["applicability"]),
                "visibility_scope": str(row["visibility_scope"]),
                "organization_ids": [
                    str(item)
                    for item in (
                        row["scope_organization_ids"]
                        if isinstance(row["scope_organization_ids"], list)
                        else []
                    )
                ],
                "status": str(row["status"]),
                "is_current": bool(row["is_current"]),
                "created_at": self._time(row["created_at"]),
            }
            for row in rows
        ]

    def set_management_product_enabled(
        self,
        scope: TenantManagementScope,
        sku: str,
        enabled: bool,
    ) -> dict[str, object]:
        with self._management_tx(scope) as cursor:
            cursor.execute(
                """
                UPDATE brand_products
                   SET status = %s, updated_by = %s, updated_at = now()
                 WHERE tenant_id = %s AND brand_id = %s AND sku = %s
                   AND current_version_id IS NOT NULL
                RETURNING id, sku, status, fact_version, current_version_id
                """,
                (
                    "active" if enabled else "retired",
                    scope.user_id,
                    scope.tenant_id,
                    scope.brand_id,
                    sku,
                ),
            )
            row = self._one(cursor, "找不到当前品牌可停用或恢复的商品")
            self._event(
                cursor,
                scope,
                "brand_product.restored" if enabled else "brand_product.retired",
                "brand_product",
                UUID(str(row["id"])),
            )
        return {
            "id": str(row["id"]),
            "sku": str(row["sku"]),
            "status": str(row["status"]),
            "fact_version": self._integer(row["fact_version"]),
            "current_version_id": str(row["current_version_id"]),
        }

    def create_publishing_account(
        self,
        scope: TenantManagementScope,
        name: str,
        channel: str,
        content_role_name: str,
        voice_boundary: str,
        operator_id: UUID,
        control_organization_id: UUID | None = None,
        operator_can_maintain_expression_profile: bool = False,
        business_data_kind: str = "formal_business_data",
        initial_profile: dict[str, str] | None = None,
        speaker_kind: SpeakerKind = "unknown",
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
            # Serialize grants for this person while allowing one natural person to operate
            # several explicitly authorized logical publishing identities.
            cursor.execute(
                "SELECT id, organization_id FROM users "
                "WHERE tenant_id = %s AND id = %s AND enabled = true "
                "AND entry_kind = 'tenant_user' FOR UPDATE",
                (scope.tenant_id, operator_id),
            )
            operator = self._one(
                cursor,
                "只能向当前租户已登记且启用的自然人授权发布账号",
            )
            # Which organization controls this account is an explicit decision, made here or
            # later by a tenant authority.  Nothing is defaulted, inferred from the creating
            # administrator, or guessed from an account name, a role name or an operator's name;
            # an account created without one simply has no maintainable profile until declared.
            if control_organization_id is not None:
                cursor.execute(
                    "SELECT id, organization_level FROM organizations WHERE tenant_id = %s AND id = %s",
                    (scope.tenant_id, control_organization_id),
                )
                self._one(
                    cursor,
                    "只能指定当前租户已有的组织作为账号控制组织",
                )
            if operator_can_maintain_expression_profile:
                if control_organization_id is None:
                    raise DomainError(
                        "账号尚未指定负责团队，不能授予五段画像维护资格"
                    )
                if UUID(str(operator["organization_id"])) != control_organization_id:
                    raise DomainError(
                        "只有账号负责团队的成员可以获得五段画像维护资格"
                    )
            cursor.execute(
                """
                SELECT account.id, account.channel, role.name AS content_role,
                       role.voice_boundary, role.speaker_kind,
                       account.control_organization_id,
                       account.business_data_kind,
                       profile.identity_position,
                       profile.authority_boundary,
                       profile.audience_relationship,
                       profile.content_territories,
                       profile.default_production_conditions,
                       EXISTS (
                           SELECT 1
                           FROM auth_grants grant_record
                           WHERE grant_record.tenant_id = account.tenant_id
                             AND grant_record.account_id = account.id
                             AND grant_record.user_id = %s
                             AND grant_record.enabled = true
                       ) AS has_operator,
                       COALESCE((
                           SELECT grant_record.can_maintain_expression_profile
                           FROM auth_grants grant_record
                           WHERE grant_record.tenant_id = account.tenant_id
                             AND grant_record.account_id = account.id
                             AND grant_record.user_id = %s
                             AND grant_record.enabled = true
                       ), false) AS operator_can_maintain
                FROM content_accounts account
                JOIN account_content_roles account_role
                  ON account_role.tenant_id = account.tenant_id
                 AND account_role.account_id = account.id
                JOIN content_roles role
                  ON role.tenant_id = account_role.tenant_id
                 AND role.id = account_role.content_role_id
                 AND role.brand_id = account.brand_id
                LEFT JOIN account_expression_profile_versions profile
                  ON profile.tenant_id = account.tenant_id
                 AND profile.account_id = account.id
                 AND profile.id = account.current_expression_profile_id
                WHERE account.tenant_id = %s
                  AND account.brand_id = %s
                  AND account.name = %s
                  AND account.enabled = true
                  AND account.carrier_of_account_id IS NULL
                """,
                (operator_id, operator_id, scope.tenant_id, scope.brand_id, name),
            )
            existing = cursor.fetchone()
            if existing is not None:
                existing_control = existing["control_organization_id"]
                if (
                    str(existing["channel"]) != channel
                    or str(existing["content_role"]) != content_role_name
                    or str(existing["voice_boundary"]) != voice_boundary
                    or str(existing["speaker_kind"]) != speaker_kind
                    or not bool(existing["has_operator"])
                    or bool(existing["operator_can_maintain"]) != operator_can_maintain_expression_profile
                    or str(existing["business_data_kind"]) != business_data_kind
                    # Control organization decides who may maintain the profile, so a repeat that
                    # names a different one is a different account, not the same one again.
                    or (str(existing_control) if existing_control is not None else None)
                    != (str(control_organization_id) if control_organization_id else None)
                ):
                    raise DomainError("当前品牌已有同名发布账号，但平台、表达身份、操作者或控制组织不同。")
                if initial_profile is not None and any(
                    str(existing[key] or "") != initial_profile[key]
                    for key in (
                        "identity_position",
                        "authority_boundary",
                        "audience_relationship",
                        "content_territories",
                        "default_production_conditions",
                    )
                ):
                    raise DomainError("当前品牌已有同名发布账号，但账号画像不同。")
                return {
                    "id": str(existing["id"]),
                    "name": name,
                    "channel": channel,
                    "content_role": content_role_name,
                    "speaker_kind": speaker_kind,
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
                "INSERT INTO content_accounts (id, tenant_id, brand_id, name, channel, "
                "control_organization_id, control_organization_source, "
                "business_data_kind) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    account_id,
                    scope.tenant_id,
                    scope.brand_id,
                    name,
                    channel,
                    control_organization_id,
                    "declared" if control_organization_id is not None else "unset",
                    business_data_kind,
                ),
            )
            cursor.execute(
                "INSERT INTO content_roles "
                "(id, tenant_id, brand_id, name, voice_boundary, speaker_kind) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (
                    content_role_id,
                    scope.tenant_id,
                    scope.brand_id,
                    content_role_name,
                    voice_boundary,
                    speaker_kind,
                ),
            )
            cursor.execute(
                "INSERT INTO account_content_roles (id, tenant_id, account_id, content_role_id) VALUES (%s, %s, %s, %s)",
                (uuid4(), scope.tenant_id, account_id, content_role_id),
            )
            profile_id: UUID | None = None
            if initial_profile is not None:
                profile_id = uuid4()
                cursor.execute(
                    """
                    INSERT INTO account_expression_profile_versions
                        (id, tenant_id, account_id, content_role_id, version,
                         identity_position, authority_boundary,
                         audience_relationship, content_territories,
                         default_production_conditions, created_by)
                    VALUES (%s, %s, %s, %s, 1, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        profile_id,
                        scope.tenant_id,
                        account_id,
                        content_role_id,
                        initial_profile["identity_position"],
                        initial_profile["authority_boundary"],
                        initial_profile["audience_relationship"],
                        initial_profile["content_territories"],
                        initial_profile["default_production_conditions"],
                        scope.user_id,
                    ),
                )
                cursor.execute(
                    "UPDATE content_accounts SET current_expression_profile_id = %s WHERE tenant_id = %s AND id = %s",
                    (profile_id, scope.tenant_id, account_id),
                )
            cursor.execute(
                "INSERT INTO auth_grants "
                "(id, tenant_id, user_id, account_id, role_name, "
                "can_maintain_expression_profile) VALUES (%s, %s, %s, %s, %s, %s)",
                (
                    uuid4(),
                    scope.tenant_id,
                    operator_id,
                    account_id,
                    "发布账号操作资格",
                    operator_can_maintain_expression_profile,
                ),
            )
            self._event(cursor, scope, "publishing_account.created", "content_account", account_id)
            if profile_id is not None:
                self._event(
                    cursor,
                    scope,
                    "account_expression_profile.version_saved",
                    "account_expression_profile",
                    profile_id,
                )
        return {
            "id": str(account_id),
            "name": name,
            "channel": channel,
            "content_role": content_role_name,
            "speaker_kind": speaker_kind,
            "voice_boundary": voice_boundary,
            "operator_id": str(operator_id),
            "shared_password": False,
        }

    def update_publishing_speaker_kind(
        self,
        scope: TenantManagementScope,
        account_id: UUID,
        speaker_kind: SpeakerKind,
    ) -> dict[str, object]:
        with self._management_tx(scope) as cursor:
            cursor.execute(
                """
                UPDATE content_roles AS role
                   SET speaker_kind = %s
                  FROM account_content_roles AS account_role
                  JOIN content_accounts AS account
                    ON account.tenant_id = account_role.tenant_id
                   AND account.id = account_role.account_id
                 WHERE role.tenant_id = %s
                   AND role.brand_id = %s
                   AND role.id = account_role.content_role_id
                   AND account.id = %s
                   AND account.brand_id = %s
                   AND account.carrier_of_account_id IS NULL
                   AND account.enabled = true
                RETURNING role.name, role.speaker_kind
                """,
                (
                    speaker_kind,
                    scope.tenant_id,
                    scope.brand_id,
                    account_id,
                    scope.brand_id,
                ),
            )
            role = self._one(
                cursor,
                "只能声明当前租户、品牌下可用逻辑发布账号的说话者类型。",
            )
            self._event(
                cursor,
                scope,
                "publishing_account.speaker_kind_updated",
                "content_account",
                account_id,
            )
        return {
            "account_id": str(account_id),
            "content_role": str(role["name"]),
            "speaker_kind": str(role["speaker_kind"]),
        }

    def update_publishing_account(
        self,
        scope: TenantManagementScope,
        account_id: UUID,
        name: str | None,
        control_organization_id: UUID | None,
    ) -> dict[str, object]:
        with self._management_tx(scope) as cursor:
            cursor.execute(
                """
                SELECT name, control_organization_id
                  FROM content_accounts
                 WHERE tenant_id = %s
                   AND brand_id = %s
                   AND id = %s
                   AND carrier_of_account_id IS NULL
                 FOR UPDATE
                """,
                (scope.tenant_id, scope.brand_id, account_id),
            )
            current = self._one(
                cursor,
                "找不到当前租户的逻辑发布账号。",
            )
            resolved_control = (
                control_organization_id
                if control_organization_id is not None
                else (
                    UUID(str(current["control_organization_id"]))
                    if current["control_organization_id"] is not None
                    else None
                )
            )
            if resolved_control is not None:
                cursor.execute(
                    "SELECT id FROM organizations "
                    "WHERE tenant_id = %s AND id = %s",
                    (scope.tenant_id, resolved_control),
                )
                self._one(cursor, "只能选择当前租户已有的负责团队。")
            resolved_name = name or str(current["name"])
            cursor.execute(
                """
                UPDATE content_accounts
                   SET name = %s,
                       control_organization_id = %s,
                       control_organization_source =
                           CASE WHEN %s IS NULL THEN 'unset' ELSE 'declared' END
                 WHERE tenant_id = %s
                   AND id = %s
                """,
                (
                    resolved_name,
                    resolved_control,
                    resolved_control,
                    scope.tenant_id,
                    account_id,
                ),
            )
            cursor.execute(
                """
                UPDATE content_accounts
                   SET control_organization_id = %s,
                       control_organization_source =
                           CASE WHEN %s IS NULL THEN 'unset' ELSE 'declared' END
                 WHERE tenant_id = %s
                   AND carrier_of_account_id = %s
                """,
                (
                    resolved_control,
                    resolved_control,
                    scope.tenant_id,
                    account_id,
                ),
            )
            cursor.execute(
                """
                UPDATE auth_grants AS grant_record
                   SET can_maintain_expression_profile = false
                  FROM users AS person
                 WHERE grant_record.tenant_id = %s
                   AND grant_record.account_id = %s
                   AND grant_record.enabled = true
                   AND grant_record.can_maintain_expression_profile = true
                   AND person.tenant_id = grant_record.tenant_id
                   AND person.id = grant_record.user_id
                   AND person.organization_id IS DISTINCT FROM %s
                """,
                (
                    scope.tenant_id,
                    account_id,
                    resolved_control,
                ),
            )
            self._event(
                cursor,
                scope,
                "publishing_account.updated",
                "content_account",
                account_id,
            )
        return {
            "id": str(account_id),
            "name": resolved_name,
            "control_organization_id": (
                str(resolved_control) if resolved_control is not None else None
            ),
        }

    def set_publishing_account_enabled(
        self,
        scope: TenantManagementScope,
        account_id: UUID,
        enabled: bool,
    ) -> dict[str, object]:
        with self._management_tx(scope) as cursor:
            cursor.execute(
                """
                UPDATE content_accounts
                   SET enabled = %s
                 WHERE tenant_id = %s
                   AND brand_id = %s
                   AND id = %s
                   AND carrier_of_account_id IS NULL
                   AND enabled <> %s
                RETURNING id
                """,
                (
                    enabled,
                    scope.tenant_id,
                    scope.brand_id,
                    account_id,
                    enabled,
                ),
            )
            self._one(
                cursor,
                "找不到需要调整状态的逻辑发布账号。",
            )
            self._event(
                cursor,
                scope,
                (
                    "publishing_account.restored"
                    if enabled
                    else "publishing_account.disabled"
                ),
                "content_account",
                account_id,
            )
        return {"id": str(account_id), "enabled": enabled}

    def create_platform_carrier(
        self,
        scope: TenantManagementScope,
        source_account_id: UUID,
        name: str,
        channel: str,
        operator_id: UUID,
    ) -> dict[str, object]:
        carrier_id = uuid4()
        with self._management_tx(scope) as cursor:
            cursor.execute(
                """
                SELECT source.channel, source.control_organization_id,
                       source.control_organization_source, account_role.content_role_id,
                       role.name AS content_role, role.voice_boundary,
                       source.business_data_kind
                FROM content_accounts source
                JOIN account_content_roles account_role
                  ON account_role.tenant_id = source.tenant_id
                 AND account_role.account_id = source.id
                JOIN content_roles role
                  ON role.tenant_id = account_role.tenant_id
                 AND role.id = account_role.content_role_id
                WHERE source.tenant_id = %s AND source.brand_id = %s
                  AND source.id = %s AND source.enabled = true
                  AND source.carrier_of_account_id IS NULL
                  AND EXISTS (
                    SELECT 1 FROM auth_grants grant_record
                    JOIN users operator
                      ON operator.tenant_id = grant_record.tenant_id
                     AND operator.id = grant_record.user_id
                     AND operator.enabled = true
                     AND operator.entry_kind = 'tenant_user'
                    WHERE grant_record.tenant_id = source.tenant_id
                      AND grant_record.account_id = source.id
                      AND grant_record.user_id = %s
                      AND grant_record.enabled = true
                  )
                """,
                (scope.tenant_id, scope.brand_id, source_account_id, operator_id),
            )
            source = self._one(
                cursor,
                "只能为当前品牌已授权的真实表达账号补充平台版本载体",
            )
            if str(source["channel"]) == channel:
                raise DomainError("这个平台已经由原发布账号承载。")
            cursor.execute(
                """
                SELECT carrier.id, carrier.name, carrier.enabled,
                       carrier.platform_enabled
                FROM content_accounts carrier
                WHERE carrier.tenant_id = %s
                  AND carrier.carrier_of_account_id = %s
                  AND carrier.channel = %s
                """,
                (scope.tenant_id, source_account_id, channel),
            )
            existing = cursor.fetchone()
            if existing is not None:
                if str(existing["name"]) != name:
                    raise DomainError("这个表达身份在目标平台已有不同的明确载体。")
                carrier_id = UUID(str(existing["id"]))
                if not bool(existing["enabled"]) or not bool(
                    existing["platform_enabled"]
                ):
                    cursor.execute(
                        "UPDATE content_accounts "
                        "SET enabled = true, platform_enabled = true "
                        "WHERE tenant_id = %s AND id = %s",
                        (scope.tenant_id, carrier_id),
                    )
                    self._event(
                        cursor,
                        scope,
                        "publishing_account.platform_carrier_restored",
                        "content_account",
                        carrier_id,
                    )
            else:
                cursor.execute(
                    """
                    INSERT INTO content_accounts
                        (id, tenant_id, brand_id, name, channel,
                         control_organization_id, control_organization_source,
                         carrier_of_account_id, business_data_kind)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        carrier_id,
                        scope.tenant_id,
                        scope.brand_id,
                        name,
                        channel,
                        source["control_organization_id"],
                        source["control_organization_source"],
                        source_account_id,
                        source["business_data_kind"],
                    ),
                )
                # Keep the matching relation during the expand-first rollback
                # window.  The UI-05 runtime never consumes it as an independent
                # role: every read resolves through source_account_id.
                cursor.execute(
                    """
                    INSERT INTO account_content_roles
                        (id, tenant_id, account_id, content_role_id)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        uuid4(),
                        scope.tenant_id,
                        carrier_id,
                        source["content_role_id"],
                    ),
                )
                self._event(
                    cursor,
                    scope,
                    "publishing_account.platform_carrier_created",
                    "content_account",
                    carrier_id,
                )
            # The previous healthy image authorizes a physical carrier directly.
            # Preserve that internal compatibility grant for rollback, while the
            # UI-05 authority resolves only enabled logical-root grants.
            cursor.execute(
                """
                INSERT INTO auth_grants
                    (id, tenant_id, user_id, account_id, role_name,
                     can_maintain_expression_profile)
                VALUES (%s, %s, %s, %s, %s, false)
                ON CONFLICT (tenant_id, user_id, account_id) DO UPDATE
                    SET enabled = true,
                        role_name = EXCLUDED.role_name,
                        can_maintain_expression_profile = false
                """,
                (
                    uuid4(),
                    scope.tenant_id,
                    operator_id,
                    carrier_id,
                    "平台版本载体兼容资格",
                ),
            )
        return {
            "id": str(carrier_id),
            "name": name,
            "channel": channel,
            "carrier_of_account_id": str(source_account_id),
            "content_role": str(source["content_role"]),
            "voice_boundary": str(source["voice_boundary"]),
            "operator_id": str(operator_id),
            "shared_password": False,
        }

    def set_platform_carrier_enabled(
        self,
        scope: TenantManagementScope,
        account_id: UUID,
        enabled: bool,
    ) -> dict[str, object]:
        with self._management_tx(scope) as cursor:
            cursor.execute(
                """
                UPDATE content_accounts AS physical
                   SET platform_enabled = %s,
                       enabled = CASE
                           WHEN physical.carrier_of_account_id IS NULL
                           THEN physical.enabled
                           ELSE %s
                       END
                 WHERE physical.tenant_id = %s
                   AND physical.brand_id = %s
                   AND physical.id = %s
                   AND physical.platform_enabled <> %s
                   AND EXISTS (
                       SELECT 1
                         FROM content_accounts AS root
                        WHERE root.tenant_id = physical.tenant_id
                          AND root.brand_id = physical.brand_id
                          AND root.id = COALESCE(
                              physical.carrier_of_account_id,
                              physical.id
                          )
                          AND root.carrier_of_account_id IS NULL
                   )
                RETURNING physical.id,
                          COALESCE(
                              physical.carrier_of_account_id,
                              physical.id
                          ) AS root_id
                """,
                (
                    enabled,
                    enabled,
                    scope.tenant_id,
                    scope.brand_id,
                    account_id,
                    enabled,
                ),
            )
            changed = self._one(
                cursor,
                "找不到需要调整状态的平台目标。",
            )
            self._event(
                cursor,
                scope,
                (
                    "publishing_account.platform_carrier_restored"
                    if enabled
                    else "publishing_account.platform_carrier_disabled"
                ),
                "content_account",
                account_id,
            )
        return {
            "id": str(changed["id"]),
            "root_account_id": str(changed["root_id"]),
            "enabled": enabled,
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
                "SELECT id FROM content_accounts "
                "WHERE tenant_id = %s AND brand_id = %s AND id = %s "
                "AND enabled = true AND carrier_of_account_id IS NULL",
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
                "INSERT INTO users "
                "(id, tenant_id, organization_id, display_name, entry_kind) "
                "VALUES (%s, %s, %s, %s, 'tenant_user')",
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
                  AND u.enabled = true AND u.entry_kind = 'tenant_user'
                  AND EXISTS (
                    SELECT 1 FROM display_access_grants display_grant
                    WHERE display_grant.tenant_id = u.tenant_id
                      AND display_grant.user_id = u.id
                      AND display_grant.enabled = true
                  )
                """,
                (scope.brand_id, scope.organization_id, scope.tenant_id, scope.user_id),
            )
            row = self._one(cursor, "找不到当前可信陈列身份")
        return {key: str(value) for key, value in row.items()}

    def recent_content(self, scope: TrustedScope) -> list[dict[str, object]]:
        with self._content_tx(scope) as cursor:
            logical_account_id = self._logical_account_id(cursor, scope)
            cursor.execute(
                """
                SELECT t.id AS task_id, t.parent_version_id, cv.id AS version_id,
                       cv.version_number, cv.outline, cv.body,
                       cv.artifact_digest, cv.version_audit_snapshot,
                       cv.created_at,
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
                WHERE t.tenant_id = %s AND t.brand_id = %s
                  AND t.logical_account_id = %s AND t.created_by = %s
                ORDER BY cv.created_at DESC LIMIT 20
                """,
                (scope.tenant_id, scope.brand_id, logical_account_id, scope.user_id),
            )
            rows = cursor.fetchall()
        result: list[dict[str, object]] = []
        for row in rows:
            content = validate_version_content(row)
            result.append(
                {
                    "task_id": str(row["task_id"]),
                    "source_version_id": (
                        str(row["parent_version_id"]) if row["parent_version_id"] is not None else None
                    ),
                    "version_id": str(row["version_id"]),
                    "version": self._integer(row["version_number"]),
                    "title": content.outline,
                    "target": str(row["target"]),
                    "updated_at": self._time(row["created_at"]),
                    "status": "已有成品",
                }
            )
        return result

    def content_versions(self, scope: TrustedScope, task_id: UUID) -> list[dict[str, object]]:
        with self._content_tx(scope) as cursor:
            logical_account_id = self._logical_account_id(cursor, scope)
            cursor.execute(
                """
                SELECT cv.id AS version_id, cv.version_number, cv.outline, cv.body,
                       cv.artifact_digest, cv.version_audit_snapshot,
                       cv.created_at, gr.model,
                       t.content_context_snapshot,
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
                  AND t.logical_account_id = %s AND t.created_by = %s
                ORDER BY cv.version_number DESC
                """,
                (
                    scope.tenant_id,
                    task_id,
                    scope.brand_id,
                    logical_account_id,
                    scope.user_id,
                ),
            )
            rows = cursor.fetchall()
        result: list[dict[str, object]] = []
        for row in rows:
            content = validate_version_content(row)
            result.append(
                {
                    "task_id": str(task_id),
                    "version_id": str(row["version_id"]),
                    "version": self._integer(row["version_number"]),
                    "outline": content.outline,
                    "body": content.body,
                    "target_key": str(row["target_key"]),
                    "ai_generated": is_ai_generated_content(row["model"]),
                    "aigc_label": aigc_disclosure(row["model"])[0],
                    "aigc_release_reminder": aigc_disclosure(row["model"])[1],
                    "created_at": self._time(row["created_at"]),
                    "translation_notice": visible_direction(row["content_context_snapshot"])[0],
                    "applied_direction": visible_direction(row["content_context_snapshot"])[1],
                }
            )
        return result

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

    def readiness(self, scope: TenantManagementScope) -> list[dict[str, object]]:
        with self._management_tx(scope) as cursor:
            cursor.execute(
                """
                SELECT
                  COALESCE(
                    (SELECT baseline.status FROM brand_expression_baselines baseline
                     WHERE baseline.tenant_id = %s AND baseline.brand_id = %s),
                    'missing'
                  ) AS expression_status,
                  (SELECT count(*) FROM content_accounts account
                   WHERE account.tenant_id = %s AND account.brand_id = %s
                     AND account.enabled = true
                     AND account.carrier_of_account_id IS NULL) AS root_accounts,
                  (SELECT count(DISTINCT account.id)
                   FROM content_accounts account
                   JOIN account_content_roles account_role
                     ON account_role.tenant_id = account.tenant_id
                    AND account_role.account_id = account.id
                   JOIN auth_grants grant_record
                     ON grant_record.tenant_id = account.tenant_id
                    AND grant_record.account_id = account.id
                    AND grant_record.enabled = true
                   JOIN users operator
                     ON operator.tenant_id = grant_record.tenant_id
                    AND operator.id = grant_record.user_id
                    AND operator.enabled = true
                    AND operator.entry_kind = 'tenant_user'
                   WHERE account.tenant_id = %s AND account.brand_id = %s
                     AND account.enabled = true
                     AND account.carrier_of_account_id IS NULL
                     AND account.current_expression_profile_id IS NOT NULL) AS expression_accounts,
                  (SELECT count(*) FROM brand_products product
                   WHERE product.tenant_id = %s AND product.brand_id = %s
                     AND product.status = 'active' AND product.source_note <> ''
                     AND product.facts <> '{}'::jsonb) AS product_facts,
                  (SELECT count(*) FROM content_series series
                   WHERE series.tenant_id = %s AND series.brand_id = %s) AS series_count,
                  (SELECT count(*) FROM (
                     SELECT root.id
                     FROM content_accounts root
                     JOIN content_accounts physical
                       ON physical.tenant_id = root.tenant_id
                      AND physical.enabled = true
                      AND physical.platform_enabled = true
                      AND (physical.id = root.id OR physical.carrier_of_account_id = root.id)
                     WHERE root.tenant_id = %s AND root.brand_id = %s
                       AND root.enabled = true
                       AND root.carrier_of_account_id IS NULL
                     GROUP BY root.id
                     HAVING count(DISTINCT physical.channel) >= 2
                   ) multi_target) AS multi_target_accounts,
                  (SELECT count(*) FROM display_stores store
                   WHERE store.tenant_id = %s AND store.brand_id = %s) AS display_stores,
                  (SELECT count(*) FROM brand_products product
                   WHERE product.tenant_id = %s AND product.brand_id = %s
                     AND product.status = 'active'
                     AND product.facts ? 'display_family') AS display_products,
                  (SELECT count(*) FROM display_access_grants display_grant
                   JOIN users display_user
                     ON display_user.tenant_id = display_grant.tenant_id
                    AND display_user.id = display_grant.user_id
                    AND display_user.enabled = true
                    AND display_user.entry_kind = 'tenant_user'
                   WHERE display_grant.tenant_id = %s
                     AND display_grant.enabled = true) AS display_users,
                  now() AS evaluated_at
                """,
                (
                    scope.tenant_id,
                    scope.brand_id,
                    scope.tenant_id,
                    scope.brand_id,
                    scope.tenant_id,
                    scope.brand_id,
                    scope.tenant_id,
                    scope.brand_id,
                    scope.tenant_id,
                    scope.brand_id,
                    scope.tenant_id,
                    scope.brand_id,
                    scope.tenant_id,
                    scope.brand_id,
                    scope.tenant_id,
                    scope.brand_id,
                    scope.tenant_id,
                ),
            )
            state = self._one(cursor, "无法读取当前可用条件")
            path_state = readiness_path_state(cursor, scope)
        expression_paths = self._mapping_list(path_state["expression_paths"])
        product_paths = self._mapping_list(path_state["product_paths"])
        library_paths = self._mapping_list(path_state["library_paths"])
        series_paths = self._mapping_list(path_state["series_paths"])
        display_paths = self._mapping_list(path_state["display_paths"])
        expression_confirmed = str(path_state["baseline_status"]) == "confirmed"
        root_accounts = self._integer(state["root_accounts"])
        expression_accounts = len(expression_paths)
        product_components = self._integer(state["product_facts"])
        display_stores = self._integer(state["display_stores"])
        display_products = self._integer(state["display_products"])
        display_users = self._integer(state["display_users"])
        evaluated_at = self._time(state["evaluated_at"])
        expression_available = expression_confirmed and bool(expression_paths)
        expression_status = self._condition_status(
            expression_available,
            expression_confirmed or root_accounts > 0,
        )
        product_status = self._condition_status(
            expression_confirmed and bool(product_paths),
            expression_available or product_components > 0,
        )
        series_status = self._condition_status(
            expression_available,
            root_accounts > 0,
        )
        platform_paths = [
            path
            for path in expression_paths
            if self._integer(path.get("target_count")) >= 2
        ]
        recompile_status = self._condition_status(
            expression_confirmed and bool(platform_paths),
            bool(expression_paths)
            or self._integer(path_state["multi_target_components"]) > 0,
        )
        display_status = self._condition_status(
            bool(display_paths),
            display_stores > 0 or display_products > 0 or display_users > 0,
        )
        common: dict[str, object] = {
            "source": "当前租户的正式业务对象",
            "version": "ux03-readiness-v3",
            "contract_version": "ux03-readiness-v3",
            "evaluated_at": evaluated_at,
        }
        selected_expression = expression_paths[0] if expression_paths else None
        expression_evidence = self._expression_path_evidence(
            path_state,
            selected_expression,
        )
        selected_account_id = (
            str(selected_expression["account_id"])
            if selected_expression is not None
            else ""
        )
        library_evidence = [
            self._library_path_evidence(path)
            for path in library_paths
            if str(path["account_id"]) == selected_account_id
        ][:3]
        selected_product = product_paths[0] if product_paths else None
        product_expression = next(
            (
                path
                for path in expression_paths
                if selected_product is not None
                and str(path["account_id"])
                == str(selected_product["account_id"])
            ),
            None,
        )
        product_expression_evidence = self._expression_path_evidence(
            path_state,
            product_expression,
        )
        product_evidence = (
            [self._product_path_evidence(selected_product)]
            if selected_product is not None
            else []
        )
        selected_platform = platform_paths[0] if platform_paths else None
        platform_expression_evidence = self._expression_path_evidence(
            path_state,
            selected_platform,
        )
        platform_evidence = (
            [self._platform_path_evidence(selected_platform)]
            if selected_platform is not None
            else []
        )
        selected_series = next(
            (
                path
                for path in series_paths
                if str(path["account_id"]) == selected_account_id
            ),
            None,
        )
        series_evidence = (
            [self._series_path_evidence(selected_series)]
            if selected_series is not None
            else []
        )
        selected_display = display_paths[0] if display_paths else None
        display_evidence = (
            self._display_path_evidence(selected_display)
            if selected_display is not None
            else []
        )
        series_count = sum(
            1
            for path in series_paths
            if str(path["account_id"]) == selected_account_id
        )
        return [
            self._diagnosis(
                "non_product_content",
                "日常非商品内容",
                expression_status,
                [f"可承担表达的逻辑发布账号：{expression_accounts}"],
                [] if expression_available else ["补齐品牌表达、账号画像和成员操作资格。"],
                "影响观点、关系和日常观察类内容能否形成完整成品。",
                "补账号资料",
                "publishing-accounts",
                common,
                evidence_details=expression_evidence + library_evidence,
                unaffected=["不依赖具体商品事实和门店挂杆资料。"],
            ),
            self._diagnosis(
                "product_facts",
                "商品选择与解释",
                product_status,
                (
                    [
                        f"{str(selected_product['account_name'])}可实际使用"
                        f"{str(selected_product['display_name'])}"
                    ]
                    if selected_product is not None
                    else ["当前没有账号与商品处于同一条可执行路径。"]
                ),
                [] if product_status == "available" else ["补充有来源、版本和可观察事实的商品资料。"],
                "只影响需要具体商品承担判断、解释或搭配关系的内容。",
                "补商品资料",
                "brand-library",
                common,
                evidence_details=product_expression_evidence + product_evidence,
                unaffected=["商品缺口不阻止非商品日常内容。"],
            ),
            self._diagnosis(
                "continuous_series",
                "连续系列",
                series_status,
                [
                    f"可操作的逻辑发布账号：{expression_accounts}",
                    f"已有连续系列：{series_count}",
                ],
                [] if series_status == "available" else ["先补齐一个可操作的发布账号和账号画像。"],
                "影响新建系列、续写和冻结系列前情。",
                "管理发布账号",
                "publishing-accounts",
                common,
                evidence_details=expression_evidence + series_evidence,
                unaffected=["不影响单条非系列内容。"],
            ),
            self._diagnosis(
                "platform_recompile",
                "跨平台版本",
                recompile_status,
                (
                    [
                        f"{str(selected_platform['account_name'])}具备"
                        f"{self._integer(selected_platform.get('target_count'))} "
                        "个启用平台与形式目标"
                    ]
                    if selected_platform is not None
                    else ["当前没有同一合格账号具备两个启用平台与形式目标。"]
                ),
                [] if recompile_status == "available" else ["为发布账号补充至少两个明确的平台载体。"],
                "影响从同一源成品另做其他平台版本。",
                "管理平台版本",
                "publishing-accounts",
                common,
                evidence_details=platform_expression_evidence + platform_evidence,
                unaffected=["不影响当前已获准平台上的单平台内容。"],
            ),
            self._diagnosis(
                "dm01_display",
                "门店墙面挂杆参考方案",
                display_status,
                (
                    [
                        f"{str(selected_display['execution_organization_name'])}"
                        "已有同组织门店档案、陈列成员和可用商品"
                    ]
                    if selected_display is not None
                    else ["门店档案、陈列成员与商品尚未在同一执行组织闭合。"]
                ),
                ([] if display_status == "available" else ["补齐门店挂杆条件、陈列商品资料和成员陈列资格中的缺项。"]),
                "只影响门店墙面双层挂杆的文字参考方案。",
                "补门店资料",
                "brand-library",
                common,
                evidence_details=display_evidence,
                unaffected=["门店资料缺口不阻止普通内容创作。"],
            ),
            self._diagnosis(
                "first_creation",
                "新成员首次创作",
                expression_status,
                [
                    f"已确认品牌表达：{'是' if expression_confirmed else '否'}",
                    (
                        "可分配的合格发布账号："
                        + "、".join(
                            str(path["account_name"])
                            for path in expression_paths
                        )
                        if expression_paths
                        else "当前没有可分配的合格发布账号"
                    ),
                ],
                (
                    []
                    if expression_available
                    else ["确认品牌表达，并为成员分配有画像的逻辑发布账号。"]
                ),
                "影响新成员首次进入后能否从弱种子开始创作。",
                "管理成员与账号",
                "members",
                common,
                evidence_details=expression_evidence,
                unaffected=["不影响品牌管理员维护资料和团队配置。"],
            ),
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
            logical_account_id = self._logical_account_id(cursor, scope)
            cursor.execute(
                """
                SELECT id, title, premise, revision FROM content_series
                WHERE tenant_id = %s AND brand_id = %s
                  AND created_by = %s AND logical_account_id = %s
                ORDER BY created_at DESC
                """,
                (
                    scope.tenant_id,
                    scope.brand_id,
                    scope.user_id,
                    logical_account_id,
                ),
            )
            series_rows = cursor.fetchall()
            result: list[dict[str, object]] = []
            for series in series_rows:
                cursor.execute(
                    """
                    SELECT item.task_id, item.position, cv.outline, cv.body,
                           cv.artifact_digest, cv.version_audit_snapshot
                    FROM content_series_items item
                    JOIN business_tasks task ON task.id = item.task_id
                        AND task.tenant_id = item.tenant_id
                    JOIN content_items content_item ON content_item.task_id = item.task_id
                        AND content_item.tenant_id = item.tenant_id
                    JOIN content_versions cv ON cv.task_id = item.task_id AND cv.tenant_id = item.tenant_id
                        AND cv.version_number = content_item.current_version
                    WHERE item.tenant_id = %s AND item.series_id = %s
                      AND task.logical_account_id = %s
                    ORDER BY item.position
                    """,
                    (scope.tenant_id, series["id"], logical_account_id),
                )
                item_rows = cursor.fetchall()
                validated_items = tuple((item, validate_version_content(item)) for item in item_rows)
                result.append(
                    {
                        "id": str(series["id"]),
                        "title": str(series["title"]),
                        "premise": str(series["premise"]),
                        "revision": self._integer(series["revision"]),
                        "items": [
                            {
                                "task_id": str(item["task_id"]),
                                "position": self._integer(item["position"]),
                                "title": content.outline,
                            }
                            for item, content in validated_items
                        ],
                    }
                )
        return result

    def create_series(self, scope: TrustedScope, title: str, premise: str) -> dict[str, object]:
        series_id = uuid4()
        with self._content_tx(scope) as cursor:
            logical_account_id = self._logical_account_id(cursor, scope)
            cursor.execute(
                """
                INSERT INTO content_series
                    (id, tenant_id, brand_id, account_id,
                     logical_account_id, created_by, title, premise)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    series_id,
                    scope.tenant_id,
                    scope.brand_id,
                    scope.account_id,
                    logical_account_id,
                    scope.user_id,
                    title,
                    premise,
                ),
            )
            self._event(cursor, scope, "content_series.created", "content_series", series_id)
        return {
            "id": str(series_id),
            "title": title,
            "premise": premise,
            "revision": 1,
            "items": [],
        }

    def add_series_item(
        self, scope: TrustedScope, series_id: UUID, task_id: UUID, position: int | None
    ) -> dict[str, object]:
        with self._content_tx(scope) as cursor:
            logical_account_id = self._logical_account_id(cursor, scope)
            existing = self._series_task_ids(cursor, scope, series_id)
            cursor.execute(
                """
                SELECT id FROM business_tasks
                WHERE tenant_id = %s AND id = %s AND brand_id = %s
                  AND created_by = %s AND logical_account_id = %s
                """,
                (
                    scope.tenant_id,
                    task_id,
                    scope.brand_id,
                    scope.user_id,
                    logical_account_id,
                ),
            )
            self._one(cursor, "只能把当前发布账号的内容纳入系列")
            if task_id in existing:
                raise DomainError("这份内容已在当前系列中。")
            insert_at = len(existing) if position is None else position - 1
            if not 0 <= insert_at <= len(existing):
                raise DomainError("系列插入位置无效。")
            existing.insert(insert_at, task_id)
            self._replace_series_items(cursor, scope, series_id, existing)
            self._increment_series_revision(cursor, scope, series_id)
            self._event(cursor, scope, "content_series.item_added", "content_series", series_id)
        return self._series_value(scope, series_id)

    def reorder_series(self, scope: TrustedScope, series_id: UUID, task_ids: tuple[UUID, ...]) -> dict[str, object]:
        with self._content_tx(scope) as cursor:
            existing = self._series_task_ids(cursor, scope, series_id)
            if len(task_ids) != len(existing) or set(task_ids) != set(existing):
                raise DomainError("只能重排当前系列已有的内容。")
            self._replace_series_items(cursor, scope, series_id, list(task_ids))
            self._increment_series_revision(cursor, scope, series_id)
            self._event(cursor, scope, "content_series.reordered", "content_series", series_id)
        return self._series_value(scope, series_id)

    def reset_series(self, scope: TrustedScope, series_id: UUID) -> dict[str, object]:
        with self._content_tx(scope) as cursor:
            self._series_task_ids(cursor, scope, series_id)
            cursor.execute(
                "DELETE FROM content_series_items WHERE tenant_id = %s AND series_id = %s",
                (scope.tenant_id, series_id),
            )
            self._increment_series_revision(cursor, scope, series_id)
            self._event(cursor, scope, "content_series.reset", "content_series", series_id)
        return self._series_value(scope, series_id)

    def list_materials(self, scope: TrustedScope) -> list[dict[str, object]]:
        with self._content_tx(scope) as cursor:
            cursor.execute(
                """
                SELECT m.id, m.title, m.media_type, m.scope, m.created_at, m.status,
                       m.original_filename, m.byte_size, m.checksum_sha256, m.reference_version,
                       m.reference_note, m.visibility_scope
                FROM material_assets m
                WHERE m.tenant_id = %s AND m.brand_id = %s AND m.status = 'active'
                  AND (
                    (m.scope = 'personal' AND m.owner_user_id = %s)
                    OR (
                      m.scope = 'organization'
                      AND (
                        m.visibility_scope = 'brand_all'
                        OR EXISTS (
                          SELECT 1
                          FROM content_accounts target_account
                          JOIN content_accounts root_account
                            ON root_account.tenant_id = target_account.tenant_id
                           AND root_account.id = COALESCE(
                                 target_account.carrier_of_account_id,
                                 target_account.id
                               )
                          JOIN material_asset_scope_organizations material_scope
                            ON material_scope.tenant_id = m.tenant_id
                           AND material_scope.asset_id = m.id
                           AND material_scope.organization_id =
                               root_account.control_organization_id
                          JOIN organizations scoped_organization
                            ON scoped_organization.tenant_id = material_scope.tenant_id
                           AND scoped_organization.id = material_scope.organization_id
                          WHERE target_account.tenant_id = %s
                            AND target_account.id = %s
                            AND (
                              m.visibility_scope = 'organizations'
                              OR (
                                m.visibility_scope = 'headquarters'
                                AND scoped_organization.organization_level = 'company'
                              )
                            )
                        )
                      )
                    )
                  )
                ORDER BY m.created_at DESC
                """,
                (
                    scope.tenant_id,
                    scope.brand_id,
                    scope.user_id,
                    scope.tenant_id,
                    scope.account_id,
                ),
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
                "reference_note": str(row["reference_note"]),
                "visibility_scope": str(row["visibility_scope"]),
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
        reference_note: str = "",
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
                    (id, tenant_id, brand_id, scope, owner_user_id,
                     owner_organization_id, title, media_type, object_key,
                     byte_size, original_filename, checksum_sha256,
                     reference_note, visibility_scope)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s)
                RETURNING id, title, media_type, scope, created_at, status, original_filename, byte_size, checksum_sha256, reference_version, reference_note
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
                    reference_note,
                    "organizations" if asset_scope == "organization" else "brand_all",
                ),
            )
            row = self._one(cursor, "素材元数据没有保存成功")
            if owner_organization_id is not None:
                cursor.execute(
                    """
                    INSERT INTO material_asset_scope_organizations
                      (id, asset_id, tenant_id, organization_id)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (uuid4(), asset_id, scope.tenant_id, owner_organization_id),
                )
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
            "reference_note": str(row["reference_note"]),
            "visibility_scope": ("organizations" if asset_scope == "organization" else "personal"),
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
        logical_account_id = self._logical_account_id(cursor, scope)
        cursor.execute(
            """
            SELECT series.id FROM content_series series
            WHERE series.tenant_id = %s AND series.id = %s AND series.brand_id = %s
              AND series.created_by = %s AND series.logical_account_id = %s
            """,
            (
                scope.tenant_id,
                series_id,
                scope.brand_id,
                scope.user_id,
                logical_account_id,
            ),
        )
        self._one(cursor, "找不到当前内容系列")
        cursor.execute(
            """
            SELECT item.task_id FROM content_series_items item
            JOIN business_tasks task ON task.id = item.task_id AND task.tenant_id = item.tenant_id
            WHERE item.tenant_id = %s AND item.series_id = %s
              AND task.logical_account_id = %s
            ORDER BY item.position
            """,
            (scope.tenant_id, series_id, logical_account_id),
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

    @staticmethod
    def _increment_series_revision(
        cursor: psycopg.Cursor[dict[str, object]],
        scope: TrustedScope,
        series_id: UUID,
    ) -> None:
        cursor.execute(
            "UPDATE content_series SET revision = revision + 1 WHERE tenant_id = %s AND id = %s",
            (scope.tenant_id, series_id),
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

    def _logical_account_id(
        self,
        cursor: psycopg.Cursor[dict[str, object]],
        scope: TrustedScope,
    ) -> UUID:
        cursor.execute(
            """
            SELECT COALESCE(account.carrier_of_account_id, account.id) AS logical_account_id
            FROM content_accounts account
            WHERE account.tenant_id = %s AND account.brand_id = %s
              AND account.id = %s AND account.enabled = true
            """,
            (scope.tenant_id, scope.brand_id, scope.account_id),
        )
        row = self._one(cursor, "找不到当前逻辑发布账号")
        return UUID(str(row["logical_account_id"]))

    @staticmethod
    def _platform_targets(
        physical_targets: list[object],
    ) -> list[dict[str, object]]:
        result: list[dict[str, object]] = []
        for raw_target in physical_targets:
            if not isinstance(raw_target, dict):
                continue
            account_id = str(raw_target.get("id") or "")
            channel = str(raw_target.get("channel") or "")
            enabled = bool(raw_target.get("enabled"))
            definitions = {
                "抖音": (("douyin_video", "抖音", "视频"),),
                "小红书": (
                    ("xiaohongshu_graphic", "小红书", "图文"),
                    ("xiaohongshu_video", "小红书", "视频"),
                ),
                "微信视频号": (("wechat_channels_video", "微信视频号", "视频"),),
            }.get(channel, ())
            for target, platform, media in definitions:
                result.append(
                    {
                        "account_id": account_id,
                        "target": target,
                        "platform": platform,
                        "media": media,
                        "enabled": enabled,
                    }
                )
        return result

    @staticmethod
    def _mapping_list(value: object) -> list[dict[str, object]]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    def _expression_path_evidence(
        self,
        path_state: dict[str, object],
        path: dict[str, object] | None,
    ) -> list[dict[str, object]]:
        evidence: list[dict[str, object]] = []
        if path_state["baseline_id"] is not None:
            evidence.append(
                {
                    "source": "当前品牌表达基线",
                    "resource_id": str(path_state["baseline_id"]),
                    "version": f"V{self._integer(path_state['baseline_version'])}",
                    "version_id": None,
                    "scope": "当前品牌",
                    "updated_at": (
                        self._evidence_time(path_state["baseline_updated_at"])
                        if path_state["baseline_updated_at"] is not None
                        else None
                    ),
                    "updated_at_label": "当前对象未记录更新时间",
                }
            )
        if path is not None:
            evidence.append(
                {
                    "source": (
                        f"{str(path['account_name'])} · "
                        f"{str(path['content_role_name'])} · "
                        f"操作者 {str(path['operator_name'])}"
                    ),
                    "resource_id": str(path["account_id"]),
                    "version": f"五段画像 V{self._integer(path['profile_version'])}",
                    "version_id": str(path["profile_version_id"]),
                    "scope": (
                        f"{str(path['control_organization_name'])}"
                        "（逻辑发布账号控制组织）"
                    ),
                    "updated_at": self._evidence_time(path["profile_created_at"]),
                    "updated_at_label": "",
                }
            )
        return evidence

    def _library_path_evidence(
        self,
        path: dict[str, object],
    ) -> dict[str, object]:
        return {
            "source": str(path["title"]),
            "resource_id": str(path["entry_id"]),
            "version": (
                f"{str(path['version_label'])}（版本 "
                f"{self._integer(path['version_number'])}）"
            ),
            "version_id": str(path["version_id"]),
            "scope": (
                f"{str(path['control_organization_name'])}可见 · "
                f"{self._visibility_name(str(path['visibility_scope']))}"
            ),
            "updated_at": self._evidence_time(path["version_created_at"]),
            "updated_at_label": "",
        }

    def _product_path_evidence(
        self,
        path: dict[str, object],
    ) -> dict[str, object]:
        return {
            "source": f"{str(path['display_name'])}（{str(path['sku'])}）",
            "resource_id": str(path["product_id"]),
            "version": f"商品事实 V{self._integer(path['version_number'])}",
            "version_id": str(path["version_id"]),
            "scope": (
                f"{str(path['control_organization_name'])}可用 · "
                f"{self._visibility_name(str(path['visibility_scope']))}"
            ),
            "updated_at": self._evidence_time(path["version_created_at"]),
            "updated_at_label": "",
        }

    def _platform_path_evidence(
        self,
        path: dict[str, object],
    ) -> dict[str, object]:
        return {
            "source": (
                f"{str(path['account_name'])}的启用平台与形式目标："
                f"{self._integer(path.get('target_count'))} 个"
            ),
            "resource_id": str(path["account_id"]),
            "version": "不适用（平台目标未版本化）",
            "version_id": None,
            "scope": str(path["control_organization_name"]),
            "updated_at": None,
            "updated_at_label": "当前平台目标未记录更新时间",
        }

    def _series_path_evidence(
        self,
        path: dict[str, object],
    ) -> dict[str, object]:
        return {
            "source": str(path["title"]),
            "resource_id": str(path["series_id"]),
            "version": f"系列修订 {self._integer(path['revision'])}",
            "version_id": None,
            "scope": str(path["account_name"]),
            "updated_at": self._evidence_time(path["created_at"]),
            "updated_at_label": "",
        }

    def _display_path_evidence(
        self,
        path: dict[str, object],
    ) -> list[dict[str, object]]:
        scope_label = str(path["execution_organization_name"])
        return [
            {
                "source": str(path["store_name"]),
                "resource_id": str(path["store_id"]),
                "version": f"门店档案 {str(path['profile_version'])}",
                "version_id": None,
                "scope": scope_label,
                "updated_at": None,
                "updated_at_label": "当前对象未记录更新时间",
            },
            {
                "source": f"陈列成员 {str(path['user_name'])}",
                "resource_id": str(path["user_id"]),
                "version": "不适用（成员资格未版本化）",
                "version_id": None,
                "scope": scope_label,
                "updated_at": None,
                "updated_at_label": "当前对象未记录更新时间",
            },
            {
                "source": str(path["display_name"]),
                "resource_id": str(path["product_id"]),
                "version": f"商品事实 V{self._integer(path['version_number'])}",
                "version_id": str(path["version_id"]),
                "scope": (
                    f"{scope_label}可用 · "
                    f"{self._visibility_name(str(path['visibility_scope']))}"
                ),
                "updated_at": self._evidence_time(path["version_created_at"]),
                "updated_at_label": "",
            },
        ]

    @staticmethod
    def _visibility_name(visibility_scope: str) -> str:
        return {
            "brand_all": "品牌全员",
            "headquarters": "总部专用",
            "organizations": "指定区域",
        }.get(visibility_scope, "当前登记范围")

    @staticmethod
    def _condition_status(available: bool, conditional: bool) -> str:
        if available:
            return "available"
        if conditional:
            return "conditional"
        return "unavailable"

    @staticmethod
    def _diagnosis(
        stable_id: str,
        title: str,
        status: str,
        evidence: list[str],
        gaps: list[str],
        impact: str,
        action_label: str,
        action_section: str,
        common: dict[str, object],
        *,
        evidence_details: list[dict[str, object]] | None = None,
        conflicts: list[str] | None = None,
        unaffected: list[str] | None = None,
    ) -> dict[str, object]:
        return {
            "id": stable_id,
            "title": title,
            "status": status,
            "evidence": evidence,
            "evidence_details": evidence_details or [],
            "gaps": gaps,
            "conflicts": conflicts or [],
            "impact": impact,
            "unaffected": unaffected or [],
            "action": {"label": action_label, "section": action_section},
            **common,
        }

    @staticmethod
    def _validated_scope_organizations(
        cursor: psycopg.Cursor[dict[str, object]],
        tenant_id: UUID,
        visibility_scope: str,
        organization_ids: tuple[UUID, ...],
        resource_label: str,
    ) -> list[dict[str, object]]:
        if visibility_scope not in {"brand_all", "headquarters", "organizations"}:
            raise DomainError(
                f"{resource_label}范围只能选择品牌全员、总部专用或指定区域。"
            )
        unique_ids = tuple(dict.fromkeys(organization_ids))
        organizations: list[dict[str, object]] = []
        if unique_ids:
            cursor.execute(
                """
                SELECT id, name, organization_level
                FROM organizations
                WHERE tenant_id = %s AND id = ANY(%s)
                ORDER BY name
                """,
                (tenant_id, list(unique_ids)),
            )
            organizations = cursor.fetchall()
            if len(organizations) != len(unique_ids):
                raise DomainError(
                    f"{resource_label}范围只能选择当前租户已有的组织。"
                )
        if visibility_scope == "brand_all" and organizations:
            raise DomainError(f"品牌全员{resource_label}不需要指定组织。")
        if visibility_scope == "headquarters":
            if len(organizations) != 1:
                raise DomainError(
                    f"总部专用{resource_label}需要明确选择一个公司级组织。"
                )
            if str(organizations[0]["organization_level"]) != "company":
                raise DomainError(
                    f"总部专用{resource_label}只能绑定明确登记的公司级组织。"
                )
        if visibility_scope == "organizations" and not organizations:
            raise DomainError(f"指定区域{resource_label}至少需要选择一个具体区域。")
        if visibility_scope == "organizations" and any(
            str(organization["organization_level"]) != "region"
            for organization in organizations
        ):
            raise DomainError(
                f"指定区域{resource_label}只能绑定明确登记的区域；门店或公司级组织不能代替区域。"
            )
        return organizations

    @staticmethod
    def _scope_projection(
        organizations: list[dict[str, object]],
    ) -> list[dict[str, str]]:
        return [
            {
                "id": str(organization["id"]),
                "name": str(organization["name"]),
                "level": str(organization["organization_level"]),
            }
            for organization in organizations
        ]

    @staticmethod
    def _visibility_label(
        visibility_scope: str,
        raw_organizations: object,
    ) -> str:
        if visibility_scope == "brand_all":
            return "品牌全员"
        if visibility_scope == "headquarters":
            return "总部专用"
        organizations = raw_organizations if isinstance(raw_organizations, list) else []
        if len(organizations) == 1 and isinstance(organizations[0], dict):
            return f"{organizations[0].get('name', '指定区域')}可用"
        return "指定区域可用"

    @staticmethod
    def _library_impact(category: str) -> str:
        return {
            "brand_expression": "改善品牌与账号表达",
            "product": "改善需要具体商品事实的内容",
            "organization_fact": "改善组织、区域或门店事实相关内容",
            "reference": "为内容创作提供候选参考资料",
            "official_material": "为获准创作者提供组织官方素材",
        }.get(category, "为当前品牌资料提供有来源的候选参考")

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
    def _evidence_time(value: object) -> str:
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, str) and value:
            return value
        raise DomainError("诊断依据时间无效")

    @staticmethod
    def _display_title(body: str) -> str:
        lines = [line.strip("# ") for line in body.splitlines() if line.strip()]
        return lines[0] if lines else "墙面双层挂杆方案"
