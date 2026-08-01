from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from src.shared.types import (
    DisplayScope,
    SpeakerKind,
    TenantManagementScope,
    TrustedScope,
)


class WorkbenchRepository(ABC):
    """Persistence port for user-visible workbench metadata, never model context."""

    @abstractmethod
    def content_identity(self, scope: TrustedScope) -> dict[str, str]: ...

    @abstractmethod
    def user_portal_identity(self, scope: TrustedScope) -> dict[str, str]: ...

    @abstractmethod
    def management_identity(self, scope: TenantManagementScope) -> dict[str, str]: ...

    @abstractmethod
    def is_content_operator(self, scope: TrustedScope) -> bool: ...

    @abstractmethod
    def is_tenant_manager(self, scope: TenantManagementScope) -> bool: ...

    def tenant_readiness_inputs(
        self,
        scope: TenantManagementScope,
    ) -> dict[str, object]:
        del scope
        return {
            "brand_name": "当前品牌",
            "source_documents": 0,
            "product_media_products": 0,
            "confirmed_stores": 0,
        }

    @abstractmethod
    def management_operators(
        self,
        scope: TenantManagementScope,
        include_archived: bool = False,
    ) -> list[dict[str, object]]: ...

    @abstractmethod
    def management_accounts(
        self,
        scope: TenantManagementScope,
        include_archived: bool = False,
    ) -> list[dict[str, object]]: ...

    @abstractmethod
    def team_usage(
        self,
        scope: TenantManagementScope,
        window_days: int,
    ) -> dict[str, object]: ...

    @abstractmethod
    def management_products(self, scope: TenantManagementScope) -> list[dict[str, object]]: ...

    @abstractmethod
    def management_organization_materials(
        self,
        scope: TenantManagementScope,
        owner_organization_id: UUID | None = None,
    ) -> list[dict[str, object]]: ...

    @abstractmethod
    def brand_library_entries(
        self,
        scope: TenantManagementScope,
    ) -> list[dict[str, object]]: ...

    @abstractmethod
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
    ) -> dict[str, object]: ...

    @abstractmethod
    def brand_library_entry_versions(
        self,
        scope: TenantManagementScope,
        entry_id: UUID,
    ) -> list[dict[str, object]]: ...

    @abstractmethod
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
    ) -> dict[str, object]: ...

    @abstractmethod
    def set_brand_library_entry_enabled(
        self,
        scope: TenantManagementScope,
        entry_id: UUID,
        enabled: bool,
    ) -> dict[str, object]: ...

    @abstractmethod
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
        exact_owner_scope: bool = False,
    ) -> dict[str, object]: ...

    @abstractmethod
    def management_material_versions(
        self,
        scope: TenantManagementScope,
        asset_id: UUID,
        owner_organization_id: UUID | None = None,
    ) -> list[dict[str, object]]: ...

    @abstractmethod
    def save_management_material_version(
        self,
        scope: TenantManagementScope,
        asset_id: UUID,
        title: str,
        reference_note: str,
        visibility_scope: str,
        organization_ids: tuple[UUID, ...],
        owner_organization_id: UUID | None = None,
    ) -> dict[str, object]: ...

    @abstractmethod
    def set_management_material_enabled(
        self,
        scope: TenantManagementScope,
        asset_id: UUID,
        enabled: bool,
        owner_organization_id: UUID | None = None,
    ) -> dict[str, object]: ...

    @abstractmethod
    def management_product_media_bindings(
        self,
        scope: TenantManagementScope,
        asset_id: UUID,
    ) -> list[dict[str, object]]: ...

    @abstractmethod
    def create_management_product_media_binding(
        self,
        scope: TenantManagementScope,
        asset_id: UUID,
        product_id: UUID,
    ) -> dict[str, object]: ...

    @abstractmethod
    def set_management_product_media_binding_enabled(
        self,
        scope: TenantManagementScope,
        asset_id: UUID,
        binding_id: UUID,
        enabled: bool,
    ) -> dict[str, object]: ...

    @abstractmethod
    def request_management_material_deletion(
        self,
        scope: TenantManagementScope,
        asset_id: UUID,
        owner_organization_id: UUID | None = None,
    ) -> str: ...

    @abstractmethod
    def finalize_management_material_deletion(
        self,
        scope: TenantManagementScope,
        asset_id: UUID,
        owner_organization_id: UUID | None = None,
    ) -> None: ...

    @abstractmethod
    def management_demo_content_index(self, scope: TenantManagementScope) -> dict[str, object]: ...

    @abstractmethod
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
    ) -> dict[str, object]: ...

    @abstractmethod
    def management_product_versions(
        self,
        scope: TenantManagementScope,
        sku: str,
    ) -> list[dict[str, object]]: ...

    @abstractmethod
    def set_management_product_enabled(
        self,
        scope: TenantManagementScope,
        sku: str,
        enabled: bool,
    ) -> dict[str, object]: ...

    @abstractmethod
    def create_publishing_account(
        self,
        scope: TenantManagementScope,
        name: str,
        channel: str,
        content_role_name: str,
        voice_boundary: str,
        operator_id: UUID | None = None,
        control_organization_id: UUID | None = None,
        operator_can_maintain_expression_profile: bool = False,
        business_data_kind: str = "formal_business_data",
        initial_profile: dict[str, str] | None = None,
        speaker_kind: SpeakerKind = "unknown",
    ) -> dict[str, object]: ...

    @abstractmethod
    def update_publishing_speaker_kind(
        self,
        scope: TenantManagementScope,
        account_id: UUID,
        speaker_kind: SpeakerKind,
    ) -> dict[str, object]: ...

    @abstractmethod
    def update_publishing_account(
        self,
        scope: TenantManagementScope,
        account_id: UUID,
        name: str | None,
        control_organization_id: UUID | None,
    ) -> dict[str, object]: ...

    @abstractmethod
    def set_publishing_account_enabled(
        self,
        scope: TenantManagementScope,
        account_id: UUID,
        enabled: bool,
    ) -> dict[str, object]: ...

    @abstractmethod
    def create_platform_carrier(
        self,
        scope: TenantManagementScope,
        source_account_id: UUID,
        name: str,
        channel: str,
        operator_id: UUID | None = None,
    ) -> dict[str, object]: ...

    @abstractmethod
    def set_platform_carrier_enabled(
        self,
        scope: TenantManagementScope,
        account_id: UUID,
        enabled: bool,
    ) -> dict[str, object]: ...

    @abstractmethod
    def create_operator(
        self,
        scope: TenantManagementScope,
        display_name: str,
        account_id: UUID,
        default_persona_name: str,
        default_persona_boundary: str,
    ) -> dict[str, object]: ...

    @abstractmethod
    def update_default_persona(self, scope: TrustedScope, name: str, boundary: str) -> dict[str, object]: ...

    @abstractmethod
    def display_identity(self, scope: DisplayScope) -> dict[str, str]: ...

    @abstractmethod
    def recent_content(self, scope: TrustedScope) -> list[dict[str, object]]: ...

    @abstractmethod
    def content_versions(self, scope: TrustedScope, task_id: UUID) -> list[dict[str, object]]: ...

    @abstractmethod
    def recent_display(self, scope: DisplayScope) -> list[dict[str, object]]: ...

    @abstractmethod
    def display_versions(self, scope: DisplayScope, task_id: UUID) -> list[dict[str, object]]: ...

    @abstractmethod
    def readiness(self, scope: TenantManagementScope) -> list[dict[str, object]]: ...

    @abstractmethod
    def management_display_stores(
        self,
        scope: TenantManagementScope,
    ) -> list[dict[str, object]]: ...

    @abstractmethod
    def save_management_display_store(
        self,
        scope: TenantManagementScope,
        store_id: UUID | None,
        name: str,
        control_organization_id: UUID,
        execution_organization_id: UUID,
        rail_profile: dict[str, object],
    ) -> dict[str, object]: ...

    @abstractmethod
    def set_management_display_store_enabled(
        self,
        scope: TenantManagementScope,
        store_id: UUID,
        enabled: bool,
    ) -> dict[str, object]: ...

    @abstractmethod
    def brand_expression(self, scope: TenantManagementScope) -> dict[str, object]: ...

    @abstractmethod
    def confirm_brand_expression(self, scope: TenantManagementScope, draft: str) -> dict[str, object]: ...

    @abstractmethod
    def list_series(self, scope: TrustedScope) -> list[dict[str, object]]: ...

    @abstractmethod
    def create_series(self, scope: TrustedScope, title: str, premise: str) -> dict[str, object]: ...

    @abstractmethod
    def add_series_item(
        self, scope: TrustedScope, series_id: UUID, task_id: UUID, position: int | None
    ) -> dict[str, object]: ...

    @abstractmethod
    def reorder_series(self, scope: TrustedScope, series_id: UUID, task_ids: tuple[UUID, ...]) -> dict[str, object]: ...

    @abstractmethod
    def reset_series(self, scope: TrustedScope, series_id: UUID) -> dict[str, object]: ...

    @abstractmethod
    def list_materials(self, scope: TrustedScope) -> list[dict[str, object]]: ...

    @abstractmethod
    def is_material_maintainer(self, scope: TrustedScope) -> bool: ...

    @abstractmethod
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
    ) -> dict[str, object]: ...

    @abstractmethod
    def request_material_deletion(self, scope: TrustedScope, asset_id: UUID) -> str: ...

    @abstractmethod
    def finalize_material_deletion(self, scope: TrustedScope, asset_id: UUID) -> None: ...
