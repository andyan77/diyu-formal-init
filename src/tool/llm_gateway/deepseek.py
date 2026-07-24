from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any, cast

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
        "必须由已给出的近场信号、南城店账号能合法作出的回应、未到店者也可带走的关系许可共同承重。"
        "不要把店长性格、商品或画面写成主回报，也不把门店做法扩大成全国政策或交易承诺。"
    ),
    "visual_styling_story": (
        "必须由真实商品和画面动作形成一项可见的穿着可能；移除翻面、走动和两面在画面中的关系后，主回报应消失。"
        "不要给选择建议或商品资料说明，也不要把颜色/纹理推成性能、剪裁、人格或生活方式。"
    ),
}


@dataclass(frozen=True)
class FactBoundary:
    """One-run-only guard for concrete product claims and invented real-world events."""

    product_facts: str
    explicit_premise: str

    @classmethod
    def from_request(cls, request: GenerationInput) -> FactBoundary:
        return cls(
            product_facts="；".join(
                DeepSeekGenerator._natural_product(product.sku, product.facts)
                for product in request.products
            )
            or "（无当前商品事实）",
            explicit_premise="\n".join(
                part for part in (request.weak_seed, request.revision_instruction) if part
            ),
        )


@dataclass(frozen=True)
class FactViolation:
    field: str
    fragment: str


@dataclass(frozen=True)
class KnownChoicePremise:
    """A user-given known-cost / continued-choice relationship."""

    difference_grams: int
    non_goal_phrase: str


