from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import cast
from uuid import UUID

import psycopg
import uvicorn
from psycopg.rows import dict_row

import src.gateway.api.app as app_module
from src.brain.content_service import ContentService
from src.composition.bootstrap import build_content_control_service
from src.gateway.api.settings import Settings
from src.infrastructure.postgres_repository import PostgresContentRepository
from src.shared.errors import DomainError
from src.tool.run_tenant01_formal_vertical import (
    FormalBoundaryGenerator,
    _dictionary,
    _settings,
)
from src.tool.tenant01_candidate_freeze import validate_candidate_freeze

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_FACTORY_USER_FACTS = (
    "今天去工厂验厂，",
    "今年量装大货的车缝品质有了大幅度的提升",
)


def _head_sha() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=_PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _free_port() -> int:
    with socket.socket() as port_socket:
        port_socket.bind(("127.0.0.1", 0))
        return int(port_socket.getsockname()[1])


def _chrome_binary() -> Path:
    configured = os.environ.get("TENANT01_CHROME", "")
    candidates = [Path(configured)] if configured else []
    candidates.extend(
        sorted(
            Path("/home/faye/diyu-build/cache/chrome-for-testing").glob("*/chrome-linux64/chrome"),
            reverse=True,
        )
    )
    candidates.extend(
        (
            Path("/usr/bin/google-chrome"),
            Path("/usr/bin/chromium"),
        )
    )
    match = next((path for path in candidates if path.is_file()), None)
    if match is None:
        raise DomainError("未找到构建缓存或系统中的受控 Chrome")
    return match.resolve()


def _provider_settings(database_url: str, candidate_sha: str) -> Settings:
    api_base_url = os.environ.get("DEEPSEEK_API_BASE_URL", "").strip()
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    model = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash").strip()
    if not api_base_url or not api_key:
        raise DomainError("正式候选模型纵向缺少受控 DeepSeek 凭据")
    if model != "deepseek-v4-flash":
        raise DomainError("正式候选模型必须固定为 deepseek-v4-flash")
    return Settings.model_validate(
        {
            "DIYU_RUNTIME_MODE": "production",
            "DIYU_APP_DATABASE_URL": database_url,
            "DIYU_SESSION_SECRET": "tenant01-formal-provider-session-secret",
            "DIYU_PUBLIC_URL": "https://diyu.example",
            "DIYU_GENERATOR_MODE": "deepseek",
            "DIYU_MODEL_TIMEOUT_SECONDS": os.environ.get("DIYU_MODEL_TIMEOUT_SECONDS", "90"),
            "DIYU_MODEL_MAX_RETRIES": "0",
            "DEEPSEEK_API_BASE_URL": api_base_url,
            "DEEPSEEK_API_KEY": api_key,
            "DEEPSEEK_MODEL": model,
            "DIYU_S3_ENDPOINT_URL": "http://127.0.0.1:9000",
            "DIYU_S3_BUCKET": "diyu-test",
            "DIYU_S3_ACCESS_KEY_ID": "local-provider-placeholder",
            "DIYU_S3_SECRET_ACCESS_KEY": "local-provider-placeholder",
            "DIYU_RUNTIME_SHA": candidate_sha,
            "DIYU_MODEL_GLOBAL_CONCURRENCY": "1",
            "DIYU_MODEL_TENANT_CONCURRENCY": "1",
            "DIYU_MODEL_TENANT_RATE_PER_MINUTE": "30",
        }
    )


def _wait_for_server(port: int) -> None:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                return
        except OSError:
            time.sleep(0.05)
    raise DomainError("正式浏览器本地服务启动超时")


