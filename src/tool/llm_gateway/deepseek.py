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
        "必须由已给出的近场信号、当前发布账号能合法作出的回应、未到店者也可带走的关系许可共同承重。"
        "不要把店长性格、商品或画面写成主回报，也不把门店做法扩大成全国政策或交易承诺。"
    ),
    "visual_styling_story": (
        "必须由真实商品和画面动作形成一项可见的穿着可能；移除翻面、走动和两面在画面中的关系后，主回报应消失。"
        "不要给选择建议或商品资料说明，也不要把颜色/纹理推成性能、剪裁、人格或生活方式。"
    ),
}
_COMPARISON_VISUAL_FIELDS = {
    "natural_guide",
    "cover_or_first_frame",
    "viewing_flow",
    "visual_actions",
    "sound_and_production",
    "hero_image",
    "image_sequence",
    "full_body",
    "layout_and_production",
}


@dataclass(frozen=True)
class FactBoundary:
    """One-run-only guard for concrete product claims and invented real-world events."""

    product_facts: str
    explicit_premise: str
    product_skus: tuple[str, ...] = ()
    known_weight_grams: tuple[int, ...] = ()
    known_colors: tuple[str, ...] = ()

    @classmethod
    def from_request(cls, request: GenerationInput) -> FactBoundary:
        weights: list[int] = []
        colors: list[str] = []
        for product in request.products:
            for key in ("sample_weight_m_grams", "comparison_single_layer_short_coat_m_grams"):
                value = product.facts.get(key)
                if isinstance(value, int):
                    weights.append(value)
            current = product.facts.get("sample_weight_m_grams")
            comparison = product.facts.get("comparison_single_layer_short_coat_m_grams")
            if isinstance(current, int) and isinstance(comparison, int):
                weights.append(abs(current - comparison))
            raw_colors = product.facts.get("colors")
            if isinstance(raw_colors, list):
                colors.extend(value for value in raw_colors if isinstance(value, str))
        return cls(
            product_facts="；".join(
                DeepSeekGenerator._natural_product(product.sku, product.facts) for product in request.products
            )
            or "（无当前商品事实）",
            explicit_premise="\n".join(part for part in (request.weak_seed, request.revision_instruction) if part),
            product_skus=tuple(product.sku for product in request.products),
            known_weight_grams=tuple(dict.fromkeys(weights)),
            known_colors=tuple(dict.fromkeys(colors)),
        )


