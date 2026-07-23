from __future__ import annotations

from abc import ABC, abstractmethod

from src.shared.types import DisplayGenerationInput, GeneratedDisplayArtifact


class DisplayGenerator(ABC):
    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the deterministic DM01 executor identifier."""

    @abstractmethod
    def generate(self, request: DisplayGenerationInput) -> GeneratedDisplayArtifact:
        """Compile one DM01 plan or raise GenerationFailed."""
