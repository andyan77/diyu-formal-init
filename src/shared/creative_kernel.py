from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Literal, TypeAlias, cast

from src.shared.errors import DomainError
from src.shared.factual_basis import FrozenFactRecord, ImmutableFactBlock
from src.shared.narrative import (
    NarrativeFrame,
    NarrativeIssue,
    ObservationType,
    ReviewerObservation,
)
from src.shared.types import ContentProduct
from src.shared.visible_structure import assert_writer_visible_text_safe

KernelPurpose: TypeAlias = Literal[
    "title",
    "natural_guide",
    "frozen_fact",
    "body",
    "media_opening",
    "media_sequence",
    "subtitle_strategy",
    "production_note",
    "release_caption",
]
KernelProgramId: TypeAlias = Literal[
    "observation_only_v1",
    "observation_with_hypothetical_example_v1",
    "observation_with_hypothetical_example_v2",
    "actuality_with_disclosed_dramatization_v1",
]
UnitTrack: TypeAlias = Literal["trusted_fact", "creative_expression"]
UnitMode: TypeAlias = Literal[
    "trusted_fact",
    "general_observation",
    "recommendation",
    "hypothesis",
    "disclosed_dramatization",
]
UnitTextSource: TypeAlias = Literal[
    "writer",
    "server_fact",
    "server_compiler",
    "prior_version",
]

LEGACY_KERNEL_VERSION = "creative-kernel-v1"
DUAL_TRACK_KERNEL_VERSION = "creative-kernel-v2"
KERNEL_VERSION = "creative-kernel-v3"
MAX_PRODUCT_FACT_BLOCKS = 3
DRAMATIZATION_DISCLOSURE = "以下是情景演绎，不对应真实人物或经历："
HYPOTHESIS_DISCLOSURE = "假设有这样一幕："
OBSERVATION_ONLY_PROGRAM: KernelProgramId = "observation_only_v1"
OBSERVATION_WITH_HYPOTHETICAL_EXAMPLE_PROGRAM: KernelProgramId = "observation_with_hypothetical_example_v1"
OBSERVATION_WITH_HYPOTHETICAL_EXAMPLE_PROGRAM_V2: KernelProgramId = "observation_with_hypothetical_example_v2"
ACTUALITY_WITH_DISCLOSED_DRAMATIZATION_PROGRAM: KernelProgramId = "actuality_with_disclosed_dramatization_v1"
_PROGRAM_IDS = frozenset(
    {
        OBSERVATION_ONLY_PROGRAM,
        OBSERVATION_WITH_HYPOTHETICAL_EXAMPLE_PROGRAM,
        OBSERVATION_WITH_HYPOTHETICAL_EXAMPLE_PROGRAM_V2,
        ACTUALITY_WITH_DISCLOSED_DRAMATIZATION_PROGRAM,
    }
)
_PURPOSES = frozenset(
    {
        "title",
        "natural_guide",
        "frozen_fact",
        "body",
        "media_opening",
        "media_sequence",
        "subtitle_strategy",
        "production_note",
        "release_caption",
    }
)
_OBSERVATION_TYPES = frozenset(
    {
        "abstract_principle",
        "situated_event",
        "institutional_assertion",
        "user_actuality",
        "hypothesis",
        "dramatization",
        "confirmed_fact",
        "uncertain",
    }
)
COMPILER_GUIDANCE_VERSION = "compiler-guidance-v1"
_COMPILER_OWNED_UNIT_TEXTS: dict[
    ContentProduct,
    dict[str, tuple[str, str]],
] = {
    "dressing_decision": {
        "unit:natural-guide": (
            "从自己的优先项出发，看看这次选择真正需要保留什么。",
            "phrase:compiler-guide-dressing-v1",
        ),
        "unit:release-caption": (
            "这次选择里，你最看重什么？",
            "phrase:compiler-release-dressing-v1",
        ),
    },
    "product_truth": {
        "unit:natural-guide": (
            "先看已经确认的信息，再保留自己的判断。",
            "phrase:compiler-guide-product-v1",
        ),
        "unit:release-caption": (
            "这些已知信息里，你最看重哪一项？",
            "phrase:compiler-release-product-v1",
        ),
    },
    "brand_life_narrative": {
        "unit:natural-guide": (
            "沿着正文主线，看看这次表达想保留什么。",
            "phrase:compiler-guide-narrative-v1",
        ),
        "unit:release-caption": (
            "你更愿意带走哪一种理解？",
            "phrase:compiler-release-narrative-v1",
        ),
    },
    "local_response": {
        "unit:natural-guide": (
            "沿着正文主线，看看这次回应的重点。",
            "phrase:compiler-guide-response-v1",
        ),
        "unit:release-caption": (
            "你更认同哪一种回应方式？",
            "phrase:compiler-release-response-v1",
        ),
    },
    "visual_styling_story": {
        "unit:natural-guide": (
            "先看已经确认的内容，再保留自己的搭配判断。",
            "phrase:compiler-guide-styling-v1",
        ),
        "unit:release-caption": (
            "你更看重哪一种呈现重点？",
            "phrase:compiler-release-styling-v1",
        ),
    },
}


def compiler_owned_unit_texts(
    primary_product: ContentProduct,
) -> dict[str, str]:
    """Return versioned neutral fields owned by DeliveryCompiler."""
    return {
        unit_id: text_and_source[0] for unit_id, text_and_source in _COMPILER_OWNED_UNIT_TEXTS[primary_product].items()
    }


