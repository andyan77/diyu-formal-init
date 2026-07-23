from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from src.shared.types import (
    ActiveAsset,
    BrandContext,
    ContentProduct,
    ContentTarget,
    FactRepairReceipt,
    MediaFormat,
    PlatformDirection,
    ProductFact,
    RecompileSource,
    TrustedScope,
)


class ContentRepository(ABC):
    @abstractmethod
    def load_brand_context(
        self, scope: TrustedScope, media_format: MediaFormat, production_conditions: str
    ) -> BrandContext:
        """Load the authorized brand/account context in the trusted scope."""

    @abstractmethod
    def create_task_and_running_run(
        self,
        scope: TrustedScope,
        weak_seed: str,
        primary_product: ContentProduct,
        parent_version_id: UUID | None,
        model: str,
        used_assets: tuple[ActiveAsset, ...],
        context: BrandContext,
        products: tuple[ProductFact, ...],
        target: ContentTarget,
        media_format: MediaFormat,
        platform_direction: PlatformDirection,
        source_description: str | None,
        production_conditions: str,
    ) -> tuple[UUID, UUID, str | None]:
        """Create a task and auditable running generation run."""

    @abstractmethod
    def complete_run_with_version(
        self,
        scope: TrustedScope,
        task_id: UUID,
        run_id: UUID,
        outline: str,
        body: str,
        model: str,
        latency_ms: int,
        retry_count: int,
        provider_usage: dict[str, int] | None,
        product_contract: dict[str, str],
        fact_repair_receipts: tuple[FactRepairReceipt, ...],
    ) -> dict[str, object]:
        """Atomically persist a new immutable content version and complete its run."""

    @abstractmethod
    def fail_run(self, scope: TrustedScope, task_id: UUID, run_id: UUID, reason: str) -> None:
        """Persist a failed run without writing a partial content version."""

    @abstractmethod
    def revise_task(
        self,
        scope: TrustedScope,
        task_id: UUID,
        instruction: str,
        model: str,
        used_assets: tuple[ActiveAsset, ...],
        context: BrandContext,
        products: tuple[ProductFact, ...],
        target: ContentTarget,
        platform_direction: PlatformDirection,
        production_conditions: str,
    ) -> tuple[UUID, UUID, str, ContentProduct]:
        """Create the next auditable run for a revision request."""

    @abstractmethod
    def fetch_version(self, scope: TrustedScope, task_id: UUID, version: int) -> dict[str, object]:
        """Return one immutable version visible to the current tenant only."""

    @abstractmethod
    def fetch_version_body(self, scope: TrustedScope, version_id: UUID) -> str:
        """Return an already-authorized body for an explicit revision or reuse only."""

    @abstractmethod
    def save_version(self, scope: TrustedScope, version_id: UUID) -> dict[str, object]:
        """Record explicit user save; no implicit knowledge promotion occurs."""

    @abstractmethod
    def latest_visible_version(self, scope: TrustedScope) -> UUID | None:
        """Find the current user's newest visible version for an explicit continuation."""

    @abstractmethod
    def latest_task_version(self, scope: TrustedScope, task_id: UUID) -> UUID:
        """Return the latest version of one already-authorized task for an explicit recompile."""

    @abstractmethod
    def load_active_assets(
        self,
        scope: TrustedScope,
        primary_product: ContentProduct,
        weak_seed: str,
        products: tuple[ProductFact, ...],
        target: ContentTarget,
        is_recompile: bool,
    ) -> tuple[ActiveAsset, ...]:
        """Compile only assets applicable to the one routed content product."""

    @abstractmethod
    def load_product_facts(self, scope: TrustedScope, weak_seed: str) -> tuple[ProductFact, ...]:
        """Read only current-brand product facts expressly named in the user task."""

    @abstractmethod
    def load_task_product_facts(
        self, scope: TrustedScope, task_id: UUID
    ) -> tuple[ProductFact, ...]:
        """Read the product references resolved and persisted when this scoped task was created."""

    @abstractmethod
    def task_details(
        self, scope: TrustedScope, task_id: UUID
    ) -> tuple[str, ContentProduct, MediaFormat, str]:
        """Load the current user's original seed and stable primary product."""

    @abstractmethod
    def load_recompile_source(self, scope: TrustedScope, version_id: UUID) -> RecompileSource:
        """Read an explicit same-user source version without exposing a source account identifier."""
