from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, replace
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

_LOGGER = logging.getLogger(__name__)
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

# Closed-world identifiers. Every reference a model may cite must appear in one
# of these registries; anything outside is "does not exist for this call".
_SPEAKER_ID = "speaker:brand_account"
_CREATOR_ACTOR_ID = "actor:creator"
_PHONE_RESOURCE_ID = "resource:phone"
_VENUE_RESOURCE_ID = "resource:venue"
_ONSITE_TEXT_RESOURCE_ID = "resource:onsite_text"
_BRAND_BASELINE_SOURCE_ID = "source:brand_baseline"
_ROLE_BOUNDARY_SOURCE_ID = "source:role_boundary"
_ORGANIZATION_SOURCE_ID = "source:organization"
_USER_REQUEST_SOURCE_ID = "source:user_request"
_USER_ACTUALITY_SOURCE_ID = "source:user_actuality"
_PRIOR_VERSION_SOURCE_ID = "source:prior_version"

_CLAIM_BASES = ("brand_viewpoint", "user_premise", "confirmed_fact", "conditional_guidance")
_CLAIM_ACTUALITIES = ("non_event", "hypothetical", "user_presented_actual")
_SPOKEN_SLOT = "spoken"
_COVER_PURPOSE = "cover"
_SCENE_PURPOSE = "scene"

# A sound_text that is nothing but a claim-id shorthand ("创作者口播：c8、c9内容").
# The writer means "this step speaks those claims" — a semantics claim_refs
# already carries — so the server resolves it deterministically to the claims'
# own text. Any id mixed into real prose still fails closed downstream.
_SOUND_CLAIM_REFERENCE = re.compile(
    r"^[（(]?\s*(?:创作者)?(?:口播|说|台词|旁白|念)?(?:内容|台词)?\s*[:：]?\s*"
    r"(c\d{1,3}(?:\s*[、,，和/]\s*c\d{1,3})*)"
    r"\s*(?:的)?(?:内容|台词|原文|部分)?\s*[。.!！]?\s*[）)]?$"
)
_CLAIM_ID_TOKEN = re.compile(r"c\d{1,3}")

ReasonCode = Literal[
    "untrusted_role",
    "invented_actuality",
    "unsupported_resource",
    "factual_conflict",
    "media_contract",
]