def compiler_owned_unit_source(
    unit_id: str,
    text: str,
) -> str | None:
    """Resolve an exact compiler phrase without trusting model authorship."""
    matches = {
        text_and_source[1]
        for values in _COMPILER_OWNED_UNIT_TEXTS.values()
        for candidate_id, text_and_source in values.items()
        if candidate_id == unit_id and text_and_source[0] == text
    }
    if len(matches) != 1:
        return None
    return next(iter(matches))


@dataclass(frozen=True)
class CreativeKernelUnit:
    unit_id: str
    purpose: KernelPurpose
    allowed_observation_types: tuple[ObservationType, ...]
    fact_refs: tuple[str, ...]
    constraint_refs: tuple[str, ...]
    visible_order: int
    text: str
    claim_refs: tuple[str, ...] = ()
    track: UnitTrack = "creative_expression"
    mode: UnitMode = "general_observation"
    scope_id: str = "scope:general-observation-v1"
    allowed_resource_ids: tuple[str, ...] = ()
    text_source: UnitTextSource = "writer"

    @property
    def writable(self) -> bool:
        return self.text_source == "writer"


@dataclass(frozen=True)
class CreativeKernelV1:
    kernel_version: str
    units: tuple[CreativeKernelUnit, ...]
    program_id: KernelProgramId = OBSERVATION_ONLY_PROGRAM
    selected_fact_block_ids: tuple[str, ...] = ()

    @property
    def writable_units(self) -> tuple[CreativeKernelUnit, ...]:
        return tuple(unit for unit in self.units if unit.writable)

    def unit(self, unit_id: str) -> CreativeKernelUnit:
        for unit in self.units:
            if unit.unit_id == unit_id:
                return unit
        raise KeyError(unit_id)


