from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from src.shared.clause_license import (
    ClauseLicenseReviewsV1,
    ClauseLicenseV1,
)
from src.shared.errors import GenerationFailed


class ReviewerProviderFailure(GenerationFailed):
    """Fail closed while retaining an optional provider response for audit."""

    def __init__(
        self,
        message: str,
        *,
        raw_payload: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.raw_payload = raw_payload


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
