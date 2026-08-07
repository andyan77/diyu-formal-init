"""EXE-01R R2 — a task deep link always serves the application.

`/content/tasks/{task}?version=N` used to answer 404 when the version was not
visible. That withheld the SPA shell, so React never booted and the person met
a bare error with nowhere to go. The shell is served either way now; the
missing version becomes a recovery page instead of a dead end.

Permission is unchanged and must stay unchanged: "not yours" may never be
rendered as "not there".
"""

from __future__ import annotations

import json
from typing import cast
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from src.gateway.api.app import create_app
from src.gateway.api.settings import Settings
from src.infrastructure.seed_demo import ACCOUNT_ID

SHELL_MARKER = "<script>window.__DIYU_BOOTSTRAP__="


def _bootstrap(text: str) -> dict[str, object]:
    payload = text.split(SHELL_MARKER, maxsplit=1)[1].split(";</script>", maxsplit=1)[0]
    value = json.loads(payload)
    assert isinstance(value, dict)
    return cast(dict[str, object], value)


def _client() -> TestClient:
    return TestClient(create_app(Settings.model_validate({})))


def _make_task(client: TestClient) -> tuple[UUID, int]:
    response = client.post(
        "/api/v1/content",
        json={
            "weak_seed": "帮我写一条秋冬羊毛大衣洗护说明的小红书图文。",
            "publishing_identity_id": str(ACCOUNT_ID),
            "target": "xiaohongshu_graphic",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body.get("kind") == "content", body
    return UUID(str(body["task_id"])), int(body["version"])


def test_a_missing_version_still_serves_the_application() -> None:
    with _client() as client:
        client.get("/ui/select/content")
        task, version = _make_task(client)
        response = client.get(
            f"/content/tasks/{task}?version={version + 99}&target=xiaohongshu_graphic"
        )

    assert response.status_code == 200, "版本不存在不应拦下 SPA 壳"
    assert SHELL_MARKER in response.text, "深链没有下发 bootstrap，React 起不来"
    assert "找不到这个版本" in response.text
    assert 'href=\'/content\'' in response.text, "无脚本回退里没有返回工作台的出口"


def test_an_unknown_task_is_a_recovery_page_not_a_404() -> None:
    with _client() as client:
        client.get("/ui/select/content")
        response = client.get(f"/content/tasks/{uuid4()}?version=1")

    assert response.status_code == 200
    assert SHELL_MARKER in response.text
    assert "找不到这个版本" in response.text


def test_a_real_version_still_renders_its_content() -> None:
    # `target` is carried explicitly. Without it the handler resolves the
    # default platform, which may not be the one the task belongs to — a
    # pre-existing property of the deep link that R2 records rather than
    # changes, because fixing it means reading the task to learn its target
    # and this package may not touch task reading.
    with _client() as client:
        client.get("/ui/select/content")
        task, version = _make_task(client)
        response = client.get(
            f"/content/tasks/{task}?version={version}&target=xiaohongshu_graphic"
        )

    assert response.status_code == 200
    assert "完整文字成品" in response.text
    assert "找不到这个版本" not in response.text, "可读版本不得落进恢复分支"
    context = _bootstrap(response.text)
    assert context.get("application") == "content"


def test_an_unauthenticated_deep_link_is_not_called_a_missing_version() -> None:
    settings = Settings.model_validate(
        {
            "DIYU_RUNTIME_MODE": "production",
            # Production settings only; the request is refused at the door,
            # so no generator or object store is ever reached.
            "DIYU_GENERATOR_MODE": "deepseek",
            "DIYU_PUBLIC_URL": "https://diyu.example.invalid",
            "DEEPSEEK_API_BASE_URL": "https://deepseek.example.invalid",
            "DEEPSEEK_API_KEY": "not-a-real-key",
            "DEEPSEEK_MODEL": "deepseek-v4-flash",
            "QWEN_REVIEWER_API_BASE_URL": "https://qwen.example.invalid",
            "DASHSCOPE_API_KEY": "not-a-real-qwen-key",
            "QWEN_REVIEWER_MODEL": "qwen3.7-max-2026-05-20",
            "DIYU_S3_ENDPOINT_URL": "http://127.0.0.1:9000",
            "DIYU_S3_BUCKET": "diyu-test",
            "DIYU_S3_ACCESS_KEY_ID": "test-access-key",
            "DIYU_S3_SECRET_ACCESS_KEY": "test-secret-key",
        }
    )
    with TestClient(create_app(settings)) as client:
        response = client.get(
            f"/content/tasks/{uuid4()}?version=1", follow_redirects=False
        )

    assert response.status_code in {303, 401, 403}, response.status_code
    assert "找不到这个版本" not in response.text, "未登录被伪装成版本不存在"
