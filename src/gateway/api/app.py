from __future__ import annotations

import base64
import binascii
from html import escape
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, urlencode
from uuid import UUID

from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Request,
    Security,
    status,
)
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.security import APIKeyCookie
from fastapi.staticfiles import StaticFiles

from src.brain.platform_directions import target_from_text
from src.composition.bootstrap import (
    build_content_service,
    build_display_service,
    build_workbench_service,
)
from src.gateway.api.contracts import (
    AddSeriesItemRequest,
    ApplicationHandoffResponse,
    BrandExpressionConfirmRequest,
    ContentQuestionResponse,
    ContentVersionResponse,
    CreateContentRequest,
    CreateDisplayRequest,
    CreateOperatorRequest,
    CreateSeriesRequest,
    DefaultPersonaRequest,
    DisplayQuestionResponse,
    DisplayRevisionRequest,
    DisplayVersionResponse,
    GreetingResponse,
    MaterialUploadRequest,
    ReorderSeriesRequest,
    RevisionRequest,
    SavedVersionResponse,
)
from src.gateway.api.html import render_spa_shell, workbench_location
from src.gateway.api.session import ApplicationId, SessionAuthority, set_session_cookie
from src.gateway.api.settings import Settings
from src.shared.application_handoff import (
    requests_content_production,
    requests_display_merchandising,
)
from src.shared.errors import DomainError
from src.shared.types import ContentTarget, DisplayScope, TrustedScope

_HEADQUARTERS_TARGETS: tuple[tuple[ContentTarget, str], ...] = (
    ("douyin_video", "抖音视频"),
    ("xiaohongshu_video", "小红书视频"),
    ("xiaohongshu_graphic", "小红书图文"),
    ("wechat_channels_video", "微信视频号视频"),
)
_STORE_TARGETS: tuple[tuple[ContentTarget, str], ...] = (("douyin_video", "抖音视频"),)


def _target(value: str | None, text: str = "") -> ContentTarget:
    natural = target_from_text(text)
    if natural is not None:
        return natural
    if value in {
        "douyin_video",
        "xiaohongshu_video",
        "xiaohongshu_graphic",
        "wechat_channels_video",
    }:
        return cast(ContentTarget, value)
    return "douyin_video"


