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
from typing import TypedDict
from urllib.parse import quote
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row

from src.shared.errors import DomainError
from src.shared.types import (
    DisplayScope,
    MaterialMaintenanceScope,
    TenantManagementScope,
    TrustedScope,
)

_TOKEN_TTL = timedelta(hours=8)
_ACTIVATION_TTL = timedelta(hours=24)
MODEL_REQUEST_DUPLICATE_WINDOW_SECONDS = 2.0
_SCRYPT_N = 2**15
_SCRYPT_MAX_MEMORY = 64 * 1024 * 1024
_DIYU_FASHION_TENANT_NAME = "笛语服饰"
_DIYU_FASHION_BRAND_DRAFT = """品牌名称：笛语服饰

我们想服务家庭生活中的真实穿衣、商品取舍、生活叙事与造型灵感。
我们尊重家庭成员各自成立、自然呼应，不要求整齐同款。
我们的表达希望真实、克制、有依据，也尊重每个人的差异。

稳定边界：不编造商品、价格、库存、研发、人物经历、顾客或门店事实；不利用儿童、身体、年龄或家庭焦虑施压。"""
_GENERIC_BRAND_DRAFT_TEMPLATE = """品牌名称：{tenant_name}

这是一份待品牌方确认的表达草案。请用自然语言补充品牌希望服务的人、准备长期表达的方向和真实成立的边界。

稳定边界：不编造商品、价格、库存、研发、人物经历、顾客或门店事实；不使用尚未确认的资料作为品牌事实。"""
_DRAFT_POSITIONING = "待品牌方确认；确认后以当前品牌表达版本为准。"
_DRAFT_DECISION_ORDER = "先使用已确认事实；未确认商品与门店资料不进入正式上下文。"
_DRAFT_TONE = "待品牌方以自然语言确认。"
_DRAFT_AUDIENCE = "不预设具体年龄、身份或消费动机；以当前任务和已确认品牌表达为准。"


@dataclass(frozen=True)
class TenantSession:
    tenant_id: UUID
    user_id: UUID
    audience: str


@dataclass(frozen=True)
class OpsSession:
    operator_id: UUID


