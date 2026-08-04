from __future__ import annotations

import time
from collections.abc import Callable
from uuid import UUID

from src.infrastructure.production_auth import MODEL_REQUEST_DUPLICATE_WINDOW_SECONDS

FORMAL_SUBMISSION_CLOCK_SAFETY_SECONDS = 0.05
FORMAL_SUBMISSION_CLOCK_EPSILON_SECONDS = 1e-9


class FormalApiSubmissionPacer:
    """Keep serial acceptance requests outside the production duplicate window."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._clock = clock
        self._sleeper = sleeper
        self._last_submission_by_tenant: dict[UUID, float] = {}

    def before_request(self, tenant_id: UUID) -> None:
        previous = self._last_submission_by_tenant.get(tenant_id)
        minimum_interval = (
            MODEL_REQUEST_DUPLICATE_WINDOW_SECONDS
            + FORMAL_SUBMISSION_CLOCK_SAFETY_SECONDS
        )
        if previous is not None:
            remaining = minimum_interval - (self._clock() - previous)
            if remaining > FORMAL_SUBMISSION_CLOCK_EPSILON_SECONDS:
                self._sleeper(remaining)
        self._last_submission_by_tenant[tenant_id] = self._clock()
