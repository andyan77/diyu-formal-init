from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal, cast
from uuid import UUID

from pydantic import SecretStr


@dataclass(frozen=True)
class Settings:
    app_database_url: str
    session_secret: SecretStr
    runtime_mode: Literal["test", "production"]
    demo_tenant_id: UUID
    demo_user_id: UUID
    demo_brand_id: UUID
    demo_account_id: UUID
    demo_headquarters_xiaohongshu_account_id: UUID
    demo_headquarters_wechat_channels_account_id: UUID
    demo_display_organization_id: UUID
    demo_display_user_id: UUID
    demo_store_content_user_id: UUID
    demo_store_content_account_id: UUID
    demo_tenant_admin_user_id: UUID
    demo_dual_qualified_user_id: UUID
    demo_external_operator_user_id: UUID
    store_active_product_refs: tuple[str, ...]
    generator_mode: Literal["stub", "deepseek"]
    model_timeout_seconds: float
    model_max_retries: int
    deepseek_api_base_url: str | None
    deepseek_api_key: SecretStr | None
    deepseek_model: str | None
    material_storage_root: str
    s3_endpoint_url: str | None
    s3_bucket: str | None
    s3_access_key_id: SecretStr | None
    s3_secret_access_key: SecretStr | None
    s3_region: str | None
    login_rate_limit_per_minute: int
    model_global_concurrency: int
    model_tenant_concurrency: int
    model_tenant_rate_per_minute: int

    @property
    def is_production(self) -> bool:
        return self.runtime_mode == "production"

    @classmethod
    def model_validate(cls, values: dict[str, object]) -> Settings:
        """Load server-only configuration without echoing values or secrets."""

        field_names = {
            "DIYU_APP_DATABASE_URL": "app_database_url",
            "DIYU_SESSION_SECRET": "session_secret",
            "DIYU_RUNTIME_MODE": "runtime_mode",
            "DIYU_DEMO_TENANT_ID": "demo_tenant_id",
            "DIYU_DEMO_USER_ID": "demo_user_id",
            "DIYU_DEMO_BRAND_ID": "demo_brand_id",
            "DIYU_DEMO_ACCOUNT_ID": "demo_account_id",
            "DIYU_DEMO_HEADQUARTERS_XIAOHONGSHU_ACCOUNT_ID": "demo_headquarters_xiaohongshu_account_id",
            "DIYU_DEMO_HEADQUARTERS_WECHAT_CHANNELS_ACCOUNT_ID": "demo_headquarters_wechat_channels_account_id",
            "DIYU_DEMO_DISPLAY_ORGANIZATION_ID": "demo_display_organization_id",
            "DIYU_DEMO_DISPLAY_USER_ID": "demo_display_user_id",
            "DIYU_DEMO_STORE_CONTENT_USER_ID": "demo_store_content_user_id",
            "DIYU_DEMO_STORE_CONTENT_ACCOUNT_ID": "demo_store_content_account_id",
            "DIYU_DEMO_TENANT_ADMIN_USER_ID": "demo_tenant_admin_user_id",
            "DIYU_DEMO_DUAL_QUALIFIED_USER_ID": "demo_dual_qualified_user_id",
            "DIYU_DEMO_EXTERNAL_OPERATOR_USER_ID": "demo_external_operator_user_id",
            "DIYU_STORE_ACTIVE_PRODUCT_REFS": "store_active_product_refs",
            "DIYU_GENERATOR_MODE": "generator_mode",
            "DIYU_MODEL_TIMEOUT_SECONDS": "model_timeout_seconds",
            "DIYU_MODEL_MAX_RETRIES": "model_max_retries",
            "DEEPSEEK_API_BASE_URL": "deepseek_api_base_url",
            "DEEPSEEK_API_KEY": "deepseek_api_key",
            "DEEPSEEK_MODEL": "deepseek_model",
            "DIYU_MATERIAL_STORAGE_ROOT": "material_storage_root",
            "DIYU_S3_ENDPOINT_URL": "s3_endpoint_url",
            "DIYU_S3_BUCKET": "s3_bucket",
            "DIYU_S3_ACCESS_KEY_ID": "s3_access_key_id",
            "DIYU_S3_SECRET_ACCESS_KEY": "s3_secret_access_key",
            "DIYU_S3_REGION": "s3_region",
            "DIYU_LOGIN_RATE_LIMIT_PER_MINUTE": "login_rate_limit_per_minute",
            "DIYU_MODEL_GLOBAL_CONCURRENCY": "model_global_concurrency",
            "DIYU_MODEL_TENANT_CONCURRENCY": "model_tenant_concurrency",
            "DIYU_MODEL_TENANT_RATE_PER_MINUTE": "model_tenant_rate_per_minute",
        }

        def read(name: str, default: str | None = None) -> str | None:
            value = values.get(field_names[name], values.get(name))
            if value is not None:
                return str(value)
            return os.environ.get(name, default)

        runtime_mode = read("DIYU_RUNTIME_MODE", "test")
        if runtime_mode not in ("test", "production"):
            raise RuntimeError("DIYU_RUNTIME_MODE 只能是 test 或 production")
        required_names: tuple[str, ...] = ("DIYU_APP_DATABASE_URL", "DIYU_SESSION_SECRET")
        if runtime_mode == "test":
            required_names += (
                "DIYU_DEMO_TENANT_ID",
                "DIYU_DEMO_USER_ID",
                "DIYU_DEMO_BRAND_ID",
                "DIYU_DEMO_ACCOUNT_ID",
            )
        missing = [name for name in required_names if not read(name)]
        if missing:
            raise RuntimeError("缺少服务器配置：" + ", ".join(missing))
        mode = read("DIYU_GENERATOR_MODE", "stub")
        if mode not in ("stub", "deepseek"):
            raise RuntimeError("DIYU_GENERATOR_MODE 只能是 stub 或 deepseek")
        timeout = float(read("DIYU_MODEL_TIMEOUT_SECONDS", "30") or "30")
        retries = int(read("DIYU_MODEL_MAX_RETRIES", "2") or "2")
        if not 1.0 <= timeout <= 120.0 or not 0 <= retries <= 4:
            raise RuntimeError("模型重试或超时配置超出安全范围")
        api_key = read("DEEPSEEK_API_KEY")
        if runtime_mode == "production" and mode != "deepseek":
            raise RuntimeError("production 模式必须使用 deepseek 生成器")
        placeholder_id = "00000000-0000-0000-0000-000000000000"
        configured = cls(
            app_database_url=str(read("DIYU_APP_DATABASE_URL")),
            session_secret=SecretStr(str(read("DIYU_SESSION_SECRET"))),
            runtime_mode=cast(Literal["test", "production"], runtime_mode),
            demo_tenant_id=UUID(str(read("DIYU_DEMO_TENANT_ID", placeholder_id))),
            demo_user_id=UUID(str(read("DIYU_DEMO_USER_ID", placeholder_id))),
            demo_brand_id=UUID(str(read("DIYU_DEMO_BRAND_ID", placeholder_id))),
            demo_account_id=UUID(str(read("DIYU_DEMO_ACCOUNT_ID", placeholder_id))),
            demo_headquarters_xiaohongshu_account_id=UUID(
                str(
                    read(
                        "DIYU_DEMO_HEADQUARTERS_XIAOHONGSHU_ACCOUNT_ID",
                        "00000000-0000-0000-0000-000000000033",
                    )
                )
            ),
            demo_headquarters_wechat_channels_account_id=UUID(
                str(
                    read(
                        "DIYU_DEMO_HEADQUARTERS_WECHAT_CHANNELS_ACCOUNT_ID",
                        "00000000-0000-0000-0000-000000000034",
                    )
                )
            ),
            demo_display_organization_id=UUID(
                str(read("DIYU_DEMO_DISPLAY_ORGANIZATION_ID", "00000000-0000-0000-0000-000000000012"))
            ),
            demo_display_user_id=UUID(str(read("DIYU_DEMO_DISPLAY_USER_ID", "00000000-0000-0000-0000-000000000013"))),
            demo_store_content_user_id=UUID(
                str(read("DIYU_DEMO_STORE_CONTENT_USER_ID", "00000000-0000-0000-0000-000000000014"))
            ),
            demo_store_content_account_id=UUID(
                str(read("DIYU_DEMO_STORE_CONTENT_ACCOUNT_ID", "00000000-0000-0000-0000-000000000032"))
            ),
            demo_tenant_admin_user_id=UUID(
                str(read("DIYU_DEMO_TENANT_ADMIN_USER_ID", "00000000-0000-0000-0000-000000000015"))
            ),
            demo_dual_qualified_user_id=UUID(
                str(read("DIYU_DEMO_DUAL_QUALIFIED_USER_ID", "00000000-0000-0000-0000-000000000016"))
            ),
            demo_external_operator_user_id=UUID(
                str(
                    read(
                        "DIYU_DEMO_EXTERNAL_OPERATOR_USER_ID",
                        "00000000-0000-0000-0000-000000000017",
                    )
                )
            ),
            store_active_product_refs=tuple(
                ref.strip().upper()
                for ref in (read("DIYU_STORE_ACTIVE_PRODUCT_REFS", "ZX-C218") or "").split(",")
                if ref.strip()
            ),
            generator_mode=cast(Literal["stub", "deepseek"], mode),
            model_timeout_seconds=timeout,
            model_max_retries=retries,
            deepseek_api_base_url=read("DEEPSEEK_API_BASE_URL"),
            deepseek_api_key=SecretStr(api_key) if api_key else None,
            deepseek_model=read("DEEPSEEK_MODEL"),
            material_storage_root=str(read("DIYU_MATERIAL_STORAGE_ROOT", "var/materials-test")),
            s3_endpoint_url=read("DIYU_S3_ENDPOINT_URL"),
            s3_bucket=read("DIYU_S3_BUCKET"),
            s3_access_key_id=(SecretStr(value) if (value := read("DIYU_S3_ACCESS_KEY_ID")) is not None else None),
            s3_secret_access_key=(
                SecretStr(value) if (value := read("DIYU_S3_SECRET_ACCESS_KEY")) is not None else None
            ),
            s3_region=read("DIYU_S3_REGION", "us-east-1"),
            login_rate_limit_per_minute=int(read("DIYU_LOGIN_RATE_LIMIT_PER_MINUTE", "10") or "10"),
            model_global_concurrency=int(read("DIYU_MODEL_GLOBAL_CONCURRENCY", "4") or "4"),
            model_tenant_concurrency=int(read("DIYU_MODEL_TENANT_CONCURRENCY", "2") or "2"),
            model_tenant_rate_per_minute=int(read("DIYU_MODEL_TENANT_RATE_PER_MINUTE", "12") or "12"),
        )
        if configured.generator_mode == "deepseek" and not all(
            (
                configured.deepseek_api_base_url,
                configured.deepseek_api_key,
                configured.deepseek_model,
            )
        ):
            raise RuntimeError("deepseek 模式必须配置 API 地址、密钥和已核验模型")
        if not 1 <= configured.login_rate_limit_per_minute <= 60:
            raise RuntimeError("登录限流配置超出安全范围")
        if not 1 <= configured.model_global_concurrency <= 20 or not 1 <= configured.model_tenant_concurrency <= 10:
            raise RuntimeError("模型并发配置超出安全范围")
        if not 1 <= configured.model_tenant_rate_per_minute <= 120:
            raise RuntimeError("模型租户速率配置超出安全范围")
        if configured.is_production and not all(
            (
                configured.s3_endpoint_url,
                configured.s3_bucket,
                configured.s3_access_key_id,
                configured.s3_secret_access_key,
            )
        ):
            raise RuntimeError("production 模式必须配置独立对象存储")
        return configured