def build_kernel_skeleton(
    *,
    frame: NarrativeFrame,
    fact_registry: Sequence[FrozenFactRecord],
    constraint_refs: Sequence[str],
    program_id: KernelProgramId = OBSERVATION_ONLY_PROGRAM,
    allowed_resource_ids: Sequence[str] = (),
    media_format: Literal["video", "graphic"] = "graphic",
    kernel_version: str = DUAL_TRACK_KERNEL_VERSION,
    primary_product: ContentProduct | None = None,
) -> CreativeKernelV1:
    """Build the one small server-owned writing skeleton for a new artifact."""
    if (
        program_id
        in {
            OBSERVATION_WITH_HYPOTHETICAL_EXAMPLE_PROGRAM,
            OBSERVATION_WITH_HYPOTHETICAL_EXAMPLE_PROGRAM_V2,
        }
        and frame.narrative_mode != "general_observation"
    ):
        raise ValueError("hypothetical example program requires general observation")
    if program_id == ACTUALITY_WITH_DISCLOSED_DRAMATIZATION_PROGRAM and frame.narrative_mode != "actuality_reflection":
        raise ValueError("local dramatization program requires actuality reflection")
    body_types: tuple[ObservationType, ...]
    product_recommendation_body = kernel_version == KERNEL_VERSION and primary_product in {
        "dressing_decision",
        "product_truth",
        "local_response",
        "visual_styling_story",
    }
    product_hypothesis_body = (
        kernel_version == KERNEL_VERSION
        and primary_product == "brand_life_narrative"
        and frame.narrative_mode == "actuality_reflection"
    )
    uses_hypothesis_body = frame.narrative_mode == "hypothesis" or product_hypothesis_body
    if uses_hypothesis_body:
        body_types = ("hypothesis",)
    elif frame.narrative_mode == "dramatization":
        body_types = ("dramatization",)
    else:
        body_types = ("abstract_principle",)
    constraints = tuple(dict.fromkeys(constraint_refs))
    resources = tuple(dict.fromkeys(allowed_resource_ids))
    expression_resources = (
        resources
        if kernel_version == KERNEL_VERSION and primary_product == "visual_styling_story"
        else tuple(resource_id for resource_id in resources if not resource_id.startswith("resource:product:"))
    )
    if kernel_version not in {DUAL_TRACK_KERNEL_VERSION, KERNEL_VERSION}:
        raise ValueError("unsupported creative kernel version")
    compiler_owned_supporting_copy = kernel_version == DUAL_TRACK_KERNEL_VERSION
    units: list[CreativeKernelUnit] = [
        CreativeKernelUnit(
            unit_id="unit:title",
            purpose="title",
            allowed_observation_types=("abstract_principle",),
            fact_refs=(),
            constraint_refs=constraints,
            visible_order=10,
            text="",
            track="creative_expression",
            mode="general_observation",
            scope_id="scope:general-observation-v1",
            allowed_resource_ids=expression_resources,
        ),
        CreativeKernelUnit(
            unit_id="unit:natural-guide",
            purpose="natural_guide",
            allowed_observation_types=("abstract_principle",),
            fact_refs=(),
            constraint_refs=constraints,
            visible_order=20,
            text="",
            track="creative_expression",
            mode="general_observation",
            scope_id="scope:general-observation-v1",
            allowed_resource_ids=expression_resources,
            text_source=("server_compiler" if compiler_owned_supporting_copy else "writer"),
        ),
    ]
    if not compiler_owned_supporting_copy:
        units.extend(
            (
                CreativeKernelUnit(
                    unit_id="unit:media-opening",
                    purpose="media_opening",
                    allowed_observation_types=("abstract_principle",),
                    fact_refs=(),
                    constraint_refs=constraints,
                    visible_order=21,
                    text="",
                    track="creative_expression",
                    mode="general_observation",
                    scope_id="scope:general-observation-v1",
                    allowed_resource_ids=resources,
                ),
                CreativeKernelUnit(
                    unit_id="unit:media-sequence",
                    purpose="media_sequence",
                    allowed_observation_types=("abstract_principle",),
                    fact_refs=(),
                    constraint_refs=constraints,
                    visible_order=22,
                    text="",
                    track="creative_expression",
                    mode="general_observation",
                    scope_id="scope:general-observation-v1",
                    allowed_resource_ids=resources,
                ),
                CreativeKernelUnit(
                    unit_id="unit:production-note",
                    purpose="production_note",
                    allowed_observation_types=("abstract_principle",),
                    fact_refs=(),
                    constraint_refs=constraints,
                    visible_order=23,
                    text="",
                    track="creative_expression",
                    mode="general_observation",
                    scope_id="scope:general-observation-v1",
                    allowed_resource_ids=resources,
                ),
            )
        )
        if media_format == "video":
            units.append(
                CreativeKernelUnit(
                    unit_id="unit:subtitle-strategy",
                    purpose="subtitle_strategy",
                    allowed_observation_types=("abstract_principle",),
                    fact_refs=(),
                    constraint_refs=constraints,
                    visible_order=24,
                    text="",
                    track="creative_expression",
                    mode="general_observation",
                    scope_id="scope:general-observation-v1",
                    allowed_resource_ids=expression_resources,
                )
            )
    allowed_fact_ids = frame.allowed_fact_ids
    frozen_records = tuple(record for record in fact_registry if record.fact_id in allowed_fact_ids)
    for index, record in enumerate(frozen_records, start=1):
        observation_type: ObservationType
        if record.fact_kind == "user_actuality":
            observation_type = "user_actuality"
        elif record.fact_kind == "brand":
            observation_type = "institutional_assertion"
        else:
            observation_type = "confirmed_fact"
        units.append(
            CreativeKernelUnit(
                unit_id=f"unit:frozen-fact:{index}",
                purpose="frozen_fact",
                allowed_observation_types=(observation_type,),
                fact_refs=(record.fact_id,),
                constraint_refs=(),
                visible_order=30 + index,
                text=record.exact_text,
                track="trusted_fact",
                mode="trusted_fact",
                scope_id=f"scope:trusted-{record.fact_kind}-v1",
                text_source="server_fact",
            )
        )
    if program_id in {
        OBSERVATION_WITH_HYPOTHETICAL_EXAMPLE_PROGRAM,
        OBSERVATION_WITH_HYPOTHETICAL_EXAMPLE_PROGRAM_V2,
    }:
        units.extend(
            (
                CreativeKernelUnit(
                    unit_id="unit:body-opening",
                    purpose="body",
                    allowed_observation_types=("abstract_principle",),
                    fact_refs=(),
                    constraint_refs=constraints,
                    visible_order=90,
                    text="",
                    track="creative_expression",
                    mode="general_observation",
                    scope_id="scope:general-observation-v1",
                    allowed_resource_ids=expression_resources,
                ),
                CreativeKernelUnit(
                    unit_id="unit:hypothetical-example",
                    purpose="body",
                    allowed_observation_types=("hypothesis",),
                    fact_refs=(),
                    constraint_refs=constraints,
                    visible_order=100,
                    text="",
                    track="creative_expression",
                    mode="hypothesis",
                    scope_id="scope:hypothesis-v1",
                    allowed_resource_ids=expression_resources,
                ),
                CreativeKernelUnit(
                    unit_id="unit:body-closing",
                    purpose="body",
                    allowed_observation_types=("abstract_principle",),
                    fact_refs=(),
                    constraint_refs=constraints,
                    visible_order=110,
                    text="",
                    track="creative_expression",
                    mode="general_observation",
                    scope_id="scope:general-observation-v1",
                    allowed_resource_ids=expression_resources,
                ),
            )
        )
        release_order = 120
    elif program_id == ACTUALITY_WITH_DISCLOSED_DRAMATIZATION_PROGRAM:
        units.extend(
            (
                CreativeKernelUnit(
                    unit_id="unit:body",
                    purpose="body",
                    allowed_observation_types=("abstract_principle",),
                    fact_refs=(),
                    constraint_refs=constraints,
                    visible_order=100,
                    text="",
                    track="creative_expression",
                    mode="general_observation",
                    scope_id="scope:general-observation-v1",
                    allowed_resource_ids=expression_resources,
                ),
                CreativeKernelUnit(
                    unit_id="unit:local-dramatization",
                    purpose="body",
                    allowed_observation_types=("dramatization",),
                    fact_refs=(),
                    constraint_refs=constraints,
                    visible_order=110,
                    text="",
                    track="creative_expression",
                    mode="disclosed_dramatization",
                    scope_id="scope:disclosed-dramatization-v1",
                    allowed_resource_ids=expression_resources,
                ),
            )
        )
        release_order = 120
    else:
        body_mode: UnitMode
        body_scope: str
        if uses_hypothesis_body:
            body_mode = "hypothesis"
            body_scope = "scope:hypothesis-v1"
        elif product_recommendation_body:
            body_mode = "recommendation"
            body_scope = "scope:recommendation-v1"
        elif frame.narrative_mode == "dramatization":
            body_mode = "disclosed_dramatization"
            body_scope = "scope:disclosed-dramatization-v1"
        else:
            body_mode = "general_observation"
            body_scope = "scope:general-observation-v1"
        units.append(
            CreativeKernelUnit(
                unit_id="unit:body",
                purpose="body",
                allowed_observation_types=body_types,
                fact_refs=(),
                constraint_refs=constraints,
                visible_order=100,
                text="",
                track="creative_expression",
                mode=body_mode,
                scope_id=body_scope,
                allowed_resource_ids=expression_resources,
            )
        )
        release_order = 110
    units.append(
        CreativeKernelUnit(
            unit_id="unit:release-caption",
            purpose="release_caption",
            allowed_observation_types=("abstract_principle",),
            fact_refs=(),
            constraint_refs=constraints,
            visible_order=release_order,
            text="",
            track="creative_expression",
            mode="general_observation",
            scope_id="scope:general-observation-v1",
            allowed_resource_ids=expression_resources,
            text_source=("server_compiler" if compiler_owned_supporting_copy else "writer"),
        )
    )
    return CreativeKernelV1(
        kernel_version=kernel_version,
        units=tuple(sorted(units, key=lambda unit: unit.visible_order)),
        program_id=program_id,
    )


