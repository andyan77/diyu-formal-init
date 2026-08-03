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
    MediaProgramSelectionV1,
)
from src.shared.types import BoundProductMedia, ContentProduct, ProductFact

PRODUCT_VALUE_CONTRACT_VERSION = "product-value-contract-v1"
PRODUCT_DECISION_BASIS_VERSION = "product-decision-basis-v2"
P2DecisionAxis: TypeAlias = Literal[
    "complete_side_choice",
    "confirmed_visible_difference",
    "internal_color_relationship",
    "confirmed_structure_and_silhouette",
]


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


@dataclass(frozen=True)
class P2ProductDecisionBasisV2:
    """Machine-only P2 semantics; it never owns user-visible prose."""

    contract_version: str
    primary_product: Literal["product_truth"]
    decision_axis: P2DecisionAxis
    product_specific_understanding: str
    tradeoff: str
    condition_of_validity: str
    supporting_fact_refs: tuple[str, ...]
    source_packet_digest: str

    @property
    def source_fact_ids(self) -> tuple[str, ...]:
        """Compatibility name for fact-closure consumers, not visible prose."""

        return self.supporting_fact_refs


@dataclass(frozen=True)
class P5ProductDecisionBasisV2:
    """Machine-only visual relation, bound to two registered resources."""

    contract_version: str
    primary_product: Literal["visual_styling_story"]
    product_specific_understanding: str
    tradeoff: str
    condition_of_validity: str
    supporting_fact_refs: tuple[str, ...]
    source_packet_digest: str
    relation_kind: Literal["color_hierarchy", "silhouette_hierarchy"]
    resource_refs: tuple[str, str]

    @property
    def source_fact_ids(self) -> tuple[str, ...]:
        return self.supporting_fact_refs


LegacyProductValueContract: TypeAlias = P2ProductValueContractV1 | P5ProductValueContractV1
ProductValueContract: TypeAlias = LegacyProductValueContract | P2ProductDecisionBasisV2 | P5ProductDecisionBasisV2

ProductDecisionBasisV2: TypeAlias = P2ProductDecisionBasisV2 | P5ProductDecisionBasisV2


def build_product_decision_basis_v2(
    *,
    primary_product: ContentProduct,
    products: Sequence[ProductFact],
    bound_product_media: Sequence[BoundProductMedia] = (),
    media_envelope: MediaCapabilityEnvelope | None = None,
    media_program: MediaProgramSelectionV1 | None = None,
) -> ProductDecisionBasisV2 | None:
    """Build the new machine plan without exposing a visible-text accessor."""

    if primary_product == "product_truth":
        return _build_p2_decision_basis_v2(products)
    legacy = build_product_value_contract(
        primary_product=primary_product,
        products=products,
        bound_product_media=bound_product_media,
        media_envelope=media_envelope,
        media_program=media_program,
    )
    if isinstance(legacy, P5ProductValueContractV1):
        return P5ProductDecisionBasisV2(
            contract_version=PRODUCT_DECISION_BASIS_VERSION,
            primary_product="visual_styling_story",
            product_specific_understanding=legacy.visible_styling_proposition,
            tradeoff=legacy.real_product_anchor,
            condition_of_validity=legacy.visual_dependency,
            supporting_fact_refs=legacy.source_fact_ids,
            source_packet_digest=legacy.source_packet_digest,
            relation_kind=legacy.relation_kind,
            resource_refs=legacy.resource_refs,
        )
    return None


