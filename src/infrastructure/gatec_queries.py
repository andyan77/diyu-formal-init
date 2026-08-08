"""Static Gate C SQL contracts kept outside orchestration functions."""

PROJECTION_TASK_CONTEXT_SQL = """
SELECT projection.id AS projection_id,
       projection.version_number AS projection_version,
       projection.digest AS projection_digest,
       projection.contract_version AS projection_contract_version,
       item.id AS item_id, item.tenant_id AS item_tenant_id,
       item.brand_id AS item_brand_id, item.position,
       item.publication_role, item.published_text,
       item.applicability, item.source_kind,
       item.source_ref, item.source_version,
       item.source_digest, item.visibility_scope,
       item.scope_organization_ids, item.effective_at,
       item.expires_at, item.authority_class,
       item.semantic_subject_type, item.semantic_subject_id,
       item.claim_key, item.scope_contract_version,
       root_account.id AS logical_account_id,
       root_account.control_organization_id,
       transaction_timestamp() AS task_context_as_of,
       segment.document_id, segment.document_version_id,
       document_version.normalized_sha256 AS source_document_digest,
       qualification.id AS qualification_id,
       qualification.path_family AS qualification_path_family,
       qualification.organization_id AS qualification_organization_id,
       qualification.involves_person,
       qualification.qualification_version,
       qualification.source_digest AS qualification_source_digest,
       qualification.digest AS qualification_digest,
       authz.id AS authorization_id,
       authz.authorization_version,
       authz.subject_ref AS authorization_subject_ref,
       authz.tenant_id AS authorization_tenant_id,
       authz.brand_id AS authorization_brand_id,
       authz.logical_account_id AS authorization_logical_account_id,
       authz.organization_id AS authorization_organization_id,
       authz.allowed_source_digest,
       authz.allowed_usage,
       authz.single_use,
       authz.effective_at AS authorization_effective_at,
       authz.expires_at AS authorization_expires_at,
       authz.authorization_state,
       authz.digest AS authorization_digest,
       reservation.status AS authorization_reservation_status
  FROM brands brand
  JOIN content_accounts target_account
    ON target_account.tenant_id = brand.tenant_id
   AND target_account.brand_id = brand.id
   AND target_account.id = %s
   AND target_account.enabled = true
  JOIN content_accounts root_account
    ON root_account.tenant_id = target_account.tenant_id
   AND root_account.brand_id = target_account.brand_id
   AND root_account.id = COALESCE(
       target_account.carrier_of_account_id,
       target_account.id
   )
   AND root_account.enabled = true
  JOIN brand_publication_projections projection
    ON projection.tenant_id = brand.tenant_id
   AND projection.brand_id = brand.id
   AND projection.id = brand.current_publication_projection_id
   AND projection.status = 'confirmed'
  JOIN brand_publication_projection_items item
    ON item.tenant_id = projection.tenant_id
   AND item.brand_id = projection.brand_id
   AND item.projection_id = projection.id
  LEFT JOIN brand_source_segments segment
    ON segment.tenant_id = item.tenant_id
   AND segment.brand_id = item.brand_id
   AND segment.id = item.source_segment_id
  LEFT JOIN brand_source_document_versions document_version
    ON document_version.tenant_id = segment.tenant_id
   AND document_version.brand_id = segment.brand_id
   AND document_version.id = segment.document_version_id
  LEFT JOIN brand_relevance_qualifications qualification
    ON qualification.tenant_id = item.tenant_id
   AND qualification.brand_id = item.brand_id
   AND qualification.projection_id = item.projection_id
   AND qualification.projection_item_id = item.id
  LEFT JOIN content_authorizations authz
    ON authz.tenant_id = qualification.tenant_id
   AND authz.id = qualification.authorization_id
  LEFT JOIN content_authorization_reservations reservation
    ON reservation.tenant_id = authz.tenant_id
   AND reservation.brand_id = authz.brand_id
   AND reservation.authorization_id = authz.id
 WHERE brand.tenant_id = %s
   AND brand.id = %s
   AND (
       item.scope_contract_version = 'publication-item-scope-v1'
       OR (
           item.scope_contract_version = 'publication-item-scope-v2'
           AND item.effective_at <= transaction_timestamp()
           AND (item.expires_at IS NULL OR transaction_timestamp() < item.expires_at)
           AND (
               item.visibility_scope = 'brand_all'
               OR (
                   item.visibility_scope = 'headquarters'
                   AND root_account.control_organization_id = ANY(item.scope_organization_ids)
               )
               OR (
                   item.visibility_scope = 'organizations'
                   AND root_account.control_organization_id IS NOT NULL
                   AND EXISTS (
                       SELECT 1
                       FROM unnest(item.scope_organization_ids) AS scoped_organization_id
                       WHERE organization_is_same_or_descendant(
                           item.tenant_id,
                           root_account.control_organization_id,
                           scoped_organization_id
                       )
                   )
               )
           )
       )
   )
   AND (
       qualification.id IS NULL
       OR qualification.authorization_id IS NULL
       OR authz.logical_account_id = root_account.id
   )
 ORDER BY item.position
"""

