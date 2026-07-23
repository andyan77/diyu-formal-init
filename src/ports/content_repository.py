from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from src.shared.types import ActiveAsset, BrandContext, TrustedScope


class ContentRepository(ABC):
    @abstractmethod
    def load_brand_context(self, scope: TrustedScope) -> BrandContext:
        """Load the authorized brand/account context in the trusted scope."""

    @abstractmethod
    def create_task_and_running_run(
        self,
        scope: TrustedScope,
        weak_seed: str,
        parent_version_id: UUID | None,
        model: str,
        used_assets: tuple[ActiveAsset, ...],
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
    ) -> tuple[UUID, UUID, str]:
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
    def load_active_assets(self, scope: TrustedScope, weak_seed: str) -> tuple[ActiveAsset, ...]:
        """Compile only currently applicable system assets for the P1 task."""

    @abstractmethod
    def task_seed(self, scope: TrustedScope, task_id: UUID) -> str:
        """Load the current user's original task seed without widening scope."""
