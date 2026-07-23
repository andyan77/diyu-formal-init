from __future__ import annotations

import json
import time

import httpx

from src.ports.display_generator import DisplayGenerator
from src.shared.errors import GenerationFailed
from src.shared.types import DisplayGenerationInput, GeneratedDisplayArtifact
from src.tool.llm_gateway.deepseek import DeepSeekGenerator


class DeepSeekDisplayGenerator(DisplayGenerator):
    """DM01 adapter using the same one-provider endpoint and bounded retry behavior."""

    def __init__(
        self, api_base_url: str, api_key: str, model: str, timeout_seconds: float, max_retries: int
    ) -> None:
        self._base, self._key, self._model = api_base_url.rstrip("/"), api_key, model
        self._timeout, self._retries = timeout_seconds, max_retries

    @property
    def model_name(self) -> str:
        return self._model

    def generate(self, request: DisplayGenerationInput) -> GeneratedDisplayArtifact:
        started, retries = time.monotonic(), 0
        prompt = f"为南城店墙面双层挂杆写完整内部执行建议。库存={dict(request.inventory)}；反馈={request.feedback or '首次'}。只用清单内 SKU，输出 JSON: body 与 plan(mounted,unmounted,zones)。必须有 A/B/C、主焦点、回应、侧挂、替代、执行步骤和内部执行建议；不声称批准、核验或已完成。"
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        with httpx.Client(timeout=httpx.Timeout(self._timeout)) as client:
            while True:
                try:
                    response = client.post(
                        f"{self._base}/chat/completions",
                        headers={"Authorization": f"Bearer {self._key}"},
                        json=payload,
                    )
                    if response.status_code < 400:
                        data = json.loads(
                            DeepSeekGenerator._json_content(
                                str(response.json()["choices"][0]["message"]["content"])
                            )
                        )
                        plan = data["plan"]
                        if not isinstance(plan, dict):
                            raise GenerationFailed("模型返回格式不完整")
                        usage = response.json().get("usage")
                        return GeneratedDisplayArtifact(
                            str(data["body"]),
                            plan,
                            self._model,
                            int((time.monotonic() - started) * 1000),
                            retries,
                            usage if isinstance(usage, dict) else None,
                        )
                    if (
                        response.status_code != 429 and not 500 <= response.status_code < 600
                    ) or retries >= self._retries:
                        raise GenerationFailed("模型服务暂时不可用")
                except httpx.TransportError as exc:
                    if retries >= self._retries:
                        raise GenerationFailed("模型网络请求失败") from exc
                retries += 1
                time.sleep(min(4.0, 0.5 * (2 ** (retries - 1))))
