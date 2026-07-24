from __future__ import annotations

import os
from pathlib import Path

from src.gateway.api.settings import Settings
from src.infrastructure.production_auth import ProductionAuthRepository
from src.infrastructure.seed_demo import TENANT_ADMIN_USER_ID, TENANT_ID
from src.shared.errors import DomainError


def _required(name: str) -> str:
    value = os.environ.get(name)
    if value is None or not value:
        raise RuntimeError(f"缺少 {name}")
    return value


def _write_root_only(path: Path, content: str) -> None:
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        output.write(content)


def bootstrap_production() -> None:
    settings = Settings.model_validate({})
    if not settings.is_production:
        raise RuntimeError("production bootstrap 只能在 production 模式执行")
    output_path = Path(_required("DIYU_BOOTSTRAP_OUTPUT_PATH"))
    if output_path.exists():
        raise RuntimeError("一次性引导文件已存在；请先由服务器管理员安全处理")
    repository = ProductionAuthRepository(settings.app_database_url)
    ops_username = _required("DIYU_INITIAL_OPS_USERNAME")
    ops_password = _required("DIYU_INITIAL_OPS_PASSWORD")
    demo_admin_username = _required("DIYU_INITIAL_DEMO_ADMIN_USERNAME")
    public_url = os.environ.get("DIYU_PUBLIC_URL", "https://diyuai.cc").rstrip("/")
    _, totp_uri = repository.bootstrap_operator(ops_username, ops_password)
    activation_token = repository.bootstrap_existing_tenant_admin(
        TENANT_ID, TENANT_ADMIN_USER_ID, demo_admin_username
    )
    _write_root_only(
        output_path,
        "平台运维 TOTP 引导：\n"
        + totp_uri
        + "\n\n折线之间首位租户管理员激活链接：\n"
        + f"{public_url}/activate/{activation_token}\n",
    )


if __name__ == "__main__":
    try:
        bootstrap_production()
    except DomainError as exc:
        raise RuntimeError(str(exc)) from exc
