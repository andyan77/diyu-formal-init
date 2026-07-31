from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, TypeAlias, cast

from src.shared.errors import DomainError, GenerationFailed
from src.shared.factual_basis import build_product_fact_packet
from src.shared.media_program import (
    BoundProductMediaResourceV2,
    MediaCapabilityEnvelope,
)
from src.shared.types import BoundProductMedia, ContentProduct, ProductFact

PRODUCT_VALUE_CONTRACT_VERSION = "product-value-contract-v1"


@dataclass(frozen=True)
class P2ProductValueContractV1:
    contract_version: str
    primary_product: Literal["product_truth"]
    product_insight: str
    tradeoff_or_limit: str
    validity_condition: str
    source_fact_ids: tuple[str, ...]
    source_packet_digest: str

    @property
    def visible_text(self) -> str:
        return "\n".join(
            (
                self.product_insight,
                self.tradeoff_or_limit,
                self.validity_condition,
            )
        )


@dataclass(frozen=True)
class P5ProductValueContractV1:
    contract_version: str
    primary_product: Literal["visual_styling_story"]
    real_product_anchor: str
    visible_styling_proposition: str
    visual_dependency: str
    relation_kind: Literal["color_hierarchy", "silhouette_hierarchy"]
    source_fact_ids: tuple[str, ...]
    source_packet_digest: str
    resource_refs: tuple[str, str]

    @property
    def visible_text(self) -> str:
        return "\n".join(
            (
                self.real_product_anchor,
                self.visible_styling_proposition,
                self.visual_dependency,
            )
        )


ProductValueContract: TypeAlias = (
    P2ProductValueContractV1 | P5ProductValueContractV1
)


def build_product_value_contract(
    *,
    primary_product: ContentProduct,
    products: Sequence[ProductFact],
    bound_product_media: Sequence[BoundProductMedia] = (),
    media_envelope: MediaCapabilityEnvelope | None = None,
) -> ProductValueContract | None:
    if primary_product == "product_truth":
        return _build_p2_contract(products)
    if primary_product == "visual_styling_story":
        return _build_p5_contract(
            products,
            bound_product_media=bound_product_media,
            media_envelope=media_envelope,
        )
    return None


def product_value_contract_document(
    contract: ProductValueContract,
) -> dict[str, object]:
    common: dict[str, object] = {
        "contract_version": contract.contract_version,
        "primary_product": contract.primary_product,
        "source_fact_ids": list(contract.source_fact_ids),
        "source_packet_digest": contract.source_packet_digest,
    }
    if isinstance(contract, P2ProductValueContractV1):
        return common | {
            "product_insight": contract.product_insight,
            "tradeoff_or_limit": contract.tradeoff_or_limit,
            "validity_condition": contract.validity_condition,
        }
    return common | {
        "real_product_anchor": contract.real_product_anchor,
        "visible_styling_proposition": contract.visible_styling_proposition,
        "visual_dependency": contract.visual_dependency,
        "relation_kind": contract.relation_kind,
        "resource_refs": list(contract.resource_refs),
    }