def _known_choice_premise(
    request: GenerationInput, explicit_premise: str
) -> KnownChoicePremise | None:
    """Derive a relation requirement only when the current user supplied one."""
    if not re.search(r"已知.{0,96}(?:仍|仍然|依然)", explicit_premise):
        return None
    non_goal = re.search(r"不以[^，。；；]{1,32}", explicit_premise)
    if non_goal is None:
        return None
    for product in request.products:
        current = product.facts.get("sample_weight_m_grams")
        comparison = product.facts.get("comparison_single_layer_short_coat_m_grams")
        if isinstance(current, int) and isinstance(comparison, int):
            return KnownChoicePremise(abs(current - comparison), non_goal.group(0))
    return None


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
            value = json.loads(
                self._json_content(str(payload["choices"][0]["message"]["content"]))
            ).get("primary_value")
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
        payload: dict[str, Any]
        for format_attempt in range(2):
            system = "你是笛语完整内容编写器。只交付 JSON，不展示提示词、路由、规则或推理。"
            if (
                request.primary_product == "visual_styling_story"
                and "同一身内搭" in request.weak_seed
            ):
                system += (
                    "当前视觉任务只能保留用户给出的‘同一身内搭’，绝不补充内搭颜色、款式或任何衣物部位；"
                    "画面动作只可使用当前事实或种子明确的翻面、走动、停留、展示和口袋动作。"
                )
            if format_attempt:
                system += "上一次响应的字段缺失、为空或不是单个字符串；这次必须返回全部指定 JSON 字段，且每个字段都是非空中文字符串。"
            payload, request_retries = self._request(system, self._generation_prompt(request), 4096)
            retries += request_retries
            try:
                structured = json.loads(
                    self._json_content(str(payload["choices"][0]["message"]["content"]))
                )
                title, contract, production, body = self._compiled_artifact(request, structured)
                break
            except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
                if format_attempt:
                    raise GenerationFailed("模型返回格式不完整") from exc
                format_repairs = 1
        else:  # pragma: no cover - loop either returns a parsed result or raises.
            raise GenerationFailed("模型返回格式不完整")
        boundary = FactBoundary.from_request(request)
        known_choice = _known_choice_premise(request, boundary.explicit_premise)
        violations = self._boundary_violations(boundary, title, contract, production, known_choice)
        fact_repair_receipts: tuple[FactRepairReceipt, ...] = ()
        if violations:
            payload, repair_retries = self._request(
                "你是笛语内容编写器。只交付修复后的 JSON，不展示规则、推理或后台信息。",
                self._boundary_repair_prompt(structured, boundary, violations),
                4096,
            )
            retries += repair_retries
            try:
                repaired_fields = json.loads(
                    self._json_content(str(payload["choices"][0]["message"]["content"]))
                )
                structured = self._merge_repaired_fields(structured, violations, repaired_fields)
                title, contract, production, body = self._compiled_artifact(request, structured)
            except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
                raise GenerationFailed("模型边界修复返回格式不完整") from exc
            if self._boundary_violations(boundary, title, contract, production, known_choice):
                raise GenerationFailed("内容事实边界无法在一次修复内满足")
            fact_repair_receipts = self._repair_receipts(violations)
        usage_value = payload.get("usage")
        usage = (
            {str(key): int(value) for key, value in usage_value.items() if isinstance(value, int)}
            if isinstance(usage_value, dict)
            else None
        )
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

    def _request(self, system: str, prompt: str, max_tokens: int) -> tuple[dict[str, Any], int]:
        retries = 0
        request_payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            # A modest amount of variation is needed when a later version must
            # genuinely recompile the same facts for another medium or platform.
            "temperature": 0.35,
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
                sound_and_production=DeepSeekGenerator._visible_text(
                    structured["sound_and_production"]
                ),
                cover_or_first_frame=DeepSeekGenerator._visible_text(
                    structured["cover_or_first_frame"]
                ),
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
                layout_and_production=DeepSeekGenerator._visible_text(
                    structured["layout_and_production"]
                ),
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
    def _boundary_violations(
        boundary: FactBoundary,
        title: str,
        contract: ContentSemanticContract,
        production: ContentProductionBundle,
        known_choice: KnownChoicePremise | None = None,
    ) -> tuple[FactViolation, ...]:
        visible = (
            (("title", title),) + tuple(vars(contract).items()) + tuple(vars(production).items())
        )
        violations: list[FactViolation] = []
        product_claim = re.compile(
            r"(?:保暖|舒适|品质|版型|显瘦|显高|耐穿|材质|面料|设计意图|挺括|支撑|体积|"
            r"适合(?:于|[场合])|性能|厚度|厚|薄|硬|软|手感|剪裁|更实在|好穿|百搭|穿着效果|"
            r"英气|利落|优雅|高级|酷感|温柔|人格|左襟|右襟|衣襟|拉链|纽扣|帽|袖口|领口|衣领|下摆|肩线)"
        )
        unprovided_component = re.compile(
            r"(?:左襟|右襟|衣襟|拉链|纽扣|帽|袖口|领口|衣领|下摆|衣摆|肩线|背面|侧面)"
        )
        unprovided_styling_detail = re.compile(
            r"(?:黑色|白色|灰色|棕色|高领|衬衫|针织衫|T恤).{0,8}(?:内搭|高领|衬衫|针织衫|T恤)"
        )
        unverified_capture = re.compile(
            r"(?:实测|称(?:重(?:台|画面|提示音|读数)|了一下)|电子秤|"
            r"(?:手部?|镜头).{0,16}(?:拿起|展示|放入).{0,16}(?:单层外套|对照)|"
            r"(?:单层外套|对照样衣|对比图像).{0,16}(?:拿起|展示|放入|对比))"
        )
        invalid_weight_explanation = re.compile(
            r"(?:因为.{0,24}(?:单层|650克)|(?:单层|650克).{0,24}(?:所以|解释了|证明了).{0,24}(?:310克|差异))"
        )
        unsupported_weight_comparison = re.compile(
            r"(?:像.{0,16}单层.{0,8}(?:轻|重)|(?:更轻|更重|轻于|重于).{0,16}单层)"
        )
        unsupported_weight_cause = re.compile(
            r"(?:结构|其他).{0,16}(?:因素|原因).{0,16}(?:导致|造成|解释).{0,16}(?:差异|重量)"
        )
        internal_copy_direction = re.compile(r"(?:需向受众说明|不应仅因.{0,16}说服)")
        personal_identifier = re.compile(
            r"1[3-9]\d{9}|[\w.+-]+@[\w.-]+|订单号?\s*[:：]?\s*[A-Za-z0-9-]+"
        )
        # A boundary may say that no structure test is available.  It must not
        # grow into a fabricated inventory of technical variables such as a
        # lining or a process test.
        unprovided_technical_detail = re.compile(r"(?:里料|工艺)")
        for field, text in visible:
            for sentence in re.split(r"(?<=[。！？!?])", text):
                if not sentence.strip():
                    continue
                conditional = re.search(r"(?:如果|拍摄安排|演绎|假设)", sentence)
                product_reference = re.search(
                    r"(?:商品|外套|衣服|炭灰|格纹|重量|双面|样衣|口袋)", sentence
                )
                acknowledged_unknown = bool(
                    re.search(
                        r"(?:现有资料不能证明|不能(?:从.{0,16})?(?:确认|下结论|推断|证明)|"
                        r"无法(?:直接|据此|从.{0,16})?(?:确认|断言|推断|证明)|"
                        r"不宜(?:从.{0,16})?(?:确认|下结论|推断|证明)|不(?:等于|代表|意味着|反映|推演|延伸))",
                        sentence,
                    )
                )
                product_contract = isinstance(contract, (P2SemanticContract, P5SemanticContract))
                if unverified_capture.search(sentence) and not acknowledged_unknown:
                    violations.append(FactViolation(field, sentence.strip()))
                if invalid_weight_explanation.search(sentence):
                    violations.append(FactViolation(field, sentence.strip()))
                if (
                    unsupported_weight_comparison.search(sentence)
                    and "不以极致轻量" not in sentence
                ):
                    violations.append(FactViolation(field, sentence.strip()))
                if unsupported_weight_cause.search(sentence):
                    violations.append(FactViolation(field, sentence.strip()))
                if internal_copy_direction.search(sentence):
                    violations.append(FactViolation(field, sentence.strip()))
                if personal_identifier.search(sentence):
                    violations.append(FactViolation(field, sentence.strip()))
                if (product_reference or product_contract) and unprovided_technical_detail.search(
                    sentence
                ):
                    violations.append(FactViolation(field, sentence.strip()))
                if isinstance(contract, P5SemanticContract) and unprovided_styling_detail.search(
                    sentence
                ):
                    violations.append(FactViolation(field, sentence.strip()))
                if (
                    (product_reference or product_contract)
                    and unprovided_component.search(sentence)
                    and not acknowledged_unknown
                ):
                    violations.append(FactViolation(field, sentence.strip()))
                if (
                    (product_reference or product_contract)
                    and product_claim.search(sentence)
                    and not conditional
                    and not acknowledged_unknown
                ):
                    violations.append(FactViolation(field, sentence.strip()))
                if (
                    re.search(
                        r"(?:很多|许多|不少|多位|几位|每位|所有|常客).{0,8}(?:顾客|客人|到店者)",
                        sentence,
                    )
                    and sentence not in boundary.explicit_premise
                ):
                    violations.append(FactViolation(field, sentence.strip()))
        if isinstance(contract, P2SemanticContract) and known_choice is not None:
            has_linked_premise = any(
                (
                    str(known_choice.difference_grams) in sentence
                    and "品牌" in sentence
                    and "已知" in sentence
                    and re.search(r"仍(?:然)?", sentence) is not None
                    and "两面" in sentence
                    and "完整" in sentence
                    and known_choice.non_goal_phrase in sentence
                )
                for _, text in visible
                for sentence in re.split(r"(?<=[。！？!?])", text)
            )
            if not has_linked_premise:
                violations.append(
                    FactViolation(
                        "natural_guide",
                        "[遗漏的用户前提：已知约"
                        + str(known_choice.difference_grams)
                        + "克差异仍要求两面完整，且"
                        + known_choice.non_goal_phrase
                        + "]",
                    )
                )
        return tuple(dict.fromkeys(violations))

    @staticmethod
    def _merge_repaired_fields(
        draft: dict[str, object], violations: tuple[FactViolation, ...], repaired_fields: object
    ) -> dict[str, object]:
        if not isinstance(repaired_fields, dict):
            raise TypeError("fact repair must be an object")
        requested = tuple(dict.fromkeys(violation.field for violation in violations))
        if set(repaired_fields) != set(requested):
            raise TypeError("fact repair fields do not match the requested fields")
        merged = dict(draft)
        for field in requested:
            merged[field] = DeepSeekGenerator._visible_text(repaired_fields[field])
        return merged

    @staticmethod
    def _repair_receipts(violations: tuple[FactViolation, ...]) -> tuple[FactRepairReceipt, ...]:
        by_field: dict[str, list[str]] = {}
        for violation in violations:
            by_field.setdefault(violation.field, []).append(violation.fragment)
        return tuple(
            FactRepairReceipt(field, tuple(dict.fromkeys(fragments)))
            for field, fragments in by_field.items()
        )

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
        return re.sub(
            r"\b(?:P[1-5]|dressing_decision|product_truth|brand_life_narrative|local_response|visual_styling_story)\b\s*[:：-]?\s*",
            "",
            str(value),
            flags=re.IGNORECASE,
        ).strip()

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
        if isinstance(production, VideoProductionBundle) and re.search(
            r"8\s*秒", production.natural_duration
        ):
            transform_sections = (("变换边界", "这是 8 秒窄主题版，不等同于原完整版本。"),)
        return (
            "标题："
            + title
            + "\n\n"
            + "\n\n".join(
                f"{heading}：{value}"
                for heading, value in contract_sections + transform_sections + sections
            )
        )

    @staticmethod
    def _retry_delay(retry_after: str | None, retries: int) -> float:
        if retry_after:
            try:
                return min(8.0, max(0.0, float(retry_after)))
            except ValueError:
                try:
                    return min(
                        8.0, max(0.0, parsedate_to_datetime(retry_after).timestamp() - time.time())
                    )
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
当输入的主回报是让没到店、未参与原事件的人带走一句可迁移的门店关系许可（例如可以先看、不必解释、按自己的节奏靠近），即使同时提到店长性格、商品或镜头，也选经营关系。只有主回报是让受众认识账号/店长怎样观察、判断和待人，才选建立人格。明确要求“同一个人、同一动作、两面在画面中换重音”，且不要选择建议或商品说明时，选视觉造型；明确要求解释“双面不等于一件顶两件”、说明已知与未知时，选解释商品。
品牌：{request.brand.brand_name}；账号：{request.brand.account_name}；角色：{request.brand.content_role_name}；受众：{request.brand.audience_description}。
当前已点名商品：{products}。
用户输入：{request.weak_seed}"""

    @staticmethod
    def _generation_prompt(request: GenerationInput) -> str:
        assets = "\n".join(asset.body for asset in request.active_domain_assets) or "（无）"
        products = (
            "\n".join(
                DeepSeekGenerator._natural_product(item.sku, item.facts)
                for item in request.products
            )
            or "（无）"
        )
        fields = ", ".join(_CONTRACT_FIELDS[request.primary_product])
        prior = request.prior_saved_body or "（未授权复用旧正文）"
        revision = request.revision_instruction or "（首次生成）"
        source = request.source_version_description or "（不是跨目标重编译）"
        shortening_boundary = (
            "若条件要求 8 秒，不能声称保留源版全部认知；明确标为 8 秒窄主题版，只保留仍能独立成立的一项命题。"
            if "8 秒" in request.brand.production_conditions
            else ""
        )
        four_image_boundary = (
            "若当前只能补拍四张，图序必须恰为四张；完整正文继续承担图片无法独立说明的归因边界。"
            if "四张" in request.brand.production_conditions
            else ""
        )
        if request.media_format == "video":
            media_contract = """交付一条可直接拍摄、表演、录音和剪辑的完整观看链。语言承重时给完整可说文本；视觉承重时给足以直接执行的画面、动作、顺序、节奏和声音。无口播版本要明确写“无口播、无对白、无解说”，并让画面和声音承担价值。不要固定时长、故事、反转、CTA、字幕或配乐。"""
            media_fields = (
                "natural_guide, cover_or_first_frame, viewing_flow, spoken_lines, visual_actions, subtitles, "
                "sound_and_production, natural_duration, release_caption_and_interaction"
            )
        else:
            media_contract = """交付一条可直接拍摄、选图、排版和发布的完整阅读链。首图、每张图的唯一职责、图中文字、完整正文与必要制作提示必须闭合；不得把视频截图、台词卡或切碎长文当作图文。图片承重时不能让正文代替画面。不要固定图片数或强塞 CTA。"""
            media_fields = (
                "natural_guide, hero_image, image_sequence, full_body, layout_and_production, "
                "release_caption_and_interaction"
            )
        return f"""为“{request.brand.account_name}”编译一个完整中文{request.brand.media_format}文字制作成品。
