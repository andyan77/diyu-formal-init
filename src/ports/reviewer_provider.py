from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from src.shared.clause_license import (
    ClauseLicenseReviewsV1,
    ClauseLicenseV1,
)


@dataclass(frozen=True)
class ReviewerProviderResult:
    """One fail-closed Reviewer response plus provider audit metadata."""

    reviews: ClauseLicenseReviewsV1
    raw_payload: dict[str, object]
    retry_count: int


class ReviewerProvider(ABC):
    """Provider boundary for the single production ClauseLicense Reviewer."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the stable provider identifier used for audit."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the immutable provider model identifier used for audit."""

    @abstractmethod
    def review(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        licenses: tuple[ClauseLicenseV1, ...],
        timeout_seconds: float,
    ) -> ReviewerProviderResult:
        """Extract one complete license proof set or fail closed."""
