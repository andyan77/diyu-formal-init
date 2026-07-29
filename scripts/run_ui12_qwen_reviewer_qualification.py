from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, cast

from scripts.run_ui12_reviewer_qualification import (
    _bundle_contexts,
    _packet,
    _required_list,
    _required_mapping,
    _required_string,
    _string_tuple,
)
from src.ports.reviewer_provider import ReviewerProviderFailure
from src.shared.clause_license import (
    ClauseLicenseReviewV1,
    UnitClauseLicensePolicyV1,
    build_unit_clause_license_policies_v1,
    materialize_clause_licenses_v1,
    reconcile_clause_license_reviews_v1,
)
from src.shared.factual_basis import build_product_fact_packet
from src.shared.narrative import NarrativeIssue, new_frame
from src.shared.review_evidence import (
    ClauseContextV2,
    UnitContractV2,
    validate_server_owned_contexts_v2,
    writer_clause_contexts_v2,
)
from src.tool.llm_gateway.deepseek import DeepSeekGenerator
from src.tool.llm_gateway.qwen_reviewer import QwenReviewerProvider

_DEFAULT_FIXTURE = Path(
    "tests/fixtures/ui12_reviewer_qualification_v1.json"
)
_REVIEWER_MODEL = "qwen3.7-max-2026-05-20"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the frozen UI-12 ClauseLicense qualification against the "
            "single Qwen Reviewer candidate."
        ),
    )
    parser.add_argument("--fixture", type=Path, default=_DEFAULT_FIXTURE)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--implementation-sha", required=True)
    return parser.parse_args()


def _mode_for_contract(contract: UnitContractV2) -> str:
    if contract == "actuality_reflection":
        return "actuality_reflection"
    if contract == "hypothetical_example":
        return "hypothesis"
    if contract == "disclosed_dramatization":
        return "dramatization"
    return "general_observation"


def _policies(
    contexts: tuple[ClauseContextV2, ...],
    *,
    actuality_facts: tuple[str, ...],
) -> tuple[UnitClauseLicensePolicyV1, ...]:
    policies: list[UnitClauseLicensePolicyV1] = []
    seen_units: set[str] = set()
    for context in writer_clause_contexts_v2(contexts):
        if context.unit_id in seen_units:
            continue
        mode = _mode_for_contract(context.unit_contract)
        frame = new_frame(
            cast(Any, mode),
            actuality_facts if mode == "actuality_reflection" else (),
            (),
        )
        policy = build_unit_clause_license_policies_v1(
            frame=frame,
            unit_contracts={
                context.unit_id: context.unit_contract,
            },
        )
        if len(policy) != 1:
            raise ValueError("qualification unit policy is incomplete")
        policies.extend(policy)
        seen_units.add(context.unit_id)
    return tuple(policies)


def _actual_ruling(
    *,
    issues: tuple[NarrativeIssue, ...],
) -> str:
    if not issues:
        return "allow"
    if any(issue.reason == "insufficient_evidence" for issue in issues):
        return "insufficient_evidence"
    return "reject"