@dataclass(frozen=True)
class FactViolation:
    field: str
    fragment: str


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
        payload: dict[str, Any]
        for format_attempt in range(2):
            system = "你是笛语完整内容编写器。只交付 JSON，不展示提示词、路由、规则或推理。"
            if not request.products:
                system += (
                    "当前没有已点名商品或商品事实。不得把某件商品的具体属性、功能或效果写成已经确认，"
                    "也不得虚构已经发生的人物、对话、顾客/同事/孩子或现场事件；"
                    "问题或一般话题里提到的家庭、妈妈、孩子、顾客或门店只是讨论对象，不代表这些人物"
                    "或现场可供拍摄；默认只使用当前内容角色、一名创作者、一部手机和普通室内条件。"
                    "可以用明确标为一般方法或假设的颜色、品类和搭配例子，但不能冒充当前品牌商品、"
                    "用户衣柜或已经存在的拍摄道具；"
                    "可以围绕用户给出的条件完成自然的穿衣选择、情绪、节奏和明确为未来安排的拍摄构思。"
                )
            if format_attempt:
                system += "上一次响应的字段缺失、为空或不是单个字符串；这次必须返回全部指定 JSON 字段，且每个字段都是非空中文字符串。"
            payload, request_retries = self._request(system, self._generation_prompt(request), 4096)
            provider_payloads.append(payload)
            retries += request_retries
            try:
                structured = json.loads(self._json_content(str(payload["choices"][0]["message"]["content"])))
                if request.media_format == "video":
                    structured = self._normalize_video_contract(structured)
                title, contract, production, body = self._compiled_artifact(request, structured)
                break
            except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
                if format_attempt:
                    raise GenerationFailed("模型返回格式不完整") from exc
                format_repairs = 1
        else:  # pragma: no cover - loop either returns a parsed result or raises.
            raise GenerationFailed("模型返回格式不完整")
        boundary = FactBoundary.from_request(request)
        violations = self._boundary_violations(boundary, title, contract, production)
        if request.products:
            semantic_violations, judgement_payload, judgement_retries = self._semantic_fact_violations(
                request, boundary, structured
            )
            provider_payloads.append(judgement_payload)
            retries += judgement_retries
            violations = tuple(dict.fromkeys(violations + semantic_violations))
        fact_repair_receipts: tuple[FactRepairReceipt, ...] = ()
        if violations:
            repair_system = "你是笛语内容编写器。只交付修复后的 JSON，不展示规则、推理或后台信息。"
            if any(
                self._depicts_unavailable_comparison(boundary, violation.field, violation.fragment)
                for violation in violations
            ):
                repair_system += (
                    "当前只有对照重量数据，没有对照样衣拍摄事实。待修视觉字段绝不能出现单层外套、"
                    "对照样衣、第二件商品、两件并排、称量或实物对比；重量只能作为当前商品旁的文字或口播数据。"
                )
            if any(self._weakens_no_weight_attribution(violation.fragment) for violation in violations):
                repair_system += (
                    "待修字段只保留两份重量记录、没有结构测试和现有资料无法归因；"
                    "不得讨论或点名任何重量原因，也不得讨论原因的程度、比例、主次或可能性。"
                )
            if any(
                "双面" in violation.fragment
                and re.search(r"(?:重量|克|差异)", violation.fragment)
                and re.search(
                    r"(?:归因|原因|造成|导致|带来|增加|来自|贡献|影响|"
                    r"多.{0,6}重量|代价|负担|值得.{0,8}重量|换来)",
                    violation.fragment,
                )
                for violation in violations
            ):
                repair_system += (
                    "待修字段只可保留两份记录存在差异以及现有资料无法归因；"
                    "不得讨论或点名任何重量原因、影响或增减关系。"
                )
            if any(self._generalizes_sample_comparison(violation.fragment) for violation in violations):
                repair_system += (
                    "当前对照仅是一份同季同长度 M 码样衣记录；待修字段不得把它泛化为普通、"
                    "一般、通常或普遍的单层外套类别结论。"
                )
            if any(self._denies_known_weight_difference(boundary, violation.fragment) for violation in violations):
                repair_system += (
                    "960 克与 650 克两份记录可以直接确认相差 310 克；待修字段不得说重量差额、"
                    "重多少或差多少未知，只能说差异原因未知。"
                )
            if any(re.search(r"(?:实测|称重|称了|称出|电子秤)", violation.fragment) for violation in violations):
                repair_system += (
                    "已知重量是既有样衣记录；待修字段不得写成我们称了、称出来、现场称重或"
                    "电子秤画面，只能把记录作为口播或文字数据。"
                )
            if any(
                re.search(
                    r"(?:双倍|两倍|翻倍).{0,8}口袋|口袋.{0,8}(?:双倍|两倍|翻倍)",
                    violation.fragment,
                )
                for violation in violations
            ):
                repair_system += (
                    "两面口袋均可使用只说明两面可用，不代表口袋数量双倍、两倍或翻倍；"
                    "待修字段只能保留两面可用这个已知事实。"
                )
            if any(
                re.search(
                    r"(?:展示|拉出|露出|翻出).{0,8}(?:内衬|里布)",
                    violation.fragment,
                )
                for violation in violations
            ):
                repair_system += (
                    "当前只提供两面完整外观和两面口袋可用；待修字段不得新增、展示或拉出"
                    "未提供的内部结构或部件。"
                )
            if any(violation.field == "natural_duration" for violation in violations):
                spoken = DeepSeekGenerator._visible_text(structured["spoken_lines"])
                spoken_count = len(re.findall(r"[\w\u4e00-\u9fff]", spoken))
                repair_system += (
                    f"完整口播约有 {spoken_count} 个可读字符；待修自然时长必须足以自然说完"
                    "全部口播并完成画面，不能通过删口播或报不可能的短时长规避。"
                )
            if any(violation.field == "spoken_lines" for violation in violations):
                repair_system += (
                    "待修台词必须是一段可以直接说出的完整口播，不能只重复标题或问题；"
                    "要自然完成入口、展开与收束，同时保持当前账号身份和事实边界。"
                )
            if any(
                violation.field
                in {
                    "viewing_flow",
                    "visual_actions",
                    "subtitles",
                    "sound_and_production",
                }
                and re.search(
                    r"(?:无口播时|无口播.{0,8}无对白.{0,8}无解说)",
                    violation.fragment,
                )
                for violation in violations
            ):
                repair_system += (
                    "完整成品已经提供口播文本；待修制作字段不得再标记无口播、无对白或无解说，应与已有口播合同保持一致。"
                )
            if not request.products:
                repair_system += (
                    "当前没有已点名商品或商品事实。待修字段不得把某件商品的具体属性、功能或效果"
                    "写成已经确认，也不得虚构已经发生的人物、对话或现场事件；"
                    "问题中提到的家庭、妈妈、孩子、顾客或门店只是讨论对象，不可改写成账号亲历或"
                    "可拍资源；只使用当前内容角色、一名创作者、一部手机和普通室内条件。"
                    "品牌关系观点不能改写成门店已经执行的服务办法、全国承诺或顾客经历。"
                    "可以保留明确作为一般方法或假设的颜色、品类与搭配例子，但不能冒充当前品牌商品、"
                    "用户衣柜或已经存在的拍摄道具；"
                    "条件性选择、情绪和明确为未来安排的拍摄构思可以保留。"
                )
            payload, repair_retries = self._request(
                repair_system,
                self._boundary_repair_prompt(structured, boundary, violations),
                4096,
            )
            provider_payloads.append(payload)
            retries += repair_retries
            try:
                repaired_fields = json.loads(self._json_content(str(payload["choices"][0]["message"]["content"])))
                structured = self._merge_repaired_fields(structured, violations, repaired_fields)
                if request.media_format == "video":
                    structured = self._normalize_video_contract(structured)
                title, contract, production, body = self._compiled_artifact(request, structured)
            except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
                raise GenerationFailed("模型边界修复返回格式不完整") from exc
            final_violations = self._boundary_violations(boundary, title, contract, production)
            if request.products:
                semantic_violations, judgement_payload, judgement_retries = self._semantic_fact_violations(
                    request, boundary, structured
                )
                provider_payloads.append(judgement_payload)
                retries += judgement_retries
                final_violations = tuple(dict.fromkeys(final_violations + semantic_violations))
            if final_violations:
                structured = self._prune_rejected_sentences(
                    request, structured, final_violations
                )
                title, contract, production, body = self._compiled_artifact(request, structured)
                residual_violations = self._boundary_violations(boundary, title, contract, production)
                if residual_violations:
                    raise GenerationFailed("内容事实边界无法在一次修复内满足")
                violations = tuple(dict.fromkeys(violations + final_violations))
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

    def _semantic_fact_violations(
        self,
        request: GenerationInput,
        boundary: FactBoundary,
        structured: dict[str, object],
    ) -> tuple[tuple[FactViolation, ...], dict[str, Any], int]:
        fields = ", ".join(structured)
        payload, retries = self._request(
            "你是笛语商品事实判定器。只返回 JSON，不改写成品，不展示推理。",
            f"""判断候选成品是否把未提供内容写成已经确认的商品事实或现实拍摄事实。
只依据以下可用商品事实和用户明确前提，不使用常识补足商品属性。
可用商品事实：{boundary.product_facts}
用户明确前提：{boundary.explicit_premise}
当前点名商品：{"、".join(boundary.product_skus) or "无"}。
判定边界：
1. SKU、记录重量、颜色、两面完整外观和两面口袋必须与可用事实一致。
2. 两份样衣重量记录只证明这两份记录存在差异；不得把任何一部分差异归因于双面结构，
   不得据此肯定更扎实、更挺、更暖、更耐用、更高级或其他未提供性质。
   涉及重量原因时，不得讨论双面结构所占程度、比例、主次或可能性；这类表达仍预设了部分归因。
   只能说明两份记录存在差异、没有结构测试、现有资料无法归因。
3. 对照重量是数据，不代表提供了可拍摄的对照样衣；候选只能安排当前点名商品入镜。
   两份样衣记录也不得泛化为普通、一般、通常或普遍的单层/双面外套品类结论。
   用文字、字幕或卡片呈现 650 克对照数据，以及拿取、翻面当前点名商品，均属合法画面；
   只有把单层对照写成第二件实物入镜才违规。
4. 对未知性质作明确否定或说明“现有资料不能证明”不算违规，但不能用“无法判断”包装
   一个已经预设成立的性能增益、原因或设计动机。
5. 创意表达、比喻、情绪、节奏、当前商品的未来拍摄安排可以保留；只在它们冒充商品事实、
   已发生事件或需要未提供人物/商品/现场时判违规。
候选 JSON：{json.dumps(structured, ensure_ascii=False)}
只返回：{{"violations":[{{"field":"候选字段名","fragment":"该字段中原样连续片段"}}]}}。
没有违规返回 {{"violations":[]}}。field 必须来自：{fields}；fragment 必须逐字存在于该字段，
不得返回解释、原因、改写建议或候选中不存在的文字。""",
            1600,
        )
        try:
            result = json.loads(self._json_content(str(payload["choices"][0]["message"]["content"])))
            raw_violations = result["violations"]
            if not isinstance(raw_violations, list):
                raise TypeError("violations must be a list")
            violations: list[FactViolation] = []
            for value in raw_violations:
                if not isinstance(value, dict):
                    raise TypeError("violation must be an object")
                field = value.get("field")
                fragment = value.get("fragment")
                candidate = structured.get(field) if isinstance(field, str) else None
                if (
                    not isinstance(field, str)
                    or field not in structured
                    or not isinstance(fragment, str)
                    or not fragment.strip()
                    or not isinstance(candidate, str)
                    or fragment not in candidate
                ):
                    raise TypeError("semantic violation is not grounded in the candidate")
                if (
                    field in _COMPARISON_VISUAL_FIELDS
                    and "单层" in fragment
                    and re.search(r"(?:卡片|文字|字幕|数据)", fragment)
                    and not self._depicts_unavailable_comparison(boundary, field, fragment)
                ):
                    continue
                violations.append(FactViolation(field, fragment))
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise GenerationFailed("模型事实判定返回格式不完整") from exc
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
    def _normalize_video_contract(structured: dict[str, object]) -> dict[str, object]:
        """Apply deterministic media consistency without rewriting creative content."""
        projected = dict(structured)
        spoken = DeepSeekGenerator._visible_text(projected["spoken_lines"])
        if re.search(r"^\s*无口播.{0,8}无对白.{0,8}无解说\s*$", spoken):
            return projected
        sound = DeepSeekGenerator._visible_text(projected["sound_and_production"])
        sound_sentences = [
            sentence.strip()
            for sentence in re.split(r"(?<=[。！？!?])", sound)
            if sentence.strip()
            and not re.search(r"无口播时", sentence)
        ]
        if sound_sentences:
            projected["sound_and_production"] = "".join(sound_sentences)
        duration = DeepSeekGenerator._visible_text(projected["natural_duration"])
        duration_match = re.search(r"(\d{1,3})\s*秒", duration)
        if duration_match:
            spoken_count = len(re.findall(r"[\w\u4e00-\u9fff]", spoken))
            minimum_seconds = (spoken_count + 5) // 6
            if int(duration_match.group(1)) < minimum_seconds:
                projected["natural_duration"] = f"约 {minimum_seconds} 秒"
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
    def _boundary_violations(
        boundary: FactBoundary,
        title: str,
        contract: ContentSemanticContract,
        production: ContentProductionBundle,
    ) -> tuple[FactViolation, ...]:
        visible = (("title", title),) + tuple(vars(contract).items()) + tuple(vars(production).items())
        violations: list[FactViolation] = []
        unsupported_product_assertion = re.compile(
            r"(?:这(?:件|款)?|该(?:件|款)?|当前(?:这件|这款)?|商品|ZX-[A-Z]\d+).{0,28}"
            r"(?:保暖|防水|透气|耐穿|显瘦|显高|挺括|支撑|版型|剪裁|"
            r"设计意图|设计动机|为了.{0,12}(?:设计|制作)|"
            r"(?:采用|使用|材质(?:是|为)|面料(?:是|为)|由.{0,10}制成).{0,12}"
            r"(?:羊毛|羊绒|棉|聚酯))"
        )
        unprovided_styling_detail = re.compile(
            r"(?:黑色|白色|灰色|棕色|高领|衬衫|针织衫|T恤).{0,8}(?:内搭|高领|衬衫|针织衫|T恤)"
        )
        unverified_capture = re.compile(
            r"(?:实测|称(?:重(?:台|画面|提示音|读数)|了(?:一下|一遍|重量))|"
            r"(?:我们|我方|店里|团队).{0,12}称(?:出来|出|得|过|了|重|量)|电子秤|"
            r"(?:一(?:只|双)手|手部?|镜头).{0,16}(?:拿起|展示|放入).{0,16}(?:单层.{0,4}外套|对照)|"
            r"(?:单层外套|对照样衣|对比图像).{0,16}(?:拿起|展示|放入|对比))"
        )
        invalid_weight_explanation = re.compile(
            r"(?:因为.{0,24}(?:单层|650克)|(?:单层|650克).{0,24}(?:所以|解释了|证明了).{0,24}(?:310克|差异))"
        )
        unsupported_weight_comparison = re.compile(
            r"(?:像.{0,16}单层.{0,8}(?:轻|重)|(?:更轻|更重|轻于|重于).{0,16}单层)"
        )
        unsupported_weight_cause = re.compile(
            r"(?:结构|其他).{0,16}(?:因素|原因).{0,16}(?:导致|造成|解释).{0,16}(?:差异|重量)|"
            r"(?:双面结构|双面).{0,16}(?:是|为).{0,12}(?:原因之一|部分原因|一部分原因)|"
            r"(?:双面结构|双面).{0,16}(?:带来|导致|造成|增加).{0,16}(?:重量|克|差异)|"
            r"(?:双面结构|双面).{0,64}(?:更重|重量(?:更大|增加|上.{0,8}代价|"
            r"是.{0,8}代价|负担)|多.{0,6}重量|值得.{0,8}重量|换来.{0,8}重量)"
        )
        positive_weight_link = re.compile(
            r"(?:双面结构|双面).{0,64}(?:更重|重量(?:更大|增加|上.{0,8}代价|"
            r"是.{0,8}代价|负担)|多.{0,6}重量|值得.{0,8}重量|换来.{0,8}重量)"
        )
        internal_copy_direction = re.compile(r"(?:需向受众说明|不应仅因.{0,16}说服)")
        personal_identifier = re.compile(r"1[3-9]\d{9}|[\w.+-]+@[\w.-]+|订单号?\s*[:：]?\s*[A-Za-z0-9-]+")
        # A boundary may say that no structure test is available.  It must not
        # grow into a fabricated inventory of technical variables such as a
        # lining or a process test.
        unprovided_technical_detail = re.compile(r"(?:面料|里料|工艺)")
        unprovided_structure_action = re.compile(
            r"(?:展示|拉出|露出|翻出).{0,8}(?:内衬|里布)"
        )
        unprovided_visual_garment = re.compile(
            r"(?:米色|蓝色|白色|黑色|灰色|棕色|深色|同色系|针织|卫衣|T恤|牛仔|棉麻|"
            r"连衣裙|童装|衬衫|裙子|外套|裤子|上衣|配饰)"
        )
        invented_real_world_event = re.compile(
            r"(?:一位|同事|顾客|店长|孩子|观众|她|他).{0,24}"
            r"(?:问|说|站在|走进|走向|看见|蹲下|拿着|拍了拍|转身离开|等(?:待)?).{0,32}"
            r"|(?:我们|我).{0,16}(?:见过|遇到过|试过|观察到|经常被问|站在镜子前|试了又试)"
            r"|(?:我|我们).{0,20}(?:最近|曾经|一直|太久|以前|当了|给孩子|家里|"
            r"观察过|买了|留下了|犹豫了|包括我自己|上周|昨天|刚才).{0,32}"
        )
        capture_resource_pattern = (
            r"(?:孩子|妈妈|爸爸|丈夫|一家三口|全家(?:人|合影)?|顾客|店员|"
            r"店内|店门|门店|衣柜|衣架|收银台|购物车|家庭合照|合照|手机相册|"
            r"玻璃门|挂着的衣物|门铃)"
        )
        unprovided_capture_resource = re.compile(capture_resource_pattern)
        text_only_topic = re.compile(
            r"^\s*(?:手写|字幕|文字|标题|封面文字).{0,20}" + capture_resource_pattern
        )
        unconfirmed_service_practice = re.compile(
            r"(?:我们|这个账号|笛语服饰).{0,24}"
            r"(?:只在.{0,8}需要时出现|不会打扰|不打扰|始终欢迎|随时来|让顾客|给顾客空间)"
        )
        has_provided_capture_resource = bool(
            re.search(r"(?:可以|可|会|让).{0,8}(?:出镜|拍摄)|现成素材|已经上传|我上传|就在门店拍", boundary.explicit_premise)
        )
        if isinstance(production, VideoProductionBundle) and not re.search(
            r"^\s*无口播.{0,8}无对白.{0,8}无解说\s*$",
            production.spoken_lines,
        ):
            for field in (
                "viewing_flow",
                "visual_actions",
                "subtitles",
                "sound_and_production",
            ):
                value = str(getattr(production, field))
                if re.search(
                    r"(?:无口播时|无口播.{0,8}无对白.{0,8}无解说)",
                    value,
                ):
                    violations.append(FactViolation(field, value))
            duration_match = re.search(r"(\d{1,3})\s*秒", production.natural_duration)
            if duration_match:
                spoken_count = len(
                    re.findall(r"[\w\u4e00-\u9fff]", production.spoken_lines)
                )
                declared_seconds = int(duration_match.group(1))
                minimum_seconds = (spoken_count + 5) // 6
                if declared_seconds < minimum_seconds:
                    violations.append(
                        FactViolation("natural_duration", production.natural_duration)
                    )
                if declared_seconds >= 20 and spoken_count < 50:
                    violations.append(
                        FactViolation("spoken_lines", production.spoken_lines)
                    )
        elif isinstance(production, VideoProductionBundle) and isinstance(
            contract, (P1SemanticContract, P3SemanticContract)
        ):
            violations.append(FactViolation("spoken_lines", production.spoken_lines))
        for field, text in visible:
            for sentence in re.split(r"(?<=[。！？!?])", text):
                if not sentence.strip():
                    continue
                conditional = re.search(r"(?:如果|若|拍摄安排|演绎|假设|可以|可在|打算|建议)", sentence)
                product_reference = re.search(
                    r"(?:商品|这(?:件|款)?|该(?:件|款)?|ZX-[A-Z]\d+|重量|双面|样衣|口袋)", sentence
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
                if DeepSeekGenerator._depicts_unavailable_comparison(boundary, field, sentence):
                    violations.append(FactViolation(field, sentence.strip()))
                if invalid_weight_explanation.search(sentence):
                    violations.append(FactViolation(field, sentence.strip()))
                if unsupported_weight_comparison.search(sentence) and "不以极致轻量" not in sentence:
                    violations.append(FactViolation(field, sentence.strip()))
                if positive_weight_link.search(sentence) or (
                    unsupported_weight_cause.search(sentence) and not acknowledged_unknown
                ):
                    violations.append(FactViolation(field, sentence.strip()))
                if DeepSeekGenerator._weakens_no_weight_attribution(sentence):
                    violations.append(FactViolation(field, sentence.strip()))
                if DeepSeekGenerator._generalizes_sample_comparison(sentence):
                    violations.append(FactViolation(field, sentence.strip()))
                if DeepSeekGenerator._denies_known_weight_difference(boundary, sentence):
                    violations.append(FactViolation(field, sentence.strip()))
                if re.search(
                    r"(?:双倍|两倍|翻倍).{0,8}口袋|"
                    r"口袋.{0,8}(?:双倍|两倍|翻倍)",
                    sentence,
                ):
                    violations.append(FactViolation(field, sentence.strip()))
                if internal_copy_direction.search(sentence):
                    violations.append(FactViolation(field, sentence.strip()))
                if personal_identifier.search(sentence):
                    violations.append(FactViolation(field, sentence.strip()))
                if (
                    boundary.product_facts == "（无当前商品事实）"
                    and unsupported_product_assertion.search(sentence)
                    and not conditional
                    and not acknowledged_unknown
                ):
                    violations.append(FactViolation(field, sentence.strip()))
                if (
                    boundary.product_facts == "（无当前商品事实）"
                    and invented_real_world_event.search(sentence)
                    and not conditional
                    and sentence not in boundary.explicit_premise
                ):
                    violations.append(FactViolation(field, sentence.strip()))
                if (
                    boundary.product_facts == "（无当前商品事实）"
                    and field in _COMPARISON_VISUAL_FIELDS
                    and unprovided_capture_resource.search(sentence)
                    and not text_only_topic.search(sentence)
                    and not has_provided_capture_resource
                ):
                    violations.append(FactViolation(field, sentence.strip()))
                if (
                    boundary.product_facts == "（无当前商品事实）"
                    and field in _COMPARISON_VISUAL_FIELDS
                    and unprovided_visual_garment.search(sentence)
                    and not text_only_topic.search(sentence)
                ):
                    violations.append(FactViolation(field, sentence.strip()))
                if (
                    boundary.product_facts == "（无当前商品事实）"
                    and unconfirmed_service_practice.search(sentence)
                    and sentence not in boundary.explicit_premise
                ):
                    violations.append(FactViolation(field, sentence.strip()))
                if (
                    boundary.product_facts != "（无当前商品事实）"
                    and unsupported_product_assertion.search(sentence)
                    and not conditional
                    and not acknowledged_unknown
                ):
                    violations.append(FactViolation(field, sentence.strip()))
                if (
                    (product_reference or product_contract)
                    and unprovided_technical_detail.search(sentence)
                    and re.search(r"(?:重量|克|差异|归因|原因|测试)", sentence)
                ):
                    violations.append(FactViolation(field, sentence.strip()))
                if unprovided_structure_action.search(sentence):
                    violations.append(FactViolation(field, sentence.strip()))
                if isinstance(contract, P5SemanticContract) and unprovided_styling_detail.search(sentence):
                    violations.append(FactViolation(field, sentence.strip()))
                if DeepSeekGenerator._conflicts_with_product_facts(boundary, sentence):
                    violations.append(FactViolation(field, sentence.strip()))
                if (
                    re.search(
                        r"(?:很多|许多|不少|多位|几位|每位|所有|常客).{0,8}(?:顾客|客人|到店者)",
                        sentence,
                    )
                    and sentence not in boundary.explicit_premise
                ):
                    violations.append(FactViolation(field, sentence.strip()))
        return tuple(dict.fromkeys(violations))

    @staticmethod
    def _weakens_no_weight_attribution(sentence: str) -> bool:
        """Reject causal degree language that quietly presupposes a partial attribution."""
        if re.search(
            r"双面结构.{0,16}(?:占|贡献|造成|导致).{0,8}"
            r"(?:多少|多大|比例|程度)",
            sentence,
        ):
            return True
        if not re.search(r"(?:重量|克|差异)", sentence) or "双面" not in sentence:
            return False
        weak_uncertainty = re.search(
            r"(?:是否|是不是|能否|唯一|主要|多少|多大|比例|程度|主次|"
            r"不一定|无法排除|不能全|不能都)",
            sentence,
        )
        weak_extent = re.search(r"(?:完全|全部|全都|全|部分)", sentence)
        safe_no_part = re.search(
            r"(?:不能|无法|没有.{0,8}(?:依据|证据)).{0,24}"
            r"(?:任何一部分|任一部分).{0,16}(?:差异|重量)|"
            r"(?:任何一部分|任一部分).{0,16}(?:差异|重量).{0,24}(?:不能|无法).{0,12}"
            r"(?:归因|确认|证明)",
            sentence,
        )
        weak_relation = weak_uncertainty is not None or weak_extent is not None
        weakened_negative = re.search(
            r"(?:无法|没法|不能|不可|不应|不要).{0,32}"
            r"(?:归因|原因|造成|导致|带来|增加|来自|贡献|影响)",
            sentence,
        )
        direct_no_attribution = re.search(
            r"(?:无法|不能|不可)(?:(?:据此|直接)|(?:将|把).{0,16})?归因|"
            r"(?:无法|不能|不可)(?:确认|确定|证明).{0,16}(?:原因|归因)",
            sentence,
        )
        return safe_no_part is None and (
            weak_relation or (weakened_negative is not None and direct_no_attribution is None)
        )

    @staticmethod
    def _generalizes_sample_comparison(sentence: str) -> bool:
        """Keep a recorded two-sample comparison from becoming a category-level claim."""
        return bool(
            re.search(r"(?:单层|双面)", sentence)
            and re.search(
                r"(?:重量|克|差异|更重|更轻|重于|轻于|比.{0,12}(?:重|轻))",
                sentence,
            )
            and re.search(r"(?:普通|一般|通常|普遍|往往|都比|均比)", sentence)
        )

    @staticmethod
    def _denies_known_weight_difference(boundary: FactBoundary, sentence: str) -> bool:
        """Reject treating an arithmetically known sample-weight difference as unknown."""
        if len(boundary.known_weight_grams) < 3:
            return False
        unknown = r"(?:无法|没法|不能|未知|不清楚|不确定)"
        amount = r"(?:重多少|差多少|重量差额|差额|差值|差了多少)"
        return bool(
            re.search(amount + r".{0,20}" + unknown, sentence) or re.search(unknown + r".{0,20}" + amount, sentence)
        )

    @staticmethod
    def _depicts_unavailable_comparison(boundary: FactBoundary, field: str, sentence: str) -> bool:
        """Reject a second physical product when the request only supplied comparison data."""
        if field not in _COMPARISON_VISUAL_FIELDS or len(boundary.product_skus) > 1:
            return False
        if re.search(
            r"不(?:展示|提及|悬挂|拿起|并排|对比).{0,32}(?:单层|对照|第二件|两件)",
            sentence,
        ):
            return False
        if re.search(r"(?:卡片|文字|字幕|数据)", sentence) and not re.search(
            r"单层.{0,12}(?:实物|平铺|悬挂|拿起|穿上|入镜)",
            sentence,
        ):
            return False
        physical_comparison = re.search(
            r"(?:展示|悬挂|拿起|平铺|并排|旁边放|按压|对比).{0,32}单层.{0,4}外套|"
            r"单层.{0,4}外套.{0,32}(?:展示|悬挂|拿起|平铺|并排|按压|对比)|"
            r"(?:两|2)\s*(?:件|款)\s*(?:外套|衣服|商品)|第二(?:件|款)(?:外套|衣服|商品)",
            sentence,
        )
        return physical_comparison is not None

    @staticmethod
    def _conflicts_with_product_facts(boundary: FactBoundary, sentence: str) -> bool:
        """Reject only concrete SKU, recorded-weight, or product-colour contradictions."""
        skus = tuple(re.findall(r"\bZX-[A-Z]\d+\b", sentence))
        if boundary.product_skus and skus and any(sku not in boundary.product_skus for sku in skus):
            return True
        weighs_product = bool(re.search(r"(?:商品|样衣|重量|外套|ZX-[A-Z]\d+)", sentence))
        grams = tuple(int(value) for value in re.findall(r"(\d{2,4})\s*克", sentence))
        if (
            boundary.known_weight_grams
            and weighs_product
            and grams
            and any(value not in boundary.known_weight_grams for value in grams)
        ):
            return True
        product_specific = bool(re.search(r"(?:商品|这(?:件|款)?|该(?:件|款)?|ZX-[A-Z]\d+)", sentence))
        color_terms = tuple(re.findall(r"(?:黑色|白色|蓝色|红色|黄色|紫色|棕色|深绿|炭灰)", sentence))
        return (
            product_specific
            and bool(boundary.known_colors)
            and bool(color_terms)
            and any(not any(color in known for known in boundary.known_colors) for color in color_terms)
        )

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
    def _prune_rejected_sentences(
        request: GenerationInput,
        draft: dict[str, object],
        violations: tuple[FactViolation, ...],
    ) -> dict[str, object]:
        """Finish one repair with safe media fallback only for no-product content."""
        rejected_by_field: dict[str, list[str]] = {}
        prunable_fields = {field for fields in _CONTRACT_FIELDS.values() for field in fields} | {
            "spoken_lines",
            "subtitles",
            "release_caption_and_interaction",
        }
        no_product_media_fallback_fields = {
            "natural_guide",
            "cover_or_first_frame",
            "viewing_flow",
            "visual_actions",
            "sound_and_production",
        }
        for violation in violations:
            if (
                violation.field not in prunable_fields
                and not (
                    not request.products
                    and violation.field in no_product_media_fallback_fields
                )
            ):
                raise GenerationFailed("内容事实边界无法在一次修复内满足")
            rejected_by_field.setdefault(violation.field, []).append(violation.fragment.strip())
        projected = dict(draft)
        contract_fields = {
            field for fields in _CONTRACT_FIELDS.values() for field in fields
        }
        for field in no_product_media_fallback_fields & rejected_by_field.keys():
            projected[field] = DeepSeekGenerator._safe_no_product_media_field(
                request, projected, field
            )
            rejected_by_field.pop(field)
        for field, rejected in rejected_by_field.items():
            value = DeepSeekGenerator._visible_text(projected[field])
            separator = r"(?<=[。！？!?])|[|｜；;\n]+" if field == "subtitles" else r"(?<=[。！？!?])"
            sentences = [sentence.strip() for sentence in re.split(separator, value) if sentence.strip()]
            kept = [
                sentence
                for sentence in sentences
                if not any(fragment in sentence or sentence in fragment for fragment in rejected)
            ]
            if not kept:
                if not request.products and field in {
                    "spoken_lines",
                    "subtitles",
                    "release_caption_and_interaction",
                } | contract_fields:
                    projected[field] = DeepSeekGenerator._safe_no_product_media_field(
                        request, projected, field
                    )
                    continue
                raise GenerationFailed("内容事实边界无法在一次修复内满足")
            retained = (" | " if field == "subtitles" else "").join(kept)
            readable_count = len(re.findall(r"[\w\u4e00-\u9fff]", retained))
            minimum = 30 if field == "spoken_lines" else 10
            if field in contract_fields:
                minimum = 4
            if readable_count < minimum and not request.products and field in {
                "spoken_lines",
                "subtitles",
                "release_caption_and_interaction",
            } | contract_fields:
                projected[field] = DeepSeekGenerator._safe_no_product_media_field(
                    request, projected, field
                )
                continue
            if readable_count < minimum:
                raise GenerationFailed("内容事实边界无法在一次修复内满足")
            projected[field] = retained
        return projected

    @staticmethod
    def _safe_no_product_media_field(
        request: GenerationInput,
        draft: dict[str, object],
        field: str,
    ) -> str:
        """Compile a usable one-person field without inventing people, products or places."""
        seed = request.weak_seed.strip()
        if field == "natural_guide":
            return "由当前创作者正对手机，从这个问题进入，展开判断后自然收束到品牌立场。"
        if field == "cover_or_first_frame":
            return f"当前创作者正对手机，首帧手写标题：“{seed}”"
        if field == "viewing_flow":
            return "固定机位：先提出问题，再说清判断与边界，最后留一句给受众继续思考。"
        if field == "visual_actions":
            return "当前创作者正对手机口播，用自然停顿、简单手势和手写关键词辅助表达。"
        if field == "sound_and_production":
            return "一人一部手机，普通室内环境收音；人声清楚，不依赖额外人物、商品、场地或素材。"
        if field == "subtitles":
            return f"{seed}｜尊重差异，也保留自己的判断"
        if field == "release_caption_and_interaction":
            return f"{seed} 你最在意的条件是什么？"
        if field == "choice":
            return "先保留每个人舒服、愿意使用的选择，再找一个可以自然呼应的共同点。"
        if field == "boundary":
            return "如果这个共同点让任何人明显不自在，就放弃统一，保留各自选择。"
        if field == "next_action":
            return "先用现有条件做一次低成本对照，再决定哪一种更自然。"
        if field == "persona_observation":
            return "这个问题值得从真实感受出发讨论，不需要替任何人物编造经历。"
        if field == "audience_return":
            return "你可以保留自己的节奏和判断，不必被一种标准答案催促。"
        if field == "brand_account_link":
            return (
                f"{request.brand.brand_name}当前表达尊重差异、真实克制；"
                "这是一项品牌立场，不代表门店已经执行某项服务。"
            )
        if field == "local_reality_or_signal":
            return "只使用用户本次明确给出的近场信号，不补写顾客原因或门店事实。"
        if field == "legitimate_account_response":
            return "当前账号只表达在其身份边界内能够成立的回应。"
        if field == "public_relationship_return":
            return "让未参与原事件的人也能带走一份可迁移的理解与选择空间。"
        if field == "spoken_lines":
            if request.primary_product == "dressing_decision":
                return (
                    f"关于“{seed}”，这次可以先这样选："
                    f"{DeepSeekGenerator._visible_text(draft['choice'])}。"
                    f"但如果{DeepSeekGenerator._visible_text(draft['boundary'])}，选择就要跟着变。"
                    f"现在可以先做一个小验证：{DeepSeekGenerator._visible_text(draft['next_action'])}。"
                )
            if request.primary_product == "brand_life_narrative":
                return (
                    f"关于“{seed}”，我们不替任何人编一段经历。"
                    f"我们想说的是：{DeepSeekGenerator._visible_text(draft['persona_observation'])}。"
                    f"对你来说，{DeepSeekGenerator._visible_text(draft['audience_return'])}。"
                    f"这也说明了{DeepSeekGenerator._visible_text(draft['brand_account_link'])}。"
                )
            if request.primary_product == "local_response":
                return (
                    f"关于“{seed}”，我们只回应当前已经给出的信号。"
                    f"{DeepSeekGenerator._visible_text(draft['legitimate_account_response'])}。"
                    f"{DeepSeekGenerator._visible_text(draft['public_relationship_return'])}。"
                )
        raise GenerationFailed("内容事实边界无法在一次修复内满足")

    @staticmethod
    def _repair_receipts(violations: tuple[FactViolation, ...]) -> tuple[FactRepairReceipt, ...]:
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
        if isinstance(production, VideoProductionBundle) and re.search(
            r"(?<!\d)8\s*秒", production.natural_duration
        ):
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
    def _generation_prompt(request: GenerationInput) -> str:
        assets = "\n".join(asset.body for asset in request.active_domain_assets) or "（无）"
        products = (
            "\n".join(DeepSeekGenerator._natural_product(item.sku, item.facts) for item in request.products) or "（无）"
        )
        fields = ", ".join(_CONTRACT_FIELDS[request.primary_product])
        prior = request.prior_saved_body or "（未授权复用旧正文）"
        revision = request.revision_instruction or "（首次生成）"
        source = request.source_version_description or "（不是跨目标重编译）"
        has_comparison_data = any(
            isinstance(item.facts.get("comparison_single_layer_short_coat_m_grams"), int) for item in request.products
        )
        production_fact_boundary = (
            "当前只提供了对照重量记录，没有提供可拍摄的对照样衣。画面只能使用当前点名商品；"
            "不得安排第二件商品、两件并排、对照样衣、重新称量或实物比较。"
            if has_comparison_data
            else "画面只能使用当前明确提供的商品、人物和现场条件。"
        )
        no_product_guard = (
            "当前没有已点名商品或可用商品事实。不得把某件未提供的商品属性、功能、效果或现实经历"
            "写成已经确认；一般方法或假设可以使用颜色、品类与搭配例子，但不得冒充当前品牌商品、"
            "用户衣柜或已存在的拍摄道具；"
            "问题或一般话题里出现的家庭、妈妈、孩子、顾客或门店只是讨论对象，不是可用人物、素材或现场；"
            "可以围绕用户给出的条件完成自然的选择、情绪、节奏和未来拍摄构思。"
            if not request.products
            else ""
        )
        writing_boundary = (
            "写作边界：当前没有商品事实。可以自然讨论穿衣选择、情绪、幽默、节奏和未来拍摄构思，"
            "但不得把某件具体衣物的属性、功能、效果或现实经历当作已经发生的事实；"
            "一般方法或假设可以用颜色、品类与搭配例子，不能冒充当前品牌商品或用户已有物品。"
            "不要写资产、版本、路由、提示或后台字段。"
            if not request.products
            else """写作边界：只把“用户种子”和“当前商品事实”当作已经发生或可以肯定的事实；未知资料不得补足为具体商品性能、材质、工艺、部位设计动机或现实事件。条件性专业解释要说明依据什么、能说明什么、不能推出什么；不得把颜色、重量或双面外观推演为性能或官方设计动机。品牌、账号、组织和内容角色只约束发声身份、语气和权威边界，绝不成为已经发生的顾客、店长、门店、服务或交易事件。
商品解释时，新增理解只能组合当前商品事实和当前适用资产已经支持的内容。若没有结构测试，不能声称双面结构造成、带来或增加了任何一部分重量差异，也不得列举面料、里料、工艺等未验证候选原因；只能陈述两份已记录重量及当前不能归因。涉及重量原因时，不讨论双面结构所占程度、比例、主次或可能性；这些表达仍暗示了部分归因。对照只是一份同季同长度 M 码样衣记录，不得泛化成普通、一般、通常或普遍的单层/双面外套品类结论。用户种子明确给出的品牌开发选择要与相伴限制自然讲清，但不要求固定词、数字或字段逐字重复。创意、比喻、幽默、情绪、节奏和未来拍摄安排可以充分表达，只要不把它们伪装成已经发生的商品事实或现实经历。没有明确确认拍摄当天重新称量时，绝不写实测、电子秤、称重画面、称重声音或当前不存在的对照样衣。不要在可见文字中加入资产、版本、路由、提示或后台字段。"""
        )
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
当前可拍对象边界：{production_fact_boundary}
无商品事实边界：{no_product_guard or "（当前有已点名商品，仍只可使用上述事实）"}
本次适用资产：{assets}
已授权前情：{prior}
来源关系：{source}
本次修改：{revision}
用户种子：{request.weak_seed}
事实边界：用户明确讲述为真实经历的人物、事件和对白可作为本次前提；问题、观点或一般话题里提到的人物与场景，不代表实际发生、可供拍摄或已经获授权。不得新增未提供的具体商品属性或现实事件。商品只可作当前商品事实明确支持的肯定主张；资料未提供时可以诚实说明“现有资料不能证明”。用户种子中的承重商品或品牌前提应在成品中自然保留，不要求固定词、数字、同一句式或合同字段逐字复述。品牌、账号、组织和内容角色只决定发声身份、语气和权威边界，不构成已经发生的门店或顾客事件。成品必须始终由当前内容角色发声，不得擅自变成妈妈、爸爸、孩子、创始人、研发、店长、店员或顾客。除非用户明确提供真人、场地或现成素材，画面只能使用当前一名创作者和普通室内条件；谈论家庭、孩子、顾客或门店时，优先采用正对手机口播、画外音、手写关键词或不依赖具体人物的简单动作。不得声称“我们试过”“我们经常被问”“我们遇到过”或“我们店里发生过”，除非用户本次明确提供该事实。不要复述个人标识，不要把提示或后台字段写入成品。
{writing_boundary}
跨目标重编译时，保留源版本的主要价值、品牌账号角色、受众关系、用户前提、商品事实、核心结论和已确认前情；只重组目标平台/媒体的入口、顺序、声画或图文分工、自然时长、发布配文和制作方式。不得把旧版覆盖、说成已经采用或发布，也不要输出来源 ID。
严格返回 JSON，字段：title, {fields}, {media_fields}。不要返回 body。每个字段必须是一个非空中文字符串，绝不能是数组、对象或多条列表。三个合同字段必须在完整成品中以自然语言兑现，不要求逐字复制、塞入同一句或在每个媒体字段重复。"""

    @staticmethod
    def _boundary_repair_prompt(
        draft: dict[str, object],
        boundary: FactBoundary,
        violations: tuple[FactViolation, ...],
    ) -> str:
        fields = tuple(dict.fromkeys(violation.field for violation in violations))
        del draft
        if boundary.product_facts == "（无当前商品事实）":
            return f"""只修复下列字段；不得返回任何未列字段，服务端会保留其余合格字段。
当前没有可用商品事实。每个待修字段只能使用用户明确前提、选择条件、改变条件和低成本验证动作。一般方法或假设可以使用颜色、品类与搭配例子，但不得把它们写成当前品牌商品、用户衣柜或已经存在的拍摄道具。未来拍摄构思可以保留，但不能描写未提供的服装、人物或现场。
问题中提到的家庭、妈妈、孩子、顾客或门店只是讨论对象，不可改写成账号亲历或可拍资源。画面只使用当前内容角色、一名创作者、一部手机和普通室内条件；可用正对手机口播、画外音、手写关键词或不依赖具体人物的简单动作。
品牌关系观点不能改写成门店已经执行的服务办法、全国承诺或顾客经历，只能表达当前品牌立场和判断。
用户明确前提：{boundary.explicit_premise}
请依据用户明确前提，为下列字段重新写出自然、完整的替换值：{", ".join(fields)}。
严格只返回一个 JSON 对象，键必须恰好为：{", ".join(fields)}。每个值必须是对应字段修复后的非空中文字符串。"""
        current_products = "、".join(boundary.product_skus) or "当前已点名商品"
        comparison_visual_repair = (
            "待修视觉字段不得提及、展示、悬挂、拿起或并排任何单层外套、对照样衣或第二件商品；"
            f"已知重量只能作为{current_products}画面旁的文字或口播数据出现，"
            "不能伪造为实物对比、称量或重新拍摄。"
            if any(
                DeepSeekGenerator._depicts_unavailable_comparison(boundary, violation.field, violation.fragment)
                for violation in violations
            )
            else ""
        )
        return f"""只修复下列字段；不得返回任何未列字段，服务端会保留其余合格字段。
请只依据可用商品事实和用户明确前提，重新写出下列字段：{", ".join(fields)}。
可用商品事实：{boundary.product_facts}
用户明确前提：{boundary.explicit_premise}
不得新增商品性能、材质、工艺、未提供部位、设计动机、现实人物/事件或重新称量；不得把当前两份样衣资料改写成实拍对比。{comparison_visual_repair}重量原因完全未知：只陈述两份已记录重量、没有结构测试和现有资料无法归因；不得讨论或点名任何候选原因，也不得讨论原因的程度、比例、主次、可能性、影响或增减关系。对照只是一份同季同长度 M 码样衣记录，不得泛化成普通、一般、通常或普遍的单层/双面外套品类结论；不得列举未验证候选因素或未提供性能。条件性、未来拍摄安排和自然表达可以保留。
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