@dataclass(frozen=True)
class BoundaryContext:
    """Ephemeral, user-invisible input semantics for one generation call.

    The six prose sections keep the input categories separated: a topic is not
    a lived fact, a brand viewpoint is not an executed practice, and a method
    note is not proof that a person, object, venue or asset exists.  The
    registries define the closed world of citable speakers, actors, resources
    and sources for this single call.
    """

    task_topic_or_request: str
    user_presented_actuality: str
    brand_viewpoint: str
    confirmed_actuality: str
    method_guidance: str
    allowed_speaker_and_resources: str
    speaker_id: str
    actors: tuple[tuple[str, str], ...]
    resources: tuple[tuple[str, str], ...]
    viewpoint_sources: tuple[tuple[str, str], ...]
    confirmed_sources: tuple[tuple[str, str], ...]
    premise_sources: tuple[tuple[str, str], ...]
    guidance_sources: tuple[tuple[str, str], ...]
    user_actuality_source: str | None
    product_skus: tuple[str, ...] = ()
    known_numbers: tuple[int, ...] = ()
    known_colors: tuple[str, ...] = ()
    internal_identifiers: tuple[str, ...] = ()

    @property
    def actor_ids(self) -> frozenset[str]:
        return frozenset(identifier for identifier, _ in self.actors)

    @property
    def resource_ids(self) -> frozenset[str]:
        return frozenset(identifier for identifier, _ in self.resources)

    @property
    def source_ids(self) -> frozenset[str]:
        return frozenset(
            identifier
            for identifier, _ in (
                *self.viewpoint_sources,
                *self.confirmed_sources,
                *self.premise_sources,
                *self.guidance_sources,
            )
        )

    def allowed_sources_for_basis(self, basis: str) -> frozenset[str]:
        """The sources that can carry a basis.

        A claim may additionally cite other registered sources (a brand
        viewpoint that names the brand naturally also cites the organization
        record), so the review requires at least one carrying source instead
        of demanding every reference to match.
        """
        if basis == "brand_viewpoint":
            # A viewpoint attributed to the named brand also grounds in the
            # organization's registered existence.
            return frozenset((_ORGANIZATION_SOURCE_ID, *(identifier for identifier, _ in self.viewpoint_sources)))
        if basis == "confirmed_fact":
            return frozenset(identifier for identifier, _ in self.confirmed_sources)
        if basis == "user_premise":
            return frozenset(identifier for identifier, _ in self.premise_sources)
        # Conditional guidance may lean on method notes or the brand baseline.
        return frozenset(identifier for identifier, _ in (*self.guidance_sources, *self.viewpoint_sources))

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

        direction_lines: list[str] = []
        creative = request.creative_direction
        if creative is not None:
            if creative.selections:
                direction_lines.append(
                    "用户本次选择的创作方向（已按当前品牌边界转译，只影响表达方式，不改变事实边界）："
                    + "、".join(
                        f"{item.axis}={item.applied_label}" for item in creative.selections
                    )
                )
            if creative.custom_text:
                direction_lines.append(f"用户本次自然补充的方向要求：{creative.custom_text}")
        if request.collaboration_note:
            # The acting person's own soft collaboration preference: it shapes how we work with
            # them, never what counts as a fact, and it is not written into any tenant record.
            # It steers the writing; it is never material the writing is allowed to talk about.
            direction_lines.append(
                "当前自然人本人的私人协作偏好说明（只影响协作方式与表达取舍，"
                "不作为事实来源，也不代表品牌立场；成品中不得引用、复述、解释或提及这段说明本身，"
                f"只体现它带来的表达取舍）：{request.collaboration_note}"
            )
        for material in request.reference_materials:
            if material.media_type == "text" and material.text_body:
                direction_lines.append(
                    f"用户本次明确选入的文字参考《{material.title}》（只作前提引用，"
                    f"不证明现实事件已发生）：{material.text_body}"
                )
            elif material.reference_note:
                direction_lines.append(
                    f"用户本次明确选入的原件《{material.title}》的人工说明（系统未读取原件本身，"
                    f"不得据此描述画面细节）：{material.reference_note}"
                )
        series = request.series_context
        if series is not None:
            prior_series = "\n".join(
                f"- 系列位置 {entry.position}，冻结版本 V{entry.version}："
                f"{entry.outline}\n{entry.body}"
                for entry in series.prior_entries
            )
            direction_lines.append(
                f"本次明确承接系列《{series.title}》第 {series.target_position} 个位置；"
                f"系列约定：{series.premise or '没有额外约定。'}\n"
                f"实际冻结并使用的必要前情：\n{prior_series or '（此前没有成品。）'}\n"
                + (
                    "用户本次明确把前情作为已经公开的连续叙事前提，可以自然承接。"
                    if series.user_asserted_published_continuity
                    else (
                        "这些前情只用于保持判断、人物和主题连续，不证明受众看过或内容已经发布；"
                        "不得对受众说“上一期/上集已经讲过”。"
                    )
                )
            )
        is_synthetic_fixture = (
            request.brand.business_data_kind == "synthetic_business_fixture"
        )
        if request.primary_product == "local_response" and is_synthetic_fixture:
            direction_lines.append(
                "本次近场种子属于等深模拟业务夹具，只能作为假设情境和演示脚本起点；"
                "不得用第一人称或现实陈述写成当前账号、操作者、门店或顾客真实发生过的经历。"
            )
        topic = "\n".join(
            part
            for part in (request.weak_seed, request.revision_instruction, *direction_lines)
            if part
        )
        # The request contract has no separate channel for user-presented
        # actuality.  Only a local_response request qualifies: its routing
        # contract already requires the user to hand over a real near-field
        # signal.  Every other seed stays a topic and proves nothing.
        if request.primary_product == "local_response" and not is_synthetic_fixture:
            user_actuality = f"用户本次明确给出的真实近场信号（仅限本次使用）：{request.weak_seed}"
            user_actuality_source: str | None = _USER_ACTUALITY_SOURCE_ID
        else:
            user_actuality = ""
            user_actuality_source = None

        products_text = (
            "；".join(
                DeepSeekGenerator._natural_product(
                    product.sku,
                    product.display_name,
                    product.facts,
                )
                for product in request.products
            )
            or "无已确认商品"
        )
        if is_synthetic_fixture:
            confirmed = "\n".join(
                (
                    f"品牌“{request.brand.brand_name}”的生产验收作用域包含等深模拟组织"
                    f"“{request.brand.organization_name}”和等深模拟表达身份"
                    f"“{request.brand.account_name}”；这些对象真实存在于生产数据库，"
                    "但不代表现实员工或现实经营账号。",
                    f"当前演示商品事实：{products_text}。这些事实只用于等深模拟业务验收，"
                    "不证明真实在售、库存、价格、性能、设计动机或销售结果。",
                    "除以上演示资料外：无真实门店事实、无已执行服务、无顾客案例、"
                    "无家庭事件、无既有照片或素材。成品属于演示成品，不得冒充现实经营记录。",
                )
            )
        else:
            confirmed = "\n".join(
                (
                    f"品牌“{request.brand.brand_name}”属组织“{request.brand.organization_name}”；"
                    f"当前发布账号“{request.brand.account_name}”真实存在。",
                    f"当前商品事实：{products_text}。",
                    "除以上外：无已确认门店事实、无已执行服务、无顾客案例、无家庭事件、"
                    "无既有照片或素材。",
                )
            )
        method = (
            ("\n".join(asset.body for asset in request.active_domain_assets) + "\n")
            if request.active_domain_assets
            else ""
        ) + "方法资料只提供创作与制作方法，不证明任何现实人物、物品、场地或素材存在。"

        viewpoint_sources: tuple[tuple[str, str], ...] = (
            (_BRAND_BASELINE_SOURCE_ID, "品牌定位、判断顺序与语气基线"),
            (_ROLE_BOUNDARY_SOURCE_ID, "账号内容角色与表达边界"),
        )
        confirmed_sources: tuple[tuple[str, str], ...] = (
            (
                _ORGANIZATION_SOURCE_ID,
                (
                    "生产数据库内的等深模拟组织与表达身份"
                    if is_synthetic_fixture
                    else "品牌、组织与发布账号在册事实"
                ),
            ),
            *(
                (
                    f"source:product:{product.sku}",
                    (
                        f"演示商品 {product.sku} 的等深模拟登记事实"
                        if product.source_kind == "synthetic_business_fixture"
                        else f"已确认商品 {product.sku} 的登记事实"
                    ),
                )
                for product in request.products
            ),
        )
        premise_sources: list[tuple[str, str]] = [(_USER_REQUEST_SOURCE_ID, "本次话题/请求原文")]
        if user_actuality_source is not None:
            premise_sources.append((_USER_ACTUALITY_SOURCE_ID, "用户本次明确提供的真实情况"))
        if request.prior_saved_body:
            premise_sources.append((_PRIOR_VERSION_SOURCE_ID, "已授权复用的旧版本正文"))
        if series is not None:
            premise_sources.extend(
                (
                    f"source:series:{entry.version_id}",
                    f"系列《{series.title}》位置 {entry.position} 的冻结版本",
                )
                for entry in series.prior_entries
            )
        premise_sources.extend(
            (f"source:material:{material.asset_id}", f"用户本次明确选入的参考《{material.title}》")
            for material in request.reference_materials
        )
        guidance_sources: tuple[tuple[str, str], ...] = tuple(
            (f"source:method:{index}", asset.display_name)
            for index, asset in enumerate(request.active_domain_assets, start=1)
        )
        resources: tuple[tuple[str, str], ...] = (
            (_PHONE_RESOURCE_ID, "一部手机（拍摄与收音）"),
            (
                _VENUE_RESOURCE_ID,
                "普通室内或门店环境，仅场地本身；场地内未明确提供的人物、商品、家具、合照、道具不包含在内",
            ),
            (_ONSITE_TEXT_RESOURCE_ID, "创作者现场手写字卡或手机屏幕文字"),
            *((f"resource:product:{product.sku}", f"已确认商品样衣 {product.sku}") for product in request.products),
        )

        return cls(
            task_topic_or_request=topic,
            user_presented_actuality=user_actuality,
            brand_viewpoint=(
                f"品牌“{request.brand.brand_name}”当前确认基线：定位“{request.brand.positioning}”；"
                f"判断顺序“{request.brand.decision_order}”；语气“{request.brand.tone}”。"
                "品牌可以据此表达认为、希望、主张或建议；这些是立场与方向，"
                "不证明品牌观察过、经历过或已经执行任何具体事件，"
                "也不得升级为操作人亲历、顾客案例、门店已执行做法或普遍政策。"
            ),
            confirmed_actuality=confirmed,
            method_guidance=method,
            allowed_speaker_and_resources=(
                f"当前发布账号“{request.brand.account_name}”；内容角色“{request.brand.content_role_name}”；"
                f"表达边界“{request.brand.content_role_boundary}”。"
                + (
                    ""
                    if request.account_expression is None
                    else (
                        f"该账号当前表达画像 V{request.account_expression.version}："
                        f"表达身份“{request.account_expression.identity_position}”；"
                        f"资格与权威边界“{request.account_expression.authority_boundary}”；"
                        f"受众关系“{request.account_expression.audience_relationship}”；"
                        f"内容领地“{request.account_expression.content_territories}”；"
                        f"默认制作条件“{request.account_expression.default_production_conditions}”。"
                        "画像只说明表达位置与资格边界，不证明本次人物、设备、场地或素材已经存在。"
                    )
                )
                + f"实际操作人“{request.brand.operator_name}”仅是操作者与拍摄者，不自动成为成品叙事人物。"
                f"当前可用条件：{request.brand.production_conditions}。"
                "这是能力选择，不证明场地内存在家庭成员、顾客、商品、合照、家具或已执行服务；"
                "未在登记表中列出的人物、设备、场地和素材一律视为当前不可用。"
                "话题中出现的对象不是可拍资源，当前创作者也不能扮演该对象。"
            ),
            speaker_id=_SPEAKER_ID,
            actors=((_CREATOR_ACTOR_ID, "当前创作者（实际操作人，仅以拍摄者/口播者身份出现，不扮演话题人物）"),),
            resources=resources,
            viewpoint_sources=viewpoint_sources,
            confirmed_sources=confirmed_sources,
            premise_sources=tuple(premise_sources),
            guidance_sources=guidance_sources,
            user_actuality_source=user_actuality_source,
            product_skus=tuple(product.sku for product in request.products),
            known_numbers=tuple(dict.fromkeys(numbers)),
            known_colors=tuple(dict.fromkeys(colors)),
            internal_identifiers=(
                request.brand.strategy_version,
                *(asset.asset_id for asset in request.active_domain_assets),
            ),
        )


@dataclass(frozen=True)
class ContentClaim:
    """One visible semantic unit with its declared basis and actuality."""

    claim_id: str
    slot: str
    text: str
    basis: str
    actuality: str
    source_refs: tuple[str, ...]


@dataclass(frozen=True)
class SceneStep:
    """One directly producible step of the visible viewing/reading chain."""

    step_id: str
    purpose: str
    actor_refs: tuple[str, ...]
    resource_refs: tuple[str, ...]
    action_text: str
    sound_text: str
    production_note: str
    claim_refs: tuple[str, ...]


@dataclass(frozen=True)
class ContentCore:
    """Structured draft that lives only inside one generation call."""

    speaker_ref: str
    claims: tuple[ContentClaim, ...]
    spoken_order: tuple[str, ...]
    scene_steps: tuple[SceneStep, ...]

    def claim(self, claim_id: str) -> ContentClaim:
        for candidate in self.claims:
            if candidate.claim_id == claim_id:
                return candidate
        raise KeyError(claim_id)

    @property
    def unit_ids(self) -> tuple[str, ...]:
        return tuple(claim.claim_id for claim in self.claims) + tuple(step.step_id for step in self.scene_steps)


@dataclass(frozen=True)
class UnitIssue:
    """A fail-closed finding against one claim or scene step."""

    unit_id: str
    reason_code: ReasonCode
    fragment: str