class CreatedTenantUser(TypedDict):
    user_id: str
    username: str
    activation_token: str
    activation_id: str
    entry_type: str
    display_store_ids: list[str]


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
            if previous is not None and now - previous < timedelta(
                seconds=MODEL_REQUEST_DUPLICATE_WINDOW_SECONDS
            ):
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
        expected_entry_kind = {
            "tenant-admin": "tenant_admin",
            "tenant-user": "tenant_user",
        }.get(audience)
        if expected_entry_kind is None:
            return None
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
                SELECT user_record.enabled AS user_enabled,
                       user_record.entry_kind,
                       user_record.business_data_kind,
                       registry.enabled AS tenant_enabled,
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
        if (
            access is None
            or not bool(access["user_enabled"])
            or not bool(access["tenant_enabled"])
            or str(access["business_data_kind"]) == "legacy_hidden"
        ):
            return None
        if str(access["entry_kind"]) != expected_entry_kind:
            return None
        if audience == "tenant-admin" and not bool(access["is_manager"]):
            return None
        if audience == "tenant-user" and bool(access["is_manager"]):
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
                SELECT user_record.enabled AS user_enabled,
                       user_record.entry_kind,
                       user_record.business_data_kind,
                       registry.enabled AS tenant_enabled,
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
        if (
            access is None
            or not bool(access["user_enabled"])
            or not bool(access["tenant_enabled"])
            or str(access["business_data_kind"]) == "legacy_hidden"
        ):
            return None
        audience = str(row["audience"])
        expected_entry_kind = {
            "tenant-admin": "tenant_admin",
            "tenant-user": "tenant_user",
        }.get(audience)
        if expected_entry_kind is None or str(access["entry_kind"]) != expected_entry_kind:
            return None
        if audience == "tenant-admin" and not bool(access["is_manager"]):
            return None
        if audience == "tenant-user" and bool(access["is_manager"]):
            return None
        return TenantSession(tenant_id, user_id, audience)

    def revoke_tenant_session(self, token: str) -> None:
        with self._tx() as cursor:
            cursor.execute(
                "UPDATE tenant_sessions SET revoked_at = now() WHERE token_digest = %s",
                (self._digest(token),),
            )

    def record_content_rate_limit(self, identity: TenantSession) -> None:
        """Record only the bounded event; never persist a prompt or content body."""
        with self._tenant_tx(identity.tenant_id) as cursor:
            self._tenant_audit(
                cursor,
                identity.tenant_id,
                identity.user_id,
                "content.rate_limited",
                identity.user_id,
            )

    def record_content_conversation(self, identity: TenantSession) -> None:
        """Count one completed ordinary conversation without retaining its text."""
        with self._tenant_tx(identity.tenant_id) as cursor:
            self._tenant_audit(
                cursor,
                identity.tenant_id,
                identity.user_id,
                "content.conversation",
                identity.user_id,
            )

    def revoke_operator_session(self, token: str) -> None:
        """Revoke only the current operations session."""
        with self._tx() as cursor:
            cursor.execute(
                "UPDATE platform_sessions SET revoked_at = now() WHERE token_digest = %s",
                (self._digest(token),),
            )

    def activation_purpose(self, raw_token: str) -> str | None:
        """Return a known link purpose so expired or used reset pages remain truthful."""
        with self._tx() as cursor:
            cursor.execute(
                """
                SELECT purpose
                FROM user_activation_tokens
                WHERE token_digest = %s
                """,
                (self._digest(raw_token),),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        purpose = str(row["purpose"])
        return purpose if purpose in {"activate", "reset"} else None

    def complete_activation(self, raw_token: str, password: str) -> str:
        token_digest = self._digest(raw_token)
        with self._tx() as cursor:
            cursor.execute(
                """
                SELECT id, tenant_id, user_id FROM user_activation_tokens
                WHERE token_digest = %s AND used_at IS NULL AND expires_at > now()
                """,
                (token_digest,),
            )
            candidate = self._one(cursor, "激活或重置链接无效或已过期")
            tenant_id = UUID(str(candidate["tenant_id"]))
            user_id = UUID(str(candidate["user_id"]))
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),))
            cursor.execute(
                "SELECT id FROM users WHERE tenant_id = %s AND id = %s AND enabled = true FOR UPDATE",
                (tenant_id, user_id),
            )
            self._one(cursor, "激活或重置链接无效或已过期")
            cursor.execute(
                """
                SELECT id, tenant_id, user_id FROM user_activation_tokens
                WHERE token_digest = %s AND tenant_id = %s AND user_id = %s
                  AND used_at IS NULL AND expires_at > now()
                FOR UPDATE
                """,
                (token_digest, tenant_id, user_id),
            )
            token = self._one(cursor, "激活或重置链接无效或已过期")
            cursor.execute(
                "UPDATE user_credentials SET password_hash = %s, password_changed_at = now() "
                "WHERE tenant_id = %s AND user_id = %s",
                (self._password_hash(password), token["tenant_id"], token["user_id"]),
            )
            cursor.execute(
                "UPDATE user_activation_tokens SET used_at = now() "
                "WHERE tenant_id = %s AND user_id = %s AND used_at IS NULL",
                (token["tenant_id"], token["user_id"]),
            )
            cursor.execute(
                "UPDATE tenant_sessions SET revoked_at = now() "
                "WHERE tenant_id = %s AND user_id = %s AND revoked_at IS NULL",
                (token["tenant_id"], token["user_id"]),
            )
            self._tenant_audit(
                cursor,
                tenant_id,
                user_id,
                "password.pending_links_invalidated_on_use",
                user_id,
            )
            self._tenant_audit(cursor, tenant_id, user_id, "password.activated_or_reset", user_id)
            cursor.execute(
                """
                SELECT entry_kind
                  FROM users
                 WHERE tenant_id = %s
                   AND id = %s
                """,
                (tenant_id, user_id),
            )
            entry_kind = str(self._one(cursor, "无法确认激活后的入口资格")["entry_kind"])
        return "tenant-admin" if entry_kind == "tenant_admin" else "tenant-user"

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
        organization_id: UUID | None,
        account_id: UUID | None,
        grants_tenant_management: bool,
        grants_material_maintenance: bool,
        grants_expression_profile_maintenance: bool = False,
        *,
        entry_type: str | None = None,
        account_ids: tuple[UUID, ...] | None = None,
        maintenance_account_ids: tuple[UUID, ...] | None = None,
        grants_content_access: bool | None = None,
        grants_display_access: bool = False,
        display_store_ids: tuple[UUID, ...] = (),
    ) -> CreatedTenantUser:
        resolved_entry_type = entry_type or ("tenant_admin" if grants_tenant_management else "tenant_user")
        if resolved_entry_type not in {"tenant_admin", "tenant_user"}:
            raise DomainError("请选择租户管理员或租户用户入口")
        requested_content_access = account_id is not None if grants_content_access is None else grants_content_access
        requested_account_ids = tuple(
            dict.fromkeys(account_ids if account_ids is not None else ((account_id,) if account_id is not None else ()))
        )
        requested_maintenance_ids = tuple(
            dict.fromkeys(
                maintenance_account_ids
                if maintenance_account_ids is not None
                else (
                    requested_account_ids
                    if grants_expression_profile_maintenance
                    else ()
                )
            )
        )
        if not set(requested_maintenance_ids).issubset(
            set(requested_account_ids)
        ):
            raise DomainError("五段画像维护资格只能授予已获准使用的发布账号")
        if requested_content_access and not requested_account_ids:
            raise DomainError("内容创作资格至少需要一个发布账号")
        if not requested_content_access and requested_account_ids:
            raise DomainError("未开通内容创作时不能分配发布账号")
        if resolved_entry_type == "tenant_admin":
            if (
                requested_content_access
                or grants_display_access
                or grants_material_maintenance
                or grants_expression_profile_maintenance
                or requested_maintenance_ids
            ):
                raise DomainError("租户管理员与内容创作、陈列搭配资格不能同时开通")
            grants_tenant_management = True
        elif grants_tenant_management:
            raise DomainError("租户用户不能同时获得租户管理入口")
        if grants_expression_profile_maintenance and not requested_content_access:
            raise DomainError("维护账号定位前，需要先具备发布账号使用资格")
        requested_store_ids = tuple(dict.fromkeys(display_store_ids))
        if grants_display_access != bool(requested_store_ids):
            raise DomainError("陈列搭配资格必须明确选择至少一个正式门店档案")

        user_id = uuid4()
        activation_id = uuid4()
        raw_token, digest = self._token()
        with self._tenant_tx(manager.tenant_id) as cursor:
            cursor.execute(
                "SELECT organization_id FROM users WHERE tenant_id = %s AND id = %s AND enabled = true",
                (manager.tenant_id, manager.user_id),
            )
            manager_organization_id = self._one(cursor, "找不到当前租户管理员")["organization_id"]
            selected_organization_id = organization_id or UUID(str(manager_organization_id))
            cursor.execute(
                "SELECT id FROM organizations WHERE tenant_id = %s AND id = %s",
                (manager.tenant_id, selected_organization_id),
            )
            self._one(cursor, "只能授予当前租户的组织资格")
            cursor.execute(
                "INSERT INTO users "
                "(id, tenant_id, organization_id, display_name, entry_kind) "
                "VALUES (%s, %s, %s, %s, %s)",
                (
                    user_id,
                    manager.tenant_id,
                    selected_organization_id,
                    display_name,
                    resolved_entry_type,
                ),
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
            for requested_account_id in requested_account_ids:
                cursor.execute(
                    "SELECT id, control_organization_id FROM content_accounts "
                    "WHERE tenant_id = %s AND id = %s AND enabled = true "
                    "AND carrier_of_account_id IS NULL",
                    (manager.tenant_id, requested_account_id),
                )
                account = self._one(
                    cursor,
                    "只能授予当前租户已启用的企业发布账号",
                )
                if (
                    requested_account_id in requested_maintenance_ids
                    and (
                        account["control_organization_id"] is None
                        or UUID(str(account["control_organization_id"]))
                        != selected_organization_id
                    )
                ):
                    raise DomainError(
                        "只有账号负责团队的成员可以获得五段画像维护资格"
                    )
                cursor.execute(
                    "INSERT INTO auth_grants "
                    "(id, tenant_id, user_id, account_id, role_name, can_maintain_expression_profile) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (
                        uuid4(),
                        manager.tenant_id,
                        user_id,
                        requested_account_id,
                        "发布账号操作资格",
                        requested_account_id in requested_maintenance_ids,
                    ),
                )
                cursor.execute(
                    """
                    INSERT INTO auth_grants
                        (id, tenant_id, user_id, account_id, role_name, enabled,
                         can_maintain_expression_profile)
                    SELECT gen_random_uuid(), root_grant.tenant_id,
                           root_grant.user_id, carrier.id,
                           '平台版本载体兼容资格', true, false
                      FROM auth_grants root_grant
                      JOIN content_accounts carrier
                        ON carrier.tenant_id = root_grant.tenant_id
                       AND carrier.carrier_of_account_id = root_grant.account_id
                     WHERE root_grant.tenant_id = %s
                       AND root_grant.user_id = %s
                       AND root_grant.account_id = %s
                    ON CONFLICT (tenant_id, user_id, account_id) DO UPDATE
                    SET enabled = true,
                        role_name = EXCLUDED.role_name,
                        can_maintain_expression_profile = false
                    """,
                    (manager.tenant_id, user_id, requested_account_id),
                )
            if grants_tenant_management:
                cursor.execute(
                    "INSERT INTO tenant_management_grants (id, tenant_id, user_id) VALUES (%s, %s, %s)",
                    (uuid4(), manager.tenant_id, user_id),
                )
            if grants_material_maintenance:
                cursor.execute(
                    "INSERT INTO organization_material_maintainers (id, tenant_id, organization_id, user_id) "
                    "VALUES (%s, %s, %s, %s)",
                    (uuid4(), manager.tenant_id, selected_organization_id, user_id),
                )
            if grants_display_access:
                self._validate_display_stores(
                    cursor,
                    manager.tenant_id,
                    selected_organization_id,
                    requested_store_ids,
                )
                cursor.execute(
                    "INSERT INTO display_access_grants (id, tenant_id, user_id, enabled) VALUES (%s, %s, %s, true)",
                    (uuid4(), manager.tenant_id, user_id),
                )
                for store_id in requested_store_ids:
                    cursor.execute(
                        "INSERT INTO display_store_access_grants "
                        "(id, tenant_id, user_id, store_id, enabled) "
                        "VALUES (%s, %s, %s, %s, true)",
                        (uuid4(), manager.tenant_id, user_id, store_id),
                    )
            self._tenant_audit(cursor, manager.tenant_id, manager.user_id, "tenant_user.created", user_id)
        return {
            "user_id": str(user_id),
            "username": username,
            "activation_token": raw_token,
            "activation_id": str(activation_id),
            "entry_type": resolved_entry_type,
            "display_store_ids": [str(value) for value in requested_store_ids],
        }

    def create_reset_token(self, manager: TenantSession, user_id: UUID) -> str:
        raw_token, digest = self._token()
        with self._tenant_tx(manager.tenant_id) as cursor:
            cursor.execute(
                "SELECT id FROM users WHERE tenant_id = %s AND id = %s AND enabled = true FOR UPDATE",
                (manager.tenant_id, user_id),
            )
            self._one(cursor, "找不到当前租户可重置的自然人")
            cursor.execute(
                "UPDATE user_activation_tokens SET used_at = now() "
                "WHERE tenant_id = %s AND user_id = %s AND used_at IS NULL",
                (manager.tenant_id, user_id),
            )
            self._tenant_audit(
                cursor,
                manager.tenant_id,
                manager.user_id,
                "password.pending_links_invalidated_on_issue",
                user_id,
            )
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

    def invalidate_pending_activation_tokens(self, manager: TenantSession, user_id: UUID) -> int:
        """Invalidate a user's outstanding links without reading their token material."""
        with self._tenant_tx(manager.tenant_id) as cursor:
            cursor.execute(
                "SELECT id FROM users WHERE tenant_id = %s AND id = %s AND enabled = true FOR UPDATE",
                (manager.tenant_id, user_id),
            )
            self._one(cursor, "找不到当前租户可失效链接的自然人")
            cursor.execute(
                "UPDATE user_activation_tokens SET used_at = now() "
                "WHERE tenant_id = %s AND user_id = %s AND used_at IS NULL",
                (manager.tenant_id, user_id),
            )
            invalidated = cursor.rowcount
            self._tenant_audit(
                cursor,
                manager.tenant_id,
                manager.user_id,
                "password.pending_links_invalidated",
                user_id,
            )
        return invalidated

    def update_tenant_user(
        self,
        manager: TenantSession,
        user_id: UUID,
        display_name: str | None,
        organization_id: UUID | None,
    ) -> dict[str, str]:
        """Update the natural-person projection without changing any work grant."""
        normalized_name = display_name.strip() if display_name is not None else None
        if display_name is not None and not normalized_name:
            raise DomainError("姓名或工作名不能为空")
        if normalized_name is None and organization_id is None:
            raise DomainError("请至少修改姓名或所属组织")
        with self._tenant_tx(manager.tenant_id) as cursor:
            cursor.execute(
                "SELECT display_name, organization_id FROM users "
                "WHERE tenant_id = %s AND id = %s AND enabled = true FOR UPDATE",
                (manager.tenant_id, user_id),
            )
            current = self._one(cursor, "找不到当前租户可维护的成员")
            resolved_organization_id = (
                organization_id
                if organization_id is not None
                else UUID(str(current["organization_id"]))
            )
            cursor.execute(
                "SELECT id, name FROM organizations WHERE tenant_id = %s AND id = %s",
                (manager.tenant_id, resolved_organization_id),
            )
            organization = self._one(cursor, "只能选择当前租户已有的组织")
            cursor.execute(
                "UPDATE users SET display_name = %s, organization_id = %s "
                "WHERE tenant_id = %s AND id = %s",
                (
                    normalized_name or str(current["display_name"]),
                    resolved_organization_id,
                    manager.tenant_id,
                    user_id,
                ),
            )
            cursor.execute(
                """
                UPDATE auth_grants AS grant_record
                   SET can_maintain_expression_profile = false
                  FROM content_accounts AS account
                 WHERE grant_record.tenant_id = %s
                   AND grant_record.user_id = %s
                   AND grant_record.enabled = true
                   AND grant_record.can_maintain_expression_profile = true
                   AND account.tenant_id = grant_record.tenant_id
                   AND account.id = grant_record.account_id
                   AND (
                       account.carrier_of_account_id IS NOT NULL
                       OR account.control_organization_id IS DISTINCT FROM %s
                   )
                """,
                (
                    manager.tenant_id,
                    user_id,
                    resolved_organization_id,
                ),
            )
            cursor.execute(
                "UPDATE tenant_sessions SET revoked_at = now() "
                "WHERE tenant_id = %s AND user_id = %s AND revoked_at IS NULL",
                (manager.tenant_id, user_id),
            )
            self._tenant_audit(
                cursor,
                manager.tenant_id,
                manager.user_id,
                "tenant_user.identity_updated",
                user_id,
            )
        return {
            "user_id": str(user_id),
            "display_name": normalized_name or str(current["display_name"]),
            "organization_id": str(resolved_organization_id),
            "organization": str(organization["name"]),
        }

    def restore_tenant_user(self, manager: TenantSession, user_id: UUID) -> dict[str, str]:
        """Restore the login shell and issue a fresh activation link.

        Disabled work grants stay disabled. A manager must explicitly assign the
        current entry and work qualifications after restoration.
        """
        activation_id = uuid4()
        raw_token, digest = self._token()
        with self._tenant_tx(manager.tenant_id) as cursor:
            cursor.execute(
                "UPDATE users SET enabled = true "
                "WHERE tenant_id = %s AND id = %s AND enabled = false RETURNING id",
                (manager.tenant_id, user_id),
            )
            self._one(cursor, "找不到当前租户可恢复的成员")
            cursor.execute(
                "UPDATE user_activation_tokens SET used_at = now() "
                "WHERE tenant_id = %s AND user_id = %s AND used_at IS NULL",
                (manager.tenant_id, user_id),
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
            self._tenant_audit(
                cursor,
                manager.tenant_id,
                manager.user_id,
                "tenant_user.restored",
                user_id,
            )
        return {
            "user_id": str(user_id),
            "activation_token": raw_token,
            "activation_id": str(activation_id),
        }

    def disable_tenant_user(self, manager: TenantSession, user_id: UUID) -> None:
        """Disable a login and irreversibly invalidate all current authentication material."""
        if user_id == manager.user_id:
            raise DomainError("不能停用当前正在使用品牌管理的自己")
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
                "UPDATE display_access_grants SET enabled = false "
                "WHERE tenant_id = %s AND user_id = %s AND enabled = true",
                (manager.tenant_id, user_id),
            )
            cursor.execute(
                "UPDATE display_store_access_grants SET enabled = false "
                "WHERE tenant_id = %s AND user_id = %s AND enabled = true",
                (manager.tenant_id, user_id),
            )
            cursor.execute(
                "DELETE FROM organization_material_maintainers WHERE tenant_id = %s AND user_id = %s",
                (manager.tenant_id, user_id),
            )
            cursor.execute(
                "UPDATE user_activation_tokens SET used_at = now() "
                "WHERE tenant_id = %s AND user_id = %s AND used_at IS NULL",
                (manager.tenant_id, user_id),
            )
            cursor.execute(
                "UPDATE user_credentials SET password_hash = NULL, password_changed_at = now() "
                "WHERE tenant_id = %s AND user_id = %s",
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
                """
                UPDATE auth_grants AS grant_record
                   SET enabled = false,
                       can_maintain_expression_profile = false
                  FROM content_accounts AS account
                 WHERE grant_record.tenant_id = %s
                   AND grant_record.user_id = %s
                   AND grant_record.enabled = true
                   AND account.tenant_id = grant_record.tenant_id
                   AND account.id = grant_record.account_id
                   AND COALESCE(account.carrier_of_account_id, account.id) = %s
                RETURNING grant_record.id
                """,
                (manager.tenant_id, user_id, account_id),
            )
            self._one(cursor, "找不到当前租户可撤销的发布账号资格")
            cursor.execute(
                "UPDATE tenant_sessions SET revoked_at = now() "
                "WHERE tenant_id = %s AND user_id = %s AND revoked_at IS NULL",
                (manager.tenant_id, user_id),
            )
            self._tenant_audit(cursor, manager.tenant_id, manager.user_id, "publishing_account_grant.revoked", user_id)

    def update_tenant_user_grants(
        self,
        manager: TenantSession,
        user_id: UUID,
        account_id: UUID | None,
        grants_account_access: bool,
        grants_tenant_management: bool,
        grants_material_maintenance: bool,
        grants_expression_profile_maintenance: bool | None,
        *,
        entry_type: str | None = None,
        account_ids: tuple[UUID, ...] | None = None,
        maintenance_account_ids: tuple[UUID, ...] | None = None,
        grants_content_access: bool | None = None,
        grants_display_access: bool | None = None,
        display_store_ids: tuple[UUID, ...] | None = None,
    ) -> dict[str, object]:
        """Replace one member's mutually exclusive entry and root-account grants."""
        resolved_entry_type = entry_type or ("tenant_admin" if grants_tenant_management else "tenant_user")
        if resolved_entry_type not in {"tenant_admin", "tenant_user"}:
            raise DomainError("请选择租户管理员或租户用户入口")
        requested_content_access = grants_account_access if grants_content_access is None else grants_content_access
        requested_account_ids = tuple(
            dict.fromkeys(account_ids if account_ids is not None else ((account_id,) if account_id is not None else ()))
        )
        requested_maintenance_ids = (
            tuple(dict.fromkeys(maintenance_account_ids))
            if maintenance_account_ids is not None
            else None
        )
        if requested_maintenance_ids is not None and not set(
            requested_maintenance_ids
        ).issubset(set(requested_account_ids)):
            raise DomainError("五段画像维护资格只能授予已获准使用的发布账号")
        requested_display_access = bool(grants_display_access)
        requested_store_ids = tuple(dict.fromkeys(display_store_ids or ()))
        if requested_display_access != bool(requested_store_ids):
            raise DomainError("陈列搭配资格必须明确选择至少一个正式门店档案")
        if requested_content_access and not requested_account_ids:
            raise DomainError("内容创作资格至少需要一个发布账号")
        if not requested_content_access and requested_account_ids:
            raise DomainError("未开通内容创作时不能分配发布账号")
        if resolved_entry_type == "tenant_admin":
            if (
                requested_content_access
                or requested_display_access
                or grants_material_maintenance
                or bool(grants_expression_profile_maintenance)
                or bool(requested_maintenance_ids)
            ):
                raise DomainError("租户管理员与内容创作、陈列搭配资格不能同时开通")
            grants_tenant_management = True
        elif grants_tenant_management:
            raise DomainError("租户用户不能同时获得租户管理入口")
        if user_id == manager.user_id and resolved_entry_type != "tenant_admin":
            raise DomainError("不能在当前登录会话中撤销自己的品牌管理资格")
        if (
            grants_expression_profile_maintenance is True
            or bool(requested_maintenance_ids)
        ) and not requested_content_access:
            raise DomainError("维护账号定位前，需要先具备这个发布账号的使用资格")

        with self._tenant_tx(manager.tenant_id) as cursor:
            cursor.execute(
                "SELECT organization_id FROM users WHERE tenant_id = %s AND id = %s AND enabled = true FOR UPDATE",
                (manager.tenant_id, user_id),
            )
            target = self._one(cursor, "找不到当前租户可维护的成员")
            organization_id = UUID(str(target["organization_id"]))
            cursor.execute(
                """
                SELECT grant_record.account_id, grant_record.enabled,
                       grant_record.can_maintain_expression_profile
                  FROM auth_grants grant_record
                  JOIN content_accounts account
                    ON account.tenant_id = grant_record.tenant_id
                   AND account.id = grant_record.account_id
                   AND account.carrier_of_account_id IS NULL
                 WHERE grant_record.tenant_id = %s
                   AND grant_record.user_id = %s
                """,
                (manager.tenant_id, user_id),
            )
            previous_grants = {
                UUID(str(row["account_id"])): {
                    "enabled": bool(row["enabled"]),
                    "maintenance": bool(
                        row["can_maintain_expression_profile"]
                    ),
                }
                for row in cursor.fetchall()
            }

            for requested_account_id in requested_account_ids:
                cursor.execute(
                    "SELECT id, enabled, control_organization_id FROM content_accounts "
                    "WHERE tenant_id = %s AND id = %s "
                    "AND carrier_of_account_id IS NULL",
                    (manager.tenant_id, requested_account_id),
                )
                account = self._one(
                    cursor,
                    "只能维护当前租户的表达账号资格",
                )
                previous = previous_grants.get(requested_account_id)
                if not bool(account["enabled"]) and not (
                    previous and bool(previous["enabled"])
                ):
                    raise DomainError(
                        "已停用的发布账号不能新增给成员使用"
                    )
                should_maintain = (
                    requested_account_id in requested_maintenance_ids
                    if requested_maintenance_ids is not None
                    else (
                        grants_expression_profile_maintenance
                        if grants_expression_profile_maintenance is not None
                        else bool(
                            previous_grants.get(
                                requested_account_id,
                                {},
                            ).get("maintenance", False)
                        )
                    )
                )
                if should_maintain and (
                    account["control_organization_id"] is None
                    or UUID(str(account["control_organization_id"]))
                    != organization_id
                ):
                    raise DomainError(
                        "只有账号负责团队的成员可以获得五段画像维护资格"
                    )

            cursor.execute(
                "UPDATE users SET entry_kind = %s WHERE tenant_id = %s AND id = %s",
                (resolved_entry_type, manager.tenant_id, user_id),
            )
            cursor.execute(
                """
                UPDATE auth_grants
                   SET enabled = false,
                       can_maintain_expression_profile = false
                 WHERE tenant_id = %s
                   AND user_id = %s
                   AND (enabled = true OR can_maintain_expression_profile = true)
                """,
                (manager.tenant_id, user_id),
            )

            if resolved_entry_type == "tenant_user":
                for requested_account_id in requested_account_ids:
                    resolved_maintenance = (
                        requested_account_id in requested_maintenance_ids
                        if requested_maintenance_ids is not None
                        else (
                            grants_expression_profile_maintenance
                            if grants_expression_profile_maintenance
                            is not None
                            else bool(
                                previous_grants.get(
                                    requested_account_id,
                                    {},
                                ).get("maintenance", False)
                            )
                        )
                    )
                    cursor.execute(
                        """
                        INSERT INTO auth_grants
                            (id, tenant_id, user_id, account_id, role_name, enabled,
                             can_maintain_expression_profile)
                        VALUES (%s, %s, %s, %s, '发布账号操作资格', true, %s)
                        ON CONFLICT (tenant_id, user_id, account_id) DO UPDATE
                        SET enabled = true,
                            can_maintain_expression_profile =
                                EXCLUDED.can_maintain_expression_profile
                        """,
                        (
                            uuid4(),
                            manager.tenant_id,
                            user_id,
                            requested_account_id,
                            resolved_maintenance,
                        ),
                    )
                    cursor.execute(
                        """
                        INSERT INTO auth_grants
                            (id, tenant_id, user_id, account_id, role_name,
                             enabled, can_maintain_expression_profile)
                        SELECT gen_random_uuid(), root_grant.tenant_id,
                               root_grant.user_id, carrier.id,
                               '平台版本载体兼容资格', true, false
                          FROM auth_grants root_grant
                          JOIN content_accounts carrier
                            ON carrier.tenant_id = root_grant.tenant_id
                           AND carrier.carrier_of_account_id = root_grant.account_id
                         WHERE root_grant.tenant_id = %s
                           AND root_grant.user_id = %s
                           AND root_grant.account_id = %s
                        ON CONFLICT (tenant_id, user_id, account_id) DO UPDATE
                        SET enabled = true,
                            role_name = EXCLUDED.role_name,
                            can_maintain_expression_profile = false
                        """,
                        (manager.tenant_id, user_id, requested_account_id),
                    )

            cursor.execute(
                """
                INSERT INTO tenant_management_grants
                    (id, tenant_id, user_id, enabled)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (tenant_id, user_id) DO UPDATE
                SET enabled = EXCLUDED.enabled
                """,
                (
                    uuid4(),
                    manager.tenant_id,
                    user_id,
                    resolved_entry_type == "tenant_admin",
                ),
            )

            if resolved_entry_type == "tenant_user" and requested_display_access:
                self._validate_display_stores(
                    cursor,
                    manager.tenant_id,
                    organization_id,
                    requested_store_ids,
                )
                cursor.execute(
                    """
                    INSERT INTO display_access_grants
                        (id, tenant_id, user_id, enabled)
                    VALUES (%s, %s, %s, true)
                    ON CONFLICT (tenant_id, user_id) DO UPDATE
                    SET enabled = EXCLUDED.enabled
                    """,
                    (
                        uuid4(),
                        manager.tenant_id,
                        user_id,
                    ),
                )
                cursor.execute(
                    "UPDATE display_store_access_grants SET enabled = false "
                    "WHERE tenant_id = %s AND user_id = %s AND enabled = true",
                    (manager.tenant_id, user_id),
                )
                for store_id in requested_store_ids:
                    cursor.execute(
                        """
                        INSERT INTO display_store_access_grants
                            (id, tenant_id, user_id, store_id, enabled)
                        VALUES (%s, %s, %s, %s, true)
                        ON CONFLICT (tenant_id, user_id, store_id) DO UPDATE
                        SET enabled = true
                        """,
                        (uuid4(), manager.tenant_id, user_id, store_id),
                    )
            else:
                cursor.execute(
                    "UPDATE display_access_grants SET enabled = false "
                    "WHERE tenant_id = %s AND user_id = %s AND enabled = true",
                    (manager.tenant_id, user_id),
                )
                cursor.execute(
                    "UPDATE display_store_access_grants SET enabled = false "
                    "WHERE tenant_id = %s AND user_id = %s AND enabled = true",
                    (manager.tenant_id, user_id),
                )

            if resolved_entry_type == "tenant_user" and grants_material_maintenance:
                cursor.execute(
                    """
                    INSERT INTO organization_material_maintainers
                        (id, tenant_id, organization_id, user_id)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (tenant_id, organization_id, user_id) DO NOTHING
                    """,
                    (uuid4(), manager.tenant_id, organization_id, user_id),
                )
            else:
                cursor.execute(
                    "DELETE FROM organization_material_maintainers "
                    "WHERE tenant_id = %s AND organization_id = %s AND user_id = %s",
                    (manager.tenant_id, organization_id, user_id),
                )

            cursor.execute(
                "UPDATE tenant_sessions SET revoked_at = now() "
                "WHERE tenant_id = %s AND user_id = %s AND revoked_at IS NULL",
                (manager.tenant_id, user_id),
            )
            self._tenant_audit(
                cursor,
                manager.tenant_id,
                manager.user_id,
                "tenant_user.grants_updated",
                user_id,
            )
        maintenance_result: bool | dict[str, bool]
        if (
            requested_maintenance_ids is None
            and grants_expression_profile_maintenance is not None
        ):
            maintenance_result = grants_expression_profile_maintenance
        else:
            maintenance_result = {
                str(account_id): (
                    account_id in requested_maintenance_ids
                    if requested_maintenance_ids is not None
                    else bool(
                        previous_grants.get(account_id, {}).get(
                            "maintenance",
                            False,
                        )
                    )
                )
                for account_id in requested_account_ids
            }
        return {
            "entry_type": resolved_entry_type,
            "account_access": requested_content_access,
            "account_ids": [str(value) for value in requested_account_ids],
            "tenant_management": resolved_entry_type == "tenant_admin",
            "display_access": requested_display_access,
            "display_store_ids": [str(value) for value in requested_store_ids],
            "material_maintenance": grants_material_maintenance,
            "expression_profile_maintenance": maintenance_result,
        }

    @classmethod
    def _validate_display_stores(
        cls,
        cursor: psycopg.Cursor[dict[str, object]],
        tenant_id: UUID,
        organization_id: UUID,
        store_ids: tuple[UUID, ...],
    ) -> None:
        cursor.execute(
            """
            SELECT id
              FROM display_stores
             WHERE tenant_id = %s
               AND id = ANY(%s)
               AND execution_organization_id = %s
               AND enabled = true
               AND business_data_kind = 'formal_business_data'
               AND current_profile_version_id IS NOT NULL
            """,
            (tenant_id, list(store_ids), organization_id),
        )
        found = {UUID(str(row["id"])) for row in cursor.fetchall()}
        if found != set(store_ids):
            raise DomainError("只能选择成员所属组织当前已确认的正式门店档案")

    def set_account_profile_maintenance(
        self,
        manager: TenantSession,
        user_id: UUID,
        account_id: UUID,
        enabled: bool,
    ) -> dict[str, object]:
        """Change one account's profile-maintenance grant and nothing else."""
        with self._tenant_tx(manager.tenant_id) as cursor:
            cursor.execute(
                """
                SELECT grant_record.id,
                       person.organization_id AS person_organization_id,
                       account.control_organization_id
                  FROM auth_grants AS grant_record
                  JOIN users AS person
                    ON person.tenant_id = grant_record.tenant_id
                   AND person.id = grant_record.user_id
                   AND person.enabled = true
                   AND person.entry_kind = 'tenant_user'
                  JOIN content_accounts AS account
                    ON account.tenant_id = grant_record.tenant_id
                   AND account.id = grant_record.account_id
                   AND account.enabled = true
                   AND account.carrier_of_account_id IS NULL
                 WHERE grant_record.tenant_id = %s
                   AND grant_record.user_id = %s
                   AND grant_record.account_id = %s
                   AND grant_record.enabled = true
                 FOR UPDATE
                """,
                (manager.tenant_id, user_id, account_id),
            )
            grant = self._one(
                cursor,
                "需要先为该成员分配这个发布账号的使用资格",
            )
            if enabled and (
                grant["control_organization_id"] is None
                or UUID(str(grant["control_organization_id"]))
                != UUID(str(grant["person_organization_id"]))
            ):
                raise DomainError("只有账号负责团队的成员可以获得五段画像维护资格")
            cursor.execute(
                "UPDATE auth_grants SET can_maintain_expression_profile = %s "
                "WHERE tenant_id = %s AND id = %s",
                (enabled, manager.tenant_id, grant["id"]),
            )
            cursor.execute(
                "UPDATE tenant_sessions SET revoked_at = now() "
                "WHERE tenant_id = %s AND user_id = %s AND revoked_at IS NULL",
                (manager.tenant_id, user_id),
            )
            self._tenant_audit(
                cursor,
                manager.tenant_id,
                manager.user_id,
                "publishing_account_grant.profile_maintenance_updated",
                user_id,
            )
        return {
            "user_id": str(user_id),
            "account_id": str(account_id),
            "can_maintain_expression_profile": enabled,
        }

    def tenant_organizations(self, manager: TenantSession) -> list[dict[str, object]]:
        """Return only the manager's tenant organizations for qualification assignment."""
        with self._tenant_tx(manager.tenant_id) as cursor:
            cursor.execute(
                """
                SELECT organization.id, organization.name,
                       organization.business_data_kind,
                       organization.organization_level,
                       organization.parent_organization_id,
                       parent.name AS parent_organization
                FROM organizations organization
                LEFT JOIN organizations parent
                  ON parent.tenant_id = organization.tenant_id
                 AND parent.id = organization.parent_organization_id
                WHERE organization.tenant_id = %s
                  AND organization.business_data_kind = 'formal_business_data'
                ORDER BY organization.name
                """,
                (manager.tenant_id,),
            )
            return [
                {
                    "id": str(row["id"]),
                    "name": str(row["name"]),
                    "business_data_kind": str(row["business_data_kind"]),
                    "organization_level": str(row["organization_level"]),
                    "parent_organization_id": (
                        str(row["parent_organization_id"])
                        if row["parent_organization_id"] is not None
                        else None
                    ),
                    "parent_organization": (
                        str(row["parent_organization"])
                        if row["parent_organization"] is not None
                        else None
                    ),
                }
                for row in cursor.fetchall()
            ]

    def create_tenant_organization(
        self,
        manager: TenantSession,
        name: str,
        as_synthetic_business_fixture: bool = False,
        organization_level: str = "unspecified",
        parent_organization_id: UUID | None = None,
    ) -> dict[str, object]:
        organization_id = uuid4()
        normalized_name = name.strip()
        if not normalized_name:
            raise DomainError("请填写真实组织名称")
        if organization_level not in {
            "company",
            "region",
            "operating_unit",
            "unspecified",
        }:
            raise DomainError("请选择公司、区域、经营单元或暂未指定")
        business_data_kind = "synthetic_business_fixture" if as_synthetic_business_fixture else "formal_business_data"
        with self._tenant_tx(manager.tenant_id) as cursor:
            parent_name: str | None = None
            if parent_organization_id is not None:
                cursor.execute(
                    """
                    SELECT name, organization_level
                    FROM organizations
                    WHERE tenant_id = %s AND id = %s
                    """,
                    (manager.tenant_id, parent_organization_id),
                )
                parent = self._one(cursor, "上级组织必须来自当前租户")
                parent_name = str(parent["name"])
                parent_level = str(parent["organization_level"])
                if organization_level == "region" and parent_level != "company":
                    raise DomainError("区域的上级组织必须是明确登记的公司级组织")
                if (
                    organization_level == "operating_unit"
                    and parent_level not in {"company", "region"}
                ):
                    raise DomainError("经营单元的上级组织必须是公司或区域")
            try:
                cursor.execute(
                    """
                    INSERT INTO organizations
                        (id, tenant_id, name, business_data_kind,
                         organization_level, parent_organization_id)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id, name, business_data_kind,
                              organization_level, parent_organization_id
                    """,
                    (
                        organization_id,
                        manager.tenant_id,
                        normalized_name,
                        business_data_kind,
                        organization_level,
                        parent_organization_id,
                    ),
                )
                row = self._one(cursor, "组织创建失败")
            except psycopg.errors.UniqueViolation as exc:
                raise DomainError("当前租户已有同名组织") from exc
            self._tenant_audit(
                cursor,
                manager.tenant_id,
                manager.user_id,
                "organization.created",
                organization_id,
            )
        return {
            "id": str(row["id"]),
            "name": str(row["name"]),
            "business_data_kind": str(row["business_data_kind"]),
            "organization_level": str(row["organization_level"]),
            "parent_organization_id": (
                str(row["parent_organization_id"])
                if row["parent_organization_id"] is not None
                else None
            ),
            "parent_organization": parent_name,
        }

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
                "UPDATE users SET entry_kind = 'tenant_admin' WHERE tenant_id = %s AND id = %s",
                (tenant_id, user_id),
            )
            cursor.execute(
                "UPDATE auth_grants SET enabled = false, "
                "can_maintain_expression_profile = false "
                "WHERE tenant_id = %s AND user_id = %s",
                (tenant_id, user_id),
            )
            cursor.execute(
                "UPDATE display_access_grants SET enabled = false WHERE tenant_id = %s AND user_id = %s",
                (tenant_id, user_id),
            )
            cursor.execute(
                "UPDATE tenant_sessions SET revoked_at = now() "
                "WHERE tenant_id = %s AND user_id = %s AND revoked_at IS NULL",
                (tenant_id, user_id),
            )
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
        tenant_name = tenant_name.strip()
        administrator_name = administrator_name.strip()
        username = username.strip()
        if not 2 <= len(tenant_name) <= 120 or not 1 <= len(administrator_name) <= 80 or not 3 <= len(username) <= 80:
            raise DomainError("租户名称、首位管理员工作名或用户名不符合开户要求")
        (
            tenant_id,
            organization_id,
            user_id,
            credential_id,
            activation_id,
            brand_id,
            baseline_id,
            audience_id,
        ) = (uuid4() for _ in range(8))
        raw_token, digest = self._token()
        brand_draft = (
            _DIYU_FASHION_BRAND_DRAFT
            if tenant_name.startswith(_DIYU_FASHION_TENANT_NAME)
            else _GENERIC_BRAND_DRAFT_TEMPLATE.format(tenant_name=tenant_name)
        )
        with self._tx() as cursor:
            try:
                cursor.execute(
                    "SELECT * FROM ops_provision_tenant("
                    "%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                    "%s, %s, %s, %s, %s, %s, %s, %s)",
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
                        brand_id,
                        baseline_id,
                        audience_id,
                        brand_draft,
                        _DRAFT_POSITIONING,
                        _DRAFT_DECISION_ORDER,
                        _DRAFT_TONE,
                        _DRAFT_AUDIENCE,
                    ),
                )
                provisioned = self._one(cursor, "租户开户没有返回完整结果")
            except psycopg.errors.UniqueViolation as exc:
                raise DomainError("租户名称或管理员用户名已被其他身份使用") from exc
            cursor.execute(
                "INSERT INTO ops_audit_events (id, operator_id, event_type, tenant_id) VALUES (%s, %s, %s, %s)",
                (
                    uuid4(),
                    operator.operator_id,
                    "tenant.provisioned",
                    UUID(str(provisioned["tenant_id"])),
                ),
            )
            provisioned_tenant_id = UUID(str(provisioned["tenant_id"]))
            provisioned_user_id = UUID(str(provisioned["user_id"]))
            cursor.execute(
                "SELECT set_config('app.tenant_id', %s, true)",
                (str(provisioned_tenant_id),),
            )
            cursor.execute(
                "UPDATE organizations SET organization_level = 'company' "
                "WHERE tenant_id = %s AND id = ("
                "SELECT organization_id FROM users "
                "WHERE tenant_id = %s AND id = %s)",
                (
                    provisioned_tenant_id,
                    provisioned_tenant_id,
                    provisioned_user_id,
                ),
            )
            cursor.execute(
                "UPDATE users SET entry_kind = 'tenant_admin' WHERE tenant_id = %s AND id = %s",
                (provisioned_tenant_id, provisioned_user_id),
            )
            cursor.execute(
                "UPDATE auth_grants SET enabled = false, "
                "can_maintain_expression_profile = false "
                "WHERE tenant_id = %s AND user_id = %s",
                (provisioned_tenant_id, provisioned_user_id),
            )
            cursor.execute(
                "UPDATE display_access_grants SET enabled = false WHERE tenant_id = %s AND user_id = %s",
                (provisioned_tenant_id, provisioned_user_id),
            )
        return {
            "tenant_id": str(provisioned["tenant_id"]),
            "administrator_id": str(provisioned["user_id"]),
            "brand_id": str(provisioned["brand_id"]),
            "username": str(provisioned["username"]),
            "activation_token": raw_token,
        }

    def set_tenant_enabled(self, operator: OpsSession, tenant_id: UUID, enabled: bool) -> None:
        with self._tx() as cursor:
            cursor.execute("SELECT ops_set_tenant_enabled(%s, %s)", (tenant_id, enabled))
            cursor.execute(
                "INSERT INTO ops_audit_events (id, operator_id, event_type, tenant_id) VALUES (%s, %s, %s, %s)",
                (uuid4(), operator.operator_id, "tenant.enabled" if enabled else "tenant.disabled", tenant_id),
            )

    def list_tenants(self, operator: OpsSession) -> list[dict[str, object]]:
        """Return the minimum operations registry projection, never tenant content."""
        del operator
        with self._tx() as cursor:
            cursor.execute(
                """
                SELECT tenant_id, tenant_name, enabled, created_at, disabled_at
                FROM ops_list_tenants()
                """
            )
            rows = cursor.fetchall()
        return [
            {
                "tenant_id": str(row["tenant_id"]),
                "tenant_name": str(row["tenant_name"]),
                "enabled": bool(row["enabled"]),
                "created_at": (
                    row["created_at"].isoformat() if isinstance(row["created_at"], datetime) else str(row["created_at"])
                ),
                "disabled_at": (row["disabled_at"].isoformat() if isinstance(row["disabled_at"], datetime) else None),
            }
            for row in rows
        ]

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

    @staticmethod
    def _targets_for_channel(channel: str) -> tuple[str, ...]:
        return {
            "抖音": ("douyin_video",),
            "小红书": ("xiaohongshu_graphic", "xiaohongshu_video"),
            "微信视频号": ("wechat_channels_video",),
        }.get(channel, ())

    @staticmethod
    def _target_channel(target: str) -> str:
        channel = {
            "douyin_video": "抖音",
            "xiaohongshu_graphic": "小红书",
            "xiaohongshu_video": "小红书",
            "wechat_channels_video": "微信视频号",
        }.get(target)
        if channel is None:
            raise DomainError("请选择当前发布账号已经开通的平台与内容形式")
        return channel

    @staticmethod
    def _publishing_identity_rows(
        cursor: psycopg.Cursor[dict[str, object]],
        identity: TenantSession,
    ) -> list[dict[str, object]]:
        cursor.execute(
            """
            SELECT DISTINCT
                   root.id,
                   root.brand_id,
                   root.name,
                   root.channel,
                   root.platform_enabled,
                   root.control_organization_id,
                   control_organization.name AS control_organization_name,
                   role_record.name AS content_role_name,
                   grant_record.can_maintain_expression_profile,
                   profile.id AS profile_id,
                   profile.version AS profile_version,
                   profile.identity_position
              FROM users AS user_record
              JOIN auth_grants AS grant_record
                ON grant_record.tenant_id = user_record.tenant_id
               AND grant_record.user_id = user_record.id
               AND grant_record.enabled = true
              JOIN content_accounts AS root
                ON root.tenant_id = grant_record.tenant_id
               AND root.id = grant_record.account_id
               AND root.enabled = true
               AND root.carrier_of_account_id IS NULL
               AND root.business_data_kind = user_record.business_data_kind
              LEFT JOIN account_content_roles AS account_role
                ON account_role.tenant_id = root.tenant_id
               AND account_role.account_id = root.id
              LEFT JOIN content_roles AS role_record
                ON role_record.tenant_id = account_role.tenant_id
               AND role_record.id = account_role.content_role_id
              LEFT JOIN account_expression_profile_versions AS profile
                ON profile.tenant_id = root.tenant_id
               AND profile.account_id = root.id
               AND profile.id = root.current_expression_profile_id
              LEFT JOIN organizations AS control_organization
                ON control_organization.tenant_id = root.tenant_id
               AND control_organization.id = root.control_organization_id
             WHERE user_record.tenant_id = %s
               AND user_record.id = %s
               AND user_record.enabled = true
               AND user_record.entry_kind = 'tenant_user'
               AND user_record.business_data_kind <> 'legacy_hidden'
               AND NOT EXISTS (
                   SELECT 1
                     FROM tenant_management_grants AS management_grant
                    WHERE management_grant.tenant_id = user_record.tenant_id
                      AND management_grant.user_id = user_record.id
                      AND management_grant.enabled = true
               )
             ORDER BY root.name, root.id
            """,
            (identity.tenant_id, identity.user_id),
        )
        return list(cursor.fetchall())

    def list_publishing_identities(
        self,
        identity: TenantSession,
    ) -> list[dict[str, object]]:
        """Return logical publishing identities; physical carriers are target details only."""
        if identity.audience != "tenant-user":
            raise DomainError("这个登录账号不能进入内容创作")
        with self._tenant_tx(identity.tenant_id) as cursor:
            roots = self._publishing_identity_rows(cursor, identity)
            result: list[dict[str, object]] = []
            for root in roots:
                root_id = UUID(str(root["id"]))
                cursor.execute(
                    """
                    SELECT id, channel
                      FROM content_accounts
                     WHERE tenant_id = %s
                       AND enabled = true
                       AND platform_enabled = true
                       AND (id = %s OR carrier_of_account_id = %s)
                     ORDER BY CASE channel
                         WHEN '抖音' THEN 1
                         WHEN '小红书' THEN 2
                         WHEN '微信视频号' THEN 3
                         ELSE 4 END,
                         id
                    """,
                    (identity.tenant_id, root_id, root_id),
                )
                platform_targets: list[dict[str, str]] = []
                seen_targets: set[str] = set()
                for account in cursor.fetchall():
                    for target in self._targets_for_channel(str(account["channel"])):
                        if target in seen_targets:
                            continue
                        seen_targets.add(target)
                        platform_targets.append(
                            {
                                "value": target,
                                "platform": str(account["channel"]),
                                "media_format": ("graphic" if target == "xiaohongshu_graphic" else "video"),
                                "carrier_id": str(account["id"]),
                            }
                        )
                result.append(
                    {
                        "id": str(root_id),
                        "name": str(root["name"]),
                        "brand_id": str(root["brand_id"]),
                        "control_organization_id": (
                            str(root["control_organization_id"])
                            if root["control_organization_id"] is not None
                            else None
                        ),
                        "control_organization": (
                            str(root["control_organization_name"])
                            if root["control_organization_name"] is not None
                            else None
                        ),
                        "content_role": str(root["content_role_name"] or ""),
                        "can_maintain_expression_profile": bool(
                            root["can_maintain_expression_profile"]
                        ),
                        "profile_id": (
                            str(root["profile_id"])
                            if root["profile_id"] is not None
                            else None
                        ),
                        "profile_version": (
                            int(str(root["profile_version"]))
                            if root["profile_version"] is not None
                            else None
                        ),
                        "profile_summary": str(root["identity_position"] or ""),
                        "platform_targets": platform_targets,
                    }
                )
        return result

    def content_scope(
        self,
        identity: TenantSession,
        target: str | None = None,
        publishing_identity_id: UUID | None = None,
    ) -> TrustedScope:
        if identity.audience != "tenant-user":
            raise DomainError("这个登录账号不能进入内容创作")
        with self._tenant_tx(identity.tenant_id) as cursor:
            roots = self._publishing_identity_rows(cursor, identity)
            if publishing_identity_id is not None:
                roots = [root for root in roots if UUID(str(root["id"])) == publishing_identity_id]
                if not roots:
                    raise DomainError("当前登录账号没有获准操作这个发布账号")
            if not roots:
                raise DomainError("当前登录账号还没有可使用的发布账号")
            if len(roots) > 1:
                raise DomainError("请先选择这次要使用的发布账号")
            root = roots[0]
            root_id = UUID(str(root["id"]))
            resolved_target = target
            if resolved_target is None:
                cursor.execute(
                    """
                    SELECT channel
                      FROM content_accounts
                     WHERE tenant_id = %s
                       AND enabled = true
                       AND platform_enabled = true
                       AND (id = %s OR carrier_of_account_id = %s)
                     ORDER BY CASE channel
                         WHEN '抖音' THEN 1
                         WHEN '小红书' THEN 2
                         WHEN '微信视频号' THEN 3
                         ELSE 4 END,
                         id
                    """,
                    (identity.tenant_id, root_id, root_id),
                )
                target_row = self._one(
                    cursor,
                    "当前发布账号还没有可使用的平台载体",
                )
                channel_targets = self._targets_for_channel(str(target_row["channel"]))
                if not channel_targets:
                    raise DomainError("当前发布账号还没有可使用的平台载体")
                resolved_target = channel_targets[0]
            target_channel = self._target_channel(resolved_target)
            if str(root["channel"]) == target_channel:
                if not bool(root["platform_enabled"]):
                    raise DomainError(
                        "当前表达身份没有明确配置这个平台的发布载体"
                    )
                row = {
                    "account_id": root["id"],
                    "brand_id": root["brand_id"],
                }
            else:
                cursor.execute(
                    """
                    SELECT carrier.id AS account_id, carrier.brand_id, carrier.channel
                    FROM content_accounts carrier
                    WHERE carrier.tenant_id = %s
                      AND carrier.carrier_of_account_id = %s
                      AND carrier.channel = %s
                      AND carrier.enabled = true
                      AND carrier.platform_enabled = true
                    """,
                    (
                        identity.tenant_id,
                        root_id,
                        target_channel,
                    ),
                )
                carriers = cursor.fetchall()
                if len(carriers) != 1:
                    raise DomainError("当前表达身份没有明确配置这个平台的发布载体")
                row = carriers[0]
        return TrustedScope(
            identity.tenant_id, identity.user_id, UUID(str(row["brand_id"])), UUID(str(row["account_id"]))
        )

    def allowed_content_targets(
        self,
        identity: TenantSession,
        publishing_identity_id: UUID | None = None,
    ) -> tuple[str, ...]:
        identities = self.list_publishing_identities(identity)
        if publishing_identity_id is not None:
            identities = [item for item in identities if UUID(str(item["id"])) == publishing_identity_id]
        if len(identities) != 1:
            return ()
        platform_targets = identities[0].get("platform_targets")
        if not isinstance(platform_targets, list):
            return ()
        return tuple(str(item["value"]) for item in platform_targets if isinstance(item, dict) and "value" in item)

    def display_stores(self, identity: TenantSession) -> list[dict[str, str]]:
        if identity.audience != "tenant-user":
            raise DomainError("这个登录账号不能进入陈列搭配")
        with self._tenant_tx(identity.tenant_id) as cursor:
            cursor.execute(
                """
                SELECT store.id, store.name, store.brand_id,
                       store.execution_organization_id AS organization_id
                FROM users user_record
                JOIN display_access_grants display_grant
                  ON display_grant.tenant_id = user_record.tenant_id
                 AND display_grant.user_id = user_record.id
                 AND display_grant.enabled = true
                JOIN display_store_access_grants store_grant
                  ON store_grant.tenant_id = user_record.tenant_id
                 AND store_grant.user_id = user_record.id
                 AND store_grant.enabled = true
                JOIN display_stores store
                  ON store.tenant_id = store_grant.tenant_id
                 AND store.id = store_grant.store_id
                 AND store.execution_organization_id = user_record.organization_id
                 AND store.enabled = true
                 AND store.business_data_kind = user_record.business_data_kind
                WHERE user_record.tenant_id = %s AND user_record.id = %s AND user_record.enabled = true
                  AND user_record.entry_kind = 'tenant_user'
                  AND user_record.business_data_kind <> 'legacy_hidden'
                  AND NOT EXISTS (
                      SELECT 1
                        FROM tenant_management_grants AS management_grant
                       WHERE management_grant.tenant_id = user_record.tenant_id
                         AND management_grant.user_id = user_record.id
                         AND management_grant.enabled = true
                  )
                ORDER BY store.name
                """,
                (identity.tenant_id, identity.user_id),
            )
            rows = cursor.fetchall()
        return [
            {
                "id": str(row["id"]),
                "name": str(row["name"]),
                "brand_id": str(row["brand_id"]),
                "organization_id": str(row["organization_id"]),
            }
            for row in rows
        ]

    def material_maintenance_scope(
        self,
        identity: TenantSession,
    ) -> MaterialMaintenanceScope:
        """Resolve an independent organization-material grant without a content account."""
        if identity.audience != "tenant-user":
            raise DomainError("这个登录账号不能维护组织官方素材")
        with self._tenant_tx(identity.tenant_id) as cursor:
            cursor.execute(
                """
                SELECT DISTINCT user_record.organization_id, brand.id AS brand_id
                  FROM users user_record
                  JOIN organization_material_maintainers maintainer
                    ON maintainer.tenant_id = user_record.tenant_id
                   AND maintainer.user_id = user_record.id
                   AND maintainer.organization_id = user_record.organization_id
                  JOIN organizations organization
                    ON organization.tenant_id = user_record.tenant_id
                   AND organization.id = user_record.organization_id
                   AND organization.business_data_kind = user_record.business_data_kind
                   AND organization.business_data_kind = 'formal_business_data'
                  JOIN brands brand ON brand.tenant_id = user_record.tenant_id
                  JOIN brand_expression_baselines baseline
                    ON baseline.tenant_id = brand.tenant_id
                   AND baseline.brand_id = brand.id
                 WHERE user_record.tenant_id = %s
                   AND user_record.id = %s
                   AND user_record.enabled = true
                   AND user_record.entry_kind = 'tenant_user'
                   AND user_record.business_data_kind <> 'legacy_hidden'
                   AND NOT EXISTS (
                       SELECT 1
                         FROM tenant_management_grants management_grant
                        WHERE management_grant.tenant_id = user_record.tenant_id
                          AND management_grant.user_id = user_record.id
                          AND management_grant.enabled = true
                   )
                 ORDER BY brand.id
                """,
                (identity.tenant_id, identity.user_id),
            )
            rows = cursor.fetchall()
        if len(rows) != 1:
            raise DomainError("当前账号没有唯一、有效的组织官方素材维护范围")
        row = rows[0]
        return MaterialMaintenanceScope(
            identity.tenant_id,
            identity.user_id,
            UUID(str(row["brand_id"])),
            UUID(str(row["organization_id"])),
        )

    def tenant_user_identity(self, identity: TenantSession) -> dict[str, str]:
        if identity.audience != "tenant-user":
            raise DomainError("这个登录账号不能进入租户用户入口")
        with self._tenant_tx(identity.tenant_id) as cursor:
            cursor.execute(
                """
                SELECT user_record.id AS operator_id,
                       user_record.display_name AS operator,
                       organization.name AS organization
                  FROM users user_record
                  JOIN organizations organization
                    ON organization.tenant_id = user_record.tenant_id
                   AND organization.id = user_record.organization_id
                   AND organization.business_data_kind = user_record.business_data_kind
                 WHERE user_record.tenant_id = %s
                   AND user_record.id = %s
                   AND user_record.enabled = true
                   AND user_record.entry_kind = 'tenant_user'
                   AND user_record.business_data_kind <> 'legacy_hidden'
                """,
                (identity.tenant_id, identity.user_id),
            )
            row = self._one(cursor, "当前租户用户已经停用或不可见")
        return {
            "operator_id": str(row["operator_id"]),
            "operator": str(row["operator"]),
            "organization": str(row["organization"]),
        }

    def display_scope(
        self,
        identity: TenantSession,
        store_id: UUID | None = None,
    ) -> DisplayScope:
        stores = self.display_stores(identity)
        selected = (
            [row for row in stores if UUID(row["id"]) == store_id]
            if store_id is not None
            else stores
        )
        if not selected:
            raise DomainError("当前登录账号没有获准使用的门店档案")
        if len(selected) != 1:
            raise DomainError("请选择本次要使用的门店档案")
        row = selected[0]
        return DisplayScope(
            identity.tenant_id,
            identity.user_id,
            UUID(row["brand_id"]),
            UUID(row["organization_id"]),
            actor_organization_id=UUID(row["organization_id"]),
            store_id=UUID(row["id"]),
        )

    def manager_scope(self, identity: TenantSession) -> TenantManagementScope:
        if identity.audience != "tenant-admin":
            raise DomainError("这个登录账号不能进入品牌管理")
        with self._tenant_tx(identity.tenant_id) as cursor:
            cursor.execute(
                """
                SELECT DISTINCT brand.id AS brand_id
                FROM users user_record
                JOIN tenant_management_grants management_grant
                  ON management_grant.tenant_id = user_record.tenant_id
                 AND management_grant.user_id = user_record.id
                 AND management_grant.enabled = true
                JOIN brands brand ON brand.tenant_id = user_record.tenant_id
                JOIN brand_expression_baselines baseline
                  ON baseline.tenant_id = brand.tenant_id
                 AND baseline.brand_id = brand.id
                WHERE user_record.tenant_id = %s AND user_record.id = %s
                  AND user_record.enabled = true
                  AND user_record.entry_kind = 'tenant_admin'
                ORDER BY brand.id
                """,
                (identity.tenant_id, identity.user_id),
            )
            rows = cursor.fetchall()
            if len(rows) != 1:
                raise DomainError("当前租户的品牌管理范围尚未唯一确定")
            row = rows[0]
        return TenantManagementScope(
            identity.tenant_id,
            identity.user_id,
            UUID(str(row["brand_id"])),
        )