def create_app(settings: Settings | None = None) -> FastAPI:
    current_settings = settings or Settings.model_validate({})
    authority = SessionAuthority(current_settings)
    service = build_content_service(current_settings)
    display_service = build_display_service(current_settings)
    workbench_service = build_workbench_service(current_settings)
    app = FastAPI(
        title="笛语双应用 API",
        version="0.1.0",
        description="可信 cookie 会话决定租户、品牌、发布账号和操作人；客户端不能切换这些作用域。",
    )
    session_cookie = APIKeyCookie(name="diyu_session", auto_error=False)
    app.mount(
        "/app", StaticFiles(directory=Path("frontend/dist"), check_dir=False), name="frontend"
    )
    business_failures: dict[int | str, dict[str, Any]] = {
        401: {"description": "缺少或无效的可信会话。"},
        403: {"description": "当前可信会话属于另一应用。"},
        422: {"description": "业务失败；生成失败时不会产生半成品版本。"},
    }
    ui_responses: dict[int | str, dict[str, Any]] = {
        303: {"description": "可信会话中的表单操作完成后重定向回工作台。"},
        401: {"description": "缺少或无效的可信会话。"},
        403: {"description": "当前可信会话属于另一应用。"},
    }

    def scope_from_request(
        request: Request, _: str | None = Security(session_cookie)
    ) -> TrustedScope:
        scope = authority.require_content(request)
        if not workbench_service.is_content_operator(scope):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="当前自然人没有此发布账号工作资格",
            )
        return scope

    def user_scope_from_request(
        request: Request, _: str | None = Security(session_cookie)
    ) -> TrustedScope:
        return authority.require_user_portal(request)

    def management_scope_from_request(
        request: Request, _: str | None = Security(session_cookie)
    ) -> TrustedScope:
        scope = authority.require_management(request)
        if not workbench_service.is_tenant_manager(scope):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="当前自然人没有租户管理资格",
            )
        return scope

    def display_scope_from_request(
        request: Request, _: str | None = Security(session_cookie)
    ) -> DisplayScope:
        return authority.require_display(request)

    def content_targets(scope: TrustedScope) -> list[dict[str, str]]:
        options = (
            _STORE_TARGETS
            if scope.account_id == current_settings.demo_store_content_account_id
            else _HEADQUARTERS_TARGETS
        )
        return [{"value": value, "label": label} for value, label in options]

    @app.get("/api/v1/session/context", responses=business_failures)
    def session_context(request: Request) -> dict[str, object]:
        application = authority.application(request)
        if application in {"tenant-admin", "dual-tenant-admin"}:
            return workbench_service.tenant_management_context(
                management_scope_from_request(request)
            )
        if application in {"tenant-user", "dual-tenant-user"}:
            return workbench_service.user_portal_context(user_scope_from_request(request))
        if application == "display-merchandising":
            return workbench_service.display_context(
                authority.require_display(request), current_settings.generator_mode
            )
        scope = scope_from_request(request)
        context = workbench_service.content_context(scope, current_settings.generator_mode)
        context["targets"] = content_targets(scope)
        return context

    @app.get("/api/v1/content/tasks", responses=business_failures)
    def list_content_tasks(
        scope: TrustedScope = Depends(scope_from_request),
    ) -> list[dict[str, object]]:
        return workbench_service.recent_content(scope)

    @app.get("/api/v1/content/tasks/{task_id}/versions", responses=business_failures)
    def list_content_versions(
        task_id: UUID, scope: TrustedScope = Depends(scope_from_request)
    ) -> list[dict[str, object]]:
        return workbench_service.content_versions(scope, task_id)

    @app.get("/api/v1/display/tasks", responses=business_failures)
    def list_display_tasks(
        scope: DisplayScope = Depends(display_scope_from_request),
    ) -> list[dict[str, object]]:
        return workbench_service.recent_display(scope)

    @app.get("/api/v1/display/tasks/{task_id}/versions", responses=business_failures)
    def list_display_versions(
        task_id: UUID, scope: DisplayScope = Depends(display_scope_from_request)
    ) -> list[dict[str, object]]:
        return workbench_service.display_versions(scope, task_id)

    @app.get("/api/v1/admin/readiness", responses=business_failures)
    def readiness(
        scope: TrustedScope = Depends(management_scope_from_request),
    ) -> dict[str, object]:
        return workbench_service.readiness(scope)

    @app.get("/api/v1/admin/brand-expression", responses=business_failures)
    def brand_expression(
        scope: TrustedScope = Depends(management_scope_from_request),
    ) -> dict[str, object]:
        return workbench_service.brand_expression(scope)

    @app.post("/api/v1/admin/brand-expression/confirm", responses=business_failures)
    def confirm_brand_expression(
        payload: BrandExpressionConfirmRequest,
        scope: TrustedScope = Depends(management_scope_from_request),
    ) -> dict[str, object]:
        return workbench_service.confirm_brand_expression(scope, payload.draft)

    @app.get("/api/v1/tenant-management/operators", responses=business_failures)
    def management_operators(
        scope: TrustedScope = Depends(management_scope_from_request),
    ) -> list[dict[str, object]]:
        return workbench_service.management_operators(scope)

    @app.get("/api/v1/tenant-management/publishing-accounts", responses=business_failures)
    def management_accounts(
        scope: TrustedScope = Depends(management_scope_from_request),
    ) -> list[dict[str, object]]:
        return workbench_service.management_accounts(scope)

    @app.post(
        "/api/v1/tenant-management/operators",
        status_code=status.HTTP_201_CREATED,
        responses=business_failures,
    )
    def create_operator(
        payload: CreateOperatorRequest,
        scope: TrustedScope = Depends(management_scope_from_request),
    ) -> dict[str, object]:
        return workbench_service.create_operator(
            scope,
            payload.display_name,
            payload.account_id,
            payload.default_persona_name,
            payload.default_persona_boundary,
        )

    @app.post("/api/v1/user/default-persona", responses=business_failures)
    def update_default_persona(
        payload: DefaultPersonaRequest,
        scope: TrustedScope = Depends(user_scope_from_request),
    ) -> dict[str, object]:
        return workbench_service.update_default_persona(scope, payload.name, payload.boundary)

    @app.get("/api/v1/content/series", responses=business_failures)
    def list_series(scope: TrustedScope = Depends(scope_from_request)) -> list[dict[str, object]]:
        return workbench_service.list_series(scope)

    @app.post(
        "/api/v1/content/series", status_code=status.HTTP_201_CREATED, responses=business_failures
    )
    def create_series(
        payload: CreateSeriesRequest, scope: TrustedScope = Depends(scope_from_request)
    ) -> dict[str, object]:
        return workbench_service.create_series(scope, payload.title, payload.premise)

    @app.post("/api/v1/content/series/{series_id}/items", responses=business_failures)
    def add_series_item(
        series_id: UUID,
        payload: AddSeriesItemRequest,
        scope: TrustedScope = Depends(scope_from_request),
    ) -> dict[str, object]:
        return workbench_service.add_series_item(
            scope, series_id, payload.task_id, payload.position
        )

    @app.put("/api/v1/content/series/{series_id}/items", responses=business_failures)
    def reorder_series(
        series_id: UUID,
        payload: ReorderSeriesRequest,
        scope: TrustedScope = Depends(scope_from_request),
    ) -> dict[str, object]:
        return workbench_service.reorder_series(scope, series_id, tuple(payload.task_ids))

    @app.post("/api/v1/content/series/{series_id}/reset", responses=business_failures)
    def reset_series(
        series_id: UUID, scope: TrustedScope = Depends(scope_from_request)
    ) -> dict[str, object]:
        return workbench_service.reset_series(scope, series_id)

    @app.get("/api/v1/materials", responses=business_failures)
    def list_materials(
        scope: TrustedScope = Depends(scope_from_request),
    ) -> list[dict[str, object]]:
        return workbench_service.list_materials(scope)

    @app.post(
        "/api/v1/materials/{asset_scope}",
        status_code=status.HTTP_201_CREATED,
        responses=business_failures,
    )
    def create_material(
        asset_scope: str,
        upload: MaterialUploadRequest,
        scope: TrustedScope = Depends(scope_from_request),
    ) -> dict[str, object]:
        try:
            payload = base64.b64decode(upload.content_base64, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="素材原件编码无效"
            ) from exc
        return workbench_service.add_material(
            scope,
            asset_scope,
            upload.title,
            upload.filename,
            upload.content_type,
            payload,
            upload.declares_identifiable_minor,
        )

    @app.delete("/api/v1/materials/{asset_id}", responses=business_failures)
    def delete_material(
        asset_id: UUID, scope: TrustedScope = Depends(scope_from_request)
    ) -> dict[str, bool]:
        workbench_service.delete_material(scope, asset_id)
        return {"deleted": True}

    @app.get("/ui/select/content", include_in_schema=False)
    def select_content(request: Request) -> RedirectResponse:
        try:
            current_application = authority.application(request)
        except HTTPException:
            current_application = None
        if current_application == "tenant-admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="当前自然人没有业务工作资格"
            )
        application: ApplicationId = (
            "dual-content-production"
            if current_application in {"dual-tenant-user", "dual-tenant-admin"}
            else "content-production"
        )
        response = RedirectResponse("/content", status_code=status.HTTP_303_SEE_OTHER)
        set_session_cookie(response, authority, application)
        return response

    @app.get("/ui/select/user", include_in_schema=False)
    def select_user_portal(request: Request) -> RedirectResponse:
        try:
            current_application = authority.application(request)
        except HTTPException:
            current_application = None
        if current_application == "tenant-admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="当前自然人没有租户用户入口资格"
            )
        response = RedirectResponse("/user", status_code=status.HTTP_303_SEE_OTHER)
        set_session_cookie(
            response,
            authority,
            "dual-tenant-user" if current_application == "dual-tenant-admin" else "tenant-user",
        )
        return response

    @app.get("/ui/select/admin", include_in_schema=False)
    def select_tenant_admin(request: Request) -> RedirectResponse:
        try:
            current_application = authority.application(request)
        except HTTPException:
            current_application = None
        if current_application in {
            "tenant-user",
            "content-production",
            "content-production-store",
            "display-merchandising",
            "external-content-production",
        }:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="当前自然人没有租户管理资格"
            )
        response = RedirectResponse("/tenant-admin", status_code=status.HTTP_303_SEE_OTHER)
        set_session_cookie(
            response,
            authority,
            "dual-tenant-admin"
            if current_application in {"dual-tenant-user", "dual-content-production"}
            else "tenant-admin",
        )
        return response

    @app.get("/ui/select/dual-user", include_in_schema=False)
    def select_dual_user_portal() -> RedirectResponse:
        response = RedirectResponse("/user", status_code=status.HTTP_303_SEE_OTHER)
        set_session_cookie(response, authority, "dual-tenant-user")
        return response

    @app.get("/ui/select/dual-admin", include_in_schema=False)
    def select_dual_tenant_admin() -> RedirectResponse:
        response = RedirectResponse("/tenant-admin", status_code=status.HTTP_303_SEE_OTHER)
        set_session_cookie(response, authority, "dual-tenant-admin")
        return response

    @app.get("/ui/select/dual-content", include_in_schema=False)
    def select_dual_content() -> RedirectResponse:
        response = RedirectResponse("/content", status_code=status.HTTP_303_SEE_OTHER)
        set_session_cookie(response, authority, "dual-content-production")
        return response

    @app.get("/ui/select/external-content", include_in_schema=False)
    def select_external_content() -> RedirectResponse:
        response = RedirectResponse("/content", status_code=status.HTTP_303_SEE_OTHER)
        set_session_cookie(response, authority, "external-content-production")
        return response

    @app.get("/ui/select/content-store", include_in_schema=False)
    def select_store_content(request: Request) -> RedirectResponse:
        try:
            current_application = authority.application(request)
        except HTTPException:
            current_application = None
        if current_application in {"tenant-admin", "dual-tenant-admin"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="当前自然人没有该内容账号工作资格"
            )
        response = RedirectResponse("/content", status_code=status.HTTP_303_SEE_OTHER)
        set_session_cookie(response, authority, "content-production-store")
        return response

    @app.get("/ui/select/display", include_in_schema=False)
    def select_display(request: Request) -> RedirectResponse:
        try:
            current_application = authority.application(request)
        except HTTPException:
            current_application = None
        if current_application in {"tenant-admin", "dual-tenant-admin"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="当前自然人没有陈列工作资格"
            )
        response = RedirectResponse("/display", status_code=status.HTTP_303_SEE_OTHER)
        set_session_cookie(response, authority, "display-merchandising")
        return response

    @app.post(
        "/api/v1/display",
        response_model=DisplayVersionResponse
        | DisplayQuestionResponse
        | ApplicationHandoffResponse,
        responses=business_failures,
    )
    def create_display(
        payload: CreateDisplayRequest, scope: DisplayScope = Depends(display_scope_from_request)
    ) -> dict[str, object]:
        if requests_content_production(payload.inventory_text):
            return {"kind": "handoff", "message": "这是面向外部受众的内容任务，请切换到内容生产。"}
        return display_service.create(scope, payload.inventory_text)

    @app.post(
        "/api/v1/display-tasks/{task_id}/revisions",
        status_code=status.HTTP_201_CREATED,
        response_model=DisplayVersionResponse | DisplayQuestionResponse,
        responses=business_failures,
    )
    def revise_display(
        task_id: UUID,
        payload: DisplayRevisionRequest,
        scope: DisplayScope = Depends(display_scope_from_request),
    ) -> dict[str, object]:
        return display_service.revise(scope, task_id, payload.feedback)

    @app.get(
        "/api/v1/display-tasks/{task_id}/versions/{version}",
        response_model=DisplayVersionResponse,
        responses=business_failures,
    )
    def get_display(
        task_id: UUID, version: int, scope: DisplayScope = Depends(display_scope_from_request)
    ) -> dict[str, object]:
        return display_service.fetch_version(scope, task_id, version)

    @app.exception_handler(DomainError)
    async def domain_error_handler(_: Request, exc: DomainError) -> object:
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.get("/assets/diyu-logo-horizontal.svg", include_in_schema=False)
    def logo() -> FileResponse:
        return FileResponse("assets/brand/diyu-vi/svg/diyu-logo-horizontal.svg")

    @app.get(
        "/display",
        response_class=HTMLResponse,
        dependencies=[Security(session_cookie)],
        responses=business_failures,
    )
    def display_workbench(
        request: Request,
        task: UUID | None = None,
        version: int | None = None,
        notice: str | None = None,
    ) -> HTMLResponse:
        scope = authority.require_display(request)
        del task, version, notice
        return HTMLResponse(
            render_spa_shell(
                workbench_service.display_context(scope, current_settings.generator_mode),
                "<p>当前能力：墙面双层挂杆执行方案</p>",
                "<h1>陈列搭配</h1><p>当前工作只处理门店内部执行方案。</p>",
            )
        )

    @app.post(
        "/ui/display/generate",
        status_code=303,
        response_class=RedirectResponse,
        dependencies=[Security(session_cookie)],
    )
    async def ui_display_generate(request: Request) -> RedirectResponse:
        fields = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
        scope = authority.require_display(request)
        inventory_text = fields.get("inventory_text", [""])[0]
        if requests_content_production(inventory_text):
            return RedirectResponse(
                "/display?"
                + urlencode({"notice": "这是面向外部受众的内容任务，请切换到内容生产。"}),
                status_code=303,
            )
        result = display_service.create(scope, inventory_text)
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
            authority.require_display(request),
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
        response_model=ContentVersionResponse
        | GreetingResponse
        | ContentQuestionResponse
        | ApplicationHandoffResponse,
        responses=business_failures,
    )
    def create_content(
        payload: CreateContentRequest,
        request: Request,
        _: TrustedScope = Depends(scope_from_request),
    ) -> dict[str, object]:
        if payload.reuse_version_id is None and requests_display_merchandising(payload.weak_seed):
            return {
                "kind": "handoff",
                "message": "这是给门店内部执行的陈列任务，请切换到陈列搭配。",
            }
        target = _target(payload.target, payload.weak_seed)
        return service.create_from_weak_seed(
            authority.require_content_target(request, target),
            payload.weak_seed,
            payload.reuse_version_id,
            target,
        )

    @app.post(
        "/api/v1/tasks/{task_id}/revisions",
        status_code=status.HTTP_201_CREATED,
        response_model=ContentVersionResponse,
        responses=business_failures,
    )
    def revise_content(
        task_id: UUID,
        payload: RevisionRequest,
        request: Request,
        _: TrustedScope = Depends(scope_from_request),
    ) -> dict[str, object]:
        target = _target(payload.target, payload.instruction)
        source_target = payload.source_target or payload.target or "douyin_video"
        source_scope = authority.require_content_target(request, source_target)
        if target != source_target:
            return service.recompile_task(
                source_scope,
                authority.require_content_target(request, target),
                task_id,
                payload.instruction,
                target,
            )
        return service.revise(source_scope, task_id, payload.instruction, target)

    @app.get(
        "/api/v1/tasks/{task_id}/versions/{version}",
        response_model=ContentVersionResponse,
        responses=business_failures,
    )
    def get_version(
        task_id: UUID,
        version: int,
        request: Request,
        target: ContentTarget = "douyin_video",
        _: TrustedScope = Depends(scope_from_request),
    ) -> dict[str, object]:
        return service.fetch_version(
            authority.require_content_target(request, target), task_id, version
        )

    @app.post(
        "/api/v1/content-versions/{version_id}/save",
        response_model=SavedVersionResponse,
        responses=business_failures,
    )
    def save_version(
        version_id: UUID,
        request: Request,
        target: ContentTarget = "douyin_video",
        _: TrustedScope = Depends(scope_from_request),
    ) -> dict[str, object]:
        return service.save_version(authority.require_content_target(request, target), version_id)

    @app.get("/", response_class=HTMLResponse)
    def workbench(
        request: Request,
        task: UUID | None = None,
        version: int | None = None,
        notice: str | None = None,
    ) -> object:
        if task is not None and version is not None:
            return RedirectResponse(
                "/content?" + urlencode({"task": str(task), "version": str(version)}),
                status_code=status.HTTP_303_SEE_OTHER,
            )
        return HTMLResponse(render_spa_shell())

    @app.get(
        "/user",
        response_class=HTMLResponse,
        dependencies=[Security(session_cookie)],
        responses=business_failures,
    )
    def tenant_user_portal(request: Request) -> HTMLResponse:
        context = workbench_service.user_portal_context(user_scope_from_request(request))
        return HTMLResponse(
            render_spa_shell(
                context,
                fallback=(
                    "<h1>租户用户工作台</h1><p>选择当前要完成的业务工作。</p>"
                    "<p><a href='/ui/select/content'>内容生产（对外）</a> · "
                    "<a href='/ui/select/display'>陈列搭配（对内）</a></p>"
                ),
            )
        )

    @app.get(
        "/tenant-admin",
        response_class=HTMLResponse,
        dependencies=[Security(session_cookie)],
        responses=business_failures,
    )
    def tenant_management_portal(request: Request) -> HTMLResponse:
        context = workbench_service.tenant_management_context(
            management_scope_from_request(request)
        )
        return HTMLResponse(
            render_spa_shell(
                context,
                fallback=(
                    "<h1>租户管理</h1><p>在当前租户范围内维护入驻、发布账号和已登记操作人。</p>"
                ),
            )
        )

    @app.get(
        "/admin",
        response_class=RedirectResponse,
        dependencies=[Security(session_cookie)],
        responses=business_failures,
    )
    def legacy_admin(request: Request) -> RedirectResponse:
        management_scope_from_request(request)
        return RedirectResponse("/tenant-admin", status_code=status.HTTP_303_SEE_OTHER)

    @app.get(
        "/content",
        response_class=HTMLResponse,
        dependencies=[Security(session_cookie)],
        responses=business_failures,
    )
    def content_workbench(
        request: Request,
        task: UUID | None = None,
        version: int | None = None,
        notice: str | None = None,
        target: ContentTarget = "douyin_video",
    ) -> HTMLResponse:
        scope_from_request(request)
        scope = authority.require_content_target(request, target)
        fallback_extra = ""
        if task is not None and version is not None:
            try:
                result = service.fetch_version(scope, task, version)
            except DomainError as exc:
                raise HTTPException(status_code=404, detail="找不到当前会话可见的版本") from exc
            fallback_extra = (
                "<h2>内容概要</h2><p>"
                + escape(str(result["outline"]))
                + "</p><h2>完整文字成品</h2><article>"
                + escape(str(result["body"]))
                + "</article>"
            )
        if current_settings.generator_mode == "stub":
            fallback_extra = (
                "<p>离线确定性测试模式：此页结果不是实际模型调用。</p>" + fallback_extra
            )
        del notice, target
        context = workbench_service.content_context(scope, current_settings.generator_mode)
        context["targets"] = content_targets(scope)
        return HTMLResponse(
            render_spa_shell(
                context,
                fallback_extra,
                fallback=("<h1>内容生产</h1><p>当前工作只使用已授权的发布账号范围。</p>"),
            )
        )

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
        target = _target(fields.get("target", [None])[0], weak_seed)
        try:
            scope = authority.require_content_target(request, target)
            if requests_display_merchandising(weak_seed):
                return RedirectResponse(
                    "/content?"
                    + urlencode({"notice": "这是给门店内部执行的陈列任务，请切换到陈列搭配。"}),
                    status_code=status.HTTP_303_SEE_OTHER,
                )
            result = service.create_from_weak_seed(scope, weak_seed, target=target)
        except DomainError as exc:
            return RedirectResponse(
                "/content?notice=" + str(exc), status_code=status.HTTP_303_SEE_OTHER
            )
        if result["kind"] in {"greeting", "question"}:
            return RedirectResponse(
                "/content?notice=" + str(result["message"]), status_code=status.HTTP_303_SEE_OTHER
            )
        return RedirectResponse(
            workbench_location(result, target=target), status_code=status.HTTP_303_SEE_OTHER
        )

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
            target = _target(fields.get("target", [None])[0], instruction)
            source_target = _target(fields.get("source_target", [None])[0])
            source_scope = authority.require_content_target(request, source_target)
            if target != source_target:
                result = service.recompile_task(
                    source_scope,
                    authority.require_content_target(request, target),
                    task_id,
                    instruction,
                    target,
                )
            else:
                result = service.revise(source_scope, task_id, instruction, target)
        except (DomainError, ValueError) as exc:
            return RedirectResponse(
                "/content?notice=" + str(exc), status_code=status.HTTP_303_SEE_OTHER
            )
        return RedirectResponse(
            workbench_location(result, target=target), status_code=status.HTTP_303_SEE_OTHER
        )

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
            target = _target(fields.get("target", [None])[0], weak_seed)
            result = service.create_from_weak_seed(
                authority.require_content_target(request, target), weak_seed, version_id, target
            )
        except (DomainError, ValueError) as exc:
            return RedirectResponse(
                "/content?notice=" + str(exc), status_code=status.HTTP_303_SEE_OTHER
            )
        if result["kind"] in {"greeting", "question"}:
            return RedirectResponse(
                "/content?notice=" + str(result["message"]), status_code=status.HTTP_303_SEE_OTHER
            )
        return RedirectResponse(
            workbench_location(result, target=target), status_code=status.HTTP_303_SEE_OTHER
        )

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
            target = _target(fields.get("target", [None])[0])
            saved = service.save_version(
                authority.require_content_target(request, target), version_id
            )
        except (DomainError, ValueError) as exc:
            return RedirectResponse(
                "/content?notice=" + str(exc), status_code=status.HTTP_303_SEE_OTHER
            )
        return RedirectResponse(
            workbench_location(
                {"task_id": task_id, "version": version},
                f"已主动保存版本 {saved['version_id']}",
                target,
            ),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return app
