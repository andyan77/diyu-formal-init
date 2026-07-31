from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from src.shared.dm01_rules import DM01RuleBundleV1
from src.shared.types import ActiveAsset, DisplayContext, DisplayScope


class DisplayRepository(ABC):
    @abstractmethod
    def load_context(
        self,
        scope: DisplayScope,
        inventory: tuple[tuple[str, int], ...] | None = None,
        product_version_inventory: tuple[tuple[UUID, int], ...] | None = None,
    ) -> DisplayContext | None:
        """Load the store identity, or resolve a formal product snapshot for a new task."""

    @abstractmethod
    def load_task_context(self, scope: DisplayScope, task_id: UUID) -> DisplayContext | None:
        """Load the frozen context this task was compiled from.

        Returns None only when the task is visible in scope but kept no snapshot; a task outside
        the caller's scope fails closed instead, so a missing snapshot never doubles as a leak.
        """

    @abstractmethod
    def load_assets(self, revision: bool) -> tuple[ActiveAsset, ...]:
        """Compile only DM01 assets applicable to this operation."""

    @abstractmethod
    def load_rule_bundle(self) -> DM01RuleBundleV1:
        """Resolve the exact governed rule bundle required by generation and revision."""

    @abstractmethod
    def available_products(self, scope: DisplayScope) -> list[dict[str, object]]:
        """List only active current product versions visible to this execution organization."""

    @abstractmethod
    def create_run(
        self,
        scope: DisplayScope,
        inventory_text: str,
        inventory: tuple[tuple[str, int], ...],
        context: DisplayContext,
        model: str,
        assets: tuple[ActiveAsset, ...],
        hard_requirements: frozenset[str],
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
    def recover_stale_runs(self, scope: DisplayScope, lease_seconds: int) -> int:
        """Fail only expired running DM01 work in the caller's trusted display scope."""

    @abstractmethod
    def fetch_version(self, scope: DisplayScope, task_id: UUID, version: int) -> dict[str, object]:
        """Return one visible immutable display version."""
