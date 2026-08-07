/**
 * GENERATED FILE — DO NOT EDIT BY HAND.
 *
 * Source:   openapi.json (sha256 61e0b67f1b08d4f442502ab6401576771fb9ed70eba54cee02977fdcba64ab8c)
 * Command:  npm --prefix frontend run contracts:gen
 * Drift:    python3 scripts/exe01/assert_codegen_drift.py
 *
 * Regenerate instead of editing; the drift gate compares byte for byte.
 */
export interface paths {
    "/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Workbench */
        get: operations["workbench__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/admin": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Legacy Admin */
        get: operations["legacy_admin_admin_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/brand-expression": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Brand Expression */
        get: operations["brand_expression_api_v1_admin_brand_expression_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/brand-expression/confirm": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Confirm Brand Expression */
        post: operations["confirm_brand_expression_api_v1_admin_brand_expression_confirm_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/readiness": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Readiness */
        get: operations["readiness_api_v1_admin_readiness_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/password": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Change Password */
        post: operations["change_password_api_v1_auth_password_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/content": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Content */
        post: operations["create_content_api_v1_content_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/content-versions/{version_id}/save": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Save Version */
        post: operations["save_version_api_v1_content_versions__version_id__save_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/content/account-expression-profile": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Account Expression Profile */
        get: operations["account_expression_profile_api_v1_content_account_expression_profile_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/content/account-expression-profile/versions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Save Account Expression Profile */
        post: operations["save_account_expression_profile_api_v1_content_account_expression_profile_versions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/content/expression-catalog": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Expression Catalog */
        get: operations["expression_catalog_api_v1_content_expression_catalog_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/content/opportunities": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Content Opportunities
         * @description Read-only: browsing or refreshing opportunities never creates a business task.
         */
        post: operations["content_opportunities_api_v1_content_opportunities_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/content/plan": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Read Content Plan */
        get: operations["read_content_plan_api_v1_content_plan_get"];
        /** Save Content Plan */
        put: operations["save_content_plan_api_v1_content_plan_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/content/publishing-identities": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Content Publishing Identities */
        get: operations["list_content_publishing_identities_api_v1_content_publishing_identities_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/content/series": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Series */
        get: operations["list_series_api_v1_content_series_get"];
        put?: never;
        /** Create Series */
        post: operations["create_series_api_v1_content_series_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/content/series/{series_id}/items": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Reorder Series */
        put: operations["reorder_series_api_v1_content_series__series_id__items_put"];
        /** Add Series Item */
        post: operations["add_series_item_api_v1_content_series__series_id__items_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/content/series/{series_id}/reset": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Reset Series */
        post: operations["reset_series_api_v1_content_series__series_id__reset_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/content/stream": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Create Content Stream
         * @description Stream real lifecycle stages; the validated artifact is emitted only once.
         */
        post: operations["create_content_stream_api_v1_content_stream_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/content/tasks": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Content Tasks */
        get: operations["list_content_tasks_api_v1_content_tasks_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/content/tasks/{task_id}/versions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Content Versions */
        get: operations["list_content_versions_api_v1_content_tasks__task_id__versions_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/content/unmet-capability-requests": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Unmet Capability Requests */
        get: operations["list_unmet_capability_requests_api_v1_content_unmet_capability_requests_get"];
        put?: never;
        /** Submit Unmet Capability Request */
        post: operations["submit_unmet_capability_request_api_v1_content_unmet_capability_requests_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/display": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Display */
        post: operations["create_display_api_v1_display_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/display-tasks/{task_id}/revisions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Revise Display */
        post: operations["revise_display_api_v1_display_tasks__task_id__revisions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/display-tasks/{task_id}/versions/{version}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Display */
        get: operations["get_display_api_v1_display_tasks__task_id__versions__version__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/display/products": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Display Products */
        get: operations["list_display_products_api_v1_display_products_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/display/tasks": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Display Tasks */
        get: operations["list_display_tasks_api_v1_display_tasks_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/display/tasks/{task_id}/versions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Display Versions */
        get: operations["list_display_versions_api_v1_display_tasks__task_id__versions_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/materials": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Materials */
        get: operations["list_materials_api_v1_materials_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/materials/{asset_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Delete Material */
        delete: operations["delete_material_api_v1_materials__asset_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/materials/{asset_id}/reference-note": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /**
         * Set Material Reference Note
         * @description One sentence about an original nobody read; without it the original stays unusable.
         */
        patch: operations["set_material_reference_note_api_v1_materials__asset_id__reference_note_patch"];
        trace?: never;
    };
    "/api/v1/materials/{asset_scope}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Material */
        post: operations["create_material_api_v1_materials__asset_scope__post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/ops/runtime-summary": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Ops Runtime Summary */
        get: operations["ops_runtime_summary_api_v1_ops_runtime_summary_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/ops/tenants": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Ops Tenants */
        get: operations["list_ops_tenants_api_v1_ops_tenants_get"];
        put?: never;
        /** Provision Tenant */
        post: operations["provision_tenant_api_v1_ops_tenants_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/ops/tenants/{tenant_id}/disable": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Disable Tenant */
        post: operations["disable_tenant_api_v1_ops_tenants__tenant_id__disable_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/ops/tenants/{tenant_id}/enable": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Enable Tenant */
        post: operations["enable_tenant_api_v1_ops_tenants__tenant_id__enable_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/ops/unmet-capability-requests": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Ops Unmet Capability Requests
         * @description The gap candidates users submitted, read through the controlled function only.
         */
        get: operations["ops_unmet_capability_requests_api_v1_ops_unmet_capability_requests_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/ops/unmet-capability-requests/{stable_request_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Classify Unmet Capability Request
         * @description Classify one candidate and write one plain answer back to the person who asked.
         *
         *     This is the whole consumption entry: no queue, no approval state machine, and no
         *     change to the catalog, brand knowledge, an account profile or anybody's preference.
         */
        post: operations["classify_unmet_capability_request_api_v1_ops_unmet_capability_requests__stable_request_id__post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/session/context": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Session Context */
        get: operations["session_context_api_v1_session_context_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tasks/{task_id}/revisions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Revise Content
         * @description Both revision paths replay what this task froze; neither reads today's preference.
         */
        post: operations["revise_content_api_v1_tasks__task_id__revisions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tasks/{task_id}/versions/{version}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Version */
        get: operations["get_version_api_v1_tasks__task_id__versions__version__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenant-management/brand-library": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Management Brand Library */
        get: operations["management_brand_library_api_v1_tenant_management_brand_library_get"];
        put?: never;
        /** Create Management Brand Library Entry */
        post: operations["create_management_brand_library_entry_api_v1_tenant_management_brand_library_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenant-management/brand-library/{entry_id}/enabled": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Set Management Brand Library Enabled */
        put: operations["set_management_brand_library_enabled_api_v1_tenant_management_brand_library__entry_id__enabled_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenant-management/brand-library/{entry_id}/versions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Management Brand Library Versions */
        get: operations["management_brand_library_versions_api_v1_tenant_management_brand_library__entry_id__versions_get"];
        put?: never;
        /** Save Management Brand Library Version */
        post: operations["save_management_brand_library_version_api_v1_tenant_management_brand_library__entry_id__versions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenant-management/brand-library/preview": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Preview Management Brand Library Entry */
        post: operations["preview_management_brand_library_entry_api_v1_tenant_management_brand_library_preview_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenant-management/brand-products": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Management Products */
        get: operations["management_products_api_v1_tenant_management_brand_products_get"];
        /** Save Management Product */
        put: operations["save_management_product_api_v1_tenant_management_brand_products_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenant-management/brand-products/{sku}/enabled": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Set Management Product Enabled */
        put: operations["set_management_product_enabled_api_v1_tenant_management_brand_products__sku__enabled_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenant-management/brand-products/{sku}/versions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Management Product Versions */
        get: operations["management_product_versions_api_v1_tenant_management_brand_products__sku__versions_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenant-management/brand-products/preview": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Preview Management Products */
        post: operations["preview_management_products_api_v1_tenant_management_brand_products_preview_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenant-management/brand-publication": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Management Brand Publication */
        get: operations["management_brand_publication_api_v1_tenant_management_brand_publication_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenant-management/brand-publication/{projection_id}/confirm": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Confirm Management Brand Publication */
        post: operations["confirm_management_brand_publication_api_v1_tenant_management_brand_publication__projection_id__confirm_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenant-management/brand-publication/candidates": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Management Brand Publication Candidate */
        post: operations["create_management_brand_publication_candidate_api_v1_tenant_management_brand_publication_candidates_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenant-management/brand-publication/sources": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Management Brand Publication Sources */
        get: operations["management_brand_publication_sources_api_v1_tenant_management_brand_publication_sources_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenant-management/control-organizations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Control Organizations */
        get: operations["control_organizations_api_v1_tenant_management_control_organizations_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenant-management/demo-content-index": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Management Demo Content Index */
        get: operations["management_demo_content_index_api_v1_tenant_management_demo_content_index_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenant-management/display-stores": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Management Display Stores */
        get: operations["management_display_stores_api_v1_tenant_management_display_stores_get"];
        put?: never;
        /** Create Management Display Store */
        post: operations["create_management_display_store_api_v1_tenant_management_display_stores_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenant-management/display-stores/{store_id}/enabled": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Set Management Display Store Enabled */
        put: operations["set_management_display_store_enabled_api_v1_tenant_management_display_stores__store_id__enabled_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenant-management/display-stores/{store_id}/versions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Save Management Display Store Version */
        post: operations["save_management_display_store_version_api_v1_tenant_management_display_stores__store_id__versions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenant-management/onboarding-prefill": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Management Onboarding Prefill */
        get: operations["management_onboarding_prefill_api_v1_tenant_management_onboarding_prefill_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenant-management/operators": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Management Operators */
        get: operations["management_operators_api_v1_tenant_management_operators_get"];
        put?: never;
        /** Create Operator */
        post: operations["create_operator_api_v1_tenant_management_operators_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenant-management/organization-materials": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Management Organization Materials */
        get: operations["management_organization_materials_api_v1_tenant_management_organization_materials_get"];
        put?: never;
        /** Create Management Organization Material */
        post: operations["create_management_organization_material_api_v1_tenant_management_organization_materials_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenant-management/organization-materials/{asset_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Delete Management Organization Material */
        delete: operations["delete_management_organization_material_api_v1_tenant_management_organization_materials__asset_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenant-management/organization-materials/{asset_id}/enabled": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Set Management Organization Material Enabled */
        put: operations["set_management_organization_material_enabled_api_v1_tenant_management_organization_materials__asset_id__enabled_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenant-management/organization-materials/{asset_id}/product-bindings": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Management Product Media Bindings */
        get: operations["management_product_media_bindings_api_v1_tenant_management_organization_materials__asset_id__product_bindings_get"];
        put?: never;
        /** Create Management Product Media Binding */
        post: operations["create_management_product_media_binding_api_v1_tenant_management_organization_materials__asset_id__product_bindings_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenant-management/organization-materials/{asset_id}/product-bindings/{binding_id}/enabled": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Set Management Product Media Binding Enabled */
        put: operations["set_management_product_media_binding_enabled_api_v1_tenant_management_organization_materials__asset_id__product_bindings__binding_id__enabled_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenant-management/organization-materials/{asset_id}/versions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Management Organization Material Versions */
        get: operations["management_organization_material_versions_api_v1_tenant_management_organization_materials__asset_id__versions_get"];
        put?: never;
        /** Save Management Organization Material Version */
        post: operations["save_management_organization_material_version_api_v1_tenant_management_organization_materials__asset_id__versions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenant-management/organizations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Tenant Organizations */
        get: operations["tenant_organizations_api_v1_tenant_management_organizations_get"];
        put?: never;
        /** Create Tenant Organization */
        post: operations["create_tenant_organization_api_v1_tenant_management_organizations_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenant-management/organizations/{organization_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Update Tenant Organization */
        patch: operations["update_tenant_organization_api_v1_tenant_management_organizations__organization_id__patch"];
        trace?: never;
    };
    "/api/v1/tenant-management/organizations/{organization_id}/enabled": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Set Tenant Organization Enabled */
        put: operations["set_tenant_organization_enabled_api_v1_tenant_management_organizations__organization_id__enabled_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenant-management/platform-carriers": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Platform Carrier */
        post: operations["create_platform_carrier_api_v1_tenant_management_platform_carriers_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenant-management/platform-carriers/{account_id}/enabled": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Set Platform Carrier Enabled */
        put: operations["set_platform_carrier_enabled_api_v1_tenant_management_platform_carriers__account_id__enabled_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenant-management/publishing-accounts": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Management Accounts */
        get: operations["management_accounts_api_v1_tenant_management_publishing_accounts_get"];
        put?: never;
        /** Create Publishing Account */
        post: operations["create_publishing_account_api_v1_tenant_management_publishing_accounts_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenant-management/publishing-accounts/{account_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Update Publishing Account */
        patch: operations["update_publishing_account_api_v1_tenant_management_publishing_accounts__account_id__patch"];
        trace?: never;
    };
    "/api/v1/tenant-management/publishing-accounts/{account_id}/control-organization": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Declare Control Organization
         * @description Declare, once, which organization controls this account.
         *
         *     A value a migration inferred from a creation event is not evidence and grants nothing;
         *     this is the explicit decision that makes profile maintenance possible.
         */
        post: operations["declare_control_organization_api_v1_tenant_management_publishing_accounts__account_id__control_organization_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenant-management/publishing-accounts/{account_id}/enabled": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Set Publishing Account Enabled */
        put: operations["set_publishing_account_enabled_api_v1_tenant_management_publishing_accounts__account_id__enabled_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenant-management/publishing-accounts/{account_id}/expression-profile": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Management Account Expression Profile */
        get: operations["management_account_expression_profile_api_v1_tenant_management_publishing_accounts__account_id__expression_profile_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenant-management/publishing-accounts/{account_id}/expression-profile/versions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Management Account Expression Versions */
        get: operations["management_account_expression_versions_api_v1_tenant_management_publishing_accounts__account_id__expression_profile_versions_get"];
        put?: never;
        /** Save Management Account Expression Profile */
        post: operations["save_management_account_expression_profile_api_v1_tenant_management_publishing_accounts__account_id__expression_profile_versions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenant-management/publishing-accounts/{account_id}/speaker-kind": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Update Publishing Speaker Kind */
        patch: operations["update_publishing_speaker_kind_api_v1_tenant_management_publishing_accounts__account_id__speaker_kind_patch"];
        trace?: never;
    };
    "/api/v1/tenant-management/team-usage": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Management Team Usage */
        get: operations["management_team_usage_api_v1_tenant_management_team_usage_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenant-management/users": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Tenant User */
        post: operations["create_tenant_user_api_v1_tenant_management_users_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenant-management/users/{user_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Update Tenant User */
        patch: operations["update_tenant_user_api_v1_tenant_management_users__user_id__patch"];
        trace?: never;
    };
    "/api/v1/tenant-management/users/{user_id}/disable": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Disable Tenant User */
        post: operations["disable_tenant_user_api_v1_tenant_management_users__user_id__disable_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenant-management/users/{user_id}/grants": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Update Tenant User Grants */
        patch: operations["update_tenant_user_grants_api_v1_tenant_management_users__user_id__grants_patch"];
        trace?: never;
    };
    "/api/v1/tenant-management/users/{user_id}/publishing-accounts/{account_id}/profile-maintenance": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Set Expression Profile Maintenance */
        put: operations["set_expression_profile_maintenance_api_v1_tenant_management_users__user_id__publishing_accounts__account_id__profile_maintenance_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenant-management/users/{user_id}/publishing-accounts/{account_id}/revoke": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Revoke Publishing Account Grant */
        post: operations["revoke_publishing_account_grant_api_v1_tenant_management_users__user_id__publishing_accounts__account_id__revoke_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenant-management/users/{user_id}/reset": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Reset Tenant User */
        post: operations["reset_tenant_user_api_v1_tenant_management_users__user_id__reset_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tenant-management/users/{user_id}/restore": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Restore Tenant User */
        post: operations["restore_tenant_user_api_v1_tenant_management_users__user_id__restore_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/user/creation-preferences": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Read Creation Preferences */
        get: operations["read_creation_preferences_api_v1_user_creation_preferences_get"];
        /** Save Creation Preferences */
        put: operations["save_creation_preferences_api_v1_user_creation_preferences_put"];
        post?: never;
        /** Delete Creation Preferences */
        delete: operations["delete_creation_preferences_api_v1_user_creation_preferences_delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/user/default-persona": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Update Default Persona */
        post: operations["update_default_persona_api_v1_user_default_persona_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/user/organization-materials": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** User Organization Materials */
        get: operations["user_organization_materials_api_v1_user_organization_materials_get"];
        put?: never;
        /** Create User Organization Material */
        post: operations["create_user_organization_material_api_v1_user_organization_materials_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/user/organization-materials/{asset_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Delete User Organization Material */
        delete: operations["delete_user_organization_material_api_v1_user_organization_materials__asset_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/user/organization-materials/{asset_id}/enabled": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Set User Organization Material Enabled */
        put: operations["set_user_organization_material_enabled_api_v1_user_organization_materials__asset_id__enabled_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/user/organization-materials/{asset_id}/versions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** User Organization Material Versions */
        get: operations["user_organization_material_versions_api_v1_user_organization_materials__asset_id__versions_get"];
        put?: never;
        /** Save User Organization Material Version */
        post: operations["save_user_organization_material_version_api_v1_user_organization_materials__asset_id__versions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/content": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Content Workbench */
        get: operations["content_workbench_content_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/content/tasks/{task}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Content Task Workbench
         * @description A task's own address (EXE-01 SEAM-06).
         *
         *     Delegates to `content_workbench` rather than repeating it: the scope
         *     resolution, the operator check and the access-denied pages there are
         *     the only implementation of those rules, and a second copy would be one
         *     more place for them to drift.
         */
        get: operations["content_task_workbench_content_tasks__task__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/display": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Display Workbench */
        get: operations["display_workbench_display_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/materials": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Organization Materials Portal */
        get: operations["organization_materials_portal_materials_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/tenant-admin": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Tenant Management Portal */
        get: operations["tenant_management_portal_tenant_admin_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ui/display/generate": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Ui Display Generate */
        post: operations["ui_display_generate_ui_display_generate_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ui/display/revise": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Ui Display Revise */
        post: operations["ui_display_revise_ui_display_revise_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ui/generate": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Ui Generate */
        post: operations["ui_generate_ui_generate_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ui/reuse": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Ui Reuse */
        post: operations["ui_reuse_ui_reuse_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ui/revise": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Ui Revise */
        post: operations["ui_revise_ui_revise_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ui/save": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Ui Save */
        post: operations["ui_save_ui_save_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/user": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Tenant User Portal */
        get: operations["tenant_user_portal_user_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /**
         * AccountExpressionVersionRequest
         * @description Five plain-language segments; saving forms the next immutable version.
         */
        AccountExpressionVersionRequest: {
            /** Audience Relationship */
            audience_relationship: string;
            /** Authority Boundary */
            authority_boundary: string;
            /** Content Territories */
            content_territories: string;
            /** Default Production Conditions */
            default_production_conditions: string;
            /** Identity Position */
            identity_position: string;
        };
        /** AddSeriesItemRequest */
        AddSeriesItemRequest: {
            /** Position */
            position?: number | null;
            /**
             * Task Id
             * Format: uuid
             */
            task_id: string;
        };
        /** ApplicationHandoffResponse */
        ApplicationHandoffResponse: {
            /**
             * Kind
             * @default handoff
             */
            kind: string;
            /** Message */
            message: string;
        };
        /** BrandExpressionConfirmRequest */
        BrandExpressionConfirmRequest: {
            /** Draft */
            draft: string;
        };
        /** BrandLibraryEntryRequest */
        BrandLibraryEntryRequest: {
            /**
             * Category
             * @enum {string}
             */
            category: "brand_expression" | "product" | "organization_fact" | "reference" | "official_material";
            /**
             * Confirm As Current
             * @constant
             */
            confirm_as_current: true;
            /** Content */
            content: string;
            /** Organization Ids */
            organization_ids?: string[];
            /** Source Note */
            source_note: string;
            /**
             * Status
             * @default active
             * @constant
             */
            status: "active";
            /** Title */
            title: string;
            /** Version */
            version: string;
            /**
             * Visibility Scope
             * @enum {string}
             */
            visibility_scope: "brand_all" | "headquarters" | "organizations";
        };
        /** BrandLibraryPreviewRequest */
        BrandLibraryPreviewRequest: {
            /**
             * Category
             * @enum {string}
             */
            category: "brand_expression" | "product" | "organization_fact" | "reference" | "official_material";
            /** Content */
            content: string;
            /** Organization Ids */
            organization_ids?: string[];
            /** Source Note */
            source_note: string;
            /** Title */
            title: string;
            /** Version */
            version: string;
            /**
             * Visibility Scope
             * @enum {string}
             */
            visibility_scope: "brand_all" | "headquarters" | "organizations";
        };
        /** BrandLibraryVersionRequest */
        BrandLibraryVersionRequest: {
            /** Content */
            content: string;
            /** Organization Ids */
            organization_ids?: string[];
            /** Source Note */
            source_note: string;
            /** Title */
            title: string;
            /** Version */
            version: string;
            /**
             * Visibility Scope
             * @enum {string}
             */
            visibility_scope: "brand_all" | "headquarters" | "organizations";
        };
        /** BrandPublicationProjectionCandidateRequest */
        BrandPublicationProjectionCandidateRequest: {
            /** Items */
            items: components["schemas"]["BrandPublicationProjectionItemRequest"][];
        };
        /** BrandPublicationProjectionItemRequest */
        BrandPublicationProjectionItemRequest: {
            /** Applicability */
            applicability?: ("dressing_decision" | "product_truth" | "brand_life_narrative" | "local_response" | "visual_styling_story")[];
            /**
             * Publication Role
             * @enum {string}
             */
            publication_role: "public_brand_fact" | "expression_constraint" | "creative_method" | "internal_only";
            /** Published Text */
            published_text: string;
            /**
             * Source Segment Id
             * Format: uuid
             */
            source_segment_id: string;
        };
        /** ChangePasswordRequest */
        ChangePasswordRequest: {
            /** Current Password */
            current_password: string;
            /** Password */
            password: string;
        };
        /** ContentPlanItem */
        ContentPlanItem: {
            /**
             * Note
             * @default
             */
            note: string;
            /** Selections */
            selections?: {
                [key: string]: string;
            };
            /** Title */
            title: string;
        };
        /** ContentPlanRequest */
        ContentPlanRequest: {
            /** Items */
            items?: components["schemas"]["ContentPlanItem"][];
        };
        /** ContentQuestionResponse */
        ContentQuestionResponse: {
            /**
             * Kind
             * @default question
             */
            kind: string;
            /** Message */
            message: string;
        };
        /** ContentVersionResponse */
        ContentVersionResponse: {
            /** Adapted From */
            adapted_from?: string | null;
            /** Ai Generated */
            ai_generated: boolean;
            /** Aigc Label */
            aigc_label?: string | null;
            /** Aigc Release Reminder */
            aigc_release_reminder?: string | null;
            /** Applied Direction */
            applied_direction?: string[];
            /** Body */
            body: string;
            /**
             * Kind
             * @default content
             */
            kind: string;
            /** Outline */
            outline: string;
            /** Target */
            target?: string | null;
            /** Target Key */
            target_key?: ("douyin_video" | "xiaohongshu_video" | "xiaohongshu_graphic" | "wechat_channels_video") | null;
            /**
             * Task Id
             * Format: uuid
             */
            task_id: string;
            /** Translation Notice */
            translation_notice?: string | null;
            /** Version */
            version: number;
            /**
             * Version Id
             * Format: uuid
             */
            version_id: string;
        };
        /**
         * ControlOrganizationRequest
         * @description Which organization controls a publishing account, declared once by a tenant authority.
         */
        ControlOrganizationRequest: {
            /**
             * Organization Id
             * Format: uuid
             */
            organization_id: string;
        };
        /** ConversationTurnRequest */
        ConversationTurnRequest: {
            /** Content */
            content: string;
            /**
             * Role
             * @enum {string}
             */
            role: "user" | "assistant";
        };
        /** CreateContentRequest */
        CreateContentRequest: {
            creative_direction?: components["schemas"]["CreativeDirectionRequest"] | null;
            /** Material Ids */
            material_ids?: string[];
            /**
             * Product Media Intent
             * @default false
             */
            product_media_intent: boolean;
            /** Publishing Identity Id */
            publishing_identity_id?: string | null;
            /** Reuse Version Id */
            reuse_version_id?: string | null;
            /** Series Id */
            series_id?: string | null;
            /** Series Position */
            series_position?: number | null;
            /** Target */
            target?: ("douyin_video" | "xiaohongshu_video" | "xiaohongshu_graphic" | "wechat_channels_video") | null;
            /**
             * Use Personal Preferences
             * @default true
             */
            use_personal_preferences: boolean;
            /** Weak Seed */
            weak_seed: string;
        };
        /**
         * CreateConversationRequest
         * @description One bounded natural turn; only a `ready` result may create a content task.
         */
        CreateConversationRequest: {
            /** Conversation */
            conversation?: components["schemas"]["ConversationTurnRequest"][];
            creative_direction?: components["schemas"]["CreativeDirectionRequest"] | null;
            /**
             * Direct Generate
             * @default false
             */
            direct_generate: boolean;
            /**
             * Interaction Mode
             * @default auto
             * @enum {string}
             */
            interaction_mode: "auto" | "conversation" | "generate";
            /** Material Ids */
            material_ids?: string[];
            /** Message */
            message: string;
            /**
             * Product Media Intent
             * @default false
             */
            product_media_intent: boolean;
            /**
             * Publishing Identity Id
             * Format: uuid
             */
            publishing_identity_id: string;
            /** Request Id */
            request_id?: string | null;
            /** Series Id */
            series_id?: string | null;
            /** Series Position */
            series_position?: number | null;
            /**
             * Target
             * @enum {string}
             */
            target: "douyin_video" | "xiaohongshu_video" | "xiaohongshu_graphic" | "wechat_channels_video";
            /** Target Conflict Resolution */
            target_conflict_resolution?: ("keep_selected" | "switch") | null;
            /**
             * Use Personal Preferences
             * @default true
             */
            use_personal_preferences: boolean;
        };
        /** CreateDisplayRequest */
        CreateDisplayRequest: {
            /**
             * Inventory Text
             * @default
             */
            inventory_text: string;
            /** Products */
            products?: components["schemas"]["DisplayProductSelectionRequest"][];
        };
        /** CreatedTenantUserResponse */
        CreatedTenantUserResponse: {
            /** Activation Link */
            activation_link: string;
            /** Activation Url */
            activation_url: string;
            /** User Id */
            user_id: string;
            /** Username */
            username: string;
        };
        /** CreateOperatorRequest */
        CreateOperatorRequest: {
            /**
             * Account Id
             * Format: uuid
             */
            account_id: string;
            /**
             * Default Persona Boundary
             * @default
             */
            default_persona_boundary: string;
            /**
             * Default Persona Name
             * @default
             */
            default_persona_name: string;
            /** Display Name */
            display_name: string;
        };
        /** CreateOrganizationRequest */
        CreateOrganizationRequest: {
            /**
             * As Synthetic Business Fixture
             * @default false
             */
            as_synthetic_business_fixture: boolean;
            /** Name */
            name: string;
            /**
             * Organization Level
             * @default unspecified
             * @enum {string}
             */
            organization_level: "company" | "region" | "operating_unit" | "unspecified";
            /** Parent Organization Id */
            parent_organization_id?: string | null;
        };
        /** CreatePlatformCarrierRequest */
        CreatePlatformCarrierRequest: {
            /**
             * Channel
             * @enum {string}
             */
            channel: "抖音" | "小红书" | "微信视频号";
            /**
             * Confirm Internal Carrier
             * @constant
             */
            confirm_internal_carrier: true;
            /** Name */
            name: string;
            /** Operator Id */
            operator_id?: string | null;
            /**
             * Source Account Id
             * Format: uuid
             */
            source_account_id: string;
        };
        /** CreateProductMediaBindingRequest */
        CreateProductMediaBindingRequest: {
            /**
             * Product Id
             * Format: uuid
             */
            product_id: string;
        };
        /** CreatePublishingAccountRequest */
        CreatePublishingAccountRequest: {
            /**
             * As Synthetic Business Fixture
             * @default false
             */
            as_synthetic_business_fixture: boolean;
            /**
             * Channel
             * @enum {string}
             */
            channel: "抖音" | "小红书" | "微信视频号";
            /** Content Role Name */
            content_role_name: string;
            /** Control Organization Id */
            control_organization_id?: string | null;
            initial_profile?: components["schemas"]["AccountExpressionVersionRequest"] | null;
            /** Name */
            name: string;
            /**
             * Operator Can Maintain Expression Profile
             * @default false
             */
            operator_can_maintain_expression_profile: boolean;
            /** Operator Id */
            operator_id?: string | null;
            /**
             * Speaker Kind
             * @default unknown
             * @enum {string}
             */
            speaker_kind: "institutional_account" | "personal_ip_account" | "unknown";
            /** Voice Boundary */
            voice_boundary?: string | null;
        };
        /** CreateSeriesRequest */
        CreateSeriesRequest: {
            /**
             * Premise
             * @default
             */
            premise: string;
            /** Title */
            title: string;
        };
        /** CreateTenantRequest */
        CreateTenantRequest: {
            /** Administrator Name */
            administrator_name: string;
            /** Administrator Username */
            administrator_username: string;
            /** Tenant Name */
            tenant_name: string;
        };
        /** CreateTenantUserRequest */
        CreateTenantUserRequest: {
            /** Account Id */
            account_id?: string | null;
            /** Capabilities */
            capabilities?: ("content" | "display")[];
            /** Display Name */
            display_name: string;
            /** Display Store Ids */
            display_store_ids?: string[];
            /** Entry Type */
            entry_type?: ("tenant_admin" | "tenant_user") | null;
            /** Expression Profile Maintenance Account Ids */
            expression_profile_maintenance_account_ids?: string[];
            /**
             * Grants Expression Profile Maintenance
             * @default false
             */
            grants_expression_profile_maintenance: boolean;
            /**
             * Grants Material Maintenance
             * @default false
             */
            grants_material_maintenance: boolean;
            /**
             * Grants Tenant Management
             * @default false
             */
            grants_tenant_management: boolean;
            /** Organization Id */
            organization_id?: string | null;
            /** Publishing Identity Ids */
            publishing_identity_ids?: string[];
            /** Username */
            username: string;
        };
        /** CreationPreferenceRequest */
        CreationPreferenceRequest: {
            /**
             * Body Related Opt In
             * @default false
             */
            body_related_opt_in: boolean;
            /**
             * Clear Direction Defaults
             * @default false
             */
            clear_direction_defaults: boolean;
            /**
             * Collaboration Note
             * @default
             */
            collaboration_note: string;
            /** Direction Defaults */
            direction_defaults?: {
                [key: string]: string;
            };
            /**
             * Enabled
             * @default true
             */
            enabled: boolean;
        };
        /**
         * CreativeDirectionRequest
         * @description The optional five-axis panel for this request only; saving a default is a separate call.
         */
        CreativeDirectionRequest: {
            /**
             * Body Related Opt In
             * @default false
             */
            body_related_opt_in: boolean;
            /** Catalog Version */
            catalog_version?: string | null;
            /** Cleared Axes */
            cleared_axes?: string[];
            /**
             * Custom Text
             * @default
             */
            custom_text: string;
            /** Selections */
            selections?: {
                [key: string]: string;
            };
        };
        /** DefaultPersonaRequest */
        DefaultPersonaRequest: {
            /** Boundary */
            boundary: string;
            /** Name */
            name: string;
        };
        /** DisplayProductSelectionRequest */
        DisplayProductSelectionRequest: {
            /**
             * Product Version Id
             * Format: uuid
             */
            product_version_id: string;
            /** Quantity */
            quantity: number;
        };
        /** DisplayQuestionResponse */
        DisplayQuestionResponse: {
            /**
             * Kind
             * @default question
             */
            kind: string;
            /** Message */
            message: string;
        };
        /** DisplayRevisionRequest */
        DisplayRevisionRequest: {
            /** Feedback */
            feedback: string;
        };
        /** DisplayVersionResponse */
        DisplayVersionResponse: {
            /** Body */
            body: string;
            /**
             * Kind
             * @default display
             */
            kind: string;
            /**
             * Task Id
             * Format: uuid
             */
            task_id: string;
            /** Version */
            version: number;
            /**
             * Version Id
             * Format: uuid
             */
            version_id: string;
        };
        /** GreetingResponse */
        GreetingResponse: {
            /**
             * Kind
             * @default greeting
             */
            kind: string;
            /** Message */
            message: string;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /** MaterialMetadataVersionRequest */
        MaterialMetadataVersionRequest: {
            /** Organization Ids */
            organization_ids?: string[];
            /** Reference Note */
            reference_note: string;
            /** Title */
            title: string;
            /**
             * Visibility Scope
             * @enum {string}
             */
            visibility_scope: "brand_all" | "headquarters" | "organizations";
        };
        /** MaterialReferenceNoteRequest */
        MaterialReferenceNoteRequest: {
            /** Reference Note */
            reference_note: string;
        };
        /** MaterialUploadRequest */
        MaterialUploadRequest: {
            /** Content Base64 */
            content_base64: string;
            /** Content Type */
            content_type: string;
            /**
             * Declares Identifiable Minor
             * @default false
             */
            declares_identifiable_minor: boolean;
            /** Filename */
            filename: string;
            /**
             * Reference Note
             * @default
             */
            reference_note: string;
            /** Title */
            title: string;
        };
        /** OrganizationMaterialUploadRequest */
        OrganizationMaterialUploadRequest: {
            /** Content Base64 */
            content_base64: string;
            /** Content Type */
            content_type: string;
            /**
             * Declares Identifiable Minor
             * @default false
             */
            declares_identifiable_minor: boolean;
            /** Filename */
            filename: string;
            /**
             * Organization Id
             * Format: uuid
             */
            organization_id: string;
            /** Organization Ids */
            organization_ids?: string[];
            /**
             * Reference Note
             * @default
             */
            reference_note: string;
            /** Title */
            title: string;
            /**
             * Visibility Scope
             * @default organizations
             * @enum {string}
             */
            visibility_scope: "brand_all" | "headquarters" | "organizations";
        };
        /** ProductImportPreviewRequest */
        ProductImportPreviewRequest: {
            /** Content */
            content: string;
            /**
             * Source Format
             * @enum {string}
             */
            source_format: "table" | "csv";
        };
        /** ProvisionedTenantResponse */
        ProvisionedTenantResponse: {
            /** Activation Link */
            activation_link: string;
            /** Activation Url */
            activation_url: string;
            /** Administrator Id */
            administrator_id: string;
            /** Tenant Id */
            tenant_id: string;
            /** Username */
            username: string;
        };
        /** ReorderSeriesRequest */
        ReorderSeriesRequest: {
            /** Task Ids */
            task_ids: string[];
        };
        /** ResetTenantUserResponse */
        ResetTenantUserResponse: {
            /** Reset Link */
            reset_link: string;
            /** Reset Url */
            reset_url: string;
        };
        /** RestoredTenantUserResponse */
        RestoredTenantUserResponse: {
            /** Activation Link */
            activation_link: string;
            /** Activation Url */
            activation_url: string;
            /** User Id */
            user_id: string;
        };
        /** RevisionRequest */
        RevisionRequest: {
            /** Instruction */
            instruction: string;
            /** Publishing Identity Id */
            publishing_identity_id?: string | null;
            /** Request Id */
            request_id?: string | null;
            /** Source Target */
            source_target?: ("douyin_video" | "xiaohongshu_video" | "xiaohongshu_graphic" | "wechat_channels_video") | null;
            /** Target */
            target?: ("douyin_video" | "xiaohongshu_video" | "xiaohongshu_graphic" | "wechat_channels_video") | null;
        };
        /** SaveBrandProductRequest */
        SaveBrandProductRequest: {
            /** Applicability */
            applicability: string;
            /**
             * As Synthetic Business Fixture
             * @default false
             */
            as_synthetic_business_fixture: boolean;
            /**
             * Category
             * @default
             */
            category: string;
            /** Colors */
            colors?: string[];
            /**
             * Confirm As Current Brand Fact
             * @constant
             */
            confirm_as_current_brand_fact: true;
            /**
             * Display Accent
             * @default false
             */
            display_accent: boolean;
            /** Display Family */
            display_family?: ("upper" | "lower") | null;
            /**
             * Display Is Long
             * @default false
             */
            display_is_long: boolean;
            /** Display Name */
            display_name: string;
            /**
             * Material Or Structure
             * @default
             */
            material_or_structure: string;
            /**
             * Observable Features
             * @default
             */
            observable_features: string;
            /** Organization Ids */
            organization_ids?: string[];
            /**
             * Silhouette
             * @default
             */
            silhouette: string;
            /** Sku */
            sku: string;
            /** Source Note */
            source_note: string;
            /**
             * Visibility Scope
             * @default brand_all
             * @enum {string}
             */
            visibility_scope: "brand_all" | "headquarters" | "organizations";
        };
        /** SaveDisplayStoreRequest */
        SaveDisplayStoreRequest: {
            /**
             * Confirm As Current
             * @constant
             */
            confirm_as_current: true;
            /**
             * Control Organization Id
             * Format: uuid
             */
            control_organization_id: string;
            /**
             * Execution Organization Id
             * Format: uuid
             */
            execution_organization_id: string;
            /** Lower Comfort Capacity */
            lower_comfort_capacity: number;
            /** Name */
            name: string;
            /** Upper Comfort Capacity */
            upper_comfort_capacity: number;
        };
        /** SavedVersionResponse */
        SavedVersionResponse: {
            /**
             * Saved At
             * Format: date-time
             */
            saved_at: string;
            /**
             * Version Id
             * Format: uuid
             */
            version_id: string;
        };
        /** SetEnabledRequest */
        SetEnabledRequest: {
            /** Enabled */
            enabled: boolean;
        };
        /** SetExpressionProfileMaintenanceRequest */
        SetExpressionProfileMaintenanceRequest: {
            /** Enabled */
            enabled: boolean;
        };
        /** UnmetCapabilityRequest */
        UnmetCapabilityRequest: {
            creative_direction?: components["schemas"]["CreativeDirectionRequest"] | null;
            /** Request Text */
            request_text: string;
        };
        /**
         * UnmetCapabilityResponseRequest
         * @description 笛语运维's minimum classification and reply; it changes nothing else.
         */
        UnmetCapabilityResponseRequest: {
            /**
             * Gap Type
             * @enum {string}
             */
            gap_type: "unclassified" | "knowledge" | "generation_method" | "media_tool" | "product_scope" | "policy_conflict" | "source_gap";
            /**
             * Response Text
             * @default
             */
            response_text: string;
            /**
             * Status
             * @enum {string}
             */
            status: "received" | "classified" | "answered";
        };
        /** UpdateOrganizationRequest */
        UpdateOrganizationRequest: {
            /** Name */
            name: string;
            /**
             * Organization Level
             * @enum {string}
             */
            organization_level: "company" | "region" | "operating_unit" | "unspecified";
            /** Parent Organization Id */
            parent_organization_id?: string | null;
        };
        /** UpdatePublishingAccountRequest */
        UpdatePublishingAccountRequest: {
            /** Control Organization Id */
            control_organization_id?: string | null;
            /** Name */
            name?: string | null;
        };
        /** UpdatePublishingSpeakerKindRequest */
        UpdatePublishingSpeakerKindRequest: {
            /**
             * Speaker Kind
             * @enum {string}
             */
            speaker_kind: "institutional_account" | "personal_ip_account" | "unknown";
        };
        /** UpdateTenantUserGrantsRequest */
        UpdateTenantUserGrantsRequest: {
            /** Account Id */
            account_id?: string | null;
            /** Capabilities */
            capabilities?: ("content" | "display")[];
            /** Display Store Ids */
            display_store_ids?: string[] | null;
            /** Entry Type */
            entry_type?: ("tenant_admin" | "tenant_user") | null;
            /** Expression Profile Maintenance Account Ids */
            expression_profile_maintenance_account_ids?: string[] | null;
            /**
             * Grants Account Access
             * @default false
             */
            grants_account_access: boolean;
            /** Grants Expression Profile Maintenance */
            grants_expression_profile_maintenance?: boolean | null;
            /**
             * Grants Material Maintenance
             * @default false
             */
            grants_material_maintenance: boolean;
            /**
             * Grants Tenant Management
             * @default false
             */
            grants_tenant_management: boolean;
            /** Publishing Identity Ids */
            publishing_identity_ids?: string[];
        };
        /** UpdateTenantUserRequest */
        UpdateTenantUserRequest: {
            /** Display Name */
            display_name?: string | null;
            /** Organization Id */
            organization_id?: string | null;
        };
        /** ValidationError */
        ValidationError: {
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    workbench__get: {
        parameters: {
            query?: {
                notice?: string | null;
                task?: string | null;
                version?: number | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "text/html": string;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    legacy_admin_admin_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            307: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    brand_expression_api_v1_admin_brand_expression_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    confirm_brand_expression_api_v1_admin_brand_expression_confirm_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BrandExpressionConfirmRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    readiness_api_v1_admin_readiness_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    change_password_api_v1_auth_password_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ChangePasswordRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: boolean;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    create_content_api_v1_content_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateContentRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ContentVersionResponse"] | components["schemas"]["GreetingResponse"] | components["schemas"]["ContentQuestionResponse"] | components["schemas"]["ApplicationHandoffResponse"];
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    save_version_api_v1_content_versions__version_id__save_post: {
        parameters: {
            query?: {
                publishing_identity_id?: string | null;
                target?: "douyin_video" | "xiaohongshu_video" | "xiaohongshu_graphic" | "wechat_channels_video";
            };
            header?: never;
            path: {
                version_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SavedVersionResponse"];
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    account_expression_profile_api_v1_content_account_expression_profile_get: {
        parameters: {
            query?: {
                target?: ("douyin_video" | "xiaohongshu_video" | "xiaohongshu_graphic" | "wechat_channels_video") | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    save_account_expression_profile_api_v1_content_account_expression_profile_versions_post: {
        parameters: {
            query?: {
                target?: ("douyin_video" | "xiaohongshu_video" | "xiaohongshu_graphic" | "wechat_channels_video") | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AccountExpressionVersionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    expression_catalog_api_v1_content_expression_catalog_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    content_opportunities_api_v1_content_opportunities_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    read_content_plan_api_v1_content_plan_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    save_content_plan_api_v1_content_plan_put: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ContentPlanRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    list_content_publishing_identities_api_v1_content_publishing_identities_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    }[];
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    list_series_api_v1_content_series_get: {
        parameters: {
            query?: {
                target?: ("douyin_video" | "xiaohongshu_video" | "xiaohongshu_graphic" | "wechat_channels_video") | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    }[];
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    create_series_api_v1_content_series_post: {
        parameters: {
            query?: {
                target?: ("douyin_video" | "xiaohongshu_video" | "xiaohongshu_graphic" | "wechat_channels_video") | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateSeriesRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    reorder_series_api_v1_content_series__series_id__items_put: {
        parameters: {
            query?: {
                target?: ("douyin_video" | "xiaohongshu_video" | "xiaohongshu_graphic" | "wechat_channels_video") | null;
            };
            header?: never;
            path: {
                series_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ReorderSeriesRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    add_series_item_api_v1_content_series__series_id__items_post: {
        parameters: {
            query?: {
                target?: ("douyin_video" | "xiaohongshu_video" | "xiaohongshu_graphic" | "wechat_channels_video") | null;
            };
            header?: never;
            path: {
                series_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AddSeriesItemRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    reset_series_api_v1_content_series__series_id__reset_post: {
        parameters: {
            query?: {
                target?: ("douyin_video" | "xiaohongshu_video" | "xiaohongshu_graphic" | "wechat_channels_video") | null;
            };
            header?: never;
            path: {
                series_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    create_content_stream_api_v1_content_stream_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateConversationRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    list_content_tasks_api_v1_content_tasks_get: {
        parameters: {
            query?: {
                target?: ("douyin_video" | "xiaohongshu_video" | "xiaohongshu_graphic" | "wechat_channels_video") | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    }[];
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    list_content_versions_api_v1_content_tasks__task_id__versions_get: {
        parameters: {
            query?: {
                target?: ("douyin_video" | "xiaohongshu_video" | "xiaohongshu_graphic" | "wechat_channels_video") | null;
            };
            header?: never;
            path: {
                task_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    }[];
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    list_unmet_capability_requests_api_v1_content_unmet_capability_requests_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    }[];
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    submit_unmet_capability_request_api_v1_content_unmet_capability_requests_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UnmetCapabilityRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    create_display_api_v1_display_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateDisplayRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DisplayVersionResponse"] | components["schemas"]["DisplayQuestionResponse"] | components["schemas"]["ApplicationHandoffResponse"];
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    revise_display_api_v1_display_tasks__task_id__revisions_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                task_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DisplayRevisionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DisplayVersionResponse"] | components["schemas"]["DisplayQuestionResponse"];
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    get_display_api_v1_display_tasks__task_id__versions__version__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                task_id: string;
                version: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DisplayVersionResponse"];
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    list_display_products_api_v1_display_products_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    }[];
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    list_display_tasks_api_v1_display_tasks_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    }[];
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    list_display_versions_api_v1_display_tasks__task_id__versions_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                task_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    }[];
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    list_materials_api_v1_materials_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    }[];
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    delete_material_api_v1_materials__asset_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                asset_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: boolean;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    set_material_reference_note_api_v1_materials__asset_id__reference_note_patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                asset_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MaterialReferenceNoteRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    create_material_api_v1_materials__asset_scope__post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                asset_scope: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MaterialUploadRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    ops_runtime_summary_api_v1_ops_runtime_summary_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: number | null;
                    };
                };
            };
        };
    };
    list_ops_tenants_api_v1_ops_tenants_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    }[];
                };
            };
        };
    };
    provision_tenant_api_v1_ops_tenants_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateTenantRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProvisionedTenantResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    disable_tenant_api_v1_ops_tenants__tenant_id__disable_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                tenant_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: boolean;
                    };
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    enable_tenant_api_v1_ops_tenants__tenant_id__enable_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                tenant_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: boolean;
                    };
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    ops_unmet_capability_requests_api_v1_ops_unmet_capability_requests_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    }[];
                };
            };
        };
    };
    classify_unmet_capability_request_api_v1_ops_unmet_capability_requests__stable_request_id__post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                stable_request_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UnmetCapabilityResponseRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    session_context_api_v1_session_context_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    revise_content_api_v1_tasks__task_id__revisions_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                task_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RevisionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ContentVersionResponse"] | components["schemas"]["ContentQuestionResponse"];
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    get_version_api_v1_tasks__task_id__versions__version__get: {
        parameters: {
            query?: {
                publishing_identity_id?: string | null;
                target?: "douyin_video" | "xiaohongshu_video" | "xiaohongshu_graphic" | "wechat_channels_video";
            };
            header?: never;
            path: {
                task_id: string;
                version: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ContentVersionResponse"];
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    management_brand_library_api_v1_tenant_management_brand_library_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    }[];
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    create_management_brand_library_entry_api_v1_tenant_management_brand_library_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BrandLibraryEntryRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    set_management_brand_library_enabled_api_v1_tenant_management_brand_library__entry_id__enabled_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                entry_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SetEnabledRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    management_brand_library_versions_api_v1_tenant_management_brand_library__entry_id__versions_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                entry_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    }[];
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    save_management_brand_library_version_api_v1_tenant_management_brand_library__entry_id__versions_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                entry_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BrandLibraryVersionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    preview_management_brand_library_entry_api_v1_tenant_management_brand_library_preview_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BrandLibraryPreviewRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    management_products_api_v1_tenant_management_brand_products_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    }[];
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    save_management_product_api_v1_tenant_management_brand_products_put: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SaveBrandProductRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    set_management_product_enabled_api_v1_tenant_management_brand_products__sku__enabled_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                sku: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SetEnabledRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    management_product_versions_api_v1_tenant_management_brand_products__sku__versions_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                sku: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    }[];
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    preview_management_products_api_v1_tenant_management_brand_products_preview_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ProductImportPreviewRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    management_brand_publication_api_v1_tenant_management_brand_publication_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    confirm_management_brand_publication_api_v1_tenant_management_brand_publication__projection_id__confirm_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                projection_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    create_management_brand_publication_candidate_api_v1_tenant_management_brand_publication_candidates_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BrandPublicationProjectionCandidateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    management_brand_publication_sources_api_v1_tenant_management_brand_publication_sources_get: {
        parameters: {
            query?: {
                query?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    }[];
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    control_organizations_api_v1_tenant_management_control_organizations_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    }[];
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    management_demo_content_index_api_v1_tenant_management_demo_content_index_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    management_display_stores_api_v1_tenant_management_display_stores_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    }[];
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    create_management_display_store_api_v1_tenant_management_display_stores_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SaveDisplayStoreRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    set_management_display_store_enabled_api_v1_tenant_management_display_stores__store_id__enabled_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                store_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SetEnabledRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    save_management_display_store_version_api_v1_tenant_management_display_stores__store_id__versions_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                store_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SaveDisplayStoreRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    management_onboarding_prefill_api_v1_tenant_management_onboarding_prefill_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    management_operators_api_v1_tenant_management_operators_get: {
        parameters: {
            query?: {
                include_archived?: boolean;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    }[];
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    create_operator_api_v1_tenant_management_operators_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateOperatorRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    management_organization_materials_api_v1_tenant_management_organization_materials_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    }[];
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    create_management_organization_material_api_v1_tenant_management_organization_materials_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OrganizationMaterialUploadRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    delete_management_organization_material_api_v1_tenant_management_organization_materials__asset_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                asset_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: boolean;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    set_management_organization_material_enabled_api_v1_tenant_management_organization_materials__asset_id__enabled_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                asset_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SetEnabledRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    management_product_media_bindings_api_v1_tenant_management_organization_materials__asset_id__product_bindings_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                asset_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    }[];
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    create_management_product_media_binding_api_v1_tenant_management_organization_materials__asset_id__product_bindings_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                asset_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateProductMediaBindingRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    set_management_product_media_binding_enabled_api_v1_tenant_management_organization_materials__asset_id__product_bindings__binding_id__enabled_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                asset_id: string;
                binding_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SetEnabledRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    management_organization_material_versions_api_v1_tenant_management_organization_materials__asset_id__versions_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                asset_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    }[];
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    save_management_organization_material_version_api_v1_tenant_management_organization_materials__asset_id__versions_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                asset_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MaterialMetadataVersionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    tenant_organizations_api_v1_tenant_management_organizations_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    }[];
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    create_tenant_organization_api_v1_tenant_management_organizations_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateOrganizationRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    update_tenant_organization_api_v1_tenant_management_organizations__organization_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                organization_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UpdateOrganizationRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    set_tenant_organization_enabled_api_v1_tenant_management_organizations__organization_id__enabled_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                organization_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SetEnabledRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    create_platform_carrier_api_v1_tenant_management_platform_carriers_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreatePlatformCarrierRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    set_platform_carrier_enabled_api_v1_tenant_management_platform_carriers__account_id__enabled_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                account_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SetEnabledRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    management_accounts_api_v1_tenant_management_publishing_accounts_get: {
        parameters: {
            query?: {
                include_archived?: boolean;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    }[];
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    create_publishing_account_api_v1_tenant_management_publishing_accounts_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreatePublishingAccountRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    update_publishing_account_api_v1_tenant_management_publishing_accounts__account_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                account_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UpdatePublishingAccountRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    declare_control_organization_api_v1_tenant_management_publishing_accounts__account_id__control_organization_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                account_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ControlOrganizationRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    set_publishing_account_enabled_api_v1_tenant_management_publishing_accounts__account_id__enabled_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                account_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SetEnabledRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    management_account_expression_profile_api_v1_tenant_management_publishing_accounts__account_id__expression_profile_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                account_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    management_account_expression_versions_api_v1_tenant_management_publishing_accounts__account_id__expression_profile_versions_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                account_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    }[];
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    save_management_account_expression_profile_api_v1_tenant_management_publishing_accounts__account_id__expression_profile_versions_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                account_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AccountExpressionVersionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    update_publishing_speaker_kind_api_v1_tenant_management_publishing_accounts__account_id__speaker_kind_patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                account_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UpdatePublishingSpeakerKindRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    management_team_usage_api_v1_tenant_management_team_usage_get: {
        parameters: {
            query?: {
                window_days?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    create_tenant_user_api_v1_tenant_management_users_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateTenantUserRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CreatedTenantUserResponse"];
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    update_tenant_user_api_v1_tenant_management_users__user_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                user_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UpdateTenantUserRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: string;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    disable_tenant_user_api_v1_tenant_management_users__user_id__disable_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                user_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: boolean;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    update_tenant_user_grants_api_v1_tenant_management_users__user_id__grants_patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                user_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UpdateTenantUserGrantsRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    set_expression_profile_maintenance_api_v1_tenant_management_users__user_id__publishing_accounts__account_id__profile_maintenance_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                account_id: string;
                user_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SetExpressionProfileMaintenanceRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    revoke_publishing_account_grant_api_v1_tenant_management_users__user_id__publishing_accounts__account_id__revoke_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                account_id: string;
                user_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: boolean;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    reset_tenant_user_api_v1_tenant_management_users__user_id__reset_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                user_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ResetTenantUserResponse"];
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    restore_tenant_user_api_v1_tenant_management_users__user_id__restore_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                user_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RestoredTenantUserResponse"];
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    read_creation_preferences_api_v1_user_creation_preferences_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    save_creation_preferences_api_v1_user_creation_preferences_put: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreationPreferenceRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    delete_creation_preferences_api_v1_user_creation_preferences_delete: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    update_default_persona_api_v1_user_default_persona_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DefaultPersonaRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    user_organization_materials_api_v1_user_organization_materials_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    }[];
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    create_user_organization_material_api_v1_user_organization_materials_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MaterialUploadRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    delete_user_organization_material_api_v1_user_organization_materials__asset_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                asset_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: boolean;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    set_user_organization_material_enabled_api_v1_user_organization_materials__asset_id__enabled_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                asset_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SetEnabledRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    user_organization_material_versions_api_v1_user_organization_materials__asset_id__versions_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                asset_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    }[];
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    save_user_organization_material_version_api_v1_user_organization_materials__asset_id__versions_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                asset_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MaterialMetadataVersionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    content_workbench_content_get: {
        parameters: {
            query?: {
                notice?: string | null;
                publishing_identity_id?: string | null;
                target?: ("douyin_video" | "xiaohongshu_video" | "xiaohongshu_graphic" | "wechat_channels_video") | null;
                task?: string | null;
                version?: number | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "text/html": string;
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    content_task_workbench_content_tasks__task__get: {
        parameters: {
            query?: {
                publishing_identity_id?: string | null;
                target?: ("douyin_video" | "xiaohongshu_video" | "xiaohongshu_graphic" | "wechat_channels_video") | null;
                version?: number | null;
            };
            header?: never;
            path: {
                task: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "text/html": string;
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    display_workbench_display_get: {
        parameters: {
            query?: {
                notice?: string | null;
                store_id?: string | null;
                task?: string | null;
                version?: number | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "text/html": string;
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    organization_materials_portal_materials_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "text/html": string;
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    tenant_management_portal_tenant_admin_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "text/html": string;
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    ui_display_generate_ui_display_generate_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            303: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    ui_display_revise_ui_display_revise_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            303: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    ui_generate_ui_generate_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 可信会话中的表单操作完成后重定向回工作台。 */
            303: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    ui_reuse_ui_reuse_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 可信会话中的表单操作完成后重定向回工作台。 */
            303: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    ui_revise_ui_revise_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 可信会话中的表单操作完成后重定向回工作台。 */
            303: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    ui_save_ui_save_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 可信会话中的表单操作完成后重定向回工作台。 */
            303: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    tenant_user_portal_user_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "text/html": string;
                };
            };
            /** @description 缺少或无效的可信会话。 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 当前可信会话属于另一应用。 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 业务失败；生成失败时不会产生半成品版本。 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
}
