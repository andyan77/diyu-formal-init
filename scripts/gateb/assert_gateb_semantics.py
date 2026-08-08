#!/usr/bin/env python3
"""Fail-closed structural assertions for Gate B's semantic contracts."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from src.shared.account_editorial_lens import (  # noqa: E402
    ACCOUNT_EDITORIAL_DEGRADED_REASONS,
    ACCOUNT_EDITORIAL_LENS_V4_VERSION,
    LENS_PRODUCTS,
)
from src.shared.product_value import P1_PRODUCT_DECISION_BASIS_VERSION  # noqa: E402
from src.shared.task_value_assembly import (  # noqa: E402
    BRAND_RELEVANCE_PATHS,
    BRAND_RELEVANCE_SOURCE_TYPES,
)

_PRODUCTS = frozenset(
    {
        "dressing_decision",
        "product_truth",
        "brand_life_narrative",
        "local_response",
        "visual_styling_story",
    }
)
_REASONS = (
    "unsupported_content_product",
    "account_profile_missing",
    "account_profile_identity_incomplete",
    "account_profile_not_confirmed",
    "brand_context_incompatible",
)
_PATHS = (
    "product_expertise",
    "existing_series",
    "audience_relationship",
    "brand_stance",
    "brand_visual",
    "local_trust",
    "organization_people",
)
_REQUIRED_TESTS = (
    "test_same_seed_cross_account_changes_semantics_not_facts_or_product_job",
    "test_p1_selected_product_freezes_v_facts_judgment_and_writer_basis",
    "test_p1_without_product_is_valid_and_product_path_is_only_unavailable",
    "test_p1_explicit_product_with_missing_or_ambiguous_basis_fails_closed",
    "test_each_brand_relevance_family_has_typed_consumed_evidence",
    "test_reserved_families_cannot_be_inferred_or_lose_qualification_refs",
    "test_no_natural_path_is_visible_and_does_not_change_life_topic_to_product",
    "test_formal_zero_model_vertical_uses_one_frozen_resolution_and_p1_basis",
)


def _source(root: Path, path: str) -> str:
    return (root / path).read_text(encoding="utf-8")


def _function_count(source: str, name: str) -> int:
    return sum(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
        for node in ast.walk(ast.parse(source))
    )


def _require(source: str, markers: tuple[str, ...], label: str) -> None:
    missing = [marker for marker in markers if marker not in source]
    if missing:
        raise SystemExit(f"Gate B semantics FAIL ({label}): missing {missing}")


def main() -> None:
    root = _ROOT
    if LENS_PRODUCTS != _PRODUCTS:
        raise SystemExit("Gate B semantics FAIL: lens product set is not exact P1-P5")
    reasons = tuple(reason.value for reason in ACCOUNT_EDITORIAL_DEGRADED_REASONS)
    if reasons != _REASONS:
        raise SystemExit("Gate B semantics FAIL: degraded reason set is not exact")
    if ACCOUNT_EDITORIAL_LENS_V4_VERSION != "account-editorial-lens-v4":
        raise SystemExit("Gate B semantics FAIL: new-task lens version is not V4")
    if BRAND_RELEVANCE_PATHS != _PATHS or set(BRAND_RELEVANCE_SOURCE_TYPES) != set(_PATHS):
        raise SystemExit("Gate B semantics FAIL: seven-family contract is incomplete")
    if P1_PRODUCT_DECISION_BASIS_VERSION != "product-decision-basis-v3":
        raise SystemExit("Gate B semantics FAIL: P1 decision contract version is missing")

    lens = _source(root, "src/shared/account_editorial_lens.py")
    service = _source(root, "src/brain/content_service.py")
    publication = _source(root, "src/shared/publication_contract.py")
    snapshot = _source(root, "src/brain/content_expression.py")
    writer = _source(root, "src/shared/writer_request.py")
    deepseek = _source(root, "src/tool/llm_gateway/deepseek.py")
    stub = _source(root, "src/tool/llm_gateway/stub.py")
    tests = _source(root, "tests/test_gateb_semantics.py")

    if _function_count(lens, "resolve_account_editorial_context") != 1:
        raise SystemExit("Gate B semantics FAIL: account semantic resolver is not unique")
    _require(
        service,
        (
            "resolve_account_editorial_context(",
            "account_editorial_resolution=account_resolution",
            "brand_relevance_state=assembly.brand_relevance_state",
            "ruleset=RULESET_V1",
        ),
        "ContentService",
    )
    _require(
        publication,
        (
            "account_editorial_resolution",
            "_assert_account_editorial_binding",
            "_assert_brand_relevance_binding",
        ),
        "PublicationContract",
    )
    _require(
        snapshot,
        ("publication_contract.account_editorial_resolution", "account_editorial_resolution_digest"),
        "snapshot",
    )
    _require(
        writer,
        (
            "account_editorial_context",
            "brand_relevance",
            "account_editorial_resolution_digest",
            "P1ProductDecisionBasisV3",
        ),
        "WriterRequest",
    )
    _require(deepseek, ("build_writer_request_v3(", "P1ProductDecisionBasisV3"), "DeepSeek adapter")
    _require(stub, ("build_writer_request_v3(", "P1ProductDecisionBasisV3"), "deterministic stub")
    _require(tests, _REQUIRED_TESTS, "Gate B tests")
    print("GATEB_SEMANTICS_OK products=5 reasons=5 paths=7 vertical=1 p1_paths=3")


if __name__ == "__main__":
    main()
