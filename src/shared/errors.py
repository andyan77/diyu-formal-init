class DomainError(Exception):
    """A user-visible invariant with a stable, non-secret failure envelope."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "DOMAIN_VALIDATION_FAILED",
        failure_stage: str = "validation",
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.failure_stage = failure_stage
        self.retryable = retryable


class GenerationFailed(DomainError):
    """The model did not return an acceptable completed artifact."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "GENERATION_VALIDATION_FAILED",
        failure_stage: str = "validation",
        retryable: bool = False,
    ) -> None:
        super().__init__(
            message,
            error_code=error_code,
            failure_stage=failure_stage,
            retryable=retryable,
        )


class MissingTenantContext(DomainError):
    """Database work was attempted without a trusted tenant scope."""