def _build_p2_decision_basis_v2(
    products: Sequence[ProductFact],
) -> P2ProductDecisionBasisV2:
    """Derive a consumer decision, never a visible safety disclaimer."""

    if len(products) != 1:
        raise GenerationFailed("商品解释需要明确选择一件已确认商品。")
    product = products[0]
    packet = build_product_fact_packet((product,))
    facts_by_key = {item.fact_key: item for item in packet.facts}
    colors = _visible_values(product.facts.get("colors"))
    both_sides = product.facts.get("both_sides_complete") is True
    observable = _visible_string(product.facts.get("observable_features"))
    structure = _visible_string(product.facts.get("material_or_structure") or product.facts.get("material"))
    silhouette = _visible_string(product.facts.get("silhouette"))

    source_keys: tuple[str, ...]
    if both_sides and len(colors) >= 2:
        decision_axis: P2DecisionAxis = "complete_side_choice"
        source_keys = ("display_name", "colors", "both_sides_complete")
        understanding = "同一件商品以两种完整可见外观，提供商品内部的两面选择。"
        tradeoff = "同一时刻主要呈现其中一面，选择一面就会暂时放下另一面的视觉重点。"
        condition = "只有用户确实需要在两种完整外观之间选择或切换时，这项价值才成立。"
    elif observable and len(colors) >= 2:
        decision_axis = "confirmed_visible_difference"
        source_keys = ("display_name", "colors", "observable_features")
        understanding = "同一件商品的已确认可见特征与两种颜色，共同提供一个明确的视觉选择维度。"
        tradeoff = "先让一种颜色或可见特征成为判断重点，就会暂时把另一种可见重点放在次位。"
        condition = "只有本次选择确实取决于这些已确认的可见差异时，这项价值才成立。"
    elif len(colors) >= 2:
        decision_axis = "internal_color_relationship"
        source_keys = ("display_name", "colors")
        understanding = "这件商品的专属可见选择点，是资料中已确认的强对比颜色关系。"
        tradeoff = "本次选择是采用这组已确认强对比作为判断重点，或不采用这项依据。"
        condition = "只有用户本次确实要按已确认的强对比颜色关系作选择时，这项价值才成立。"
    elif structure and silhouette:
        decision_axis = "confirmed_structure_and_silhouette"
        structure_key = "material_or_structure" if "material_or_structure" in facts_by_key else "material"
        source_keys = ("display_name", structure_key, "silhouette")
        understanding = "同一件商品已确认的结构与轮廓，提供两个可以相互复核的选择维度。"
        tradeoff = "把结构作为主要判断时，轮廓会退到辅助位置；先看轮廓时，结构则用于复核。"
        condition = "只有本次选择确实同时需要核对结构与轮廓时，这项价值才成立。"
    else:
        raise GenerationFailed("这件商品的当前已确认信息还不足以形成商品专属理解、相伴取舍和成立条件。")

    supporting_fact_refs = tuple(facts_by_key[key].fact_id for key in source_keys if key in facts_by_key)
    if len(supporting_fact_refs) < 2:
        raise GenerationFailed("商品解释缺少可追踪的商品专属事实。")
    result = P2ProductDecisionBasisV2(
        contract_version=PRODUCT_DECISION_BASIS_VERSION,
        primary_product="product_truth",
        decision_axis=decision_axis,
        product_specific_understanding=understanding,
        tradeoff=tradeoff,
        condition_of_validity=condition,
        supporting_fact_refs=supporting_fact_refs,
        source_packet_digest=packet.packet_digest,
    )
    assert_product_decision_basis_v2(result)
    return result


def build_product_value_contract(
    *,
    primary_product: ContentProduct,
    products: Sequence[ProductFact],
    bound_product_media: Sequence[BoundProductMedia] = (),
    media_envelope: MediaCapabilityEnvelope | None = None,
    media_program: MediaProgramSelectionV1 | None = None,
) -> LegacyProductValueContract | None:
    if primary_product == "product_truth":
        return _build_p2_contract(products)
    if primary_product == "visual_styling_story":
        return _build_p5_contract(
            products,
            bound_product_media=bound_product_media,
            media_envelope=media_envelope,
            media_program=media_program,
        )
    return None


