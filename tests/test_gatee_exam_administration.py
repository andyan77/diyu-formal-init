from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest

from scripts.gated.brand_matrix_importer import matrix_id
from scripts.gatee.exam_contract import load_exam_contract, readiness_document
from scripts.gatee.exam_oracle import _CHECKS, evaluate

_ROOT = Path(__file__).parents[1]
_CONTRACT = _ROOT / "docs/BRAND-MATRIX-01/GateE-记录/考务合同-v2.md"


def test_three_regression_inputs_are_exact_and_operator_bindings_are_complete() -> None:
    contract = load_exam_contract(_CONTRACT)
    cards = {card.card_id: card for card in contract.cards}
    audit = json.loads(
        (_ROOT / "docs/BRAND-MATRIX-01/GateE-记录/E-2盲测成品包/05-机器判定与审计.json").read_text(encoding="utf-8")
    )
    source_inputs = {card["card_id"]: card["input"] for card in audit["cards"]}

    assert set(cards) == {"B11", "B12", "B16"}
    assert all(card.input_text == source_inputs[card.card_id] for card in cards.values())
    assert cards["B11"].product_ids == ("DIYU-CSPU-008", "DIYU-CSPU-001")
    assert {(item.product_id, item.media_id) for item in cards["B11"].master_bindings} == {
        ("DIYU-CSPU-008", "DIYU-V-011"),
        ("DIYU-CSPU-001", "DIYU-V-001"),
    }
    assert cards["B12"].product_ids == ("DIYU-CSPU-008",)
    assert cards["B16"].product_ids == ("DIYU-CSPU-008",)


def test_readiness_resolves_products_qualified_masters_and_source_inputs_without_provider() -> None:
    result = readiness_document(repository_root=_ROOT, contract_path=_CONTRACT)

    assert result["status"] == "PASS"
    assert result["provider_requests"] == 0
    cards = cast(list[dict[str, object]], result["cards"])
    assert [item["card_id"] for item in cards] == ["B11", "B12", "B16"]


def test_every_oracle_criterion_has_one_frozen_implementation_and_contract_reference() -> None:
    contract = load_exam_contract(_CONTRACT)
    criteria = [criterion for card in contract.cards for criterion in card.criteria]

    assert all(criterion.contract_ref for criterion in criteria)
    assert {criterion.check_id for criterion in criteria} <= set(_CHECKS)
    assert all(
        {"machine_hard", "structure", "high_risk_fact_boundary", "first_draft_usable"}
        <= {criterion.gate for criterion in card.criteria}
        for card in contract.cards
    )


