from __future__ import annotations

import base64
import binascii
import json
import logging
import queue
import threading
import time
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from html import escape
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, urlencode, urlsplit
from uuid import UUID

import psycopg
from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Request,
    Security,
    status,
)
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    StreamingResponse,
)
from fastapi.security import APIKeyCookie
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response

from src.brain.content_expression import assert_custom_direction_available
from src.brain.platform_directions import target_from_text
from src.composition.bootstrap import (
    build_content_control_service,
    build_content_service,
    build_display_service,
    build_workbench_service,
)
from src.gateway.api.contracts import (
    AccountExpressionVersionRequest,
    AddSeriesItemRequest,
    ApplicationHandoffResponse,
    BrandExpressionConfirmRequest,
    BrandLibraryEntryRequest,
    BrandLibraryPreviewRequest,
    BrandLibraryVersionRequest,
    ChangePasswordRequest,
    ContentPlanRequest,
    ContentQuestionResponse,
    ContentVersionResponse,
    ControlOrganizationRequest,
    CreateContentRequest,
    CreateConversationRequest,
    CreateDisplayRequest,
    CreatedTenantUserResponse,
    CreateOperatorRequest,
    CreateOrganizationRequest,
    CreatePlatformCarrierRequest,
    CreatePublishingAccountRequest,
    CreateSeriesRequest,
    CreateTenantRequest,
    CreateTenantUserRequest,
    CreationPreferenceRequest,
    CreativeDirectionRequest,
    DefaultPersonaRequest,
    DisplayQuestionResponse,
    DisplayRevisionRequest,
    DisplayVersionResponse,
    GreetingResponse,
    MaterialMetadataVersionRequest,
    MaterialReferenceNoteRequest,
    MaterialUploadRequest,
    OrganizationMaterialUploadRequest,
    ProductImportPreviewRequest,
    ProvisionedTenantResponse,
    ReorderSeriesRequest,
    ResetTenantUserResponse,
    RestoredTenantUserResponse,
    RevisionRequest,
    SaveBrandProductRequest,
    SavedVersionResponse,
    SetEnabledRequest,
    SetExpressionProfileMaintenanceRequest,
    UnmetCapabilityRequest,
    UnmetCapabilityResponseRequest,
    UpdatePublishingAccountRequest,
    UpdatePublishingSpeakerKindRequest,
    UpdateTenantUserGrantsRequest,
    UpdateTenantUserRequest,
)
from src.gateway.api.html import (
    render_activation_failure,
    render_login_failure,
    render_spa_shell,
    render_tenant_admin_access_denied,
    render_tenant_user_access_denied,
    workbench_location,
)
from src.gateway.api.session import (
    ApplicationId,
    ProductionSessionAuthority,
    SessionAuthority,
    clear_production_ops_cookie,
    clear_production_tenant_cookie,
    set_production_ops_cookie,
    set_production_tenant_cookie,
    set_session_cookie,
)
from src.gateway.api.settings import Settings
from src.infrastructure.production_auth import TenantSession
from src.infrastructure.s3_object_store import S3ObjectStore
from src.shared.application_handoff import (
    requests_content_production,
    requests_display_merchandising,
)
from src.shared.errors import DomainError, GenerationFailed
from src.shared.types import (
    ContentTarget,
    ConversationTurn,
    CreativeDirection,
    DirectionSelection,
    DisplayScope,
    RequestedControls,
    TenantManagementScope,
    TrustedScope,
)

_HEADQUARTERS_TARGETS: tuple[tuple[ContentTarget, str], ...] = (
    ("douyin_video", "抖音视频"),
    ("xiaohongshu_video", "小红书视频"),
    ("xiaohongshu_graphic", "小红书图文"),
    ("wechat_channels_video", "微信视频号视频"),
)
_STORE_TARGETS: tuple[tuple[ContentTarget, str], ...] = (("douyin_video", "抖音视频"),)
_RUNTIME_LOGGER = logging.getLogger("diyu.runtime")
# No revision path may re-read today's private preference: a same-goal revision replays the
# conditions the task froze, and a cross-goal adaptation recompiles those same conditions.
_REVISION_MAY_READ_PREFERENCE = False


def _safe_log_path(path: str) -> str:
    return "/activate/:token" if path.startswith("/activate/") else path


def _target(value: str | None, text: str = "") -> ContentTarget:
    del text
    if value in {
        "douyin_video",
        "xiaohongshu_video",
        "xiaohongshu_graphic",
        "wechat_channels_video",
    }:
        return cast(ContentTarget, value)
    return "douyin_video"


def _target_metadata(value: ContentTarget) -> dict[str, str]:
    labels: dict[ContentTarget, tuple[str, str, str]] = {
        "douyin_video": ("抖音视频", "抖音", "视频"),
        "xiaohongshu_graphic": ("小红书图文", "小红书", "图文"),
        "xiaohongshu_video": ("小红书视频", "小红书", "视频"),
        "wechat_channels_video": ("微信视频号视频", "微信视频号", "视频"),
    }
    label, platform_label, format_label = labels[value]
    return {
        "value": value,
        "label": label,
        "platform_label": platform_label,
        "format_label": format_label,
    }


