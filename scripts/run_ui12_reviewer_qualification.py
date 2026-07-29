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

from src.shared.closed_review import (
    CLOSED_REVIEW_DIMENSIONS,
    PRODUCT_REVIEW_DIMENSIONS,
    ClosedReviewAnswer,
    ClosedReviewAnswers,
    ClosedReviewQuestion,
    ReviewDimension,
    build_closed_review_questions,
    reconcile_closed_review_answers,
)
from src.shared.factual_basis import (
    ProductFactPacket,
    build_product_fact_packet,
)
from src.shared.review_evidence import (
    ClauseContextV2,
    ProtectedSubjectScopeV2,
    validate_server_owned_contexts_v2,
)
from src.shared.types import ProductFact
from src.tool.llm_gateway.deepseek import DeepSeekGenerator

_DEFAULT_FIXTURE = Path("tests/fixtures/ui12_reviewer_qualification_v1.json")
_REVIEWER_MODEL = "deepseek-v4-pro"
_WRITER_MODEL = "deepseek-v4-flash"
_ALL_DIMENSIONS = frozenset((*CLOSED_REVIEW_DIMENSIONS, *PRODUCT_REVIEW_DIMENSIONS))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the frozen UI-12 Reviewer-only semantic qualification.",
    )
    parser.add_argument("--fixture", type=Path, default=_DEFAULT_FIXTURE)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--implementation-sha", required=True)
    return parser.parse_args()


def _required_mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be an object")
    return cast(dict[str, Any], value)


