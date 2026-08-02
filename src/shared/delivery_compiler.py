from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, TypeAlias

from src.shared.creative_kernel import (
    DRAMATIZATION_DISCLOSURE,
    DUAL_TRACK_KERNEL_VERSION,
    HYPOTHESIS_DISCLOSURE,
    KERNEL_VERSION,
    MEDIA_NATIVE_KERNEL_VERSION,
    PRODUCT_VALUE_UNIT_ID,
    CreativeKernelUnit,
    CreativeKernelV1,
    UnitMode,
    compiler_owned_unit_source,
    compiler_owned_unit_texts,
)
from src.shared.errors import GenerationFailed
from src.shared.factual_basis import ImmutableFactBlock
from src.shared.media_program import (
    MediaCapabilityEnvelope,
    MediaProgramSelectionV1,
    assert_media_program_allowed,
    media_envelope_digest,
    media_program_digest,
)
from src.shared.product_value import (
    P2ProductValueContractV1,
    P5ProductValueContractV1,
    ProductValueContract,
)
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
from src.shared.visible_structure import v3_compiler_visible_heading

DeliveryMedia: TypeAlias = Literal["video", "graphic"]

LEGACY_DELIVERY_COMPILER_VERSION = "delivery-compiler-v1"
DUAL_TRACK_DELIVERY_COMPILER_VERSION = "delivery-compiler-v2"
MEDIA_NATIVE_DELIVERY_COMPILER_VERSION = "delivery-compiler-v3"
DELIVERY_COMPILER_VERSION = "delivery-compiler-v4"
SUPPORTED_DELIVERY_COMPILER_VERSIONS = frozenset(
    {
        LEGACY_DELIVERY_COMPILER_VERSION,
        DUAL_TRACK_DELIVERY_COMPILER_VERSION,
        MEDIA_NATIVE_DELIVERY_COMPILER_VERSION,
        DELIVERY_COMPILER_VERSION,
    }
)
ORIGINAL_COMPOSITION_RESOURCE_ID = "resource:original_composition"
CREATOR_EXPRESSION_RESOURCE_ID = "resource:creator_expression"
_PHRASES: dict[str, str] = {
    "phrase:fact-boundary": "本篇只在已提供事实与当前表达条件内成立。",
    "phrase:account-view": "本篇来自当前账号的观察视角，不构成品牌机构事实或历史主张。",
    "phrase:resource-boundary": "画面只使用本次已登记资源与版本化中性编译形式。",
    "phrase:graphic-hero": "使用原创标题文字卡与留白排版，不调用现实人物、场地或道具。",
    "phrase:graphic-product-hero": "使用已登记商品近景与标题排版，不增加未登记道具。",
    "phrase:graphic-sequence": (
        "第 1 张为保留表达范围的标题文字卡；中间页按冻结顺序排入已标识的创作表达与事实原句；末页使用发布配文收束。"
    ),
    "phrase:graphic-sequence-four": (
        "只补拍四张：第 1 张为保留表达范围的标题文字卡；第 2、3 张按冻结顺序"
        "排入已标识的创作表达与事实原句；第 4 张使用发布配文收束。"
    ),
    "phrase:graphic-layout": "使用原创文字卡、基础排版和留白；只可加入本次冻结的已登记素材。",
    "phrase:video-cover": "以保留表达范围的原创标题文字卡作为封面或首帧，不要求现实场地或道具。",
    "phrase:video-flow": "标题文字卡进入已标识的正文旁白或文字卡，按冻结顺序展开，再由发布配文自然收束。",
    "phrase:video-action": "用原创文字卡按冻结顺序切换，不重演用户现实，也不增加人物、场地或道具。",
    "phrase:video-product-action": "只使用已登记商品近景与原创文字卡按冻结顺序切换，不增加人物、场地或道具。",
    "phrase:video-drama": ("演绎段使用文字对话卡或创作者一人分段旁白；不表示第二演员或家庭现场存在。"),
    "phrase:video-sound": "不要求环境声；可静音或使用创作者本人旁白，不模拟未登记现场声音。",
    "phrase:video-silent": "无口播、无对白、无解说；完整已审文字由文字卡和字幕承担。",
    "phrase:scope-user-fact": "你提到：",
    "phrase:scope-brand-fact": "",
    "phrase:scope-product-fact": "已确认的商品信息：",
    "phrase:scope-general": "下面是创作性的生活观察，不对应真实人物或经历：",
    "phrase:scope-recommendation": "不妨试试：",
    "phrase:scope-hypothesis": HYPOTHESIS_DISCLOSURE,
    "phrase:scope-dramatization": DRAMATIZATION_DISCLOSURE,
    "phrase:title-general": "一种生活观察：",
    "phrase:title-user-fact": "从你提供的片段出发：",
    "phrase:title-confirmed-fact": "从已确认的信息出发：",
    "phrase:title-hypothesis": "假设一下：",
    "phrase:title-dramatization": "情景演绎：",
    "phrase:artifact-general": "以下是围绕这个主题的创作表达，不对应真实人物或经历。",
    "phrase:artifact-user-fact": ("以下内容保留你提供的真实片段；其余为创作性观察，不补充现实细节。"),
    "phrase:artifact-confirmed-fact": ("以下只引用已确认的信息；其余为一般观察，不增加新的现实主张。"),
    "phrase:artifact-recommendation": "以下是可选择的创作建议，不表示已经执行。",
    "phrase:artifact-user-fact-recommendation": ("以下内容保留你提供的真实片段；其余为可选择建议，不表示已经执行。"),
    "phrase:artifact-confirmed-fact-recommendation": (
        "以下只引用已确认的信息；其余为可选择建议，不新增商品或现实事实。"
    ),
    "phrase:artifact-hypothesis": "下面的片段是假设，不代表真实发生。",
    "phrase:artifact-user-fact-hypothesis": ("以下保留你提供的真实片段；其余是创作性推演，不作为这段经历的事实补充。"),
    "phrase:artifact-dramatization": "以下内容包含情景演绎，不对应真实人物或经历。",
    "phrase:artifact-user-fact-drama": ("以下内容保留你提供的真实片段；小剧场为情景演绎，不对应现实经历。"),
}


