from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Literal

ProviderState = Literal["available", "degraded", "unavailable"]
PublicProviderState = Literal["available", "degraded", "unavailable", "unknown"]

STATUS_CONTRACT_VERSION = "public-service-status-v1"
DEFAULT_PROVIDER_FRESHNESS_SECONDS = 900


@dataclass(frozen=True)
class ProviderObservation:
    state: ProviderState
    observed_at: datetime


class ProviderStatusTracker:
    """Keep one normalized process-local observation without request or provider details."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._observation: ProviderObservation | None = None

    def record(self, state: ProviderState, observed_at: datetime | None = None) -> None:
        timestamp = observed_at or datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            raise ValueError("provider observation must be timezone-aware")
        with self._lock:
            self._observation = ProviderObservation(state, timestamp)

    def snapshot(self) -> ProviderObservation | None:
        with self._lock:
            return self._observation


def public_service_status(
    *,
    core_ready: bool,
    provider_observation: ProviderObservation | None,
    now: datetime | None = None,
    freshness_seconds: int = DEFAULT_PROVIDER_FRESHNESS_SECONDS,
) -> dict[str, object]:
    checked_at = now or datetime.now(timezone.utc)
    if checked_at.tzinfo is None or freshness_seconds < 1:
        raise ValueError("status projection requires an aware time and positive freshness")
    content_state: PublicProviderState = "unknown"
    observed_at: str | None = None
    fresh_until: str | None = None
    if provider_observation is not None:
        observed_at = provider_observation.observed_at.isoformat()
        age = (checked_at - provider_observation.observed_at).total_seconds()
        fresh_until = datetime.fromtimestamp(
            provider_observation.observed_at.timestamp() + freshness_seconds,
            tz=timezone.utc,
        ).isoformat()
        if 0 <= age <= freshness_seconds:
            content_state = provider_observation.state
    return {
        "contract_version": STATUS_CONTRACT_VERSION,
        "checked_at": checked_at.isoformat(),
        "provider_freshness_seconds": freshness_seconds,
        "core": {"state": "available" if core_ready else "unavailable"},
        "content_generation": {
            "state": content_state,
            "observed_at": observed_at,
            "fresh_until": fresh_until,
        },
        "text_display": {"state": "available" if core_ready else "unavailable"},
    }
