from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_GENERATOR = _REPOSITORY_ROOT / "scripts" / "exev0" / "build_fixed_samples.py"
_MANIFEST = _REPOSITORY_ROOT / "docs" / "EXE-V0" / "固定样本对照.json"
_ONBOARDING_PROFILE = _REPOSITORY_ROOT / "config" / "onboarding" / "diyu-m7-2b-prefill-v1.json"


def test_the_committed_fixed_samples_still_reproduce_byte_for_byte() -> None:
    result = subprocess.run(
        [sys.executable, str(_GENERATOR)],
        cwd=_REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_the_sample_matrix_covers_the_shapes_the_package_promised() -> None:
    manifest = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    rows = manifest["rows"]

    assert manifest["six_topic_kinds_distinct"] == 6
    assert {row["content_product"] for row in rows} == {
        "dressing_decision",
        "product_truth",
        "brand_life_narrative",
        "local_response",
        "visual_styling_story",
    }
    assert {row["topic_origin"] for row in rows} == {"explicit_user", "system_selected"}
    assert {row["product_basis_present"] for row in rows} == {True, False}
    assert {row["series_basis_present"] for row in rows} == {True, False}
    assert len({row["profile_id"] for row in rows}) >= 2
    assert {"design", "holdout", "fallback"} <= {row["profile_role"] for row in rows}
    assert any(row["payoff_origin"] == "static_fallback" for row in rows)
    assert manifest["production_profile_calibration"] == "UNVERIFIED"


def test_no_account_profile_sentence_was_written_into_the_repository() -> None:
    onboarding = json.loads(_ONBOARDING_PROFILE.read_text(encoding="utf-8"))
    segments = onboarding["account_profiles"][0]["segments"]
    published = (
        _MANIFEST.read_text(encoding="utf-8")
        + (_REPOSITORY_ROOT / "docs" / "EXE-V0" / "固定样本对照.md").read_text(encoding="utf-8")
    )

    for segment in segments.values():
        assert str(segment) not in published