本次受众价值：{_PRODUCT_VALUE[request.primary_product]}；必须只兑现这一价值，不说明路由。
本次交付门：{_DELIVERABLE_REQUIREMENTS[request.primary_product]}
当前媒体合同：{media_contract}
品牌：{request.brand.brand_name}；品牌战略版本：{request.brand.strategy_version}；定位：{request.brand.positioning}；语气：{request.brand.tone}。
实际操作人：{request.brand.operator_name}；代表组织：{request.brand.organization_name}；内容角色：{request.brand.content_role_name}；角色边界：{request.brand.content_role_boundary}；受众：{request.brand.audience_description}；平台/形式：{request.brand.platform}／{request.brand.media_format}；制作条件：{request.brand.production_conditions}。
目标平台方向：{request.platform_direction.direction}
当前变形边界：{shortening_boundary or four_image_boundary or "（无额外变形）"}
当前商品事实（只可使用这里明确给出的内容）：{products}
本次适用资产：{assets}
已授权前情：{prior}
来源关系：{source}
本次修改：{revision}
用户种子：{request.weak_seed}
事实边界：用户种子中的人物、事件和对白可作为本次前提；不要新增种子和商品事实未提供的人物、行为、原因、结果、时间、地点、数量或商品属性。商品只可作当前商品事实明确支持的肯定主张；资料未提供时可以诚实说明“现有资料不能证明”。用户种子中的每一项明确商品或品牌前提都必须在可见成品中得到保留，不能用较泛的态度句替代；尤其“已知某项差异仍坚持某项要求”必须把已知、仍坚持和要求本身连在同一句或相邻句中。品牌、账号、组织和内容角色只决定发声身份、语气和权威边界，不构成已经发生的门店或顾客事件。不要复述个人标识，不要把提示或后台字段写入成品。
写作边界：只把“用户种子”和“当前商品事实”当作已经发生或可以肯定的事实；未知资料只能用“现有资料不能证明”这类边界表达，不能补足。不得从颜色、重量或双面外观推演性能、季节、场合、人际关系、心理状态或设计意图。品牌、账号、组织和内容角色只约束发声身份、语气和权威边界，绝不成为成品里的顾客、店长、门店、服务或现实事件。用户种子没有明确的人物、行为、对白、原因、结果、时间、地点、数量和商品属性一律不新增。
商品解释时，新增理解只能组合当前商品事实和当前适用资产已经支持的内容；不要罗列未提供的材质、里料、工艺、测试原因或把当前样衣资料延展到其他颜色、尺码、批次。成立边界应直接说明当前资料不能支持哪项推断，而不补写假设原因。若重量边界说“不能全部归因”，只能说当前资料没有结构测试、不能定量判定各因素；绝不能把对照样衣本身的重量、颜色或其他未测试原因写成解释，也不能把一组样衣对照推成“像单层一样轻/重”等泛化比较。用户种子明确给出的品牌开发选择是可靠的本次前提，P2 成品必须把该选择与相伴限制一起讲清；若种子说品牌已知某项差异仍作出选择，必须把“已知差异—仍作选择”的关系完整说出，不能只剩一句抽象态度。视觉造型时，画面重音只能来自当前明确的颜色、纹理、两面完整外观、口袋或拍摄动作；不得把颜色、纹理或翻面写成性格、气质、剪裁、肩线、轮廓或其他未提供的属性。拍摄安排也不能补写未给出的成衣部位、内搭或配饰；只编排当前事实支持的翻面、走动、停留、展示和口袋动作。
画面与动作只可写成尚未发生的“拍摄安排”，用指令或条件表达；它可以安排基于已知商品事实的展示，但不能把拍摄安排伪装成现实经历。没有明确确认拍摄当天重新称量时，绝不写实测、电子秤、称重画面、称重声音或当前不存在的对照样衣；约650克只可作为带完整范围的口播或屏显数据。不要在可见文字中加入资产、版本、路由、提示或后台字段。
可见句子只能属于三类：复述用户种子已经给出的前提；逐项陈述当前商品事实已经给出的内容；或以“拍摄安排：”开头的未来制作指令。三类之外只可使用连接词和“现有资料不能证明”的边界句。不要为了自然、生动或完整而补写场景、人物、动作、对话、用途、感受、效果或结论。重量数字只能表述为当前样衣与受控对照样衣存在差异，绝不推成厚薄、手感、挺括、耐穿、保暖、品质或任何其他性质；颜色和细格纹只能用作画面里的视觉重音，绝不推成性格、穿着效果、剪裁或生活方式。
跨目标重编译时，保留源版本的主要价值、品牌账号角色、受众关系、用户前提、商品事实、核心结论和已确认前情；只重组目标平台/媒体的入口、顺序、声画或图文分工、自然时长、发布配文和制作方式。不得把旧版覆盖、说成已经采用或发布，也不要输出来源 ID。
严格返回 JSON，字段：title, {fields}, {media_fields}。不要返回 body。每个字段必须是一个非空中文字符串，绝不能是数组、对象或多条列表。三个验证字段必须各自逐字出现于自然导读、完整观看链/图序、台词/正文、画面/排版、字幕或声音制作提示中的至少一处；它们只作后台校验，不会直接展示。"""

    @staticmethod
    def _boundary_repair_prompt(
        draft: dict[str, object],
        boundary: FactBoundary,
        violations: tuple[FactViolation, ...],
    ) -> str:
        fields = tuple(dict.fromkeys(violation.field for violation in violations))
        flagged = "\n".join(f"- {item.field}：{item.fragment}" for item in violations)
        local_draft = {field: draft[field] for field in fields}
        silent_visual_repair = (
            "本次是无口播视觉任务：若待修字段是画面与动作或完整观看链，必须从零重写为只含翻面、走动、"
            "停留、展示和当前已确认口袋动作的连续安排；不得写左右、正背、侧面、衣领、衣摆、下摆，"
            "不得给内搭添加颜色或款式，也不得加固定秒数。"
            if all(phrase in boundary.explicit_premise for phrase in ("无口播", "同一身内搭"))
            else ""
        )
        return f"""仅局部修复被标记的字段；未列出的字段已经合格，服务端会原样保留，不能也不需要返回它们。
