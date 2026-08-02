from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from src.shared.errors import DomainError
from src.shared.narrative import NarrativeFrame, frame_document
from src.shared.types import ContentProduct, MediaFormat

SERVER_BEARING_EXPRESSION_VERSION = "server-bearing-expression-v1"
P1_SELECTION_UNIT_ID = "unit:p1-selection-skeleton"

_P1_SELECTION_SKELETON = (
    "先在已经给出的条件里选出最不能妥协的一项，再只保留一个需要兼顾的变化。"
    "如果更想少带东西，可以用可增减的穿着层次留出调整空间，但不预设某件单品一定有效；"
    "如果两种情况都必须覆盖，就需要接受多保留一个层次。出门前先按最不想承受的情况作一次取舍。"
)
_VISIBLE_CLAUSE_SEPARATOR = re.compile(r"[，。！？!?；;\n]+")


@dataclass(frozen=True)
class ServerBearingExpressionUnitV1:
    unit_id: str
    purpose: str
    mode: str
    text: str


@dataclass(frozen=True)
class ServerBearingExpressionContractV1:
    contract_version: str
    primary_product: ContentProduct
    media_format: MediaFormat
    series_position: int | None
    narrative_frame_digest: str
    fact_source_ids: tuple[str, ...]
    units: tuple[ServerBearingExpressionUnitV1, ...]

    @property
    def unit_text_by_id(self) -> dict[str, str]:
        return {unit.unit_id: unit.text for unit in self.units}


def build_server_bearing_expression_contract(
    *,
    primary_product: ContentProduct,
    media_format: MediaFormat,
    frame: NarrativeFrame,
    series_position: int | None,
) -> ServerBearingExpressionContractV1 | None:
    """Build only the narrow expression surfaces whose claims need server ownership."""

    units: tuple[ServerBearingExpressionUnitV1, ...] = ()
    if primary_product == "dressing_decision":
        units = (
            ServerBearingExpressionUnitV1(
                unit_id=P1_SELECTION_UNIT_ID,
                purpose="body",
                mode="recommendation",
                text=_P1_SELECTION_SKELETON,
            ),
        )
    elif (
        primary_product in {"brand_life_narrative", "local_response"}
        and frame.narrative_mode == "actuality_reflection"
        and frame.user_facts
    ):
        clauses = _actuality_clauses(frame)
        title = clauses[0] if len(clauses) == 1 else f"{clauses[0]}：{clauses[1]}"
        focus = clauses[-1]
        units = (
            ServerBearingExpressionUnitV1(
                unit_id="unit:title",
                purpose="title",
                mode="general_observation",
                text=title,
            ),
            ServerBearingExpressionUnitV1(
                unit_id="unit:release-caption",
                purpose="release_caption",
                mode="general_observation",
                text=_actuality_release_caption(
                    primary_product=primary_product,
                    media_format=media_format,
                    focus=focus,
                    series_position=series_position,
                ),
            ),
        )
    if not units:
        return None
    return ServerBearingExpressionContractV1(
        contract_version=SERVER_BEARING_EXPRESSION_VERSION,
        primary_product=primary_product,
        media_format=media_format,
        series_position=series_position,
        narrative_frame_digest=_frame_digest(frame),
        fact_source_ids=tuple(fact.source_id for fact in frame.user_facts),
        units=units,
    )


def assert_server_bearing_expression_matches(
    contract: ServerBearingExpressionContractV1,
    *,
    primary_product: ContentProduct,
    media_format: MediaFormat,
    frame: NarrativeFrame,
    series_position: int | None,
) -> None:
    expected = build_server_bearing_expression_contract(
        primary_product=primary_product,
        media_format=media_format,
        frame=frame,
        series_position=series_position,
    )
    if expected is None or contract != expected:
        raise DomainError("冻结的服务端承重表达合同与当前任务不一致")


def server_bearing_expression_document(
    contract: ServerBearingExpressionContractV1,
) -> dict[str, object]:
    return {
        "contract_version": contract.contract_version,
        "primary_product": contract.primary_product,
        "media_format": contract.media_format,
        "series_position": contract.series_position,
        "narrative_frame_digest": contract.narrative_frame_digest,
        "fact_source_ids": list(contract.fact_source_ids),
        "units": [
            {
                "unit_id": unit.unit_id,
                "purpose": unit.purpose,
                "mode": unit.mode,
                "text": unit.text,
            }
            for unit in contract.units
        ],
    }


