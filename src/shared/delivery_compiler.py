from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, TypeAlias

from src.shared.creative_kernel import (
    DRAMATIZATION_DISCLOSURE,
    CreativeKernelUnit,
    CreativeKernelV1,
    compiler_owned_unit_source,
    compiler_owned_unit_texts,
)
from src.shared.errors import GenerationFailed
from src.shared.factual_basis import ImmutableFactBlock
from src.shared.types import (
    ContentProduct,
    ContentProductionBundle,
    ContentSemanticContract,
    GraphicProductionBundle,
    P1SemanticContract,
    P2SemanticContract,
    P3SemanticContract,
    P4SemanticContract,
    P5SemanticContract,
    ProductFact,
    VideoProductionBundle,
)

DeliveryMedia: TypeAlias = Literal["video", "graphic"]

DELIVERY_COMPILER_VERSION = "delivery-compiler-v1"
ORIGINAL_COMPOSITION_RESOURCE_ID = "resource:original_composition"
CREATOR_EXPRESSION_RESOURCE_ID = "resource:creator_expression"
_PHRASES: dict[str, str] = {
    "phrase:fact-boundary": "本篇只在已提供事实与当前表达条件内成立。",
    "phrase:account-view": "本篇来自当前账号的观察视角，不构成品牌机构事实或历史主张。",
    "phrase:resource-boundary": "画面只使用本次已登记资源与版本化中性编译形式。",
    "phrase:graphic-hero": "使用原创标题文字卡与留白排版，不调用现实人物、场地或道具。",
    "phrase:graphic-product-hero": "使用已登记商品近景与标题排版，不增加未登记道具。",
    "phrase:graphic-sequence": (
        "第 1 张为标题文字卡；中间页按内核可见顺序排入正文与事实原句；"
        "末页使用发布配文收束。"
    ),
    "phrase:graphic-sequence-four": (
        "只补拍四张：第 1 张为标题文字卡；第 2、3 张按内核可见顺序排入正文与"
        "事实原句；第 4 张使用发布配文收束。"
    ),
    "phrase:graphic-layout": "使用原创文字卡、基础排版和留白；只可加入本次冻结的已登记素材。",
    "phrase:video-cover": "以原创标题文字卡作为封面或首帧，不要求现实场地或道具。",
    "phrase:video-flow": "标题文字卡进入正文旁白或文字卡，按内核顺序展开，再由发布配文自然收束。",
    "phrase:video-action": "用原创文字卡按内核顺序切换，不重演用户现实，也不增加人物、场地或道具。",
    "phrase:video-product-action": "只使用已登记商品近景与原创文字卡按内核顺序切换，不增加人物、场地或道具。",
    "phrase:video-drama": (
        "演绎段使用文字对话卡或创作者一人分段旁白；不表示第二演员或家庭现场存在。"
    ),
    "phrase:video-sound": "不要求环境声；可静音或使用创作者本人旁白，不模拟未登记现场声音。",
    "phrase:video-silent": "无口播、无对白、无解说；完整已审文字由文字卡和字幕承担。",
}


@dataclass(frozen=True)
class DeliveryCompileInput:
    primary_product: ContentProduct
    media_format: DeliveryMedia
    products: tuple[ProductFact, ...]
    production_conditions: str
    allowed_resource_ids: frozenset[str]
    immutable_fact_blocks: tuple[ImmutableFactBlock, ...] = ()


@dataclass(frozen=True)
class CompiledDelivery:
    outline: str
    body: str
    semantic_contract: ContentSemanticContract
    production: ContentProductionBundle
    resource_refs: tuple[str, ...]
    visible_provenance: dict[str, tuple[str, ...]]


def compile_delivery(
    request: DeliveryCompileInput,
    kernel: CreativeKernelV1,
) -> CompiledDelivery:
    compiled = _compile_delivery(request, kernel)
    assert_compiled_delivery(request, kernel, compiled)
    return compiled


def assert_compiled_delivery(
    request: DeliveryCompileInput,
    kernel: CreativeKernelV1,
    compiled: CompiledDelivery,
) -> None:
    _assert_immutable_fact_blocks(request, kernel)
    expected = _compile_delivery(request, kernel)
    if compiled != expected:
        raise GenerationFailed("确定性成品编译结果包含未审文字或结构漂移")
    if any(
        resource not in request.allowed_resource_ids
        for resource in compiled.resource_refs
    ):
        raise GenerationFailed("确定性成品编译使用了未登记资源")
    allowed_sources = {
        *(unit.unit_id for unit in kernel.units),
        *_PHRASES,
        *(
            source
            for unit_id, text in compiler_owned_unit_texts(
                request.primary_product
            ).items()
            if (
                source := compiler_owned_unit_source(
                    unit_id,
                    text,
                )
            )
            is not None
        ),
        "compiler:duration",
        "compiler:visible-body",
    }
    if any(
        source not in allowed_sources
        for sources in compiled.visible_provenance.values()
        for source in sources
    ):
        raise GenerationFailed("确定性成品编译包含未知可见来源")