def select_kernel_program(
    *,
    frame: NarrativeFrame,
    prior_kernel: CreativeKernelV1 | None = None,
    revision_instruction: str | None = None,
) -> KernelProgramId:
    """Choose one bounded program from trusted frozen context.

    Revisions and recompiles retain their original program.  A new general
    observation without any frozen actuality, product or brand fact receives
    one explicitly scoped hypothetical example; fact-bearing and explicitly
    hypothetical/dramatized work keeps the existing single-body program.
    """
    if (
        prior_kernel is not None
        and frame.narrative_mode == "actuality_reflection"
        and _requests_local_dramatization(revision_instruction)
    ):
        return ACTUALITY_WITH_DISCLOSED_DRAMATIZATION_PROGRAM
    if prior_kernel is not None:
        return prior_kernel.program_id
    if frame.narrative_mode == "general_observation" and not frame.allowed_fact_ids:
        return OBSERVATION_WITH_HYPOTHETICAL_EXAMPLE_PROGRAM_V2
    return OBSERVATION_ONLY_PROGRAM


def freeze_prior_revision_units(
    skeleton: CreativeKernelV1,
    prior_kernel: CreativeKernelV1 | None,
) -> CreativeKernelV1:
    """Carry a prior reflection as server-owned text when adding local drama."""
    if skeleton.program_id != ACTUALITY_WITH_DISCLOSED_DRAMATIZATION_PROGRAM:
        return skeleton
    if prior_kernel is None:
        raise ValueError("local dramatization revision requires a prior kernel")
    try:
        prior_reflection = prior_kernel.unit("unit:body")
    except KeyError as exc:
        raise ValueError("prior reflection unit is unavailable") from exc
    if (
        prior_reflection.track != "creative_expression"
        or prior_reflection.mode
        not in {
            "general_observation",
            "recommendation",
            "hypothesis",
        }
        or not prior_reflection.text
    ):
        raise ValueError("prior reflection unit cannot be frozen")
    return replace(
        skeleton,
        units=tuple(
            (
                replace(
                    unit,
                    text=prior_reflection.text,
                    claim_refs=prior_reflection.claim_refs,
                    text_source="prior_version",
                )
                if unit.unit_id == "unit:body"
                else unit
            )
            for unit in skeleton.units
        ),
    )


