from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from src.infrastructure.system_asset_catalog import validate_system_asset_governance

_GOVERNANCE = (
    Path(__file__).resolve().parents[1]
    / "首批领域数据库知识数据"
    / "第五批：评测与导入包"
    / "12-系统资产运行治理-v1.json"
)


def test_governance_fails_closed_for_source_lifecycle_and_fixture_binding(tmp_path: Path) -> None:
    governance = json.loads(_GOVERNANCE.read_text(encoding="utf-8"))
    candidate = tmp_path / "governance.json"
    candidate.write_text(json.dumps(governance, ensure_ascii=False), encoding="utf-8")
    validated, records = validate_system_asset_governance(candidate, _GOVERNANCE.parents[2])
    assert len(records) == 243
    assert len(validated.assets) == 41

    for field, value in (
        ("sha256", "not-a-source-sha"),
        ("lifecycle", "retired"),
        ("valid_until", "2000-01-01"),
        ("superseded_by", "UNKNOWN-ASSET"),
        ("superseded_by", "B-TPO-001"),
    ):
        changed = deepcopy(governance)
        target = changed["candidate_source"] if field == "sha256" else changed["assets"][0]
        target[field] = value
        candidate.write_text(json.dumps(changed, ensure_ascii=False), encoding="utf-8")
        with pytest.raises(RuntimeError):
            validate_system_asset_governance(candidate, _GOVERNANCE.parents[2])
