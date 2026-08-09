#!/usr/bin/env python3
"""Freeze the eight E-1' objects after engineering and CI evidence are complete."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, cast

_ROOT = Path(__file__).resolve().parents[2]
_EXPECTED_CANDIDATE = "bb9e63daa4558b9b202465d148b43d7c92a83266"
_GATE_A_MANIFEST_DIGEST = "14fed12141dc3b277c09c878a2a30ef71b445ce8ea31457c0122b403aeb48a06"
_MEDIA_MANIFEST_DIGEST = "587d821315d896c414b382a1f277a07e1f7290f95cb8e0d829334cc53efc335b"
_QUALITY_SOURCE_DIGEST = "62b43ff4ba93f6856b50c95486574a7b2ec966669b4d828fc18b0c2894fb1d7a"
_WRITER_VERSION = "publication-contract-v3 / ADJ-CONTENT-TERRITORY-01"
_RULE_VERSION = "immutable-product-fact-renderer-v3 / ADJ-WRITER-BOUNDARY-05"


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain one JSON object")
    return cast(dict[str, Any], value)


def _source_map(paths: tuple[str, ...]) -> dict[str, str]:
    return {path: _file_digest(_ROOT / path) for path in paths}


def _assert_candidate(candidate_sha: str) -> None:
    if candidate_sha != _EXPECTED_CANDIDATE:
        raise RuntimeError("E-1' candidate is not the re-signed mainline baseline")
    runtime_paths = (
        "src",
        "frontend",
        "alembic",
        "deploy",
        "Dockerfile",
        "pyproject.toml",
        "uv.lock",
    )
    changed = subprocess.run(
        ("git", "diff", "--name-only", candidate_sha, "--", *runtime_paths),
        cwd=_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    if changed:
        raise RuntimeError(f"runtime/configuration differs from the frozen candidate: {changed}")


def build_receipt(
    *,
    candidate_sha: str,
    image_binding_path: Path,
    setup_evidence_path: Path,
    ci_evidence_path: Path,
) -> dict[str, object]:
    _assert_candidate(candidate_sha)
    image = _load(image_binding_path)
    setup = _load(setup_evidence_path)
    ci = _load(ci_evidence_path)
    if (
        image.get("implementation_sha") != candidate_sha
        or image.get("build_count") != 1
        or not str(image.get("image_digest", "")).startswith("sha256:")
    ):
        raise RuntimeError("build-once image binding differs from the candidate")
    if (
        ci.get("event") != "workflow_dispatch"
        or ci.get("head_sha") != str(ci.get("branch_head_sha"))
        or ci.get("conclusion") != "success"
        or ci.get("non_success_steps") != 0
    ):
        raise RuntimeError("CI four-check evidence is incomplete")
    if (
        setup.get("status") != "PASS"
        or setup.get("provider_requests") != 0
        or setup.get("batch_digest") != "961e33d93b4b504318c5b9531064574a34ab5e6d2b5362f76c22ca19e3389088"
        or setup.get("object_fingerprint") != "03c572b79ee0ef36e5852a2c9657abb484ff318dc11c38d492007b48fee1ec28"
    ):
        raise RuntimeError("isolated data freeze evidence differs from accepted R1-R4")

    writer_sources = _source_map(
        (
            "src/tool/llm_gateway/deepseek.py",
            "src/shared/publication_contract.py",
            "src/shared/writer_request.py",
        )
    )
    writer_document = {
        "contract_version": _WRITER_VERSION,
        "sources": writer_sources,
    }
    model_document = {
        "content_max_retries": 0,
        "model": "deepseek-v4-flash",
        "provider_endpoint_policy": "AUTH-PROVIDER-ENDPOINT-20260809-01",
        "provider_host": "api.deepseek.com",
        "temperature": 0,
        "transport_max_retries": 2,
        "transport_retries_are_content_retries": False,
    }
    rule_sources = _source_map(
        (
            "src/shared/factual_basis.py",
            "src/shared/content_territory.py",
            "src/shared/visible_structure.py",
        )
    )
    rule_document = {"rule_version": _RULE_VERSION, "sources": rule_sources}

    gate_a_contract = _ROOT / "docs/BRAND-MATRIX-01/GateA-素材合同/import-contract.json"
    gate_a_manifest = _ROOT / "docs/BRAND-MATRIX-01/GateA-素材合同/import-manifest.json"
    media_manifest = _ROOT / "docs/BRAND-MATRIX-01/GateD-记录/media-master-manifest.json"
    authorization = _ROOT / "docs/BRAND-MATRIX-01/GateD-记录/授权修订单-AMD-AUTH-20260809-01.md"
    quality_source = _ROOT / "docs/BRAND-MATRIX-01/素材草案-v0/05-品控记录汇编-演示补充.md"
    if (
        _file_digest(gate_a_manifest) != _GATE_A_MANIFEST_DIGEST
        or _load(media_manifest).get("manifest_digest") != _MEDIA_MANIFEST_DIGEST
        or _file_digest(quality_source) != _QUALITY_SOURCE_DIGEST
    ):
        raise RuntimeError("one signed data source digest drifted")
    gate_a_contract_document = _load(gate_a_contract)
    amendments = gate_a_contract_document.get("amendments")
    if not isinstance(amendments, list) or [item.get("amendment_id") for item in amendments] != [
        "AMD-2026-0808-01",
        "AMD-CONTENT-TERRITORY-20260809-01",
    ]:
        raise RuntimeError("Gate A append-only content-territory amendment differs")
    data_document = {
        "authorization_amendment_sha256": _file_digest(authorization),
        "gate_a_contract_sha256": _file_digest(gate_a_contract),
        "gate_a_manifest_digest": _GATE_A_MANIFEST_DIGEST,
        "import_batch_digest": setup["batch_digest"],
        "import_object_fingerprint": setup["object_fingerprint"],
        "media_manifest_digest": _MEDIA_MANIFEST_DIGEST,
        "publication_projection_digest": setup["publication_projection_digest"],
        "quality_content_amendment_digest": _canonical_digest(amendments[-1]),
        "quality_source_sha256": _QUALITY_SOURCE_DIGEST,
    }
    exam_sources = _source_map(
        (
            "docs/BRAND-MATRIX-01/GateE-记录/考务合同-v2.md",
            "scripts/gatee/exam_contract.py",
            "scripts/gatee/exam_readiness.py",
            "scripts/gatee/run_negative_suite.py",
            "scripts/gatee/run_three_card_regression.py",
            "scripts/gatee/setup_isolated_exam.py",
        )
    )
    exam_document = {
        "contract_version": "brand-matrix-exam-administration-v2",
        "sources": exam_sources,
    }
    oracle_source = "scripts/gatee/exam_oracle.py"
    oracle_document = {
        "oracle_version": "brand-matrix-exam-oracle-v2",
        "source": oracle_source,
        "source_sha256": _file_digest(_ROOT / oracle_source),
    }
    objects = [
        {"object": "candidate_git_sha", "digest": candidate_sha},
        {
            "object": "writer_contract",
            "contract_version": _WRITER_VERSION,
            "digest": _canonical_digest(writer_document),
            "sources": writer_sources,
        },
        {"object": "model_configuration", "digest": _canonical_digest(model_document), **model_document},
        {
            "object": "guard_and_rules",
            "rule_version": _RULE_VERSION,
            "digest": _canonical_digest(rule_document),
            "sources": rule_sources,
        },
        {"object": "data_manifest_bundle", "digest": _canonical_digest(data_document), **data_document},
        {
            "object": "production_image",
            "digest": image["image_digest"],
            "implementation_label": candidate_sha,
            "build_count": 1,
            "binding_sha256": _file_digest(image_binding_path),
        },
        {
            "object": "exam_contract_and_runner",
            "digest": _canonical_digest(exam_document),
            "contract_version": exam_document["contract_version"],
            "sources": exam_sources,
        },
        {
            "object": "oracle",
            "digest": _canonical_digest(oracle_document),
            **oracle_document,
        },
    ]
    return {
        "receipt_version": "brand-matrix-gate-e-eight-object-freeze-v2",
        "status": "FROZEN_PUBLIC_REGRESSION_PENDING",
        "documentation_parent_sha": subprocess.run(
            ("git", "rev-parse", "HEAD"),
            cwd=_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip(),
        "eight_objects": objects,
        "ci_evidence": ci,
        "execution_boundary": {
            "provider_requests_during_e1_prime_before_public_regression": 0,
            "provider_requests_lifetime_budget_used": 76,
            "provider_requests_lifetime_budget_total": 300,
            "production_contact": 0,
            "dotenv_read": False,
            "binary_added_to_git": 0,
        },
    }


def _markdown(receipt: dict[str, object]) -> str:
    lines = [
        "# BRAND-MATRIX-01 · Gate E E-1' 八对象冻结回执",
        "",
        "状态：**`FROZEN · PUBLIC_REGRESSION_PENDING`**",
        "",
        "| 对象 | 冻结摘要 |",
        "|---|---|",
    ]
    for item in cast(list[dict[str, object]], receipt["eight_objects"]):
        lines.append(f"| `{item['object']}` | `{item['digest']}` |")
    ci = cast(dict[str, object], receipt["ci_evidence"])
    lines.extend(
        [
            "",
            "## CI 四查",
            "",
            f"- run：`{ci['run_id']}`；event=`{ci['event']}`；headSha=`{ci['head_sha']}`。",
            f"- conclusion=`{ci['conclusion']}`；非成功步骤=`{ci['non_success_steps']}`。",
            "",
            "## 边界",
            "",
            "- 本回执冻结的是主线候选代码、考务与判据；分支新增内容只承载考务工具、测试与证据。",
            "- 回执生成前 provider request=`0`；生产接触=`0`；未读取 `.env`；二进制入 Git=`0`。",
            "- 下一步只允许按考务合同逐字运行 B11/B12/B16，各一次；任一卡失败即 FAILED_SAFE。",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--image-binding", type=Path, required=True)
    parser.add_argument("--setup-evidence", type=Path, required=True)
    parser.add_argument("--ci-evidence", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    arguments = parser.parse_args()
    receipt = build_receipt(
        candidate_sha=str(arguments.candidate_sha),
        image_binding_path=arguments.image_binding.resolve(),
        setup_evidence_path=arguments.setup_evidence.resolve(),
        ci_evidence_path=arguments.ci_evidence.resolve(),
    )
    arguments.output_json.parent.mkdir(parents=True, exist_ok=True)
    arguments.output_json.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    arguments.output_md.write_text(_markdown(receipt), encoding="utf-8")
    print(json.dumps({"objects": 8, "status": receipt["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
