from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import BoundedSemaphore, Lock
from urllib.parse import quote
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row

from src.shared.errors import DomainError
from src.shared.types import DisplayScope, TrustedScope

_TOKEN_TTL = timedelta(hours=8)
_ACTIVATION_TTL = timedelta(hours=24)
_SCRYPT_N = 2**15
_SCRYPT_MAX_MEMORY = 64 * 1024 * 1024


@dataclass(frozen=True)
class TenantSession:
    tenant_id: UUID
    user_id: UUID
    audience: str


@dataclass(frozen=True)
class OpsSession:
    operator_id: UUID


class LoginRateLimiter:
    """Small process-local guard for the single first-release application instance."""

    def __init__(self, limit_per_minute: int) -> None:
        self._limit = limit_per_minute
        self._attempts: dict[str, deque[datetime]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str) -> bool:
        now = datetime.now(timezone.utc)
        floor = now - timedelta(minutes=1)
        with self._lock:
            attempts = self._attempts[key]
            while attempts and attempts[0] <= floor:
                attempts.popleft()
            if len(attempts) >= self._limit:
                return False
            attempts.append(now)
            return True


class ModelRequestLimiter:
    """Bound model work per process without retaining prompts or request bodies."""

    def __init__(self, global_limit: int, tenant_limit: int, tenant_rate_per_minute: int) -> None:
        self._global = BoundedSemaphore(global_limit)
        self._tenant_limit = tenant_limit
        self._tenant_rate_per_minute = tenant_rate_per_minute
        self._tenants: dict[UUID, BoundedSemaphore] = {}
        self._tenant_attempts: dict[UUID, deque[datetime]] = defaultdict(deque)
        self._recent_submissions: dict[tuple[UUID, UUID], datetime] = {}
        self._lock = Lock()

    def acquire(self, tenant_id: UUID, user_id: UUID) -> bool:
        now = datetime.now(timezone.utc)
        key = (tenant_id, user_id)
        with self._lock:
            previous = self._recent_submissions.get(key)
            if previous is not None and now - previous < timedelta(seconds=2):
                return False
            attempts = self._tenant_attempts[tenant_id]
            floor = now - timedelta(minutes=1)
            while attempts and attempts[0] <= floor:
                attempts.popleft()
            if len(attempts) >= self._tenant_rate_per_minute:
                return False
            tenant = self._tenants.setdefault(tenant_id, BoundedSemaphore(self._tenant_limit))
            if not self._global.acquire(blocking=False):
                return False
            if not tenant.acquire(blocking=False):
                self._global.release()
                return False
            self._recent_submissions[key] = now
            attempts.append(now)
            return True

    def release(self, tenant_id: UUID) -> None:
        with self._lock:
            tenant = self._tenants.get(tenant_id)
        if tenant is None:
            raise RuntimeError("模型并发租户状态丢失")
        tenant.release()
        self._global.release()