def product_value_contract_document(
    contract: ProductValueContract,
) -> dict[str, object]:
    common: dict[str, object] = {
        "contract_version": contract.contract_version,
        "primary_product": contract.primary_product,
        "source_packet_digest": contract.source_packet_digest,
    }
    if isinstance(
        contract,
        (P2ProductDecisionBasisV2, P5ProductDecisionBasisV2),
    ):
        result = common | {
            "product_specific_understanding": (contract.product_specific_understanding),
            "tradeoff": contract.tradeoff,
            "condition_of_validity": contract.condition_of_validity,
            "supporting_fact_refs": list(contract.supporting_fact_refs),
        }
        if isinstance(contract, P2ProductDecisionBasisV2):
            result["decision_axis"] = contract.decision_axis
        if isinstance(contract, P5ProductDecisionBasisV2):
            result.update(
                {
                    "relation_kind": contract.relation_kind,
                    "resource_refs": list(contract.resource_refs),
                }
            )
        return result
    common["source_fact_ids"] = list(contract.source_fact_ids)
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
    if version == PRODUCT_DECISION_BASIS_VERSION:
        primary_product = value.get("primary_product")
        fact_refs = _string_tuple(value.get("supporting_fact_refs"))
        packet_digest = _required_digest(value.get("source_packet_digest"))
        product_specific_understanding = _required_string(value.get("product_specific_understanding"))
        tradeoff = _required_string(value.get("tradeoff"))
        condition_of_validity = _required_string(value.get("condition_of_validity"))
        if primary_product == "product_truth":
            decision_axis = value.get("decision_axis")
            if decision_axis not in {
                "complete_side_choice",
                "confirmed_visible_difference",
                "internal_color_relationship",
                "confirmed_structure_and_silhouette",
            }:
                raise DomainError("内容任务冻结的商品选择维度无效")
            contract_v2: ProductDecisionBasisV2 = P2ProductDecisionBasisV2(
                contract_version=PRODUCT_DECISION_BASIS_VERSION,
                primary_product="product_truth",
                decision_axis=cast(P2DecisionAxis, decision_axis),
                product_specific_understanding=product_specific_understanding,
                tradeoff=tradeoff,
                condition_of_validity=condition_of_validity,
                supporting_fact_refs=fact_refs,
                source_packet_digest=packet_digest,
            )
        elif primary_product == "visual_styling_story":
            raw_resources = _string_tuple(value.get("resource_refs"))
            if len(raw_resources) != 2:
                raise DomainError("内容任务冻结的商品价值合同无效")
            relation_kind = value.get("relation_kind")
            if relation_kind not in {
                "color_hierarchy",
                "silhouette_hierarchy",
            }:
                raise DomainError("内容任务冻结的商品价值合同无效")
            contract_v2 = P5ProductDecisionBasisV2(
                contract_version=PRODUCT_DECISION_BASIS_VERSION,
                primary_product="visual_styling_story",
                product_specific_understanding=product_specific_understanding,
                tradeoff=tradeoff,
                condition_of_validity=condition_of_validity,
                supporting_fact_refs=fact_refs,
                source_packet_digest=packet_digest,
                relation_kind=cast(
                    Literal["color_hierarchy", "silhouette_hierarchy"],
                    relation_kind,
                ),
                resource_refs=(raw_resources[0], raw_resources[1]),
            )
        else:
            raise DomainError("内容任务冻结的商品价值合同无效")
        assert_product_decision_basis_v2(contract_v2)
        return contract_v2
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
            visible_styling_proposition=_required_string(value.get("visible_styling_proposition")),
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


