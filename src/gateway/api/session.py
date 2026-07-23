from __future__ import annotations

import hashlib
import hmac

from fastapi import HTTPException, Request

from src.gateway.api.settings import Settings
from src.shared.types import DisplayScope, TrustedScope

_COOKIE_NAME = "diyu_session"
_SESSION_MARKER = b"m3-p1-server-session"


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

    def display_scope(self) -> DisplayScope:
        return DisplayScope(
            self._scope.tenant_id,
            self._settings.demo_display_user_id,
            self._scope.brand_id,
            self._settings.demo_display_organization_id,
        )

    def issue(self) -> str:
        return hmac.new(self._secret, _SESSION_MARKER, hashlib.sha256).hexdigest()

    def require(self, request: Request) -> TrustedScope:
        presented = request.cookies.get(_COOKIE_NAME, "")
        if not hmac.compare_digest(presented, self.issue()):
            raise HTTPException(status_code=401, detail="请先打开内容工作台建立可信会话")
        return self._scope


def set_session_cookie(response: object, authority: SessionAuthority) -> None:
    response.set_cookie(  # type: ignore[attr-defined]
        _COOKIE_NAME,
        authority.issue(),
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=60 * 60 * 8,
    )
