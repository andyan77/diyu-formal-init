"""Add scope-aware publication items and durable authorization governance.

Revision ID: 20260818_45
Revises: 20260817_44

The schema is expand-forward only.  Existing publication rows retain their
V1 digest and brand-wide compatibility meaning.  V2 scope, lifecycle,
conflict, feedback and authorization facts are additive and are never removed
by an application rollback.
"""

from alembic import op

revision = "20260818_45"
down_revision = "20260817_44"
branch_labels = None
depends_on = None


_NEW_TENANT_TABLES = (
    "brand_feedback_observations",
    "content_authorizations",
    "content_authorization_reservations",
    "content_authorization_events",
    "brand_relevance_qualifications",
    "brand_publication_claim_conflicts",
)


def _tenant_rls(table: str, privileges: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {table}_tenant_scope ON {table} "
        "USING (tenant_id = current_setting('app.tenant_id')::uuid) "
        "WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid)"
    )
    op.execute(f"GRANT {privileges} ON {table} TO diyu_app")


def _immutable(table: str) -> None:
    op.execute(
        f"CREATE TRIGGER {table}_immutable "
        f"BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW "
        "EXECUTE FUNCTION reject_gatec_immutable_mutation()"
    )


def upgrade() -> None:
    # Projection-level identity stays where it already lives.  Only the
    # contract discriminator is added here; scope and time belong to items.
    op.execute(
        "ALTER TABLE brand_publication_projections "
        "ADD COLUMN contract_version text NOT NULL "
        "DEFAULT 'brand-publication-projection-v1'"
    )
    op.execute(
        "ALTER TABLE brand_publication_projections ADD CONSTRAINT "
        "brand_publication_projection_contract_version_check CHECK "
        "(contract_version IN ("
        "'brand-publication-projection-v1', "
        "'brand-publication-projection-v2'))"
    )
    op.execute(
        "ALTER TABLE brand_publication_projection_items ADD COLUMN visibility_scope text NOT NULL DEFAULT 'brand_all'"
    )
    op.execute(
        "ALTER TABLE brand_publication_projection_items ADD COLUMN scope_organization_ids uuid[] NOT NULL DEFAULT '{}'"
    )
    op.execute("ALTER TABLE brand_publication_projection_items ADD COLUMN effective_at timestamptz")
    op.execute("ALTER TABLE brand_publication_projection_items ADD COLUMN expires_at timestamptz")
    op.execute(
        "ALTER TABLE brand_publication_projection_items "
        "ADD COLUMN authority_class text NOT NULL DEFAULT 'legacy_compatibility'"
    )
    op.execute("ALTER TABLE brand_publication_projection_items ADD COLUMN semantic_subject_type text")
    op.execute("ALTER TABLE brand_publication_projection_items ADD COLUMN semantic_subject_id text")
    op.execute("ALTER TABLE brand_publication_projection_items ADD COLUMN claim_key text")
    op.execute(
        "ALTER TABLE brand_publication_projection_items "
        "ADD COLUMN scope_contract_version text NOT NULL "
        "DEFAULT 'publication-item-scope-v1'"
    )
    op.execute(
        "ALTER TABLE brand_publication_projection_items ADD CONSTRAINT "
        "brand_publication_item_scope_contract_check CHECK "
        "(scope_contract_version IN ("
        "'publication-item-scope-v1', 'publication-item-scope-v2'))"
    )
    op.execute(
        "ALTER TABLE brand_publication_projection_items ADD CONSTRAINT "
        "brand_publication_item_visibility_check CHECK "
        "(visibility_scope IN ('brand_all', 'headquarters', 'organizations'))"
    )
    op.execute(
        "ALTER TABLE brand_publication_projection_items ADD CONSTRAINT "
        "brand_publication_item_authority_check CHECK "
        "(authority_class IN ("
        "'legacy_compatibility', 'headquarters_formal', "
        "'local_formal', 'local_ordinary', 'expression_governance'))"
    )
    op.execute(
        "ALTER TABLE brand_publication_projection_items ADD CONSTRAINT "
        "brand_publication_item_time_window_check CHECK "
        "(expires_at IS NULL OR effective_at IS NULL OR expires_at > effective_at)"
    )
    op.execute(
        "ALTER TABLE brand_publication_projection_items ADD CONSTRAINT "
        "brand_publication_item_v2_shape_check CHECK ("
        "scope_contract_version = 'publication-item-scope-v1' OR ("
        "effective_at IS NOT NULL "
        "AND authority_class <> 'legacy_compatibility' "
        "AND ((visibility_scope = 'brand_all' AND cardinality(scope_organization_ids) = 0) "
        "OR (visibility_scope IN ('headquarters', 'organizations') "
        "AND cardinality(scope_organization_ids) > 0)) "
        "AND (publication_role <> 'public_brand_fact' OR ("
        "length(btrim(semantic_subject_type)) > 0 "
        "AND length(btrim(claim_key)) > 0))))"
    )
    op.execute(
        "ALTER TABLE brand_publication_projection_items ADD CONSTRAINT "
        "brand_publication_item_observation_not_formal_source CHECK "
        "(source_kind <> 'brand_feedback_observation')"
    )
    op.execute(
        "ALTER TABLE brand_publication_projection_items ADD CONSTRAINT "
        "brand_publication_items_tenant_brand_id_gatec_key "
        "UNIQUE (tenant_id, brand_id, id)"
    )
    op.execute("ALTER TABLE business_tasks ADD CONSTRAINT business_tasks_tenant_id_id_gatec_key UNIQUE (tenant_id, id)")
    op.execute(
        "ALTER TABLE generation_runs ADD CONSTRAINT generation_runs_tenant_id_id_gatec_key UNIQUE (tenant_id, id)"
    )
    op.execute(
        "ALTER TABLE content_accounts ADD CONSTRAINT "
        "content_accounts_tenant_brand_id_gatec_key UNIQUE (tenant_id, brand_id, id)"
    )
    op.execute(
        "ALTER TABLE business_tasks ADD CONSTRAINT "
        "business_tasks_tenant_brand_id_gatec_key UNIQUE (tenant_id, brand_id, id)"
    )
    op.execute(
        "ALTER TABLE content_versions ADD CONSTRAINT content_versions_tenant_id_id_gatec_key UNIQUE (tenant_id, id)"
    )

    op.execute(
        """
        CREATE FUNCTION reject_gatec_immutable_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'Gate C governance facts are append-only';
        END
        $$
        """
    )

    op.execute(
        """
        CREATE TABLE brand_feedback_observations (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES tenants(id),
            brand_id uuid NOT NULL,
            source_task_id uuid NOT NULL,
            source_version_id uuid,
            source_account_id uuid NOT NULL,
            actor_id uuid NOT NULL,
            observation_payload jsonb NOT NULL,
            candidate_status text NOT NULL DEFAULT 'candidate'
                CHECK (candidate_status = 'candidate'),
            observation_digest text NOT NULL
                CHECK (observation_digest ~ '^[0-9a-f]{64}$'),
            recorded_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
            UNIQUE (tenant_id, id),
            FOREIGN KEY (tenant_id, brand_id) REFERENCES brands(tenant_id, id),
            FOREIGN KEY (tenant_id, brand_id, source_task_id)
                REFERENCES business_tasks(tenant_id, brand_id, id),
            FOREIGN KEY (tenant_id, source_version_id)
                REFERENCES content_versions(tenant_id, id),
            FOREIGN KEY (tenant_id, brand_id, source_account_id)
                REFERENCES content_accounts(tenant_id, brand_id, id),
            FOREIGN KEY (tenant_id, actor_id) REFERENCES users(tenant_id, id)
        )
        """
    )
    _tenant_rls("brand_feedback_observations", "SELECT, INSERT")
    _immutable("brand_feedback_observations")

    op.execute(
        """
        CREATE TABLE content_authorizations (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES tenants(id),
            brand_id uuid NOT NULL,
            logical_account_id uuid NOT NULL,
            organization_id uuid NOT NULL,
            subject_ref text NOT NULL CHECK (length(btrim(subject_ref)) > 0),
            authorization_version text NOT NULL
                CHECK (length(btrim(authorization_version)) > 0),
            allowed_source_digest text NOT NULL
                CHECK (allowed_source_digest ~ '^[0-9a-f]{64}$'),
            allowed_usage text[] NOT NULL CHECK (cardinality(allowed_usage) > 0),
            single_use boolean NOT NULL,
            effective_at timestamptz NOT NULL,
            expires_at timestamptz,
            authorization_state text NOT NULL DEFAULT 'active'
                CHECK (authorization_state IN ('active', 'revoked')),
            digest text NOT NULL CHECK (digest ~ '^[0-9a-f]{64}$'),
            recorded_by uuid NOT NULL,
            recorded_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
            UNIQUE (tenant_id, id),
            UNIQUE (tenant_id, brand_id, id),
            FOREIGN KEY (tenant_id, brand_id) REFERENCES brands(tenant_id, id),
            FOREIGN KEY (tenant_id, brand_id, logical_account_id)
                REFERENCES content_accounts(tenant_id, brand_id, id),
            FOREIGN KEY (tenant_id, organization_id)
                REFERENCES organizations(tenant_id, id),
            FOREIGN KEY (tenant_id, recorded_by) REFERENCES users(tenant_id, id),
            CHECK (expires_at IS NULL OR expires_at > effective_at)
        )
        """
    )
    # UPDATE is needed only for SELECT ... FOR UPDATE reservation locking;
    # the immutable trigger still rejects every content mutation.
    _tenant_rls("content_authorizations", "SELECT, INSERT, UPDATE")
    _immutable("content_authorizations")

    op.execute(
        """
        CREATE TABLE content_authorization_reservations (
            authorization_id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL,
            brand_id uuid NOT NULL,
            task_id uuid NOT NULL,
            run_id uuid NOT NULL,
            task_lineage_id uuid NOT NULL,
            status text NOT NULL CHECK (status IN ('reserved', 'released', 'consumed')),
            actor_id uuid NOT NULL,
            reserved_at timestamptz NOT NULL,
            finalized_at timestamptz,
            reservation_digest text NOT NULL
                CHECK (reservation_digest ~ '^[0-9a-f]{64}$'),
            UNIQUE (tenant_id, authorization_id),
            FOREIGN KEY (tenant_id, brand_id, authorization_id)
                REFERENCES content_authorizations(tenant_id, brand_id, id),
            FOREIGN KEY (tenant_id, brand_id, task_id)
                REFERENCES business_tasks(tenant_id, brand_id, id),
            FOREIGN KEY (tenant_id, brand_id, task_lineage_id)
                REFERENCES business_tasks(tenant_id, brand_id, id),
            FOREIGN KEY (tenant_id, run_id) REFERENCES generation_runs(tenant_id, id),
            FOREIGN KEY (tenant_id, actor_id) REFERENCES users(tenant_id, id),
            CHECK ((status = 'reserved' AND finalized_at IS NULL) OR
                   (status IN ('released', 'consumed') AND finalized_at IS NOT NULL))
        )
        """
    )
    _tenant_rls("content_authorization_reservations", "SELECT, INSERT, UPDATE")

    op.execute(
        """
        CREATE FUNCTION enforce_authorization_reservation_transition()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NEW.status <> 'reserved' THEN
                    RAISE EXCEPTION 'authorization reservation must start reserved';
                END IF;
                RETURN NEW;
            END IF;
            IF OLD.status = 'reserved' AND NEW.status IN ('released', 'consumed') THEN
                IF NEW.authorization_id <> OLD.authorization_id
                   OR NEW.tenant_id <> OLD.tenant_id
                   OR NEW.brand_id <> OLD.brand_id
                   OR NEW.task_id <> OLD.task_id
                   OR NEW.run_id <> OLD.run_id
                   OR NEW.task_lineage_id <> OLD.task_lineage_id
                   OR NEW.reserved_at <> OLD.reserved_at THEN
                    RAISE EXCEPTION 'authorization reservation identity is immutable';
                END IF;
                RETURN NEW;
            END IF;
            IF OLD.status = 'released' AND NEW.status = 'reserved' THEN
                IF NEW.authorization_id <> OLD.authorization_id
                   OR NEW.tenant_id <> OLD.tenant_id
                   OR NEW.brand_id <> OLD.brand_id THEN
                    RAISE EXCEPTION 'authorization identity is immutable';
                END IF;
                RETURN NEW;
            END IF;
            RAISE EXCEPTION 'invalid authorization reservation transition';
        END
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER content_authorization_reservation_transition "
        "BEFORE INSERT OR UPDATE OR DELETE ON content_authorization_reservations "
        "FOR EACH ROW EXECUTE FUNCTION enforce_authorization_reservation_transition()"
    )

    op.execute(
        """
        CREATE TABLE content_authorization_events (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL,
            brand_id uuid NOT NULL,
            authorization_id uuid NOT NULL,
            task_id uuid NOT NULL,
            run_id uuid NOT NULL,
            task_lineage_id uuid NOT NULL,
            event_type text NOT NULL
                CHECK (event_type IN ('reserved', 'released', 'consumed')),
            actor_id uuid NOT NULL,
            event_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
            event_digest text NOT NULL CHECK (event_digest ~ '^[0-9a-f]{64}$'),
            UNIQUE (tenant_id, id),
            FOREIGN KEY (tenant_id, brand_id, authorization_id)
                REFERENCES content_authorizations(tenant_id, brand_id, id),
            FOREIGN KEY (tenant_id, brand_id, task_id)
                REFERENCES business_tasks(tenant_id, brand_id, id),
            FOREIGN KEY (tenant_id, brand_id, task_lineage_id)
                REFERENCES business_tasks(tenant_id, brand_id, id),
            FOREIGN KEY (tenant_id, run_id) REFERENCES generation_runs(tenant_id, id),
            FOREIGN KEY (tenant_id, actor_id) REFERENCES users(tenant_id, id)
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX content_authorization_one_consumption "
        "ON content_authorization_events (tenant_id, authorization_id) "
        "WHERE event_type = 'consumed'"
    )
    _tenant_rls("content_authorization_events", "SELECT, INSERT")
    _immutable("content_authorization_events")

    op.execute(
        """
        CREATE TABLE brand_relevance_qualifications (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES tenants(id),
            brand_id uuid NOT NULL,
            projection_id uuid NOT NULL,
            projection_item_id uuid NOT NULL,
            path_family text NOT NULL
                CHECK (path_family IN ('local_trust', 'organization_people')),
            organization_id uuid NOT NULL,
            involves_person boolean NOT NULL,
            authorization_id uuid,
            qualification_version text NOT NULL,
            source_digest text NOT NULL CHECK (source_digest ~ '^[0-9a-f]{64}$'),
            digest text NOT NULL CHECK (digest ~ '^[0-9a-f]{64}$'),
            created_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
            UNIQUE (tenant_id, projection_item_id, path_family),
            UNIQUE (tenant_id, id),
            FOREIGN KEY (tenant_id, brand_id, projection_id)
                REFERENCES brand_publication_projections(tenant_id, brand_id, id),
            FOREIGN KEY (tenant_id, projection_id, projection_item_id)
                REFERENCES brand_publication_projection_items(tenant_id, projection_id, id),
            FOREIGN KEY (tenant_id, organization_id)
                REFERENCES organizations(tenant_id, id),
            FOREIGN KEY (tenant_id, brand_id, authorization_id)
                REFERENCES content_authorizations(tenant_id, brand_id, id),
            CHECK (path_family <> 'organization_people' OR
                   (involves_person AND authorization_id IS NOT NULL)),
            CHECK (path_family <> 'local_trust' OR
                   NOT involves_person OR authorization_id IS NOT NULL)
        )
        """
    )
    _tenant_rls("brand_relevance_qualifications", "SELECT, INSERT")
    _immutable("brand_relevance_qualifications")

    op.execute(
        """
        CREATE TABLE brand_publication_claim_conflicts (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES tenants(id),
            brand_id uuid NOT NULL,
            projection_id uuid NOT NULL,
            left_item_id uuid NOT NULL,
            right_item_id uuid NOT NULL,
            semantic_subject_type text NOT NULL,
            semantic_subject_id text,
            claim_key text NOT NULL,
            authority_class text NOT NULL,
            review_state text NOT NULL CHECK (review_state = 'needs_review'),
            conflict_digest text NOT NULL CHECK (conflict_digest ~ '^[0-9a-f]{64}$'),
            detected_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
            UNIQUE (tenant_id, projection_id, left_item_id, right_item_id),
            UNIQUE (tenant_id, id),
            FOREIGN KEY (tenant_id, brand_id, projection_id)
                REFERENCES brand_publication_projections(tenant_id, brand_id, id),
            FOREIGN KEY (tenant_id, projection_id, left_item_id)
                REFERENCES brand_publication_projection_items(tenant_id, projection_id, id),
            FOREIGN KEY (tenant_id, projection_id, right_item_id)
                REFERENCES brand_publication_projection_items(tenant_id, projection_id, id)
        )
        """
    )
    _tenant_rls("brand_publication_claim_conflicts", "SELECT, INSERT")
    _immutable("brand_publication_claim_conflicts")

    op.execute(
        """
        CREATE FUNCTION publication_item_scopes_overlap(
            p_tenant_id uuid,
            p_left_scope text,
            p_left_ids uuid[],
            p_right_scope text,
            p_right_ids uuid[]
        ) RETURNS boolean
        LANGUAGE sql
        STABLE
        AS $$
            SELECT CASE
                WHEN p_left_scope = 'brand_all' OR p_right_scope = 'brand_all'
                    THEN true
                ELSE EXISTS (
                    SELECT 1
                    FROM unnest(p_left_ids) left_id
                    CROSS JOIN unnest(p_right_ids) right_id
                    WHERE left_id = right_id
                       OR organization_is_same_or_descendant(
                            p_tenant_id, left_id, right_id
                          )
                       OR organization_is_same_or_descendant(
                            p_tenant_id, right_id, left_id
                          )
                )
            END
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION validate_scope_aware_publication_item()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            matching_organizations integer;
            projection_contract text;
        BEGIN
            IF NEW.scope_contract_version = 'publication-item-scope-v1' THEN
                RETURN NEW;
            END IF;
            SELECT contract_version INTO projection_contract
              FROM brand_publication_projections
             WHERE tenant_id = NEW.tenant_id
               AND brand_id = NEW.brand_id
               AND id = NEW.projection_id;
            IF projection_contract <> 'brand-publication-projection-v2' THEN
                RAISE EXCEPTION 'scope-aware item requires projection v2';
            END IF;
            IF cardinality(NEW.scope_organization_ids) > 0 THEN
                SELECT count(DISTINCT organization.id) INTO matching_organizations
                  FROM organizations organization
                 WHERE organization.tenant_id = NEW.tenant_id
                   AND organization.id = ANY(NEW.scope_organization_ids);
                IF matching_organizations <> cardinality(NEW.scope_organization_ids) THEN
                    RAISE EXCEPTION 'publication item organization scope is invalid';
                END IF;
            END IF;
            IF NEW.visibility_scope = 'headquarters' AND EXISTS (
                SELECT 1 FROM organizations organization
                 WHERE organization.tenant_id = NEW.tenant_id
                   AND organization.id = ANY(NEW.scope_organization_ids)
                   AND organization.organization_level <> 'company'
            ) THEN
                RAISE EXCEPTION 'headquarters scope requires an exact company organization';
            END IF;
            RETURN NEW;
        END
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER brand_publication_item_scope_valid "
        "BEFORE INSERT ON brand_publication_projection_items "
        "FOR EACH ROW EXECUTE FUNCTION validate_scope_aware_publication_item()"
    )
    op.execute(
        """
        CREATE FUNCTION block_feedback_observation_as_formal_source()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM brand_feedback_observations observation
                 WHERE observation.tenant_id = NEW.tenant_id
                   AND observation.brand_id = NEW.brand_id
                   AND observation.id::text = NEW.source_ref
            ) THEN
                RAISE EXCEPTION 'feedback observation cannot be a formal projection source';
            END IF;
            RETURN NEW;
        END
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER brand_feedback_observation_not_formal_source "
        "BEFORE INSERT ON brand_publication_projection_items "
        "FOR EACH ROW EXECUTE FUNCTION block_feedback_observation_as_formal_source()"
    )
    op.execute(
        """
        CREATE FUNCTION detect_brand_publication_claim_conflict()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.scope_contract_version <> 'publication-item-scope-v2'
               OR NEW.claim_key IS NULL THEN
                RETURN NEW;
            END IF;
            INSERT INTO brand_publication_claim_conflicts (
                id, tenant_id, brand_id, projection_id,
                left_item_id, right_item_id,
                semantic_subject_type, semantic_subject_id,
                claim_key, authority_class, review_state, conflict_digest
            )
            SELECT gen_random_uuid(), NEW.tenant_id, NEW.brand_id, NEW.projection_id,
                   NEW.id, existing.id,
                   NEW.semantic_subject_type, NEW.semantic_subject_id,
                   NEW.claim_key, NEW.authority_class, 'needs_review',
                   encode(sha256(convert_to(
                       'publication-claim-conflict-v1|' || NEW.id::text || '|' ||
                       existing.id::text || '|' || NEW.source_digest || '|' ||
                       existing.source_digest,
                       'UTF8'
                   )), 'hex')
              FROM brand_publication_projection_items existing
             WHERE existing.tenant_id = NEW.tenant_id
               AND existing.brand_id = NEW.brand_id
               AND existing.projection_id = NEW.projection_id
               AND existing.id <> NEW.id
               AND existing.scope_contract_version = 'publication-item-scope-v2'
               AND existing.semantic_subject_type = NEW.semantic_subject_type
               AND existing.semantic_subject_id IS NOT DISTINCT FROM NEW.semantic_subject_id
               AND existing.claim_key = NEW.claim_key
               AND existing.authority_class = NEW.authority_class
               AND (existing.published_text <> NEW.published_text
                    OR existing.source_digest <> NEW.source_digest)
               AND publication_item_scopes_overlap(
                    NEW.tenant_id,
                    existing.visibility_scope,
                    existing.scope_organization_ids,
                    NEW.visibility_scope,
                    NEW.scope_organization_ids
               )
               AND COALESCE(existing.expires_at, 'infinity'::timestamptz) > NEW.effective_at
               AND COALESCE(NEW.expires_at, 'infinity'::timestamptz) > existing.effective_at
            ON CONFLICT DO NOTHING;
            RETURN NEW;
        END
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER brand_publication_item_conflict_detection "
        "AFTER INSERT ON brand_publication_projection_items "
        "FOR EACH ROW EXECUTE FUNCTION detect_brand_publication_claim_conflict()"
    )
    op.execute(
        """
        CREATE FUNCTION block_conflicted_projection_confirmation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.status = 'confirmed' AND OLD.status <> 'confirmed' AND EXISTS (
                SELECT 1 FROM brand_publication_claim_conflicts conflict
                 WHERE conflict.tenant_id = NEW.tenant_id
                   AND conflict.brand_id = NEW.brand_id
                   AND conflict.projection_id = NEW.id
                   AND conflict.review_state = 'needs_review'
            ) THEN
                RAISE EXCEPTION 'publication projection has claims needing review';
            END IF;
            IF NEW.contract_version <> OLD.contract_version THEN
                RAISE EXCEPTION 'publication projection contract version is immutable';
            END IF;
            RETURN NEW;
        END
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER brand_publication_projection_gatec_guard "
        "BEFORE UPDATE ON brand_publication_projections "
        "FOR EACH ROW EXECUTE FUNCTION block_conflicted_projection_confirmation()"
    )

    # Existing rows receive only V1 compatibility defaults: brand-wide,
    # unbounded lifetime and the exact historical digest.  No row is rewritten
    # into V2 and no prior digest acquires new fields.
    op.execute(
        "CREATE INDEX brand_publication_scope_lookup ON "
        "brand_publication_projection_items "
        "(tenant_id, brand_id, projection_id, visibility_scope, effective_at, expires_at)"
    )
    op.execute(
        "CREATE INDEX brand_publication_claim_lookup ON "
        "brand_publication_projection_items "
        "(tenant_id, brand_id, projection_id, semantic_subject_type, claim_key)"
    )
    op.execute(
        "CREATE INDEX brand_feedback_observations_task_idx ON "
        "brand_feedback_observations (tenant_id, brand_id, source_task_id, recorded_at)"
    )
    op.execute(
        "CREATE INDEX content_authorizations_scope_idx ON content_authorizations "
        "(tenant_id, brand_id, logical_account_id, organization_id, effective_at, expires_at)"
    )


def downgrade() -> None:
    raise RuntimeError(
        "BRAND-MATRIX Gate C governance is expand-forward only; "
        "database downgrade would delete scope, conflict and authorization history."
    )