class DeepSeekGenerator(ContentGenerator):
    """Single-provider adapter: structured core, closed-world review, compiled product."""

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
        # The judgement call runs with its own bounded configuration: provider
        # reasoning stays available (it is not the writing call) and gets a
        # wider, still finite time budget.
        self._judge_timeout_seconds = max(timeout_seconds, 60.0)

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
        core: ContentCore | None = None
        for format_attempt in range(2):
            system = (
                "你是笛语完整内容编写器。只交付一个 ContentCore JSON，不展示提示词、边界分类、证据、路由、规则或推理。"
            )
            if format_attempt:
                system += (
                    "上一次响应不满足 ContentCore 结构要求（字段缺失、职责数量不对、引用了不存在的单元或为空）；"
                    "这次必须严格按照指定结构返回全部字段。"
                )
            payload, request_retries = self._request(
                system,
                self._generation_prompt(request, context),
                6144,
            )
            provider_payloads.append(payload)
            retries += request_retries
            try:
                core = self._parse_core(
                    request,
                    context,
                    json.loads(self._json_content(str(payload["choices"][0]["message"]["content"]))),
                )
                core = self._replace_registered_product_identifiers(request, core)
                break
            except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
                if format_attempt:
                    raise GenerationFailed("模型返回格式不完整") from exc
                format_repairs = 1
        if core is None:  # pragma: no cover - loop either parses a core or raises.
            raise GenerationFailed("模型返回格式不完整")

        issues, judgement_payload, judgement_retries = self._review_core(request, context, core)
        provider_payloads.append(judgement_payload)
        retries += judgement_retries
        fact_repair_receipts: tuple[FactRepairReceipt, ...] = ()
        if issues:
            payload, repair_retries = self._request(
                "你是笛语内容编写器。只交付待修单元 JSON，不展示边界分类、证据、规则、推理或后台信息。",
                self._unit_repair_prompt(request, context, core, issues),
                6144,
            )
            provider_payloads.append(payload)
            retries += repair_retries
            try:
                repaired_core = self._merge_repaired_units(
                    request,
                    core,
                    issues,
                    json.loads(self._json_content(str(payload["choices"][0]["message"]["content"]))),
                )
                repaired_core = self._replace_registered_product_identifiers(request, repaired_core)
            except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise GenerationFailed("模型边界修复返回格式不完整") from exc
            final_issues, judgement_payload, judgement_retries = self._review_core(request, context, repaired_core)
            provider_payloads.append(judgement_payload)
            retries += judgement_retries
            if final_issues:
                _LOGGER.warning(
                    "content boundary remained unsatisfied after unit repair: %s",
                    ",".join(f"{issue.unit_id}:{issue.reason_code}" for issue in final_issues),
                )
                raise GenerationFailed("内容边界无法在一次单元修复内满足")
            fact_repair_receipts = self._issue_receipts(request, core, issues)
            core = repaired_core
        title, contract, production, body = self._compile_core(request, core)
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

    # ------------------------------------------------------------------
    # ContentCore parsing (structural fail-closed layer)
    # ------------------------------------------------------------------

    @staticmethod
    def _singleton_slots(product: ContentProduct, media_format: str) -> tuple[str, ...]:
        base: tuple[str, ...] = ("title", "natural_guide", "release_caption")
        if media_format == "video":
            base = (*base, "viewing_flow")
        return (*base, *_CONTRACT_FIELDS[product])

    @staticmethod
    def _required_string(value: object) -> str:
        if not isinstance(value, str) or not value.strip():
            raise TypeError("core field must be a non-empty string")
        return value.strip()

    @staticmethod
    def _optional_string(value: object) -> str:
        if value is None:
            return ""
        if not isinstance(value, str):
            raise TypeError("core field must be a string")
        return value.strip()

    @staticmethod
    def _string_refs(value: object) -> tuple[str, ...]:
        if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
            raise TypeError("references must be a list of non-empty strings")
        return tuple(dict.fromkeys(item.strip() for item in value))

    def _parse_core(
        self,
        request: GenerationInput,
        context: BoundaryContext,
        raw: object,
    ) -> ContentCore:
        if not isinstance(raw, dict):
            raise TypeError("core must be an object")
        if raw.get("speaker_ref") != context.speaker_id:
            raise ValueError("speaker_ref must be the registered speaker")
        raw_claims = raw.get("claims")
        raw_order = raw.get("spoken_order")
        raw_steps = raw.get("scene_steps")
        if not isinstance(raw_claims, list) or not raw_claims:
            raise TypeError("claims must be a non-empty list")
        if not isinstance(raw_order, list) or not raw_order:
            raise TypeError("spoken_order must be a non-empty list")
        if not isinstance(raw_steps, list) or not raw_steps:
            raise TypeError("scene_steps must be a non-empty list")

        singleton_slots = self._singleton_slots(request.primary_product, request.media_format)
        allowed_slots = {*singleton_slots, _SPOKEN_SLOT}
        claims: list[ContentClaim] = []
        for entry in raw_claims:
            if not isinstance(entry, dict):
                raise TypeError("claim must be an object")
            slot = self._required_string(entry.get("slot"))
            if slot not in allowed_slots:
                raise ValueError(f"unknown claim slot: {slot}")
            basis = self._required_string(entry.get("basis"))
            actuality = self._required_string(entry.get("actuality"))
            if basis not in _CLAIM_BASES:
                raise ValueError(f"unknown claim basis: {basis}")
            if actuality not in _CLAIM_ACTUALITIES:
                raise ValueError(f"unknown claim actuality: {actuality}")
            claims.append(
                ContentClaim(
                    claim_id=self._required_string(entry.get("claim_id")),
                    slot=slot,
                    text=self._required_string(entry.get("text")),
                    basis=basis,
                    actuality=actuality,
                    source_refs=self._string_refs(entry.get("source_refs")),
                )
            )
        claim_ids = [claim.claim_id for claim in claims]
        if len(set(claim_ids)) != len(claim_ids):
            raise ValueError("claim ids must be unique")
        for slot in singleton_slots:
            if sum(1 for claim in claims if claim.slot == slot) != 1:
                raise ValueError(f"slot {slot} must appear exactly once")
        spoken_ids = [claim.claim_id for claim in claims if claim.slot == _SPOKEN_SLOT]
        if not spoken_ids:
            raise ValueError("at least one spoken claim is required")
        order = [self._required_string(item) for item in raw_order]
        if len(order) != len(spoken_ids) or set(order) != set(spoken_ids):
            raise ValueError("spoken_order must cover every spoken claim exactly once")

        steps: list[SceneStep] = []
        for entry in raw_steps:
            if not isinstance(entry, dict):
                raise TypeError("scene step must be an object")
            purpose = self._required_string(entry.get("purpose"))
            if purpose not in (_COVER_PURPOSE, _SCENE_PURPOSE):
                raise ValueError(f"unknown step purpose: {purpose}")
            claim_refs = self._string_refs(entry.get("claim_refs"))
            if not claim_refs or any(ref not in claim_ids for ref in claim_refs):
                raise ValueError("every scene step must reference existing claims")
            steps.append(
                SceneStep(
                    step_id=self._required_string(entry.get("step_id")),
                    purpose=purpose,
                    actor_refs=self._string_refs(entry.get("actor_refs") or []),
                    resource_refs=self._string_refs(entry.get("resource_refs") or []),
                    action_text=self._required_string(entry.get("action_text")),
                    sound_text=self._optional_string(entry.get("sound_text")),
                    production_note=self._optional_string(entry.get("production_note")),
                    claim_refs=claim_refs,
                )
            )
        step_ids = [step.step_id for step in steps]
        if len(set(step_ids)) != len(step_ids) or set(step_ids) & set(claim_ids):
            raise ValueError("step ids must be unique and distinct from claim ids")
        if sum(1 for step in steps if step.purpose == _COVER_PURPOSE) != 1:
            raise ValueError("exactly one cover step is required")
        if not any(step.purpose == _SCENE_PURPOSE for step in steps):
            raise ValueError("at least one scene step is required")
        core = self._resolve_sound_references(
            ContentCore(
                speaker_ref=context.speaker_id,
                claims=tuple(claims),
                spoken_order=tuple(order),
                scene_steps=tuple(steps),
            )
        )
        self._assert_media_presence(request, core)
        return core

    @staticmethod
    def _resolve_sound_references(core: ContentCore) -> ContentCore:
        claim_text = {claim.claim_id: claim.text for claim in core.claims}
        steps: list[SceneStep] = []
        changed = False
        for step in core.scene_steps:
            match = _SOUND_CLAIM_REFERENCE.match(step.sound_text.strip()) if step.sound_text else None
            if match:
                refs = _CLAIM_ID_TOKEN.findall(match.group(1))
                if refs and all(ref in step.claim_refs and ref in claim_text for ref in refs):
                    spoken = "".join(claim_text[ref] for ref in refs)
                    steps.append(replace(step, sound_text=f"创作者口播：{spoken}"))
                    changed = True
                    continue
            steps.append(step)
        if not changed:
            return core
        return ContentCore(
            speaker_ref=core.speaker_ref,
            claims=core.claims,
            spoken_order=core.spoken_order,
            scene_steps=tuple(steps),
        )

    @staticmethod
    def _replace_registered_product_identifiers(
        request: GenerationInput,
        core: ContentCore,
    ) -> ContentCore:
        """Keep internal product identifiers out of the visible artifact.

        Product source and resource references retain the frozen SKU. Only
        user-visible prose is normalized, using the display name from the same
        registered ProductFact snapshot rather than a model guess.
        """

        replacements = tuple(
            sorted(
                (
                    (product.sku, product.display_name.strip() or "当前商品")
                    for product in request.products
                    if product.sku and product.sku != product.display_name.strip()
                ),
                key=lambda item: len(item[0]),
                reverse=True,
            )
        )
        if not replacements:
            return core

        def visible(text: str) -> str:
            for identifier, display_name in replacements:
                text = text.replace(identifier, display_name)
            return text

        return ContentCore(
            speaker_ref=core.speaker_ref,
            claims=tuple(replace(claim, text=visible(claim.text)) for claim in core.claims),
            spoken_order=core.spoken_order,
            scene_steps=tuple(
                replace(
                    step,
                    action_text=visible(step.action_text),
                    sound_text=visible(step.sound_text),
                    production_note=visible(step.production_note),
                )
                for step in core.scene_steps
            ),
        )

    @staticmethod
    def _assert_media_presence(request: GenerationInput, core: ContentCore) -> None:
        if request.media_format == "video":
            if not any(step.sound_text or step.production_note for step in core.scene_steps):
                raise ValueError("video steps must carry at least one sound or production note")
        elif not any(step.production_note for step in core.scene_steps):
            raise ValueError("graphic steps must carry at least one production note")

    # ------------------------------------------------------------------
    # Fail-closed review: closed world + deterministic + complete verdicts
    # ------------------------------------------------------------------

    def _review_core(
        self,
        request: GenerationInput,
        context: BoundaryContext,
        core: ContentCore,
    ) -> tuple[tuple[UnitIssue, ...], dict[str, Any], int]:
        server_side = (
            *self._closed_world_issues(context, core),
            *self._deterministic_unit_issues(context, core),
            *self._media_issues(request, core),
        )
        judged, payload, retries = self._judgement_issues(context, core)
        merged: dict[tuple[str, str], UnitIssue] = {}
        for issue in (*server_side, *judged):
            merged.setdefault((issue.unit_id, issue.reason_code), issue)
        return tuple(merged.values()), payload, retries

    @staticmethod
    def _closed_world_issues(context: BoundaryContext, core: ContentCore) -> tuple[UnitIssue, ...]:
        issues: list[UnitIssue] = []
        for claim in core.claims:
            # Closed world: every reference must be registered, and at least
            # one reference must be able to carry the declared basis.
            allowed = context.allowed_sources_for_basis(claim.basis)
            if (
                not claim.source_refs
                or any(ref not in context.source_ids for ref in claim.source_refs)
                or not any(ref in allowed for ref in claim.source_refs)
            ):
                issues.append(UnitIssue(claim.claim_id, "factual_conflict", claim.text))
            if claim.actuality == "user_presented_actual" and (
                context.user_actuality_source is None or _USER_ACTUALITY_SOURCE_ID not in claim.source_refs
            ):
                issues.append(UnitIssue(claim.claim_id, "invented_actuality", claim.text))
            if (
                claim.basis in ("brand_viewpoint", "conditional_guidance")
                and claim.actuality == "user_presented_actual"
            ):
                issues.append(UnitIssue(claim.claim_id, "invented_actuality", claim.text))
            if claim.basis == "confirmed_fact" and claim.actuality != "non_event":
                issues.append(UnitIssue(claim.claim_id, "invented_actuality", claim.text))
        for step in core.scene_steps:
            if any(ref not in context.actor_ids for ref in step.actor_refs):
                issues.append(UnitIssue(step.step_id, "untrusted_role", step.action_text))
        return tuple(issues)

    @staticmethod
    def _deterministic_unit_issues(context: BoundaryContext, core: ContentCore) -> tuple[UnitIssue, ...]:
        """Keep exact identifiers and concrete product values on trusted rails."""
        internal_identifier = re.compile(
            r"(?:schema[_ -]?version|asset[_ -]?id|DIYU-[A-Z0-9-]+)",
            re.IGNORECASE,
        )
        reference_leak = re.compile(r"(?:speaker|actor|resource|source)\s*[:：]\s*[A-Za-z0-9_.:-]+", re.IGNORECASE)
        # Bare internal unit ids ("c8" / "s2") must never surface in visible
        # text.  ASCII lookarounds instead of \b: a preceding CJK character is
        # still a word character, so \b would miss "对应c8".  Lowercase-only
        # keeps confirmed SKUs like ZX-C218 unaffected.
        unit_id_leak = re.compile(r"(?<![A-Za-z0-9])[cs]\d{1,3}(?![A-Za-z0-9])")
        personal_identifier = re.compile(r"1[3-9]\d{9}|[\w.+-]+@[\w.-]+|订单号?\s*[:：]?\s*[A-Za-z0-9-]+")
        sku_pattern = re.compile(r"\b[A-Z]{2,}(?:-[A-Z0-9]+)+\b")
        measured_value = re.compile(r"(?<!\d)(\d{1,6})\s*(?:克|元|%|厘米|cm)\b", re.IGNORECASE)
        colour = re.compile(r"(黑色|白色|蓝色|红色|黄色|紫色|棕色|灰色|绿色|炭灰|深绿)")
        product_marker = re.compile(r"(?:当前商品|这件商品|该商品|当前样衣)")

        def scan(unit_id: str, text: str, product_bound: bool) -> list[UnitIssue]:
            found: list[UnitIssue] = []
            for identifier in context.internal_identifiers:
                if identifier and identifier in text:
                    found.append(UnitIssue(unit_id, "factual_conflict", identifier))
            for pattern in (internal_identifier, reference_leak, unit_id_leak, personal_identifier):
                for match in pattern.finditer(text):
                    found.append(UnitIssue(unit_id, "factual_conflict", match.group(0)))
            for sku in sku_pattern.findall(text):
                if sku not in context.product_skus:
                    found.append(UnitIssue(unit_id, "factual_conflict", sku))
            if not context.product_skus:
                return found
            specific = (
                product_bound or any(sku in text for sku in context.product_skus) or bool(product_marker.search(text))
            )
            if not specific:
                return found
            for match in measured_value.finditer(text):
                if int(match.group(1)) not in context.known_numbers:
                    found.append(UnitIssue(unit_id, "factual_conflict", match.group(0)))
            if context.known_colors:
                for match in colour.finditer(text):
                    if not any(match.group(1) in known for known in context.known_colors):
                        found.append(UnitIssue(unit_id, "factual_conflict", match.group(0)))
            return found

        issues: list[UnitIssue] = []
        for claim in core.claims:
            issues.extend(scan(claim.claim_id, claim.text, claim.basis == "confirmed_fact"))
        for step in core.scene_steps:
            for text in (step.action_text, step.sound_text, step.production_note):
                if text:
                    issues.extend(scan(step.step_id, text, False))
        return tuple(dict.fromkeys(issues))

    def _media_issues(self, request: GenerationInput, core: ContentCore) -> tuple[UnitIssue, ...]:
        if request.media_format != "video":
            return ()
        spoken = self._compiled_spoken(core)
        if self._is_no_voice(spoken):
            return ()
        fixed_seconds = self._fixed_duration_seconds(request.brand.production_conditions)
        if fixed_seconds is not None and self._natural_spoken_seconds(spoken) > fixed_seconds:
            return tuple(
                UnitIssue(claim_id, "media_contract", core.claim(claim_id).text) for claim_id in core.spoken_order
            )
        return ()

    def _judgement_issues(
        self,
        context: BoundaryContext,
        core: ContentCore,
    ) -> tuple[tuple[UnitIssue, ...], dict[str, Any], int]:
        payload, retries = self._request(
            ("你是笛语内容边界判定器。对每个单元独立做完整判定，只返回最终 JSON；不改写成品，不展示核对过程或推理。"),
            self._judgement_prompt(context, core),
            # Provider reasoning tokens are billed inside max_tokens; the
            # bounded budget must leave room for reasoning plus one complete
            # verdict per unit, or the verdict JSON truncates and fails closed.
            8192,
            thinking_disabled=False,
            timeout_seconds=self._judge_timeout_seconds,
        )
        verdicts = self._parse_verdicts(payload, core.unit_ids)
        issues: list[UnitIssue] = []
        reason_by_flag: tuple[tuple[str, ReasonCode], ...] = (
            ("identity_ok", "untrusted_role"),
            ("actuality_ok", "invented_actuality"),
            ("fact_ok", "factual_conflict"),
        )
        step_by_id = {step.step_id: step for step in core.scene_steps}
        for unit_id in core.unit_ids:
            verdict = verdicts[unit_id]
            fragment = core.claim(unit_id).text if unit_id not in step_by_id else step_by_id[unit_id].action_text
            for flag, reason in reason_by_flag:
                if not verdict[flag]:
                    issues.append(UnitIssue(unit_id, reason, fragment))
        return tuple(issues), payload, retries

    @staticmethod
    def _parse_verdicts(payload: dict[str, Any], expected_ids: tuple[str, ...]) -> dict[str, dict[str, bool]]:
        """Every unit gets a complete verdict; a sparse or drifting id set fails closed."""
        try:
            result = json.loads(DeepSeekGenerator._json_content(str(payload["choices"][0]["message"]["content"])))
            raw_verdicts = result["verdicts"]
            if not isinstance(raw_verdicts, list):
                raise TypeError("verdicts must be a list")
            verdicts: dict[str, dict[str, bool]] = {}
            for entry in raw_verdicts:
                if not isinstance(entry, dict):
                    raise TypeError("verdict must be an object")
                unit_id = entry.get("id")
                if not isinstance(unit_id, str) or unit_id not in expected_ids or unit_id in verdicts:
                    raise TypeError("verdict id set does not match the units under review")
                flags: dict[str, bool] = {}
                for flag in ("identity_ok", "actuality_ok", "resource_ok", "fact_ok"):
                    value = entry.get(flag)
                    if not isinstance(value, bool):
                        raise TypeError("verdict flags must be complete booleans")
                    flags[flag] = value
                verdicts[unit_id] = flags
            if set(verdicts) != set(expected_ids):
                raise TypeError("verdict id set does not match the units under review")
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise GenerationFailed("模型边界判定返回格式不完整") from exc
        return verdicts

    # ------------------------------------------------------------------
    # One unit-level repair, then a fresh complete review
    # ------------------------------------------------------------------

    def _merge_repaired_units(
        self,
        request: GenerationInput,
        core: ContentCore,
        issues: tuple[UnitIssue, ...],
        raw: object,
    ) -> ContentCore:
        if not isinstance(raw, dict):
            raise TypeError("repair must be an object")
        raw_repairs = raw.get("repairs")
        if not isinstance(raw_repairs, list):
            raise TypeError("repairs must be a list")
        requested = {issue.unit_id for issue in issues}
        claim_ids = {claim.claim_id for claim in core.claims}
        replacements_claims: dict[str, ContentClaim] = {}
        replacements_steps: dict[str, SceneStep] = {}
        for entry in raw_repairs:
            if not isinstance(entry, dict):
                raise TypeError("repair unit must be an object")
            claim_id = entry.get("claim_id")
            step_id = entry.get("step_id")
            if isinstance(claim_id, str) and claim_id in claim_ids:
                if claim_id not in requested or claim_id in replacements_claims:
                    raise TypeError("repair units do not match the requested units")
                original = core.claim(claim_id)
                basis = self._required_string(entry.get("basis"))
                actuality = self._required_string(entry.get("actuality"))
                if basis not in _CLAIM_BASES or actuality not in _CLAIM_ACTUALITIES:
                    raise ValueError("repaired claim uses an unknown basis or actuality")
                replacements_claims[claim_id] = replace(
                    original,
                    text=self._required_string(entry.get("text")),
                    basis=basis,
                    actuality=actuality,
                    source_refs=self._string_refs(entry.get("source_refs")),
                )
            elif isinstance(step_id, str):
                if step_id not in requested or step_id in replacements_steps:
                    raise TypeError("repair units do not match the requested units")
                original_step = next((step for step in core.scene_steps if step.step_id == step_id), None)
                if original_step is None:
                    raise TypeError("repair units do not match the requested units")
                claim_refs = self._string_refs(entry.get("claim_refs"))
                if not claim_refs or any(ref not in claim_ids for ref in claim_refs):
                    raise ValueError("repaired step must reference existing claims")
                replacements_steps[step_id] = replace(
                    original_step,
                    actor_refs=self._string_refs(entry.get("actor_refs") or []),
                    resource_refs=self._string_refs(entry.get("resource_refs") or []),
                    action_text=self._required_string(entry.get("action_text")),
                    sound_text=self._optional_string(entry.get("sound_text")),
                    production_note=self._optional_string(entry.get("production_note")),
                    claim_refs=claim_refs,
                )
            else:
                raise TypeError("repair units do not match the requested units")
        if set(replacements_claims) | set(replacements_steps) != requested:
            raise TypeError("repair units do not match the requested units")
        repaired = self._resolve_sound_references(
            ContentCore(
                speaker_ref=core.speaker_ref,
                claims=tuple(replacements_claims.get(claim.claim_id, claim) for claim in core.claims),
                spoken_order=core.spoken_order,
                scene_steps=tuple(replacements_steps.get(step.step_id, step) for step in core.scene_steps),
            )
        )
        self._assert_media_presence(request, repaired)
        return repaired

    def _issue_receipts(
        self,
        request: GenerationInput,
        core: ContentCore,
        issues: tuple[UnitIssue, ...],
    ) -> tuple[FactRepairReceipt, ...]:
        step_by_id = {step.step_id: step for step in core.scene_steps}
        by_field: dict[str, list[str]] = {}
        for issue in issues:
            if issue.unit_id in step_by_id:
                field = self._step_field(request, step_by_id[issue.unit_id])
            else:
                field = self._claim_field(request, core.claim(issue.unit_id))
            by_field.setdefault(field, []).append(issue.fragment)
        return tuple(FactRepairReceipt(field, tuple(dict.fromkeys(fragments))) for field, fragments in by_field.items())

    @staticmethod
    def _claim_field(request: GenerationInput, claim: ContentClaim) -> str:
        if claim.slot == _SPOKEN_SLOT:
            return "spoken_lines" if request.media_format == "video" else "full_body"
        if claim.slot == "release_caption":
            return "release_caption_and_interaction"
        return claim.slot

    @staticmethod
    def _step_field(request: GenerationInput, step: SceneStep) -> str:
        if step.purpose == _COVER_PURPOSE:
            return "cover_or_first_frame" if request.media_format == "video" else "hero_image"
        return "visual_actions" if request.media_format == "video" else "image_sequence"

    # ------------------------------------------------------------------
    # Server-side compilation of the existing visible product
    # ------------------------------------------------------------------

    @staticmethod
    def _compiled_spoken(core: ContentCore) -> str:
        return "".join(core.claim(claim_id).text for claim_id in core.spoken_order)

    def _compile_core(
        self,
        request: GenerationInput,
        core: ContentCore,
    ) -> tuple[str, ContentSemanticContract, ContentProductionBundle, str]:
        slot_text = {claim.slot: claim.text for claim in core.claims if claim.slot != _SPOKEN_SLOT}
        title = self._visible_text(slot_text["title"])
        contract = self._contract(request.primary_product, slot_text)
        spoken = self._visible_text(self._compiled_spoken(core))
        cover = next(step for step in core.scene_steps if step.purpose == _COVER_PURPOSE)
        scenes = tuple(step for step in core.scene_steps if step.purpose == _SCENE_PURPOSE)
        sound_parts: list[str] = []
        for step in core.scene_steps:
            for text in (step.sound_text, step.production_note):
                if text and (not sound_parts or sound_parts[-1] != text):
                    sound_parts.append(text)
        production: ContentProductionBundle
        if request.media_format == "video":
            fixed_seconds = self._fixed_duration_seconds(request.brand.production_conditions)
            if fixed_seconds is not None:
                duration = f"{fixed_seconds} 秒"
            elif self._is_no_voice(spoken):
                # No spoken basis exists; derive a conservative floor from the
                # number of passed scene steps instead of trusting a label.
                duration = f"约 {max(6, 3 * len(scenes))} 秒"
            else:
                duration = f"约 {self._natural_spoken_seconds(spoken)} 秒"
            production = VideoProductionBundle(
                natural_guide=self._visible_text(slot_text["natural_guide"]),
                spoken_lines=spoken,
                visual_actions=self._visible_text("".join(step.action_text for step in scenes)),
                subtitles=spoken,
                sound_and_production=self._visible_text("".join(sound_parts)),
                cover_or_first_frame=self._visible_text(cover.action_text),
                viewing_flow=self._visible_text(slot_text["viewing_flow"]),
                natural_duration=duration,
                release_caption_and_interaction=self._visible_text(slot_text["release_caption"]),
            )
        else:
            production = GraphicProductionBundle(
                natural_guide=self._visible_text(slot_text["natural_guide"]),
                hero_image=self._visible_text(cover.action_text),
                image_sequence=self._visible_text(
                    "".join(f"第{index}张：{step.action_text}" for index, step in enumerate(scenes, start=1))
                ),
                full_body=spoken,
                layout_and_production=self._visible_text(
                    "".join(step.production_note for step in core.scene_steps if step.production_note)
                ),
                release_caption_and_interaction=self._visible_text(slot_text["release_caption"]),
            )
        return title, contract, production, self._visible_body(
            title,
            production,
            contract,
            synthetic_business_fixture=(
                request.brand.business_data_kind == "synthetic_business_fixture"
            ),
        )

    @staticmethod
    def _contract(product: ContentProduct, slot_text: dict[str, str]) -> ContentSemanticContract:
        fields = _CONTRACT_FIELDS[product]
        values = tuple(DeepSeekGenerator._visible_text(slot_text[field]) for field in fields)
        if product == "dressing_decision":
            return P1SemanticContract(*values)
        if product == "product_truth":
            return P2SemanticContract(*values)
        if product == "brand_life_narrative":
            return P3SemanticContract(*values)
        if product == "local_response":
            return P4SemanticContract(*values)
        return P5SemanticContract(*values)

    # ------------------------------------------------------------------
    # Provider transport
    # ------------------------------------------------------------------

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

    def _request(
        self,
        system: str,
        prompt: str,
        max_tokens: int,
        *,
        thinking_disabled: bool = True,
        timeout_seconds: float | None = None,
    ) -> tuple[dict[str, Any], int]:
        retries = 0
        request_payload: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            # Fact-bound JSON must not drift through stochastic rewording. A
            # revision still changes when its explicit instruction changes.
            "temperature": 0.0,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        if thinking_disabled:
            # The writing and repair calls need a complete JSON object in the
            # visible content channel, not an open-ended reasoning pass that
            # can exhaust the response budget.  The judgement call keeps the
            # provider default reasoning under its own bounded budget.
            request_payload["thinking"] = {"type": "disabled"}
        with httpx.Client(timeout=httpx.Timeout(timeout_seconds or self._timeout_seconds)) as client:
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
    def _natural_spoken_seconds(spoken: str) -> int:
        readable = len(re.findall(r"[一-鿿]|[A-Za-z0-9]+", spoken))
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
        if not re.search(r"[\w一-鿿]", visible):
            raise TypeError("visible content must contain readable text")
        return visible

    @staticmethod
    def _visible_body(
        title: str,
        production: ContentProductionBundle,
        contract: ContentSemanticContract | None = None,
        *,
        synthetic_business_fixture: bool = False,
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
                (
                    "演示商品锚点"
                    if synthetic_business_fixture
                    else "真实商品锚点",
                    contract.real_product_anchor,
                ),
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

    # ------------------------------------------------------------------
    # Prompts
    # ------------------------------------------------------------------

    @staticmethod
    def _routing_prompt(request: RoutingInput) -> str:
        products = ", ".join(product.sku for product in request.products) or "无已点名商品"
        return f"""判断当前内容工作台输入是否已形成内容任务。只返回 JSON：{{\"primary_value\": \"普通交流\" 或一个自然语言价值}}。
可选自然价值：帮助选择、解释商品、建立人格、经营关系、视觉造型。
按主要受众最终获得的价值判断；只有纯问候或情绪交流返回普通交流。凡是要求把具体商品观察、选择疑问、账号观察、近场回应或画面设想做成可发布内容的输入，必须选择一个内容价值，不能回落为普通交流。独立、可单独采用的新成果重新判断。
帮助选择强调条件、改变条件和下一步；解释商品强调已知事实、限制与不能下的结论；建立人格强调账号怎样观察、判断和待人；经营关系强调近场信号、合法回应和可迁移许可；视觉造型强调必须由画面承重的穿着可能。
解释商品必须以当前已点名且有已确认事实的商品为对象；当前没有已点名商品时不得选择解释商品。品牌、账号或家庭生活观点主要让受众认识账号怎样观察、判断和待人时，选择建立人格。
经营关系必须有用户明确给出的真实评论、门店观察或近场事件；等深模拟业务作用域中明确标记的模拟近场种子也可用于演示这一内容机制，但不能写成真实经历。只有一个假设、一般问题或品牌关系观点而没有近场信号时，选择建立人格，不能把问题补成门店事实。当输入的主回报是让没到店、未参与原事件的人带走一句可迁移的门店关系许可，且已经有近场信号时，即使同时提到人物性格、商品或镜头，也选经营关系。只有主回报是让受众认识账号怎样观察、判断和待人，才选建立人格。当主回报必须通过真实商品与画面变化，让受众直接看见一种新的穿着或造型可能，并且不是帮助选择或解释商品时，选视觉造型；当主回报是说明商品已知、限制和不能下的结论时，选解释商品。
品牌：{request.brand.brand_name}；账号：{request.brand.account_name}；角色：{request.brand.content_role_name}；受众：{request.brand.audience_description}。
当前已点名商品：{products}。
用户输入：{request.weak_seed}"""

    @staticmethod
    def _boundary_sections(context: BoundaryContext) -> str:
        registry_lines = "\n".join(
            (
                f"可用说话人：{context.speaker_id} = 当前发布账号（唯一合法说话人）",
                "可出镜人物："
                + "；".join(f"{identifier} = {description}" for identifier, description in context.actors),
                "可用资源："
                + "；".join(f"{identifier} = {description}" for identifier, description in context.resources),
                "可引用来源："
                + "；".join(
                    f"{identifier} = {description}"
                    for identifier, description in (
                        *context.viewpoint_sources,
                        *context.confirmed_sources,
                        *context.premise_sources,
                        *context.guidance_sources,
                    )
                ),
            )
        )
        return f"""【一、本次话题/请求 task_topic_or_request】用户提出的问题、题材、讨论方向和创作要求。话题中出现的人物、事件、物品只是讨论对象，不是用户亲历，不是身份事实，也不是可拍资源。话题里的疑问句、预设或他人转述（如“是不是很多人都问过你们”）同样只界定要聊什么，不构成品牌或任何人已经发生过的询问、讨论、观察或经历，不得写成既成事实；要引入话题预设，只能以问题、假设或条件表达：
{context.task_topic_or_request}

【二、用户明确提供的真实情况 user_presented_actuality】只有这里列出的内容可以当作用户提供的真实经历、事件或经营事实，仅限本次使用：
{context.user_presented_actuality or "（本次没有。没有列出即为不存在，不得虚构。）"}

【三、品牌观点与立场 brand_viewpoint】
{context.brand_viewpoint}

【四、已确认现实 confirmed_actuality】
{context.confirmed_actuality}

【五、方法与领域知识 method_guidance】
{context.method_guidance}

【六、当前说话人与可用资源 allowed_speaker_and_resources】
{context.allowed_speaker_and_resources}
{registry_lines}"""

    @staticmethod
    def _generation_prompt(
        request: GenerationInput,
        context: BoundaryContext | None = None,
    ) -> str:
        boundary = context or BoundaryContext.from_request(request)
        contract_fields = _CONTRACT_FIELDS[request.primary_product]
        prior = request.prior_saved_body or "（未授权复用旧正文）"
        revision = request.revision_instruction or "（首次生成）"
        source = request.source_version_description or "（不是跨目标重编译）"
        revision_rule = (
            "本次是自然修改：已授权前情只是待修改的旧稿，不是事实来源。修改要求约束全部可见单元；"
            "逐一检查标题、合同字段、导读、完整正文/口播、画面动作、声音、制作提示和发布互动，"
            "凡与修改要求冲突的旧内容都必须删除或重写，不能只改合同字段、摘要或时长标签。"
            if request.revision_instruction
            else "本次是首次生成，不存在需要照搬的旧稿。"
        )
        series_rule = (
            "本次已把所选系列的冻结前情编入边界一；保持必要连续，但不从前情推断发布事实。"
            if request.series_context is not None
            else "本次没有选择系列，不得自行补造系列前情。"
        )
        fixed_seconds = DeepSeekGenerator._fixed_duration_seconds(request.brand.production_conditions)
        transform_boundary = (
            f"用户明确要求 {fixed_seconds} 秒；spoken 单元的完整口播必须真实适配，不要只改时长标签。"
            if fixed_seconds is not None
            else "用户未要求固定时长；保留完整口播，由服务端根据最终口播形成自然时长。"
        )
        product_contract_rule = (
            "本次是画面承重的造型内容：real_product_anchor 只能复述边界四已登记商品的名称、"
            "品类、颜色、材质/结构、轮廓或肉眼可观察特征，basis=confirmed_fact、"
            "actuality=non_event，并引用相应 source:product:…；不得把画面命题、搭配效果、"
            "适合人群或穿着结果混入商品锚点。visible_styling_proposition 和 visual_dependency "
            "只承载本次要求的画面组织与成立条件，不能伪装成已确认商品事实。"
            if request.primary_product == "visual_styling_story"
            else ""
        )
        if request.media_format == "video":
            media_contract = (
                "交付可直接拍摄、表演、录音和剪辑的完整观看链。口播必须完整自然；"
                "字幕与自然时长将由服务端从最终口播确定性派生。声音、动作和画面只能由 scene_steps 承载，"
                "每一步只使用登记表中的人物与资源；不能另造人物、商品、场地、道具、既有图片或事件。"
                "没有明确提供实物时，用当前创作者面对手机口播、手势、现场手写字卡或屏幕文字承担画面，"
                "不安排话题对象出镜。"
            )
            slot_lines = (
                "title（1条，标题）、natural_guide（1条，自然导读）、viewing_flow（1条，完整观看链说明）、"
                "release_caption（1条，发布配文与互动）、"
                + "、".join(f"{field}（1条，合同字段）" for field in contract_fields)
                + "、spoken（≥1条，完整口播按顺序拆成的自然句组；合起来就是完整台词/解说）"
            )
        else:
            media_contract = (
                "交付可直接拍摄、选图、排版和发布的完整阅读链。完整正文由 spoken 单元按顺序构成；"
                "首图与图序由 scene_steps 承载（cover 为首图，scene 为图序各张），每张只使用登记表中的资源；"
                "production_note 写拍摄/排版提示。"
            )
            slot_lines = (
                "title（1条，标题）、natural_guide（1条，自然导读）、"
                "release_caption（1条，发布配文与互动）、"
                + "、".join(f"{field}（1条，合同字段）" for field in contract_fields)
                + "、spoken（≥1条，完整发布正文按顺序拆成的自然段落）"
            )
        return f"""为“{request.brand.account_name}”编写一个完整中文{request.brand.media_format}成品的结构化底稿 ContentCore。
本次受众价值：{_PRODUCT_VALUE[request.primary_product]}；必须只兑现这一价值，不说明路由。
本次交付门：{_DELIVERABLE_REQUIREMENTS[request.primary_product]}
{product_contract_rule}
当前媒体合同：{media_contract}
受众：{request.brand.audience_description}；平台/形式：{request.brand.platform}／{request.brand.media_format}。
目标平台方向：{request.platform_direction.direction}
当前变形边界：{transform_boundary}

以下六类输入语义分开、互不越界；边界未明确提供的事实或资源一律视为不存在：

{DeepSeekGenerator._boundary_sections(boundary)}

已授权前情：{prior}
来源关系：{source}
本次修改：{revision}
修改一致性：{revision_rule}
系列承接：{series_rule}

创作要求：标题、观点、比喻、幽默、节奏、完整口播和互动由你自然创作，允许口语化、停顿感和真实的不完美；
不得写成培训讲义、企业宣言、口号堆叠或固定安全模板。同时：
- 话题中出现对象不表示账号或创作者就是该对象，也不表示事件已经发生或对象可供拍摄；
- 第一人称只能表达当前品牌观点或当前拍摄动作，不能补写操作人的生活经历、刚刚做过的事、
  顾客案例、门店经历或研发过程；
- 品牌观点用“我们认为、希望、主张或建议”等立场表达，不能写成门店已经执行的服务或普遍政策；
  谈门店或服务只能表达希望与主张（如“我们希望店里……”），不得写成“你来店里会看到……”、
  “我们的导购会/不会……”这类现实描述；
- 不得声称品牌的商品线、商品能力或“我们做某类衣服”；边界四没有已确认商品时，只能谈观点与方法；
- 一般颜色、品类和搭配只可作为明确的假设例子被口播讨论，不能被当作现有实物安排出镜；
- 私人协作偏好说明只调整协作方式与表达取舍，成品中不得出现它的原文、转述或对它的解释；
- 可用条件存在多个替代项时，采用能完成内容的最小资源组合。

跨目标重编译时只重组入口、顺序、声画或图文分工和制作方式；不得把旧版说成已经采用或发布。

严格只返回一个 JSON 对象，结构如下（不要返回其他字段或解释）：
{{"speaker_ref": "{boundary.speaker_id}",
 "claims": [{{"claim_id": "c1", "slot": "…", "text": "…", "basis": "…", "actuality": "…", "source_refs": ["…"]}}],
 "spoken_order": ["…"],
 "scene_steps": [{{"step_id": "s1", "purpose": "cover 或 scene", "actor_refs": [], "resource_refs": [],
   "action_text": "…", "sound_text": "…", "production_note": "…", "claim_refs": ["…"]}}]}}
claims 规则：每条是一个可见语义单元；slot 必须恰好覆盖：{slot_lines}。
text 是该单元完整中文内容；basis 四选一：brand_viewpoint（品牌立场）、user_premise（用户话题或前提）、
confirmed_fact（已确认事实）、conditional_guidance（条件性建议或方法）；actuality 三选一：
non_event（观点、性质或状态，不主张发生过）、hypothetical（假设、例子）、user_presented_actual
（仅限第二类中用户明确提供的真实情况）。
source_refs 非空，只能引用可引用来源列表中的 id，且至少一个来源要与 basis 匹配：
brand_viewpoint ↔ source:brand_baseline / source:role_boundary / source:organization；
confirmed_fact ↔ source:organization / source:product:…；
user_premise ↔ source:user_request / source:user_actuality / source:prior_version；
conditional_guidance ↔ source:method:… / source:brand_baseline / source:role_boundary。
共享不变量：凡声称现实品牌、账号、组织或人物曾经、反复或长期发生过询问、讨论、观察、经历、
服务、执行或改变，必须使用 user_premise 且引用 source:user_actuality，或 confirmed_fact 且引用
已确认来源；没有这类来源时，保留观点本身，删除经历外壳，或改写为问题、假设或条件表达。
brand_viewpoint 与 conditional_guidance 只承载当前立场、希望、主张和建议。该不变量同样约束
sound_text、production_note 中引述的口播词句。
text、action_text、sound_text、production_note 中不得出现单元编号（如 c1、s2）或任何 id 标记；
不得使用未登记的品牌 logo、贴纸、已有照片或成品图形素材；现场手写字卡与屏幕文字可用。
spoken_order 把全部 slot=spoken 的 claim_id 按口播顺序排列，各出现一次。
scene_steps 规则：purpose=cover 恰好 1 条（封面/首帧或首图），purpose=scene 至少 1 条（画面步骤/图序）；
actor_refs/resource_refs 只能引用登记表中的 id，需要谁列谁，不需要则留空数组；action_text 为该步可直接
拍摄的画面与动作；sound_text 为该步听到的声音（人声、环境底噪或可选背景音乐），必须写出实际语句或
声音描述，禁止用编号指代台词（错误示例：口播：c8、c9内容），没有额外声音留空字符串；
production_note 为制作提示，可留空；claim_refs 非空，指向该步服务的 claim。
每个字段都必须是字符串或字符串数组，不要嵌套其他对象。"""

    @staticmethod
    def _judgement_prompt(context: BoundaryContext, core: ContentCore) -> str:
        serialized = json.dumps(
            {
                "speaker_ref": core.speaker_ref,
                "claims": [
                    {
                        "id": claim.claim_id,
                        "slot": claim.slot,
                        "text": claim.text,
                        "basis": claim.basis,
                        "actuality": claim.actuality,
                        "source_refs": list(claim.source_refs),
                    }
                    for claim in core.claims
                ],
                "spoken_order": list(core.spoken_order),
                "scene_steps": [
                    {
                        "id": step.step_id,
                        "purpose": step.purpose,
                        "actor_refs": list(step.actor_refs),
                        "resource_refs": list(step.resource_refs),
                        "action_text": step.action_text,
                        "sound_text": step.sound_text,
                        "production_note": step.production_note,
                        "claim_refs": list(step.claim_refs),
                    }
                    for step in core.scene_steps
                ],
            },
            ensure_ascii=False,
        )
        unit_ids = ", ".join(core.unit_ids)
        return f"""只依据以下六类临时边界，对候选底稿的每个单元独立完成完整判定。
边界未明确提供的事实或资源一律视为不存在，不能用常识、常见拍法或话题里出现的对象补足。

{DeepSeekGenerator._boundary_sections(context)}

候选底稿 ContentCore：
{serialized}

对下面列出的每一个 id 各返回一条完整判定，四项都必须给出 true/false：
- identity_ok：为 false 当该单元让账号或当前创作者以第一人称、表演或叙事位置冒充边界外的自然人或岗位
  （妈妈、家长、孩子的照护者、店长、店员、顾客、研发人员等）。用户只是在话题中提到某类人，
  不构成账号具备该身份。当前创作者以拍摄者、口播者或账号运营身份自称（如“我是品牌账号运营”、
  “这里是品牌官方账号”）不属于冒充。
- actuality_ok：为 false 当该单元把观点、假设、话题对象或未知情况写成操作人亲历、真实案例、已经发生的
  动作/场景、门店已执行做法或普遍政策；或把品牌“认为、希望、主张、建议”写成已经发生或正在执行；
  或出现“我们见过、我们观察到、有位顾客、很多家庭”等边界二、四未提供的经历与观察；
  或在没有边界二（用户明确前提）或边界四（已确认事实）来源支撑时，声称现实品牌、账号、组织或人物
  曾经、反复或长期发生过询问、讨论、观察、经历、服务、执行或改变——无论该表述出现在 text、
  sound_text、production_note 还是其中引述的口播词句里。品牌观点只能承载当前立场、希望、主张和建议。
- resource_ok：为 false 当该单元的画面、动作、声音或制作步骤实际需要边界六未登记的人物、商品、衣物、
  图片、合照、场地、家具、道具或既有素材；叠加品牌 logo、贴纸、成品图形或已有照片同样属于使用
  未登记素材。话题对象可以被口播抽象讨论，但不能出镜、行动、发声或被当作现有素材。
- fact_ok：为 false 当该单元与边界三、四中的品牌、商品、资料或明确作用域冲突，或提出了边界外的具体
  商品事实、价格、参数；边界四没有相应已确认商品时，声称品牌的商品线、商品能力或“我们做某类
  衣服”同样为 false。
不要误杀：依据品牌基线表达的观点与条件性建议、明确标注的假设与比喻、普通视觉标题、当前创作者对手机
口播、现有场地中的中性动作，以及对“本次话题/请求”的忠实抽象讨论，这些应当四项均为 true。
关键区别是“谈论某个对象”不需要该资源；“让该对象出镜、行动、发声或把事件写成已经发生”需要当前依据。
对每个单元只依据其自身文本与上述边界独立判定；不要因为其他单元存在问题而改变对本单元的判定。

待判定 id：{unit_ids}
只返回：{{"verdicts":[{{"id":"…","identity_ok":true,"actuality_ok":true,"resource_ok":true,"fact_ok":true}}]}}。
verdicts 必须恰好覆盖上面列出的每个 id，一次且仅一次；不得返回解释、理由、置信度或其他字段。"""

    @staticmethod
    def _unit_repair_prompt(
        request: GenerationInput,
        context: BoundaryContext,
        core: ContentCore,
        issues: tuple[UnitIssue, ...],
    ) -> str:
        step_by_id = {step.step_id: step for step in core.scene_steps}
        reasons_by_unit: dict[str, list[str]] = {}
        for issue in issues:
            reasons_by_unit.setdefault(issue.unit_id, []).append(issue.reason_code)
        lines: list[str] = []
        for unit_id, reasons in reasons_by_unit.items():
            if unit_id in step_by_id:
                step = step_by_id[unit_id]
                original = json.dumps(
                    {
                        "step_id": step.step_id,
                        "purpose": step.purpose,
                        "actor_refs": list(step.actor_refs),
                        "resource_refs": list(step.resource_refs),
                        "action_text": step.action_text,
                        "sound_text": step.sound_text,
                        "production_note": step.production_note,
                        "claim_refs": list(step.claim_refs),
                    },
                    ensure_ascii=False,
                )
            else:
                claim = core.claim(unit_id)
                original = json.dumps(
                    {
                        "claim_id": claim.claim_id,
                        "slot": claim.slot,
                        "text": claim.text,
                        "basis": claim.basis,
                        "actuality": claim.actuality,
                        "source_refs": list(claim.source_refs),
                    },
                    ensure_ascii=False,
                )
            lines.append(f"- {unit_id} | 问题：{'、'.join(sorted(set(reasons)))} | 原文：{original}")
        issue_text = "\n".join(lines)
        return f"""只修复下列单元；不得返回任何未列出的单元，服务端会保留其余合格单元并重新完整复核。
不要删除整篇的主要价值，也不要用固定安全文案代替成品。

{DeepSeekGenerator._boundary_sections(context)}

待修单元与问题：
{issue_text}

问题含义：untrusted_role = 冒充边界外身份；invented_actuality = 把观点、假设或话题写成已发生的经历、
案例或门店已执行做法；unsupported_resource = 使用了未登记的人物、商品、图片、场地、家具或素材；
factual_conflict = 与已确认品牌、商品、资料或作用域冲突，或引用了不允许的来源；media_contract =
必须真实缩短口播以适配用户指定时长，不能只改时长标签。
修复要求：保留原话题价值；身份或现实主张越界时改成品牌明确标示的观点、建议或条件性判断；
制作资源越界时改用登记表中的创作者、手机、现场手写字卡和场地内中性动作；话题人物、商品、图片和
道具只可被抽象谈论，不能出镜或当作已持有素材。修复后的 claim 需要给出正确的 basis、actuality 和
source_refs（至少一个来源与 basis 匹配：brand_viewpoint ↔ brand_baseline/role_boundary/organization；
confirmed_fact ↔ organization/product；user_premise ↔ user_request/user_actuality/prior_version；
conditional_guidance ↔ method/brand_baseline/role_boundary）；修复后的 scene step 需要给出正确的
actor_refs、resource_refs 和 claim_refs。可见文字中不得出现单元编号或 id 标记；若问题片段是
c1、s2 这类编号，必须把编号替换为对应台词原文或删去，不得在任何字段保留编号。
若问题单元是没有用户明确前提或已确认事实来源、却声称现实品牌/账号/组织/人物曾经、反复或长期
发生过询问、讨论、观察、经历、服务、执行或改变的表述：保留观点本身，删除经历外壳，或改写为
问题、假设或条件表达；不得为其编造来源。
不要输出分类、证据、审查过程或解释。
严格只返回一个 JSON 对象：{{"repairs":[…]}}。repairs 中每个元素是完整替换单元：claim 用
{{"claim_id":"…","text":"…","basis":"…","actuality":"…","source_refs":["…"]}}；scene step 用
{{"step_id":"…","action_text":"…","sound_text":"…","production_note":"…","actor_refs":[],
"resource_refs":[],"claim_refs":["…"]}}。repairs 必须恰好覆盖：{", ".join(reasons_by_unit)}。"""

    # ------------------------------------------------------------------
    # Natural-language rendering of confirmed product facts
    # ------------------------------------------------------------------

    @staticmethod
    def _natural_product(
        sku: str,
        display_name: str,
        facts: dict[str, object],
    ) -> str:
        category = DeepSeekGenerator._natural_category(facts.get("category"))
        raw_colors = facts.get("colors")
        colors = (
            "、".join(value for value in raw_colors if isinstance(value, str)) if isinstance(raw_colors, list) else ""
        )
        parts = [f"商品 {display_name or sku}（编号 {sku}）"]
        if category != "未提供品类":
            parts.append(f"品类：{category}")
        if colors:
            parts.append(f"颜色：{colors}")
        for key, label in (
            ("material_or_structure", "材质或结构"),
            ("material", "材质"),
            ("structure", "结构"),
            ("silhouette", "轮廓"),
            ("observable_features", "可观察特征"),
        ):
            value = facts.get(key)
            if isinstance(value, str) and value.strip():
                parts.append(f"{label}：{value.strip()}")
        weight = facts.get("sample_weight_m_grams")
        comparison = facts.get("comparison_single_layer_short_coat_m_grams")
        both_sides_complete = facts.get("both_sides_complete")
        if isinstance(both_sides_complete, bool):
            parts.append("两面均为完整外观" if both_sides_complete else "两面完整外观未得到确认")
        functional_pockets = facts.get("pockets_functional_both_sides")
        if isinstance(functional_pockets, bool):
            parts.append(
                "两面口袋均可正常使用"
                if functional_pockets
                else "两面口袋不能确认均可正常使用"
            )
        if isinstance(weight, int):
            parts.append(f"M 码当前样衣为 {weight} 克")
        if isinstance(comparison, int):
            parts.append(f"同季同长度单层短外套 M 码样衣为 {comparison} 克")
        raw_boundary = facts.get("weight_boundary")
        if isinstance(raw_boundary, str) and raw_boundary.strip():
            parts.append(DeepSeekGenerator._weight_boundary(raw_boundary))
        return "；".join(parts)

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
