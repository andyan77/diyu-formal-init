from __future__ import annotations

from abc import ABC, abstractmethod

from src.shared.types import (
    ContentProduct,
    ConversationDecision,
    ConversationInput,
    GeneratedArtifact,
    GenerationInput,
    RoutingInput,
)


class ContentGenerator(ABC):
    @property
    @abstractmethod
    def model_name(self) -> str:
        """The provider-verified model identifier recorded for each run."""

    @property
    @abstractmethod
    def reviewer_model_name(self) -> str:
        """The independently configured Reviewer model recorded for each run."""

    @abstractmethod
    def route(self, request: RoutingInput) -> ContentProduct | None:
        """Return one primary product, or no task for ordinary conversation."""

    def collaborate(self, request: ConversationInput) -> ConversationDecision:
        """Continue natural collaboration or return one generation-ready brief.

        Legacy test and integration generators may implement only the durable generation
        contract. They remain usable for that path, while the UI-05 conversation endpoint
        requires an adapter that explicitly overrides this method.
        """
        del request
        raise NotImplementedError("this content generator does not support natural collaboration")

    @abstractmethod
    def generate(self, request: GenerationInput) -> GeneratedArtifact:
        """Generate one complete P1 artifact or raise GenerationFailed."""