待修字段原文：{json.dumps(local_draft, ensure_ascii=False)}
具体违规片段：
{flagged}
可用商品事实：{boundary.product_facts}
用户明确前提：{boundary.explicit_premise}
只处理七种问题：把未提供的商品材质、保暖、舒适、品质、版型效果、适用场景、设计动机或普遍穿着结果改成不作肯定主张的表达；删除未提供的衣物部位、内搭颜色或内搭款式，只保留用户已给出的“同一身内搭”及当前商品事实支持的翻面、走动、停留和口袋动作；删除由品牌、账号、角色或受众画像凭空形成的现实人物、门店、顾客、行为、对白、原因或结果；删除手机号、邮件地址、订单号和任何个人标识；删除“实测”、电子秤、称重画面/声音、当前不存在的对照样衣或把两件样衣放到镜头中的表述；删除用对照样衣的重量、颜色或其他未测试原因解释“为什么有这份差异”的说法；补回标记为“遗漏的用户前提”的当前用户明确关系，必须保留其已知、仍作选择和限制三者的连结，不得补造原因；删除面向创作者的内部写作指令，改成可直接对受众使用的自然语言。{silent_visual_repair} 重量对照只能作为已提供的屏显或口播数据，不能冒充已经拍到或重新称量；若不能归因，只能明确当前没有结构测试、不能定量判断。每个已标记片段都必须从修复后的 JSON 消失，遗漏前提则必须在该字段中完整出现；不得换词重复同一未经证实的主张。条件性、假设性、拍摄演绎、比喻、幽默、情绪、节奏和基于颜色纹理动作的视觉重音都可保留。不要整篇改写。
严格只返回一个 JSON 对象，且键必须恰好为：{", ".join(fields)}。每个值必须是对应字段修复后的非空中文字符串；不得返回任何未列字段，不返回 body。"""

    @staticmethod
    def _natural_product(sku: str, facts: dict[str, object]) -> str:
        category = DeepSeekGenerator._natural_category(facts.get("category"))
        raw_colors = facts.get("colors")
        colors = (
            "、".join(value for value in raw_colors if isinstance(value, str))
            if isinstance(raw_colors, list)
            else ""
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
            return "当前只知道这两份样衣存在重量差异，不能把全部差异归因于双面结构。"
        if isinstance(value, str) and value.strip():
            return (
                "当前重量边界已登记；只能以两份样衣的已记录重量为准，不能从重量推断其他未测试性质。"
            )
        return "当前只可确认已记录的样衣重量，不能从重量推断其他性质。"

    @staticmethod
    def _natural_category(value: object) -> str:
        if value == "double-faced short coat":
            return "双面短外套"
        return "类别未提供"