class ProductionAuthRepository:
    """Authentication persistence only; it never reads tenant content or source materials."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    @contextmanager
    def _tx(self) -> Iterator[psycopg.Cursor[dict[str, object]]]:
        with (
            psycopg.connect(self._database_url, row_factory=dict_row) as connection,
            connection.cursor() as cursor,
        ):
            yield cursor

    @contextmanager
    def _tenant_tx(self, tenant_id: UUID) -> Iterator[psycopg.Cursor[dict[str, object]]]:
        with self._tx() as cursor:
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),))
            yield cursor

    @staticmethod
    def _digest(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _token() -> tuple[str, str]:
        raw = secrets.token_urlsafe(32)
        return raw, ProductionAuthRepository._digest(raw)

    @staticmethod
    def _one(cursor: psycopg.Cursor[dict[str, object]], message: str) -> dict[str, object]:
        row = cursor.fetchone()
        if row is None:
            raise DomainError(message)
        return row

    @staticmethod
    def _tenant_audit(
        cursor: psycopg.Cursor[dict[str, object]],
        tenant_id: UUID,
        actor_id: UUID,
        event_type: str,
        entity_id: UUID,
    ) -> None:
        cursor.execute(
            "INSERT INTO activity_events (id, tenant_id, actor_id, event_type, entity_type, entity_id) "
            "VALUES (%s, %s, %s, %s, 'formal_identity', %s)",
            (uuid4(), tenant_id, actor_id, event_type, entity_id),
        )

    @staticmethod
    def _verify(password_hash: str | None, password: str) -> bool:
        if password_hash is None:
            return False
        try:
            kind, encoded_salt, encoded_hash = password_hash.split("$", maxsplit=2)
            if kind != "scrypt":
                return False
            salt = base64.urlsafe_b64decode(encoded_salt.encode("ascii"))
            expected = base64.urlsafe_b64decode(encoded_hash.encode("ascii"))
            actual = hashlib.scrypt(
                password.encode("utf-8"),
                salt=salt,
                n=_SCRYPT_N,
                r=8,
                p=1,
                dklen=32,
                maxmem=_SCRYPT_MAX_MEMORY,
            )
            return hmac.compare_digest(actual, expected)
        except (ValueError, TypeError):
            return False

    @staticmethod
    def _password_hash(password: str) -> str:
        salt = secrets.token_bytes(16)
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=_SCRYPT_N,
            r=8,
            p=1,
            dklen=32,
            maxmem=_SCRYPT_MAX_MEMORY,
        )
        return (
            "scrypt$"
            + base64.urlsafe_b64encode(salt).decode("ascii")
            + "$"
            + base64.urlsafe_b64encode(digest).decode("ascii")
        )

    @staticmethod
    def _totp_secret() -> str:
        return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")

    @staticmethod
    def _totp_code(secret: str, counter: int) -> str:
        padded = secret + "=" * (-len(secret) % 8)
        digest = hmac.new(
            base64.b32decode(padded.encode("ascii"), casefold=True),
            counter.to_bytes(8, "big"),
            hashlib.sha1,
        ).digest()
        offset = digest[-1] & 0x0F
        value = int.from_bytes(digest[offset : offset + 4], "big") & 0x7FFFFFFF
        return f"{value % 1_000_000:06d}"

    @classmethod
    def _verify_totp(cls, secret: str, code: str) -> bool:
        if len(code) != 6 or not code.isdecimal():
            return False
        counter = int(time.time() // 30)
        try:
            return any(hmac.compare_digest(cls._totp_code(secret, counter + delta), code) for delta in (-1, 0, 1))
        except (ValueError, binascii.Error):
            return False

    def authenticate_tenant_user(self, username: str, password: str, audience: str) -> TenantSession | None:
        with self._tx() as cursor:
            cursor.execute(
                """
                SELECT credential.user_id, credential.tenant_id, credential.password_hash
                FROM user_credentials credential
                WHERE lower(credential.username) = lower(%s)
                """,
                (username,),
            )
            row = cursor.fetchone()
        if row is None or not self._verify(
            str(row["password_hash"]) if row["password_hash"] is not None else None, password
        ):
            return None
        tenant_id = UUID(str(row["tenant_id"]))
        user_id = UUID(str(row["user_id"]))
        with self._tenant_tx(tenant_id) as cursor:
            cursor.execute(
                """
                SELECT user_record.enabled AS user_enabled, registry.enabled AS tenant_enabled,
                       EXISTS (
                         SELECT 1 FROM tenant_management_grants grant_record
                         WHERE grant_record.tenant_id = %s
                           AND grant_record.user_id = %s AND grant_record.enabled = true
                       ) AS is_manager
                FROM users user_record
                JOIN ops_tenant_registry registry ON registry.tenant_id = user_record.tenant_id
                WHERE user_record.tenant_id = %s AND user_record.id = %s
                """,
                (tenant_id, user_id, tenant_id, user_id),
            )
            access = cursor.fetchone()
        if access is None or not bool(access["user_enabled"]) or not bool(access["tenant_enabled"]):
            return None
        if audience == "tenant-admin" and not bool(access["is_manager"]):
            return None
        return TenantSession(tenant_id, user_id, audience)

    def create_tenant_session(self, identity: TenantSession) -> str:
        raw, digest = self._token()
        with self._tx() as cursor:
            cursor.execute(
                """
                INSERT INTO tenant_sessions (id, tenant_id, user_id, audience, token_digest, expires_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    uuid4(),
                    identity.tenant_id,
                    identity.user_id,
                    identity.audience,
                    digest,
                    datetime.now(timezone.utc) + _TOKEN_TTL,
                ),
            )
        return raw

    def load_tenant_session(self, token: str) -> TenantSession | None:
        with self._tx() as cursor:
            cursor.execute(
                """
                SELECT session.tenant_id, session.user_id, session.audience
                FROM tenant_sessions session
                WHERE session.token_digest = %s AND session.revoked_at IS NULL AND session.expires_at > now()
                """,
                (self._digest(token),),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        tenant_id = UUID(str(row["tenant_id"]))
        user_id = UUID(str(row["user_id"]))
        with self._tenant_tx(tenant_id) as cursor:
            cursor.execute(
                """
                SELECT user_record.enabled AS user_enabled, registry.enabled AS tenant_enabled,
                       EXISTS (
                         SELECT 1 FROM tenant_management_grants grant_record
                         WHERE grant_record.tenant_id = %s
                           AND grant_record.user_id = %s AND grant_record.enabled = true
                       ) AS is_manager
                FROM users user_record
                JOIN ops_tenant_registry registry ON registry.tenant_id = user_record.tenant_id
                WHERE user_record.tenant_id = %s AND user_record.id = %s
                """,
                (tenant_id, user_id, tenant_id, user_id),
            )
            access = cursor.fetchone()
        if access is None or not bool(access["user_enabled"]) or not bool(access["tenant_enabled"]):
            return None
        if str(row["audience"]) == "tenant-admin" and not bool(access["is_manager"]):
            return None
        return TenantSession(tenant_id, user_id, str(row["audience"]))

    def revoke_tenant_session(self, token: str) -> None:
        with self._tx() as cursor:
            cursor.execute(
                "UPDATE tenant_sessions SET revoked_at = now() WHERE token_digest = %s",
                (self._digest(token),),
            )

    def complete_activation(self, raw_token: str, password: str) -> None:
        token_digest = self._digest(raw_token)
        with self._tx() as cursor:
            cursor.execute(
                """
                SELECT id, tenant_id, user_id FROM user_activation_tokens
                WHERE token_digest = %s AND used_at IS NULL AND expires_at > now()
                """,
                (token_digest,),
            )
            token = self._one(cursor, "激活或重置链接无效或已过期")
            tenant_id = UUID(str(token["tenant_id"]))
            user_id = UUID(str(token["user_id"]))
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),))
            cursor.execute(
                "UPDATE user_credentials SET password_hash = %s, password_changed_at = now() "
                "WHERE tenant_id = %s AND user_id = %s",
                (self._password_hash(password), token["tenant_id"], token["user_id"]),
            )
            cursor.execute("UPDATE user_activation_tokens SET used_at = now() WHERE id = %s", (token["id"],))
            cursor.execute(
                "UPDATE tenant_sessions SET revoked_at = now() "
                "WHERE tenant_id = %s AND user_id = %s AND revoked_at IS NULL",
                (token["tenant_id"], token["user_id"]),
            )
            self._tenant_audit(cursor, tenant_id, user_id, "password.activated_or_reset", user_id)

    def change_password(self, identity: TenantSession, current_password: str, new_password: str) -> bool:
        with self._tx() as cursor:
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(identity.tenant_id),))
            cursor.execute(
                "SELECT password_hash FROM user_credentials WHERE tenant_id = %s AND user_id = %s",
                (identity.tenant_id, identity.user_id),
            )
            row = cursor.fetchone()
            if row is None or not self._verify(
                str(row["password_hash"]) if row["password_hash"] is not None else None,
                current_password,
            ):
                return False
            cursor.execute(
                "UPDATE user_credentials SET password_hash = %s, password_changed_at = now() "
                "WHERE tenant_id = %s AND user_id = %s",
                (self._password_hash(new_password), identity.tenant_id, identity.user_id),
            )
            cursor.execute(
                "UPDATE tenant_sessions SET revoked_at = now() "
                "WHERE tenant_id = %s AND user_id = %s AND revoked_at IS NULL",
                (identity.tenant_id, identity.user_id),
            )
            self._tenant_audit(cursor, identity.tenant_id, identity.user_id, "password.changed", identity.user_id)
        return True

    def create_tenant_user(
        self,
        manager: TenantSession,
        display_name: str,
        username: str,
        account_id: UUID | None,
        grants_tenant_management: bool,
    ) -> dict[str, str]:
        user_id = uuid4()
        activation_id = uuid4()
        raw_token, digest = self._token()
        with self._tenant_tx(manager.tenant_id) as cursor:
            cursor.execute(
                "SELECT organization_id FROM users WHERE tenant_id = %s AND id = %s AND enabled = true",
                (manager.tenant_id, manager.user_id),
            )
            organization_id = self._one(cursor, "找不到当前租户管理员")["organization_id"]
            cursor.execute(
                "INSERT INTO users (id, tenant_id, organization_id, display_name) VALUES (%s, %s, %s, %s)",
                (user_id, manager.tenant_id, organization_id, display_name),
            )
            cursor.execute(
                "INSERT INTO user_credentials (user_id, tenant_id, username) VALUES (%s, %s, %s)",
                (user_id, manager.tenant_id, username),
            )
            cursor.execute(
                "INSERT INTO user_activation_tokens "
                "(id, tenant_id, user_id, purpose, token_digest, expires_at, created_by) "
                "VALUES (%s, %s, %s, 'activate', %s, %s, %s)",
                (
                    activation_id,
                    manager.tenant_id,
                    user_id,
                    digest,
                    datetime.now(timezone.utc) + _ACTIVATION_TTL,
                    manager.user_id,
                ),
            )
            if account_id is not None:
                cursor.execute(
                    "SELECT id FROM content_accounts WHERE tenant_id = %s AND id = %s AND enabled = true",
                    (manager.tenant_id, account_id),
                )
                self._one(cursor, "只能授予当前租户已启用的企业发布账号")
                cursor.execute(
                    "INSERT INTO auth_grants (id, tenant_id, user_id, account_id, role_name) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (uuid4(), manager.tenant_id, user_id, account_id, "发布账号操作资格"),
                )
            if grants_tenant_management:
                cursor.execute(
                    "INSERT INTO tenant_management_grants (id, tenant_id, user_id) VALUES (%s, %s, %s)",
                    (uuid4(), manager.tenant_id, user_id),
                )
            self._tenant_audit(cursor, manager.tenant_id, manager.user_id, "tenant_user.created", user_id)
        return {
            "user_id": str(user_id),
            "username": username,
            "activation_token": raw_token,
            "activation_id": str(activation_id),
        }

    def create_reset_token(self, manager: TenantSession, user_id: UUID) -> str:
        raw_token, digest = self._token()
        with self._tenant_tx(manager.tenant_id) as cursor:
            cursor.execute(
                "SELECT id FROM users WHERE tenant_id = %s AND id = %s AND enabled = true",
                (manager.tenant_id, user_id),
            )
            self._one(cursor, "找不到当前租户可重置的自然人")
            cursor.execute(
                "INSERT INTO user_activation_tokens "
                "(id, tenant_id, user_id, purpose, token_digest, expires_at, created_by) "
                "VALUES (%s, %s, %s, 'reset', %s, %s, %s)",
                (
                    uuid4(),
                    manager.tenant_id,
                    user_id,
                    digest,
                    datetime.now(timezone.utc) + _ACTIVATION_TTL,
                    manager.user_id,
                ),
            )
            self._tenant_audit(cursor, manager.tenant_id, manager.user_id, "password.reset_issued", user_id)
        return raw_token

    def disable_tenant_user(self, manager: TenantSession, user_id: UUID) -> None:
        """Disable a natural login and every current work grant in its own tenant."""
        with self._tenant_tx(manager.tenant_id) as cursor:
            cursor.execute(
                "UPDATE users SET enabled = false WHERE tenant_id = %s AND id = %s AND enabled = true RETURNING id",
                (manager.tenant_id, user_id),
            )
            self._one(cursor, "找不到当前租户可停用的自然人")
            cursor.execute(
                "UPDATE auth_grants SET enabled = false WHERE tenant_id = %s AND user_id = %s AND enabled = true",
                (manager.tenant_id, user_id),
            )
            cursor.execute(
                "UPDATE tenant_management_grants SET enabled = false "
                "WHERE tenant_id = %s AND user_id = %s AND enabled = true",
                (manager.tenant_id, user_id),
            )
            cursor.execute(
                "UPDATE tenant_sessions SET revoked_at = now() WHERE tenant_id = %s AND user_id = %s "
                "AND revoked_at IS NULL",
                (manager.tenant_id, user_id),
            )
            self._tenant_audit(cursor, manager.tenant_id, manager.user_id, "tenant_user.disabled", user_id)

    def revoke_account_grant(self, manager: TenantSession, user_id: UUID, account_id: UUID) -> None:
        with self._tenant_tx(manager.tenant_id) as cursor:
            cursor.execute(
                "UPDATE auth_grants SET enabled = false WHERE tenant_id = %s AND user_id = %s "
                "AND account_id = %s AND enabled = true RETURNING id",
                (manager.tenant_id, user_id, account_id),
            )
            self._one(cursor, "找不到当前租户可撤销的发布账号资格")
            self._tenant_audit(cursor, manager.tenant_id, manager.user_id, "publishing_account_grant.revoked", user_id)

    def bootstrap_existing_tenant_admin(self, tenant_id: UUID, user_id: UUID, username: str) -> str:
        """Create the first one-time activation material without creating a synthetic password."""
        raw_token, digest = self._token()
        with self._tenant_tx(tenant_id) as cursor:
            cursor.execute(
                "SELECT id FROM tenant_management_grants WHERE tenant_id = %s AND user_id = %s AND enabled = true",
                (tenant_id, user_id),
            )
            self._one(cursor, "指定自然人不是当前租户管理员")
            cursor.execute(
                "SELECT user_id FROM user_credentials WHERE tenant_id = %s AND user_id = %s",
                (tenant_id, user_id),
            )
            if cursor.fetchone() is not None:
                raise DomainError("指定租户管理员已经有正式登录身份")
            cursor.execute(
                "INSERT INTO user_credentials (user_id, tenant_id, username) VALUES (%s, %s, %s)",
                (user_id, tenant_id, username),
            )
            cursor.execute(
                "INSERT INTO user_activation_tokens "
                "(id, tenant_id, user_id, purpose, token_digest, expires_at) "
                "VALUES (%s, %s, %s, 'activate', %s, %s)",
                (uuid4(), tenant_id, user_id, digest, datetime.now(timezone.utc) + _ACTIVATION_TTL),
            )
        return raw_token

    def authenticate_operator(self, username: str, password: str, totp_code: str) -> OpsSession | None:
        with self._tx() as cursor:
            cursor.execute(
                "SELECT id, password_hash, totp_secret, enabled FROM platform_operators "
                "WHERE lower(username) = lower(%s)",
                (username,),
            )
            row = cursor.fetchone()
        if row is None or not bool(row["enabled"]):
            return None
        if not self._verify(str(row["password_hash"]), password):
            return None
        if not self._verify_totp(str(row["totp_secret"]), totp_code):
            return None
        return OpsSession(UUID(str(row["id"])))

    def create_operator_session(self, identity: OpsSession) -> str:
        raw, digest = self._token()
        with self._tx() as cursor:
            cursor.execute(
                "INSERT INTO platform_sessions (id, operator_id, token_digest, expires_at) VALUES (%s, %s, %s, %s)",
                (uuid4(), identity.operator_id, digest, datetime.now(timezone.utc) + _TOKEN_TTL),
            )
        return raw

    def load_operator_session(self, token: str) -> OpsSession | None:
        with self._tx() as cursor:
            cursor.execute(
                """
                SELECT session.operator_id FROM platform_sessions session
                JOIN platform_operators operator_record ON operator_record.id = session.operator_id
                WHERE session.token_digest = %s AND session.revoked_at IS NULL AND session.expires_at > now()
                  AND operator_record.enabled = true
                """,
                (self._digest(token),),
            )
            row = cursor.fetchone()
        return OpsSession(UUID(str(row["operator_id"]))) if row is not None else None

    def bootstrap_operator(self, username: str, password: str) -> tuple[str, str]:
        operator_id = uuid4()
        totp_secret = self._totp_secret()
        with self._tx() as cursor:
            cursor.execute("SELECT COUNT(*) AS count FROM platform_operators")
            if int(str(self._one(cursor, "无法读取平台运维初始化状态")["count"])) != 0:
                raise DomainError("平台运维首位身份已经初始化")
            cursor.execute(
                "INSERT INTO platform_operators (id, username, password_hash, totp_secret) VALUES (%s, %s, %s, %s)",
                (operator_id, username, self._password_hash(password), totp_secret),
            )
        return (
            str(operator_id),
            f"otpauth://totp/{quote('笛语')}:{quote(username)}?secret={totp_secret}&issuer={quote('笛语')}",
        )

    def provision_tenant(
        self, operator: OpsSession, tenant_name: str, administrator_name: str, username: str
    ) -> dict[str, str]:
        tenant_id, organization_id, user_id, credential_id, activation_id = (uuid4() for _ in range(5))
        raw_token, digest = self._token()
        with self._tx() as cursor:
            cursor.execute(
                "SELECT * FROM ops_provision_tenant(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    tenant_id,
                    tenant_name,
                    organization_id,
                    user_id,
                    administrator_name,
                    username,
                    credential_id,
                    activation_id,
                    digest,
                    datetime.now(timezone.utc) + _ACTIVATION_TTL,
                ),
            )
            cursor.execute(
                "INSERT INTO ops_audit_events (id, operator_id, event_type, tenant_id) VALUES (%s, %s, %s, %s)",
                (uuid4(), operator.operator_id, "tenant.provisioned", tenant_id),
            )
        return {
            "tenant_id": str(tenant_id),
            "administrator_id": str(user_id),
            "username": username,
            "activation_token": raw_token,
        }

    def set_tenant_enabled(self, operator: OpsSession, tenant_id: UUID, enabled: bool) -> None:
        with self._tx() as cursor:
            cursor.execute("SELECT ops_set_tenant_enabled(%s, %s)", (tenant_id, enabled))
            cursor.execute(
                "INSERT INTO ops_audit_events (id, operator_id, event_type, tenant_id) VALUES (%s, %s, %s, %s)",
                (uuid4(), operator.operator_id, "tenant.enabled" if enabled else "tenant.disabled", tenant_id),
            )

    def runtime_summary(self, operator: OpsSession) -> dict[str, int | float | None]:
        """Return only fleet-level counters; the controlled function exposes no tenant bodies."""
        del operator
        with self._tx() as cursor:
            cursor.execute("SELECT * FROM ops_runtime_summary()")
            row = self._one(cursor, "无法读取平台运行汇总")
            cursor.execute("SELECT ops_runtime_provider_tokens() AS provider_total_tokens")
            provider = self._one(cursor, "无法读取供应商用量汇总")
        summary: dict[str, int | float | None] = {
            key: (float(str(value)) if key == "average_latency_ms" and value is not None else int(str(value or 0)))
            for key, value in row.items()
        }
        summary["provider_total_tokens"] = int(str(provider["provider_total_tokens"] or 0))
        return summary

    def content_scope(self, identity: TenantSession, target: str | None = None) -> TrustedScope:
        with self._tenant_tx(identity.tenant_id) as cursor:
            cursor.execute(
                """
                SELECT account.id AS account_id, account.brand_id
                FROM auth_grants grant_record
                JOIN content_accounts account ON account.id = grant_record.account_id
                    AND account.tenant_id = grant_record.tenant_id
                WHERE grant_record.tenant_id = %s AND grant_record.user_id = %s
                  AND grant_record.enabled = true AND account.enabled = true
                  AND (%s::text IS NULL OR (account.channel = CASE WHEN %s LIKE 'xiaohongshu%%' THEN '小红书'
                     WHEN %s = 'wechat_channels_video' THEN '微信视频号' ELSE '抖音' END))
                ORDER BY account.name LIMIT 1
                """,
                (identity.tenant_id, identity.user_id, target, target, target),
            )
            row = self._one(cursor, "当前自然人没有可用发布账号资格")
        return TrustedScope(
            identity.tenant_id, identity.user_id, UUID(str(row["brand_id"])), UUID(str(row["account_id"]))
        )

    def allowed_content_targets(self, identity: TenantSession) -> tuple[str, ...]:
        targets: list[str] = []
        with self._tenant_tx(identity.tenant_id) as cursor:
            cursor.execute(
                """
                SELECT DISTINCT account.channel
                FROM auth_grants grant_record
                JOIN content_accounts account ON account.id = grant_record.account_id
                    AND account.tenant_id = grant_record.tenant_id
                WHERE grant_record.tenant_id = %s AND grant_record.user_id = %s
                  AND grant_record.enabled = true AND account.enabled = true
                """,
                (identity.tenant_id, identity.user_id),
            )
            channels = {str(row["channel"]) for row in cursor.fetchall()}
        if "抖音" in channels:
            targets.append("douyin_video")
        if "小红书" in channels:
            targets.extend(("xiaohongshu_video", "xiaohongshu_graphic"))
        if "微信视频号" in channels:
            targets.append("wechat_channels_video")
        return tuple(targets)

    def display_scope(self, identity: TenantSession) -> DisplayScope:
        with self._tenant_tx(identity.tenant_id) as cursor:
            cursor.execute(
                """
                SELECT store.brand_id, user_record.organization_id
                FROM users user_record
                JOIN display_stores store ON store.tenant_id = user_record.tenant_id
                    AND store.execution_organization_id = user_record.organization_id
                WHERE user_record.tenant_id = %s AND user_record.id = %s AND user_record.enabled = true
                ORDER BY store.name LIMIT 1
                """,
                (identity.tenant_id, identity.user_id),
            )
            row = self._one(cursor, "当前自然人没有陈列执行资格")
        return DisplayScope(
            identity.tenant_id,
            identity.user_id,
            UUID(str(row["brand_id"])),
            UUID(str(row["organization_id"])),
        )

    def manager_scope(self, identity: TenantSession) -> TrustedScope:
        with self._tenant_tx(identity.tenant_id) as cursor:
            cursor.execute(
                "SELECT brand_id, id AS account_id FROM content_accounts "
                "WHERE tenant_id = %s AND enabled = true ORDER BY name LIMIT 1",
                (identity.tenant_id,),
            )
            row = self._one(cursor, "当前租户还没有可管理的发布账号")
        return TrustedScope(
            identity.tenant_id, identity.user_id, UUID(str(row["brand_id"])), UUID(str(row["account_id"]))
        )
