from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any, Literal, cast

import httpx

from src.ports.content_generator import ContentGenerator
from src.shared.errors import GenerationFailed
from src.shared.types import (
    ContentProduct,
    ContentProductionBundle,
    ContentSemanticContract,
    FactRepairReceipt,
    GeneratedArtifact,
    GenerationInput,
    GraphicProductionBundle,
    P1SemanticContract,
    P2SemanticContract,
    P3SemanticContract,
    P4SemanticContract,
    P5SemanticContract,
    RoutingInput,
    VideoProductionBundle,
)

_CONTRACT_FIELDS: dict[ContentProduct, tuple[str, str, str]] = {
    "dressing_decision": ("choice", "boundary", "next_action"),
    "product_truth": ("product_insight", "tradeoff_or_limit", "validity_condition"),
    "brand_life_narrative": ("persona_observation", "audience_return", "brand_account_link"),
    "local_response": (
        "local_reality_or_signal",
        "legitimate_account_response",
        "public_relationship_return",
    ),
    "visual_styling_story": (
        "real_product_anchor",
        "visible_styling_proposition",
        "visual_dependency",
    ),
}
_PRODUCT_VALUE: dict[ContentProduct, str] = {
    "dressing_decision": "帮助受众完成有条件、有边界的穿衣选择",
    "product_truth": "解释一件商品能确认什么、不能确认什么",
    "brand_life_narrative": "让受众认识这个账号怎样观察、判断和待人",
    "local_response": "从门店近场信号给未到店者一份关系回应",
    "visual_styling_story": "用真实商品与画面动作创造可见的穿着可能",
}
_DELIVERABLE_REQUIREMENTS: dict[ContentProduct, str] = {
    "dressing_decision": (
        "必须给出一个有条件的优先选择、一条会令选择反转的条件，以及一个不依赖未经提供商品事实的低成本验证动作。"
        "本卡的主回报是帮助选择，不能把商品介绍或画面变化写成主回报。"
    ),
    "product_truth": (
        "必须形成一项商品专属新增理解，逐项说清可确认事实、相伴限制与当前不能下的结论。"
        "画面只能作为商品认知的证据，不能替用户选面或把视觉变化写成主回报。"
        "新增理解、限制和成立边界必须由当前商品事实与当前适用资产共同形成，不能把资产的一般表述冒充为商品事实。"
    ),
    "brand_life_narrative": (
        "必须让受众认识账号怎样观察、判断和待人；近场事件、商品和镜头只能服务这一人格回报。"
        "不要把可迁移的门店关系许可写成主回报，也不要把商品改写为造型主张。"
    ),
    "local_response": (
        "必须由已给出的近场信号、当前发布账号能合法作出的回应、未到店者也可带走的关系许可共同承重。"
        "不要把店长性格、商品或画面写成主回报，也不把门店做法扩大成全国政策或交易承诺。"
    ),
    "visual_styling_story": (
        "必须由真实商品和画面动作形成一项可见的穿着可能；移除翻面、走动和两面在画面中的关系后，主回报应消失。"
        "不要给选择建议或商品资料说明，也不要把颜色/纹理推成性能、剪裁、人格或生活方式。"
    ),
}


@dataclass(frozen=True)
class BoundaryContext:
    """Ephemeral, user-invisible boundary for one generation call."""

    trusted_identity: str
    confirmed_facts: str
    user_premise: str
    brand_viewpoint: str
    production_resources: str
    product_skus: tuple[str, ...] = ()
    known_numbers: tuple[int, ...] = ()
    known_colors: tuple[str, ...] = ()
    internal_identifiers: tuple[str, ...] = ()

    @classmethod
    def from_request(cls, request: GenerationInput) -> BoundaryContext:
        numbers: list[int] = []
        colors: list[str] = []
        for product in request.products:
            for value in product.facts.values():
                if isinstance(value, int):
                    numbers.append(value)
            raw_colors = product.facts.get("colors")
            if isinstance(raw_colors, list):
                colors.extend(value for value in raw_colors if isinstance(value, str))
        recorded_numbers = tuple(dict.fromkeys(numbers))
        numbers.extend(
            abs(left - right) for index, left in enumerate(recorded_numbers) for right in recorded_numbers[index + 1 :]
        )
        facts = "\n".join(
            (
                f"当前品牌有效基线：定位“{request.brand.positioning}”；"
                f"判断顺序“{request.brand.decision_order}”；语气“{request.brand.tone}”。",
                "当前商品事实："
                + (
                    "；".join(
                        DeepSeekGenerator._natural_product(product.sku, product.facts) for product in request.products
                    )
                    or "无已确认商品"
                ),
                "本次适用可信资料："
                + ("；".join(asset.body for asset in request.active_domain_assets) or "无额外可信资料"),
            )
        )
        return cls(
            trusted_identity=(
                f"当前发布账号“{request.brand.account_name}”；当前内容角色"
                f"“{request.brand.content_role_name}”；表达边界“{request.brand.content_role_boundary}”；"
                f"实际操作人“{request.brand.operator_name}”仅是操作者，不自动成为成品叙事人物。"
            ),
            confirmed_facts=facts,
            user_premise="\n".join(part for part in (request.weak_seed, request.revision_instruction) if part),
            brand_viewpoint=(
                f"品牌“{request.brand.brand_name}”可以依据已确认基线表达认为、希望、主张或建议；"
                "观点不得升级为操作人亲历、顾客案例、门店已经执行或普遍政策。"
            ),
            production_resources=(
                f"当前可用条件：{request.brand.production_conditions}。"
                "除此之外，只能使用本次已确认商品与可信资料明确提供的人物、设备、场地和素材；"
                "未明确提供即为当前不可用。话题中出现的对象不是可拍资源，当前创作者也不能"
                "扮演该对象。制作方法资料不证明某个人、实物、图片、场所陈设或既有素材真实可用；"
                "场地可用也不自动证明场地内的任何实物可用。"
            ),
            product_skus=tuple(product.sku for product in request.products),
            known_numbers=tuple(dict.fromkeys(numbers)),
            known_colors=tuple(dict.fromkeys(colors)),
            internal_identifiers=(
                request.brand.strategy_version,
                *(asset.asset_id for asset in request.active_domain_assets),
            ),
        )


