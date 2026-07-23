from __future__ import annotations

from abc import ABC, abstractmethod

from src.shared.types import ContentProduct, GeneratedArtifact, GenerationInput, RoutingInput


class ContentGenerator(ABC):
    @property
    @abstractmethod
    def model_name(self) -> str:
        """The provider-verified model identifier recorded for each run."""

    @abstractmethod
    def route(self, request: RoutingInput) -> ContentProduct | None:
        """Return one primary product, or no task for ordinary conversation."""

    @abstractmethod
    def generate(self, request: GenerationInput) -> GeneratedArtifact:
        """Generate one complete P1 artifact or raise GenerationFailed."""
