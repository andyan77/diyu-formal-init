from __future__ import annotations

import hashlib
import hmac
from typing import Literal, cast
from uuid import UUID

from fastapi import HTTPException, Request

from src.gateway.api.settings import Settings
from src.infrastructure.production_auth import (
    LoginRateLimiter,
    ModelRequestLimiter,
    OpsSession,
    ProductionAuthRepository,
    TenantSession,
)
from src.shared.types import ContentTarget, DisplayScope, TrustedScope

_COOKIE_NAME = "diyu_session"
ApplicationId = Literal[
    "tenant-user",
    "tenant-admin",
    "dual-tenant-user",
    "dual-tenant-admin",
    "content-production",
    "content-production-store",
    "display-merchandising",
    "dual-content-production",
    "external-content-production",
]
_APPLICATIONS: tuple[ApplicationId, ...] = (
    "tenant-user",
    "tenant-admin",
    "dual-tenant-user",
    "dual-tenant-admin",
    "content-production",
    "content-production-store",
    "display-merchandising",
    "dual-content-production",
    "external-content-production",
)
_CONTENT_APPLICATIONS: tuple[ApplicationId, ...] = (
    "content-production",
    "content-production-store",
    "dual-content-production",
    "external-content-production",
)
_USER_PORTAL_APPLICATIONS: tuple[ApplicationId, ...] = (
    "tenant-user",
    "dual-tenant-user",
    *_CONTENT_APPLICATIONS,
    "display-merchandising",
)
_MANAGEMENT_APPLICATIONS: tuple[ApplicationId, ...] = ("tenant-admin", "dual-tenant-admin")