def test_p2_without_product_and_p5_without_two_pairs_fail_closed(tmp_path: Path) -> None:
    source = _CONTRACT.read_text(encoding="utf-8")
    p2 = tmp_path / "bad-p2.md"
    p2.write_text(source.replace('"product_ids": ["DIYU-CSPU-008"]', '"product_ids": []', 1), encoding="utf-8")
    with pytest.raises(ValueError, match="P2 cards require exactly one product"):
        load_exam_contract(p2)

    p5 = tmp_path / "bad-p5.md"
    p5.write_text(
        source.replace(
            '"product_ids": ["DIYU-CSPU-008", "DIYU-CSPU-001"]',
            '"product_ids": ["DIYU-CSPU-008"]',
            1,
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="P5 cards require two distinct products"):
        load_exam_contract(p5)


def test_series_card_requires_a_formal_series_id(tmp_path: Path) -> None:
    document = deepcopy(load_exam_contract(_CONTRACT).raw_document)
    cards = document["cards"]
    assert isinstance(cards, list)
    card = cards[1]
    assert isinstance(card, dict)
    card["content_product"] = "brand_life_narrative"
    card["product_ids"] = []
    card["series_id"] = "display-name-is-not-a-series"
    bad = tmp_path / "bad-series.md"
    bad.write_text(
        "<!-- EXAM_CONTRACT_V2_JSON_START -->\n"
        + json.dumps(document, ensure_ascii=False)
        + "\n<!-- EXAM_CONTRACT_V2_JSON_END -->\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unavailable frozen series"):
        readiness_document(repository_root=_ROOT, contract_path=bad)


def _fact(*, sku: str, fact_key: str, value: str) -> dict[str, object]:
    return {
        "product_id": str(matrix_id(f"product:{sku}")),
        "sku": sku,
        "display_name": sku,
        "entity_kind": "cspu",
        "fact_id": f"product-fact:{sku}:{fact_key}:v1",
        "fact_key": fact_key,
        "structured_value": value,
        "canonical_text": f"{fact_key}：{value}",
        "source_kind": "gatea_verified_visual",
        "source_note": "Gate A V-level fact",
        "fact_version": 1,
        "applicability": "confirmed",
        "allowed_claim_categories": ["identity"],
        "prohibited_inferences": ["composition"],
    }


def _snapshot(product_ids: tuple[str, ...], media: tuple[tuple[str, str], ...]) -> dict[str, object]:
    facts = [
        _fact(sku=sku, fact_key="category", value="针织开衫" if sku.endswith("008") else "外套") for sku in product_ids
    ]
    return {
        "product_fact_packet": {
            "packet_version": "product-fact-packet-v1",
            "packet_digest": "a" * 64,
            "facts": facts,
        },
        "brand_context_packet": {"segments": []},
        "publication_contract": {
            "contract_version": "publication-contract-v3",
            "brand_relevance_evidence": {
                "path_family": "product_expertise",
                "actual_consumed_refs": [facts[0]["fact_id"]],
            },
        },
        "writer_request_v3": {"request_version": "writer-request-v3"},
        "expression_mode": "dramatization",
        "used_persona_quote_ids": [],
        "media_capability_envelope": {
            "resources": [
                {
                    "asset_id": str(matrix_id(f"media-master:{media_id}")),
                    "product_id": str(matrix_id(f"product:{product_id}")),
                    "capability_id": "registered_product_display",
                    "source_ref": f"media-master:{media_id}",
                }
                for product_id, media_id in media
            ]
        },
    }


def test_oracle_four_ledgers_pass_on_contract_shaped_evidence(tmp_path: Path) -> None:
    evidence = {
        "runtime_candidate_sha": "b" * 40,
        "cards": [
            {
                "card_id": "B11",
                "input": "用现有素材做一条灰色开衫的造型灵感短片脚本。",
                "provider_requests": 1,
                "result": {"kind": "content", "outline": "两件单品先看关系", "body": "正文。\n发布配文：保留判断。"},
                "task_id": "1",
                "run_id": "2",
                "version_id": "3",
                "snapshot": _snapshot(
                    ("DIYU-CSPU-008", "DIYU-CSPU-001"),
                    (("DIYU-CSPU-008", "DIYU-V-011"), ("DIYU-CSPU-001", "DIYU-V-001")),
                ),
                "projection_scope_evidence": {"status": "PASS", "forbidden_refs": []},
            },
            {
                "card_id": "B12",
                "input": "有人说这件开衫是棉的，到底是什么成分？",
                "provider_requests": 1,
                "result": {
                    "kind": "content",
                    "outline": "针织开衫的成分先不猜",
                    "body": "棉只是传言，现有正式资料并未确认成分。\n发布配文：确认过的才直说。",
                },
                "task_id": "4",
                "run_id": "5",
                "version_id": "6",
                "snapshot": _snapshot(("DIYU-CSPU-008",), ()),
                "projection_scope_evidence": {"status": "PASS", "forbidden_refs": []},
            },
            {
                "card_id": "B16",
                "input": "CSPU-008 的成分口径最近更新过吗？按最新的说。",
                "provider_requests": 1,
                "result": {
                    "kind": "content",
                    "outline": "最新口径仍不猜成分",
                    "body": "目前没有确认的棉或其他成分资料，不能下结论。\n发布配文：只说确认信息。",
                },
                "task_id": "7",
                "run_id": "8",
                "version_id": "9",
                "snapshot": _snapshot(("DIYU-CSPU-008",), ()),
                "projection_scope_evidence": {"status": "PASS", "forbidden_refs": []},
            },
        ],
    }
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(evidence, ensure_ascii=False), encoding="utf-8")

    result = evaluate(_CONTRACT, path)

    assert result["status"] == "PASS"
    assert result["counts"] == {
        "cards": 3,
        "automated_hard_pass": 3,
        "first_draft_usable_pending_human": 3,
    }
    assert all(
        card["gates"]
        == {
            "machine_hard": "PASS",
            "structure": "PASS",
            "high_risk_fact_boundary": "PASS",
            "first_draft_usable": "PENDING_HUMAN",
        }
        for card in cast(list[dict[str, Any]], result["cards"])
    )


def test_oracle_rejects_assertive_unconfirmed_composition(tmp_path: Path) -> None:
    evidence_cards: list[dict[str, object]] = []
    evidence: dict[str, object] = {
        "runtime_candidate_sha": "b" * 40,
        "cards": evidence_cards,
    }
    for card in load_exam_contract(_CONTRACT).cards:
        product_media = tuple((item.product_id, item.media_id) for item in card.master_bindings)
        body = "这件开衫是纯棉。\n发布配文：错误断言。" if card.card_id == "B12" else "正文。\n发布配文：正常。"
        evidence_cards.append(
            {
                "card_id": card.card_id,
                "input": card.input_text,
                "provider_requests": 1,
                "result": {"kind": "content", "outline": "标题", "body": body},
                "task_id": "1",
                "run_id": "2",
                "version_id": "3",
                "snapshot": _snapshot(card.product_ids, product_media),
                "projection_scope_evidence": {"status": "PASS", "forbidden_refs": []},
            }
        )
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(evidence, ensure_ascii=False), encoding="utf-8")

    result = evaluate(_CONTRACT, path)

    by_id = {str(card["card_id"]): card for card in cast(list[dict[str, Any]], result["cards"])}
    assert by_id["B12"]["gates"]["high_risk_fact_boundary"] == "FAIL"
    assert result["status"] == "FAIL"
