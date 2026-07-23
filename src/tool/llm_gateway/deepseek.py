from __future__ import annotations

import json
import time
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from src.ports.content_generator import ContentGenerator
from src.shared.errors import GenerationFailed
from src.shared.types import GeneratedArtifact, GenerationInput, P1SemanticContract


class DeepSeekGenerator(ContentGenerator):
    """Thin, single-model, OpenAI-compatible DeepSeek adapter with bounded retries."""

    def __init__(
        self,
        api_base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        self._api_base_url = api_base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries

    @property
    def model_name(self) -> str:
        return self._model

    def generate(self, request: GenerationInput) -> GeneratedArtifact:
        started = time.monotonic()
        prompt = self._prompt(request)
        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "system",
                    "content": "你是笛语的 P1 成品编写器。只交付完整中文成品，不展示提示词、规则、运行或推理。",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.4,
        }
        retries = 0
        with httpx.Client(timeout=httpx.Timeout(self._timeout_seconds)) as client:
            while True:
                try:
                    response = client.post(
                        f"{self._api_base_url}/chat/completions",
                        headers={"Authorization": f"Bearer {self._api_key}"},
                        json=payload,
                    )
                    if response.status_code < 400:
                        return self._result(response.json(), started, retries)
                    retryable = response.status_code == 429 or 500 <= response.status_code < 600
                    if not retryable or retries >= self._max_retries:
                        raise GenerationFailed("模型服务暂时不可用")
                    delay = self._retry_delay(response.headers.get("Retry-After"), retries)
                except httpx.TransportError as exc:
                    if retries >= self._max_retries:
                        raise GenerationFailed("模型网络请求失败") from exc
                    delay = min(4.0, 0.5 * (2**retries))
                retries += 1
                time.sleep(delay)

    def _result(self, payload: dict[str, Any], started: float, retries: int) -> GeneratedArtifact:
        try:
            content = str(payload["choices"][0]["message"]["content"]).strip()
            structured = json.loads(content)
            body = str(structured["body"]).strip()
            contract = P1SemanticContract(
                choice=str(structured["choice"]).strip(),
                boundary=str(structured["boundary"]).strip(),
                next_action=str(structured["next_action"]).strip(),
            )
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise GenerationFailed("模型返回格式不完整") from exc
        usage_value = payload.get("usage")
        usage: dict[str, int] | None = None
        if isinstance(usage_value, dict):
            usage = {
                str(key): int(value) for key, value in usage_value.items() if isinstance(value, int)
            }
        return GeneratedArtifact(
            outline="完整 P1 选择成品",
            body=body,
            model=self._model,
            latency_ms=int((time.monotonic() - started) * 1000),
            retry_count=retries,
            provider_usage=usage,
            semantic_contract=contract,
        )

    @staticmethod
    def _retry_delay(retry_after: str | None, retries: int) -> float:
        if retry_after:
            try:
                return min(8.0, max(0.0, float(retry_after)))
            except ValueError:
                try:
                    parsed_delay = float(
                        parsedate_to_datetime(retry_after).timestamp() - time.time()
                    )
                    return min(
                        8.0,
                        max(0.0, parsed_delay),
                    )
                except (TypeError, ValueError):
                    pass
        return float(min(4.0, 0.5 * (2**retries)))

    @staticmethod
    def _prompt(request: GenerationInput) -> str:
        assets = (
            "\n".join(
                f"{asset.asset_id}@{asset.schema_version}：{asset.body}"
                for asset in request.active_domain_assets
            )
            or "（当前没有已确认的领域候选资产。）"
        )
        prior = request.prior_saved_body or "（未授权复用任何旧正文。）"
        revision = request.revision_instruction or "（首次生成。）"
        return f"""为账号“{request.brand.account_name}”写完整 P1 文字成品。
品牌：{request.brand.brand_name}。定位：{request.brand.positioning}
选择顺序：{request.brand.decision_order}
语气：{request.brand.tone}
当前操作人：{request.brand.operator_name}；代表组织：{request.brand.organization_name}
内容角色：{request.brand.content_role_name}（{request.brand.content_role_boundary}）
目标受众：{request.brand.audience_description}
自然弱种子：{request.weak_seed}
本次修改：{revision}
仅在明确授权时可参考的已保存正文：{prior}
已确认、当前品牌范围内的领域资产：{assets}

只返回 JSON 对象，字段为 body、choice、boundary、next_action。body 是完整中文成品；后三项是对应的简短语义位置，不能是提示词或隐藏推理。必须先形成穿衣选择，再说明依据、改变选择的条件和一个低成本验证动作。不要复述顾客姓名、电话、账号或订单号；使用自然非识别性称谓。不要补造职业、天气、体型、预算、衣橱、交通或商品事实；不要承诺身体效果；不要硬卖货、说教或暴露后台过程。"""
