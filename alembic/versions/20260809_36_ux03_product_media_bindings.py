"""Bind confirmed products to versioned organization media.

Revision ID: 20260809_36
Revises: 20260808_35

This migration is expand-only. Existing products, materials, tasks and media
envelopes are unchanged. New bindings are tenant-scoped, keep immutable
subjects, and can only be removed through an exact transaction-local synthetic
fixture maintenance boundary.
"""

from alembic import op

revision = "20260809_36"
down_revision = "20260808_35"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE product_media_bindings (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES tenants(id),
            brand_id uuid NOT NULL REFERENCES brands(id),
            product_id uuid NOT NULL REFERENCES brand_products(id),
            asset_id uuid NOT NULL REFERENCES material_assets(id),
            usage_kind text NOT NULL DEFAULT 'existing_product_media'
                CHECK (usage_kind = 'existing_product_media'),
            status text NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'inactive')),
            created_by uuid NOT NULL REFERENCES users(id),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (tenant_id, brand_id, product_id, asset_id)
        )
        """
    )
    op.execute(
        """
        CREATE FUNCTION validate_product_media_binding()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            product_tenant uuid;
            product_brand uuid;
            product_current_version uuid;
            asset_tenant uuid;
            asset_brand uuid;
            asset_scope text;
            asset_media_type text;
            asset_current_version uuid;
            creator_tenant uuid;
        BEGIN
            IF TG_OP = 'UPDATE' AND (
                NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
                OR NEW.brand_id IS DISTINCT FROM OLD.brand_id
                OR NEW.product_id IS DISTINCT FROM OLD.product_id
                OR NEW.asset_id IS DISTINCT FROM OLD.asset_id
                OR NEW.usage_kind IS DISTINCT FROM OLD.usage_kind
                OR NEW.created_by IS DISTINCT FROM OLD.created_by
                OR NEW.created_at IS DISTINCT FROM OLD.created_at
            ) THEN
                RAISE EXCEPTION 'product media binding subjects are immutable';
            END IF;

            SELECT product.tenant_id, product.brand_id,
                   product.current_version_id
              INTO product_tenant, product_brand, product_current_version
              FROM brand_products product
             WHERE product.id = NEW.product_id;
            SELECT asset.tenant_id, asset.brand_id, asset.scope,
                   asset.media_type, asset.current_version_id
              INTO asset_tenant, asset_brand, asset_scope,
                   asset_media_type, asset_current_version
             FROM material_assets asset
             WHERE asset.id = NEW.asset_id;
            SELECT user_record.tenant_id
              INTO creator_tenant
              FROM users user_record
             WHERE user_record.id = NEW.created_by;

            IF product_tenant IS DISTINCT FROM NEW.tenant_id
               OR product_brand IS DISTINCT FROM NEW.brand_id
               OR asset_tenant IS DISTINCT FROM NEW.tenant_id
               OR asset_brand IS DISTINCT FROM NEW.brand_id
               OR creator_tenant IS DISTINCT FROM NEW.tenant_id THEN
                RAISE EXCEPTION 'product media binding tenant or brand mismatch';
            END IF;
            IF product_current_version IS NULL
               OR asset_current_version IS NULL THEN
                RAISE EXCEPTION 'product media binding requires current versions';
            END IF;
            IF asset_scope IS DISTINCT FROM 'organization'
               OR asset_media_type NOT IN ('image', 'video') THEN
                RAISE EXCEPTION 'product media binding requires organization image or video';
            END IF;
            NEW.updated_at := now();
            RETURN NEW;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER product_media_binding_valid
        BEFORE INSERT OR UPDATE ON product_media_bindings
        FOR EACH ROW EXECUTE FUNCTION validate_product_media_binding()
        """
    )
    op.execute(
        """
        CREATE FUNCTION reject_product_media_binding_delete()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            table_owner name;
            synthetic_fixture boolean;
        BEGIN
            SELECT pg_get_userbyid(relation.relowner)
              INTO table_owner
              FROM pg_class relation
             WHERE relation.oid = TG_RELID;
            IF current_user <> table_owner
               AND current_user <> 'diyu_migrator' THEN
                RAISE EXCEPTION 'product media binding deletion requires the maintenance role';
            END IF;
            IF current_setting(
                   'diyu.product_media_binding_maintenance',
                   true
               ) IS DISTINCT FROM 'delete_synthetic_fixture'
               OR current_setting(
                   'diyu.product_media_binding_maintenance_transaction_id',
                   true
               ) IS DISTINCT FROM pg_current_xact_id()::text
               OR current_setting(
                   'diyu.product_media_binding_maintenance_tenant_id',
                   true
               ) IS DISTINCT FROM OLD.tenant_id::text
               OR current_setting(
                   'diyu.product_media_binding_maintenance_binding_id',
                   true
               ) IS DISTINCT FROM OLD.id::text THEN
                RAISE EXCEPTION 'product media binding deletion requires an exact transaction-local maintenance boundary';
            END IF;
            SELECT EXISTS (
                SELECT 1
                  FROM content_accounts account_record
                 WHERE account_record.tenant_id = OLD.tenant_id
                   AND account_record.brand_id = OLD.brand_id
                   AND account_record.business_data_kind =
                       'synthetic_business_fixture'
            ) INTO synthetic_fixture;
            IF synthetic_fixture IS DISTINCT FROM true THEN
                RAISE EXCEPTION 'only a synthetic fixture binding can be deleted';
            END IF;
            RETURN OLD;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER product_media_binding_no_delete
        BEFORE DELETE ON product_media_bindings
        FOR EACH ROW EXECUTE FUNCTION reject_product_media_binding_delete()
        """
    )
    op.execute("ALTER TABLE product_media_bindings ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE product_media_bindings FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY product_media_bindings_tenant_scope
        ON product_media_bindings
        USING (tenant_id = current_setting('app.tenant_id')::uuid)
        WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid)
        """
    )
    op.execute("GRANT SELECT, INSERT, UPDATE ON product_media_bindings TO diyu_app")
    op.execute(
        "CREATE INDEX product_media_bindings_asset_lookup "
        "ON product_media_bindings (tenant_id, brand_id, asset_id, status)"
    )
    op.execute(
        "CREATE INDEX product_media_bindings_product_lookup "
        "ON product_media_bindings (tenant_id, brand_id, product_id, status)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX product_media_bindings_product_lookup")
    op.execute("DROP INDEX product_media_bindings_asset_lookup")
    op.execute("DROP TRIGGER product_media_binding_no_delete ON product_media_bindings")
    op.execute("DROP FUNCTION reject_product_media_binding_delete()")
    op.execute("DROP TRIGGER product_media_binding_valid ON product_media_bindings")
    op.execute("DROP FUNCTION validate_product_media_binding()")
    op.execute("DROP TABLE product_media_bindings")