def create_app(settings: Settings | None = None) -> FastAPI:
    current_settings = settings or Settings.model_validate({})
    authority = (
        ProductionSessionAuthority(current_settings)
        if current_settings.is_production
        else SessionAuthority(current_settings)
    )
    synthetic_authority = cast(SessionAuthority, authority)
    service = build_content_service(current_settings)
    display_service = build_display_service(current_settings)
    workbench_service = build_workbench_service(current_settings)
    control_service = build_content_control_service(current_settings)
    app = FastAPI(
        title="笛语双应用 API",
        version="0.1.0",
        description="可信 cookie 会话决定租户、品牌、发布账号和操作人；客户端不能切换这些作用域。",
    )
    app.state.session_authority = authority
    session_cookie = APIKeyCookie(name="diyu_session", auto_error=False)
    app.mount("/app", StaticFiles(directory=Path("frontend/dist"), check_dir=False), name="frontend")
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

    def dependencies_are_ready() -> bool:
        """Check only the two dependencies already used by readiness."""
        if not current_settings.is_production:
            return True
        try:
            with (
                psycopg.connect(current_settings.app_database_url) as connection,
                connection.cursor() as cursor,
            ):
                cursor.execute("SELECT 1")
            assert current_settings.s3_endpoint_url is not None
            assert current_settings.s3_bucket is not None
            assert current_settings.s3_access_key_id is not None
            assert current_settings.s3_secret_access_key is not None
            assert current_settings.s3_region is not None
            return S3ObjectStore(
                current_settings.s3_endpoint_url,
                current_settings.s3_bucket,
                current_settings.s3_access_key_id.get_secret_value(),
                current_settings.s3_secret_access_key.get_secret_value(),
                current_settings.s3_region,
            ).is_ready()
        except (AssertionError, psycopg.Error, RuntimeError, ValueError):
            return False

    def requested_publishing_identity(request: Request) -> UUID | None:
        raw = request.query_params.get("publishing_identity_id")
        if not raw:
            return None
        try:
            return UUID(raw)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="请选择一个当前可用的发布账号",
            ) from exc

    def resolve_content_scope(
        request: Request,
        target: ContentTarget | None = None,
        publishing_identity_id: UUID | None = None,
    ) -> TrustedScope:
        if current_settings.is_production:
            assert production_authority is not None
            identity = production_authority._tenant_identity(request)
            if identity.audience != "tenant-user":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="这个账号不能使用内容创作入口",
                )
            scope = production_authority.repository.content_scope(
                identity,
                target,
                publishing_identity_id,
            )
        else:
            scope = (
                authority.require_content(request)
                if target is None
                else authority.require_content_target(request, target)
            )
        if not workbench_service.is_content_operator(scope):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="你没有使用这个发布账号的资格",
            )
        return scope

    def scope_from_request(request: Request, _: str | None = Security(session_cookie)) -> TrustedScope:
        raw_target = request.query_params.get("target")
        target = _target(raw_target) if raw_target in {item[0] for item in _HEADQUARTERS_TARGETS} else None
        return resolve_content_scope(
            request,
            target,
            requested_publishing_identity(request),
        )

    def user_scope_from_request(request: Request, _: str | None = Security(session_cookie)) -> TrustedScope:
        if current_settings.is_production:
            return resolve_content_scope(
                request,
                None,
                requested_publishing_identity(request),
            )
        return authority.require_user_portal(request)

    def optional_target_scope(
        request: Request,
        target: ContentTarget | None,
        current_scope: TrustedScope,
    ) -> TrustedScope:
        scope = (
            current_scope
            if target is None
            else resolve_content_scope(
                request,
                target,
                requested_publishing_identity(request),
            )
        )
        if not workbench_service.is_content_operator(scope):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="当前自然人没有此发布账号工作资格",
            )
        return scope

    def management_scope_from_request(
        request: Request, _: str | None = Security(session_cookie)
    ) -> TenantManagementScope:
        scope = authority.require_management(request)
        if not workbench_service.is_tenant_manager(scope):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="当前自然人没有租户管理资格",
            )
        return scope

    def display_scope_from_request(request: Request, _: str | None = Security(session_cookie)) -> DisplayScope:
        return authority.require_display(request)

    def content_targets(
        scope: TrustedScope,
        request: Request | None = None,
        identity: TenantSession | None = None,
        publishing_identity_id: UUID | None = None,
    ) -> list[dict[str, str]]:
        if current_settings.is_production:
            if production_authority is None or request is None:
                raise RuntimeError("正式内容目标必须从当前正式会话解析")
            resolved_identity = identity or production_authority._tenant_identity(request)
            allowed = set(
                production_authority.repository.allowed_content_targets(
                    resolved_identity,
                    publishing_identity_id,
                )
            )
            return [_target_metadata(value) for value, _label in _HEADQUARTERS_TARGETS if value in allowed]
        options = (
            _STORE_TARGETS
            if scope.account_id == current_settings.demo_store_content_account_id
            else _HEADQUARTERS_TARGETS
        )
        return [_target_metadata(value) for value, _label in options]

    def publishing_identities(identity: TenantSession) -> list[dict[str, object]]:
        """Project logical identities; physical carriers stay nested platform targets."""
        if production_authority is None:
            return []
        projected: list[dict[str, object]] = []
        for item in production_authority.repository.list_publishing_identities(identity):
            raw_targets = item.get("platform_targets")
            target_values = (
                [str(target.get("value")) for target in raw_targets if isinstance(target, dict) and target.get("value")]
                if isinstance(raw_targets, list)
                else []
            )
            projected_targets = [
                _target_metadata(value) for value, _label in _HEADQUARTERS_TARGETS if value in target_values
            ]
            projected.append(
                {
                    "id": str(item["id"]),
                    "name": str(item["name"]),
                    "profile_summary": str(item.get("profile_summary") or "尚未填写账号画像"),
                    "content_role": str(item.get("content_role") or "发布账号"),
                    "can_maintain_profile": bool(
                        item.get("can_maintain_expression_profile")
                    ),
                    "control_organization": (
                        str(item["control_organization"])
                        if item.get("control_organization") is not None
                        else None
                    ),
                    "profile_id": (
                        str(item["profile_id"])
                        if item.get("profile_id") is not None
                        else None
                    ),
                    "profile_version": item.get("profile_version"),
                    "platform_targets": projected_targets,
                }
            )
        return projected

    production_authority = cast(ProductionSessionAuthority, authority) if current_settings.is_production else None

    @contextmanager
    def model_slot(request: Request) -> Iterator[None]:
        if production_authority is None:
            yield
            return
        identity = production_authority._tenant_identity(request)
        if not production_authority.model_limiter.acquire(identity.tenant_id, identity.user_id):
            production_authority.repository.record_content_rate_limit(identity)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="当前模型请求过于密集或并发已满，请稍后重试",
            )
        try:
            yield
        finally:
            production_authority.model_limiter.release(identity.tenant_id)

    if current_settings.is_production:
        assert production_authority is not None

        @app.middleware("http")
        async def production_csrf_guard(
            request: Request, call_next: Callable[[Request], Awaitable[Response]]
        ) -> Response:
            if request.method not in {"GET", "HEAD", "OPTIONS"}:
                origin = request.headers.get("origin")
                fetch_site = request.headers.get("sec-fetch-site")
                null_origin_is_same_origin = origin == "null" and fetch_site == "same-origin"
                if (
                    origin is not None
                    and not null_origin_is_same_origin
                    and urlsplit(origin).hostname != request.url.hostname
                ):
                    return JSONResponse({"detail": "跨站请求被拒绝"}, status_code=status.HTTP_403_FORBIDDEN)
            started = time.perf_counter()
            try:
                response = await call_next(request)
            except Exception:
                _RUNTIME_LOGGER.info(
                    json.dumps(
                        {
                            "event": "request.completed",
                            "method": request.method,
                            "path": _safe_log_path(request.url.path),
                            "status": 500,
                            "duration_ms": round((time.perf_counter() - started) * 1000),
                        },
                        ensure_ascii=False,
                    )
                )
                raise
            _RUNTIME_LOGGER.info(
                json.dumps(
                    {
                        "event": "request.completed",
                        "method": request.method,
                        "path": _safe_log_path(request.url.path),
                        "status": response.status_code,
                        "duration_ms": round((time.perf_counter() - started) * 1000),
                    },
                    ensure_ascii=False,
                )
            )
            return response

        def tenant_login_response(
            request: Request, username: str, password: str, audience: str, redirect_to: str
        ) -> Response:
            entry_name = "品牌管理登录" if audience == "tenant-admin" else "内容创作登录"
            login_href = "/tenant-admin/login" if audience == "tenant-admin" else "/login"
            if not production_authority.login_limiter.allow(
                f"tenant:{request.client.host if request.client else 'unknown'}:{username.lower()}"
            ):
                return HTMLResponse(
                    render_login_failure(entry_name, login_href, "尝试次数较多，请稍后再试。"),
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                )
            identity = production_authority.repository.authenticate_tenant_user(username, password, audience)
            if identity is None:
                return HTMLResponse(
                    render_login_failure(
                        entry_name,
                        login_href,
                        "用户名、密码或当前入口不匹配，请确认后重新登录。",
                    ),
                    status_code=status.HTTP_401_UNAUTHORIZED,
                )
            response = RedirectResponse(redirect_to, status_code=status.HTTP_303_SEE_OTHER)
            set_production_tenant_cookie(response, production_authority.repository.create_tenant_session(identity))
            return response

        def formal_manager_identity(request: Request) -> TenantSession:
            identity = production_authority._tenant_identity(request)
            if identity.audience != "tenant-admin":
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前正式会话没有租户管理入口资格")
            return identity

        @app.get("/login", include_in_schema=False)
        def tenant_login_page() -> HTMLResponse:
            return HTMLResponse(
                render_spa_shell(
                    {"application": "login", "entry": "tenant-user"},
                    fallback=(
                        "<main><h1>笛语内容创作</h1><form method='post' action='/login'>"
                        "<label>用户名 <input name='username' autocomplete='username' required></label>"
                        "<label>密码 <input type='password' name='password' "
                        "autocomplete='current-password' required></label>"
                        "<button type='submit'>登录</button></form></main>"
                    ),
                )
            )

        @app.post("/login", include_in_schema=False)
        async def tenant_login(request: Request) -> Response:
            fields = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
            return tenant_login_response(
                request, fields.get("username", [""])[0], fields.get("password", [""])[0], "tenant-user", "/user"
            )

        @app.get("/tenant-admin/login", include_in_schema=False)
        def tenant_admin_login_page(request: Request) -> HTMLResponse:
            next_value = "demo" if request.query_params.get("next") == "demo" else ""
            hidden_next = "<input type='hidden' name='next' value='demo'>" if next_value else ""
            return HTMLResponse(
                render_spa_shell(
                    {"application": "login", "entry": "tenant-admin"},
                    fallback=(
                        "<main><h1>笛语品牌管理</h1>"
                        "<form method='post' action='/tenant-admin/login'>"
                        + hidden_next
                        + "<label>用户名 <input name='username' autocomplete='username' "
                        "required></label><label>密码 <input type='password' name='password' "
                        "autocomplete='current-password' required></label>"
                        "<button type='submit'>登录</button></form>"
                        "<p>忘记密码？请联系另一名品牌管理员或笛语运维，"
                        "获取一次性重设密码链接。</p></main>"
                    ),
                )
            )

        @app.post("/tenant-admin/login", include_in_schema=False)
        async def tenant_admin_login(request: Request) -> Response:
            fields = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
            return tenant_login_response(
                request,
                fields.get("username", [""])[0],
                fields.get("password", [""])[0],
                "tenant-admin",
                ("/tenant-admin?section=demo" if fields.get("next", [""])[0] == "demo" else "/tenant-admin"),
            )

        @app.post("/tenant-admin/logout", include_in_schema=False)
        def tenant_admin_logout(request: Request) -> RedirectResponse:
            token = request.cookies.get("diyu_session", "")
            if token:
                production_authority.repository.revoke_tenant_session(token)
            destination = "/login" if request.query_params.get("next") == "user" else "/tenant-admin/login"
            response = RedirectResponse(
                destination,
                status_code=status.HTTP_303_SEE_OTHER,
            )
            clear_production_tenant_cookie(response)
            return response

        @app.get("/ops/login", include_in_schema=False)
        def ops_login_page() -> HTMLResponse:
            return HTMLResponse(
                render_spa_shell(
                    {"application": "login", "entry": "ops"},
                    fallback=(
                        "<main><h1>笛语运维</h1><form method='post' action='/ops/login'>"
                        "<label>用户名 <input name='username' autocomplete='username' "
                        "required></label><label>密码 <input type='password' name='password' "
                        "autocomplete='current-password' required></label>"
                        "<label>身份验证器 6 位码 <input name='totp_code' inputmode='numeric' "
                        "autocomplete='one-time-code' minlength='6' maxlength='6' "
                        "pattern='[0-9]{6}' required>"
                        "<small>来自已绑定的身份验证器。</small></label>"
                        "<button type='submit'>登录</button></form></main>"
                    ),
                )
            )

        @app.post("/ops/login", include_in_schema=False)
        async def ops_login(request: Request) -> Response:
            fields = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
            username = fields.get("username", [""])[0]
            if not production_authority.login_limiter.allow(
                f"ops:{request.client.host if request.client else 'unknown'}:{username.lower()}"
            ):
                return HTMLResponse(
                    render_login_failure("笛语运维登录", "/ops/login", "尝试次数较多，请稍后再试。"),
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                )
            identity = production_authority.repository.authenticate_operator(
                username, fields.get("password", [""])[0], fields.get("totp_code", [""])[0]
            )
            if identity is None:
                return HTMLResponse(
                    render_login_failure(
                        "笛语运维登录",
                        "/ops/login",
                        "用户名、密码、身份验证器 6 位码或当前入口不匹配，请确认后重新登录。",
                    ),
                    status_code=status.HTTP_401_UNAUTHORIZED,
                )
            response = RedirectResponse("/ops", status_code=status.HTTP_303_SEE_OTHER)
            set_production_ops_cookie(response, production_authority.repository.create_operator_session(identity))
            return response

        def render_activation_form(
            activation_token: str,
            activation_purpose: str,
            *,
            error: str | None = None,
            response_status: int = status.HTTP_200_OK,
        ) -> HTMLResponse:
            resetting = activation_purpose == "reset"
            heading = "重新设置密码" if resetting else "设置笛语密码"
            action = "更新密码" if resetting else "完成设置"
            error_markup = (
                "<p role='alert' id='activation-password-error'>" + escape(error) + "</p>"
                if error
                else ""
            )
            return HTMLResponse(
                render_spa_shell(
                    {
                        "application": "activation",
                        "activation_purpose": activation_purpose,
                        "activation_error": error,
                    },
                    fallback=(
                        "<main><h1>"
                        + heading
                        + "</h1>"
                        + error_markup
                        + "<form method='post' action='/activate/"
                        + escape(activation_token)
                        + "'><label>新密码 <input type='password' name='password' "
                        "autocomplete='new-password' minlength='12' required></label>"
                        "<label>再次输入新密码 <input type='password' name='password_confirm' "
                        "autocomplete='new-password' minlength='12' required></label>"
                        "<button type='submit'>"
                        + action
                        + "</button></form></main>"
                    ),
                ),
                status_code=response_status,
            )

        @app.get("/activate/{activation_token}", include_in_schema=False)
        def activation_page(activation_token: str) -> HTMLResponse:
            activation_purpose = (
                production_authority.repository.activation_purpose(activation_token)
                or "activate"
            )
            return render_activation_form(activation_token, activation_purpose)

        @app.post("/activate/{activation_token}", include_in_schema=False)
        async def activate(activation_token: str, request: Request) -> Response:
            if not production_authority.login_limiter.allow(
                f"activation:{request.client.host if request.client else 'unknown'}"
            ):
                return HTMLResponse(
                    render_activation_failure("尝试次数较多，请稍后再试，或请管理员重新生成一次性链接。"),
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                )
            fields = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
            password = fields.get("password", [""])[0]
            password_confirm = fields.get("password_confirm", [""])[0]
            activation_purpose = (
                production_authority.repository.activation_purpose(activation_token)
                or "activate"
            )
            if len(password) < 12:
                return render_activation_form(
                    activation_token,
                    activation_purpose,
                    error="新密码至少需要 12 个字符。",
                    response_status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
            if len(password_confirm) < 12:
                return render_activation_form(
                    activation_token,
                    activation_purpose,
                    error="请再次输入至少 12 个字符的新密码。",
                    response_status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
            if password != password_confirm:
                return render_activation_form(
                    activation_token,
                    activation_purpose,
                    error="两次输入的密码不一致，请重新确认。",
                    response_status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
            try:
                audience = production_authority.repository.complete_activation(activation_token, password)
            except DomainError:
                return HTMLResponse(
                    render_activation_failure("链接可能已使用、已失效或已过期，请管理员重新生成。"),
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
            destination = "/tenant-admin/login" if audience == "tenant-admin" else "/login"
            return RedirectResponse(destination, status_code=status.HTTP_303_SEE_OTHER)

        @app.post("/api/v1/auth/password", responses=business_failures)
        def change_password(payload: ChangePasswordRequest, request: Request) -> dict[str, bool]:
            identity = production_authority._tenant_identity(request)
            if not production_authority.repository.change_password(
                identity, payload.current_password, payload.password
            ):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="当前密码不正确")
            return {"changed": True}

        def activation_paths(raw_token: str) -> tuple[str, str]:
            relative = f"/activate/{raw_token}"
            return relative, f"{current_settings.public_url.rstrip('/')}{relative}"

        def validate_entry_grants(
            entry_type: str | None,
            capabilities: list[str],
            publishing_identity_ids: list[UUID],
            grants_tenant_management: bool,
        ) -> None:
            if entry_type is None:
                return
            if entry_type == "tenant_admin":
                if (
                    not grants_tenant_management
                    or capabilities
                    or publishing_identity_ids
                ):
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="租户管理员只能进入品牌管理，不能同时取得内容、陈列或发布账号资格",
                    )
                return
            if grants_tenant_management:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="租户用户不能同时取得品牌管理入口",
                )
            has_content = "content" in capabilities
            if has_content != bool(publishing_identity_ids):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="内容创作资格必须同时绑定至少一个获准发布账号",
                )

        @app.post(
            "/api/v1/tenant-management/users",
            status_code=status.HTTP_201_CREATED,
            responses=business_failures,
            response_model=CreatedTenantUserResponse,
        )
        def create_tenant_user(
            payload: CreateTenantUserRequest,
            request: Request,
        ) -> CreatedTenantUserResponse:
            identity = formal_manager_identity(request)
            validate_entry_grants(
                payload.entry_type,
                list(payload.capabilities),
                payload.publishing_identity_ids,
                payload.grants_tenant_management,
            )
            try:
                created = production_authority.repository.create_tenant_user(
                    identity,
                    payload.display_name,
                    payload.username,
                    payload.organization_id,
                    payload.account_id,
                    payload.grants_tenant_management,
                    payload.grants_material_maintenance,
                    payload.grants_expression_profile_maintenance,
                    entry_type=payload.entry_type,
                    account_ids=tuple(payload.publishing_identity_ids),
                    maintenance_account_ids=(
                        tuple(
                            payload.expression_profile_maintenance_account_ids
                        )
                        if "expression_profile_maintenance_account_ids"
                        in payload.model_fields_set
                        else None
                    ),
                    grants_content_access="content" in payload.capabilities,
                    grants_display_access="display" in payload.capabilities,
                )
            except psycopg.errors.UniqueViolation as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="当前租户已有同名自然人，或登录用户名已被使用",
                ) from exc
            activation_link, activation_url = activation_paths(created["activation_token"])
            return CreatedTenantUserResponse(
                user_id=created["user_id"],
                username=created["username"],
                activation_link=activation_link,
                activation_url=activation_url,
            )

        @app.get("/api/v1/tenant-management/organizations", responses=business_failures)
        def tenant_organizations(request: Request) -> list[dict[str, object]]:
            return production_authority.repository.tenant_organizations(formal_manager_identity(request))

        @app.post(
            "/api/v1/tenant-management/organizations",
            status_code=status.HTTP_201_CREATED,
            responses=business_failures,
        )
        def create_tenant_organization(
            payload: CreateOrganizationRequest,
            request: Request,
        ) -> dict[str, object]:
            return production_authority.repository.create_tenant_organization(
                formal_manager_identity(request),
                payload.name,
                payload.as_synthetic_business_fixture,
                payload.organization_level,
                payload.parent_organization_id,
            )

        @app.patch(
            "/api/v1/tenant-management/users/{user_id}",
            responses=business_failures,
        )
        def update_tenant_user(
            user_id: UUID,
            payload: UpdateTenantUserRequest,
            request: Request,
        ) -> dict[str, str]:
            return production_authority.repository.update_tenant_user(
                formal_manager_identity(request),
                user_id,
                payload.display_name,
                payload.organization_id,
            )

        @app.post(
            "/api/v1/tenant-management/users/{user_id}/reset",
            responses=business_failures,
            response_model=ResetTenantUserResponse,
        )
        def reset_tenant_user(
            user_id: UUID,
            request: Request,
        ) -> ResetTenantUserResponse:
            identity = formal_manager_identity(request)
            token = production_authority.repository.create_reset_token(identity, user_id)
            reset_link, reset_url = activation_paths(token)
            return ResetTenantUserResponse(reset_link=reset_link, reset_url=reset_url)

        @app.post(
            "/api/v1/tenant-management/users/{user_id}/restore",
            responses=business_failures,
            response_model=RestoredTenantUserResponse,
        )
        def restore_tenant_user(
            user_id: UUID,
            request: Request,
        ) -> RestoredTenantUserResponse:
            restored = production_authority.repository.restore_tenant_user(
                formal_manager_identity(request),
                user_id,
            )
            activation_link, activation_url = activation_paths(
                restored["activation_token"]
            )
            return RestoredTenantUserResponse(
                user_id=restored["user_id"],
                activation_link=activation_link,
                activation_url=activation_url,
            )

        @app.post("/api/v1/tenant-management/users/{user_id}/disable", responses=business_failures)
        def disable_tenant_user(user_id: UUID, request: Request) -> dict[str, bool]:
            identity = formal_manager_identity(request)
            production_authority.repository.disable_tenant_user(identity, user_id)
            return {"disabled": True}

        @app.post(
            "/api/v1/tenant-management/users/{user_id}/publishing-accounts/{account_id}/revoke",
            responses=business_failures,
        )
        def revoke_publishing_account_grant(user_id: UUID, account_id: UUID, request: Request) -> dict[str, bool]:
            identity = formal_manager_identity(request)
            production_authority.repository.revoke_account_grant(identity, user_id, account_id)
            return {"revoked": True}

        @app.patch(
            "/api/v1/tenant-management/users/{user_id}/grants",
            responses=business_failures,
        )
        def update_tenant_user_grants(
            user_id: UUID,
            payload: UpdateTenantUserGrantsRequest,
            request: Request,
        ) -> dict[str, object]:
            validate_entry_grants(
                payload.entry_type,
                list(payload.capabilities),
                payload.publishing_identity_ids,
                payload.grants_tenant_management,
            )
            return production_authority.repository.update_tenant_user_grants(
                formal_manager_identity(request),
                user_id,
                payload.account_id,
                payload.grants_account_access,
                payload.grants_tenant_management,
                payload.grants_material_maintenance,
                payload.grants_expression_profile_maintenance,
                entry_type=payload.entry_type,
                account_ids=tuple(payload.publishing_identity_ids),
                maintenance_account_ids=(
                    tuple(payload.expression_profile_maintenance_account_ids)
                    if payload.expression_profile_maintenance_account_ids
                    is not None
                    else None
                ),
                grants_content_access="content" in payload.capabilities,
                grants_display_access="display" in payload.capabilities,
            )

        @app.put(
            "/api/v1/tenant-management/users/{user_id}/publishing-accounts/"
            "{account_id}/profile-maintenance",
            responses=business_failures,
        )
        def set_expression_profile_maintenance(
            user_id: UUID,
            account_id: UUID,
            payload: SetExpressionProfileMaintenanceRequest,
            request: Request,
        ) -> dict[str, object]:
            return production_authority.repository.set_account_profile_maintenance(
                formal_manager_identity(request),
                user_id,
                account_id,
                payload.enabled,
            )

        @app.post(
            "/api/v1/ops/tenants",
            status_code=status.HTTP_201_CREATED,
            response_model=ProvisionedTenantResponse,
        )
        def provision_tenant(
            payload: CreateTenantRequest,
            request: Request,
        ) -> ProvisionedTenantResponse:
            operator = production_authority.require_ops(request)
            created = production_authority.repository.provision_tenant(
                operator, payload.tenant_name, payload.administrator_name, payload.administrator_username
            )
            activation_link, activation_url = activation_paths(created["activation_token"])
            return ProvisionedTenantResponse(
                tenant_id=created["tenant_id"],
                administrator_id=created["administrator_id"],
                username=created["username"],
                activation_link=activation_link,
                activation_url=activation_url,
            )

        @app.post("/api/v1/ops/tenants/{tenant_id}/disable")
        def disable_tenant(tenant_id: UUID, request: Request) -> dict[str, bool]:
            operator = production_authority.require_ops(request)
            production_authority.repository.set_tenant_enabled(operator, tenant_id, False)
            return {"disabled": True}

        @app.post("/api/v1/ops/tenants/{tenant_id}/enable")
        def enable_tenant(tenant_id: UUID, request: Request) -> dict[str, bool]:
            operator = production_authority.require_ops(request)
            production_authority.repository.set_tenant_enabled(operator, tenant_id, True)
            return {"enabled": True}

        @app.get("/api/v1/ops/tenants")
        def list_ops_tenants(request: Request) -> list[dict[str, object]]:
            operator = production_authority.require_ops(request)
            return production_authority.repository.list_tenants(operator)

        @app.get("/api/v1/ops/runtime-summary")
        def ops_runtime_summary(request: Request) -> dict[str, int | float | None]:
            operator = production_authority.require_ops(request)
            summary = production_authority.repository.runtime_summary(operator)
            summary.update(
                {
                    "model_global_concurrency": current_settings.model_global_concurrency,
                    "model_tenant_concurrency": current_settings.model_tenant_concurrency,
                    "model_tenant_rate_per_minute": current_settings.model_tenant_rate_per_minute,
                }
            )
            return summary

        @app.get("/api/v1/ops/unmet-capability-requests")
        def ops_unmet_capability_requests(request: Request) -> list[dict[str, object]]:
            """The gap candidates users submitted, read through the controlled function only."""
            production_authority.require_ops(request)
            return control_service.ops_unmet_requests()

        @app.post("/api/v1/ops/unmet-capability-requests/{stable_request_id}")
        def classify_unmet_capability_request(
            stable_request_id: str,
            payload: UnmetCapabilityResponseRequest,
            request: Request,
        ) -> dict[str, object]:
            """Classify one candidate and write one plain answer back to the person who asked.

            This is the whole consumption entry: no queue, no approval state machine, and no
            change to the catalog, brand knowledge, an account profile or anybody's preference.
            """
            production_authority.require_ops(request)
            return control_service.ops_classify_unmet_request(
                stable_request_id, payload.gap_type, payload.status, payload.response_text
            )

        @app.get("/ops", include_in_schema=False)
        def ops_dashboard(request: Request) -> Response:
            try:
                operator = production_authority.require_ops(request)
            except HTTPException as exc:
                if exc.status_code == status.HTTP_401_UNAUTHORIZED:
                    return RedirectResponse(
                        "/ops/login",
                        status_code=status.HTTP_303_SEE_OTHER,
                    )
                raise
            summary = production_authority.repository.runtime_summary(operator)
            pending = [item for item in control_service.ops_unmet_requests() if str(item["status"]) != "answered"]
            return HTMLResponse(
                render_spa_shell(
                    {
                        "application": "ops",
                        "identity": {"operator": str(operator.operator_id)},
                        "runtime_summary": summary,
                        "pending_requests": len(pending),
                        "formal_runtime": True,
                    },
                    fallback="<main><h1>笛语运维</h1><p>当前运行汇总。</p></main>",
                )
            )

        @app.post("/ops/unmet-capability-requests", include_in_schema=False)
        async def classify_unmet_capability_request_from_form(request: Request) -> HTMLResponse:
            production_authority.require_ops(request)
            fields = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
            answered = control_service.ops_classify_unmet_request(
                fields.get("stable_request_id", [""])[0],
                fields.get("gap_type", [""])[0],
                fields.get("status", [""])[0],
                fields.get("response_text", [""])[0],
            )
            return HTMLResponse(
                "<main><h1>已记录分类与回告</h1><p>"
                + escape(str(answered["stable_request_id"]))
                + " · "
                + escape(str(answered["status"]))
                + "</p><p><a href='/ops'>返回</a></p></main>"
            )

        @app.post("/ops/logout", include_in_schema=False)
        def ops_logout(request: Request) -> RedirectResponse:
            token = request.cookies.get("diyu_ops_session", "")
            if token:
                production_authority.repository.revoke_operator_session(token)
            response = RedirectResponse(
                "/ops/login",
                status_code=status.HTTP_303_SEE_OTHER,
            )
            clear_production_ops_cookie(response)
            return response

        @app.post("/ops/tenants", include_in_schema=False)
        async def provision_tenant_from_form(request: Request) -> HTMLResponse:
            operator = production_authority.require_ops(request)
            fields = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
            created = production_authority.repository.provision_tenant(
                operator,
                fields.get("tenant_name", [""])[0],
                fields.get("administrator_name", [""])[0],
                fields.get("administrator_username", [""])[0],
            )
            _, activation_url = activation_paths(created["activation_token"])
            return HTMLResponse(
                "<main><h1>租户壳已创建</h1><p>用户名："
                + escape(created["username"])
                + "</p><p>一次性激活链接：<a href='"
                + escape(activation_url)
                + "'>"
                + escape(activation_url)
                + "</a></p></main>",
                status_code=status.HTTP_201_CREATED,
            )

        @app.get("/health/live", include_in_schema=False)
        def health_live() -> dict[str, str]:
            return {"status": "live"}

        @app.get("/health/ready", include_in_schema=False)
        def health_ready() -> dict[str, str]:
            if not dependencies_are_ready():
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="服务暂不可用",
                )
            return {"status": "ready"}

    @app.get("/status", response_class=HTMLResponse, include_in_schema=False)
    def public_status() -> HTMLResponse:
        service_state = "available" if dependencies_are_ready() else "unavailable"
        return HTMLResponse(
            render_spa_shell(
                {
                    "application": "status",
                    "service_state": service_state,
                },
                fallback=(
                    "<main><h1>服务状态</h1><p>"
                    + ("笛语当前可以使用。" if service_state == "available" else "笛语暂时不可用，请稍后再试。")
                    + "</p></main>"
                ),
            )
        )

    @app.get("/api/v1/session/context", responses=business_failures)
    def session_context(request: Request) -> dict[str, object]:
        application = authority.application(request)
        if application in {"tenant-admin", "dual-tenant-admin"}:
            return workbench_service.tenant_management_context(management_scope_from_request(request))
        if application in {"tenant-user", "dual-tenant-user"}:
            if production_authority is not None:
                identity = production_authority._tenant_identity(request)
                identities = publishing_identities(identity)
                capabilities: list[str] = []
                identity_projection: dict[str, object] = {}
                if identities:
                    first_identity_id = UUID(str(identities[0]["id"]))
                    identity_scope = production_authority.repository.content_scope(
                        identity,
                        None,
                        first_identity_id,
                    )
                    raw_projection = workbench_service.user_portal_context(
                        identity_scope
                    ).get("identity")
                    if isinstance(raw_projection, dict):
                        identity_projection = raw_projection
                    capabilities.append("content")
                try:
                    production_authority.repository.display_scope(identity)
                except DomainError:
                    pass
                else:
                    capabilities.append("display")
                return {
                    "application": "tenant_user",
                    "identity": identity_projection,
                    "publishing_identities": identities,
                    "capabilities": capabilities,
                    "formal_runtime": True,
                }
            return workbench_service.user_portal_context(user_scope_from_request(request))
        if application == "display-merchandising":
            return workbench_service.display_context(
                authority.require_display(request), current_settings.generator_mode
            )
        scope = scope_from_request(request)
        context = workbench_service.content_context(scope, current_settings.generator_mode)
        context["targets"] = content_targets(scope, request)
        return context

    @app.get("/api/v1/content/publishing-identities", responses=business_failures)
    def list_content_publishing_identities(
        request: Request,
    ) -> list[dict[str, object]]:
        if production_authority is not None:
            identity = production_authority._tenant_identity(request)
            if identity.audience != "tenant-user":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="这个账号不能使用内容创作入口",
                )
            return publishing_identities(identity)
        scope = authority.require_content(request)
        return [
            {
                "id": str(scope.account_id),
                "name": "当前发布账号",
                "profile_summary": "沿用当前账号画像",
                "content_role": "当前表达身份",
                "platform_targets": content_targets(scope, request),
            }
        ]

    @app.get("/api/v1/content/tasks", responses=business_failures)
    def list_content_tasks(
        request: Request,
        target: ContentTarget | None = None,
        current_scope: TrustedScope = Depends(scope_from_request),
    ) -> list[dict[str, object]]:
        scope = optional_target_scope(request, target, current_scope)
        return workbench_service.recent_content(scope)

    @app.get("/api/v1/content/tasks/{task_id}/versions", responses=business_failures)
    def list_content_versions(
        task_id: UUID,
        request: Request,
        target: ContentTarget | None = None,
        current_scope: TrustedScope = Depends(scope_from_request),
    ) -> list[dict[str, object]]:
        scope = optional_target_scope(request, target, current_scope)
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
        scope: TenantManagementScope = Depends(management_scope_from_request),
    ) -> dict[str, object]:
        return workbench_service.readiness(scope)

    @app.get("/api/v1/admin/brand-expression", responses=business_failures)
    def brand_expression(
        scope: TenantManagementScope = Depends(management_scope_from_request),
    ) -> dict[str, object]:
        return workbench_service.brand_expression(scope)

    @app.post("/api/v1/admin/brand-expression/confirm", responses=business_failures)
    def confirm_brand_expression(
        payload: BrandExpressionConfirmRequest,
        scope: TenantManagementScope = Depends(management_scope_from_request),
    ) -> dict[str, object]:
        return workbench_service.confirm_brand_expression(scope, payload.draft)

    @app.get("/api/v1/tenant-management/operators", responses=business_failures)
    def management_operators(
        scope: TenantManagementScope = Depends(management_scope_from_request),
    ) -> list[dict[str, object]]:
        return workbench_service.management_operators(scope)

    @app.get("/api/v1/tenant-management/publishing-accounts", responses=business_failures)
    def management_accounts(
        scope: TenantManagementScope = Depends(management_scope_from_request),
    ) -> list[dict[str, object]]:
        return workbench_service.management_accounts(scope)

    @app.get("/api/v1/tenant-management/team-usage", responses=business_failures)
    def management_team_usage(
        window_days: int = 7,
        scope: TenantManagementScope = Depends(management_scope_from_request),
    ) -> dict[str, object]:
        result = workbench_service.team_usage(scope, window_days)
        result["tenant_quota"] = {
            "model_concurrency": current_settings.model_tenant_concurrency,
            "model_requests_per_minute": current_settings.model_tenant_rate_per_minute,
            "label": "当前租户请求额度",
        }
        return result

    @app.get("/api/v1/tenant-management/brand-library", responses=business_failures)
    def management_brand_library(
        scope: TenantManagementScope = Depends(management_scope_from_request),
    ) -> list[dict[str, object]]:
        return workbench_service.brand_library_entries(scope)

    @app.post(
        "/api/v1/tenant-management/brand-library",
        status_code=status.HTTP_201_CREATED,
        responses=business_failures,
    )
    def create_management_brand_library_entry(
        payload: BrandLibraryEntryRequest,
        scope: TenantManagementScope = Depends(management_scope_from_request),
    ) -> dict[str, object]:
        return workbench_service.create_brand_library_entry(
            scope,
            payload.category,
            payload.title,
            payload.source_note,
            payload.content,
            payload.version,
            payload.status,
            payload.visibility_scope,
            tuple(payload.organization_ids),
        )

    @app.post(
        "/api/v1/tenant-management/brand-library/preview",
        responses=business_failures,
    )
    def preview_management_brand_library_entry(
        payload: BrandLibraryPreviewRequest,
        _: TenantManagementScope = Depends(management_scope_from_request),
    ) -> dict[str, object]:
        return workbench_service.preview_brand_library_entry(
            payload.category,
            payload.title,
            payload.source_note,
            payload.content,
            payload.version,
            payload.visibility_scope,
            tuple(payload.organization_ids),
        )

    @app.get(
        "/api/v1/tenant-management/brand-library/{entry_id}/versions",
        responses=business_failures,
    )
    def management_brand_library_versions(
        entry_id: UUID,
        scope: TenantManagementScope = Depends(management_scope_from_request),
    ) -> list[dict[str, object]]:
        return workbench_service.brand_library_entry_versions(scope, entry_id)

    @app.post(
        "/api/v1/tenant-management/brand-library/{entry_id}/versions",
        responses=business_failures,
    )
    def save_management_brand_library_version(
        entry_id: UUID,
        payload: BrandLibraryVersionRequest,
        scope: TenantManagementScope = Depends(management_scope_from_request),
    ) -> dict[str, object]:
        return workbench_service.save_brand_library_entry_version(
            scope,
            entry_id,
            payload.title,
            payload.source_note,
            payload.content,
            payload.version,
            payload.visibility_scope,
            tuple(payload.organization_ids),
        )

    @app.put(
        "/api/v1/tenant-management/brand-library/{entry_id}/enabled",
        responses=business_failures,
    )
    def set_management_brand_library_enabled(
        entry_id: UUID,
        payload: SetEnabledRequest,
        scope: TenantManagementScope = Depends(management_scope_from_request),
    ) -> dict[str, object]:
        return workbench_service.set_brand_library_entry_enabled(
            scope,
            entry_id,
            payload.enabled,
        )

    @app.get("/api/v1/tenant-management/brand-products", responses=business_failures)
    def management_products(
        scope: TenantManagementScope = Depends(management_scope_from_request),
    ) -> list[dict[str, object]]:
        return workbench_service.management_products(scope)

    @app.get(
        "/api/v1/tenant-management/organization-materials",
        responses=business_failures,
    )
    def management_organization_materials(
        scope: TenantManagementScope = Depends(management_scope_from_request),
    ) -> list[dict[str, object]]:
        return workbench_service.management_organization_materials(scope)

    @app.post(
        "/api/v1/tenant-management/organization-materials",
        status_code=status.HTTP_201_CREATED,
        responses=business_failures,
    )
    def create_management_organization_material(
        upload: OrganizationMaterialUploadRequest,
        scope: TenantManagementScope = Depends(management_scope_from_request),
    ) -> dict[str, object]:
        try:
            payload = base64.b64decode(upload.content_base64, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="素材原件编码无效",
            ) from exc
        return workbench_service.add_management_organization_material(
            scope,
            upload.organization_id,
            upload.title,
            upload.filename,
            upload.content_type,
            payload,
            upload.declares_identifiable_minor,
            upload.reference_note,
            upload.visibility_scope,
            tuple(upload.organization_ids),
        )

    @app.get(
        "/api/v1/tenant-management/organization-materials/{asset_id}/versions",
        responses=business_failures,
    )
    def management_organization_material_versions(
        asset_id: UUID,
        scope: TenantManagementScope = Depends(management_scope_from_request),
    ) -> list[dict[str, object]]:
        return workbench_service.management_material_versions(scope, asset_id)

    @app.post(
        "/api/v1/tenant-management/organization-materials/{asset_id}/versions",
        responses=business_failures,
    )
    def save_management_organization_material_version(
        asset_id: UUID,
        payload: MaterialMetadataVersionRequest,
        scope: TenantManagementScope = Depends(management_scope_from_request),
    ) -> dict[str, object]:
        return workbench_service.save_management_material_version(
            scope,
            asset_id,
            payload.title,
            payload.reference_note,
            payload.visibility_scope,
            tuple(payload.organization_ids),
        )

    @app.put(
        "/api/v1/tenant-management/organization-materials/{asset_id}/enabled",
        responses=business_failures,
    )
    def set_management_organization_material_enabled(
        asset_id: UUID,
        payload: SetEnabledRequest,
        scope: TenantManagementScope = Depends(management_scope_from_request),
    ) -> dict[str, object]:
        return workbench_service.set_management_material_enabled(
            scope,
            asset_id,
            payload.enabled,
        )

    @app.delete(
        "/api/v1/tenant-management/organization-materials/{asset_id}",
        responses=business_failures,
    )
    def delete_management_organization_material(
        asset_id: UUID,
        scope: TenantManagementScope = Depends(management_scope_from_request),
    ) -> dict[str, bool]:
        workbench_service.delete_management_organization_material(scope, asset_id)
        return {"deleted": True}

    @app.get(
        "/api/v1/tenant-management/demo-content-index",
        responses=business_failures,
    )
    def management_demo_content_index(
        scope: TenantManagementScope = Depends(management_scope_from_request),
    ) -> dict[str, object]:
        return workbench_service.management_demo_content_index(scope)

    @app.get("/api/v1/tenant-management/onboarding-prefill", responses=business_failures)
    def management_onboarding_prefill(
        scope: TenantManagementScope = Depends(management_scope_from_request),
    ) -> dict[str, object]:
        return workbench_service.management_onboarding_prefill(scope)

    @app.put("/api/v1/tenant-management/brand-products", responses=business_failures)
    def save_management_product(
        payload: SaveBrandProductRequest,
        scope: TenantManagementScope = Depends(management_scope_from_request),
    ) -> dict[str, object]:
        return workbench_service.save_management_product(
            scope,
            payload.sku,
            payload.display_name,
            payload.category,
            tuple(payload.colors),
            payload.material_or_structure,
            payload.silhouette,
            payload.observable_features,
            payload.source_note,
            payload.applicability,
            payload.confirm_as_current_brand_fact,
            payload.as_synthetic_business_fixture,
            payload.visibility_scope,
            tuple(payload.organization_ids),
        )

    @app.post(
        "/api/v1/tenant-management/brand-products/preview",
        responses=business_failures,
    )
    def preview_management_products(
        payload: ProductImportPreviewRequest,
        _: TenantManagementScope = Depends(management_scope_from_request),
    ) -> dict[str, object]:
        return workbench_service.preview_product_import(
            payload.source_format,
            payload.content,
        )

    @app.get(
        "/api/v1/tenant-management/brand-products/{sku}/versions",
        responses=business_failures,
    )
    def management_product_versions(
        sku: str,
        scope: TenantManagementScope = Depends(management_scope_from_request),
    ) -> list[dict[str, object]]:
        return workbench_service.management_product_versions(scope, sku)

    @app.put(
        "/api/v1/tenant-management/brand-products/{sku}/enabled",
        responses=business_failures,
    )
    def set_management_product_enabled(
        sku: str,
        payload: SetEnabledRequest,
        scope: TenantManagementScope = Depends(management_scope_from_request),
    ) -> dict[str, object]:
        return workbench_service.set_management_product_enabled(
            scope,
            sku,
            payload.enabled,
        )

    @app.post(
        "/api/v1/tenant-management/publishing-accounts",
        status_code=status.HTTP_201_CREATED,
        responses=business_failures,
    )
    def create_publishing_account(
        payload: CreatePublishingAccountRequest,
        scope: TenantManagementScope = Depends(management_scope_from_request),
    ) -> dict[str, object]:
        return workbench_service.create_publishing_account(
            scope,
            payload.name,
            payload.channel,
            payload.content_role_name,
            payload.voice_boundary,
            payload.operator_id,
            payload.control_organization_id,
            payload.operator_can_maintain_expression_profile,
            payload.as_synthetic_business_fixture,
            (
                payload.initial_profile.model_dump()
                if payload.initial_profile is not None
                else None
            ),
            payload.speaker_kind,
        )

    @app.patch(
        "/api/v1/tenant-management/publishing-accounts/{account_id}",
        responses=business_failures,
    )
    def update_publishing_account(
        account_id: UUID,
        payload: UpdatePublishingAccountRequest,
        scope: TenantManagementScope = Depends(management_scope_from_request),
    ) -> dict[str, object]:
        return workbench_service.update_publishing_account(
            scope,
            account_id,
            payload.name,
            payload.control_organization_id,
        )

    @app.put(
        "/api/v1/tenant-management/publishing-accounts/{account_id}/enabled",
        responses=business_failures,
    )
    def set_publishing_account_enabled(
        account_id: UUID,
        payload: SetEnabledRequest,
        scope: TenantManagementScope = Depends(management_scope_from_request),
    ) -> dict[str, object]:
        return workbench_service.set_publishing_account_enabled(
            scope,
            account_id,
            payload.enabled,
        )

    @app.patch(
        "/api/v1/tenant-management/publishing-accounts/{account_id}/speaker-kind",
        responses=business_failures,
    )
    def update_publishing_speaker_kind(
        account_id: UUID,
        payload: UpdatePublishingSpeakerKindRequest,
        scope: TenantManagementScope = Depends(management_scope_from_request),
    ) -> dict[str, object]:
        return workbench_service.update_publishing_speaker_kind(
            scope,
            account_id,
            payload.speaker_kind,
        )

    @app.post(
        "/api/v1/tenant-management/platform-carriers",
        status_code=status.HTTP_201_CREATED,
        responses=business_failures,
    )
    def create_platform_carrier(
        payload: CreatePlatformCarrierRequest,
        scope: TenantManagementScope = Depends(management_scope_from_request),
    ) -> dict[str, object]:
        return workbench_service.create_platform_carrier(
            scope,
            payload.source_account_id,
            payload.name,
            payload.channel,
            payload.operator_id,
            payload.confirm_internal_carrier,
        )

    @app.put(
        "/api/v1/tenant-management/platform-carriers/{account_id}/enabled",
        responses=business_failures,
    )
    def set_platform_carrier_enabled(
        account_id: UUID,
        payload: SetEnabledRequest,
        scope: TenantManagementScope = Depends(management_scope_from_request),
    ) -> dict[str, object]:
        return workbench_service.set_platform_carrier_enabled(
            scope,
            account_id,
            payload.enabled,
        )

    @app.post(
        "/api/v1/tenant-management/operators",
        status_code=status.HTTP_201_CREATED,
        responses=business_failures,
    )
    def create_operator(
        payload: CreateOperatorRequest,
        scope: TenantManagementScope = Depends(management_scope_from_request),
    ) -> dict[str, object]:
        if current_settings.is_production:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="正式环境只允许通过自然人登录身份与一次性激活链接创建操作者",
            )
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
    def list_series(
        request: Request,
        target: ContentTarget | None = None,
        current_scope: TrustedScope = Depends(scope_from_request),
    ) -> list[dict[str, object]]:
        return workbench_service.list_series(optional_target_scope(request, target, current_scope))

    @app.post("/api/v1/content/series", status_code=status.HTTP_201_CREATED, responses=business_failures)
    def create_series(
        payload: CreateSeriesRequest,
        request: Request,
        target: ContentTarget | None = None,
        current_scope: TrustedScope = Depends(scope_from_request),
    ) -> dict[str, object]:
        return workbench_service.create_series(
            optional_target_scope(request, target, current_scope),
            payload.title,
            payload.premise,
        )

    @app.post("/api/v1/content/series/{series_id}/items", responses=business_failures)
    def add_series_item(
        series_id: UUID,
        payload: AddSeriesItemRequest,
        request: Request,
        target: ContentTarget | None = None,
        current_scope: TrustedScope = Depends(scope_from_request),
    ) -> dict[str, object]:
        return workbench_service.add_series_item(
            optional_target_scope(request, target, current_scope),
            series_id,
            payload.task_id,
            payload.position,
        )

    @app.put("/api/v1/content/series/{series_id}/items", responses=business_failures)
    def reorder_series(
        series_id: UUID,
        payload: ReorderSeriesRequest,
        request: Request,
        target: ContentTarget | None = None,
        current_scope: TrustedScope = Depends(scope_from_request),
    ) -> dict[str, object]:
        return workbench_service.reorder_series(
            optional_target_scope(request, target, current_scope),
            series_id,
            tuple(payload.task_ids),
        )

    @app.post("/api/v1/content/series/{series_id}/reset", responses=business_failures)
    def reset_series(
        series_id: UUID,
        request: Request,
        target: ContentTarget | None = None,
        current_scope: TrustedScope = Depends(scope_from_request),
    ) -> dict[str, object]:
        return workbench_service.reset_series(
            optional_target_scope(request, target, current_scope),
            series_id,
        )

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
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="素材原件编码无效") from exc
        return workbench_service.add_material(
            scope,
            asset_scope,
            upload.title,
            upload.filename,
            upload.content_type,
            payload,
            upload.declares_identifiable_minor,
            upload.reference_note,
        )

    @app.delete("/api/v1/materials/{asset_id}", responses=business_failures)
    def delete_material(asset_id: UUID, scope: TrustedScope = Depends(scope_from_request)) -> dict[str, bool]:
        workbench_service.delete_material(scope, asset_id)
        return {"deleted": True}

    @app.get("/ui/select/content", include_in_schema=False)
    def select_content(request: Request) -> RedirectResponse:
        if current_settings.is_production:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        try:
            current_application = authority.application(request)
        except HTTPException:
            current_application = None
        if current_application in {"tenant-admin", "dual-tenant-admin"}:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前自然人没有业务工作资格")
        application: ApplicationId = (
            "dual-content-production"
            if current_application in {"dual-tenant-user", "dual-tenant-admin"}
            else "content-production"
        )
        response = RedirectResponse("/content", status_code=status.HTTP_303_SEE_OTHER)
        set_session_cookie(response, synthetic_authority, application)
        return response

    @app.get("/ui/select/user", include_in_schema=False)
    def select_user_portal(request: Request) -> RedirectResponse:
        if current_settings.is_production:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        try:
            current_application = authority.application(request)
        except HTTPException:
            current_application = None
        if current_application in {"tenant-admin", "dual-tenant-admin"}:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前自然人没有租户用户入口资格")
        response = RedirectResponse("/user", status_code=status.HTTP_303_SEE_OTHER)
        set_session_cookie(
            response,
            synthetic_authority,
            "dual-tenant-user" if current_application == "dual-tenant-admin" else "tenant-user",
        )
        return response

    @app.get("/ui/select/admin", include_in_schema=False)
    def select_tenant_admin(request: Request) -> RedirectResponse:
        if current_settings.is_production:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
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
            "dual-tenant-user",
            "dual-content-production",
        }:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前自然人没有租户管理资格")
        response = RedirectResponse("/tenant-admin", status_code=status.HTTP_303_SEE_OTHER)
        set_session_cookie(
            response,
            synthetic_authority,
            "dual-tenant-admin"
            if current_application in {"dual-tenant-user", "dual-content-production"}
            else "tenant-admin",
        )
        return response

    @app.get("/ui/select/dual-user", include_in_schema=False)
    def select_dual_user_portal() -> RedirectResponse:
        if current_settings.is_production:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="租户管理员不能进入租户用户入口")

    @app.get("/ui/select/dual-admin", include_in_schema=False)
    def select_dual_tenant_admin() -> RedirectResponse:
        if current_settings.is_production:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        response = RedirectResponse("/tenant-admin", status_code=status.HTTP_303_SEE_OTHER)
        set_session_cookie(response, synthetic_authority, "dual-tenant-admin")
        return response

    @app.get("/ui/select/dual-content", include_in_schema=False)
    def select_dual_content() -> RedirectResponse:
        if current_settings.is_production:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="租户管理员不能进入内容创作入口")

    @app.get("/ui/select/external-content", include_in_schema=False)
    def select_external_content() -> RedirectResponse:
        if current_settings.is_production:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        response = RedirectResponse("/content", status_code=status.HTTP_303_SEE_OTHER)
        set_session_cookie(response, synthetic_authority, "external-content-production")
        return response

    @app.get("/ui/select/content-store", include_in_schema=False)
    def select_store_content(request: Request) -> RedirectResponse:
        if current_settings.is_production:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        try:
            current_application = authority.application(request)
        except HTTPException:
            current_application = None
        if current_application in {"tenant-admin", "dual-tenant-admin"}:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前自然人没有该内容账号工作资格")
        response = RedirectResponse("/content", status_code=status.HTTP_303_SEE_OTHER)
        set_session_cookie(response, synthetic_authority, "content-production-store")
        return response

    @app.get("/ui/select/display", include_in_schema=False)
    def select_display(request: Request) -> RedirectResponse:
        if current_settings.is_production:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        try:
            current_application = authority.application(request)
        except HTTPException:
            current_application = None
        if current_application in {"tenant-admin", "dual-tenant-admin"}:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前自然人没有陈列工作资格")
        response = RedirectResponse("/display", status_code=status.HTTP_303_SEE_OTHER)
        set_session_cookie(response, synthetic_authority, "display-merchandising")
        return response

    @app.post(
        "/api/v1/display",
        response_model=DisplayVersionResponse | DisplayQuestionResponse | ApplicationHandoffResponse,
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

    @app.get("/assets/diyu-logo-horizontal-ondark.svg", include_in_schema=False)
    def logo_on_dark() -> FileResponse:
        return FileResponse("assets/brand/diyu-vi/svg/diyu-logo-horizontal-ondark.svg")

    @app.get("/assets/diyu-logo-primary.svg", include_in_schema=False)
    def primary_logo() -> FileResponse:
        return FileResponse("assets/brand/diyu-vi/svg/diyu-logo-primary.svg")

    @app.get("/assets/diyu-symbol.svg", include_in_schema=False)
    def symbol() -> FileResponse:
        return FileResponse("assets/brand/diyu-vi/svg/diyu-symbol.svg")

    @app.get("/assets/diyu-symbol-ondark.svg", include_in_schema=False)
    def symbol_on_dark() -> FileResponse:
        return FileResponse("assets/brand/diyu-vi/svg/diyu-symbol-ondark.svg")

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> FileResponse:
        return FileResponse("assets/brand/diyu-vi/favicon/favicon.ico")

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
    ) -> Response:
        if production_authority is not None:
            try:
                identity = production_authority._tenant_identity(request)
            except HTTPException as exc:
                if exc.status_code == status.HTTP_401_UNAUTHORIZED:
                    return RedirectResponse(
                        "/login",
                        status_code=status.HTTP_303_SEE_OTHER,
                    )
                raise
            if identity.audience != "tenant-user":
                return HTMLResponse(
                    render_tenant_user_access_denied(
                        "陈列搭配入口",
                        "/tenant-admin",
                        "返回租户管理入口",
                    ),
                    status_code=status.HTTP_403_FORBIDDEN,
                )
            try:
                scope = production_authority.repository.display_scope(identity)
            except DomainError:
                return HTMLResponse(
                    render_tenant_user_access_denied(
                        "陈列搭配入口",
                        "/user",
                        "返回租户用户入口",
                    ),
                    status_code=status.HTTP_403_FORBIDDEN,
                )
        else:
            scope = authority.require_display(request)
        del task, version, notice
        context = workbench_service.display_context(scope, current_settings.generator_mode)
        if current_settings.is_production:
            context["formal_runtime"] = True
        return HTMLResponse(
            render_spa_shell(
                context,
                "<p>当前能力：墙面双层挂杆参考执行方案</p>",
                "<h1>陈列搭配</h1><p>当前工作只给出门店内部参考建议。</p>",
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
                "/display?" + urlencode({"notice": "这是面向外部受众的内容任务，请切换到内容生产。"}),
                status_code=303,
            )
        result = display_service.create(scope, inventory_text)
        if result["kind"] == "question":
            return RedirectResponse("/display?" + urlencode({"notice": str(result["message"])}), status_code=303)
        return RedirectResponse(f"/display?task={result['task_id']}&version={result['version']}", status_code=303)

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
            return RedirectResponse("/display?" + urlencode({"notice": str(result["message"])}), status_code=303)
        return RedirectResponse(f"/display?task={result['task_id']}&version={result['version']}", status_code=303)

    def _controls(
        payload: CreateContentRequest | CreateConversationRequest,
        bypassed: bool,
    ) -> RequestedControls:
        """Client control input stays untrusted data; it can never carry a scope."""
        direction = payload.creative_direction
        return RequestedControls(
            catalog_version=direction.catalog_version if direction else None,
            selections=tuple(direction.selections.items()) if direction else (),
            cleared_axes=tuple(direction.cleared_axes) if direction else (),
            custom_text=direction.custom_text if direction else "",
            body_related_opt_in=bool(direction and direction.body_related_opt_in),
            use_personal_preferences=payload.use_personal_preferences and not bypassed,
            material_ids=tuple(payload.material_ids),
        )

    def preference_session_bypassed(request: Request) -> bool:
        """A temporary preference-free session declares itself on every request it makes.

        While it is on, the catalog, the opportunities, generation and revision neither read nor
        write the acting person's private preference, and the preference entry itself is closed
        rather than quietly reachable.
        """
        return request.headers.get("x-diyu-preference-session", "").strip().lower() == "bypass"

    def _refuse_in_bypass(bypassed: bool) -> None:
        if bypassed:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="你正在临时无偏好会话中，这里不读取也不写入你的私人偏好。退出后可以继续查看和修改。",
            )

    @app.get("/api/v1/content/expression-catalog", responses=business_failures)
    def expression_catalog(
        scope: TrustedScope = Depends(scope_from_request),
        bypassed: bool = Depends(preference_session_bypassed),
    ) -> dict[str, object]:
        return control_service.catalog_view(scope, read_preference=not bypassed)

    @app.get("/api/v1/content/account-expression-profile", responses=business_failures)
    def account_expression_profile(
        request: Request,
        target: ContentTarget | None = None,
        current_scope: TrustedScope = Depends(scope_from_request),
    ) -> dict[str, object]:
        return control_service.account_expression(optional_target_scope(request, target, current_scope))

    @app.post(
        "/api/v1/content/account-expression-profile/versions",
        status_code=status.HTTP_201_CREATED,
        responses=business_failures,
    )
    def save_account_expression_profile(
        payload: AccountExpressionVersionRequest,
        request: Request,
        target: ContentTarget | None = None,
        current_scope: TrustedScope = Depends(scope_from_request),
    ) -> dict[str, object]:
        return control_service.save_account_expression(
            optional_target_scope(request, target, current_scope),
            payload.model_dump(),
        )

    @app.get(
        "/api/v1/tenant-management/publishing-accounts/{account_id}/expression-profile",
        responses=business_failures,
    )
    def management_account_expression_profile(
        account_id: UUID,
        scope: TenantManagementScope = Depends(management_scope_from_request),
    ) -> dict[str, object]:
        return control_service.management_account_expression(scope, account_id)

    @app.post(
        "/api/v1/tenant-management/publishing-accounts/{account_id}/expression-profile/versions",
        status_code=status.HTTP_201_CREATED,
        responses=business_failures,
    )
    def save_management_account_expression_profile(
        account_id: UUID,
        payload: AccountExpressionVersionRequest,
        scope: TenantManagementScope = Depends(management_scope_from_request),
    ) -> dict[str, object]:
        return control_service.save_management_account_expression(scope, account_id, payload.model_dump())

    @app.get(
        "/api/v1/tenant-management/publishing-accounts/{account_id}/expression-profile/versions",
        responses=business_failures,
    )
    def management_account_expression_versions(
        account_id: UUID,
        scope: TenantManagementScope = Depends(management_scope_from_request),
    ) -> list[dict[str, object]]:
        return control_service.management_account_expression_versions(
            scope,
            account_id,
        )

    @app.get("/api/v1/tenant-management/control-organizations", responses=business_failures)
    def control_organizations(
        scope: TenantManagementScope = Depends(management_scope_from_request),
    ) -> list[dict[str, object]]:
        return control_service.management_organizations(scope)

    @app.post(
        "/api/v1/tenant-management/publishing-accounts/{account_id}/control-organization",
        responses=business_failures,
    )
    def declare_control_organization(
        account_id: UUID,
        payload: ControlOrganizationRequest,
        scope: TenantManagementScope = Depends(management_scope_from_request),
    ) -> dict[str, object]:
        """Declare, once, which organization controls this account.

        A value a migration inferred from a creation event is not evidence and grants nothing;
        this is the explicit decision that makes profile maintenance possible.
        """
        return control_service.declare_control_organization(scope, account_id, payload.organization_id)

    @app.get("/api/v1/user/creation-preferences", responses=business_failures)
    def read_creation_preferences(
        scope: TrustedScope = Depends(scope_from_request),
        bypassed: bool = Depends(preference_session_bypassed),
    ) -> dict[str, object]:
        _refuse_in_bypass(bypassed)
        return control_service.creation_preference(scope)

    @app.put("/api/v1/user/creation-preferences", responses=business_failures)
    def save_creation_preferences(
        payload: CreationPreferenceRequest,
        scope: TrustedScope = Depends(scope_from_request),
        bypassed: bool = Depends(preference_session_bypassed),
    ) -> dict[str, object]:
        _refuse_in_bypass(bypassed)
        return control_service.save_creation_preference(
            scope,
            payload.enabled,
            payload.direction_defaults,
            payload.collaboration_note,
            payload.body_related_opt_in,
            payload.clear_direction_defaults,
        )

    @app.delete("/api/v1/user/creation-preferences", responses=business_failures)
    def delete_creation_preferences(
        scope: TrustedScope = Depends(scope_from_request),
        bypassed: bool = Depends(preference_session_bypassed),
    ) -> dict[str, object]:
        _refuse_in_bypass(bypassed)
        return control_service.delete_creation_preference(scope)

    @app.patch("/api/v1/materials/{asset_id}/reference-note", responses=business_failures)
    def set_material_reference_note(
        asset_id: UUID,
        payload: MaterialReferenceNoteRequest,
        scope: TrustedScope = Depends(scope_from_request),
    ) -> dict[str, object]:
        """One sentence about an original nobody read; without it the original stays unusable."""
        return control_service.set_material_reference_note(scope, asset_id, payload.reference_note)

    @app.post("/api/v1/content/opportunities", responses=business_failures)
    def content_opportunities(
        scope: TrustedScope = Depends(scope_from_request),
        bypassed: bool = Depends(preference_session_bypassed),
    ) -> dict[str, object]:
        """Read-only: browsing or refreshing opportunities never creates a business task."""
        return control_service.opportunities(scope, read_preference=not bypassed)

    @app.get("/api/v1/content/plan", responses=business_failures)
    def read_content_plan(scope: TrustedScope = Depends(scope_from_request)) -> dict[str, object]:
        return control_service.plan(scope)

    @app.put("/api/v1/content/plan", responses=business_failures)
    def save_content_plan(
        payload: ContentPlanRequest, scope: TrustedScope = Depends(scope_from_request)
    ) -> dict[str, object]:
        return control_service.save_plan(scope, {"items": [item.model_dump() for item in payload.items]})

    @app.post(
        "/api/v1/content/unmet-capability-requests",
        status_code=status.HTTP_201_CREATED,
        responses=business_failures,
    )
    def submit_unmet_capability_request(
        payload: UnmetCapabilityRequest,
        scope: TrustedScope = Depends(scope_from_request),
    ) -> dict[str, object]:
        direction = _requested_direction(payload.creative_direction)
        return control_service.create_unmet_request(scope, payload.request_text, direction)

    @app.get("/api/v1/content/unmet-capability-requests", responses=business_failures)
    def list_unmet_capability_requests(
        scope: TrustedScope = Depends(scope_from_request),
    ) -> list[dict[str, object]]:
        return control_service.list_unmet_requests(scope)

    def _requested_direction(payload: CreativeDirectionRequest | None) -> CreativeDirection | None:
        """Only record what the user actually saw; unknown ids are dropped, never guessed."""
        if payload is None:
            return None
        catalog = control_service.catalog
        selections = tuple(
            DirectionSelection(axis, entry.stable_id, entry.label, entry.label, False, "")
            for axis, stable_id in payload.selections.items()
            if (entry := catalog.entry(stable_id)) is not None
            and entry.axis == axis
            and (payload.body_related_opt_in or not entry.body_related)
        )
        return CreativeDirection(
            catalog_version=catalog.catalog_version,
            selections=selections,
            custom_text=payload.custom_text,
            body_related_opt_in=payload.body_related_opt_in,
            translation_notice=None,
            cleared_axes=tuple(payload.cleared_axes),
        )

    @app.post(
        "/api/v1/content",
        response_model=ContentVersionResponse | GreetingResponse | ContentQuestionResponse | ApplicationHandoffResponse,
        responses=business_failures,
    )
    def create_content(
        payload: CreateContentRequest,
        request: Request,
        _session_token: str | None = Security(session_cookie),
        bypassed: bool = Depends(preference_session_bypassed),
    ) -> dict[str, object]:
        if payload.reuse_version_id is None and requests_display_merchandising(payload.weak_seed):
            return {
                "kind": "handoff",
                "message": "这是给门店内部执行的陈列任务，请切换到陈列搭配。",
            }
        if payload.creative_direction is not None:
            assert_custom_direction_available(payload.creative_direction.custom_text)
        target = _target(payload.target)
        scope = resolve_content_scope(
            request,
            target,
            payload.publishing_identity_id,
        )
        with model_slot(request):
            return service.create_from_weak_seed(
                scope,
                payload.weak_seed,
                payload.reuse_version_id,
                target,
                _controls(payload, bypassed),
                payload.series_id,
                payload.series_position,
            )

    @app.post(
        "/api/v1/content/stream",
        response_class=StreamingResponse,
        responses=business_failures,
    )
    def create_content_stream(
        payload: CreateConversationRequest,
        request: Request,
        _session_token: str | None = Security(session_cookie),
        bypassed: bool = Depends(preference_session_bypassed),
    ) -> StreamingResponse:
        """Stream real lifecycle stages; the validated artifact is emitted only once."""
        if payload.creative_direction is not None:
            assert_custom_direction_available(payload.creative_direction.custom_text)
        selected_target = payload.target
        mentioned_target = target_from_text(payload.message)
        if (
            mentioned_target is not None
            and mentioned_target != selected_target
            and payload.target_conflict_resolution == "switch"
        ):
            selected_target = mentioned_target
        scope = resolve_content_scope(
            request,
            selected_target,
            payload.publishing_identity_id,
        )
        production_identity = (
            production_authority._tenant_identity(request)
            if production_authority is not None
            else None
        )
        events: queue.Queue[dict[str, object] | None] = queue.Queue(maxsize=16)
        cancelled = threading.Event()

        def emit(stage: str) -> None:
            if cancelled.is_set():
                raise GenerationFailed("生成已取消")
            events.put({"event": stage})

        def worker() -> None:
            try:
                if requests_display_merchandising(payload.message):
                    events.put(
                        {
                            "event": "conversation",
                            "kind": "chat",
                            "message": "这是门店内部陈列任务，请从陈列搭配入口继续。",
                        }
                    )
                    return
                if (
                    mentioned_target is not None
                    and mentioned_target != selected_target
                    and payload.target_conflict_resolution is None
                ):
                    events.put(
                        {
                            "event": "target_conflict",
                            "mentioned_target": mentioned_target,
                            "selected_target": selected_target,
                            "label": _target_metadata(mentioned_target)["label"],
                            "message": ("你在文字里提到了另一个平台。要切换过去，还是继续使用当前选择？"),
                        }
                    )
                    return
                if (
                    payload.request_id is not None
                    and payload.interaction_mode != "conversation"
                ):
                    completed = service.completed_request(scope, payload.request_id)
                    if completed is not None:
                        events.put(
                            {
                                "event": "completed",
                                "result": ContentVersionResponse.model_validate(
                                    completed
                                ).model_dump(mode="json"),
                            }
                        )
                        return
                with model_slot(request):
                    conversation_only = payload.interaction_mode == "conversation"
                    direct_generate = (
                        payload.interaction_mode == "generate"
                        or payload.direct_generate
                    )
                    result = service.respond_to_conversation(
                        scope,
                        payload.message,
                        tuple(ConversationTurn(turn.role, turn.content) for turn in payload.conversation),
                        selected_target,
                        _controls(payload, bypassed),
                        payload.series_id,
                        payload.series_position,
                        emit,
                        direct_generate,
                        conversation_only,
                        payload.request_id,
                    )
                if result.get("kind") == "content":
                    events.put({"event": "completed", "result": result})
                else:
                    if conversation_only and production_identity is not None:
                        assert production_authority is not None
                        production_authority.repository.record_content_conversation(
                            production_identity
                        )
                    events.put(
                        {
                            "event": "conversation",
                            "kind": result.get("kind", "chat"),
                            "message": result.get("message", ""),
                            "direct_generation_available": bool(
                                result.get("direct_generation_available", False)
                            ),
                        }
                    )
            except HTTPException as exc:
                message = (
                    "当前请求较多，请稍后再试。"
                    if exc.status_code == status.HTTP_429_TOO_MANY_REQUESTS
                    else "当前入口不能完成这次操作，请返回后重新进入。"
                )
                events.put({"event": "failed", "message": message})
            except (DomainError, GenerationFailed):
                events.put(
                    {
                        "event": "failed",
                        "message": (
                            "这次还没能整理成一份可靠的成品。你的想法仍然保留，"
                            "可以直接再试一次，也可以告诉我最想保留哪部分。"
                        ),
                    }
                )
            except Exception:
                _RUNTIME_LOGGER.exception("content collaboration failed")
                events.put(
                    {
                        "event": "failed",
                        "message": (
                            "这次还没能整理成一份可靠的成品。你的想法仍然保留，"
                            "可以直接再试一次，也可以告诉我最想保留哪部分。"
                        ),
                    }
                )
            finally:
                events.put(None)

        def event_stream() -> Iterator[bytes]:
            thread = threading.Thread(
                target=worker,
                name="content-collaboration",
                daemon=True,
            )
            thread.start()
            try:
                while True:
                    item = events.get()
                    if item is None:
                        break
                    yield (json.dumps(item, ensure_ascii=False) + "\n").encode("utf-8")
            finally:
                cancelled.set()

        return StreamingResponse(
            event_stream(),
            media_type="application/x-ndjson",
            headers={
                "Cache-Control": "no-store",
                "X-Accel-Buffering": "no",
            },
        )

    @app.post(
        "/api/v1/tasks/{task_id}/revisions",
        status_code=status.HTTP_201_CREATED,
        response_model=ContentVersionResponse | ContentQuestionResponse,
        responses=business_failures,
    )
    def revise_content(
        task_id: UUID,
        payload: RevisionRequest,
        request: Request,
        bypassed: bool = Depends(preference_session_bypassed),
    ) -> dict[str, object]:
        """Both revision paths replay what this task froze; neither reads today's preference."""
        target = _target(payload.target)
        source_target = payload.source_target or payload.target or "douyin_video"
        source_scope = resolve_content_scope(
            request,
            source_target,
            payload.publishing_identity_id,
        )
        # A same-goal revision reads the frozen snapshot and nothing else.  A cross-goal
        # adaptation recompiles from that same task, so it is handed an explicitly
        # preference-free control input.  Declaring the temporary preference-free session here
        # keeps that session honest end to end: it can only narrow this further, never widen it.
        reads_preference = _REVISION_MAY_READ_PREFERENCE and not bypassed
        if payload.request_id is not None:
            completed = service.completed_request(source_scope, payload.request_id)
            if completed is not None:
                return completed
        with model_slot(request):
            if target != source_target:
                return service.recompile_task(
                    source_scope,
                    resolve_content_scope(
                        request,
                        target,
                        payload.publishing_identity_id,
                    ),
                    task_id,
                    payload.instruction,
                    target,
                    RequestedControls(use_personal_preferences=reads_preference),
                )
            return service.revise(
                source_scope,
                task_id,
                payload.instruction,
                target,
                payload.request_id,
            )

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
        publishing_identity_id: UUID | None = None,
    ) -> dict[str, object]:
        return service.fetch_version(
            resolve_content_scope(request, target, publishing_identity_id),
            task_id,
            version,
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
        publishing_identity_id: UUID | None = None,
    ) -> dict[str, object]:
        return service.save_version(
            resolve_content_scope(request, target, publishing_identity_id),
            version_id,
        )

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
        return HTMLResponse(
            render_spa_shell(
                {"application": "public"},
                fallback=(
                    "<main><h1>笛语</h1><p>把一句想法，变成真正属于品牌的表达。</p><a href='/login'>开始创作</a></main>"
                ),
            )
        )

    @app.get(
        "/user",
        response_class=HTMLResponse,
        dependencies=[Security(session_cookie)],
        responses=business_failures,
    )
    def tenant_user_portal(request: Request) -> Response:
        if production_authority is not None:
            try:
                identity = production_authority._tenant_identity(request)
            except HTTPException as exc:
                if exc.status_code == status.HTTP_401_UNAUTHORIZED:
                    return RedirectResponse(
                        "/login",
                        status_code=status.HTTP_303_SEE_OTHER,
                    )
                raise
            if identity.audience != "tenant-user":
                return HTMLResponse(
                    render_tenant_user_access_denied(
                        "租户用户入口",
                        "/tenant-admin",
                        "返回租户管理入口",
                    ),
                    status_code=status.HTTP_403_FORBIDDEN,
                )
            capabilities: list[str] = []
            context: dict[str, object] | None = None
            available_identities = publishing_identities(identity)
            if available_identities:
                first_identity_id = UUID(str(available_identities[0]["id"]))
                identity_scope = production_authority.repository.content_scope(
                    identity,
                    None,
                    first_identity_id,
                )
                context = {
                    "application": "tenant_user",
                    "identity": workbench_service.user_portal_context(
                        identity_scope
                    )["identity"],
                    "publishing_identities": available_identities,
                }
                capabilities.append("content")
            try:
                display_scope = production_authority.repository.display_scope(identity)
            except DomainError:
                pass
            else:
                capabilities.append("display")
                if context is None:
                    display_context = workbench_service.display_context(
                        display_scope,
                        current_settings.generator_mode,
                    )
                    context = {
                        "application": "tenant_user",
                        "identity": display_context["identity"],
                    }
            if context is None:
                return HTMLResponse(
                    render_tenant_user_access_denied(
                        "租户用户入口",
                        "/login",
                        "返回租户用户登录",
                    ),
                    status_code=status.HTTP_403_FORBIDDEN,
                )
            context["capabilities"] = capabilities
            context["formal_runtime"] = True
        else:
            context = workbench_service.user_portal_context(user_scope_from_request(request))
            context["capabilities"] = ["content", "display"]
        return HTMLResponse(
            render_spa_shell(
                context,
                fallback=(
                    "<h1>租户用户工作台</h1><p>选择当前要完成的业务工作。</p>"
                    "<p><a href='/content'>内容生产（对外）</a> · <a href='/display'>陈列搭配（对内）</a></p>"
                    if current_settings.is_production
                    else "<p><a href='/ui/select/content'>内容生产（对外）</a> · "
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
    def tenant_management_portal(request: Request) -> Response:
        if production_authority is not None:
            try:
                identity = production_authority._tenant_identity(request)
            except HTTPException as exc:
                if exc.status_code == status.HTTP_401_UNAUTHORIZED:
                    destination = (
                        "/tenant-admin/login?next=demo"
                        if request.query_params.get("section") == "demo"
                        else "/tenant-admin/login"
                    )
                    return RedirectResponse(
                        destination,
                        status_code=status.HTTP_303_SEE_OTHER,
                    )
                raise
            if identity.audience != "tenant-admin":
                return HTMLResponse(
                    render_tenant_admin_access_denied(),
                    status_code=status.HTTP_403_FORBIDDEN,
                )
            try:
                context = workbench_service.tenant_management_context(
                    production_authority.repository.manager_scope(identity)
                )
            except DomainError:
                return HTMLResponse(
                    "<main><h1>租户管理</h1><p>租户壳已创建。完成品牌和企业发布账号基础资料后，"
                    "即可在本租户范围内维护自然人登录身份与账号资格。</p></main>"
                )
            context["formal_runtime"] = True
        else:
            context = workbench_service.tenant_management_context(management_scope_from_request(request))
        return HTMLResponse(
            render_spa_shell(
                context,
                fallback=("<h1>租户管理</h1><p>在当前租户范围内维护入驻、发布账号和已登记操作人。</p>"),
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
        target: ContentTarget | None = None,
        publishing_identity_id: UUID | None = None,
    ) -> Response:
        identity: TenantSession | None = None
        identity_options: list[dict[str, object]] = []
        selected_identity_id = publishing_identity_id
        if production_authority is not None:
            try:
                identity = production_authority._tenant_identity(request)
            except HTTPException as exc:
                if exc.status_code == status.HTTP_401_UNAUTHORIZED:
                    return RedirectResponse(
                        "/login",
                        status_code=status.HTTP_303_SEE_OTHER,
                    )
                raise
            if identity.audience != "tenant-user":
                return HTMLResponse(
                    render_tenant_user_access_denied(
                        "内容生产入口",
                        "/tenant-admin",
                        "返回租户管理入口",
                    ),
                    status_code=status.HTTP_403_FORBIDDEN,
                )
            try:
                identity_options = publishing_identities(identity)
                if not identity_options:
                    raise DomainError("当前账号还没有可使用的发布账号")
                available_identity_ids = {UUID(str(item["id"])) for item in identity_options}
                if selected_identity_id is None and len(identity_options) == 1:
                    selected_identity_id = next(iter(available_identity_ids))
                if selected_identity_id is None:
                    context: dict[str, object] = {
                        "application": "content",
                        "generator_mode": current_settings.generator_mode,
                        "identity": {},
                        "publishing_identities": identity_options,
                        "current_publishing_identity_id": None,
                        "targets": [],
                        "current_target": None,
                        "formal_runtime": True,
                    }
                    return HTMLResponse(
                        render_spa_shell(
                            context,
                            fallback=("<h1>内容创作</h1><p>请先选择这次要使用的发布账号。</p>"),
                        )
                    )
                if selected_identity_id not in available_identity_ids:
                    raise DomainError("当前账号没有获准操作这个发布账号")
                root_scope = production_authority.repository.content_scope(
                    identity,
                    None,
                    selected_identity_id,
                )
                target_options = content_targets(
                    root_scope,
                    request,
                    identity,
                    selected_identity_id,
                )
                if not target_options:
                    raise DomainError("当前表达身份没有可用的内容平台目标")
                allowed_targets = {item["value"] for item in target_options}
                resolved_target = target if target is not None else cast(ContentTarget, target_options[0]["value"])
                if resolved_target not in allowed_targets:
                    raise DomainError("当前表达身份没有这个内容平台目标")
                scope = production_authority.repository.content_scope(
                    identity,
                    resolved_target,
                    selected_identity_id,
                )
                if not workbench_service.is_content_operator(scope):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="当前自然人没有此发布账号工作资格",
                    )
            except DomainError:
                return HTMLResponse(
                    render_tenant_user_access_denied(
                        "内容生产入口",
                        "/user",
                        "返回租户用户入口",
                    ),
                    status_code=status.HTTP_403_FORBIDDEN,
                )
            except HTTPException as exc:
                if exc.status_code != status.HTTP_403_FORBIDDEN:
                    raise
                return HTMLResponse(
                    render_tenant_user_access_denied(
                        "内容生产入口",
                        "/user",
                        "返回租户用户入口",
                    ),
                    status_code=status.HTTP_403_FORBIDDEN,
                )
        else:
            scope_from_request(request)
            resolved_target = target or "douyin_video"
            scope = authority.require_content_target(
                request,
                resolved_target,
                publishing_identity_id,
            )
            target_options = content_targets(scope, request)
            selected_identity_id = scope.account_id
            identity_options = [
                {
                    "id": str(scope.account_id),
                    "name": "当前发布账号",
                    "profile_summary": "沿用当前账号画像",
                    "content_role": "当前表达身份",
                    "platform_targets": target_options,
                }
            ]
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
            fallback_extra = "<p>离线确定性测试模式：此页结果不是实际模型调用。</p>" + fallback_extra
        del notice
        assert selected_identity_id is not None
        context = workbench_service.content_context(scope, current_settings.generator_mode)
        context["targets"] = target_options
        context["current_target"] = resolved_target
        context["publishing_identities"] = identity_options
        context["current_publishing_identity_id"] = str(selected_identity_id)
        if current_settings.is_production:
            context["formal_runtime"] = True
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
            raw_series_id = fields.get("series_id", [""])[0]
            raw_series_position = fields.get("series_position", [""])[0]
            series_id = UUID(raw_series_id) if raw_series_id else None
            series_position = int(raw_series_position) if raw_series_position else None
            if requests_display_merchandising(weak_seed):
                return RedirectResponse(
                    "/content?" + urlencode({"notice": "这是给门店内部执行的陈列任务，请切换到陈列搭配。"}),
                    status_code=status.HTTP_303_SEE_OTHER,
                )
            with model_slot(request):
                result = service.create_from_weak_seed(
                    scope,
                    weak_seed,
                    target=target,
                    series_id=series_id,
                    series_position=series_position,
                )
        except DomainError as exc:
            return RedirectResponse("/content?notice=" + str(exc), status_code=status.HTTP_303_SEE_OTHER)
        if result["kind"] in {"greeting", "question"}:
            return RedirectResponse("/content?notice=" + str(result["message"]), status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(workbench_location(result, target=target), status_code=status.HTTP_303_SEE_OTHER)

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
            with model_slot(request):
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
            return RedirectResponse("/content?notice=" + str(exc), status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(workbench_location(result, target=target), status_code=status.HTTP_303_SEE_OTHER)

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
            with model_slot(request):
                result = service.create_from_weak_seed(
                    authority.require_content_target(request, target), weak_seed, version_id, target
                )
        except (DomainError, ValueError) as exc:
            return RedirectResponse("/content?notice=" + str(exc), status_code=status.HTTP_303_SEE_OTHER)
        if result["kind"] in {"greeting", "question"}:
            return RedirectResponse("/content?notice=" + str(result["message"]), status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(workbench_location(result, target=target), status_code=status.HTTP_303_SEE_OTHER)

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
            saved = service.save_version(authority.require_content_target(request, target), version_id)
        except (DomainError, ValueError) as exc:
            return RedirectResponse("/content?notice=" + str(exc), status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(
            workbench_location(
                {"task_id": task_id, "version": version},
                f"已主动保存版本 {saved['version_id']}",
                target,
            ),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return app