def assert_product_decision_basis_v2(
    contract: ProductDecisionBasisV2,
) -> None:
    if (
        contract.contract_version != PRODUCT_DECISION_BASIS_VERSION
        or not contract.product_specific_understanding.strip()
        or not contract.tradeoff.strip()
        or not contract.condition_of_validity.strip()
        or not contract.supporting_fact_refs
        or len(contract.supporting_fact_refs) != len(set(contract.supporting_fact_refs))
        or len(contract.source_packet_digest) != 64
        or any(character not in "0123456789abcdef" for character in contract.source_packet_digest)
    ):
        raise DomainError("内容任务冻结的商品选择依据无效")
    if isinstance(contract, P5ProductDecisionBasisV2) and (
        len(contract.resource_refs) != 2 or len(set(contract.resource_refs)) != 2
    ):
        raise DomainError("内容任务冻结的商品选择资源无效")
    if isinstance(contract, P2ProductDecisionBasisV2) and contract.decision_axis not in {
        "complete_side_choice",
        "confirmed_visible_difference",
        "internal_color_relationship",
        "confirmed_structure_and_silhouette",
    }:
        raise DomainError("内容任务冻结的商品选择维度无效")


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
    structure = _visible_string(product.facts.get("material_or_structure") or product.facts.get("material"))
    silhouette = _visible_string(product.facts.get("silhouette"))
    observable = _visible_string(product.facts.get("observable_features"))
    source_keys: tuple[str, ...]
    if both_sides and len(colors) >= 2:
        source_keys = ("display_name", "colors", "both_sides_complete")
        insight = (
            f"{product.display_name}的{colors[0]}与{colors[1]}两面都以完整外观存在，"
            "带来的不是一个局部细节变化，而是同一件商品的两种完整可见选择。"
        )
        tradeoff = (
            "同一时刻对外主要呈现的仍是其中一面：选定一面，就会暂时放下另一面的视觉重点；双面也不能被说成两件商品。"
        )
        condition = (
            "只有你确实需要在这两种完整外观之间切换时，这项选择价值才成立；"
            "如果始终只会固定呈现其中一面，双面就不是决定因素。"
        )
    elif observable and len(colors) >= 2:
        source_keys = ("display_name", "colors", "observable_features")
        insight = (
            f"{colors[0]}和{colors[1]}不是两个零散色块；因为{product.display_name}的"
            f"“{observable}”，真正要选的是此刻先让哪一面成为整件商品的视觉重心。"
        )
        tradeoff = (
            f"先呈现{colors[0]}这一面时，{colors[1]}会暂时退到看不见的位置；换到"
            f"{colors[1]}这一面，也会暂时放下{colors[0]}的重点。一次只能让其中一套"
            "完整外观站在前面，但它仍是同一件商品。"
        )
        condition = (
            "如果你确实会在这两套完整外观之间切换，这种双面选择才有价值；如果始终只会呈现固定一面，它就不是决定因素。"
        )
    elif len(colors) >= 2:
        source_keys = ("display_name", "colors")
        insight = (
            f"{product.display_name}的{colors[0]}与{colors[1]}提供了不同的可见重心，"
            "选择应落在本次想让哪一种颜色先被看见。"
        )
        tradeoff = "先突出一种颜色，就会暂时放下另一种颜色的视觉重点；一次选择不能同时让两种颜色都成为主角。"
        condition = "只有本次选择确实依赖颜色差异时，这项价值才成立；如果颜色不是决定因素，这组差异就不必承担本次选择。"
    elif structure and silhouette:
        structure_key = "material_or_structure" if "material_or_structure" in facts_by_key else "material"
        source_keys = ("display_name", structure_key, "silhouette")
        insight = (
            f"{product.display_name}已确认的{structure}与{silhouette}"
            "可以放在同一个选择里解释，让结构信息和轮廓信息彼此校准，而不是各说一遍。"
        )
        tradeoff = "这项选择只能落在已确认的结构与轮廓关系上，不能由此推出材质手感、保暖、舒适、用途或上身效果。"
        condition = "当本次选择确实同时依赖这项结构和轮廓时，这个判断成立；如果问题依赖体验、性能或具体场景，就不成立。"
    elif observable:
        source_keys = ("display_name", "observable_features")
        insight = (
            f"{product.display_name}已确认的“{observable}”可以成为本次选择的观察支点，判断只围绕它具体怎样被看见展开。"
        )
        tradeoff = "选择这项可见特征作为依据，就不能再用它替代尚未确认的材质、性能、用途或穿着体验。"
        condition = "当本次问题直接依赖这项可见特征时，这个判断成立；如果决定因素在其他未确认信息上，就不成立。"
    elif structure:
        structure_key = "material_or_structure" if "material_or_structure" in facts_by_key else "material"
        source_keys = ("display_name", structure_key)
        insight = (
            f"{product.display_name}当前已确认的{structure}把本次判断"
            "限定在这一项具体结构信息上，而不是一份通用商品介绍。"
        )
        tradeoff = "以结构信息作选择依据，就不能同时把尚未确认的材质手感、性能、用途、舒适或上身效果当作结论。"
        condition = "当本次问题直接依赖这项结构信息时，这个判断成立；如果问题依赖体验或使用场景，就不成立。"
    elif silhouette:
        source_keys = ("display_name", "silhouette")
        insight = (
            f"{product.display_name}已确认的{silhouette}让本次判断可以"
            "聚焦轮廓本身怎样被看见，而不是借未确认属性补足意义。"
        )
        tradeoff = "以轮廓作选择依据，就不能同时把尚未确认的材质、性能、用途、舒适或上身效果当作结论。"
        condition = "当本次选择确实由这项轮廓决定时，这个判断成立；如果决定因素在其他未确认信息上，就不成立。"
    else:
        raise GenerationFailed("这件商品的当前已确认信息还不足以形成商品专属理解、相伴取舍和成立条件。")
    source_fact_ids = tuple(facts_by_key[key].fact_id for key in source_keys if key in facts_by_key)
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
    media_program: MediaProgramSelectionV1 | None,
) -> P5ProductValueContractV1:
    if len(products) != 2 or len(bound_product_media) != 2 or media_envelope is None:
        raise GenerationFailed("这条视觉内容需要两件不同商品、对应的登记素材和可见商品信息。")
    if len({item.product_id for item in bound_product_media}) != 2:
        raise GenerationFailed("这条视觉内容需要两件不同商品。")
    resources = tuple(
        resource for resource in media_envelope.resources if isinstance(resource, BoundProductMediaResourceV2)
    )
    if len(resources) != 2 or len({item.resource_id for item in resources}) != 2:
        raise GenerationFailed("这条视觉内容缺少两份冻结的登记商品素材。")
    resource_by_product = {resource.product_id: resource for resource in resources}
    resource_by_id = {resource.resource_id: resource for resource in resources}
    media_by_product = {str(item.product_id): item for item in bound_product_media}
    if set(resource_by_product) != set(media_by_product):
        raise GenerationFailed("登记商品素材与当前商品关系不一致。")
    if (
        media_program is None
        or not media_program.primary_resource_id
        or not media_program.secondary_resource_id
        or media_program.primary_resource_id not in resource_by_id
        or media_program.secondary_resource_id not in resource_by_id
        or media_program.primary_resource_id == media_program.secondary_resource_id
    ):
        raise GenerationFailed("这条视觉内容缺少本次明确的主视觉与辅助视觉选择。")
    ordered_resources = (
        resource_by_id[media_program.primary_resource_id],
        resource_by_id[media_program.secondary_resource_id],
    )
    ordered_media = tuple(media_by_product[resource.product_id] for resource in ordered_resources)
    ordered_products = tuple(item.product for item in ordered_media)
    packets = tuple(build_product_fact_packet((product,)) for product in ordered_products)
    source_fact_ids: list[str] = []
    colors = tuple(_visible_values(product.facts.get("colors")) for product in ordered_products)
    color_pair = _distinct_pair(colors[0], colors[1])
    relation_kind: Literal["color_hierarchy", "silhouette_hierarchy"]
    if color_pair is not None:
        relation_kind = "color_hierarchy"
        for packet in packets:
            source_fact_ids.extend(item.fact_id for item in packet.facts if item.fact_key in {"display_name", "colors"})
        proposition = (
            f"让{ordered_products[0].display_name}的已确认{color_pair[0]}先成为画面主色，"
            f"再让{ordered_products[1].display_name}的已确认{color_pair[1]}在侧边回应；"
            "主色先定调，回应色再把两件商品的关系拉开。"
        )
        dependency = "两份图片都要清楚呈现各自已确认的颜色；只要其中一种颜色在图片里看不清，这组主辅关系就不成立。"
    else:
        silhouettes = tuple(_visible_string(product.facts.get("silhouette")) for product in ordered_products)
        if not silhouettes[0] or not silhouettes[1] or silhouettes[0] == silhouettes[1]:
            raise GenerationFailed("这两件商品的当前资料还不足以形成具体造型关系；请补充不同的已确认颜色或轮廓信息。")
        relation_kind = "silhouette_hierarchy"
        for packet in packets:
            source_fact_ids.extend(
                item.fact_id for item in packet.facts if item.fact_key in {"display_name", "silhouette"}
            )
        proposition = (
            f"让{ordered_products[0].display_name}的已确认{silhouettes[0]}先成为画面主体，"
            f"再让{ordered_products[1].display_name}的已确认{silhouettes[1]}在侧边回应；"
            "主体先定形，回应轮廓再把两件商品的关系拉开。"
        )
        dependency = "两份图片都要清楚呈现各自已确认的轮廓；只要其中一个轮廓在图片里看不清，这组主辅关系就不成立。"
    packet_digest = hashlib.sha256(":".join(packet.packet_digest for packet in packets).encode()).hexdigest()
    resource_refs = tuple(resource.resource_id for resource in ordered_resources)
    return P5ProductValueContractV1(
        contract_version=PRODUCT_VALUE_CONTRACT_VERSION,
        primary_product="visual_styling_story",
        real_product_anchor=("这组画面只使用你这次选定的两件商品素材，两件商品各有自己的视觉位置。"),
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
    return tuple(text for item in value if (text := _visible_string(item)))


def _visible_string(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _distinct_pair(
    first: tuple[str, ...],
    second: tuple[str, ...],
) -> tuple[str, str] | None:
    return next(
        ((left, right) for left in first for right in second if left != right),
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
