from __future__ import annotations

import hashlib
import hmac
from typing import Literal
from uuid import UUID

from fastapi import HTTPException, Request

from src.gateway.api.settings import Settings
from src.shared.types import ContentTarget, DisplayScope, TrustedScope

_COOKIE_NAME = "diyu_session"
ApplicationId = Literal["content-production", "content-production-store", "display-merchandising"]
_CONTENT_APPLICATION: ApplicationId = "content-production"
_STORE_CONTENT_APPLICATION: ApplicationId = "content-production-store"
_DISPLAY_APPLICATION: ApplicationId = "display-merchandising"


class SessionAuthority:
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

    def _display_scope(self) -> DisplayScope:
        return DisplayScope(
            self._scope.tenant_id,
            self._settings.demo_display_user_id,
            self._scope.brand_id,
            self._settings.demo_display_organization_id,
        )

    def issue(self, application: ApplicationId) -> str:
        return hmac.new(self._secret, application.encode("utf-8"), hashlib.sha256).hexdigest()

    def _require_application(self, request: Request, application: ApplicationId | tuple[ApplicationId, ...]) -> ApplicationId:
        presented = request.cookies.get(_COOKIE_NAME, "")
        if not presented:
            raise HTTPException(status_code=401, detail="请先从应用首页进入折线之间合成演示")
        expected = (application,) if isinstance(application, str) else application
        for candidate in expected:
            if hmac.compare_digest(presented, self.issue(candidate)):
                return candidate
        if any(
            hmac.compare_digest(presented, self.issue(candidate))
            for candidate in (_CONTENT_APPLICATION, _STORE_CONTENT_APPLICATION, _DISPLAY_APPLICATION)
        ):
            raise HTTPException(status_code=403, detail="当前演示会话属于另一应用，请先切换入口")
        raise HTTPException(status_code=401, detail="缺少或无效的可信演示会话")

    def require_content(self, request: Request) -> TrustedScope:
        application = self._require_application(
            request, (_CONTENT_APPLICATION, _STORE_CONTENT_APPLICATION)
        )
        if application == _STORE_CONTENT_APPLICATION:
            return TrustedScope(
                self._scope.tenant_id,
                self._settings.demo_store_content_user_id,
                self._scope.brand_id,
                self._settings.demo_store_content_account_id,
            )
        return self._scope

    def require_content_target(self, request: Request, target: ContentTarget) -> TrustedScope:
        """Map a natural target to a server-trusted account; no account ID is accepted from a client."""
        application = self._require_application(
            request, (_CONTENT_APPLICATION, _STORE_CONTENT_APPLICATION)
        )
        if application == _STORE_CONTENT_APPLICATION:
            if target != "douyin_video":
                raise HTTPException(status_code=403, detail="南城店内容身份不能切换到总部平台账号")
            return TrustedScope(
                self._scope.tenant_id,
                self._settings.demo_store_content_user_id,
                self._scope.brand_id,
                self._settings.demo_store_content_account_id,
            )
        accounts: dict[ContentTarget, UUID] = {
            "douyin_video": self._scope.account_id,
            "xiaohongshu_video": self._settings.demo_headquarters_xiaohongshu_account_id,
            "xiaohongshu_graphic": self._settings.demo_headquarters_xiaohongshu_account_id,
            "wechat_channels_video": self._settings.demo_headquarters_wechat_channels_account_id,
        }
        return TrustedScope(self._scope.tenant_id, self._scope.user_id, self._scope.brand_id, accounts[target])

    def require_display(self, request: Request) -> DisplayScope:
        self._require_application(request, _DISPLAY_APPLICATION)
        return self._display_scope()


def set_session_cookie(
    response: object, authority: SessionAuthority, application: ApplicationId
) -> None:
    response.set_cookie(  # type: ignore[attr-defined]
        _COOKIE_NAME,
        authority.issue(application),
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=60 * 60 * 8,
    )
