#!/usr/bin/env python3
"""Evaluate Gate E artifacts against only contract-bound exam obligations."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from scripts.gated.brand_matrix_importer import matrix_id  # noqa: E402
from scripts.gatee.exam_contract import ExamCard, load_exam_contract  # noqa: E402
from src.shared.factual_basis import (  # noqa: E402
    ProductClaimCategory,
    ProductFactPacket,
    ProductFactPacketItem,
    product_fact_value_conflicts,
    unconfirmed_product_specificity_spans,
)

Check = Callable[[ExamCard, dict[str, Any]], tuple[bool, object]]
_COMPOSITION_TERMS = re.compile(r"棉|腈纶|羊毛|羊绒|涤纶|聚酯纤维|锦纶|氨纶|粘纤|莱赛尔|莫代尔|麻|真丝")
_NON_ASSERTIVE = re.compile(
    r"未确认|没有确认|并未确认|尚未确认|不是已确认|不能确认|无法确认|不确定|"
    r"不作判断|不作确定|不能下结论|候选|传言|有人说|到底|是否|没有依据|没有证据"
)
_SENTENCE = re.compile(r"[^。！？!?\n]+[。！？!?]?")


def _object(value: object, message: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(message)
    return cast(dict[str, Any], value)


def _list(value: object, message: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(message)
    return value


def _visible(evidence: dict[str, Any]) -> str:
    result = _object(evidence.get("result"), "card evidence result must be one object")
    return f"{result.get('outline', '')}\n{result.get('body', '')}"


def _snapshot(evidence: dict[str, Any]) -> dict[str, Any]:
    return _object(evidence.get("snapshot"), "card evidence snapshot must be one object")


def _packet(snapshot: dict[str, Any]) -> ProductFactPacket:
    document = _object(snapshot.get("product_fact_packet"), "product fact packet is missing")
    facts: list[ProductFactPacketItem] = []
    for value in _list(document.get("facts"), "product fact packet facts must be one list"):
        item = _object(value, "product fact packet item must be one object")
        structured = item.get("structured_value")
        if isinstance(structured, list):
            structured = tuple(str(part) for part in structured)
        if not isinstance(structured, (str, int, bool, tuple)):
            raise ValueError("product fact structured value has an unsupported shape")
        facts.append(
            ProductFactPacketItem(
                product_id=str(item["product_id"]),
                sku=str(item["sku"]),
                display_name=str(item["display_name"]),
                entity_kind=str(item["entity_kind"]),
                fact_id=str(item["fact_id"]),
                fact_key=str(item["fact_key"]),
                structured_value=structured,
                canonical_text=str(item["canonical_text"]),
                source_kind=str(item["source_kind"]),
                source_note=str(item["source_note"]),
                fact_version=int(item["fact_version"]),
                applicability=str(item["applicability"]),
                allowed_claim_categories=cast(
                    tuple[ProductClaimCategory, ...],
                    tuple(str(part) for part in _list(item["allowed_claim_categories"], "categories must be a list")),
                ),
                prohibited_inferences=tuple(
                    str(part) for part in _list(item["prohibited_inferences"], "inferences must be a list")
                ),
            )
        )
    return ProductFactPacket(
        packet_version=str(document["packet_version"]),
        packet_digest=str(document["packet_digest"]),
        facts=tuple(facts),
    )


def _input_exact(card: ExamCard, evidence: dict[str, Any]) -> tuple[bool, object]:
    observed = str(evidence.get("input", ""))
    return observed == card.input_text, {"expected": card.input_text, "observed": observed}


def _provider_once(card: ExamCard, evidence: dict[str, Any]) -> tuple[bool, object]:
    del card
    observed = int(evidence.get("provider_requests", -1))
    return observed == 1, {"observed": observed}


def _projection_scope_visible(card: ExamCard, evidence: dict[str, Any]) -> tuple[bool, object]:
    del card
    scope = _object(evidence.get("projection_scope_evidence"), "projection scope evidence is missing")
    forbidden = _list(scope.get("forbidden_refs"), "forbidden refs must be one list")
    passed = scope.get("status") == "PASS" and not forbidden
    return passed, {"forbidden_refs": forbidden, "status": scope.get("status")}


def _hard_specificity_absent(card: ExamCard, evidence: dict[str, Any]) -> tuple[bool, object]:
    del card
    spans = unconfirmed_product_specificity_spans(_visible(evidence))
    return not spans, {"spans": list(spans)}


def _product_value_conflicts_absent(card: ExamCard, evidence: dict[str, Any]) -> tuple[bool, object]:
    del card
    conflicts = product_fact_value_conflicts(_packet(_snapshot(evidence)), _visible(evidence))
    return not conflicts, {"conflicts": list(conflicts)}


def _authorized_quotes_only(card: ExamCard, evidence: dict[str, Any]) -> tuple[bool, object]:
    used = _list(_snapshot(evidence).get("used_persona_quote_ids", []), "used quote ids must be one list")
    unauthorized = sorted(set(str(value) for value in used) - set(card.allowed_quote_ids))
    return not unauthorized, {"used": used, "unauthorized": unauthorized}


def _artifact_complete(card: ExamCard, evidence: dict[str, Any]) -> tuple[bool, object]:
    del card
    result = _object(evidence.get("result"), "card evidence result must be one object")
    outline = str(result.get("outline", "")).strip()
    body = str(result.get("body", "")).strip()
    passed = result.get("kind") == "content" and bool(outline) and bool(body) and "发布配文" in body
    return passed, {
        "kind": result.get("kind"),
        "outline_nonempty": bool(outline),
        "body_nonempty": bool(body),
        "publish_caption_present": "发布配文" in body,
    }


def _task_chain_complete(card: ExamCard, evidence: dict[str, Any]) -> tuple[bool, object]:
    del card
    snapshot = _snapshot(evidence)
    publication = snapshot.get("publication_contract")
    writer = snapshot.get("writer_request_v3")
    ids = {key: str(evidence.get(key, "")) for key in ("task_id", "run_id", "version_id")}
    passed = (
        all(ids.values())
        and isinstance(publication, dict)
        and publication.get("contract_version") == "publication-contract-v3"
        and isinstance(writer, dict)
        and snapshot.get("expression_mode") == "dramatization"
    )
    return passed, ids | {"publication_v3": isinstance(publication, dict), "writer_v3": isinstance(writer, dict)}


def _selected_products_exact(card: ExamCard, evidence: dict[str, Any]) -> tuple[bool, object]:
    observed = sorted({item.sku for item in _packet(_snapshot(evidence)).facts})
    expected = sorted(card.product_ids)
    return observed == expected, {"expected": expected, "observed": observed}


def _p5_qualified_masters_exact(card: ExamCard, evidence: dict[str, Any]) -> tuple[bool, object]:
    envelope = _object(
        _snapshot(evidence).get("media_capability_envelope"),
        "P5 media capability envelope is missing",
    )
    resources = _list(envelope.get("resources"), "P5 media resources must be one list")
    observed = {
        (str(item.get("asset_id")), str(item.get("product_id")))
        for value in resources
        if isinstance(value, dict)
        for item in [cast(dict[str, Any], value)]
        if item.get("capability_id") == "registered_product_display"
    }
    expected = {
        (str(matrix_id(f"media-master:{binding.media_id}")), str(matrix_id(f"product:{binding.product_id}")))
        for binding in card.master_bindings
    }
    return observed == expected, {
        "expected": sorted([list(item) for item in expected]),
        "observed": sorted([list(item) for item in observed]),
    }


def _original_media_absent(card: ExamCard, evidence: dict[str, Any]) -> tuple[bool, object]:
    del card
    envelope = _object(_snapshot(evidence).get("media_capability_envelope"), "P5 envelope is missing")
    resources = _list(envelope.get("resources"), "P5 media resources must be one list")
    forbidden = [
        str(item.get("source_ref"))
        for value in resources
        if isinstance(value, dict)
        for item in [cast(dict[str, Any], value)]
        if item.get("capability_id") == "selected_media_asset"
    ]
    return not forbidden, {"original_or_unregistered_refs": forbidden}


def _unconfirmed_composition_not_asserted(card: ExamCard, evidence: dict[str, Any]) -> tuple[bool, object]:
    del card
    violations: list[str] = []
    for match in _SENTENCE.finditer(_visible(evidence)):
        sentence = match.group(0).strip()
        if _COMPOSITION_TERMS.search(sentence) and _NON_ASSERTIVE.search(sentence) is None:
            violations.append(sentence)
    return not violations, {"assertive_composition_sentences": violations}


def _store_error_source_absent(card: ExamCard, evidence: dict[str, Any]) -> tuple[bool, object]:
    del card
    packet = _object(_snapshot(evidence).get("brand_context_packet"), "brand context packet is missing")
    segments = _list(packet.get("segments"), "brand context segments must be one list")
    forbidden = [
        str(item.get("source_id") or item.get("claim_key") or item.get("segment_id"))
        for value in segments
        if isinstance(value, dict)
        for item in [cast(dict[str, Any], value)]
        if "SK-CD" in json.dumps(item, ensure_ascii=False) or "门店错误成分" in json.dumps(item, ensure_ascii=False)
    ]
    return not forbidden, {"forbidden_store_sources": forbidden}


def _first_draft_manual(card: ExamCard, evidence: dict[str, Any]) -> tuple[bool, object]:
    del card, evidence
    return True, {"result": "PENDING_HUMAN", "score": None, "reviewer": None}


_CHECKS: dict[str, Check] = {
    "input_exact": _input_exact,
    "provider_once": _provider_once,
    "projection_scope_visible": _projection_scope_visible,
    "hard_specificity_absent": _hard_specificity_absent,
    "product_value_conflicts_absent": _product_value_conflicts_absent,
    "authorized_quotes_only": _authorized_quotes_only,
    "artifact_complete": _artifact_complete,
    "task_chain_complete": _task_chain_complete,
    "selected_products_exact": _selected_products_exact,
    "p5_qualified_masters_exact": _p5_qualified_masters_exact,
    "original_media_absent": _original_media_absent,
    "unconfirmed_composition_not_asserted": _unconfirmed_composition_not_asserted,
    "store_error_source_absent": _store_error_source_absent,
    "first_draft_manual": _first_draft_manual,
}


def evaluate(contract_path: Path, evidence_path: Path) -> dict[str, object]:
    contract = load_exam_contract(contract_path)
    evidence = _object(json.loads(evidence_path.read_text(encoding="utf-8")), "evidence must be one object")
    evidence_cards = {
        str(item.get("card_id", "")): item
        for value in _list(evidence.get("cards"), "evidence cards must be one list")
        for item in [_object(value, "evidence card must be one object")]
    }
    if set(evidence_cards) != {card.card_id for card in contract.cards}:
        raise ValueError("evidence card set differs from the exam contract")
    cards: list[dict[str, object]] = []
    for card in contract.cards:
        card_evidence = evidence_cards[card.card_id]
        checks: list[dict[str, object]] = []
        for criterion in card.criteria:
            implementation = _CHECKS.get(criterion.check_id)
            if implementation is None:
                raise ValueError(f"criterion {criterion.check_id} has no frozen oracle implementation")
            passed, observed = implementation(card, card_evidence)
            result = "PENDING_HUMAN" if criterion.gate == "first_draft_usable" else ("PASS" if passed else "FAIL")
            checks.append(
                {
                    "check_id": criterion.check_id,
                    "gate": criterion.gate,
                    "contract_ref": criterion.contract_ref,
                    "result": result,
                    "observed": observed,
                }
            )
        gate_results = {
            gate: (
                "PENDING_HUMAN"
                if gate == "first_draft_usable"
                else ("PASS" if all(item["result"] == "PASS" for item in checks if item["gate"] == gate) else "FAIL")
            )
            for gate in (
                "machine_hard",
                "structure",
                "high_risk_fact_boundary",
                "first_draft_usable",
            )
        }
        cards.append(
            {
                "card_id": card.card_id,
                "checks": checks,
                "gates": gate_results,
                "automated_hard_result": (
                    "PASS"
                    if all(
                        gate_results[gate] == "PASS"
                        for gate in (
                            "machine_hard",
                            "structure",
                            "high_risk_fact_boundary",
                        )
                    )
                    else "FAIL"
                ),
            }
        )
    automated_pass = sum(item["automated_hard_result"] == "PASS" for item in cards)
    return {
        "oracle_version": "brand-matrix-exam-oracle-v2",
        "runtime_candidate_sha": evidence.get("runtime_candidate_sha"),
        "cards": cards,
        "counts": {
            "cards": len(cards),
            "automated_hard_pass": automated_pass,
            "first_draft_usable_pending_human": len(cards),
        },
        "status": "PASS" if automated_pass == len(cards) else "FAIL",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    result = evaluate(arguments.contract.resolve(), arguments.evidence.resolve())
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if arguments.output is not None:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(rendered, encoding="utf-8")
    print(
        json.dumps(
            {
                "automated_hard_pass": result["counts"]["automated_hard_pass"],  # type: ignore[index]
                "cards": result["counts"]["cards"],  # type: ignore[index]
                "status": result["status"],
            },
            sort_keys=True,
        )
    )
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
