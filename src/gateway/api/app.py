from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlencode
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request, Security, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.security import APIKeyCookie

from src.composition.bootstrap import build_content_service, build_display_service
from src.gateway.api.contracts import (
    ContentVersionResponse,
    CreateContentRequest,
    CreateDisplayRequest,
    DisplayQuestionResponse,
    DisplayRevisionRequest,
    DisplayVersionResponse,
    GreetingResponse,
    RevisionRequest,
    SavedVersionResponse,
)
from src.gateway.api.html import render_display_workbench, render_workbench, workbench_location
from src.gateway.api.session import SessionAuthority, set_session_cookie
from src.gateway.api.settings import Settings
from src.shared.errors import DomainError
from src.shared.types import TrustedScope


def create_app(settings: Settings | None = None) -> FastAPI:
    current_settings = settings or Settings.model_validate({})
    authority = SessionAuthority(current_settings)
    service = build_content_service(current_settings)
    display_service = build_display_service(current_settings)
    app = FastAPI(
        title="笛语 M3-1 P1 API",
        version="0.1.0",
        description="可信 cookie 会话决定租户、品牌、发布账号和操作人；客户端不能切换这些作用域。",
    )
    session_cookie = APIKeyCookie(name="diyu_session", auto_error=False)
    business_failures: dict[int | str, dict[str, Any]] = {
        401: {"description": "缺少或无效的可信会话。"},
        422: {"description": "业务失败；生成失败时不会产生半成品版本。"},
    }
    ui_responses: dict[int | str, dict[str, Any]] = {
        303: {"description": "可信会话中的表单操作完成后重定向回工作台。"},
        401: {"description": "缺少或无效的可信会话。"},
    }

    def scope_from_request(
        request: Request, _: str | None = Security(session_cookie)
    ) -> TrustedScope:
        return authority.require(request)

    def display_scope_from_request(
        request: Request, _: str | None = Security(session_cookie)
    ) -> object:
        authority.require(request)
        return authority.display_scope()

    @app.post(
        "/api/v1/display",
        response_model=DisplayVersionResponse | DisplayQuestionResponse,
        responses=business_failures,
    )
    def create_display(
        payload: CreateDisplayRequest, scope: object = Depends(display_scope_from_request)
    ) -> dict[str, object]:
        return display_service.create(scope, payload.inventory_text)  # type: ignore[arg-type]

    @app.post(
        "/api/v1/display-tasks/{task_id}/revisions",
        status_code=status.HTTP_201_CREATED,
        response_model=DisplayVersionResponse | DisplayQuestionResponse,
        responses=business_failures,
    )
    def revise_display(
        task_id: UUID,
        payload: DisplayRevisionRequest,
        scope: object = Depends(display_scope_from_request),
    ) -> dict[str, object]:
        return display_service.revise(scope, task_id, payload.feedback)  # type: ignore[arg-type]

    @app.get(
        "/api/v1/display-tasks/{task_id}/versions/{version}",
        response_model=DisplayVersionResponse,
        responses=business_failures,
    )
    def get_display(
        task_id: UUID, version: int, scope: object = Depends(display_scope_from_request)
    ) -> dict[str, object]:
        return display_service.fetch_version(scope, task_id, version)  # type: ignore[arg-type]

    @app.exception_handler(DomainError)
    async def domain_error_handler(_: Request, exc: DomainError) -> object:
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.get("/assets/diyu-logo-horizontal.svg", include_in_schema=False)
    def logo() -> FileResponse:
        return FileResponse("assets/brand/diyu-vi/svg/diyu-logo-horizontal.svg")

    @app.get("/display", response_class=HTMLResponse)
    def display_workbench(
        request: Request,
        task: UUID | None = None,
        version: int | None = None,
        notice: str | None = None,
    ) -> HTMLResponse:
        result = None
        if task is not None and version is not None:
            authority.require(request)
            result = display_service.fetch_version(authority.display_scope(), task, version)
        response = HTMLResponse(render_display_workbench(result, notice))
        set_session_cookie(response, authority)
        return response

    @app.post(
        "/ui/display/generate",
        status_code=303,
        response_class=RedirectResponse,
        dependencies=[Security(session_cookie)],
    )
    async def ui_display_generate(request: Request) -> RedirectResponse:
        fields = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
        result = display_service.create(
            authority.display_scope(), fields.get("inventory_text", [""])[0]
        )
        if result["kind"] == "question":
            return RedirectResponse(
                "/display?" + urlencode({"notice": str(result["message"])}), status_code=303
            )
        return RedirectResponse(
            f"/display?task={result['task_id']}&version={result['version']}", status_code=303
        )

    @app.post(
        "/ui/display/revise",
        status_code=303,
        response_class=RedirectResponse,
        dependencies=[Security(session_cookie)],
    )
    async def ui_display_revise(request: Request) -> RedirectResponse:
        fields = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
        result = display_service.revise(
            authority.display_scope(),
            UUID(fields.get("task_id", [""])[0]),
            fields.get("feedback", [""])[0],
        )
        if result["kind"] == "question":
            return RedirectResponse(
                "/display?" + urlencode({"notice": str(result["message"])}), status_code=303
            )
        return RedirectResponse(
            f"/display?task={result['task_id']}&version={result['version']}", status_code=303
        )

    @app.post(
        "/api/v1/content",
        response_model=ContentVersionResponse | GreetingResponse,
        responses=business_failures,
    )
    def create_content(
        payload: CreateContentRequest, scope: TrustedScope = Depends(scope_from_request)
    ) -> dict[str, object]:
        return service.create_from_weak_seed(scope, payload.weak_seed, payload.reuse_version_id)

    @app.post(
        "/api/v1/tasks/{task_id}/revisions",
        status_code=status.HTTP_201_CREATED,
        response_model=ContentVersionResponse,
        responses=business_failures,
    )
    def revise_content(
        task_id: UUID, payload: RevisionRequest, scope: TrustedScope = Depends(scope_from_request)
    ) -> dict[str, object]:
        return service.revise(scope, task_id, payload.instruction)

    @app.get(
        "/api/v1/tasks/{task_id}/versions/{version}",
        response_model=ContentVersionResponse,
        responses=business_failures,
    )
    def get_version(
        task_id: UUID, version: int, scope: TrustedScope = Depends(scope_from_request)
    ) -> dict[str, object]:
        return service.fetch_version(scope, task_id, version)

    @app.post(
        "/api/v1/content-versions/{version_id}/save",
        response_model=SavedVersionResponse,
        responses=business_failures,
    )
    def save_version(
        version_id: UUID, scope: TrustedScope = Depends(scope_from_request)
    ) -> dict[str, object]:
        return service.save_version(scope, version_id)

    @app.get("/", response_class=HTMLResponse)
    def workbench(
        request: Request,
        task: UUID | None = None,
        version: int | None = None,
        notice: str | None = None,
    ) -> HTMLResponse:
        result = None
        if task is not None and version is not None:
            try:
                result = service.fetch_version(authority.require(request), task, version)
            except DomainError as exc:
                raise HTTPException(status_code=404, detail="找不到当前会话可见的版本") from exc
        response = HTMLResponse(render_workbench(current_settings.generator_mode, result, notice))
        set_session_cookie(response, authority)
        return response

    @app.post(
        "/ui/generate",
        status_code=status.HTTP_303_SEE_OTHER,
        response_class=RedirectResponse,
        dependencies=[Security(session_cookie)],
        responses=ui_responses,
    )
    async def ui_generate(request: Request) -> RedirectResponse:
        fields = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
        weak_seed = fields.get("weak_seed", [""])[0]
        try:
            result = service.create_from_weak_seed(authority.require(request), weak_seed)
        except DomainError as exc:
            return RedirectResponse("/?notice=" + str(exc), status_code=status.HTTP_303_SEE_OTHER)
        if result["kind"] == "greeting":
            return RedirectResponse(
                "/?notice=" + str(result["message"]), status_code=status.HTTP_303_SEE_OTHER
            )
        return RedirectResponse(workbench_location(result), status_code=status.HTTP_303_SEE_OTHER)

    @app.post(
        "/ui/revise",
        status_code=status.HTTP_303_SEE_OTHER,
        response_class=RedirectResponse,
        dependencies=[Security(session_cookie)],
        responses=ui_responses,
    )
    async def ui_revise(request: Request) -> RedirectResponse:
        fields = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
        try:
            task_id = UUID(fields.get("task_id", [""])[0])
            instruction = fields.get("instruction", [""])[0]
            result = service.revise(authority.require(request), task_id, instruction)
        except (DomainError, ValueError) as exc:
            return RedirectResponse("/?notice=" + str(exc), status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(workbench_location(result), status_code=status.HTTP_303_SEE_OTHER)

    @app.post(
        "/ui/reuse",
        status_code=status.HTTP_303_SEE_OTHER,
        response_class=RedirectResponse,
        dependencies=[Security(session_cookie)],
        responses=ui_responses,
    )
    async def ui_reuse(request: Request) -> RedirectResponse:
        fields = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
        try:
            version_id = UUID(fields.get("reuse_version_id", [""])[0])
            weak_seed = fields.get("weak_seed", [""])[0]
            result = service.create_from_weak_seed(
                authority.require(request), weak_seed, version_id
            )
        except (DomainError, ValueError) as exc:
            return RedirectResponse("/?notice=" + str(exc), status_code=status.HTTP_303_SEE_OTHER)
        if result["kind"] == "greeting":
            return RedirectResponse(
                "/?notice=" + str(result["message"]), status_code=status.HTTP_303_SEE_OTHER
            )
        return RedirectResponse(workbench_location(result), status_code=status.HTTP_303_SEE_OTHER)

    @app.post(
        "/ui/save",
        status_code=status.HTTP_303_SEE_OTHER,
        response_class=RedirectResponse,
        dependencies=[Security(session_cookie)],
        responses=ui_responses,
    )
    async def ui_save(request: Request) -> RedirectResponse:
        fields = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
        try:
            version_id = UUID(fields.get("version_id", [""])[0])
            task_id = UUID(fields.get("task_id", [""])[0])
            version = int(fields.get("version", [""])[0])
            saved = service.save_version(authority.require(request), version_id)
        except (DomainError, ValueError) as exc:
            return RedirectResponse("/?notice=" + str(exc), status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(
            workbench_location(
                {"task_id": task_id, "version": version},
                f"已主动保存版本 {saved['version_id']}",
            ),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return app
