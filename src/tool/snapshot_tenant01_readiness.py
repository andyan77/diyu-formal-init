from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import cast

from fastapi.testclient import TestClient

import src.gateway.api.app as app_module
from src.shared.errors import DomainError
from src.tool.render_tenant01_usage_guide import validate_readiness_document
from src.tool.run_tenant01_formal_vertical import _login, _settings


def _dictionary(value: object, message: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise DomainError(message)
    return cast(dict[str, object], value)


def snapshot_readiness(
    *,
    database_url: str,
    credential_path: Path,
    candidate_sha: str,
    schema_revision: str,
    output_path: Path,
) -> str:
    if output_path.exists():
        raise DomainError("readiness 快照已存在，拒绝静默覆盖")
    if credential_path.stat().st_mode & 0o077:
        raise DomainError("正式凭据文件权限必须为 0600")
    credentials = _dictionary(
        json.loads(credential_path.read_text(encoding="utf-8")),
        "正式凭据文件无效",
    )
    if credentials.get("candidate_sha") != candidate_sha:
        raise DomainError("正式凭据与候选 SHA 不一致")
    settings = _settings(database_url, candidate_sha)
    with TestClient(app_module.create_app(settings), base_url="https://diyu.example") as client:
        _login(
            client,
            "/tenant-admin/login",
            str(credentials["admin_username"]),
            str(credentials["admin_password"]),
        )
        response = client.get("/api/v1/admin/readiness")
        if response.status_code != 200:
            raise DomainError(f"正式 readiness 读取失败 ({response.status_code})")
        document = _dictionary(response.json(), "正式 readiness 返回无效")
    validate_readiness_document(
        document,
        candidate_sha=candidate_sha,
        schema_revision=schema_revision,
    )
    output_path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    output_path.parent.chmod(0o700)
    payload = (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    output_path.write_bytes(payload)
    output_path.chmod(0o600)
    if output_path.stat().st_mode & 0o077:
        raise DomainError("readiness 快照权限不是 0600")
    return hashlib.sha256(payload).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Snapshot TENANT-01 readiness through the formal administrator API."
    )
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--credentials", required=True, type=Path)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--schema-revision", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    digest = snapshot_readiness(
        database_url=args.database_url,
        credential_path=args.credentials.resolve(strict=True),
        candidate_sha=args.candidate_sha,
        schema_revision=args.schema_revision,
        output_path=args.output.resolve(),
    )
    print(json.dumps({"sha256": digest, "verdict": "PASS"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