class SessionAuthority:
    """Synthetic M5-3 sessions only; production authentication stays in M5-4."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._secret = settings.session_secret.get_secret_value().encode("utf-8")
        self._scope = TrustedScope(
            tenant_id=settings.demo_tenant_id,
            user_id=settings.demo_user_id,
            brand_id=settings.demo_brand_id,
            account_id=settings.demo_account_id,
        )

    @property
    def scope(self) -> TrustedScope:
        return self._scope

    @property
    def secure_cookie(self) -> bool:
        return False

    def _scope_for_user(self, user_id: UUID, account_id: UUID | None = None) -> TrustedScope:
        return TrustedScope(
            self._scope.tenant_id,
            user_id,
            self._scope.brand_id,
            account_id or self._scope.account_id,
        )

    def _display_scope(self) -> DisplayScope:
        return DisplayScope(
            self._scope.tenant_id,
            self._settings.demo_display_user_id,
            self._scope.brand_id,
            self._settings.demo_display_organization_id,
        )

    def issue(self, application: ApplicationId) -> str:
        return hmac.new(self._secret, application.encode("utf-8"), hashlib.sha256).hexdigest()

    def application(self, request: Request) -> ApplicationId:
        presented = request.cookies.get(_COOKIE_NAME, "")
        if not presented:
            raise HTTPException(status_code=401, detail="请先从合成入口进入当前工作空间")
        for candidate in _APPLICATIONS:
            if hmac.compare_digest(presented, self.issue(candidate)):
                return candidate
        raise HTTPException(status_code=401, detail="缺少或无效的可信合成会话")

    def _require_application(self, request: Request, applications: tuple[ApplicationId, ...]) -> ApplicationId:
        application = self.application(request)
        if application not in applications:
            raise HTTPException(status_code=403, detail="当前合成会话没有此入口资格")
        return application

    def _content_scope(self, application: ApplicationId) -> TrustedScope:
        if application == "content-production-store":
            return self._scope_for_user(
                self._settings.demo_store_content_user_id,
                self._settings.demo_store_content_account_id,
            )
        if application == "dual-content-production":
            return self._scope_for_user(self._settings.demo_dual_qualified_user_id)
        if application == "external-content-production":
            return self._scope_for_user(self._settings.demo_external_operator_user_id)
        return self._scope

    def require_content(self, request: Request) -> TrustedScope:
        return self._content_scope(self._require_application(request, _CONTENT_APPLICATIONS))

    def require_content_target(self, request: Request, target: ContentTarget) -> TrustedScope:
        """Map a natural target to the server-trusted account; clients never send account IDs."""
        application = self._require_application(request, _CONTENT_APPLICATIONS)
        scope = self._content_scope(application)
        if application == "content-production-store":
            if target != "douyin_video":
                raise HTTPException(status_code=403, detail="南城店内容身份不能切换到总部平台账号")
            return scope
        accounts: dict[ContentTarget, UUID] = {
            "douyin_video": scope.account_id,
            "xiaohongshu_video": self._settings.demo_headquarters_xiaohongshu_account_id,
            "xiaohongshu_graphic": self._settings.demo_headquarters_xiaohongshu_account_id,
            "wechat_channels_video": self._settings.demo_headquarters_wechat_channels_account_id,
        }
        return TrustedScope(scope.tenant_id, scope.user_id, scope.brand_id, accounts[target])

    def require_display(self, request: Request) -> DisplayScope:
        self._require_application(request, ("display-merchandising",))
        return self._display_scope()

    def require_user_portal(self, request: Request) -> TrustedScope:
        application = self._require_application(request, _USER_PORTAL_APPLICATIONS)
        if application in _CONTENT_APPLICATIONS:
            return self._content_scope(application)
        if application == "dual-tenant-user":
            return self._scope_for_user(self._settings.demo_dual_qualified_user_id)
        return self._scope

    def require_management(self, request: Request) -> TrustedScope:
        application = self._require_application(request, _MANAGEMENT_APPLICATIONS)
        if application == "dual-tenant-admin":
            return self._scope_for_user(self._settings.demo_dual_qualified_user_id)
        return self._scope_for_user(self._settings.demo_tenant_admin_user_id)


def set_session_cookie(response: object, authority: SessionAuthority, application: ApplicationId) -> None:
    response.set_cookie(  # type: ignore[attr-defined]
        _COOKIE_NAME,
        authority.issue(application),
        httponly=True,
        samesite="lax",
        secure=authority.secure_cookie,
        max_age=60 * 60 * 8,
    )


class ProductionSessionAuthority:
    """Formal production sessions; synthetic selector cookies are deliberately unsupported."""

    def __init__(self, settings: Settings) -> None:
        self.repository = ProductionAuthRepository(settings.app_database_url)
        self.login_limiter = LoginRateLimiter(settings.login_rate_limit_per_minute)
        self.model_limiter = ModelRequestLimiter(
            settings.model_global_concurrency,
            settings.model_tenant_concurrency,
            settings.model_tenant_rate_per_minute,
        )

    @property
    def secure_cookie(self) -> bool:
        return True

    @staticmethod
    def _tenant_identity(request: Request) -> TenantSession:
        authority = cast(ProductionSessionAuthority, request.app.state.session_authority)
        token = request.cookies.get(_COOKIE_NAME, "")
        session = authority.repository.load_tenant_session(token) if token else None
        if session is None:
            raise HTTPException(status_code=401, detail="请先通过当前正式入口登录")
        return session

    def application(self, request: Request) -> ApplicationId:
        return cast(ApplicationId, self._tenant_identity(request).audience)

    def require_content(self, request: Request) -> TrustedScope:
        identity = self._tenant_identity(request)
        if identity.audience != "tenant-user":
            raise HTTPException(status_code=403, detail="当前正式会话没有租户用户入口资格")
        return self.repository.content_scope(identity)

    def require_content_target(self, request: Request, target: ContentTarget) -> TrustedScope:
        identity = self._tenant_identity(request)
        if identity.audience != "tenant-user":
            raise HTTPException(status_code=403, detail="当前正式会话没有租户用户入口资格")
        return self.repository.content_scope(identity, target)

    def require_display(self, request: Request) -> DisplayScope:
        identity = self._tenant_identity(request)
        if identity.audience != "tenant-user":
            raise HTTPException(status_code=403, detail="当前正式会话没有租户用户入口资格")
        return self.repository.display_scope(identity)

    def require_user_portal(self, request: Request) -> TrustedScope:
        identity = self._tenant_identity(request)
        if identity.audience != "tenant-user":
            raise HTTPException(status_code=403, detail="当前正式会话没有租户用户入口资格")
        return self.repository.content_scope(identity)

    def require_management(self, request: Request) -> TrustedScope:
        identity = self._tenant_identity(request)
        if identity.audience != "tenant-admin":
            raise HTTPException(status_code=403, detail="当前正式会话没有租户管理入口资格")
        return self.repository.manager_scope(identity)

    def require_ops(self, request: Request) -> OpsSession:
        token = request.cookies.get("diyu_ops_session", "")
        session = self.repository.load_operator_session(token) if token else None
        if session is None:
            raise HTTPException(status_code=401, detail="请先通过平台运维入口完成密码和 MFA 登录")
        return session


def set_production_tenant_cookie(response: object, token: str) -> None:
    response.set_cookie(  # type: ignore[attr-defined]
        _COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        secure=True,
        max_age=60 * 60 * 8,
    )


def set_production_ops_cookie(response: object, token: str) -> None:
    response.set_cookie(  # type: ignore[attr-defined]
        "diyu_ops_session",
        token,
        httponly=True,
        samesite="lax",
        secure=True,
        max_age=60 * 60 * 8,
    )