def _assert_immutable_fact_blocks(
    request: DeliveryCompileInput,
    kernel: CreativeKernelV1,
) -> None:
    block_by_id = {
        block.fact_block_id: block
        for block in request.immutable_fact_blocks
    }
    if any(
        block_id not in block_by_id
        for block_id in kernel.selected_fact_block_ids
    ):
        raise GenerationFailed("确定性成品编译无法解析商品事实块")
    selected = tuple(
        block_by_id[block_id]
        for block_id in kernel.selected_fact_block_ids
    )
    unit_by_fact_id = {
        unit.fact_refs[0]: unit
        for unit in kernel.units
        if unit.purpose == "frozen_fact"
        and len(unit.fact_refs) == 1
    }
    for block in selected:
        unit = unit_by_fact_id.get(block.fact_id)
        if unit is None or unit.text != block.canonical_text:
            raise GenerationFailed("确定性成品编译发现商品事实块漂移")
    selected_fact_ids = {block.fact_id for block in selected}
    available_fact_ids = {
        block.fact_id for block in request.immutable_fact_blocks
    }
    visible_product_fact_ids = {
        unit.fact_refs[0]
        for unit in kernel.units
        if unit.purpose == "frozen_fact"
        and len(unit.fact_refs) == 1
        and unit.fact_refs[0] in available_fact_ids
    }
    if visible_product_fact_ids != selected_fact_ids:
        raise GenerationFailed("确定性成品编译商品事实块覆盖漂移")


def _compile_delivery(
    request: DeliveryCompileInput,
    kernel: CreativeKernelV1,
) -> CompiledDelivery:
    singleton_by_purpose = {
        unit.purpose: unit
        for unit in kernel.units
        if unit.purpose in {"title", "natural_guide", "release_caption"}
    }
    body_units = tuple(
        unit for unit in kernel.units if unit.purpose == "body"
    )
    required = {"title", "natural_guide", "release_caption"}
    if set(singleton_by_purpose) != required or not body_units:
        raise GenerationFailed("创作内核缺少完整可见单元")
    if any(
        sum(unit.purpose == purpose for unit in kernel.units) != 1
        for purpose in required
    ):
        raise GenerationFailed("创作内核单值可见单元重复")
    title = singleton_by_purpose["title"].text
    expected_compiler_texts = compiler_owned_unit_texts(
        request.primary_product
    )
    guide = expected_compiler_texts["unit:natural-guide"]
    release = expected_compiler_texts["unit:release-caption"]
    guide_source = compiler_owned_unit_source(
        "unit:natural-guide",
        guide,
    )
    release_source = compiler_owned_unit_source(
        "unit:release-caption",
        release,
    )
    if guide_source is None or release_source is None:
        raise GenerationFailed("确定性成品编译中性字段来源无效")
    fact_units = tuple(
        unit for unit in kernel.units if unit.purpose == "frozen_fact"
    )
    creative_body = "\n\n".join(unit.text for unit in body_units)
    spoken_parts = tuple(
        unit
        for unit in kernel.units
        if unit.purpose in {"frozen_fact", "body"}
    )
    spoken = "\n\n".join(unit.text for unit in spoken_parts)
    contract = _contract(
        request.primary_product,
        guide,
        creative_body,
        release,
        fact_units,
    )
    product_resources = tuple(
        f"resource:product:{product.sku}"
        for product in request.products
        if f"resource:product:{product.sku}"
        in request.allowed_resource_ids
    )
    base_resources = (ORIGINAL_COMPOSITION_RESOURCE_ID,)
    if ORIGINAL_COMPOSITION_RESOURCE_ID not in request.allowed_resource_ids:
        raise GenerationFailed("确定性成品编译缺少原创文字卡资源")
    resource_refs = tuple(
        dict.fromkeys(
            (
                *base_resources,
                *(
                    product_resources
                    if request.primary_product
                    in {"product_truth", "visual_styling_story"}
                    else ()
                ),
            )
        )
    )
    spoken_sources = tuple(unit.unit_id for unit in spoken_parts)
    provenance: dict[str, tuple[str, ...]] = {
        "outline": (singleton_by_purpose["title"].unit_id,),
        "natural_guide": (guide_source,),
        "release_caption_and_interaction": (release_source,),
    }
    production: ContentProductionBundle
    if request.media_format == "graphic":
        hero_id = (
            "phrase:graphic-product-hero"
            if product_resources
            else "phrase:graphic-hero"
        )
        sequence_id = (
            "phrase:graphic-sequence-four"
            if "四张" in request.production_conditions
            else "phrase:graphic-sequence"
        )
        production = GraphicProductionBundle(
            natural_guide=guide,
            hero_image=_PHRASES[hero_id],
            image_sequence=_PHRASES[sequence_id],
            full_body=spoken,
            layout_and_production=_PHRASES["phrase:graphic-layout"],
            release_caption_and_interaction=release,
        )
        provenance.update(
            {
                "hero_image": (hero_id,),
                "image_sequence": (sequence_id, *spoken_sources),
                "full_body": spoken_sources,
                "layout_and_production": ("phrase:graphic-layout",),
            }
        )
    else:
        silent = all(
            marker in request.production_conditions
            for marker in ("无口播", "无对白", "无解说")
        )
        action_phrase = (
            "phrase:video-drama"
            if any(
                unit.text.startswith(DRAMATIZATION_DISCLOSURE)
                for unit in body_units
            )
            else (
                "phrase:video-product-action"
                if product_resources
                else "phrase:video-action"
            )
        )
        if (
            not silent
            and CREATOR_EXPRESSION_RESOURCE_ID
            in request.allowed_resource_ids
        ):
            resource_refs = tuple(
                dict.fromkeys((*resource_refs, CREATOR_EXPRESSION_RESOURCE_ID))
            )
        duration = _duration(spoken, request.production_conditions)
        production = VideoProductionBundle(
            natural_guide=guide,
            spoken_lines=(
                _PHRASES["phrase:video-silent"] if silent else spoken
            ),
            visual_actions=_PHRASES[action_phrase],
            subtitles=spoken,
            sound_and_production=_PHRASES["phrase:video-sound"],
            cover_or_first_frame=_PHRASES["phrase:video-cover"],
            viewing_flow=_PHRASES["phrase:video-flow"],
            natural_duration=duration,
            release_caption_and_interaction=release,
        )
        provenance.update(
            {
                "cover_or_first_frame": ("phrase:video-cover",),
                "viewing_flow": ("phrase:video-flow", *spoken_sources),
                "spoken_lines": spoken_sources,
                "visual_actions": (action_phrase,),
                "subtitles": spoken_sources,
                "sound_and_production": ("phrase:video-sound",),
                "natural_duration": ("compiler:duration",),
            }
        )
        if silent:
            provenance["spoken_lines"] = ("phrase:video-silent",)
    body = _visible_body(title, production)
    provenance["body"] = (
        "compiler:visible-body",
        *tuple(
            source
            for sources in provenance.values()
            for source in sources
        ),
    )
    return CompiledDelivery(
        outline=title,
        body=body,
        semantic_contract=contract,
        production=production,
        resource_refs=resource_refs,
        visible_provenance=provenance,
    )