@dataclass(frozen=True)
class DeliveryCompileInput:
    primary_product: ContentProduct
    media_format: DeliveryMedia
    products: tuple[ProductFact, ...]
    production_conditions: str
    allowed_resource_ids: frozenset[str]
    immutable_fact_blocks: tuple[ImmutableFactBlock, ...] = ()
    trusted_fact_texts: tuple[tuple[str, str], ...] = ()
    media_capability_envelope: MediaCapabilityEnvelope | None = None
    media_program: MediaProgramSelectionV1 | None = None
    product_value_contract: ProductValueContract | None = None


@dataclass(frozen=True)
class CompiledDelivery:
    outline: str
    body: str
    semantic_contract: ContentSemanticContract
    production: ContentProductionBundle
    resource_refs: tuple[str, ...]
    visible_provenance: dict[str, tuple[str, ...]]


def compiler_owned_media_unit_texts(
    request: DeliveryCompileInput,
) -> dict[str, str]:
    """Return an explicit restricted fallback media plan.

    This compatibility helper is not part of the creative-kernel-v3 production
    path.  A caller that deliberately cannot run Writer may use the text as an
    honestly constrained fallback, but v3 parsing rejects it as compiler-owned
    copy.  A seed or trusted fact is not permission to invent a photograph,
    location or prop.
    """

    product_resources = tuple(
        resource_id for resource_id in request.allowed_resource_ids if resource_id.startswith("resource:product:")
    )
    if request.media_format == "graphic":
        if product_resources:
            sequence = (
                "只补拍四张：第 1 张让本次已登记样衣完整进入画面；第 2、3 张保持同一背景与机位呈现每件样衣；"
                "第 4 张呈现它们的并置关系。事实原句由服务端独立排入图序。"
                if "四张" in request.production_conditions
                else (
                    "先拍每件已登记样衣的完整轮廓，再保持同一背景与机位呈现它们的"
                    "并置关系；事实原句由服务端独立排入图序，末张回到本篇选择。"
                )
            )
            return {
                "unit:media-opening": ("首图让本次已登记商品样衣完整进入画面，背景和标题不遮挡主体。"),
                "unit:media-sequence": sequence,
                "unit:production-note": (
                    "只使用本次登记的商品样衣、创作者、手机和普通室内条件；不补入未登记人物、地点、道具或商品属性。"
                ),
            }
        return {
            "unit:media-opening": ("首图使用本篇标题、抽象色块和线条构图，不调用现实照片或未登记对象。"),
            "unit:media-sequence": (
                "第 1 张呈现标题与观看回报；中间页分别承接服务端插入的事实原句和核心表达；末张保留发布配文。"
            ),
            "unit:production-note": (
                "只使用原创字体排版、色块、线条、符号和留白；不添加现实人物、场地、道具、商品或外部素材。"
            ),
        }
    if product_resources:
        opening = "开头两秒让本次已登记商品样衣完整进入同一画面，创作者只说本篇标题。"
        sequence = (
            "保持同一机位和背景，先给每件已登记样衣一个完整镜头，再呈现它们的"
            "并置关系；事实原句由服务端独立进入字幕，最后回到可执行选择。"
        )
        production = "只使用本次登记的商品样衣、创作者、手机和普通室内条件；不增加演员、地点、道具或商品属性。"
    else:
        opening = (
            "开头由创作者本人直接说出标题；不重演用户经历，也不调用未登记场景或道具。"
            if CREATOR_EXPRESSION_RESOURCE_ID in request.allowed_resource_ids
            else "开头使用原创标题字与抽象图形，不调用现实人物、场地或道具。"
        )
        sequence = "先给出观看回报，再由创作者本人或原创文字画面承接事实原句与核心表达，最后自然收束；不重演现实经过。"
        production = "只使用创作者本人、原创排版与已登记声音条件完成；不增加演员、地点、商品、道具或外部素材。"
    return {
        "unit:media-opening": opening,
        "unit:media-sequence": sequence,
        "unit:subtitle-strategy": ("字幕只保留标题、事实原句和关键转折，不机械复制整段台词。"),
        "unit:production-note": production,
    }


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
    _assert_expression_plan(request, kernel)
    expected = _compile_delivery(request, kernel)
    if compiled != expected:
        raise GenerationFailed("确定性成品编译结果包含未审文字或结构漂移")
    if any(resource not in request.allowed_resource_ids for resource in compiled.resource_refs):
        raise GenerationFailed("确定性成品编译使用了未登记资源")
    allowed_sources = {
        *(unit.unit_id for unit in kernel.units),
        *_PHRASES,
        *(
            source
            for unit_id, text in compiler_owned_unit_texts(request.primary_product).items()
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
        *(
            (
                f"media-envelope:{media_envelope_digest(request.media_capability_envelope)}",
                f"media-program:{media_program_digest(request.media_program)}",
                    f"media-program:{request.media_program.program_id}",
                    *(f"media-resource:{resource_id}" for resource_id in request.media_program.required_resource_ids),
                    *(
                        (
                            "media-role:primary:"
                            f"{request.media_program.primary_resource_id}",
                            "media-role:secondary:"
                            f"{request.media_program.secondary_resource_id}",
                        )
                        if request.media_program.primary_resource_id
                        and request.media_program.secondary_resource_id
                        else ()
                    ),
                *(
                    (f"compiler:optional-capture-suggestion:{request.media_program.optional_capture_suggestion_id}",)
                    if request.media_program.optional_capture_suggestion_id
                    else ()
                ),
            )
            if request.media_capability_envelope is not None and request.media_program is not None
            else ()
        ),
    }
    if any(source not in allowed_sources for sources in compiled.visible_provenance.values() for source in sources):
        raise GenerationFailed("确定性成品编译包含未知可见来源")


def _assert_immutable_fact_blocks(
    request: DeliveryCompileInput,
    kernel: CreativeKernelV1,
) -> None:
    block_by_id = {block.fact_block_id: block for block in request.immutable_fact_blocks}
    if any(block_id not in block_by_id for block_id in kernel.selected_fact_block_ids):
        raise GenerationFailed("确定性成品编译无法解析商品事实块")
    selected = tuple(block_by_id[block_id] for block_id in kernel.selected_fact_block_ids)
    unit_by_fact_id = {
        unit.fact_refs[0]: unit for unit in kernel.units if unit.purpose == "frozen_fact" and len(unit.fact_refs) == 1
    }
    for block in selected:
        unit = unit_by_fact_id.get(block.fact_id)
        if unit is None or unit.text != block.canonical_text:
            raise GenerationFailed("确定性成品编译发现商品事实块漂移")
    selected_fact_ids = {block.fact_id for block in selected}
    available_fact_ids = {block.fact_id for block in request.immutable_fact_blocks}
    visible_product_fact_ids = {
        unit.fact_refs[0]
        for unit in kernel.units
        if unit.purpose == "frozen_fact" and len(unit.fact_refs) == 1 and unit.fact_refs[0] in available_fact_ids
    }
    if visible_product_fact_ids != selected_fact_ids:
        raise GenerationFailed("确定性成品编译商品事实块覆盖漂移")


def _assert_expression_plan(
    request: DeliveryCompileInput,
    kernel: CreativeKernelV1,
) -> None:
    unit_ids = [unit.unit_id for unit in kernel.units]
    orders = [unit.visible_order for unit in kernel.units]
    if len(unit_ids) != len(set(unit_ids)) or len(orders) != len(set(orders)) or orders != sorted(orders):
        raise GenerationFailed("确定性成品编译发现表达计划标识或顺序漂移")
    fact_text_by_id = dict(request.trusted_fact_texts)
    if len(fact_text_by_id) != len(request.trusted_fact_texts):
        raise GenerationFailed("可信事实轨来源重复")
    for unit in kernel.units:
        if unit.track == "trusted_fact":
            if (
                unit.purpose != "frozen_fact"
                or unit.mode != "trusted_fact"
                or len(unit.fact_refs) != 1
                or unit.constraint_refs
                or unit.allowed_resource_ids
                or fact_text_by_id.get(unit.fact_refs[0]) != unit.text
                or unit.text_source != "server_fact"
            ):
                raise GenerationFailed("可信事实轨结构漂移")
            continue
        if (
            unit.track != "creative_expression"
            or unit.purpose == "frozen_fact"
            or unit.fact_refs
            or not unit.scope_id
            or any(resource_id not in request.allowed_resource_ids for resource_id in unit.allowed_resource_ids)
        ):
            raise GenerationFailed("创作表达轨结构漂移")
        if kernel.kernel_version == DUAL_TRACK_KERNEL_VERSION:
            if unit.purpose in {"natural_guide", "release_caption"}:
                if unit.text_source != "server_compiler":
                    raise GenerationFailed("编译器中性文字来源漂移")
            elif unit.text_source not in {"writer", "prior_version"}:
                raise GenerationFailed("创作表达文字来源漂移")
        elif unit.unit_id == PRODUCT_VALUE_UNIT_ID:
            if (
                request.product_value_contract is None
                or unit.text_source != "server_compiler"
                or unit.purpose != "body"
                or unit.mode != "recommendation"
                or unit.text != request.product_value_contract.visible_text
            ):
                raise GenerationFailed("商品价值合同可见单元漂移")
        elif unit.text_source not in {"writer", "prior_version"}:
            raise GenerationFailed("创作表达文字来源漂移")
        if kernel.kernel_version == KERNEL_VERSION and unit.allowed_resource_ids:
            raise GenerationFailed("Writer 创作单元不得绑定媒体资源")
        if unit.mode not in {
            "general_observation",
            "recommendation",
            "hypothesis",
            "disclosed_dramatization",
        }:
            raise GenerationFailed("创作表达轨语态无效")
    value_units = tuple(
        unit for unit in kernel.units if unit.unit_id == PRODUCT_VALUE_UNIT_ID
    )
    if request.product_value_contract is None:
        if value_units:
            raise GenerationFailed("无商品价值合同的成品包含商品价值单元")
    elif (
        len(value_units) != 1
        or request.product_value_contract.primary_product
        != request.primary_product
    ):
        raise GenerationFailed("商品价值合同与成品产品不一致")


def _compile_delivery(
    request: DeliveryCompileInput,
    kernel: CreativeKernelV1,
) -> CompiledDelivery:
    if kernel.kernel_version == KERNEL_VERSION:
        return _compile_delivery_v4(request, kernel)
    if kernel.kernel_version == MEDIA_NATIVE_KERNEL_VERSION:
        return _compile_delivery_v3(request, kernel)
    return _compile_delivery_v2(request, kernel)


def _compile_delivery_v2(
    request: DeliveryCompileInput,
    kernel: CreativeKernelV1,
) -> CompiledDelivery:
    singleton_by_purpose = {
        unit.purpose: unit for unit in kernel.units if unit.purpose in {"title", "natural_guide", "release_caption"}
    }
    body_units = tuple(unit for unit in kernel.units if unit.purpose == "body")
    required = {"title", "natural_guide", "release_caption"}
    if set(singleton_by_purpose) != required or not body_units:
        raise GenerationFailed("创作内核缺少完整可见单元")
    if any(sum(unit.purpose == purpose for unit in kernel.units) != 1 for purpose in required):
        raise GenerationFailed("创作内核单值可见单元重复")
    title, title_scope_source = _scoped_title(
        singleton_by_purpose["title"].text,
        kernel,
    )
    expected_compiler_texts = compiler_owned_unit_texts(request.primary_product)
    raw_guide = expected_compiler_texts["unit:natural-guide"]
    raw_release = expected_compiler_texts["unit:release-caption"]
    guide, artifact_scope_source = _scoped_compiler_text(raw_guide, kernel)
    release, release_scope_source = _scoped_compiler_text(raw_release, kernel)
    guide_source = compiler_owned_unit_source(
        "unit:natural-guide",
        raw_guide,
    )
    release_source = compiler_owned_unit_source(
        "unit:release-caption",
        raw_release,
    )
    if guide_source is None or release_source is None:
        raise GenerationFailed("确定性成品编译中性字段来源无效")
    fact_units = tuple(unit for unit in kernel.units if unit.purpose == "frozen_fact")
    creative_body = "\n\n".join(_visible_unit(unit) for unit in body_units)
    spoken_parts = tuple(unit for unit in kernel.units if unit.purpose in {"frozen_fact", "body"})
    spoken = "\n\n".join(_visible_unit(unit) for unit in spoken_parts)
    contract = _contract(
        request.primary_product,
        guide,
        creative_body,
        release,
        fact_units,
        media_native=False,
    )
    product_resources = tuple(
        f"resource:product:{product.sku}"
        for product in request.products
        if f"resource:product:{product.sku}" in request.allowed_resource_ids
    )
    base_resources = (ORIGINAL_COMPOSITION_RESOURCE_ID,)
    if ORIGINAL_COMPOSITION_RESOURCE_ID not in request.allowed_resource_ids:
        raise GenerationFailed("确定性成品编译缺少原创文字卡资源")
    resource_refs = tuple(
        dict.fromkeys(
            (
                *base_resources,
                *(product_resources if request.primary_product in {"product_truth", "visual_styling_story"} else ()),
            )
        )
    )
    spoken_sources = tuple(
        source for unit in spoken_parts for source in (unit.unit_id, _visible_unit_scope_source(unit))
    )
    provenance: dict[str, tuple[str, ...]] = {
        "outline": (singleton_by_purpose["title"].unit_id, title_scope_source),
        "natural_guide": (guide_source, artifact_scope_source),
        "release_caption_and_interaction": (release_source, release_scope_source),
    }
    production: ContentProductionBundle
    if request.media_format == "graphic":
        hero_id = "phrase:graphic-product-hero" if product_resources else "phrase:graphic-hero"
        sequence_id = (
            "phrase:graphic-sequence-four" if "四张" in request.production_conditions else "phrase:graphic-sequence"
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
        silent = all(marker in request.production_conditions for marker in ("无口播", "无对白", "无解说"))
        action_phrase = (
            "phrase:video-drama"
            if any(unit.mode == "disclosed_dramatization" for unit in body_units)
            else ("phrase:video-product-action" if product_resources else "phrase:video-action")
        )
        if not silent and CREATOR_EXPRESSION_RESOURCE_ID in request.allowed_resource_ids:
            resource_refs = tuple(dict.fromkeys((*resource_refs, CREATOR_EXPRESSION_RESOURCE_ID)))
        duration = _duration(spoken, request.production_conditions)
        production = VideoProductionBundle(
            natural_guide=guide,
            spoken_lines=(_PHRASES["phrase:video-silent"] if silent else spoken),
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
        *tuple(source for sources in provenance.values() for source in sources),
    )
    return CompiledDelivery(
        outline=title,
        body=body,
        semantic_contract=contract,
        production=production,
        resource_refs=resource_refs,
        visible_provenance=provenance,
    )


def _compile_delivery_v4(
    request: DeliveryCompileInput,
    kernel: CreativeKernelV1,
) -> CompiledDelivery:
    """Compile the resource-closed v4 artifact from one frozen MediaProgram."""

    envelope = request.media_capability_envelope
    program = request.media_program
    if envelope is None or program is None:
        raise GenerationFailed("新成品缺少冻结媒体能力包或媒体程序")
    assert_media_program_allowed(envelope, program)
    if request.media_format != envelope.media_format:
        raise GenerationFailed("媒体能力包与成品形式不一致")
    if request.allowed_resource_ids != envelope.resource_ids:
        raise GenerationFailed("成品编译资源集合与冻结媒体能力包不一致")
    forbidden_media_purposes = {
        "media_opening",
        "media_sequence",
        "subtitle_strategy",
        "production_note",
    }
    if any(unit.purpose in forbidden_media_purposes for unit in kernel.units):
        raise GenerationFailed("Writer 返回了服务端专属媒体单元")
    singleton_purposes = {
        "title",
        "natural_guide",
        "release_caption",
    }
    singleton = {unit.purpose: unit for unit in kernel.units if unit.purpose in singleton_purposes}
    if set(singleton) != singleton_purposes or any(
        sum(unit.purpose == purpose for unit in kernel.units) != 1 for purpose in singleton_purposes
    ):
        raise GenerationFailed("创作内核缺少完整文字单元")
    body_units = tuple(unit for unit in kernel.units if unit.purpose == "body")
    if not body_units or any(not unit.text.strip() for unit in (*singleton.values(), *body_units)):
        raise GenerationFailed("创作内核包含空的可见创作单元")
    if isinstance(request.product_value_contract, P2ProductValueContractV1):
        writer_visible_text = "\n".join(
            unit.text
            for unit in kernel.units
            if unit.text_source == "writer"
        )
        if any(
            label in writer_visible_text
            for label in ("专属新增理解", "相伴取舍", "成立条件")
        ):
            raise GenerationFailed("Writer 把内部商品语义标签写进了成品")
        if any(
            phrase in request.product_value_contract.tradeoff_or_limit
            for phrase in (
                "内容只能",
                "稿件只能",
                "页面只能",
                "表达只能",
            )
        ):
            raise GenerationFailed("商品取舍错误地落在了内容表达上")
    title = singleton["title"].text.strip()
    guide = singleton["natural_guide"].text.strip()
    release = singleton["release_caption"].text.strip()
    fact_units = tuple(unit for unit in kernel.units if unit.purpose == "frozen_fact")
    creative_body = "\n\n".join(_visible_unit_v3(unit) for unit in body_units)
    artifact_scope_source = _artifact_scope_source(kernel)
    artifact_scope = _PHRASES[artifact_scope_source]
    if isinstance(request.product_value_contract, P2ProductValueContractV1):
        contract: ContentSemanticContract = P2SemanticContract(
            request.product_value_contract.product_insight,
            request.product_value_contract.tradeoff_or_limit,
            request.product_value_contract.validity_condition,
        )
    elif isinstance(
        request.product_value_contract,
        P5ProductValueContractV1,
    ):
        contract = P5SemanticContract(
            request.product_value_contract.real_product_anchor,
            request.product_value_contract.visible_styling_proposition,
            request.product_value_contract.visual_dependency,
        )
    else:
        contract = _contract(
            request.primary_product,
            guide,
            creative_body,
            release,
            fact_units,
            media_native=True,
        )
    if isinstance(
        request.product_value_contract,
        (P2ProductValueContractV1, P5ProductValueContractV1),
    ):
        content_units = fact_units
        full_body = _product_value_full_body(
            fact_units,
            request.product_value_contract.visible_text,
        )
    else:
        content_units = (*fact_units, *body_units)
        full_body = "\n\n".join(
            _visible_unit_v3(unit) for unit in content_units
        )
    envelope_source = f"media-envelope:{media_envelope_digest(envelope)}"
    program_digest_source = f"media-program:{media_program_digest(program)}"
    program_source = f"media-program:{program.program_id}"
    resource_sources = tuple(f"media-resource:{resource_id}" for resource_id in program.required_resource_ids)
    content_sources = tuple(
        source
        for unit in content_units
        for source in (
            unit.unit_id,
            *((_visible_unit_scope_source(unit),) if unit.track == "trusted_fact" else ()),
        )
    )
    provenance: dict[str, tuple[str, ...]] = {
        "outline": (singleton["title"].unit_id,),
        "artifact_scope": (artifact_scope_source,),
        "natural_guide": (singleton["natural_guide"].unit_id,),
        "release_caption_and_interaction": (singleton["release_caption"].unit_id,),
        "media_program": (
            envelope_source,
            program_digest_source,
            program_source,
            *resource_sources,
            *(
                (
                    f"media-role:primary:{program.primary_resource_id}",
                    f"media-role:secondary:{program.secondary_resource_id}",
                )
                if program.primary_resource_id
                and program.secondary_resource_id
                else ()
            ),
        ),
    }
    optional_suggestion = _optional_capture_suggestion(program, title)
    if optional_suggestion is not None:
        provenance["optional_capture_suggestion"] = (
            f"compiler:optional-capture-suggestion:{program.optional_capture_suggestion_id}",
            singleton["title"].unit_id,
        )
    production: ContentProductionBundle
    if request.media_format == "graphic":
        opening, sequence, production_note = _bind_graphic_program_to_title(
            title,
            _graphic_media_program_text(program),
        )
        production = GraphicProductionBundle(
            natural_guide=guide,
            hero_image=opening,
            image_sequence=sequence,
            full_body=full_body,
            layout_and_production=production_note,
            release_caption_and_interaction=release,
            optional_capture_suggestion=optional_suggestion,
        )
        provenance.update(
            {
                "hero_image": (
                    program_source,
                    envelope_source,
                    singleton["title"].unit_id,
                ),
                "image_sequence": (
                    program_source,
                    singleton["title"].unit_id,
                    *content_sources,
                    *resource_sources,
                ),
                "full_body": content_sources,
                "layout_and_production": (
                    program_source,
                    envelope_source,
                    singleton["title"].unit_id,
                ),
            }
        )
    else:
        (
            opening,
            sequence,
            spoken,
            subtitles,
            production_note,
        ) = _bind_video_program_to_title(
            title,
            _video_media_program_text(
                program,
                full_body,
            ),
        )
        production = VideoProductionBundle(
            natural_guide=guide,
            spoken_lines=spoken,
            visual_actions=sequence,
            subtitles=subtitles,
            sound_and_production=production_note,
            cover_or_first_frame=opening,
            viewing_flow=f"{opening}\n{sequence}",
            natural_duration=_duration(
                full_body,
                request.production_conditions,
            ),
            release_caption_and_interaction=release,
            optional_capture_suggestion=optional_suggestion,
        )
        provenance.update(
            {
                "cover_or_first_frame": (
                    program_source,
                    envelope_source,
                    singleton["title"].unit_id,
                ),
                "viewing_flow": (
                    program_source,
                    singleton["title"].unit_id,
                    *content_sources,
                    *resource_sources,
                ),
                "spoken_lines": (
                    *content_sources,
                    program_source,
                ),
                "visual_actions": (
                    program_source,
                    singleton["title"].unit_id,
                    *resource_sources,
                ),
                "subtitles": (
                    *content_sources,
                    program_source,
                ),
                "sound_and_production": (
                    program_source,
                    envelope_source,
                    singleton["title"].unit_id,
                ),
                "natural_duration": ("compiler:duration",),
            }
        )
    body = _visible_body_v3(
        title,
        artifact_scope,
        production,
    )
    provenance["body"] = (
        "compiler:visible-body",
        artifact_scope_source,
        *tuple(source for sources in provenance.values() for source in sources),
    )
    return CompiledDelivery(
        outline=title,
        body=body,
        semantic_contract=contract,
        production=production,
        resource_refs=program.required_resource_ids,
        visible_provenance=provenance,
    )


def _optional_capture_suggestion(
    program: MediaProgramSelectionV1,
    title: str,
) -> str | None:
    if program.optional_capture_suggestion_id == "optional-current-product-capture-v1":
        return (
            f"如果《{title}》提到的商品仍在手边，而且你愿意补拍，可以另加一张整体照片；"
            "没有也不影响，当前版本可直接用文字、色块和留白完成。"
        )
    if program.optional_capture_suggestion_id == "optional-current-subject-capture-v1":
        return (
            f"如果《{title}》提到的事物仍在手边，而且你愿意补拍，可以另加一张照片；"
            "没有也不影响，当前版本可直接用文字、色块和留白完成。"
        )
    return None


def _bind_graphic_program_to_title(
    title: str,
    texts: tuple[str, str, str],
) -> tuple[str, str, str]:
    opening, sequence, production_note = texts
    return (
        f"{opening} 本篇首图只承接《{title}》这个具体切口。",
        f"{sequence} 页面转折只承接《{title}》与本篇已审正文。",
        f"{production_note} 排版只承接《{title}》和本篇已审文字。",
    )


def _bind_video_program_to_title(
    title: str,
    texts: tuple[str, str, str, str, str],
) -> tuple[str, str, str, str, str]:
    opening, sequence, spoken, subtitles, production_note = texts
    return (
        f"{opening} 本篇首帧只承接《{title}》这个具体切口。",
        f"{sequence} 观看链只承接《{title}》与本篇已审正文。",
        spoken,
        subtitles,
        f"{production_note} 制作只承接《{title}》和本篇已审文字。",
    )


def _graphic_media_program_text(
    program: MediaProgramSelectionV1,
) -> tuple[str, str, str]:
    abstract_note = "仅使用文字、排版、色块、线条、符号和留白；不要求现实人物、商品、照片、家具、场地或道具。"
    if program.program_id == "graphic_registered_product_relation_v1":
        if not program.primary_resource_id or not program.secondary_resource_id:
            # Historical media-program-v1 artifacts retain their original
            # projection.  New v2 tasks cannot reach this branch because the
            # media-contract validator requires both frozen roles.
            return (
                "首图将本次选中的登记商品素材以同一尺度并列，标题不遮挡主体。",
                "先分别完整呈现每个登记素材，再保持一致画面条件呈现彼此关系；"
                "事实原句独立排入对应页面，末页回到本篇视觉选择。",
                "只使用本次冻结的登记商品素材与抽象排版；保持一致尺度、间距、层级和画面重心，不增加其他实物。",
            )
        return (
            "首图先让主视觉素材居中并占较大面积，辅助视觉素材位于侧边、面积较小；标题不遮挡两件商品。",
            "第 1 页先完整呈现主视觉素材；第 2 页让辅助视觉素材从侧边回应；"
            "第 3 页保持主视觉居中且约占六成、辅助视觉侧置且约占四成，"
            "呈现冻结的一主一辅关系；事实原句独立排入对应页面，末页回到本篇选择。",
            "只使用本次冻结的两份登记商品素材与抽象排版；主视觉始终先出现、居中且较大，"
            "辅助视觉随后出现、侧置且较小，不交换角色，不增加其他实物。",
        )
    if (
        program.program_id == "graphic_observation_progression_v1"
        and program.series_position == 1
    ):
        return (
            "首图用标题和一条起始线建立本系列的第一个观察，不预告尚未形成的后续内容。",
            "第 1 页交代本篇具体处境；中间页依次展开本篇判断和可选动作；末页留下下一篇可以继续回应的问题。",
            "用文字层级、单一色块、线条和留白区分处境、判断与动作；不要求现实人物、商品、照片、家具、场地或道具。",
        )
    by_program: dict[str, tuple[str, str, str]] = {
        "graphic_fact_guided_v1": (
            "首图用标题与两块克制色块建立“已知信息／选择判断”的阅读入口。",
            "第 1 页给标题和观看回报；第 2 页逐字呈现已确认事实；第 3 页进入正文中的选择解释；末页用发布配文收束。",
            abstract_note,
        ),
        "graphic_observation_progression_v1": (
            "首图用标题、单一强调色和留白制造一次可读停顿。",
            "第 1 页交代标题；第 2 页给自然导读；中间页按正文段落逐层推进；末页只保留本篇发布配文。",
            abstract_note,
        ),
        "graphic_choice_contrast_v1": (
            "首图把标题放在中轴，两侧用不同色块预告两种选择条件。",
            "第 1 页提出选择；第 2、3 页分别承接两组条件与边界；第 4 页给下一步动作；末页用发布配文收束。",
            abstract_note,
        ),
        "graphic_series_response_v1": (
            "首图保留系列标题位置，并用一条推进线标出这是对前一篇的回应。",
            "第 1 页回扣前篇留下的问题；中间页只展开本篇新增回应；末页留下下一篇仍可继续的空间。",
            abstract_note,
        ),
        "graphic_series_choice_v1": (
            "首图用两段错位文字承接前两篇，并把本篇选择放在视觉重心。",
            "第 1 页承接前两篇共同问题；第 2 页分开可选路径；第 3 页说明本篇取舍；末页保留开放选择。",
            abstract_note,
        ),
        "graphic_selected_asset_sequence_v1": (
            "首图使用本次明确选择的登记素材，并把标题置于不遮挡内容的留白区。",
            "按冻结素材顺序进入，每页只承担一个正文转折；末页回到发布配文，不补入未选择素材。",
            "只使用本次冻结的所选素材与抽象排版，不根据文件名或说明猜测现实事实。",
        ),
    }
    try:
        return by_program[program.program_id]
    except KeyError as exc:
        raise GenerationFailed("图文媒体程序与成品形式不一致") from exc


def _video_media_program_text(
    program: MediaProgramSelectionV1,
    full_body: str,
) -> tuple[str, str, str, str, str]:
    abstract_sound = "默认静音，不要求环境声；仅使用文字、排版、色块、线条、符号、留白和字幕切换完成。"
    if program.program_id == "video_dynamic_text_v1":
        return (
            "首帧只出现标题和一处强调色，不调用现实画面。",
            "标题短停后，正文按段落逐屏进入；关键转折改变对齐与留白，最后回到发布配文。",
            "本版不要求口播；完整正文由动态文字与字幕承担。",
            full_body,
            abstract_sound,
        )
    if program.program_id == "video_condition_choice_v1":
        return (
            "首帧用左右两块色域提出两种条件，标题位于中间。",
            "先给共同问题，再让两组条件交替进入；选择边界单独停留，最后显示下一步动作与发布配文。",
            "本版不要求口播；完整选择帮助由动态文字与字幕承担。",
            full_body,
            abstract_sound,
        )
    if program.program_id == "video_creator_expression_v1":
        return (
            "首帧先给标题，随后由已登记创作者表达进入。",
            "标题短停后进入完整正文表达；关键转折用字幕强调，最后以发布配文收束。",
            full_body,
            "字幕保留标题、事实原句和每段关键转折，不另写现实细节。",
            "只使用已登记的创作者表达与抽象编排；不要求场地、道具或环境声。",
        )
    if program.program_id == "video_registered_product_display_v1":
        if program.primary_resource_id and program.secondary_resource_id:
            return (
                "首帧先让主视觉素材居中并占较大面积，辅助视觉素材侧置且较小，标题不遮挡主体。",
                "先完整呈现主视觉素材，再让辅助视觉素材从侧边进入；关系帧保持主视觉约六成、"
                "辅助视觉约四成，最后回到两者的一主一辅关系；事实原句只进入对应字幕。",
                "本版不要求口播；正文由字幕与两份登记商品素材共同承担。",
                full_body,
                "只使用冻结的两份登记商品素材和抽象编排；主视觉先出现、居中且较大，"
                "辅助视觉后出现、侧置且较小，不交换角色，不增加演员、场地、道具或环境声。",
            )
        return (
            "首帧让本次选中的登记商品素材完整进入同一画面，标题不遮挡主体。",
            "按冻结顺序分别完整呈现登记素材，再以一致画面条件呈现彼此关系；事实原句只进入对应字幕。",
            "本版不要求口播；正文由字幕与登记商品画面共同承担。",
            full_body,
            "只使用冻结的登记商品素材和抽象编排；不增加演员、场地、道具或环境声。",
        )
    if program.program_id == "video_selected_asset_sequence_v1":
        return (
            "首帧使用本次明确选择的登记素材，标题位于不遮挡内容的区域。",
            "按冻结素材顺序推进，每个素材只承接一个正文转折；最后回到发布配文，不补入未选择素材。",
            "本版不要求口播；正文由字幕与所选素材共同承担。",
            full_body,
            "只使用本次冻结的所选素材与抽象编排，不根据文件名或说明猜测现实事实。",
        )
    raise GenerationFailed("视频媒体程序与成品形式不一致")


def _compile_delivery_v3(
    request: DeliveryCompileInput,
    kernel: CreativeKernelV1,
) -> CompiledDelivery:
    """Compile a media-native artifact without inventing its creative copy.

    Every creative field is preallocated by the service and filled by Writer.
    Compiler only inserts frozen facts, one artifact-level scope, registered
    resources and deterministic structure.
    """

    singleton_purposes = {
        "title",
        "natural_guide",
        "media_opening",
        "media_sequence",
        "production_note",
        "release_caption",
    }
    if request.media_format == "video":
        singleton_purposes.add("subtitle_strategy")
    singleton = {unit.purpose: unit for unit in kernel.units if unit.purpose in singleton_purposes}
    if set(singleton) != singleton_purposes or any(
        sum(unit.purpose == purpose for unit in kernel.units) != 1 for purpose in singleton_purposes
    ):
        raise GenerationFailed("创作内核缺少完整媒体原生单元")
    body_units = tuple(unit for unit in kernel.units if unit.purpose == "body")
    if not body_units:
        raise GenerationFailed("创作内核缺少完整核心正文")
    if any(not unit.text.strip() for unit in (*singleton.values(), *body_units)):
        raise GenerationFailed("创作内核包含空的可见创作单元")

    title = singleton["title"].text.strip()
    guide = singleton["natural_guide"].text.strip()
    release = singleton["release_caption"].text.strip()
    fact_units = tuple(unit for unit in kernel.units if unit.purpose == "frozen_fact")
    spoken_parts = (*fact_units, *body_units)
    spoken = "\n\n".join(_visible_unit_v3(unit) for unit in spoken_parts)
    creative_body = "\n\n".join(_visible_unit_v3(unit) for unit in body_units)
    artifact_scope_source = _artifact_scope_source(kernel)
    artifact_scope = _PHRASES[artifact_scope_source]
    contract = _contract(
        request.primary_product,
        guide,
        creative_body,
        release,
        fact_units,
        media_native=True,
    )

    product_resources = tuple(
        f"resource:product:{product.sku}"
        for product in request.products
        if f"resource:product:{product.sku}" in request.allowed_resource_ids
    )
    if ORIGINAL_COMPOSITION_RESOURCE_ID not in request.allowed_resource_ids:
        raise GenerationFailed("确定性成品编译缺少原创编排资源")
    resource_refs: tuple[str, ...] = (ORIGINAL_COMPOSITION_RESOURCE_ID,)
    if request.primary_product in {"product_truth", "visual_styling_story"}:
        resource_refs = tuple(dict.fromkeys((*resource_refs, *product_resources)))
    if request.media_format == "video" and CREATOR_EXPRESSION_RESOURCE_ID in request.allowed_resource_ids:
        resource_refs = tuple(dict.fromkeys((*resource_refs, CREATOR_EXPRESSION_RESOURCE_ID)))

    scope_and_units = (
        artifact_scope_source,
        *(unit.unit_id for unit in spoken_parts),
    )
    provenance: dict[str, tuple[str, ...]] = {
        "outline": (singleton["title"].unit_id,),
        "artifact_scope": (artifact_scope_source,),
        "natural_guide": (singleton["natural_guide"].unit_id,),
        "release_caption_and_interaction": (singleton["release_caption"].unit_id,),
    }
    production: ContentProductionBundle
    if request.media_format == "graphic":
        production = GraphicProductionBundle(
            natural_guide=guide,
            hero_image=singleton["media_opening"].text.strip(),
            image_sequence=singleton["media_sequence"].text.strip(),
            full_body=spoken,
            layout_and_production=singleton["production_note"].text.strip(),
            release_caption_and_interaction=release,
        )
        provenance.update(
            {
                "hero_image": (singleton["media_opening"].unit_id,),
                "image_sequence": (singleton["media_sequence"].unit_id,),
                "full_body": tuple(
                    source
                    for unit in spoken_parts
                    for source in (
                        unit.unit_id,
                        *((_visible_unit_scope_source(unit),) if unit.track == "trusted_fact" else ()),
                    )
                ),
                "layout_and_production": (singleton["production_note"].unit_id,),
            }
        )
    else:
        opening = singleton["media_opening"].text.strip()
        sequence = singleton["media_sequence"].text.strip()
        production = VideoProductionBundle(
            natural_guide=guide,
            spoken_lines=spoken,
            visual_actions=sequence,
            subtitles=singleton["subtitle_strategy"].text.strip(),
            sound_and_production=singleton["production_note"].text.strip(),
            cover_or_first_frame=opening,
            viewing_flow=f"{opening}\n{sequence}",
            natural_duration=_duration(
                spoken,
                request.production_conditions,
            ),
            release_caption_and_interaction=release,
        )
        provenance.update(
            {
                "cover_or_first_frame": (singleton["media_opening"].unit_id,),
                "viewing_flow": (
                    singleton["media_opening"].unit_id,
                    singleton["media_sequence"].unit_id,
                ),
                "spoken_lines": tuple(
                    source
                    for unit in spoken_parts
                    for source in (
                        unit.unit_id,
                        *((_visible_unit_scope_source(unit),) if unit.track == "trusted_fact" else ()),
                    )
                ),
                "visual_actions": (singleton["media_sequence"].unit_id,),
                "subtitles": (singleton["subtitle_strategy"].unit_id,),
                "sound_and_production": (singleton["production_note"].unit_id,),
                "natural_duration": ("compiler:duration",),
            }
        )
    body = _visible_body_v3(
        title,
        artifact_scope,
        production,
    )
    provenance["body"] = (
        "compiler:visible-body",
        *scope_and_units,
        *tuple(source for sources in provenance.values() for source in sources),
    )
    return CompiledDelivery(
        outline=title,
        body=body,
        semantic_contract=contract,
        production=production,
        resource_refs=resource_refs,
        visible_provenance=provenance,
    )


def _visible_unit_v3(unit: CreativeKernelUnit) -> str:
    if unit.track != "trusted_fact":
        return unit.text.strip()
    source = _visible_unit_scope_source(unit)
    prefix = _PHRASES[source]
    if source == "phrase:scope-user-fact":
        return f"{prefix}“{unit.text}”"
    return f"{prefix}{unit.text}"


def _product_value_full_body(
    fact_units: tuple[CreativeKernelUnit, ...],
    product_value_text: str,
) -> str:
    visible_parts: list[str] = []
    grouped_facts: dict[str, list[str]] = {}
    for unit in fact_units:
        source = _visible_unit_scope_source(unit)
        if source == "phrase:scope-user-fact":
            visible_parts.append(_visible_unit_v3(unit))
            continue
        grouped_facts.setdefault(source, []).append(unit.text.strip())
    for source, facts in grouped_facts.items():
        visible_parts.append(f"{_PHRASES[source]}\n" + "\n".join(facts))
    visible_parts.append(product_value_text.strip())
    return "\n\n".join(visible_parts)


def _visible_unit(unit: CreativeKernelUnit) -> str:
    source = _visible_unit_scope_source(unit)
    prefix = _PHRASES[source]
    if source == "phrase:scope-user-fact":
        return f"{prefix}“{unit.text}”"
    return f"{prefix}{unit.text}"


def _visible_unit_scope_source(unit: CreativeKernelUnit) -> str:
    if unit.track == "trusted_fact":
        if unit.allowed_observation_types == ("user_actuality",):
            return "phrase:scope-user-fact"
        if unit.allowed_observation_types == ("institutional_assertion",):
            return "phrase:scope-brand-fact"
        return "phrase:scope-product-fact"
    source_by_mode: dict[UnitMode, str] = {
        "trusted_fact": "",
        "general_observation": "phrase:scope-general",
        "recommendation": "phrase:scope-recommendation",
        "hypothesis": "phrase:scope-hypothesis",
        "disclosed_dramatization": "phrase:scope-dramatization",
    }
    source = source_by_mode[unit.mode]
    if not source:
        raise GenerationFailed("创作表达轨缺少可见范围")
    return source


def _artifact_scope_source(kernel: CreativeKernelV1) -> str:
    body_modes = {unit.mode for unit in kernel.units if unit.purpose == "body" and unit.track == "creative_expression"}
    has_user_fact = any(
        unit.track == "trusted_fact" and unit.allowed_observation_types == ("user_actuality",) for unit in kernel.units
    )
    has_confirmed_fact = any(
        unit.track == "trusted_fact" and unit.allowed_observation_types != ("user_actuality",) for unit in kernel.units
    )
    if "disclosed_dramatization" in body_modes:
        return "phrase:artifact-user-fact-drama" if has_user_fact else "phrase:artifact-dramatization"
    if "hypothesis" in body_modes:
        return "phrase:artifact-user-fact-hypothesis" if has_user_fact else "phrase:artifact-hypothesis"
    if "recommendation" in body_modes:
        if has_user_fact:
            return "phrase:artifact-user-fact-recommendation"
        if has_confirmed_fact:
            return "phrase:artifact-confirmed-fact-recommendation"
        return "phrase:artifact-recommendation"
    if has_user_fact:
        return "phrase:artifact-user-fact"
    if has_confirmed_fact:
        return "phrase:artifact-confirmed-fact"
    return "phrase:artifact-general"


def _title_scope_source(kernel: CreativeKernelV1) -> str:
    artifact_source = _artifact_scope_source(kernel)
    if artifact_source in {"phrase:artifact-dramatization", "phrase:artifact-user-fact-drama"}:
        return "phrase:title-dramatization"
    if artifact_source in {
        "phrase:artifact-hypothesis",
        "phrase:artifact-user-fact-hypothesis",
    }:
        return "phrase:title-hypothesis"
    if artifact_source == "phrase:artifact-user-fact":
        return "phrase:title-user-fact"
    if artifact_source == "phrase:artifact-confirmed-fact":
        return "phrase:title-confirmed-fact"
    return "phrase:title-general"


def _scoped_title(text: str, kernel: CreativeKernelV1) -> tuple[str, str]:
    source = _title_scope_source(kernel)
    return f"{_PHRASES[source]}{text}", source


def _scoped_compiler_text(text: str, kernel: CreativeKernelV1) -> tuple[str, str]:
    source = _artifact_scope_source(kernel)
    return f"{_PHRASES[source]}{text}", source


def _contract(
    product: ContentProduct,
    guide: str,
    body: str,
    release: str,
    facts: tuple[CreativeKernelUnit, ...],
    *,
    media_native: bool,
) -> ContentSemanticContract:
    fact_text = "\n".join(unit.text for unit in facts) or _PHRASES["phrase:fact-boundary"]
    if product == "dressing_decision":
        return P1SemanticContract(body, _PHRASES["phrase:fact-boundary"], release)
    if product == "product_truth":
        return P2SemanticContract(fact_text, body, _PHRASES["phrase:fact-boundary"])
    if product == "brand_life_narrative":
        return P3SemanticContract(
            body,
            release,
            guide if media_native else _PHRASES["phrase:account-view"],
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
    return "标题：" + title + "\n\n" + "\n\n".join(f"{heading}：{value}" for heading, value in sections)


def _visible_body_v3(
    title: str,
    artifact_scope: str,
    production: ContentProductionBundle,
) -> str:
    if isinstance(production, VideoProductionBundle):
        sections: tuple[tuple[str, str], ...] = (
            ("表达范围", artifact_scope),
            (
                v3_compiler_visible_heading("video", "natural_guide"),
                production.natural_guide,
            ),
            (
                v3_compiler_visible_heading("video", "media_opening"),
                production.cover_or_first_frame,
            ),
            (
                v3_compiler_visible_heading("video", "body"),
                production.spoken_lines,
            ),
            (
                v3_compiler_visible_heading("video", "media_sequence"),
                production.visual_actions,
            ),
            (
                v3_compiler_visible_heading("video", "subtitle_strategy"),
                production.subtitles,
            ),
            (
                v3_compiler_visible_heading("video", "production_note"),
                production.sound_and_production,
            ),
            ("自然时长", production.natural_duration),
            (
                v3_compiler_visible_heading("video", "release_caption"),
                production.release_caption_and_interaction,
            ),
            *(
                (
                    (
                        "可选补拍建议",
                        production.optional_capture_suggestion,
                    ),
                )
                if production.optional_capture_suggestion
                else ()
            ),
        )
    else:
        sections = (
            ("表达范围", artifact_scope),
            (
                v3_compiler_visible_heading("graphic", "natural_guide"),
                production.natural_guide,
            ),
            (
                v3_compiler_visible_heading("graphic", "media_opening"),
                production.hero_image,
            ),
            (
                v3_compiler_visible_heading("graphic", "media_sequence"),
                production.image_sequence,
            ),
            (
                v3_compiler_visible_heading("graphic", "body"),
                production.full_body,
            ),
            (
                v3_compiler_visible_heading("graphic", "production_note"),
                production.layout_and_production,
            ),
            (
                v3_compiler_visible_heading("graphic", "release_caption"),
                production.release_caption_and_interaction,
            ),
            *(
                (
                    (
                        "可选补拍建议",
                        production.optional_capture_suggestion,
                    ),
                )
                if production.optional_capture_suggestion
                else ()
            ),
        )
    return "标题：" + title + "\n\n" + "\n\n".join(f"{heading}：{value}" for heading, value in sections)
