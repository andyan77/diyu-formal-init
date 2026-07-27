from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from src.shared.types import DisplayScope, TenantManagementScope, TrustedScope


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

    @abstractmethod
    def management_operators(self, scope: TenantManagementScope) -> list[dict[str, object]]: ...

    @abstractmethod
    def management_accounts(self, scope: TenantManagementScope) -> list[dict[str, object]]: ...

    @abstractmethod
    def management_products(self, scope: TenantManagementScope) -> list[dict[str, object]]: ...

    @abstractmethod
    def management_organization_materials(
        self, scope: TenantManagementScope
    ) -> list[dict[str, object]]: ...

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
    ) -> dict[str, object]: ...

    @abstractmethod
    def request_management_material_deletion(
        self,
        scope: TenantManagementScope,
        asset_id: UUID,
    ) -> str: ...

    @abstractmethod
    def finalize_management_material_deletion(
        self,
        scope: TenantManagementScope,
        asset_id: UUID,
    ) -> None: ...

    @abstractmethod
    def management_demo_content_index(
        self, scope: TenantManagementScope
    ) -> dict[str, object]: ...

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
    ) -> dict[str, object]: ...

    @abstractmethod
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
    ) -> dict[str, object]: ...

    @abstractmethod
    def create_platform_carrier(
        self,
        scope: TenantManagementScope,
        source_account_id: UUID,
        name: str,
        channel: str,
        operator_id: UUID,
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
    def readiness(self, scope: TenantManagementScope) -> list[dict[str, str]]: ...

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