def _contract(
    product: ContentProduct,
    guide: str,
    body: str,
    release: str,
    facts: tuple[CreativeKernelUnit, ...],
) -> ContentSemanticContract:
    fact_text = "\n".join(
        unit.text for unit in facts
    ) or _PHRASES["phrase:fact-boundary"]
    if product == "dressing_decision":
        return P1SemanticContract(body, _PHRASES["phrase:fact-boundary"], release)
    if product == "product_truth":
        return P2SemanticContract(fact_text, body, _PHRASES["phrase:fact-boundary"])
    if product == "brand_life_narrative":
        return P3SemanticContract(
            body,
            release,
            _PHRASES["phrase:account-view"],
        )
    if product == "local_response":
        return P4SemanticContract(guide, body, release)
    return P5SemanticContract(
        fact_text,
        body,
        _PHRASES["phrase:resource-boundary"],
    )


def _duration(spoken: str, production_conditions: str) -> str:
    if "8 秒" in production_conditions:
        return "8 秒窄主题版：只保留仍能独立成立的一项命题，不称与原完整版本等义。"
    return f"约 {max(8, math.ceil(len(spoken) / 4.2))} 秒"


def _visible_body(
    title: str,
    production: ContentProductionBundle,
) -> str:
    if isinstance(production, VideoProductionBundle):
        sections: tuple[tuple[str, str], ...] = (
            ("内容概要", production.natural_guide),
            ("封面/首帧", production.cover_or_first_frame),
            ("完整观看链", production.viewing_flow),
            ("完整台词/解说", production.spoken_lines),
            ("画面与动作", production.visual_actions),
            ("字幕", production.subtitles),
            ("声音与制作提示", production.sound_and_production),
            ("自然时长", production.natural_duration),
            ("发布配文与互动", production.release_caption_and_interaction),
        )
    else:
        sections = (
            ("内容概要", production.natural_guide),
            ("首图方案", production.hero_image),
            ("图序与每张职责", production.image_sequence),
            ("完整发布正文", production.full_body),
            ("拍摄/排版提示", production.layout_and_production),
            ("发布配文与互动", production.release_caption_and_interaction),
        )
    return "标题：" + title + "\n\n" + "\n\n".join(
        f"{heading}：{value}" for heading, value in sections
    )
