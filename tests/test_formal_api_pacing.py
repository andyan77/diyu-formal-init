from __future__ import annotations

from uuid import uuid4

import pytest

from src.tool.formal_api_pacing import FormalApiSubmissionPacer


def test_formal_acceptance_pacer_preserves_production_duplicate_window() -> None:
    now = 100.0
    sleeps: list[float] = []

    def clock() -> float:
        return now

    def sleeper(seconds: float) -> None:
        nonlocal now
        sleeps.append(seconds)
        now += seconds

    primary_tenant = uuid4()
    secondary_tenant = uuid4()
    pacer = FormalApiSubmissionPacer(clock=clock, sleeper=sleeper)

    pacer.before_request(primary_tenant)
    pacer.before_request(secondary_tenant)
    pacer.before_request(primary_tenant)

    assert sleeps == pytest.approx([2.05])
    now += 2.05
    pacer.before_request(primary_tenant)
    assert sleeps == pytest.approx([2.05])


def test_formal_acceptance_pacer_waits_again_after_fast_preflight() -> None:
    now = 500.0
    sleeps: list[float] = []

    def clock() -> float:
        return now

    def sleeper(seconds: float) -> None:
        nonlocal now
        sleeps.append(seconds)
        now += seconds

    tenant_id = uuid4()
    pacer = FormalApiSubmissionPacer(clock=clock, sleeper=sleeper)
    pacer.before_request(tenant_id)
    now += 0.1
    pacer.before_request(tenant_id)

    assert sleeps == pytest.approx([1.95])