def _required_list(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise TypeError(f"{label} must be an array")
    return value


def _required_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise TypeError(f"{label} must be a non-empty string")
    return value


def _string_tuple(value: object, label: str) -> tuple[str, ...]:
    raw = _required_list(value, label)
    if any(not isinstance(item, str) or not item for item in raw):
        raise TypeError(f"{label} must contain non-empty strings")
    return tuple(cast(list[str], raw))


def _qualification_product() -> ProductFact:
    return ProductFact(
        sku="ZX-C218",
        display_name="双面短外套",
        facts={
            "entity_kind": "apparel_product",
            "category": "外套",
        },
        source_kind="verified_product_record",
        source_note="UI-12 冻结资格夹具",
        fact_version=1,
        applicability="qualification_only",
    )


def _packet(enabled: bool) -> ProductFactPacket | None:
    return build_product_fact_packet((_qualification_product(),)) if enabled else None


def _bundle_contexts(
    bundle: dict[str, Any],
    packet: ProductFactPacket | None,
) -> tuple[
    tuple[ClauseContextV2, ...],
    dict[str, str],
    dict[str, dict[str, Any]],
]:
    actuality_facts = _string_tuple(bundle.get("actuality_facts"), "actuality_facts")
    fact_text_by_id = {
        f"source:user_actuality:{index}": text
        for index, text in enumerate(actuality_facts, start=1)
    }
    if packet is not None:
        fact_text_by_id.update(
            {
                item.fact_id: item.canonical_text
                for item in packet.facts
            }
        )
    contexts: list[ClauseContextV2] = []
    samples_by_clause: dict[str, dict[str, Any]] = {}
    for visible_order, raw_sample in enumerate(
        _required_list(bundle.get("samples"), "samples"),
        start=1,
    ):
        sample = _required_mapping(raw_sample, "sample")
        sample_id = _required_string(sample.get("sample_id"), "sample_id")
        clause_key = sample.get("consistency_key") or sample_id
        clause_id = f"qualification:{_required_string(clause_key, 'clause_key')}"
        if clause_id in samples_by_clause:
            raise ValueError(f"duplicate clause id in bundle: {clause_id}")
        fact_ref = sample.get("fact_ref")
        if fact_ref is not None and not isinstance(fact_ref, str):
            raise TypeError("fact_ref must be a string or null")
        context = ClauseContextV2(
            clause_id=clause_id,
            unit_id=f"unit:{sample_id}",
            exact_text=_required_string(sample.get("exact_text"), "exact_text"),
            visible_order=visible_order,
            text_source=_required_string(sample.get("text_source"), "text_source"),  # type: ignore[arg-type]
            unit_contract=_required_string(sample.get("unit_contract"), "unit_contract"),  # type: ignore[arg-type]
            speaker_kind="institutional_account",
            fact_ref=fact_ref,
        )
        contexts.append(context)
        samples_by_clause[clause_id] = sample
    return tuple(contexts), fact_text_by_id, samples_by_clause


def _answer_by_question(
    questions: tuple[ClosedReviewQuestion, ...],
    answers: ClosedReviewAnswers,
) -> dict[str, ClosedReviewAnswer]:
    if len(questions) != len(answers.answers):
        raise ValueError("answer count drifted from the closed question set")
    return {
        question.question_id: answer
        for question, answer in zip(questions, answers.answers, strict=True)
    }


def _expected_present(sample: dict[str, Any]) -> dict[str, tuple[str, ...]]:
    raw_present = _required_mapping(sample.get("present"), "present")
    present: dict[str, tuple[str, ...]] = {}
    for raw_dimension, raw_operands in raw_present.items():
        if raw_dimension not in _ALL_DIMENSIONS:
            raise ValueError(f"unknown expected dimension: {raw_dimension}")
        present[raw_dimension] = _string_tuple(
            raw_operands,
            f"present.{raw_dimension}",
        )
    return present


def _qualification_mismatches(
    *,
    samples_by_clause: dict[str, dict[str, Any]],
    questions: tuple[ClosedReviewQuestion, ...],
    answers: ClosedReviewAnswers,
    issues_by_unit: dict[str, tuple[str, ...]],
) -> list[dict[str, object]]:
    answer_by_id = _answer_by_question(questions, answers)
    question_by_clause: dict[str, list[ClosedReviewQuestion]] = defaultdict(list)
    for question in questions:
        question_by_clause[question.clause_id].append(question)
    mismatches: list[dict[str, object]] = []
    for clause_id, sample in samples_by_clause.items():
        expected_present = _expected_present(sample)
        expected_uncertain = frozenset(
            _string_tuple(sample.get("uncertain"), "uncertain")
        )
        explicit_absent = frozenset(
            _string_tuple(sample.get("absent"), "absent")
        )
        if (
            set(expected_present) & expected_uncertain
            or set(expected_present) & explicit_absent
            or expected_uncertain & explicit_absent
        ):
            raise ValueError(f"overlapping oracle dimensions for {clause_id}")
        actual_signature: dict[str, tuple[str, tuple[str, ...]]] = {}
        for question in question_by_clause.get(clause_id, []):
            answer = answer_by_id[question.question_id]
            actual_signature[question.dimension] = (
                answer.status,
                answer.operands,
            )
            expected_status = (
                "present"
                if question.dimension in expected_present
                else "uncertain"
                if question.dimension in expected_uncertain
                else "absent"
            )
            expected_operands = (
                expected_present.get(question.dimension, ())
                if expected_status == "present"
                else ()
            )
            if answer.status != expected_status or (
                expected_status == "present"
                and frozenset(answer.operands) != frozenset(expected_operands)
            ):
                mismatches.append(
                    {
                        "sample_id": sample["sample_id"],
                        "dimension": question.dimension,
                        "expected_status": expected_status,
                        "expected_operands": list(expected_operands),
                        "actual_status": answer.status,
                        "actual_operands": list(answer.operands),
                    }
                )
        expected_ruling = _required_string(
            sample.get("expected_ruling"),
            "expected_ruling",
        )
        unit_id = f"unit:{sample['sample_id']}"
        actual_reasons = issues_by_unit.get(unit_id, ())
        ruling_matches = (
            not actual_reasons
            if expected_ruling == "allow"
            else "insufficient_evidence" in actual_reasons
            if expected_ruling == "insufficient_evidence"
            else bool(actual_reasons)
            if expected_ruling == "reject"
            else False
        )
        if not ruling_matches:
            mismatches.append(
                {
                    "sample_id": sample["sample_id"],
                    "dimension": "server_ruling",
                    "expected_status": expected_ruling,
                    "expected_operands": [],
                    "actual_status": (
                        "allow" if not actual_reasons else ",".join(actual_reasons)
                    ),
                    "actual_operands": [],
                }
            )
        sample["_actual_signature"] = actual_signature
    return mismatches


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
        raise FileExistsError("qualification output directory must be empty")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(stat.S_IRWXU)


def main() -> int:
    args = _parse_args()
    api_base_url = os.environ.get("DEEPSEEK_API_BASE_URL", "").strip()
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    configured_reviewer = os.environ.get(
        "DEEPSEEK_REVIEWER_MODEL",
        "",
    ).strip()
    if not api_base_url or not api_key:
        raise RuntimeError("protected DeepSeek configuration is unavailable")
    if configured_reviewer != _REVIEWER_MODEL:
        raise RuntimeError("Reviewer qualification requires deepseek-v4-pro")
    fixture_bytes = args.fixture.read_bytes()
    fixture = _required_mapping(
        json.loads(fixture_bytes),
        "fixture",
    )
    if fixture.get("qualification_version") != "ui12-reviewer-qualification-v1":
        raise ValueError("unexpected qualification version")
    _safe_output_directory(args.output_dir)
    generator = DeepSeekGenerator(
        api_base_url=api_base_url,
        api_key=api_key,
        model=_WRITER_MODEL,
        reviewer_model=_REVIEWER_MODEL,
        max_retries=0,
    )
    qualification_started = time.monotonic()
    records: list[dict[str, object]] = []
    consistency: dict[str, list[dict[str, tuple[str, tuple[str, ...]]]]] = defaultdict(list)
    all_mismatches: list[dict[str, object]] = []

    for raw_bundle in _required_list(fixture.get("bundles"), "bundles"):
        bundle = _required_mapping(raw_bundle, "bundle")
        bundle_id = _required_string(bundle.get("bundle_id"), "bundle_id")
        packet = _packet(bundle.get("product_scope") is True)
        contexts, fact_text_by_id, samples_by_clause = _bundle_contexts(
            bundle,
            packet,
        )
        structural_issues = validate_server_owned_contexts_v2(
            contexts=contexts,
            fact_text_by_id=fact_text_by_id,
        )
        questions = build_closed_review_questions(
            contexts,
            product_fact_packet=packet,
        )
        if not questions:
            if structural_issues:
                all_mismatches.append(
                    {
                        "bundle_id": bundle_id,
                        "dimension": "server_owned_structure",
                        "issues": [
                            {
                                "target_id": issue.target_id,
                                "reason": issue.reason,
                            }
                            for issue in structural_issues
                        ],
                    }
                )
            records.append(
                {
                    "bundle_id": bundle_id,
                    "partition": bundle["partition"],
                    "reviewer_call_count": 0,
                    "question_count": 0,
                    "result": "pass" if not structural_issues else "fail",
                }
            )
            continue

        prompt = generator._kernel_reviewer_prompt(
            questions=questions,
            contexts=tuple(
                context
                for context in contexts
                if context.text_source == "writer_unit"
            ),
            actuality_facts=tuple(
                (fact_id, text)
                for fact_id, text in fact_text_by_id.items()
                if fact_id.startswith("source:user_actuality:")
            ),
            protected_subjects=_string_tuple(
                bundle.get("protected_subjects"),
                "protected_subjects",
            ),
        )
        started = time.monotonic()
        raw_payload, retry_count = generator._request_strict_review(
            "你是独立 CreativeKernel 风险问题回答器。只回答服务端给出的闭合问题，不决定事实许可或通过失败，"
            "不回传或改写正文，只调用指定函数一次。",
            prompt,
            question_count=len(questions),
            questions=questions,
            timeout_seconds=120.0,
        )
        elapsed_ms = int((time.monotonic() - started) * 1000)
        raw_path = args.output_dir / f"{bundle_id}.raw.json"
        raw_sha256 = _write_json(raw_path, raw_payload)
        answers = generator._strict_review_answers(
            raw_payload,
            questions=questions,
        )
        protected = ProtectedSubjectScopeV2(
            exact_names=_string_tuple(
                bundle.get("protected_subjects"),
                "protected_subjects",
            ),
            speaker_kind="institutional_account",
        )
        result = reconcile_closed_review_answers(
            contexts=contexts,
            questions=questions,
            answers=answers,
            fact_text_by_id=fact_text_by_id,
            protected_subjects=protected,
            product_fact_packet=packet,
        )
        issues_by_unit: dict[str, tuple[str, ...]] = {
            unit_id: tuple(
                issue.reason
                for issue in result.issues
                if issue.target_id == unit_id
            )
            for unit_id in {
                context.unit_id
                for context in contexts
            }
        }
        mismatches = _qualification_mismatches(
            samples_by_clause=samples_by_clause,
            questions=questions,
            answers=answers,
            issues_by_unit=issues_by_unit,
        )
        for mismatch in mismatches:
            mismatch["bundle_id"] = bundle_id
        all_mismatches.extend(mismatches)
        for sample in samples_by_clause.values():
            consistency_key = sample.get("consistency_key")
            if isinstance(consistency_key, str):
                consistency[consistency_key].append(
                    cast(
                        dict[str, tuple[str, tuple[str, ...]]],
                        sample.pop("_actual_signature"),
                    )
                )
            else:
                sample.pop("_actual_signature", None)
        usage = raw_payload.get("usage")
        records.append(
            {
                "bundle_id": bundle_id,
                "partition": bundle["partition"],
                "reviewer_call_count": 1,
                "question_count": len(questions),
                "retry_count": retry_count,
                "latency_ms": elapsed_ms,
                "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                "raw_sha256": raw_sha256,
                "usage": usage if isinstance(usage, dict) else {},
                "result": "pass" if not mismatches else "fail",
            }
        )

    for key, signatures in consistency.items():
        if len(signatures) != 2 or signatures[0] != signatures[1]:
            all_mismatches.append(
                {
                    "consistency_key": key,
                    "dimension": "cross_bundle_consistency",
                    "signature_count": len(signatures),
                }
            )
    summary = {
        "qualification_version": fixture["qualification_version"],
        "implementation_sha": args.implementation_sha,
        "fixture_sha256": hashlib.sha256(fixture_bytes).hexdigest(),
        "writer_model": _WRITER_MODEL,
        "reviewer_model": _REVIEWER_MODEL,
        "temperature": 0,
        "max_retries": 0,
        "thinking": "disabled",
        "strict_function_transport": True,
        "bundle_records": records,
        "mismatches": all_mismatches,
        "elapsed_ms": int((time.monotonic() - qualification_started) * 1000),
        "result": "pass" if not all_mismatches else "fail",
    }
    _write_json(args.output_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0 if not all_mismatches else 1


if __name__ == "__main__":
    raise SystemExit(main())