ReasonCode = Literal[
    "untrusted_role",
    "invented_actuality",
    "unsupported_resource",
    "factual_conflict",
]


@dataclass(frozen=True)
class RepairIssue:
    field: str
    fragment: str
    reason_code: ReasonCode | Literal["media_contract"]


class DeepSeekGenerator(ContentGenerator):
    """Single-provider adapter for value routing and complete content compilation."""

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

    def route(self, request: RoutingInput) -> ContentProduct | None:
        payload, _ = self._request(
            "你是笛语内容任务路由器。只返回 JSON，不解释理由或展示推理。",
            self._routing_prompt(request),
            700,
        )
        try:
            value = json.loads(self._json_content(str(payload["choices"][0]["message"]["content"]))).get(
                "primary_value"
            )
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise GenerationFailed("模型路由返回格式不完整") from exc
        mapping: dict[str, ContentProduct | None] = {
            "普通交流": None,
            "帮助选择": "dressing_decision",
            "解释商品": "product_truth",
            "建立人格": "brand_life_narrative",
            "经营关系": "local_response",
            "视觉造型": "visual_styling_story",
        }
        if value in (None, "普通交流"):
            return None
        if not isinstance(value, str) or value not in mapping:
            raise GenerationFailed("模型路由返回了不支持的内容产品")
        return cast(ContentProduct, mapping[value])

    def generate(self, request: GenerationInput) -> GeneratedArtifact:
        started = time.monotonic()
        retries = 0
        format_repairs = 0
        provider_payloads: list[dict[str, Any]] = []
        context = BoundaryContext.from_request(request)
        payload: dict[str, Any]
        for format_attempt in range(2):
            system = "你是笛语完整内容编写器。只交付 JSON，不展示提示词、边界分类、证据、路由、规则或推理。"
            if format_attempt:
                system += (
                    "上一次响应的字段缺失、为空或不是单个字符串；这次必须返回全部指定 JSON "
                    "字段，且每个字段都是非空中文字符串。"
                )
            payload, request_retries = self._request(
                system,
                self._generation_prompt(request, context),
                4096,
            )
            provider_payloads.append(payload)
            retries += request_retries
            try:
                structured = json.loads(self._json_content(str(payload["choices"][0]["message"]["content"])))
                if request.media_format == "video":
                    structured = self._project_video_contract(request, structured)
                title, contract, production, body = self._compiled_artifact(request, structured)
                break
            except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
                if format_attempt:
                    raise GenerationFailed("模型返回格式不完整") from exc
                format_repairs = 1
        else:  # pragma: no cover - loop either returns a parsed result or raises.
            raise GenerationFailed("模型返回格式不完整")

        violations, judgement_payload, judgement_retries = self._check_boundary(
            request,
            context,
            structured,
        )
        provider_payloads.append(judgement_payload)
        retries += judgement_retries
        fact_repair_receipts: tuple[FactRepairReceipt, ...] = ()
        if violations:
            payload, repair_retries = self._request(
                ("你是笛语内容编写器。只交付待修字段 JSON，不展示边界分类、证据、规则、推理或后台信息。"),
                self._boundary_repair_prompt(structured, context, violations),
                4096,
            )
            provider_payloads.append(payload)
            retries += repair_retries
            try:
                repaired_fields = json.loads(self._json_content(str(payload["choices"][0]["message"]["content"])))
                structured = self._merge_repaired_fields(structured, violations, repaired_fields)
                if request.media_format == "video":
                    structured = self._project_video_contract(request, structured)
                title, contract, production, body = self._compiled_artifact(request, structured)
            except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
                raise GenerationFailed("模型边界修复返回格式不完整") from exc
            final_violations, judgement_payload, judgement_retries = self._check_boundary(
                request,
                context,
                structured,
            )
            provider_payloads.append(judgement_payload)
            retries += judgement_retries
            if final_violations:
                raise GenerationFailed("内容边界无法在一次字段修复内满足")
            fact_repair_receipts = self._repair_receipts(violations)
        usage = self._combined_usage(provider_payloads)
        return GeneratedArtifact(
            outline=title,
            body=body,
            model=self._model,
            latency_ms=int((time.monotonic() - started) * 1000),
            retry_count=retries + format_repairs,
            provider_usage=usage,
            primary_product=request.primary_product,
            semantic_contract=contract,
            production=production,
            fact_repair_receipts=fact_repair_receipts,
        )

    def _check_boundary(
        self,
        request: GenerationInput,
        context: BoundaryContext,
        structured: dict[str, object],
    ) -> tuple[tuple[RepairIssue, ...], dict[str, Any], int]:
        deterministic = self._deterministic_boundary_violations(context, structured)
        media = self._media_violations(request, structured)
        semantic, payload, retries = self._semantic_boundary_violations(context, structured)
        return tuple(dict.fromkeys(deterministic + media + semantic)), payload, retries

    def _semantic_boundary_violations(
        self,
        context: BoundaryContext,
        structured: dict[str, object],
    ) -> tuple[tuple[RepairIssue, ...], dict[str, Any], int]:
        fields = ", ".join(structured)
        payload, retries = self._request(
            (
                "你是笛语内容边界判定器。逐字段做完边界核对，只返回最终 JSON；"
                "不改写成品，不展示核对过程或推理。"
            ),
            f"""只依据本次临时边界判断候选成品。边界未明确提供的事实或资源一律视为不存在，
不能用常识、常见拍法或话题里出现的对象补足。

可信表达身份：
{context.trusted_identity}

已确认事实：
{context.confirmed_facts}

用户本次前提：
{context.user_premise}

品牌观点与条件性判断：
{context.brand_viewpoint}

当前可用制作资源：
{context.production_resources}

对每个候选字段分别核对以下四个问题；一个字段只要有一项成立，就至少返回该字段的一条违规，
同一字段不必穷举：
- untrusted_role：账号或当前创作者是否用第一人称、表演或叙事位置冒充了边界外的自然人或岗位。
  用户只是在话题中提到某类人，不构成账号具备该身份。
- invented_actuality：是否把观点、假设、话题对象或未知情况写成操作人亲历、真实案例、已经发生的
  动作/场景、门店已执行做法或普遍政策。品牌“认为、希望、主张、建议”不属于已发生事实。
  如果确认事实只有品牌观点、没有组织或场所的实际执行状态，任何用品牌口吻肯定描述当前服务、
  员工做法、现场安排或对外承诺的句子，都属于 invented_actuality，即使该做法符合品牌观点。
- unsupported_resource：画面、动作、声音或制作步骤是否实际需要边界未提供的人物、商品、图片、
  场地、设备、道具或既有素材。话题对象可以被口播抽象讨论，但不能因此成为演员、实物或现场。
- factual_conflict：是否与已确认品牌、商品、资料或明确作用域冲突。

不要误杀依据品牌基线表达的观点、条件性建议、普通视觉标题、当前创作者对手机口播、现有场地中的
中性动作，或从用户明确前提忠实改写的内容。关键区别是“谈论某个对象”不需要该资源，
“让该对象出镜、行动、发声或把事件拍成已经发生”需要当前依据。

候选 JSON：{json.dumps(structured, ensure_ascii=False)}
只返回：
{{"violations":[{{"field":"候选字段名","fragment":"该字段中原样连续片段",
"reason_code":"四类之一"}}]}}。
没有违规返回 {{"violations":[]}}。field 必须来自：{fields}；fragment 必须逐字存在于该字段且
是足以定位违规的最小连续片段。不得返回解释、理由、置信度、改写建议或候选中不存在的文字。""",
            2400,
        )
        try:
            result = json.loads(self._json_content(str(payload["choices"][0]["message"]["content"])))
            raw_violations = result["violations"]
            if not isinstance(raw_violations, list):
                raise TypeError("violations must be a list")
            violations: list[RepairIssue] = []
            for value in raw_violations:
                if not isinstance(value, dict):
                    raise TypeError("violation must be an object")
                field = value.get("field")
                fragment = value.get("fragment")
                reason_code = value.get("reason_code")
                candidate = structured.get(field) if isinstance(field, str) else None
                if (
                    not isinstance(field, str)
                    or field not in structured
                    or not isinstance(fragment, str)
                    or not fragment.strip()
                    or not isinstance(candidate, str)
                    or fragment not in candidate
                    or reason_code
                    not in {
                        "untrusted_role",
                        "invented_actuality",
                        "unsupported_resource",
                        "factual_conflict",
                    }
                ):
                    raise TypeError("semantic violation is not grounded in the candidate")
                violations.append(
                    RepairIssue(
                        field,
                        fragment,
                        cast(ReasonCode, reason_code),
                    )
                )
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise GenerationFailed("模型边界判定返回格式不完整") from exc
        return tuple(dict.fromkeys(violations)), payload, retries

    @staticmethod
    def _combined_usage(payloads: list[dict[str, Any]]) -> dict[str, int] | None:
        totals: dict[str, int] = {}
        for payload in payloads:
            usage = payload.get("usage")
            if not isinstance(usage, dict):
                continue
            for key, value in usage.items():
                if isinstance(value, int):
                    totals[str(key)] = totals.get(str(key), 0) + value
        return totals or None

    def _request(self, system: str, prompt: str, max_tokens: int) -> tuple[dict[str, Any], int]:
        retries = 0
        request_payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            # Fact-bound JSON must not drift through stochastic rewording. A
            # revision still changes when its explicit instruction changes.
            "temperature": 0.0,
            "max_tokens": max_tokens,
            # The current provider enables reasoning by default.  This adapter
            # needs a complete JSON object in the visible content channel, not
            # an open-ended reasoning pass that can exhaust the response budget.
            "thinking": {"type": "disabled"},
            "response_format": {"type": "json_object"},
        }
        with httpx.Client(timeout=httpx.Timeout(self._timeout_seconds)) as client:
            while True:
                try:
                    response = client.post(
                        f"{self._api_base_url}/chat/completions",
                        headers={"Authorization": f"Bearer {self._api_key}"},
                        json=request_payload,
                    )
                    if response.status_code < 400:
                        result = response.json()
                        if not isinstance(result, dict):
                            raise GenerationFailed("模型返回无效")
                        return result, retries
                    if response.status_code != 429 and not 500 <= response.status_code < 600:
                        raise GenerationFailed("模型服务拒绝当前请求")
                    if retries >= self._max_retries:
                        raise GenerationFailed("模型服务暂时不可用")
                    delay = self._retry_delay(response.headers.get("Retry-After"), retries)
                except httpx.TransportError as exc:
                    if retries >= self._max_retries:
                        raise GenerationFailed("模型网络请求失败") from exc
                    delay = min(4.0, 0.5 * (2**retries))
                retries += 1
                time.sleep(delay)

    @staticmethod
    def _project_video_contract(
        request: GenerationInput,
        structured: dict[str, object],
    ) -> dict[str, object]:
        """Derive subtitles and truthful duration from the final spoken copy."""
        projected = dict(structured)
        spoken = DeepSeekGenerator._visible_text(projected["spoken_lines"])
        if DeepSeekGenerator._is_no_voice(spoken):
            return projected
        subtitle = DeepSeekGenerator._visible_text(projected["subtitles"])
        projected["subtitles"] = subtitle if DeepSeekGenerator._subtitle_is_grounded(spoken, subtitle) else spoken
        fixed_seconds = DeepSeekGenerator._fixed_duration_seconds(request.brand.production_conditions)
        projected["natural_duration"] = (
            f"{fixed_seconds} 秒"
            if fixed_seconds is not None
            else f"约 {DeepSeekGenerator._natural_spoken_seconds(spoken)} 秒"
        )
        return projected

    @staticmethod
    def _compiled_artifact(
        request: GenerationInput, structured: dict[str, object]
    ) -> tuple[str, ContentSemanticContract, ContentProductionBundle, str]:
        title = DeepSeekGenerator._visible_text(structured["title"])
        contract = DeepSeekGenerator._contract(request.primary_product, structured)
        production: ContentProductionBundle
        if request.media_format == "video":
            production = VideoProductionBundle(
                natural_guide=DeepSeekGenerator._visible_text(structured["natural_guide"]),
                spoken_lines=DeepSeekGenerator._visible_text(structured["spoken_lines"]),
                visual_actions=DeepSeekGenerator._visible_text(structured["visual_actions"]),
                subtitles=DeepSeekGenerator._visible_text(structured["subtitles"]),
                sound_and_production=DeepSeekGenerator._visible_text(structured["sound_and_production"]),
                cover_or_first_frame=DeepSeekGenerator._visible_text(structured["cover_or_first_frame"]),
                viewing_flow=DeepSeekGenerator._visible_text(structured["viewing_flow"]),
                natural_duration=DeepSeekGenerator._visible_text(structured["natural_duration"]),
                release_caption_and_interaction=DeepSeekGenerator._visible_text(
                    structured["release_caption_and_interaction"]
                ),
            )
        else:
            production = GraphicProductionBundle(
                natural_guide=DeepSeekGenerator._visible_text(structured["natural_guide"]),
                hero_image=DeepSeekGenerator._visible_text(structured["hero_image"]),
                image_sequence=DeepSeekGenerator._visible_text(structured["image_sequence"]),
                full_body=DeepSeekGenerator._visible_text(structured["full_body"]),
                layout_and_production=DeepSeekGenerator._visible_text(structured["layout_and_production"]),
                release_caption_and_interaction=DeepSeekGenerator._visible_text(
                    structured["release_caption_and_interaction"]
                ),
            )
        return (
            title,
            contract,
            production,
            DeepSeekGenerator._visible_body(title, production, contract),
        )

    @staticmethod
    def _deterministic_boundary_violations(
        context: BoundaryContext,
        structured: dict[str, object],
    ) -> tuple[RepairIssue, ...]:
        """Keep exact identifiers and concrete product values on trusted rails."""
        violations: list[RepairIssue] = []
        internal_identifier = re.compile(
            r"(?:schema[_ -]?version|asset[_ -]?id|DIYU-[A-Z0-9-]+)",
            re.IGNORECASE,
        )
        personal_identifier = re.compile(r"1[3-9]\d{9}|[\w.+-]+@[\w.-]+|订单号?\s*[:：]?\s*[A-Za-z0-9-]+")
        sku_pattern = re.compile(r"\b[A-Z]{2,}(?:-[A-Z0-9]+)+\b")
        measured_value = re.compile(r"(?<!\d)(\d{1,6})\s*(?:克|元|%|厘米|cm)\b", re.IGNORECASE)
        colour = re.compile(r"(黑色|白色|蓝色|红色|黄色|紫色|棕色|灰色|绿色|炭灰|深绿)")
        for field, value in structured.items():
            text = DeepSeekGenerator._visible_text(value)
            for identifier in context.internal_identifiers:
                if identifier and identifier in text:
                    violations.append(RepairIssue(field, identifier, "factual_conflict"))
            for pattern in (internal_identifier, personal_identifier):
                for match in pattern.finditer(text):
                    violations.append(
                        RepairIssue(
                            field,
                            match.group(0),
                            "factual_conflict",
                        )
                    )
            for sku in sku_pattern.findall(text):
                if sku not in context.product_skus:
                    violations.append(RepairIssue(field, sku, "factual_conflict"))
            if not context.product_skus:
                continue
            product_specific = bool(
                any(sku in text for sku in context.product_skus)
                or re.search(r"(?:当前商品|这件商品|该商品|当前样衣)", text)
            )
            if not product_specific:
                continue
            for match in measured_value.finditer(text):
                if int(match.group(1)) not in context.known_numbers:
                    violations.append(
                        RepairIssue(
                            field,
                            match.group(0),
                            "factual_conflict",
                        )
                    )
            if context.known_colors:
                for match in colour.finditer(text):
                    if not any(match.group(1) in known for known in context.known_colors):
                        violations.append(
                            RepairIssue(
                                field,
                                match.group(0),
                                "factual_conflict",
                            )
                        )
        return tuple(dict.fromkeys(violations))

    @staticmethod
    def _media_violations(
        request: GenerationInput,
        structured: dict[str, object],
    ) -> tuple[RepairIssue, ...]:
        if request.media_format != "video":
            return ()
        spoken = DeepSeekGenerator._visible_text(structured["spoken_lines"])
        if DeepSeekGenerator._is_no_voice(spoken):
            return ()
        fixed_seconds = DeepSeekGenerator._fixed_duration_seconds(request.brand.production_conditions)
        if fixed_seconds is not None and DeepSeekGenerator._natural_spoken_seconds(spoken) > fixed_seconds:
            return (RepairIssue("spoken_lines", spoken, "media_contract"),)
        return ()

    @staticmethod
    def _natural_spoken_seconds(spoken: str) -> int:
        readable = len(re.findall(r"[\u4e00-\u9fff]|[A-Za-z0-9]+", spoken))
        pauses = len(re.findall(r"[。！？!?；;\n]", spoken))
        return max(1, (readable + 3) // 4 + (pauses + 1) // 2)

    @staticmethod
    def _fixed_duration_seconds(production_conditions: str) -> int | None:
        match = re.search(r"(?<!\d)(\d{1,3})\s*秒", production_conditions)
        return int(match.group(1)) if match else None

    @staticmethod
    def _is_no_voice(spoken: str) -> bool:
        normalized = re.sub(r"[\s、，,。；;]+", "", spoken)
        return normalized in {"无口播无对白无解说", "无口播"}

    @staticmethod
    def _subtitle_is_grounded(spoken: str, subtitle: str) -> bool:
        """Allow an ordered compression, never a second vocabulary of facts."""
        spoken_tokens = re.findall(r"[\u4e00-\u9fff]|[A-Za-z0-9]+", spoken)
        subtitle_tokens = re.findall(r"[\u4e00-\u9fff]|[A-Za-z0-9]+", subtitle)
        if not subtitle_tokens:
            return False
        cursor = iter(spoken_tokens)
        return all(any(token == candidate for candidate in cursor) for token in subtitle_tokens)

    @staticmethod
    def _merge_repaired_fields(
        draft: dict[str, object],
        violations: tuple[RepairIssue, ...],
        repaired_fields: object,
    ) -> dict[str, object]:
        if not isinstance(repaired_fields, dict):
            raise TypeError("boundary repair must be an object")
        requested = tuple(dict.fromkeys(violation.field for violation in violations))
        if set(repaired_fields) != set(requested):
            raise TypeError("boundary repair fields do not match the requested fields")
        merged = dict(draft)
        for field in requested:
            merged[field] = DeepSeekGenerator._visible_text(repaired_fields[field])
        return merged

    @staticmethod
    def _repair_receipts(
        violations: tuple[RepairIssue, ...],
    ) -> tuple[FactRepairReceipt, ...]:
        by_field: dict[str, list[str]] = {}
        for violation in violations:
            by_field.setdefault(violation.field, []).append(violation.fragment)
        return tuple(FactRepairReceipt(field, tuple(dict.fromkeys(fragments))) for field, fragments in by_field.items())

    @staticmethod
    def _contract(product: ContentProduct, payload: dict[str, object]) -> ContentSemanticContract:
        fields = _CONTRACT_FIELDS[product]
        values = tuple(DeepSeekGenerator._visible_text(payload[field]) for field in fields)
        if product == "dressing_decision":
            return P1SemanticContract(*values)
        if product == "product_truth":
            return P2SemanticContract(*values)
        if product == "brand_life_narrative":
            return P3SemanticContract(*values)
        if product == "local_response":
            return P4SemanticContract(*values)
        return P5SemanticContract(*values)

    @staticmethod
    def _json_content(content: str) -> str:
        stripped = content.strip()
        if stripped.startswith("```") and stripped.endswith("```"):
            stripped = re.sub(r"^```(?:json)?\s*", "", stripped, count=1, flags=re.IGNORECASE)
            stripped = re.sub(r"\s*```$", "", stripped, count=1)
        return stripped

    @staticmethod
    def _visible_text(value: object) -> str:
        """Remove only reserved routing labels before a model response reaches a user artifact."""
        if not isinstance(value, str) or not value.strip():
            raise TypeError("visible content must be a non-empty string")
        visible = re.sub(
            r"\b(?:P[1-5]|dressing_decision|product_truth|brand_life_narrative|local_response|visual_styling_story)\b\s*[:：-]?\s*",
            "",
            str(value),
            flags=re.IGNORECASE,
        ).strip()
        if not re.search(r"[\w\u4e00-\u9fff]", visible):
            raise TypeError("visible content must contain readable text")
        return visible

    @staticmethod
    def _visible_body(
        title: str,
        production: ContentProductionBundle,
        contract: ContentSemanticContract | None = None,
    ) -> str:
        if isinstance(production, VideoProductionBundle):
            sections: tuple[tuple[str, str], ...] = (
                ("自然导读", production.natural_guide),
                ("封面/首帧", production.cover_or_first_frame),
                ("完整观看链", production.viewing_flow),
                ("完整台词/解说", production.spoken_lines),
                ("画面与动作", production.visual_actions),
                ("字幕", production.subtitles),
                ("声音与制作提示", production.sound_and_production),
                ("自然时长", production.natural_duration),
                ("发布配文与互动", production.release_caption_and_interaction),
            )
        elif isinstance(production, GraphicProductionBundle):
            sections = (
                ("自然导读", production.natural_guide),
                ("首图方案", production.hero_image),
                ("图序与每张职责", production.image_sequence),
                ("完整发布正文", production.full_body),
                ("拍摄/排版提示", production.layout_and_production),
                ("发布配文与互动", production.release_caption_and_interaction),
            )
        else:  # Backward-compatible helper for pre-M5-2 deterministic test fixtures.
            legacy = cast(Any, production)
            sections = (
                ("自然导读", legacy.natural_guide),
                ("完整台词/解说", legacy.spoken_lines),
                ("画面与动作", legacy.visual_actions),
                ("字幕", legacy.subtitles),
                ("声音与制作提示", legacy.sound_and_production),
            )
        contract_sections: tuple[tuple[str, str], ...] = ()
        if isinstance(contract, P2SemanticContract):
            contract_sections = (
                ("商品新增理解", contract.product_insight),
                ("限制", contract.tradeoff_or_limit),
                ("成立边界", contract.validity_condition),
            )
        elif isinstance(contract, P1SemanticContract):
            contract_sections = (
                ("当前选择", contract.choice),
                ("改变条件", contract.boundary),
                ("下一步", contract.next_action),
            )
        elif isinstance(contract, P3SemanticContract):
            contract_sections = (
                ("账号观察", contract.persona_observation),
                ("受众获得", contract.audience_return),
                ("账号关系", contract.brand_account_link),
            )
        elif isinstance(contract, P4SemanticContract):
            contract_sections = (
                ("近场信号", contract.local_reality_or_signal),
                ("账号回应", contract.legitimate_account_response),
                ("公开关系回报", contract.public_relationship_return),
            )
        elif isinstance(contract, P5SemanticContract):
            contract_sections = (
                ("真实商品锚点", contract.real_product_anchor),
                ("可见造型命题", contract.visible_styling_proposition),
                ("画面成立条件", contract.visual_dependency),
            )
        transform_sections: tuple[tuple[str, str], ...] = ()
        if isinstance(production, VideoProductionBundle) and re.search(r"(?<!\d)8\s*秒", production.natural_duration):
            transform_sections = (("变换边界", "这是 8 秒窄主题版，不等同于原完整版本。"),)
        return (
            "标题："
            + title
            + "\n\n"
            + "\n\n".join(f"{heading}：{value}" for heading, value in contract_sections + transform_sections + sections)
        )

    @staticmethod
    def _retry_delay(retry_after: str | None, retries: int) -> float:
        if retry_after:
            try:
                return min(8.0, max(0.0, float(retry_after)))
            except ValueError:
                try:
                    return min(8.0, max(0.0, parsedate_to_datetime(retry_after).timestamp() - time.time()))
                except (TypeError, ValueError):
                    pass
        return float(min(4.0, 0.5 * (2**retries)))

    @staticmethod
    def _routing_prompt(request: RoutingInput) -> str:
        products = ", ".join(product.sku for product in request.products) or "无已点名商品"
        return f"""判断当前内容工作台输入是否已形成内容任务。只返回 JSON：{{\"primary_value\": \"普通交流\" 或一个自然语言价值}}。
可选自然价值：帮助选择、解释商品、建立人格、经营关系、视觉造型。
按主要受众最终获得的价值判断；只有纯问候或情绪交流返回普通交流。凡是要求把具体商品观察、选择疑问、账号观察、近场回应或画面设想做成可发布内容的输入，必须选择一个内容价值，不能回落为普通交流。独立、可单独采用的新成果重新判断。
帮助选择强调条件、改变条件和下一步；解释商品强调已知事实、限制与不能下的结论；建立人格强调账号怎样观察、判断和待人；经营关系强调近场信号、合法回应和可迁移许可；视觉造型强调必须由画面承重的穿着可能。
解释商品必须以当前已点名且有已确认事实的商品为对象；当前没有已点名商品时不得选择解释商品。品牌、账号或家庭生活观点主要让受众认识账号怎样观察、判断和待人时，选择建立人格。
经营关系必须有用户明确给出的真实评论、门店观察或近场事件；只有一个假设、一般问题或品牌关系观点而没有真实近场信号时，选择建立人格，不能把问题补成门店事实。当输入的主回报是让没到店、未参与原事件的人带走一句可迁移的门店关系许可，且已经有真实近场信号时，即使同时提到店长性格、商品或镜头，也选经营关系。只有主回报是让受众认识账号/店长怎样观察、判断和待人，才选建立人格。明确要求“同一个人、同一动作、两面在画面中换重音”，且不要选择建议或商品说明时，选视觉造型；明确要求解释“双面不等于一件顶两件”、说明已知与未知时，选解释商品。
品牌：{request.brand.brand_name}；账号：{request.brand.account_name}；角色：{request.brand.content_role_name}；受众：{request.brand.audience_description}。
当前已点名商品：{products}。
用户输入：{request.weak_seed}"""

    @staticmethod
    def _generation_prompt(
        request: GenerationInput,
        context: BoundaryContext | None = None,
    ) -> str:
        boundary = context or BoundaryContext.from_request(request)
        fields = ", ".join(_CONTRACT_FIELDS[request.primary_product])
        prior = request.prior_saved_body or "（未授权复用旧正文）"
        revision = request.revision_instruction or "（首次生成）"
        source = request.source_version_description or "（不是跨目标重编译）"
        fixed_seconds = DeepSeekGenerator._fixed_duration_seconds(request.brand.production_conditions)
        transform_boundary = (
            f"用户明确要求 {fixed_seconds} 秒；完整口播必须真实适配，不要只改时长标签。"
            if fixed_seconds is not None
            else "用户未要求固定时长；保留完整口播，由服务端根据最终口播形成自然时长。"
        )
        if request.media_format == "video":
            media_contract = (
                "交付可直接拍摄、表演、录音和剪辑的完整观看链。口播必须完整自然；"
                "字幕将由服务端从最终口播同源形成。声音和动作只能使用当前画面与可用资源，"
                "不能另造人物、商品、场地、道具、既有图片或事件。没有明确提供实物时，"
                "用当前创作者面对手机口播、手势或屏幕文字承担画面，不安排话题对象出镜。"
            )
            media_fields = (
                "natural_guide, cover_or_first_frame, viewing_flow, spoken_lines, visual_actions, subtitles, "
                "sound_and_production, natural_duration, release_caption_and_interaction"
            )
        else:
            media_contract = (
                "交付可直接拍摄、选图、排版和发布的完整阅读链。首图、图序、完整正文与制作提示闭合，只使用当前可用资源。"
            )
            media_fields = (
                "natural_guide, hero_image, image_sequence, full_body, layout_and_production, "
                "release_caption_and_interaction"
            )
        return f"""为“{request.brand.account_name}”编译一个完整中文{request.brand.media_format}文字制作成品。
本次受众价值：{_PRODUCT_VALUE[request.primary_product]}；必须只兑现这一价值，不说明路由。
本次交付门：{_DELIVERABLE_REQUIREMENTS[request.primary_product]}
当前媒体合同：{media_contract}
受众：{request.brand.audience_description}；平台/形式：{request.brand.platform}／{request.brand.media_format}。
目标平台方向：{request.platform_direction.direction}
当前变形边界：{transform_boundary}

可信表达身份：
{boundary.trusted_identity}

已确认事实：
{boundary.confirmed_facts}

用户本次前提：
{boundary.user_premise}

品牌观点与条件性判断：
{boundary.brand_viewpoint}

当前可用制作资源：
{boundary.production_resources}

已授权前情：{prior}
来源关系：{source}
本次修改：{revision}

明确区分讨论对象、说话身份、确认事实、品牌观点和可用制作资源：
- 话题中出现对象不表示账号或创作者就是该对象，也不表示事件已经发生或对象可供拍摄；
- 第一人称只能表达当前品牌观点或当前拍摄动作，不能补写操作人的生活经历、刚刚做过的事、
  顾客案例、门店经历或研发过程；
- 品牌观点用“我们认为、希望、主张或建议”等立场表达，不能写成门店已经执行的服务或普遍政策；
- 画面、动作和声音逐项只使用当前可用资源。没有明确提供的人物、商品、衣物、图片、门店、
  家具或道具不能被安排出镜；一般颜色、品类和搭配只可作为明确的假设例子被口播讨论。
  可用条件存在多个替代项时，采用能完成内容的最小资源组合；不为了丰富画面自动选择人物、
  实物、门店或既有素材。
可以自然表达观点、假设、比喻和条件性建议；不能新增未确认的角色、亲历、案例、已执行事实、
商品事实或制作资源。不要输出个人标识、内部标识、上下文分类、证据或审查过程。

跨目标重编译时只重组入口、顺序、声画或图文分工和制作方式；不得把旧版说成已经采用或发布。
严格返回 JSON，字段：title, {fields}, {media_fields}。不要返回 body。每个字段必须是一个非空中文字符串，绝不能是数组、对象或多条列表。三个合同字段必须在完整成品中以自然语言兑现，不要求逐字复制、塞入同一句或在每个媒体字段重复。"""

    @staticmethod
    def _boundary_repair_prompt(
        draft: dict[str, object],
        context: BoundaryContext,
        violations: tuple[RepairIssue, ...],
    ) -> str:
        fields = tuple(dict.fromkeys(violation.field for violation in violations))
        issue_text = "\n".join(
            f"- {violation.field} | {violation.reason_code} | {violation.fragment}" for violation in violations
        )
        candidate = {field: DeepSeekGenerator._visible_text(draft[field]) for field in fields}
        return f"""只修复下列字段；不得返回任何未列字段，服务端会保留其余合格字段。
不要删除整篇的主要价值，也不要用固定安全文案代替成品。只让字段重新满足本次边界。

可信表达身份：{context.trusted_identity}
已确认事实：{context.confirmed_facts}
用户本次前提：{context.user_premise}
品牌观点与条件性判断：{context.brand_viewpoint}
当前可用制作资源：{context.production_resources}

待修字段原文：{json.dumps(candidate, ensure_ascii=False)}
定位到的问题：
{issue_text}

若问题是 media_contract，必须真实缩短口播以适配用户指定时长；不能只改时长标签。
身份或现实主张越界时，保留原话题价值，改成当前品牌明确标示的观点、建议或条件性判断，
不能继续让账号扮演话题人物，也不能保留没有依据的亲历、案例或已执行事实。
制作资源越界时，保留原内容职责，改用当前明确提供的创作者、手机和场地内的中性动作；
话题人物、商品、图片和道具只可被抽象谈论，不能被安排出镜或当成已经持有的素材。
不要输出分类、证据、审查过程或解释。
严格只返回一个 JSON 对象，键必须恰好为：{", ".join(fields)}。每个值必须是对应字段修复后的非空中文字符串。"""

    @staticmethod
    def _natural_product(sku: str, facts: dict[str, object]) -> str:
        category = DeepSeekGenerator._natural_category(facts.get("category"))
        raw_colors = facts.get("colors")
        colors = (
            "、".join(value for value in raw_colors if isinstance(value, str)) if isinstance(raw_colors, list) else ""
        )
        weight = facts.get("sample_weight_m_grams")
        comparison = facts.get("comparison_single_layer_short_coat_m_grams")
        both_sides_complete = facts.get("both_sides_complete")
        both_sides = (
            "两面均为完整外观"
            if both_sides_complete is True
            else "两面完整外观情况未提供"
            if both_sides_complete is None
            else "两面完整外观未得到确认"
        )
        functional_pockets = facts.get("pockets_functional_both_sides")
        pockets = (
            "两面口袋均可正常使用"
            if functional_pockets is True
            else "两面口袋可用性未提供"
            if functional_pockets is None
            else "两面口袋不能确认均可正常使用"
        )
        weight_boundary = DeepSeekGenerator._weight_boundary(facts.get("weight_boundary"))
        return (
            f"商品 {sku}（{category}）：颜色为{colors or '未提供'}；{both_sides}；{pockets}；"
            f"M 码当前样衣为{weight if isinstance(weight, int) else '未提供'}克；"
            f"同季同长度单层短外套 M 码样衣为{comparison if isinstance(comparison, int) else '未提供'}克；"
            f"{weight_boundary}"
        )

    @staticmethod
    def _weight_boundary(value: object) -> str:
        if (
            value
            == "only the current sample weight difference is known; do not attribute all difference to the double-faced structure"
        ):
            return "当前只知道这两份样衣存在重量差异；没有结构测试，现有资料无法归因。"
        if isinstance(value, str) and value.strip():
            return "当前重量边界已登记；只能以两份样衣的已记录重量为准，不能从重量推断其他未测试性质。"
        return "当前只可确认已记录的样衣重量，不能从重量推断其他性质。"

    @staticmethod
    def _natural_category(value: object) -> str:
        if value == "double-faced short coat":
            return "双面短外套"
        return "类别未提供"
