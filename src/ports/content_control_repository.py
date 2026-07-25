from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from src.shared.types import TenantManagementScope, TrustedScope


class ContentControlRepository(ABC):
    """Persistence for the minimum content control surface.

    Account expression profiles, private creation preferences, this-task material references,
    the lightweight plan and unmet capability requests each keep their own scope; none of them
    may stand in for another.
    """

    @abstractmethod
    def expression_source(self, scope: TrustedScope) -> dict[str, str]:
        """Read the brand, role and audience facts a profile draft may legitimately use."""

    @abstractmethod
    def current_account_expression(
        self, tenant_id: UUID, account_id: UUID
    ) -> dict[str, object] | None:
        """Return the account's current profile version, or None when none is confirmed yet."""

    @abstractmethod
    def account_expression_by_id(
        self, tenant_id: UUID, account_id: UUID, profile_id: UUID
    ) -> dict[str, object] | None:
        """Return one immutable historical version so old tasks keep reading what they used."""

    @abstractmethod
    def can_maintain_account_expression(self, scope: TrustedScope) -> bool:
        """Account use never implies profile maintenance; the control organization decides."""

    @abstractmethod
    def can_manage_account_expression(
        self, scope: TenantManagementScope, account_id: UUID
    ) -> bool:
        """A tenant administrator only maintains accounts their own organization controls."""

    @abstractmethod
    def save_account_expression(
        self,
        tenant_id: UUID,
        account_id: UUID,
        created_by: UUID,
        segments: tuple[str, str, str, str, str],
    ) -> dict[str, object]:
        """Append one immutable version and move the account's current pointer to it."""

    @abstractmethod
    def management_accounts_with_expression(
        self, scope: TenantManagementScope
    ) -> list[dict[str, object]]:
        """List this brand's accounts with control organization and current profile version."""

    @abstractmethod
    def creation_preference(self, scope: TrustedScope) -> dict[str, object] | None:
        """Read only the acting person's own private preference."""

    @abstractmethod
    def save_creation_preference(
        self,
        scope: TrustedScope,
        enabled: bool,
        direction_defaults: dict[str, str],
        collaboration_note: str,
        body_related_opt_in: bool,
    ) -> dict[str, object]:
        """Persist the acting person's own private preference and bump its version."""

    @abstractmethod
    def delete_creation_preference(self, scope: TrustedScope) -> bool:
        """Remove the acting person's own private preference; nothing else is affected."""

    @abstractmethod
    def selected_materials(
        self, scope: TrustedScope, asset_ids: tuple[UUID, ...]
    ) -> tuple[dict[str, object], ...]:
        """Resolve explicitly chosen references inside the current scope; fail closed."""

    @abstractmethod
    def available_material_notes(self, scope: TrustedScope) -> tuple[dict[str, object], ...]:
        """List readable text materials and human-written media notes for opportunity drafting."""

    @abstractmethod
    def plan(self, scope: TrustedScope) -> dict[str, object]:
        """Read one account/user scoped lightweight plan document."""

    @abstractmethod
    def save_plan(self, scope: TrustedScope, document: dict[str, object]) -> dict[str, object]:
        """Persist the lightweight plan document; it never creates business tasks."""

    @abstractmethod
    def create_unmet_request(
        self,
        scope: TrustedScope,
        request_text: str,
        catalog_version: str,
        direction_snapshot: dict[str, object],
    ) -> dict[str, object]:
        """Record one explicitly submitted capability gap candidate."""

    @abstractmethod
    def list_unmet_requests(self, scope: TrustedScope) -> list[dict[str, object]]:
        """Return only the acting person's own submitted candidates."""