def server_bearing_expression_digest(
    contract: ServerBearingExpressionContractV1,
) -> str:
    return hashlib.sha256(
        json.dumps(
            server_bearing_expression_document(contract),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    ).hexdigest()


def server_bearing_expression_from_document(
    value: object,
) -> ServerBearingExpressionContractV1:
    if not isinstance(value, Mapping) or frozenset(value) != frozenset(
        {
            "contract_version",
            "primary_product",
            "media_format",
            "series_position",
            "narrative_frame_digest",
            "fact_source_ids",
            "units",
        }
    ):
        raise DomainError("冻结的服务端承重表达合同无效")
    contract_version = value.get("contract_version")
    primary_product = value.get("primary_product")
    media_format = value.get("media_format")
    series_position = value.get("series_position")
    narrative_frame_digest = value.get("narrative_frame_digest")
    fact_source_ids = _string_tuple(value.get("fact_source_ids"))
    raw_units = value.get("units")
    if (
        contract_version != SERVER_BEARING_EXPRESSION_VERSION
        or primary_product
        not in {
            "dressing_decision",
            "product_truth",
            "brand_life_narrative",
            "local_response",
            "visual_styling_story",
        }
        or media_format not in {"graphic", "video"}
        or (series_position is not None and (not isinstance(series_position, int) or series_position < 1))
        or not isinstance(narrative_frame_digest, str)
        or len(narrative_frame_digest) != 64
        or not isinstance(raw_units, list)
        or not raw_units
    ):
        raise DomainError("冻结的服务端承重表达合同无效")
    units: list[ServerBearingExpressionUnitV1] = []
    for raw_unit in raw_units:
        if not isinstance(raw_unit, Mapping) or frozenset(raw_unit) != frozenset(
            {"unit_id", "purpose", "mode", "text"}
        ):
            raise DomainError("冻结的服务端承重表达单元无效")
        unit_id = raw_unit.get("unit_id")
        purpose = raw_unit.get("purpose")
        mode = raw_unit.get("mode")
        text = raw_unit.get("text")
        if not all(isinstance(item, str) and item for item in (unit_id, purpose, mode, text)):
            raise DomainError("冻结的服务端承重表达单元无效")
        units.append(
            ServerBearingExpressionUnitV1(
                unit_id=cast(str, unit_id),
                purpose=cast(str, purpose),
                mode=cast(str, mode),
                text=cast(str, text),
            )
        )
    if len({unit.unit_id for unit in units}) != len(units):
        raise DomainError("冻结的服务端承重表达单元重复")
    return ServerBearingExpressionContractV1(
        contract_version=SERVER_BEARING_EXPRESSION_VERSION,
        primary_product=cast(ContentProduct, primary_product),
        media_format=cast(MediaFormat, media_format),
        series_position=series_position,
        narrative_frame_digest=narrative_frame_digest,
        fact_source_ids=fact_source_ids,
        units=tuple(units),
    )


def _actuality_clauses(frame: NarrativeFrame) -> tuple[str, ...]:
    clauses = tuple(
        clause.strip()
        for fact in frame.user_facts
        for clause in _VISIBLE_CLAUSE_SEPARATOR.split(fact.exact_text)
        if clause.strip()
    )
    if not clauses:
        raise DomainError("服务端承重表达合同缺少可引用的现实片段")
    # A title and caption need at most the first two observable clauses.  Any
    # later creation instruction remains frozen in the source fact but cannot
    # become a publication claim.
    return clauses[:2]


def _actuality_release_caption(
    *,
    primary_product: ContentProduct,
    media_format: MediaFormat,
    focus: str,
    series_position: int | None,
) -> str:
    if primary_product == "local_response":
        if series_position is not None and series_position > 1:
            return f"如果要继续回应“{focus}”，可以先让对方保留下一步的选择。"
        return f"如果要回应“{focus}”，可以先给对方留出选择，不替这段现场下结论。"
    if media_format == "video":
        return f"把“{focus}”留到最后一拍；先看见变化，不替它补原因。"
    return f"这次先停在“{focus}”上；不急着替这个变化补原因。"


def _frame_digest(frame: NarrativeFrame) -> str:
    return hashlib.sha256(
        json.dumps(
            frame_document(frame),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    ).hexdigest()


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise DomainError("冻结的服务端承重表达来源无效")
    return tuple(cast(list[str], value))