def _write_json(path: Path, value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode()
    path.write_bytes(payload)
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return hashlib.sha256(payload).hexdigest()


def _safe_output_directory(path: Path) -> None:
    if path.exists() and any(path.iterdir()):
        raise FileExistsError(
            "qualification output directory must be empty"
        )
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(stat.S_IRWXU)


def _review_signature(
    reviews: tuple[ClauseLicenseReviewV1, ...],
) -> dict[str, tuple[object, ...]]:
    return {
        review.clause_id: (
            review.expression_type,
            tuple(
                (check.binding_id, check.status)
                for check in review.binding_checks
            ),
            review.unsupported_quote,
        )
        for review in reviews
    }


def main() -> int:
    args = _parse_args()
    api_base_url = os.environ.get(
        "QWEN_REVIEWER_API_BASE_URL",
        "",
    ).strip()
    api_key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
    configured_model = os.environ.get(
        "QWEN_REVIEWER_MODEL",
        "",
    ).strip()
    if not api_base_url or not api_key:
        raise RuntimeError(
            "protected Qwen Reviewer configuration is unavailable"
        )
    if configured_model != _REVIEWER_MODEL:
        raise RuntimeError(
            "Reviewer qualification requires the frozen Qwen snapshot"
        )
    fixture_bytes = args.fixture.read_bytes()
    fixture = _required_mapping(
        json.loads(fixture_bytes),
        "fixture",
    )
    if fixture.get("qualification_version") != (
        "ui12-reviewer-qualification-v1"
    ):
        raise ValueError("unexpected qualification version")
    _safe_output_directory(args.output_dir)
    provider = QwenReviewerProvider(
        api_base_url=api_base_url,
        api_key=api_key,
        model=configured_model,
    )
    started = time.monotonic()
    records: list[dict[str, object]] = []
    mismatches: list[dict[str, object]] = []
    consistency: dict[
        str,
        list[dict[str, tuple[object, ...]]],
    ] = defaultdict(list)
    for raw_bundle in _required_list(
        fixture.get("bundles"),
        "bundles",
    ):
        bundle = _required_mapping(raw_bundle, "bundle")
        bundle_id = _required_string(
            bundle.get("bundle_id"),
            "bundle_id",
        )
        packet = _packet(bundle.get("product_scope") is True)
        contexts, fact_text_by_id, samples_by_clause = _bundle_contexts(
            bundle,
            packet,
        )
        source_issues = validate_server_owned_contexts_v2(
            contexts=contexts,
            fact_text_by_id=fact_text_by_id,
        )
        writer_contexts = writer_clause_contexts_v2(contexts)
        if not writer_contexts:
            structural_expectations = {
                _required_string(
                    sample.get("expected_ruling"),
                    "expected_ruling",
                )
                for sample in samples_by_clause.values()
            }
            passed = not source_issues and structural_expectations == {
                "structurally_valid"
            }
            if not passed:
                mismatches.append(
                    {
                        "bundle_id": bundle_id,
                        "reason": "server_owned_structure",
                    }
                )
            records.append(
                {
                    "bundle_id": bundle_id,
                    "partition": bundle["partition"],
                    "reviewer_call_count": 0,
                    "clause_count": 0,
                    "result": "pass" if passed else "fail",
                }
            )
            continue
        actuality_facts = _string_tuple(
            bundle.get("actuality_facts"),
            "actuality_facts",
        )
        policies = _policies(
            contexts,
            actuality_facts=actuality_facts,
        )
        licenses = materialize_clause_licenses_v1(
            contexts=contexts,
            policies=policies,
        )
        if packet is None:
            packet = build_product_fact_packet(())
        prompt = DeepSeekGenerator._kernel_license_reviewer_prompt(
            licenses=licenses,
            contexts=writer_contexts,
            actuality_facts=tuple(
                (fact_id, text)
                for fact_id, text in fact_text_by_id.items()
                if fact_id.startswith("source:user_actuality:")
            ),
            protected_subjects=_string_tuple(
                bundle.get("protected_subjects"),
                "protected_subjects",
            ),
            product_fact_packet=packet,
        )
        bundle_started = time.monotonic()
        try:
            provider_result = provider.review(
                system_prompt=(
                    "你是独立 CreativeKernel clause 许可证支持核对器。"
                    "只核对文字是否完全符合服务端既定许可，不决定事实许可、"
                    "通过失败、保存、重试、修复或制作资源，只调用指定函数一次。"
                ),
                user_prompt=prompt,
                licenses=licenses,
                timeout_seconds=300.0,
            )
        except ReviewerProviderFailure as exc:
            if exc.raw_payload is None:
                raise
            raw_sha256 = _write_json(
                args.output_dir / f"{bundle_id}.raw.json",
                exc.raw_payload,
            )
            mismatch = {
                "bundle_id": bundle_id,
                "reason": "provider_response_invalid",
            }
            mismatches.append(mismatch)
            records.append(
                {
                    "bundle_id": bundle_id,
                    "partition": bundle["partition"],
                    "reviewer_call_count": 1,
                    "clause_count": len(licenses),
                    "retry_count": 0,
                    "latency_ms": int(
                        (time.monotonic() - bundle_started) * 1000
                    ),
                    "prompt_sha256": hashlib.sha256(
                        prompt.encode()
                    ).hexdigest(),
                    "raw_sha256": raw_sha256,
                    "usage": {},
                    "result": "fail",
                }
            )
            continue
        raw_path = args.output_dir / f"{bundle_id}.raw.json"
        raw_sha256 = _write_json(
            raw_path,
            provider_result.raw_payload,
        )
        result = reconcile_clause_license_reviews_v1(
            contexts=contexts,
            policies=policies,
            licenses=licenses,
            reviews=provider_result.reviews,
            fact_text_by_id=fact_text_by_id,
            product_fact_packet=packet,
        )
        issues_by_unit = {
            context.unit_id: tuple(
                issue
                for issue in result.issues
                if issue.target_id == context.unit_id
            )
            for context in writer_contexts
        }
        bundle_mismatches: list[dict[str, object]] = []
        review_by_clause = {
            review.clause_id: review
            for review in provider_result.reviews.reviews
        }
        for clause_id, sample in samples_by_clause.items():
            expected_ruling = _required_string(
                sample.get("expected_ruling"),
                "expected_ruling",
            )
            actual = _actual_ruling(
                issues=issues_by_unit.get(
                    f"unit:{sample['sample_id']}",
                    (),
                ),
            )
            if expected_ruling != actual:
                bundle_mismatches.append(
                    {
                        "sample_id": sample["sample_id"],
                        "expected": expected_ruling,
                        "actual": actual,
                    }
                )
            review = review_by_clause.get(clause_id)
            expected_uncertain = _string_tuple(
                sample.get("uncertain"),
                "uncertain",
            )
            if review is not None:
                has_uncertain = any(
                    check.status == "uncertain"
                    for check in review.binding_checks
                )
                if bool(expected_uncertain) != has_uncertain:
                    bundle_mismatches.append(
                        {
                            "sample_id": sample["sample_id"],
                            "expected": (
                                "uncertain"
                                if expected_uncertain
                                else "clear"
                            ),
                            "actual": review.verdict,
                        }
                    )
        for mismatch in bundle_mismatches:
            mismatch["bundle_id"] = bundle_id
        mismatches.extend(bundle_mismatches)
        review_signatures = _review_signature(
            provider_result.reviews.reviews,
        )
        for clause_id, sample in samples_by_clause.items():
            consistency_key = sample.get("consistency_key")
            if isinstance(consistency_key, str):
                consistency[consistency_key].append(
                    {clause_id: review_signatures[clause_id]}
                )
        usage = provider_result.raw_payload.get("usage")
        records.append(
            {
                "bundle_id": bundle_id,
                "partition": bundle["partition"],
                "reviewer_call_count": 1,
                "clause_count": len(licenses),
                "retry_count": provider_result.retry_count,
                "latency_ms": int(
                    (time.monotonic() - bundle_started) * 1000
                ),
                "prompt_sha256": hashlib.sha256(
                    prompt.encode()
                ).hexdigest(),
                "raw_sha256": raw_sha256,
                "usage": usage if isinstance(usage, dict) else {},
                "result": (
                    "pass" if not bundle_mismatches else "fail"
                ),
            }
        )
    for key, consistency_signatures in consistency.items():
        normalized = [
            next(iter(signature.values()))
            for signature in consistency_signatures
        ]
        if len(normalized) != 2 or normalized[0] != normalized[1]:
            mismatches.append(
                {
                    "consistency_key": key,
                    "reason": "cross_bundle_consistency",
                }
            )
    summary = {
        "qualification_version": fixture["qualification_version"],
        "implementation_sha": args.implementation_sha,
        "fixture_sha256": hashlib.sha256(
            fixture_bytes
        ).hexdigest(),
        "reviewer_provider": provider.provider_name,
        "reviewer_model": provider.model_name,
        "reasoning_effort": "high",
        "max_retries": 0,
        "transport": "responses_single_function_fail_closed_auto_choice",
        "bundle_records": records,
        "mismatches": mismatches,
        "elapsed_ms": int((time.monotonic() - started) * 1000),
        "result": "pass" if not mismatches else "fail",
    }
    _write_json(args.output_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0 if not mismatches else 1


if __name__ == "__main__":
    raise SystemExit(main())
