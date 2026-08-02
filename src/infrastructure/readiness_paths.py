from __future__ import annotations

import psycopg

from src.shared.errors import DomainError
from src.shared.types import TenantManagementScope


def readiness_path_state(
    cursor: psycopg.Cursor[dict[str, object]],
    scope: TenantManagementScope,
) -> dict[str, object]:
    """Project complete readiness paths without combining unrelated objects."""

    cursor.execute(
        """
        WITH params AS (
          SELECT %s::uuid AS tenant_id, %s::uuid AS brand_id
        ),
        publication AS (
          SELECT projection.id, projection.version_number AS version,
                 projection.status, projection.confirmed_at AS updated_at
          FROM params
          JOIN brands brand
            ON brand.tenant_id = params.tenant_id
           AND brand.id = params.brand_id
          JOIN brand_publication_projections projection
            ON projection.tenant_id = brand.tenant_id
           AND projection.brand_id = brand.id
           AND projection.id = brand.current_publication_projection_id
           AND projection.status = 'confirmed'
        ),
        target_channels AS (
          SELECT DISTINCT root.id AS account_id, physical.channel
          FROM params
          JOIN content_accounts root
            ON root.tenant_id = params.tenant_id
           AND root.brand_id = params.brand_id
           AND root.enabled = true
           AND root.business_data_kind = 'formal_business_data'
           AND root.carrier_of_account_id IS NULL
          JOIN content_accounts physical
            ON physical.tenant_id = root.tenant_id
           AND physical.brand_id = root.brand_id
           AND physical.enabled = true
           AND physical.platform_enabled = true
           AND physical.business_data_kind = 'formal_business_data'
           AND (
             physical.id = root.id
             OR physical.carrier_of_account_id = root.id
           )
        ),
        target_counts AS (
          SELECT account_id,
                 sum(
                   CASE channel
                     WHEN '小红书' THEN 2
                     WHEN '抖音' THEN 1
                     WHEN '微信视频号' THEN 1
                     ELSE 0
                   END
                 )::integer AS target_count
          FROM target_channels
          GROUP BY account_id
        ),
        expression_paths AS (
          SELECT DISTINCT ON (account.id)
                 account.id AS account_id,
                 account.name AS account_name,
                 account.control_organization_id,
                 control_organization.name AS control_organization_name,
                 role.id AS content_role_id,
                 role.name AS content_role_name,
                 profile.id AS profile_version_id,
                 profile.version AS profile_version,
                 profile.created_at AS profile_created_at,
                 operator.id AS operator_id,
                 operator.display_name AS operator_name,
                 COALESCE(target_counts.target_count, 0) AS target_count
          FROM params
          JOIN content_accounts account
            ON account.tenant_id = params.tenant_id
           AND account.brand_id = params.brand_id
           AND account.enabled = true
           AND account.carrier_of_account_id IS NULL
           AND account.control_organization_id IS NOT NULL
           AND account.current_expression_profile_id IS NOT NULL
           AND account.business_data_kind = 'formal_business_data'
          JOIN organizations control_organization
            ON control_organization.tenant_id = account.tenant_id
           AND control_organization.id = account.control_organization_id
           AND control_organization.business_data_kind = 'formal_business_data'
          JOIN account_content_roles account_role
            ON account_role.tenant_id = account.tenant_id
           AND account_role.account_id = account.id
          JOIN content_roles role
            ON role.tenant_id = account_role.tenant_id
           AND role.id = account_role.content_role_id
           AND role.brand_id = params.brand_id
          JOIN account_expression_profile_versions profile
            ON profile.tenant_id = account.tenant_id
           AND profile.account_id = account.id
           AND profile.id = account.current_expression_profile_id
           AND profile.content_role_id = role.id
          JOIN auth_grants grant_record
            ON grant_record.tenant_id = account.tenant_id
           AND grant_record.account_id = account.id
           AND grant_record.enabled = true
          JOIN users operator
            ON operator.tenant_id = grant_record.tenant_id
           AND operator.id = grant_record.user_id
           AND operator.enabled = true
           AND operator.entry_kind = 'tenant_user'
           AND operator.business_data_kind = 'formal_business_data'
          LEFT JOIN target_counts
            ON target_counts.account_id = account.id
          ORDER BY account.id, operator.display_name, operator.id
        ),
        product_paths AS (
          SELECT path.account_id, path.account_name,
                 path.control_organization_id,
                 path.control_organization_name,
                 product.id AS product_id, product.sku,
                 product.display_name, product.visibility_scope,
                 version.id AS version_id,
                 version.version_number,
                 version.created_at AS version_created_at
          FROM expression_paths path
          JOIN params ON true
          JOIN brand_products product
            ON product.tenant_id = params.tenant_id
           AND product.brand_id = params.brand_id
           AND product.status = 'active'
           AND product.current_version_id IS NOT NULL
           AND product.source_kind <> ''
           AND product.source_note <> ''
           AND product.facts <> '{}'::jsonb
           AND product.business_data_kind = 'formal_business_data'
          JOIN brand_product_versions version
            ON version.tenant_id = product.tenant_id
           AND version.product_id = product.id
           AND version.id = product.current_version_id
          WHERE product.visibility_scope = 'brand_all'
             OR EXISTS (
               SELECT 1
               FROM brand_product_scope_organizations product_scope
               JOIN organizations scoped_organization
                 ON scoped_organization.tenant_id = product_scope.tenant_id
                AND scoped_organization.id = product_scope.organization_id
               WHERE product_scope.tenant_id = product.tenant_id
                 AND product_scope.product_id = product.id
                 AND (
                   (
                     product.visibility_scope = 'organizations'
                     AND organization_is_same_or_descendant(
                           product.tenant_id,
                           path.control_organization_id,
                           product_scope.organization_id
                         )
                   )
                   OR (
                     product.visibility_scope = 'headquarters'
                     AND scoped_organization.organization_level = 'company'
                     AND product_scope.organization_id =
                         path.control_organization_id
                   )
                 )
             )
        ),
        library_paths AS (
          SELECT path.account_id, path.account_name,
                 path.control_organization_name,
                 entry.id AS entry_id, entry.title,
                 entry.visibility_scope,
                 version.id AS version_id,
                 version.version_number,
                 version.version_label,
                 version.created_at AS version_created_at
          FROM expression_paths path
          JOIN params ON true
          JOIN brand_library_entries entry
            ON entry.tenant_id = params.tenant_id
           AND entry.brand_id = params.brand_id
           AND entry.status = 'active'
           AND entry.current_version_id IS NOT NULL
           AND entry.business_data_kind = 'formal_business_data'
          JOIN brand_library_entry_versions version
            ON version.tenant_id = entry.tenant_id
           AND version.entry_id = entry.id
           AND version.id = entry.current_version_id
          WHERE entry.visibility_scope = 'brand_all'
             OR EXISTS (
               SELECT 1
               FROM brand_library_entry_organizations entry_scope
               JOIN organizations scoped_organization
                 ON scoped_organization.tenant_id = entry_scope.tenant_id
                AND scoped_organization.id = entry_scope.organization_id
               WHERE entry_scope.tenant_id = entry.tenant_id
                 AND entry_scope.entry_id = entry.id
                 AND (
                   (
                     entry.visibility_scope = 'organizations'
                     AND organization_is_same_or_descendant(
                           entry.tenant_id,
                           path.control_organization_id,
                           entry_scope.organization_id
                         )
                   )
                   OR (
                     entry.visibility_scope = 'headquarters'
                     AND scoped_organization.organization_level = 'company'
                     AND entry_scope.organization_id =
                         path.control_organization_id
                   )
                 )
             )
        ),
        series_paths AS (
          SELECT path.account_id, path.account_name,
                 series.id AS series_id, series.title,
                 series.revision, series.created_at
          FROM expression_paths path
          JOIN params ON true
          JOIN content_series series
            ON series.tenant_id = params.tenant_id
           AND series.brand_id = params.brand_id
           AND series.logical_account_id = path.account_id
           AND series.business_data_kind = 'formal_business_data'
        ),
        display_paths AS (
          SELECT DISTINCT ON (store.id)
                 store.id AS store_id, store.name AS store_name,
                 store.profile_version,
                 store.execution_organization_id,
                 execution_organization.name AS execution_organization_name,
                 display_user.id AS user_id,
                 display_user.display_name AS user_name,
                 product.id AS product_id, product.display_name,
                 product.visibility_scope,
                 version.id AS version_id,
                 version.version_number,
                 version.created_at AS version_created_at
          FROM params
          JOIN display_stores store
            ON store.tenant_id = params.tenant_id
           AND store.brand_id = params.brand_id
           AND store.enabled = true
           AND store.business_data_kind = 'formal_business_data'
          JOIN organizations execution_organization
            ON execution_organization.tenant_id = store.tenant_id
           AND execution_organization.id = store.execution_organization_id
           AND execution_organization.business_data_kind = 'formal_business_data'
          JOIN display_access_grants display_grant
            ON display_grant.tenant_id = store.tenant_id
           AND display_grant.enabled = true
          JOIN users display_user
            ON display_user.tenant_id = display_grant.tenant_id
           AND display_user.id = display_grant.user_id
           AND display_user.enabled = true
           AND display_user.entry_kind = 'tenant_user'
           AND display_user.organization_id =
               store.execution_organization_id
           AND display_user.business_data_kind = 'formal_business_data'
          JOIN brand_products product
            ON product.tenant_id = params.tenant_id
           AND product.brand_id = params.brand_id
           AND product.status = 'active'
           AND product.current_version_id IS NOT NULL
           AND product.source_kind <> ''
           AND product.source_note <> ''
           AND product.facts ? 'display_family'
           AND product.business_data_kind = 'formal_business_data'
          JOIN brand_product_versions version
            ON version.tenant_id = product.tenant_id
           AND version.product_id = product.id
           AND version.id = product.current_version_id
          WHERE product.visibility_scope = 'brand_all'
             OR EXISTS (
               SELECT 1
               FROM brand_product_scope_organizations product_scope
               JOIN organizations scoped_organization
                 ON scoped_organization.tenant_id = product_scope.tenant_id
                AND scoped_organization.id = product_scope.organization_id
               WHERE product_scope.tenant_id = product.tenant_id
                 AND product_scope.product_id = product.id
                 AND (
                   (
                     product.visibility_scope = 'organizations'
                     AND organization_is_same_or_descendant(
                           product.tenant_id,
                           store.execution_organization_id,
                           product_scope.organization_id
                         )
                   )
                   OR (
                     product.visibility_scope = 'headquarters'
                     AND scoped_organization.organization_level = 'company'
                     AND product_scope.organization_id =
                         store.execution_organization_id
                   )
                 )
             )
          ORDER BY store.id, display_user.display_name, product.display_name
        )
        SELECT
          (SELECT id FROM publication) AS publication_id,
          (SELECT version FROM publication) AS publication_version,
          COALESCE((SELECT status FROM publication), 'missing') AS publication_status,
          (SELECT updated_at FROM publication) AS publication_updated_at,
          COALESCE(
            (SELECT jsonb_agg(to_jsonb(path) ORDER BY path.account_name)
             FROM expression_paths path),
            '[]'::jsonb
          ) AS expression_paths,
          COALESCE(
            (SELECT jsonb_agg(to_jsonb(path)
                              ORDER BY path.account_name, path.display_name)
             FROM product_paths path),
            '[]'::jsonb
          ) AS product_paths,
          COALESCE(
            (SELECT jsonb_agg(to_jsonb(path)
                              ORDER BY path.account_name, path.title)
             FROM library_paths path),
            '[]'::jsonb
          ) AS library_paths,
          COALESCE(
            (SELECT jsonb_agg(to_jsonb(path)
                              ORDER BY path.account_name, path.title)
             FROM series_paths path),
            '[]'::jsonb
          ) AS series_paths,
          COALESCE(
            (SELECT jsonb_agg(to_jsonb(path) ORDER BY path.store_name)
             FROM display_paths path),
            '[]'::jsonb
          ) AS display_paths,
          (SELECT count(*) FROM target_counts
           WHERE target_count >= 2) AS multi_target_components
        """,
        (scope.tenant_id, scope.brand_id),
    )
    row = cursor.fetchone()
    if row is None:
        raise DomainError("无法读取当前可执行路径")
    return row