def product_value_contract_digest(contract: ProductValueContract) -> str:
    return hashlib.sha256(
        json.dumps(
            product_value_contract_document(contract),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    ).hexdigest()


def product_value_contract_from_document(
    value: object,
) -> ProductValueContract:
    if not isinstance(value, Mapping):
        raise DomainError("内容任务冻结的商品价值合同无效")
    version = _required_string(value.get("contract_version"))
    if version != PRODUCT_VALUE_CONTRACT_VERSION:
        raise DomainError("内容任务冻结的商品价值合同版本无效")
    primary_product = value.get("primary_product")
    source_fact_ids = _string_tuple(value.get("source_fact_ids"))
    packet_digest = _required_digest(value.get("source_packet_digest"))
    if primary_product == "product_truth":
        expected = {
            "contract_version",
            "primary_product",
            "product_insight",
            "tradeoff_or_limit",
            "validity_condition",
            "source_fact_ids",
            "source_packet_digest",
        }
        if set(value) != expected:
            raise DomainError("内容任务冻结的商品解释合同字段无效")
        return P2ProductValueContractV1(
            contract_version=version,
            primary_product="product_truth",
            product_insight=_required_string(value.get("product_insight")),
            tradeoff_or_limit=_required_string(value.get("tradeoff_or_limit")),
            validity_condition=_required_string(value.get("validity_condition")),
            source_fact_ids=source_fact_ids,
            source_packet_digest=packet_digest,
        )
    if primary_product == "visual_styling_story":
        expected = {
            "contract_version",
            "primary_product",
            "real_product_anchor",
            "visible_styling_proposition",
            "visual_dependency",
            "relation_kind",
            "source_fact_ids",
            "source_packet_digest",
            "resource_refs",
        }
        if set(value) != expected:
            raise DomainError("内容任务冻结的视觉命题合同字段无效")
        relation_kind = value.get("relation_kind")
        if relation_kind not in {"color_hierarchy", "silhouette_hierarchy"}:
            raise DomainError("内容任务冻结的视觉命题类型无效")
        resource_refs = _string_tuple(value.get("resource_refs"))
        if len(resource_refs) != 2 or len(set(resource_refs)) != 2:
            raise DomainError("内容任务冻结的视觉命题资源无效")
        return P5ProductValueContractV1(
            contract_version=version,
            primary_product="visual_styling_story",
            real_product_anchor=_required_string(value.get("real_product_anchor")),
            visible_styling_proposition=_required_string(
                value.get("visible_styling_proposition")
            ),
            visual_dependency=_required_string(value.get("visual_dependency")),
            relation_kind=cast(
                Literal["color_hierarchy", "silhouette_hierarchy"],
                relation_kind,
            ),
            source_fact_ids=source_fact_ids,
            source_packet_digest=packet_digest,
            resource_refs=resource_refs,
        )
    raise DomainError("内容任务冻结的商品价值合同产品类型无效")


def _build_p2_contract(
    products: Sequence[ProductFact],
) -> P2ProductValueContractV1:
    if len(products) != 1:
        raise GenerationFailed("商品解释需要明确选择一件已确认商品。")
    product = products[0]
    packet = build_product_fact_packet((product,))
    facts_by_key = {item.fact_key: item for item in packet.facts}
    colors = _visible_values(product.facts.get("colors"))
    both_sides = product.facts.get("both_sides_complete") is True
    structure = _visible_string(
        product.facts.get("material_or_structure")
        or product.facts.get("material")
    )
    silhouette = _visible_string(product.facts.get("silhouette"))
    observable = _visible_string(product.facts.get("observable_features"))
    source_keys: tuple[str, ...]
    if both_sides and len(colors) >= 2:
        source_keys = ("display_name", "colors", "both_sides_complete")
        insight = (
            f"{product.display_name}的专属新增理解是：{colors[0]}与{colors[1]}两面都作为"
            "完整外观存在时，选择的单位不是一个局部细节，而是同一件商品的两套完整视觉呈现。"
        )
        tradeoff = (
            "相伴取舍是一次内容只能先突出其中一套完整外观；突出一面会暂时弱化"
            "另一面的可见存在，不能把双面直接夸成两件商品。"
        )
        condition = (
            "这项理解只在本次判断确实围绕两面完整外观时成立；如果本次只固定呈现"
            "其中一面，双面就不是这次选择的决定因素。"
        )
    elif len(colors) >= 2:
        source_keys = ("display_name", "colors")
        insight = (
            f"{product.display_name}的专属新增理解是：已确认的{colors[0]}与{colors[1]}"
            "提供了不同的可见重心，选择应落在本次想让哪一种颜色先被看见。"
        )
        tradeoff = (
            "相伴取舍是突出一种颜色会弱化其他颜色在本次内容里的存在；这不等于"
            "颜色已经证明用途、效果或穿着体验。"
        )
        condition = (
            "这项理解只在本次问题确实依赖颜色差异时成立；如果选择并不取决于颜色，"
            "这组颜色就不能替代其他尚未确认的判断依据。"
        )
    elif structure and silhouette:
        structure_key = (
            "material_or_structure"
            if "material_or_structure" in facts_by_key
            else "material"
        )
        source_keys = ("display_name", structure_key, "silhouette")
        insight = (
            f"{product.display_name}的专属新增理解是：已确认的{structure}与{silhouette}"
            "可以放在同一个选择里解释，让结构信息和轮廓信息彼此校准，而不是各说一遍。"
        )
        tradeoff = (
            "相伴取舍是这项解释只能落在已确认的结构与轮廓关系上，不能由此推出材质手感、"
            "保暖、舒适、用途或上身效果。"
        )
        condition = (
            "当本次选择确实同时依赖这项结构和轮廓时，这个判断成立；如果问题依赖体验、"
            "性能或具体场景，就不成立。"
        )
    elif observable:
        source_keys = ("display_name", "observable_features")
        insight = (
            f"{product.display_name}的专属新增理解是：已确认的“{observable}”可以成为本次"
            "内容唯一的观察支点，解释应围绕它具体怎样被看见展开。"
        )
        tradeoff = (
            "相伴取舍是这项可见特征不能替代尚未确认的材质、性能、用途或穿着体验。"
        )
        condition = (
            "当本次问题直接依赖这项可见特征时，这个判断成立；如果决定因素在其他未确认"
            "信息上，就不成立。"
        )
    elif structure:
        structure_key = (
            "material_or_structure"
            if "material_or_structure" in facts_by_key
            else "material"
        )
        source_keys = ("display_name", structure_key)
        insight = (
            f"{product.display_name}的专属新增理解是：当前已确认的{structure}把本次解释"
            "限定在这一项具体结构信息上，而不是一份通用商品介绍。"
        )
        tradeoff = (
            "相伴取舍是结构信息本身不能证明材质手感、性能、用途、舒适或上身效果。"
        )
        condition = (
            "当本次问题直接依赖这项结构信息时，这个判断成立；如果问题依赖体验或使用"
            "场景，就不成立。"
        )
    elif silhouette:
        source_keys = ("display_name", "silhouette")
        insight = (
            f"{product.display_name}的专属新增理解是：已确认的{silhouette}让本次解释可以"
            "聚焦轮廓本身怎样被看见，而不是借未确认属性补足意义。"
        )
        tradeoff = (
            "相伴取舍是轮廓信息不能自动证明材质、性能、用途、舒适或上身效果。"
        )
        condition = (
            "当本次选择确实由这项轮廓决定时，这个判断成立；如果决定因素在其他未确认"
            "信息上，就不成立。"
        )
    else:
        raise GenerationFailed(
            "这件商品的当前已确认信息还不足以形成商品专属理解、相伴取舍和成立条件。"
        )
    source_fact_ids = tuple(
        facts_by_key[key].fact_id
        for key in source_keys
        if key in facts_by_key
    )
    if len(source_fact_ids) < 2:
        raise GenerationFailed("商品解释缺少可追踪的商品专属事实。")
    return P2ProductValueContractV1(
        contract_version=PRODUCT_VALUE_CONTRACT_VERSION,
        primary_product="product_truth",
        product_insight=insight,
        tradeoff_or_limit=tradeoff,
        validity_condition=condition,
        source_fact_ids=source_fact_ids,
        source_packet_digest=packet.packet_digest,
    )


def _build_p5_contract(
    products: Sequence[ProductFact],
    *,
    bound_product_media: Sequence[BoundProductMedia],
    media_envelope: MediaCapabilityEnvelope | None,
) -> P5ProductValueContractV1:
    if len(products) != 2 or len(bound_product_media) != 2 or media_envelope is None:
        raise GenerationFailed(
            "这条视觉内容需要两件不同商品、对应的登记素材和可见商品信息。"
        )
    if len({item.product_id for item in bound_product_media}) != 2:
        raise GenerationFailed("这条视觉内容需要两件不同商品。")
    resources = tuple(
        resource
        for resource in media_envelope.resources
        if isinstance(resource, BoundProductMediaResourceV2)
    )
    if len(resources) != 2 or len({item.resource_id for item in resources}) != 2:
        raise GenerationFailed("这条视觉内容缺少两份冻结的登记商品素材。")
    resource_by_product = {resource.product_id: resource for resource in resources}
    media_by_product = {str(item.product_id): item for item in bound_product_media}
    if set(resource_by_product) != set(media_by_product):
        raise GenerationFailed("登记商品素材与当前商品关系不一致。")
    ordered_media = tuple(
        sorted(
            bound_product_media,
            key=lambda item: str(item.product_id),
        )
    )
    ordered_products = tuple(item.product for item in ordered_media)
    packets = tuple(build_product_fact_packet((product,)) for product in ordered_products)
    source_fact_ids: list[str] = []
    colors = tuple(_visible_values(product.facts.get("colors")) for product in ordered_products)
    color_pair = _distinct_pair(colors[0], colors[1])
    relation_kind: Literal["color_hierarchy", "silhouette_hierarchy"]
    if color_pair is not None:
        relation_kind = "color_hierarchy"
        for packet in packets:
            source_fact_ids.extend(
                item.fact_id
                for item in packet.facts
                if item.fact_key in {"display_name", "colors"}
            )
        proposition = (
            f"让{ordered_products[0].display_name}的已确认{color_pair[0]}承担画面主色，"
            f"让{ordered_products[1].display_name}的已确认{color_pair[1]}作为回应色，"
            "形成一主一次、不能互换的具体色彩关系。"
        )
        dependency = (
            "只有两份登记素材都能承载各自冻结颜色时，这条色彩主次命题才成立；"
            "任一颜色关系无法由登记素材承载，就退出这条造型命题。"
        )
    else:
        silhouettes = tuple(
            _visible_string(product.facts.get("silhouette"))
            for product in ordered_products
        )
        if (
            not silhouettes[0]
            or not silhouettes[1]
            or silhouettes[0] == silhouettes[1]
        ):
            raise GenerationFailed(
                "这两件商品的当前资料还不足以形成具体造型关系；请补充不同的已确认颜色或轮廓信息。"
            )
        relation_kind = "silhouette_hierarchy"
        for packet in packets:
            source_fact_ids.extend(
                item.fact_id
                for item in packet.facts
                if item.fact_key in {"display_name", "silhouette"}
            )
        proposition = (
            f"让{ordered_products[0].display_name}的已确认{silhouettes[0]}承担画面主体，"
            f"让{ordered_products[1].display_name}的已确认{silhouettes[1]}作为回应，"
            "形成一主一次、不能互换的具体轮廓关系。"
        )
        dependency = (
            "只有两份登记素材都能承载各自冻结轮廓时，这条轮廓主次命题才成立；"
            "任一轮廓无法由登记素材承载，就退出这条造型命题。"
        )
    packet_digest = hashlib.sha256(
        ":".join(packet.packet_digest for packet in packets).encode()
    ).hexdigest()
    resource_refs = tuple(
        resource_by_product[str(item.product_id)].resource_id
        for item in ordered_media
    )
    return P5ProductValueContractV1(
        contract_version=PRODUCT_VALUE_CONTRACT_VERSION,
        primary_product="visual_styling_story",
        real_product_anchor=(
            "本篇只依赖本次冻结的两份登记商品素材，并让两件不同商品各承担一个不可互换的位置。"
        ),
        visible_styling_proposition=proposition,
        visual_dependency=dependency,
        relation_kind=relation_kind,
        source_fact_ids=tuple(dict.fromkeys(source_fact_ids)),
        source_packet_digest=packet_digest,
        resource_refs=cast(tuple[str, str], resource_refs),
    )


def _visible_values(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(
        text
        for item in value
        if (text := _visible_string(item))
    )


def _visible_string(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _distinct_pair(
    first: tuple[str, ...],
    second: tuple[str, ...],
) -> tuple[str, str] | None:
    return next(
        (
            (left, right)
            for left in first
            for right in second
            if left != right
        ),
        None,
    )


def _required_string(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DomainError("内容任务冻结的商品价值合同文字无效")
    return value


def _required_digest(value: object) -> str:
    text = _required_string(value)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise DomainError("内容任务冻结的商品价值合同摘要无效")
    return text


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise DomainError("内容任务冻结的商品价值合同引用无效")
    result = tuple(item for item in value if isinstance(item, str) and item)
    if len(result) != len(value) or len(result) != len(set(result)):
        raise DomainError("内容任务冻结的商品价值合同引用无效")
    return result
