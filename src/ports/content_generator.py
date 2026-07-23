from __future__ import annotations

from abc import ABC, abstractmethod

from src.shared.types import GeneratedArtifact, GenerationInput


class ContentGenerator(ABC):
    @property
    @abstractmethod
    def model_name(self) -> str:
        """The provider-verified model identifier recorded for each run."""

    @abstractmethod
    def generate(self, request: GenerationInput) -> GeneratedArtifact:
        """Generate one complete P1 artifact or raise GenerationFailed."""
