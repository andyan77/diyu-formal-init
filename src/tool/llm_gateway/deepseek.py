from __future__ import annotations

import json
import re
import time
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from src.ports.content_generator import ContentGenerator
from src.shared.errors import GenerationFailed
from src.shared.types import (
    GeneratedArtifact,
    GenerationInput,
    P1ProductionBundle,
    P1SemanticContract,
)


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
            "temperature": 0.2,
            "max_tokens": 3072,
            "response_format": {"type": "json_object"},
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
            content = self._json_content(str(payload["choices"][0]["message"]["content"]))
            structured = json.loads(content)
            body = str(structured["body"]).strip()
            contract = P1SemanticContract(
                choice=str(structured["choice"]).strip(),
                boundary=str(structured["boundary"]).strip(),
                next_action=str(structured["next_action"]).strip(),
            )
            body = self._body_with_contract(body, contract)
            production = P1ProductionBundle(
                natural_guide=str(structured["natural_guide"]).strip(),
                spoken_lines=str(structured["spoken_lines"]).strip(),
                visual_actions=str(structured["visual_actions"]).strip(),
                subtitles=str(structured["subtitles"]).strip(),
                sound_and_production=str(structured["sound_and_production"]).strip(),
            )
            body = self._body_with_production(body, production)
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
            production=production,
        )

    @staticmethod
    def _json_content(content: str) -> str:
        """Accept a provider's fenced JSON while rejecting any non-JSON response."""
        stripped = content.strip()
        if stripped.startswith("```") and stripped.endswith("```"):
            stripped = re.sub(r"^```(?:json)?\s*", "", stripped, count=1, flags=re.IGNORECASE)
            stripped = re.sub(r"\s*```$", "", stripped, count=1)
        return stripped

    @staticmethod
    def _body_with_contract(body: str, contract: P1SemanticContract) -> str:
        """Keep the user-visible artifact faithful to its small semantic contract."""
        if all(
            value in body for value in (contract.choice, contract.boundary, contract.next_action)
        ):
            return body
        return (
            f"{body}\n\n本条选择：{contract.choice}\n"
            f"适用边界：{contract.boundary}\n"
            f"下一步：{contract.next_action}"
        )

    @staticmethod
    def _body_with_production(body: str, production: P1ProductionBundle) -> str:
        sections = (
            ("自然导读", production.natural_guide),
            ("完整台词/解说", production.spoken_lines),
            ("画面与动作", production.visual_actions),
            ("字幕", production.subtitles),
            ("声音与制作提示", production.sound_and_production),
        )
        missing = [f"{heading}：{value}" for heading, value in sections if heading not in body]
        return body if not missing else f"{body}\n\n" + "\n".join(missing)

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
品牌战略版本：{request.brand.strategy_version}
发布平台与媒体：{request.brand.platform}／{request.brand.media_format}
当前制作条件：{request.brand.production_conditions}
自然弱种子：{request.weak_seed}
本次修改：{revision}
仅在明确授权时可参考的已保存正文：{prior}
已确认、当前品牌范围内的领域资产：{assets}

只返回一个可由 JSON 解析器直接解析的对象，不能使用 Markdown 代码块、前后说明或省略号。键名只能是 body、choice、boundary、next_action、natural_guide、spoken_lines、visual_actions、subtitles、sound_and_production，九个键都必须出现且值为非空字符串。body 必须完整呈现五个制作部分：自然导读、完整台词/解说、画面与动作、字幕、声音与制作提示；并逐字包含 choice、boundary、next_action 三个值。其他字段是对应可执行部分，不能是提示词或隐藏推理。必须先形成穿衣选择，再说明依据、改变选择的条件和一个低成本验证动作。不要复述顾客姓名、电话、账号或订单号；使用自然非识别性称谓。只能给出条件性的穿搭建议，例如“可以优先考虑”“如果已有这类单品”；绝不虚构品牌测试、门店经验、商品款号、面料、口袋、剪裁、功能或既有产品设计，也不要写“我们测试过”“特意设计”“自带”。不得把输入的相对时间改写为具体钟点，不得新增未给定的职业、场地、人物或拍摄素材。不要补造职业、天气、体型、预算、衣橱、交通或商品事实；不要承诺身体效果；不要硬卖货、说教或暴露后台过程。"""