PROJECTION_V2_ITEMS_SQL = """
SELECT position, publication_role, published_text,
       applicability, source_kind, source_ref,
       source_version, source_digest, visibility_scope,
       scope_organization_ids, effective_at, expires_at,
       authority_class, semantic_subject_type,
       semantic_subject_id, claim_key, scope_contract_version
  FROM brand_publication_projection_items
 WHERE tenant_id = %s AND brand_id = %s AND projection_id = %s
 ORDER BY position
"""

ROOT_TASK_LINEAGE_SQL = """
WITH RECURSIVE lineage(task_id, parent_version_id) AS (
    SELECT source_task.id, source_task.parent_version_id
      FROM content_versions source_version
      JOIN business_tasks source_task
        ON source_task.tenant_id = source_version.tenant_id
       AND source_task.id = source_version.task_id
     WHERE source_version.tenant_id = %s AND source_version.id = %s
    UNION ALL
    SELECT parent_task.id, parent_task.parent_version_id
      FROM lineage child
      JOIN content_versions parent_version
        ON parent_version.tenant_id = %s
       AND parent_version.id = child.parent_version_id
      JOIN business_tasks parent_task
        ON parent_task.tenant_id = parent_version.tenant_id
       AND parent_task.id = parent_version.task_id
)
SELECT task_id FROM lineage WHERE parent_version_id IS NULL
"""

AUTHORIZATION_FOR_UPDATE_SQL = """
SELECT id, tenant_id, brand_id, logical_account_id, organization_id,
       subject_ref, authorization_version, allowed_source_digest,
       allowed_usage, single_use, effective_at, expires_at,
       authorization_state, digest
  FROM content_authorizations
 WHERE tenant_id = %s AND brand_id = %s AND id = %s
 FOR UPDATE
"""

AUTHORIZATION_RESERVATION_SQL = """
SELECT status, task_lineage_id
  FROM content_authorization_reservations
 WHERE tenant_id = %s AND brand_id = %s AND authorization_id = %s
 FOR UPDATE
"""

AUTHORIZATION_RESERVATION_UPSERT_SQL = """
INSERT INTO content_authorization_reservations (
    authorization_id, tenant_id, brand_id, task_id, run_id, task_lineage_id,
    status, actor_id, reserved_at, reservation_digest
) VALUES (%s, %s, %s, %s, %s, %s, 'reserved', %s,
          transaction_timestamp(), %s)
ON CONFLICT (authorization_id) DO UPDATE
   SET task_id = EXCLUDED.task_id,
       run_id = EXCLUDED.run_id,
       task_lineage_id = EXCLUDED.task_lineage_id,
       status = 'reserved',
       actor_id = EXCLUDED.actor_id,
       reserved_at = transaction_timestamp(),
       finalized_at = NULL,
       reservation_digest = EXCLUDED.reservation_digest
 WHERE content_authorization_reservations.tenant_id = EXCLUDED.tenant_id
   AND content_authorization_reservations.brand_id = EXCLUDED.brand_id
   AND content_authorization_reservations.status = 'released'
"""

AUTHORIZATION_RELEASE_SQL = """
SELECT authorization_id, task_lineage_id
  FROM content_authorization_reservations
 WHERE tenant_id = %s AND brand_id = %s
   AND task_id = %s AND run_id = %s AND status = 'reserved'
 FOR UPDATE
"""
