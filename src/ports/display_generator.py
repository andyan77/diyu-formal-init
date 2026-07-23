from __future__ import annotations

from abc import ABC, abstractmethod

from src.shared.types import DisplayGenerationInput, GeneratedDisplayArtifact


class DisplayGenerator(ABC):
    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the single configured generator model identifier."""

    @abstractmethod
    def generate(self, request: DisplayGenerationInput) -> GeneratedDisplayArtifact:
        """Generate one DM01 plan or raise GenerationFailed."""
