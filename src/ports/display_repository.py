from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from src.shared.types import ActiveAsset, DisplayContext, DisplayScope


class DisplayRepository(ABC):
    @abstractmethod
    def load_context(self, scope: DisplayScope) -> DisplayContext | None:
        """Load the wall structure and the default seed a new task starts from."""

    @abstractmethod
    def load_task_context(self, scope: DisplayScope, task_id: UUID) -> DisplayContext | None:
        """Load the frozen context an existing task was compiled from, or None if it predates it."""

    @abstractmethod
    def load_assets(self, revision: bool) -> tuple[ActiveAsset, ...]:
        """Compile only DM01 assets applicable to this operation."""

    @abstractmethod
    def create_run(
        self,
        scope: DisplayScope,
        inventory_text: str,
        inventory: tuple[tuple[str, int], ...],
        context: DisplayContext,
        model: str,
        assets: tuple[ActiveAsset, ...],
    ) -> tuple[UUID, UUID]:
        """Create an internal display task and auditable running generation."""

    @abstractmethod
    def create_revision_run(
        self,
        scope: DisplayScope,
        task_id: UUID,
        feedback: str,
        context: DisplayContext,
        model: str,
        assets: tuple[ActiveAsset, ...],
    ) -> tuple[UUID, dict[str, object], tuple[tuple[str, int], ...]]:
        """Lock the visible task and create its next running revision."""

    @abstractmethod
    def complete_run(
        self,
        scope: DisplayScope,
        task_id: UUID,
        run_id: UUID,
        artifact: dict[str, object],
        model: str,
        latency_ms: int,
        retry_count: int,
        usage: dict[str, int] | None,
    ) -> dict[str, object]:
        """Atomically persist an immutable DisplayArtifact version."""

    @abstractmethod
    def fail_run(self, scope: DisplayScope, task_id: UUID, run_id: UUID, reason: str) -> None:
        """Record a failed run without any version."""

    @abstractmethod
    def fetch_version(self, scope: DisplayScope, task_id: UUID, version: int) -> dict[str, object]:
        """Return one visible immutable display version."""
