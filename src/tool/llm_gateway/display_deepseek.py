from __future__ import annotations

import json
import re
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
        prompt = self._prompt(request)
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
                        return self._result(response.json(), started, retries)
                    if (
                        response.status_code != 429 and not 500 <= response.status_code < 600
                    ) or retries >= self._retries:
                        raise GenerationFailed("模型服务暂时不可用")
                except httpx.TransportError as exc:
                    if retries >= self._retries:
                        raise GenerationFailed("模型网络请求失败") from exc
                retries += 1
                time.sleep(
                    DeepSeekGenerator._retry_delay(response.headers.get("Retry-After"), retries - 1)
                )

    @staticmethod
    def _prompt(request: DisplayGenerationInput) -> str:
        assets = "\n".join(
            f"- {asset.asset_id}@{asset.schema_version}: {asset.body}"
            for asset in request.active_domain_assets
        )
        products = "\n".join(f"- {sku}: {facts}" for sku, facts in request.context.products)
        feedback = request.feedback or "（首次生成；没有现场反馈。）"
        prior = (
            json.dumps(request.prior_plan, ensure_ascii=False)
            if request.prior_plan
            else "（首次生成；没有上一版结构。）"
        )
        return f"""你只为 DM01 墙面双层挂杆合同生成一份完整的中文内部执行建议。
当前实际操作组织：{request.context.organization_name}；当前操作人：{request.context.operator_name}。
品牌：{request.context.brand_name}。陈列标准版本 {request.context.policy_version}：{request.context.policy}
门店：{request.context.store_name}。挂杆档案版本 {request.context.store_profile_version}：{request.context.rail_profile}
当前商品事实：
{products}
当前人工库存（仅本任务，不是 ERP）：{dict(request.inventory)}
本次适用陈列资产：
{assets or "（无）"}
自然反馈：{feedback}
修订时上一版本必要结构：{prior}

首次生成只使用库存、品牌标准、挂杆档案、商品事实和本次资产。冻结首次任务的 mounted 必须严格为 ZX-C218:2、ZX-S104:2、ZX-K126:2、ZX-P211:3、ZX-V113:2、ZX-Q117:4（共15件）；zones 必须严格为 A={{ZX-C218:1,ZX-P211:2}}、B={{ZX-S104:2,ZX-K126:2,ZX-Q117:2}}、C={{ZX-C218:1,ZX-V113:2,ZX-P211:1,ZX-Q117:2}}。A 为左侧深绿细格 C218 主正挂，C 为右侧炭灰面 C218 弱回应，不能换成其他商品正挂。修订时只改反馈影响范围：C 的 ZX-V113 从2改为1、共14件，其他商品和 A/B 区、全部下杆、主次焦点、左右动线继承不变。不得补造未给出的商品属性、库房、设施或行动事实，也不得使用或提及发布账号、ContentRole、平台、CTA、提示词、资产 ID、运行记录、其他租户/品牌/组织资料。

严格只返回 JSON 对象：body 为完整、可直接执行的中文正文；plan 为对象，且必须包含 mounted、unmounted、zones。mounted 与 unmounted 使用 SKU→整数；所有库存 SKU 必须逐项对账，禁止清单外 SKU 或超量。zones 必须含 A、B、C。正文必须包含主焦点、回应、侧挂、替代、执行步骤和“内部执行建议”，并明确不表示总部批准、系统核验或门店已经完成。"""

    def _result(
        self, payload: dict[str, object], started: float, retries: int
    ) -> GeneratedDisplayArtifact:
        try:
            choices = payload["choices"]
            choice = choices[0]  # type: ignore[index]
            content = choice["message"]["content"]
            data = json.loads(DeepSeekGenerator._json_content(str(content)))
            body = re.sub(r"\b(?:G|GM)-[A-Z]+-\d{3}\b", "", str(data["body"])).strip()
            plan = data["plan"]
            if not body or not isinstance(plan, dict):
                raise TypeError("display result")
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise GenerationFailed("模型返回格式不完整") from exc
        usage = payload.get("usage")
        return GeneratedDisplayArtifact(
            body,
            plan,
            self._model,
            int((time.monotonic() - started) * 1000),
            retries,
            usage if isinstance(usage, dict) else None,
        )
