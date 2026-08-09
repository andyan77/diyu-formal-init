"""Parse and validate the frozen Gate E exam-administration contract."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

_START = "<!-- EXAM_CONTRACT_V2_JSON_START -->"
_END = "<!-- EXAM_CONTRACT_V2_JSON_END -->"
CONTRACT_VERSION = "brand-matrix-exam-administration-v2"
ALLOWED_PRODUCTS = frozenset(
    {
        "dressing_decision",
        "product_truth",
        "brand_life_narrative",
        "local_response",
        "visual_styling_story",
    }
)
ALLOWED_GATES = frozenset(
    {
        "machine_hard",
        "structure",
        "high_risk_fact_boundary",
        "first_draft_usable",
    }
)


@dataclass(frozen=True)
class MasterBinding:
    product_id: str
    media_id: str


@dataclass(frozen=True)
class Criterion:
    check_id: str
    gate: str
    contract_ref: str


@dataclass(frozen=True)
class ExamCard:
    card_id: str
    account_code: str
    content_product: str
    target: str
    input_text: str
    product_ids: tuple[str, ...]
    master_bindings: tuple[MasterBinding, ...]
    series_id: str | None
    allowed_quote_ids: tuple[str, ...]
    criteria: tuple[Criterion, ...]


@dataclass(frozen=True)
class ExamContract:
    contract_version: str
    source_audit_json: Path
    cards: tuple[ExamCard, ...]
    raw_document: dict[str, object]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _object(value: object, message: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(message)
    return cast(dict[str, Any], value)


def _list(value: object, message: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(message)
    return value


def _embedded_document(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    if text.count(_START) != 1 or text.count(_END) != 1:
        raise ValueError("exam contract must contain one canonical JSON block")
    raw = text.split(_START, maxsplit=1)[1].split(_END, maxsplit=1)[0].strip()
    document = json.loads(raw)
    return cast(dict[str, object], _object(document, "exam contract JSON must be one object"))


def _criteria(raw: object) -> tuple[Criterion, ...]:
    criteria: list[Criterion] = []
    for value in _list(raw, "exam card criteria must be one list"):
        item = _object(value, "exam criterion must be one object")
        criterion = Criterion(
            check_id=str(item.get("check_id", "")),
            gate=str(item.get("gate", "")),
            contract_ref=str(item.get("contract_ref", "")),
        )
        if not criterion.check_id or criterion.gate not in ALLOWED_GATES or not criterion.contract_ref:
            raise ValueError("every criterion needs a check id, one known gate, and a frozen contract reference")
        criteria.append(criterion)
    if len({item.check_id for item in criteria}) != len(criteria):
        raise ValueError("exam card criterion ids must be unique")
    if "first_draft_usable" not in {item.gate for item in criteria}:
        raise ValueError("exam card must retain the human first-draft ledger")
    return tuple(criteria)


def _card(raw: object) -> ExamCard:
    item = _object(raw, "exam card must be one object")
    product_ids = tuple(str(value) for value in _list(item.get("product_ids", []), "product ids must be a list"))
    bindings = tuple(
        MasterBinding(
            product_id=str(_object(value, "master binding must be one object").get("product_id", "")),
            media_id=str(_object(value, "master binding must be one object").get("media_id", "")),
        )
        for value in _list(item.get("master_bindings", []), "master bindings must be a list")
    )
    card = ExamCard(
        card_id=str(item.get("card_id", "")),
        account_code=str(item.get("account_code", "")),
        content_product=str(item.get("content_product", "")),
        target=str(item.get("target", "")),
        input_text=str(item.get("input", "")),
        product_ids=product_ids,
        master_bindings=bindings,
        series_id=str(item["series_id"]) if item.get("series_id") is not None else None,
        allowed_quote_ids=tuple(
            str(value) for value in _list(item.get("allowed_quote_ids", []), "allowed quote ids must be a list")
        ),
        criteria=_criteria(item.get("criteria")),
    )
    if (
        not card.card_id
        or not card.account_code
        or not card.input_text
        or card.content_product not in ALLOWED_PRODUCTS
        or not card.target
        or len(set(card.product_ids)) != len(card.product_ids)
    ):
        raise ValueError("exam card identity, route, input, or product binding is invalid")
    if card.content_product == "product_truth" and (
        len(card.product_ids) != 1 or card.master_bindings or card.series_id is not None
    ):
        raise ValueError("P2 cards require exactly one product and no media or series binding")
    if card.content_product == "visual_styling_story" and (
        len(card.product_ids) != 2
        or len(card.master_bindings) != 2
        or {item.product_id for item in card.master_bindings} != set(card.product_ids)
        or len({item.media_id for item in card.master_bindings}) != 2
        or card.series_id is not None
    ):
        raise ValueError("P5 cards require two distinct products and one distinct master for each")
    if card.series_id is not None and card.content_product != "brand_life_narrative":
        raise ValueError("series bindings belong only to P3 series cards")
    return card


def load_exam_contract(path: Path) -> ExamContract:
    document = _embedded_document(path)
    version = str(document.get("contract_version", ""))
    source_audit = str(document.get("source_audit_json", ""))
    raw_cards = _list(document.get("cards"), "exam contract cards must be one list")
    cards = tuple(_card(item) for item in raw_cards)
    if version != CONTRACT_VERSION or not source_audit or not cards:
        raise ValueError("exam contract version, source audit, or cards differ")
    if len({card.card_id for card in cards}) != len(cards):
        raise ValueError("exam card ids must be unique")
    return ExamContract(
        contract_version=version,
        source_audit_json=Path(source_audit),
        cards=cards,
        raw_document=document,
    )


def readiness_document(
    *,
    repository_root: Path,
    contract_path: Path,
) -> dict[str, object]:
    contract = load_exam_contract(contract_path)
    gate_a_path = repository_root / "docs/BRAND-MATRIX-01/GateA-素材合同/import-contract.json"
    media_path = repository_root / "docs/BRAND-MATRIX-01/GateD-记录/media-master-manifest.json"
    source_audit_path = repository_root / contract.source_audit_json
    gate_a = _object(json.loads(gate_a_path.read_text(encoding="utf-8")), "Gate A contract must be an object")
    media = _object(json.loads(media_path.read_text(encoding="utf-8")), "media manifest must be an object")
    source_audit = _object(
        json.loads(source_audit_path.read_text(encoding="utf-8")),
        "source audit must be an object",
    )
    product_ids = {
        str(_object(item, "deep SKU package must be an object").get("cspu_id", ""))
        for item in _list(gate_a.get("deep_sku_packages"), "deep SKU packages must be a list")
    }
    series_ids = {
        str(_object(item, "series item must be an object").get("series_id", ""))
        for item in _list(gate_a.get("series"), "series must be a list")
    }
    media_by_id = {
        str(_object(item, "media record must be an object").get("media_id", "")): _object(
            item, "media record must be an object"
        )
        for item in _list(media.get("records"), "media records must be a list")
    }
    source_inputs = {
        str(_object(item, "source card must be an object").get("card_id", "")): str(
            _object(item, "source card must be an object").get("input", "")
        )
        for item in _list(source_audit.get("cards"), "source audit cards must be a list")
    }
    checks: list[dict[str, object]] = []
    for card in contract.cards:
        if not set(card.product_ids) <= product_ids:
            raise ValueError(f"{card.card_id} names a product outside the frozen Gate A SKU set")
        if card.series_id is not None and card.series_id not in series_ids:
            raise ValueError(f"{card.card_id} names an unavailable frozen series")
        if source_inputs.get(card.card_id) != card.input_text:
            raise ValueError(f"{card.card_id} input differs from the archived E-2 audit JSON")
        for binding in card.master_bindings:
            record = media_by_id.get(binding.media_id)
            if (
                record is None
                or record.get("master_p5_eligible") is not True
                or record.get("release_status") != "PASS"
                or binding.product_id not in cast(list[object], record.get("formal_product_bindings", []))
            ):
                raise ValueError(f"{card.card_id} media binding is not one PASS P5-qualified master")
        checks.append(
            {
                "card_id": card.card_id,
                "input_exact": True,
                "product_ids": list(card.product_ids),
                "master_media_ids": [item.media_id for item in card.master_bindings],
                "series_id": card.series_id,
                "status": "PASS",
            }
        )
    return {
        "contract_version": contract.contract_version,
        "contract_sha256": sha256_file(contract_path),
        "source_audit_sha256": sha256_file(source_audit_path),
        "gate_a_contract_sha256": sha256_file(gate_a_path),
        "media_manifest_sha256": sha256_file(media_path),
        "provider_requests": 0,
        "cards": checks,
        "status": "PASS",
    }