def _counts(database_url: str, tenant_id: UUID) -> dict[str, int]:
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        connection.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),))
        row = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM business_tasks WHERE tenant_id=%s) AS tasks,
              (SELECT count(*) FROM generation_runs WHERE tenant_id=%s) AS runs,
              (SELECT count(*) FROM content_versions WHERE tenant_id=%s) AS versions,
              (SELECT count(*) FROM generation_runs
                WHERE tenant_id=%s AND status='running') AS running
            """,
            (tenant_id, tenant_id, tenant_id, tenant_id),
        ).fetchone()
    if row is None:
        raise DomainError("正式浏览器数据库计数无法读取")
    return {key: int(row[key]) for key in ("tasks", "runs", "versions", "running")}


def _new_task_rows(
    database_url: str,
    tenant_id: UUID,
    started_at: datetime,
) -> list[dict[str, object]]:
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        connection.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),))
        rows = connection.execute(
            """
            SELECT task.id, task.brand_id, task.account_id,
                   task.logical_account_id, task.created_by, task.media_format,
                   task.primary_content_product, task.product_refs,
                   task.content_context_snapshot,
                   task.content_context_snapshot #>>
                     '{brand_context_packet,publication_projection_id}'
                     AS publication_projection_id,
                   task.content_context_snapshot #>>
                     '{brand_context_packet,publication_projection_version}'
                     AS publication_projection_version,
                   task.content_context_snapshot #>>
                     '{brand_context_packet,publication_projection_digest}'
                     AS publication_projection_digest,
                   count(DISTINCT run.id) AS run_count,
                   count(DISTINCT version.id) AS version_count,
                   max(version.version_number) AS current_version,
                   bool_and(run.status='succeeded') AS all_runs_succeeded,
                   array_agg(DISTINCT run.model) AS models,
                   max(run.retry_count) AS max_retry_count
              FROM business_tasks task
              LEFT JOIN generation_runs run
                ON run.tenant_id=task.tenant_id AND run.task_id=task.id
              LEFT JOIN content_versions version
                ON version.tenant_id=task.tenant_id AND version.task_id=task.id
             WHERE task.tenant_id=%s AND task.created_at >= %s
             GROUP BY task.id, task.brand_id, task.account_id,
                      task.logical_account_id, task.created_by, task.media_format,
                      task.primary_content_product, task.product_refs,
                      task.content_context_snapshot
             ORDER BY task.id
            """,
            (tenant_id, started_at),
        ).fetchall()
    records: list[dict[str, object]] = []
    for row in rows:
        snapshot = _dictionary(
            row["content_context_snapshot"],
            "正式浏览器任务上下文快照无效",
        )
        narrative = _dictionary(
            snapshot.get("narrative_frame"),
            "正式浏览器叙事快照无效",
        )
        raw_user_facts = narrative.get("user_facts")
        if not isinstance(raw_user_facts, list) or any(not isinstance(value, dict) for value in raw_user_facts):
            raise DomainError("正式浏览器用户事实快照无效")
        packet = _dictionary(
            snapshot.get("brand_context_packet"),
            "正式浏览器品牌上下文快照无效",
        )
        publication = _dictionary(
            snapshot.get("publication_contract"),
            "正式浏览器发布合同快照无效",
        )
        permission = _dictionary(
            publication.get("account_editorial_permission"),
            "正式浏览器账号画像快照无效",
        )
        platform = _dictionary(
            publication.get("platform_direction"),
            "正式浏览器平台目标快照无效",
        )
        raw_consumed = packet.get("consumed_segment_refs")
        if not isinstance(raw_consumed, list) or any(not isinstance(value, str) for value in raw_consumed):
            raise DomainError("正式浏览器已消费品牌来源引用无效")
        projection_version = packet.get("publication_projection_version")
        profile_version = snapshot.get("account_expression_profile_version")
        if type(projection_version) is not int or type(profile_version) is not int:
            raise DomainError("正式浏览器投影或画像版本快照无效")
        if (
            publication.get("publication_projection_id") != packet.get("publication_projection_id")
            or publication.get("publication_projection_version") != projection_version
            or publication.get("publication_projection_digest") != packet.get("publication_projection_digest")
            or permission.get("source_profile_id") != snapshot.get("account_expression_profile_id")
            or permission.get("source_profile_version") != profile_version
        ):
            raise DomainError("正式浏览器发布合同与任务冻结上下文发生漂移")
        records.append(
            {
                "task_id": str(row["id"]),
                "brand_id": str(row["brand_id"]),
                "platform_target_account_id": str(row["account_id"]),
                "publishing_account_id": str(row["logical_account_id"]),
                "created_by": str(row["created_by"]),
                "content_product": str(row["primary_content_product"]),
                "product_refs": list(row["product_refs"]),
                "publication_projection_id": str(row["publication_projection_id"]),
                "publication_projection_version": projection_version,
                "publication_projection_digest": str(row["publication_projection_digest"]),
                "account_expression_profile_id": str(snapshot["account_expression_profile_id"]),
                "account_expression_profile_version": profile_version,
                "content_role": str(snapshot["content_role"]),
                "content_role_id": str(snapshot["content_role_id"]),
                "platform_target_key": str(platform["target"]),
                "media_format": str(platform["media_format"]),
                "run_count": int(row["run_count"]),
                "version_count": int(row["version_count"]),
                "current_version": int(row["current_version"]),
                "all_runs_succeeded": bool(row["all_runs_succeeded"]),
                "models": sorted(str(value) for value in row["models"] if value),
                "max_retry_count": int(row["max_retry_count"]),
                "user_facts": [str(value.get("exact_text")) for value in cast(list[dict[str, object]], raw_user_facts)],
                "consumed_segment_refs": list(cast(list[str], raw_consumed)),
            }
        )
    return records


def _new_artifacts(
    database_url: str,
    tenant_id: UUID,
    started_at: datetime,
) -> list[dict[str, object]]:
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        connection.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),))
        rows = connection.execute(
            """
            SELECT id, task_id, version_number, outline, body,
                   artifact_digest, created_at
              FROM content_versions
             WHERE tenant_id=%s AND created_at >= %s
             ORDER BY task_id, version_number
            """,
            (tenant_id, started_at),
        ).fetchall()
    return [
        {
            "version_id": str(row["id"]),
            "task_id": str(row["task_id"]),
            "version": int(row["version_number"]),
            "outline": str(row["outline"]),
            "body": str(row["body"]),
            "artifact_digest": str(row["artifact_digest"]),
            "created_at": row["created_at"].isoformat(),
        }
        for row in rows
    ]


def _write_private(path: Path, document: dict[str, object]) -> str:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    payload = (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    path.write_bytes(payload)
    path.chmod(0o600)
    if path.stat().st_mode & 0o077:
        raise DomainError("正式浏览器证据权限不是 0600")
    return hashlib.sha256(payload).hexdigest()


def run(
    *,
    database_url: str,
    credentials_path: Path,
    context_evidence_path: Path,
    output_path: Path,
    candidate_sha: str,
    candidate_freeze_path: Path | None = None,
    expect_formally_tested: bool = False,
    provider_model: bool = False,
) -> dict[str, object]:
    if _head_sha() != candidate_sha:
        raise DomainError("正式浏览器候选 SHA 与当前 HEAD 不一致")
    if output_path.exists():
        raise DomainError("正式浏览器证据已存在，拒绝静默覆盖")
    credentials = _dictionary(
        json.loads(credentials_path.read_text(encoding="utf-8")),
        "正式浏览器凭据文件无效",
    )
    if credentials.get("candidate_sha") != candidate_sha:
        raise DomainError("正式浏览器凭据与候选 SHA 不一致")
    if credentials_path.stat().st_mode & 0o077:
        raise DomainError("正式浏览器凭据权限不是 0600")
    context_evidence = _dictionary(
        json.loads(context_evidence_path.read_text(encoding="utf-8")),
        "正式上下文证据无效",
    )
    if (
        context_evidence.get("candidate_sha") != candidate_sha
        or context_evidence.get("tenant_id") != credentials.get("tenant_id")
        or context_evidence.get("verdict") != "PASS"
    ):
        raise DomainError("正式浏览器与上下文消费证据不一致")
    projection_isolation = _dictionary(
        context_evidence.get("projection_isolation"),
        "正式浏览器缺少确认后的 current projection",
    )

    frozen_binding: dict[str, object] | None = None
    candidate_freeze_sha256: str | None = None
    if provider_model:
        if candidate_freeze_path is None:
            raise DomainError("正式候选模型调用缺少不可变 candidate freeze")
        frozen_binding, candidate_freeze_sha256 = validate_candidate_freeze(
            database_url=database_url,
            candidate_freeze_path=candidate_freeze_path,
            context_evidence_path=context_evidence_path,
            candidate_sha=candidate_sha,
        )
        if (
            frozen_binding.get("tenant_id") != credentials.get("tenant_id")
            or frozen_binding.get("brand_id") != credentials.get("brand_id")
            or frozen_binding.get("publishing_account_id") != credentials.get("account_id")
        ):
            raise DomainError("正式候选冻结与受控租户凭据不一致")

    tenant_id = UUID(str(credentials["tenant_id"]))
    before = _counts(database_url, tenant_id)
    started_at = datetime.now(timezone.utc)
    generator: FormalBoundaryGenerator | None = None
    if provider_model:
        app = app_module.create_app(_provider_settings(database_url, candidate_sha))
    else:
        generator = FormalBoundaryGenerator()
        original_builder = cast(
            Callable[[Settings], ContentService],
            app_module.build_content_service,  # type: ignore[attr-defined]
        )

        def builder(settings: Settings) -> ContentService:
            return ContentService(
                PostgresContentRepository(settings.app_database_url),
                generator,
                build_content_control_service(settings),
            )

        app_module.build_content_service = builder  # type: ignore[attr-defined]
        try:
            app = app_module.create_app(_settings(database_url, candidate_sha))
        finally:
            app_module.build_content_service = original_builder  # type: ignore[attr-defined,assignment]

    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_level="warning",
            access_log=False,
        )
    )
    thread = threading.Thread(target=server.run, name="tenant01-formal-browser", daemon=True)
    thread.start()
    try:
        _wait_for_server(port)
        temporary_output = output_path.with_suffix(".browser.tmp.json")
        if temporary_output.exists():
            temporary_output.unlink()
        environment = {
            **os.environ,
            "TENANT01_CHROME": str(_chrome_binary()),
            "TENANT01_BROWSER_BASE_URL": f"http://127.0.0.1:{port}",
            "TENANT01_BROWSER_CREDENTIALS": str(credentials_path),
            "TENANT01_CONTEXT_EVIDENCE": str(context_evidence_path),
            "TENANT01_BROWSER_OUTPUT": str(temporary_output),
            "TENANT01_CANDIDATE_SHA": candidate_sha,
            "TENANT01_EXPECT_FORMALLY_TESTED": ("1" if expect_formally_tested else "0"),
            "TENANT01_EXPECT_AIGC": "1" if provider_model else "0",
        }
        result = subprocess.run(
            ["node", "frontend/test/tenant01-formal-browser.mjs"],
            cwd=_PROJECT_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=600 if provider_model else 240,
        )
        if result.returncode != 0:
            diagnostic = (result.stderr or result.stdout).strip()[-3000:]
            raise DomainError(f"正式 Chrome 旅程失败：{diagnostic}")
        browser = _dictionary(
            json.loads(temporary_output.read_text(encoding="utf-8")),
            "正式 Chrome 输出无效",
        )
        temporary_output.unlink()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
    if thread.is_alive():
        raise DomainError("正式浏览器本地服务没有正常退出")

    after = _counts(database_url, tenant_id)
    new_tasks = _new_task_rows(database_url, tenant_id, started_at)
    new_artifacts = _new_artifacts(database_url, tenant_id, started_at)
    deltas = {key: after[key] - before[key] for key in ("tasks", "runs", "versions")}
    new_task = new_tasks[0] if len(new_tasks) == 1 else {}
    raw_user_facts = new_task.get("user_facts")
    frozen_user_facts = (
        tuple(cast(list[str], raw_user_facts))
        if isinstance(raw_user_facts, list) and all(isinstance(value, str) for value in raw_user_facts)
        else ()
    )
    writer_calls = None if generator is None else generator.writer_calls
    if (
        browser.get("verdict") != "PASS"
        or browser.get("candidate_sha") != candidate_sha
        or browser.get("tenant_id") != str(tenant_id)
        or deltas != {"tasks": 1, "runs": 2, "versions": 2}
        or after["running"] != 0
        or (not provider_model and writer_calls != 2)
        or len(new_tasks) != 1
        or new_task.get("content_product") != "brand_life_narrative"
        or new_task.get("product_refs")
        or new_task.get("publication_projection_id") != projection_isolation.get("new_projection_id")
        or new_task.get("publication_projection_digest") != projection_isolation.get("new_projection_digest")
        or new_task.get("current_version") != 2
        or new_task.get("all_runs_succeeded") is not True
        or new_task.get("max_retry_count") != 0
        or frozen_user_facts != _FACTORY_USER_FACTS
        or not new_task.get("consumed_segment_refs")
        or len(new_artifacts) != 2
        or len({str(item["artifact_digest"]) for item in new_artifacts}) != 2
    ):
        raise DomainError("正式浏览器业务对象增量或边界未达到冻结结果")
    if provider_model:
        if frozen_binding is None or candidate_freeze_sha256 is None:
            raise DomainError("正式候选模型调用缺少已验证冻结绑定")
        task_binding = {
            "tenant_id": str(tenant_id),
            "brand_id": new_task.get("brand_id"),
            "publishing_account_id": new_task.get("publishing_account_id"),
            "platform_target_account_id": new_task.get("platform_target_account_id"),
            "platform_target_key": new_task.get("platform_target_key"),
            "media_format": new_task.get("media_format"),
            "content_role_id": new_task.get("content_role_id"),
            "account_expression_profile_id": new_task.get("account_expression_profile_id"),
            "account_expression_profile_version": new_task.get("account_expression_profile_version"),
            "publication_projection_id": new_task.get("publication_projection_id"),
            "publication_projection_version": new_task.get("publication_projection_version"),
            "publication_projection_digest": new_task.get("publication_projection_digest"),
        }
        if any(frozen_binding.get(key) != value for key, value in task_binding.items()):
            raise DomainError("正式模型任务消费上下文与 candidate freeze 不一致")
    browser["database_evidence"] = {
        "before": before,
        "after": after,
        "deltas": deltas,
        "writer_calls": writer_calls,
        "new_tasks": new_tasks,
    }
    if provider_model:
        browser["provider_artifacts"] = new_artifacts
        browser["provider_model"] = "deepseek-v4-flash"
        browser["provider_max_retries"] = 0
        browser["candidate_freeze"] = {
            "sha256": candidate_freeze_sha256,
            "binding": frozen_binding,
        }
    browser["context_evidence_sha256"] = hashlib.sha256(context_evidence_path.read_bytes()).hexdigest()
    browser["generated_at"] = datetime.now(timezone.utc).isoformat()
    browser["expected_formally_tested"] = expect_formally_tested
    browser["provider_model_used"] = provider_model
    browser["verdict"] = "PASS"
    payload = json.dumps(browser, ensure_ascii=False, sort_keys=True)
    for field in ("admin_password", "content_password"):
        secret = str(credentials[field])
        if secret and secret in payload:
            raise DomainError("正式浏览器证据意外包含凭据")
    digest = _write_private(output_path, browser)
    return {
        "candidate_sha": candidate_sha,
        "tenant_id": str(tenant_id),
        "checks": len(cast(list[object], browser["checks"])),
        "task_delta": deltas["tasks"],
        "run_delta": deltas["runs"],
        "version_delta": deltas["versions"],
        "permanent_running": after["running"],
        "output": str(output_path),
        "sha256": digest,
        "verdict": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the bounded formal TENANT-01 React/Chrome vertical.")
    parser.add_argument("--credentials", required=True, type=Path)
    parser.add_argument("--context-evidence", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--candidate-freeze", type=Path)
    parser.add_argument("--expect-formally-tested", action="store_true")
    parser.add_argument("--provider-model", action="store_true")
    args = parser.parse_args()
    database_url = os.environ.get("DIYU_APP_DATABASE_URL", "")
    if not database_url:
        raise DomainError("缺少本地正式应用数据库连接")
    result = run(
        database_url=database_url,
        credentials_path=args.credentials.resolve(strict=True),
        context_evidence_path=args.context_evidence.resolve(strict=True),
        output_path=args.output.resolve(),
        candidate_sha=args.candidate_sha,
        candidate_freeze_path=(
            args.candidate_freeze.resolve(strict=True)
            if args.candidate_freeze is not None
            else None
        ),
        expect_formally_tested=args.expect_formally_tested,
        provider_model=args.provider_model,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
