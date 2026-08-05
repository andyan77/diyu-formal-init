from __future__ import annotations

import json
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pytest

from src.brain.input_role_resolver import resolve_input_roles
from src.shared.errors import DomainError
from src.shared.intake_contract import (
    parse_live_intake_role_projection,
    replay_legacy_intake_role_projection,
)
from src.shared.narrative import user_fact_candidates
from src.shared.publication_contract import INTAKE_ROLE_CONTRACT_VERSION
from src.tool.replay_tenant01_intake_failure import replay
from src.tool.tenant01_evidence import (
    Tenant01EvidenceError,
    assert_failed_generation_gate_evaluation,
    failed_generation_gate_evaluation,
)

_MESSAGE = "早上有点凉，中午又热，我不想带太多东西，今天怎么穿更稳妥？"


def _roles() -> list[dict[str, str]]:
    candidates = user_fact_candidates((_MESSAGE,))
    return [
        {
            "sentence_id": candidate.source_id,
            "role": "creation_instruction" if index == 3 else "observable_actuality",
        }
        for index, candidate in enumerate(candidates)
    ]


def test_live_intake_roles_are_the_only_fact_selection_authority() -> None:
    candidates = user_fact_candidates((_MESSAGE,))
    projection = parse_live_intake_role_projection(
        {"user_sentence_roles": _roles()},
        candidates,
    )
    resolution = resolve_input_roles(
        user_turns=(_MESSAGE,),
        candidates=candidates,
        roles=dict(projection.roles),
        contract_version=projection.contract_version,
    )

    assert projection.contract_version == INTAKE_ROLE_CONTRACT_VERSION
    assert projection.actuality_source_ids == tuple(candidate.source_id for candidate in candidates[:3])
    assert projection.instruction_source_ids == (candidates[3].source_id,)
    assert resolution.actuality_texts == tuple(candidate.exact_text for candidate in candidates[:3])
    assert resolution.instruction_source_ids == (candidates[3].source_id,)


@pytest.mark.parametrize("deleted_field", ("user_fact_sentence_ids", "user_instruction_sentence_ids"))
def test_live_intake_strictly_rejects_deleted_duplicate_fields(deleted_field: str) -> None:
    candidates = user_fact_candidates((_MESSAGE,))
    document: dict[str, object] = {
        "user_sentence_roles": _roles(),
        deleted_field: [candidate.source_id for candidate in candidates],
    }

    with pytest.raises(DomainError, match="已删除"):
        parse_live_intake_role_projection(document, candidates)


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("missing", "未完整覆盖"),
        ("duplicate", "重复候选"),
        ("reordered", "改变了冻结候选顺序"),
        ("unknown", "未知候选"),
        ("illegal_role", "非法角色"),
    ),
)
def test_intake_role_projection_mutations_fail_closed(mutation: str, message: str) -> None:
    candidates = user_fact_candidates((_MESSAGE,))
    roles = _roles()
    if mutation == "missing":
        roles.pop()
    elif mutation == "duplicate":
        roles[-1] = deepcopy(roles[0])
    elif mutation == "reordered":
        roles[0], roles[1] = roles[1], roles[0]
    elif mutation == "unknown":
        roles[0]["sentence_id"] = "source:user_actuality:unknown"
    elif mutation == "illegal_role":
        roles[0]["role"] = "trusted_fact"

    with pytest.raises(DomainError, match=message):
        parse_live_intake_role_projection({"user_sentence_roles": roles}, candidates)


def test_legacy_replay_ignores_conflicting_fact_lists_instead_of_merging_them() -> None:
    candidates = user_fact_candidates((_MESSAGE,))
    base: dict[str, object] = {
        "user_sentence_roles": _roles(),
        "user_fact_sentence_ids": [candidate.source_id for candidate in candidates],
    }
    union_mutation = deepcopy(base)
    union_mutation["user_fact_sentence_ids"] = [
        *[candidate.source_id for candidate in candidates],
        "source:user_actuality:invented",
    ]
    intersection_mutation = deepcopy(base)
    intersection_mutation["user_fact_sentence_ids"] = [candidates[0].source_id]

    projections = tuple(
        replay_legacy_intake_role_projection(document, candidates)
        for document in (base, union_mutation, intersection_mutation)
    )

    assert all(projection.legacy_replay for projection in projections)
    assert len({projection.actuality_source_ids for projection in projections}) == 1
    assert projections[0].actuality_source_ids == tuple(candidate.source_id for candidate in candidates[:3])
    assert projections[0].instruction_source_ids == (candidates[3].source_id,)


def test_pre_artifact_protocol_failure_cannot_be_recorded_as_product_gate_failures() -> None:
    expected = failed_generation_gate_evaluation()
    assert expected == {
        "protocol_contract": "FAIL",
        "machine_hard": "NOT_EVALUABLE",
        "structure": "NOT_EVALUABLE",
        "human_high_risk_boundary": "NOT_EVALUABLE",
        "product_usable": "NOT_EVALUABLE",
    }
    assert_failed_generation_gate_evaluation(expected)

    mutation = dict(expected, machine_hard="FAIL", structure="FAIL")
    with pytest.raises(Tenant01EvidenceError, match="错误记入"):
        assert_failed_generation_gate_evaluation(mutation)


def test_legacy_raw_replay_uses_roles_without_calling_a_model(tmp_path: Path) -> None:
    raw_path = tmp_path / "P1.failed.raw.json"
    config_path = tmp_path / "golden-v1.json"
    legacy_document = {
        "user_sentence_roles": _roles(),
        "user_fact_sentence_ids": [
            candidate.source_id
            for candidate in user_fact_candidates((_MESSAGE,))
        ],
    }
    raw_path.write_text(
        json.dumps(
            {
                "card_id": "P1",
                "request_count": 1,
                "responses": [
                    {
                        "stage": "intake",
                        "response": {
                            "choices": [
                                {"message": {"content": json.dumps(legacy_document)}}
                            ]
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    config_path.write_text(
        json.dumps({"cards": [{"card_id": "P1", "message": _MESSAGE}]}),
        encoding="utf-8",
    )
    raw_sha256 = sha256(raw_path.read_bytes()).hexdigest()

    result = replay(
        raw_path=raw_path,
        config_path=config_path,
        expected_raw_sha256=raw_sha256,
        candidate_sha="a" * 40,
    )

    assert result["provider_request_count"] == 0
    assert result["source_raw_sha256_before"] == result["source_raw_sha256_after"]
    assert result["legacy_duplicate_field_authoritative"] is False
    assert result["derived_actuality_source_ids"] == [
        candidate.source_id
        for candidate in user_fact_candidates((_MESSAGE,))[:3]
    ]