def parse_writer_kernel(
    raw: object,
    skeleton: CreativeKernelV1,
    *,
    fact_blocks: Sequence[ImmutableFactBlock] = (),
    allowed_claim_ids: frozenset[str] = frozenset(),
    require_claim_refs: bool = False,
    required_fact_block_ids: tuple[str, ...] | None = None,
    compiler_owned_text_by_id: Mapping[str, str] | None = None,
) -> CreativeKernelV1:
    product_contract = bool(fact_blocks)
    server_selected_product_facts = product_contract and bool(skeleton.selected_fact_block_ids)
    expected_root = (
        frozenset({"units", "fact_block_refs"})
        if product_contract and not server_selected_product_facts
        else frozenset({"units"})
    )
    if not isinstance(raw, Mapping) or frozenset(raw) != expected_root:
        raise TypeError("writer returned fields outside the kernel contract")
    selected_fact_block_ids = skeleton.selected_fact_block_ids
    if product_contract and not server_selected_product_facts:
        raw_block_refs = raw.get("fact_block_refs")
        if not isinstance(raw_block_refs, list) or not raw_block_refs:
            raise TypeError("writer must select immutable fact blocks")
        if any(not isinstance(value, str) or not value for value in raw_block_refs) or len(raw_block_refs) != len(
            set(raw_block_refs)
        ):
            raise ValueError("writer fact block refs are invalid")
        selected_fact_block_ids = tuple(cast(list[str], raw_block_refs))
        if len(selected_fact_block_ids) > MAX_PRODUCT_FACT_BLOCKS:
            raise ValueError("writer selected too many immutable fact blocks")
        available_block_ids = {block.fact_block_id for block in fact_blocks}
        if any(block_id not in available_block_ids for block_id in selected_fact_block_ids):
            raise ValueError("writer invented an immutable fact block")
        if required_fact_block_ids is not None and selected_fact_block_ids != required_fact_block_ids:
            raise ValueError("revision changed immutable fact blocks")
    elif product_contract:
        available_block_ids = {block.fact_block_id for block in fact_blocks}
        if len(selected_fact_block_ids) > MAX_PRODUCT_FACT_BLOCKS or any(
            block_id not in available_block_ids for block_id in selected_fact_block_ids
        ):
            raise ValueError("service-selected immutable fact blocks are invalid")
        if required_fact_block_ids is not None and selected_fact_block_ids != required_fact_block_ids:
            raise ValueError("revision changed immutable fact blocks")
    raw_units = raw.get("units")
    if not isinstance(raw_units, list) or not raw_units:
        raise TypeError("writer units are incomplete")
    compiler_texts = dict(compiler_owned_text_by_id or {})
    unit_by_id = {unit.unit_id: unit for unit in skeleton.units}
    writable_by_id = {unit.unit_id: unit for unit in skeleton.writable_units}
    compiler_ids = set(compiler_texts)
    legacy_compiler_ids = {
        "unit:natural-guide",
        "unit:release-caption",
    }
    invalid_compiler_contract = any(
        unit_id not in unit_by_id or not isinstance(text, str) or not text.strip()
        for unit_id, text in compiler_texts.items()
    )
    if skeleton.kernel_version == DUAL_TRACK_KERNEL_VERSION:
        invalid_compiler_contract = (
            invalid_compiler_contract
            or compiler_ids not in (set(), legacy_compiler_ids)
            or any(
                unit_by_id[unit_id].text_source != "server_compiler"
                or compiler_owned_unit_source(unit_id, text) is None
                for unit_id, text in compiler_texts.items()
            )
        )
    elif skeleton.kernel_version == KERNEL_VERSION:
        invalid_compiler_contract = (
            invalid_compiler_contract
            or bool(compiler_ids)
        )
    if invalid_compiler_contract:
        raise ValueError("compiler-owned unit contract is invalid")
    expected = {unit_id: unit for unit_id, unit in writable_by_id.items() if unit_id not in compiler_ids}
    returned_ids = [value.get("unit_id") for value in raw_units if isinstance(value, Mapping)]
    if (
        len(returned_ids) != len(raw_units)
        or len(returned_ids) != len(set(returned_ids))
        or set(returned_ids) != set(expected)
    ):
        raise ValueError("writer unit coverage drifted from server skeleton")
    replacements: dict[str, CreativeKernelUnit] = {
        unit_id: replace(
            unit_by_id[unit_id],
            text=text,
            text_source="server_compiler",
        )
        for unit_id, text in compiler_texts.items()
    }
    unit_fields = (
        frozenset({"unit_id", "text", "claim_refs"})
        if (product_contract and not server_selected_product_facts) or require_claim_refs
        else frozenset({"unit_id", "text"})
    )
    for raw_unit in raw_units:
        if not isinstance(raw_unit, Mapping) or frozenset(raw_unit) != unit_fields:
            message = (
                "writer creative unit fields are invalid"
                if (product_contract and not server_selected_product_facts) or require_claim_refs
                else "writer units may contain only unit_id and text"
            )
            raise TypeError(message)
        unit_id = _required_string(raw_unit.get("unit_id"))
        claim_refs = _string_tuple(raw_unit.get("claim_refs")) if "claim_refs" in unit_fields else ()
        if any(ref not in allowed_claim_ids for ref in claim_refs):
            raise ValueError("writer claim ref is outside ProductFactPacket")
        replacements[unit_id] = replace(
            expected[unit_id],
            text=_normalize_writer_visible_text(_required_string(raw_unit.get("text"))),
            claim_refs=claim_refs,
        )
    units = tuple(replacements.get(unit.unit_id, unit) for unit in skeleton.units)
    if product_contract:
        block_by_id = {block.fact_block_id: block for block in fact_blocks}
        product_fact_ids = frozenset(block.fact_id for block in fact_blocks)
        product_unit_by_fact_id = {
            unit.fact_refs[0]: unit
            for unit in skeleton.units
            if unit.purpose == "frozen_fact" and len(unit.fact_refs) == 1 and unit.fact_refs[0] in product_fact_ids
        }
        selected_product_units = tuple(
            product_unit_by_fact_id[block_by_id[block_id].fact_id] for block_id in selected_fact_block_ids
        )
        if len(selected_product_units) != len(selected_fact_block_ids):
            raise ValueError("immutable fact block cannot resolve to skeleton")
        other_fact_units = tuple(
            unit
            for unit in units
            if unit.purpose == "frozen_fact" and (len(unit.fact_refs) != 1 or unit.fact_refs[0] not in product_fact_ids)
        )
        reordered_facts = tuple(
            replace(
                unit,
                unit_id=f"unit:frozen-fact:{index}",
                visible_order=30 + index,
            )
            for index, unit in enumerate(
                (*other_fact_units, *selected_product_units),
                start=1,
            )
        )
        units = (
            *(unit for unit in units if unit.purpose != "frozen_fact"),
            *reordered_facts,
        )
    return CreativeKernelV1(
        kernel_version=skeleton.kernel_version,
        units=tuple(sorted(units, key=lambda unit: unit.visible_order)),
        program_id=skeleton.program_id,
        selected_fact_block_ids=selected_fact_block_ids,
    )


