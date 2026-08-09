#!/usr/bin/env python3
"""Assert E-1' bindings, oracle ledgers, and zero-provider preflight evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, cast

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from scripts.gatee.exam_contract import load_exam_contract, readiness_document  # noqa: E402
from scripts.gatee.exam_oracle import _CHECKS  # noqa: E402

_CONTRACT = _ROOT / "docs/BRAND-MATRIX-01/GateE-记录/考务合同-v2.md"
_EXPECTED_CHECKS = {
    "input_exact",
    "provider_once",
    "projection_scope_visible",
    "hard_specificity_absent",
    "product_value_conflicts_absent",
    "authorized_quotes_only",
    "artifact_complete",
    "task_chain_complete",
    "selected_products_exact",
    "p5_qualified_masters_exact",
    "original_media_absent",
    "unconfirmed_composition_not_asserted",
    "store_error_source_absent",
    "first_draft_manual",
}


def _object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain one object")
    return cast(dict[str, Any], value)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--negative-evidence", type=Path)
    arguments = parser.parse_args()
    contract = load_exam_contract(_CONTRACT)
    cards = {card.card_id: card for card in contract.cards}
    if set(cards) != {"B11", "B12", "B16"}:
        raise RuntimeError("the E-1' public regression card set differs")
    if cards["B11"].product_ids != ("DIYU-CSPU-008", "DIYU-CSPU-001"):
        raise RuntimeError("B11 two-product operator binding differs")
    if {(item.product_id, item.media_id) for item in cards["B11"].master_bindings} != {
        ("DIYU-CSPU-008", "DIYU-V-011"),
        ("DIYU-CSPU-001", "DIYU-V-001"),
    }:
        raise RuntimeError("B11 qualified master pairing differs")
    if cards["B12"].product_ids != ("DIYU-CSPU-008",) or cards["B16"].product_ids != ("DIYU-CSPU-008",):
        raise RuntimeError("B12/B16 P2 operator binding differs")
    criteria = {criterion.check_id for card in contract.cards for criterion in card.criteria}
    if criteria != _EXPECTED_CHECKS or criteria != set(_CHECKS):
        raise RuntimeError("oracle implementation and frozen criterion set differ")
    if any(
        {"machine_hard", "structure", "high_risk_fact_boundary", "first_draft_usable"}
        - {criterion.gate for criterion in card.criteria}
        for card in contract.cards
    ):
        raise RuntimeError("one card is missing a four-ledger gate")
    readiness = readiness_document(repository_root=_ROOT, contract_path=_CONTRACT)
    if readiness["status"] != "PASS" or readiness["provider_requests"] != 0:
        raise RuntimeError("readiness did not remain zero-provider PASS")
    if arguments.negative_evidence is not None:
        negative = _object(arguments.negative_evidence)
        if (
            negative.get("status") != "PASS"
            or negative.get("provider_requests") != 0
            or negative.get("counts_before") != negative.get("counts_after")
            or any(value != 0 for value in cast(dict[str, int], negative.get("pollution_delta", {})).values())
        ):
            raise RuntimeError("negative suite called a provider or polluted task/run/version")
    print("freeze2 semantics PASS: cards=3 four_ledgers=4 readiness_provider=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
