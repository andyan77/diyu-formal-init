class DomainError(Exception):
    """A user-visible domain invariant failure."""


class GenerationFailed(DomainError):
    """The model did not return an acceptable completed artifact."""


class MissingTenantContext(DomainError):
    """Database work was attempted without a trusted tenant scope."""