def repair_kernel_units(
    *,
    kernel: CreativeKernelV1,
    affected_unit_ids: frozenset[str],
    raw: object,
    allowed_claim_ids: frozenset[str] = frozenset(),
) -> CreativeKernelV1:
    if not affected_unit_ids:
        raise ValueError("repair has no affected writable units")
    if any(not kernel.unit(unit_id).writable for unit_id in affected_unit_ids):
        raise ValueError("service-authored fact units cannot be repaired")
    repair_skeleton = CreativeKernelV1(
        kernel_version=kernel.kernel_version,
        units=tuple(replace(unit, text="") for unit in kernel.units if unit.unit_id in affected_unit_ids),
        program_id=kernel.program_id,
        selected_fact_block_ids=kernel.selected_fact_block_ids,
    )
    repaired = parse_writer_kernel(
        raw,
        repair_skeleton,
        allowed_claim_ids=allowed_claim_ids,
        require_claim_refs=bool(allowed_claim_ids),
    )
    replacements = {unit.unit_id: unit for unit in repaired.units}
    if any(replacements[unit_id].text == kernel.unit(unit_id).text for unit_id in affected_unit_ids):
        raise ValueError("repair did not change every affected unit")
    return CreativeKernelV1(
        kernel_version=kernel.kernel_version,
        units=tuple(replacements.get(unit.unit_id, unit) for unit in kernel.units),
        program_id=kernel.program_id,
        selected_fact_block_ids=kernel.selected_fact_block_ids,
    )


def kernel_document(kernel: CreativeKernelV1) -> dict[str, object]:
    return {
        "kernel_version": kernel.kernel_version,
        "program_id": kernel.program_id,
        "selected_fact_block_ids": list(kernel.selected_fact_block_ids),
        "units": [
            {
                "unit_id": unit.unit_id,
                "purpose": unit.purpose,
                "allowed_observation_types": list(unit.allowed_observation_types),
                "fact_refs": list(unit.fact_refs),
                "constraint_refs": list(unit.constraint_refs),
                "visible_order": unit.visible_order,
                "text": unit.text,
                "claim_refs": list(unit.claim_refs),
                "track": unit.track,
                "mode": unit.mode,
                "scope_id": unit.scope_id,
                "allowed_resource_ids": list(unit.allowed_resource_ids),
                "text_source": unit.text_source,
            }
            for unit in kernel.units
        ],
    }


def kernel_from_document(value: object) -> CreativeKernelV1:
    if not isinstance(value, Mapping) or frozenset(value) not in {
        frozenset({"kernel_version", "units"}),
        frozenset({"kernel_version", "program_id", "units"}),
        frozenset(
            {
                "kernel_version",
                "selected_fact_block_ids",
                "units",
            }
        ),
        frozenset(
            {
                "kernel_version",
                "program_id",
                "selected_fact_block_ids",
                "units",
            }
        ),
    }:
        raise DomainError("冻结创作内核结构无效")
    raw_units = value.get("units")
    raw_program = value.get("program_id", OBSERVATION_ONLY_PROGRAM)
    selected_fact_block_ids = _string_tuple(value.get("selected_fact_block_ids", []))
    if (
        value.get("kernel_version")
        not in {
            LEGACY_KERNEL_VERSION,
            DUAL_TRACK_KERNEL_VERSION,
            KERNEL_VERSION,
        }
        or not isinstance(raw_units, list)
        or not isinstance(raw_program, str)
        or raw_program not in _PROGRAM_IDS
    ):
        raise DomainError("冻结创作内核版本无效")
    units: list[CreativeKernelUnit] = []
    for raw in raw_units:
        if not isinstance(raw, Mapping) or frozenset(raw) not in {
            frozenset(
                {
                    "unit_id",
                    "purpose",
                    "allowed_observation_types",
                    "fact_refs",
                    "constraint_refs",
                    "visible_order",
                    "text",
                }
            ),
            frozenset(
                {
                    "unit_id",
                    "purpose",
                    "allowed_observation_types",
                    "fact_refs",
                    "constraint_refs",
                    "visible_order",
                    "text",
                    "claim_refs",
                }
            ),
            frozenset(
                {
                    "unit_id",
                    "purpose",
                    "allowed_observation_types",
                    "fact_refs",
                    "constraint_refs",
                    "visible_order",
                    "text",
                    "claim_refs",
                    "track",
                    "mode",
                    "scope_id",
                    "allowed_resource_ids",
                }
            ),
            frozenset(
                {
                    "unit_id",
                    "purpose",
                    "allowed_observation_types",
                    "fact_refs",
                    "constraint_refs",
                    "visible_order",
                    "text",
                    "claim_refs",
                    "track",
                    "mode",
                    "scope_id",
                    "allowed_resource_ids",
                    "text_source",
                }
            ),
        }:
            raise DomainError("冻结创作内核单元无效")
        purpose = raw.get("purpose")
        allowed = _string_tuple(raw.get("allowed_observation_types"))
        order = raw.get("visible_order")
        if (
            not isinstance(purpose, str)
            or purpose not in _PURPOSES
            or not allowed
            or any(item not in _OBSERVATION_TYPES for item in allowed)
            or not isinstance(order, int)
        ):
            raise DomainError("冻结创作内核单元字段无效")
        track, mode, scope_id = _unit_track_contract(
            purpose=cast(KernelPurpose, purpose),
            allowed=cast(tuple[ObservationType, ...], allowed),
            raw=raw,
        )
        text_source = _unit_text_source(
            purpose=cast(KernelPurpose, purpose),
            raw=raw,
            kernel_version=str(value.get("kernel_version")),
        )
        raw_text = raw.get("text")
        text = "" if text_source == "server_compiler" and raw_text == "" else _required_string(raw_text)
        units.append(
            CreativeKernelUnit(
                unit_id=_required_string(raw.get("unit_id")),
                purpose=cast(KernelPurpose, purpose),
                allowed_observation_types=cast(tuple[ObservationType, ...], allowed),
                fact_refs=_string_tuple(raw.get("fact_refs")),
                constraint_refs=_string_tuple(raw.get("constraint_refs")),
                visible_order=order,
                text=text,
                claim_refs=_string_tuple(raw.get("claim_refs", [])),
                track=track,
                mode=mode,
                scope_id=scope_id,
                allowed_resource_ids=_string_tuple(raw.get("allowed_resource_ids", [])),
                text_source=text_source,
            )
        )
    identifiers = [unit.unit_id for unit in units]
    orders = [unit.visible_order for unit in units]
    if (
        not units
        or len(identifiers) != len(set(identifiers))
        or len(orders) != len(set(orders))
        or orders != sorted(orders)
    ):
        raise DomainError("冻结创作内核顺序或标识无效")
    return CreativeKernelV1(
        str(value.get("kernel_version")),
        tuple(units),
        raw_program,
        selected_fact_block_ids,
    )


