"""Gate D management routes kept outside the legacy composition-root function."""
# ruff: noqa: B008

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import Depends, FastAPI, status

from src.brain.workbench_service import WorkbenchService
from src.gateway.api.contracts import (
    BrandFeedbackObservationRequest,
    BrandPublicationProjectionCandidateRequest,
)
from src.shared.types import TenantManagementScope

ScopeDependency = Callable[..., TenantManagementScope]
FailureResponses = dict[int | str, dict[str, Any]]


def register_publication_preview_route(
    app: FastAPI,
    service: WorkbenchService,
    scope_dependency: ScopeDependency,
    responses: FailureResponses,
) -> None:
    @app.post("/api/v1/tenant-management/brand-publication/preview", responses=responses)
    def preview_management_brand_publication_candidate(
        payload: BrandPublicationProjectionCandidateRequest,
        scope: TenantManagementScope = Depends(scope_dependency),
    ) -> dict[str, object]:
        return service.preview_brand_publication_candidate(
            scope,
            tuple(item.model_dump() for item in payload.items),
        )


def register_feedback_governance_routes(
    app: FastAPI,
    service: WorkbenchService,
    scope_dependency: ScopeDependency,
    responses: FailureResponses,
) -> None:
    @app.get("/api/v1/tenant-management/brand-feedback-observations", responses=responses)
    def management_brand_feedback_observations(
        scope: TenantManagementScope = Depends(scope_dependency),
    ) -> list[dict[str, object]]:
        return service.brand_feedback_observations(scope)

    @app.post(
        "/api/v1/tenant-management/brand-feedback-observations",
        status_code=status.HTTP_201_CREATED,
        responses=responses,
    )
    def create_management_brand_feedback_observation(
        payload: BrandFeedbackObservationRequest,
        scope: TenantManagementScope = Depends(scope_dependency),
    ) -> dict[str, object]:
        return service.create_brand_feedback_observation(
            scope,
            payload.source_task_id,
            payload.source_version_id,
            payload.source_account_id,
            payload.observation_payload,
        )

    @app.get("/api/v1/tenant-management/brand-relevance-governance", responses=responses)
    def management_brand_relevance_governance(
        scope: TenantManagementScope = Depends(scope_dependency),
    ) -> dict[str, object]:
        return service.brand_relevance_governance(scope)


def register_gate_d_management_routes(
    app: FastAPI,
    service: WorkbenchService,
    scope_dependency: ScopeDependency,
    responses: FailureResponses,
) -> None:
    register_publication_preview_route(app, service, scope_dependency, responses)
    register_feedback_governance_routes(app, service, scope_dependency, responses)