def kernel_digest(kernel: CreativeKernelV1) -> str:
    canonical = json.dumps(
        kernel_document(kernel),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


def creative_units_digest(kernel: CreativeKernelV1) -> str:
    canonical = json.dumps(
        [
            {
                "unit_id": unit.unit_id,
                "text": unit.text,
                "claim_refs": list(unit.claim_refs),
            }
            for unit in kernel.writable_units
            if unit.text_source != "server_compiler"
        ],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


def reconcile_kernel_observations(
    *,
    kernel: CreativeKernelV1,
    observations: Sequence[ReviewerObservation],
    fact_text_by_id: Mapping[str, str],
    allowed_constraint_ids: frozenset[str],
) -> tuple[NarrativeIssue, ...]:
    """Close the review world around the reviewed kernel and nothing else."""
    by_id: dict[str, ReviewerObservation] = {}
    issues: list[NarrativeIssue] = []
    units = {unit.unit_id: unit for unit in kernel.units}
    for observation in observations:
        if observation.target_id not in units or observation.target_id in by_id:
            issues.append(
                NarrativeIssue(
                    observation.target_id,
                    "review_coverage",
                    observation.target_id,
                )
            )
            continue
        unit = units[observation.target_id]
        if observation.target_kind != "unit":
            issues.append(
                NarrativeIssue(
                    unit.unit_id,
                    "review_coverage",
                    observation.target_kind,
                )
            )
        if observation.text_spans != (unit.text,):
            issues.append(
                NarrativeIssue(
                    unit.unit_id,
                    "review_coverage",
                    observation.text_spans[0],
                )
            )
        semantic_spans = (
            *observation.people,
            *observation.relationships,
            *observation.actions_or_events,
            *observation.dialogue,
            *observation.motives,
            *observation.causes,
            *observation.results,
            *observation.times,
            *observation.locations,
            *observation.possessions,
            *observation.dramatization_disclosure_spans,
            *observation.instruction_conflicts,
        )
        if any(span not in unit.text for span in semantic_spans):
            issues.append(
                NarrativeIssue(
                    unit.unit_id,
                    "missing_exact_span",
                    next(span for span in semantic_spans if span not in unit.text),
                )
            )
        if observation.uncertain or observation.observation_type == "uncertain":
            issues.append(NarrativeIssue(unit.unit_id, "uncertain_meaning", unit.text))
        if observation.instruction_conflicts:
            issues.append(
                NarrativeIssue(
                    unit.unit_id,
                    "instruction_conflict",
                    observation.instruction_conflicts[0],
                )
            )
        if observation.resource_refs:
            issues.append(
                NarrativeIssue(
                    unit.unit_id,
                    "review_resource_claim",
                    observation.resource_refs[0],
                )
            )
        if observation.observation_type not in unit.allowed_observation_types:
            reason = (
                "unsupported_institutional_assertion"
                if observation.observation_type == "institutional_assertion"
                else "unit_observation_drift"
            )
            issues.append(NarrativeIssue(unit.unit_id, reason, unit.text))
        if unit.purpose == "frozen_fact":
            exact = {fact_text_by_id[ref] for ref in unit.fact_refs if ref in fact_text_by_id}
            if len(unit.fact_refs) != 1 or unit.text not in exact or unit.constraint_refs:
                issues.append(
                    NarrativeIssue(
                        unit.unit_id,
                        "frozen_fact_changed",
                        unit.text,
                    )
                )
        elif unit.fact_refs:
            issues.append(
                NarrativeIssue(
                    unit.unit_id,
                    "writer_fact_binding",
                    unit.text,
                )
            )
        if any(ref not in allowed_constraint_ids for ref in unit.constraint_refs):
            issues.append(
                NarrativeIssue(
                    unit.unit_id,
                    "unknown_constraint_ref",
                    unit.text,
                )
            )
        if observation.observation_type == "dramatization" and (
            DRAMATIZATION_DISCLOSURE not in observation.dramatization_disclosure_spans
            or not unit.text.startswith(DRAMATIZATION_DISCLOSURE)
        ):
            issues.append(
                NarrativeIssue(
                    unit.unit_id,
                    "dramatization_not_visible",
                    unit.text,
                )
            )
        by_id[unit.unit_id] = observation
    for missing_id in set(units) - set(by_id):
        issues.append(NarrativeIssue(missing_id, "review_coverage", missing_id))
    return tuple(dict.fromkeys(issues))


def _requests_local_dramatization(instruction: str | None) -> bool:
    """Recognize the user's positive request for a visibly disclosed local scene.

    This is a bounded product-control grammar, not a list of unsafe topics or
    model-output patches.
    """
    if not instruction:
        return False
    markers = ("荒诞", "戏剧", "小情景", "情景演绎", "小剧场")
    negations = ("不要", "别", "不想", "不用", "无需", "避免", "取消", "去掉", "不再")
    clauses: list[str] = []
    start = 0
    for index, character in enumerate(instruction):
        if character not in "，,。！？!?\n；;":
            continue
        clauses.append(instruction[start:index])
        start = index + 1
    clauses.append(instruction[start:])
    for clause in clauses:
        for marker in markers:
            position = clause.find(marker)
            while position >= 0:
                prefix = clause[max(0, position - 6) : position]
                if not any(negation in prefix for negation in negations):
                    return True
                position = clause.find(marker, position + len(marker))
    return False


def _unit_track_contract(
    *,
    purpose: KernelPurpose,
    allowed: tuple[ObservationType, ...],
    raw: Mapping[str, object],
) -> tuple[UnitTrack, UnitMode, str]:
    if purpose == "frozen_fact":
        expected = ("trusted_fact", "trusted_fact")
        default_scope = "scope:trusted-fact-v1"
    elif allowed == ("hypothesis",):
        expected = ("creative_expression", "hypothesis")
        default_scope = "scope:hypothesis-v1"
    elif allowed == ("dramatization",):
        expected = ("creative_expression", "disclosed_dramatization")
        default_scope = "scope:disclosed-dramatization-v1"
    else:
        expected = ("creative_expression", "general_observation")
        default_scope = "scope:general-observation-v1"
    raw_track = raw.get("track", expected[0])
    raw_mode = raw.get("mode", expected[1])
    if purpose != "frozen_fact" and allowed == ("abstract_principle",) and raw_mode == "recommendation":
        expected = ("creative_expression", "recommendation")
        default_scope = "scope:recommendation-v1"
    raw_scope = raw.get("scope_id", default_scope)
    if raw_track != expected[0] or raw_mode != expected[1] or not isinstance(raw_scope, str) or not raw_scope:
        raise DomainError("冻结创作内核表达轨无效")
    return cast(UnitTrack, raw_track), cast(UnitMode, raw_mode), raw_scope


def _unit_text_source(
    *,
    purpose: KernelPurpose,
    raw: Mapping[str, object],
    kernel_version: str = KERNEL_VERSION,
) -> UnitTextSource:
    if purpose == "frozen_fact":
        expected: UnitTextSource = "server_fact"
    elif purpose in {"natural_guide", "release_caption"} and kernel_version != KERNEL_VERSION:
        expected = "server_compiler"
    else:
        expected = "writer"
    value = raw.get("text_source", expected)
    if value not in {
        "writer",
        "server_fact",
        "server_compiler",
        "prior_version",
    }:
        raise DomainError("冻结创作内核文字来源无效")
    if purpose == "frozen_fact" and value != "server_fact":
        raise DomainError("冻结事实文字来源无效")
    if (
        purpose in {"natural_guide", "release_caption"}
        and kernel_version != KERNEL_VERSION
        and value != "server_compiler"
    ):
        raise DomainError("编译器文字来源无效")
    if value == "prior_version" and purpose != "body":
        raise DomainError("历史版本文字来源无效")
    if value == "server_fact" and purpose != "frozen_fact":
        raise DomainError("冻结事实文字来源无效")
    return cast(UnitTextSource, value)


def _normalize_writer_visible_text(text: str) -> str:
    """Normalize neutral typography before review and visible digesting.

    Frozen facts never pass through this function. Paired ASCII double quotes
    are presentation punctuation in Writer-owned Chinese copy; turning them
    into curly quotes avoids delegating JSON escaping to Reviewer output while
    preserving the visible words. An unmatched quote fails closed.
    """
    assert_writer_visible_text_safe(text)
    quote_count = text.count('"')
    if quote_count == 0:
        return text
    if quote_count % 2:
        raise ValueError("writer visible text has unmatched double quote")
    result: list[str] = []
    opening = True
    for character in text:
        if character != '"':
            result.append(character)
            continue
        result.append("“" if opening else "”")
        opening = not opening
    return "".join(result)


def _required_string(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TypeError("value must be a non-empty string")
    return value.strip()


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise DomainError("冻结创作内核字符串列表无效")
    values = cast(list[str], value)
    if len(values) != len(set(values)):
        raise DomainError("冻结创作内核字符串列表重复")
    return tuple(values)
