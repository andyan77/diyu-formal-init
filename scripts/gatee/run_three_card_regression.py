#!/usr/bin/env python3
"""Run the three public Gate E regression cards once on the frozen candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import psycopg

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from scripts.gated.brand_matrix_importer import (  # noqa: E402
    BRAND_ID,
    OPERATOR_IDS,
    TENANT_ID,
    matrix_id,
)
from scripts.gated.provider_env import probe_provider_tcp_tls  # noqa: E402
from scripts.gated.run_formal_acceptance import EvidenceGenerator  # noqa: E402
from scripts.gatee.exam_contract import (  # noqa: E402
    ExamCard,
    load_exam_contract,
    readiness_document,
)
from scripts.gatee.exam_oracle import evaluate  # noqa: E402
from src.brain.content_control_service import ContentControlService  # noqa: E402
from src.brain.content_service import ContentService  # noqa: E402
from src.infrastructure.content_control_repository import (  # noqa: E402
    PostgresContentControlRepository,
)
from src.infrastructure.local_object_store import LocalObjectStore  # noqa: E402
from src.infrastructure.postgres_repository import PostgresContentRepository  # noqa: E402
from src.shared.types import ProductFact, RequestedControls, TrustedScope  # noqa: E402

_EXPECTED_CANDIDATE_SHA = "bb9e63daa4558b9b202465d148b43d7c92a83266"
_EXPECTED_MODEL = "deepseek-v4-flash"
_PRIOR_PROVIDER_REQUESTS = 76
_FINAL_PROVIDER_REQUESTS = 79
_HQ_ORGANIZATION = "DIYU-HQ-001"
_PRIVATE_ROOT_PREFIX = "diyu-evidence-brand-matrix-gatee-regression-"


class OperatorBoundRepository(PostgresContentRepository):
    """Resolve explicit operator bindings while preserving the card input byte-for-byte."""

    def __init__(self, database_url: str, product_ids: tuple[str, ...]) -> None:
        super().__init__(database_url)
        self._operator_product_ids = product_ids

    def load_product_facts(self, scope: TrustedScope, weak_seed: str) -> tuple[ProductFact, ...]:
        del weak_seed
        return super().load_product_facts(scope, " ".join(self._operator_product_ids))


def _write_private_json(path: Path, value: object) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as target:
        json.dump(value, target, ensure_ascii=False, indent=2, sort_keys=True)
        target.write("\n")


def _write_public_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _scope(card: ExamCard) -> TrustedScope:
    account_id = matrix_id(f"account:{card.account_code}")
    if card.target.startswith("xiaohongshu_"):
        account_id = matrix_id(f"account:{card.account_code}:carrier:xiaohongshu")
    elif card.target == "wechat_channels_video":
        account_id = matrix_id(f"account:{card.account_code}:carrier:wechat_video")
    return TrustedScope(
        TENANT_ID,
        OPERATOR_IDS[_HQ_ORGANIZATION],
        BRAND_ID,
        account_id,
    )


def _persisted_artifact(database_url: str, result: dict[str, object]) -> dict[str, Any]:
    task_id = UUID(str(result["task_id"]))
    version_id = UUID(str(result["version_id"]))
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
        cursor.execute(
            """
            SELECT task.content_context_snapshot, version.run_id, version.artifact_digest
              FROM content_versions version
              JOIN business_tasks task
                ON task.tenant_id=version.tenant_id AND task.id=version.task_id
             WHERE version.tenant_id=%s AND version.id=%s AND task.id=%s
            """,
            (TENANT_ID, version_id, task_id),
        )
        row = cursor.fetchone()
    if row is None or not isinstance(row[0], dict):
        raise RuntimeError("the card did not persist one readable frozen snapshot")
    return {
        "snapshot": row[0],
        "run_id": str(row[1]),
        "artifact_digest": str(row[2]),
    }


def _scope_evidence(snapshot: dict[str, Any]) -> dict[str, object]:
    packet = snapshot.get("brand_context_packet")
    if not isinstance(packet, dict) or not isinstance(packet.get("segments"), list):
        raise RuntimeError("the frozen brand context packet is unavailable")
    forbidden: list[str] = []
    refs: list[str] = []
    for raw_segment in cast(list[object], packet["segments"]):
        if not isinstance(raw_segment, dict):
            raise RuntimeError("the frozen brand context segment is malformed")
        segment = cast(dict[str, object], raw_segment)
        source_ref = str(segment.get("source_id") or segment.get("claim_key") or segment.get("segment_id") or "")
        refs.append(source_ref)
        serialized = json.dumps(segment, ensure_ascii=False, sort_keys=True)
        if "SK-" in serialized or "RK-" in serialized:
            forbidden.append(source_ref)
    return {
        "account_control_organization_id": str(matrix_id(f"organization:{_HQ_ORGANIZATION}")),
        "forbidden_refs": sorted(set(forbidden)),
        "selected_refs": refs,
        "status": "PASS" if not forbidden else "FAIL",
    }


def _assert_candidate_source(candidate_sha: str) -> None:
    if candidate_sha != _EXPECTED_CANDIDATE_SHA:
        raise RuntimeError("runtime candidate differs from the re-signed E-1' baseline")
    candidate = subprocess.run(
        ("git", "rev-parse", candidate_sha),
        cwd=_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if candidate != candidate_sha:
        raise RuntimeError("runtime candidate cannot be resolved")
    changed = subprocess.run(
        ("git", "diff", "--name-only", candidate_sha, "--", "src", "frontend", "alembic"),
        cwd=_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    if changed:
        raise RuntimeError("runtime code differs from the frozen mainline candidate")


def _model_environment() -> tuple[str, str, str]:
    """Read only process-injected values; this tool never opens a dotenv file."""
    values = tuple(os.environ.get(key, "") for key in ("DEEPSEEK_API_BASE_URL", "DEEPSEEK_API_KEY", "DEEPSEEK_MODEL"))
    api_base_url, api_key, model = values
    if not api_base_url or not api_key or not model:
        raise RuntimeError("the three DeepSeek keys were not injected into the process environment")
    if model != _EXPECTED_MODEL:
        raise RuntimeError("the injected model differs from the frozen model configuration")
    return api_base_url, api_key, model


def _public_card(evidence: dict[str, Any], oracle_card: dict[str, Any]) -> dict[str, object]:
    result = cast(dict[str, Any], evidence["result"])
    snapshot = cast(dict[str, Any], evidence["snapshot"])
    publication = cast(dict[str, Any], snapshot["publication_contract"])
    relevance = publication.get("brand_relevance_evidence")
    relevance_object = relevance if isinstance(relevance, dict) else {}
    return {
        "card_id": evidence["card_id"],
        "input": evidence["input"],
        "operator_bindings": evidence["operator_bindings"],
        "outline": result["outline"],
        "body": result["body"],
        "task_id": evidence["task_id"],
        "run_id": evidence["run_id"],
        "version_id": evidence["version_id"],
        "artifact_digest": evidence["artifact_digest"],
        "brand_relevance_family": relevance_object.get("path_family"),
        "brand_relevance_consumed_refs": relevance_object.get("actual_consumed_refs", []),
        "used_persona_quote_ids": snapshot.get("used_persona_quote_ids", []),
        "provider_requests": evidence["provider_requests"],
        "oracle": oracle_card,
    }


def _markdown_report(public_document: dict[str, object]) -> str:
    lines = [
        "# Gate E E-1' 三卡公开回归成品与四门判定",
        "",
        f"- runtime candidate：`{public_document['runtime_candidate_sha']}`",
        f"- 模型：`{public_document['model']}`；temperature `0`；内容重试 `0`。",
        "- `first_draft_usable` 留给人工复核，不由执行工具自评。",
        "",
    ]
    for raw in cast(list[dict[str, Any]], public_document["cards"]):
        oracle = cast(dict[str, Any], raw["oracle"])
        lines.extend(
            [
                f"## {raw['card_id']}",
                "",
                f"- 输入：{raw['input']}",
                f"- 操作员绑定：`{json.dumps(raw['operator_bindings'], ensure_ascii=False, sort_keys=True)}`",
                f"- task/run/version：`{raw['task_id']}` / `{raw['run_id']}` / `{raw['version_id']}`",
                f"- 四门：`{json.dumps(oracle['gates'], ensure_ascii=False, sort_keys=True)}`",
                "",
                f"### 标题\n\n{raw['outline']}",
                "",
                f"### 正文\n\n{raw['body']}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def run(arguments: argparse.Namespace) -> dict[str, object]:
    candidate_sha = str(arguments.candidate_sha)
    _assert_candidate_source(candidate_sha)
    contract = load_exam_contract(cast(Path, arguments.contract))
    if [card.card_id for card in contract.cards] != ["B11", "B12", "B16"]:
        raise RuntimeError("the public regression card order differs")
    api_base_url, api_key, model = _model_environment()
    handshake = probe_provider_tcp_tls(api_base_url)
    evidence_root = cast(Path, arguments.evidence_root).resolve()
    expected_root = Path.home() / f"{_PRIVATE_ROOT_PREFIX}{candidate_sha}"
    if evidence_root != expected_root or evidence_root.exists():
        raise RuntimeError("private evidence root must be a new candidate-bound directory")
    evidence_root.mkdir(mode=0o700)
    evidence_root.chmod(0o700)
    _write_private_json(evidence_root / "provider-handshake.json", handshake)
    object_root = evidence_root / "object-store"
    object_root.mkdir(mode=0o700)
    generator = EvidenceGenerator(
        evidence_root=evidence_root,
        prior_request_count=_PRIOR_PROVIDER_REQUESTS,
        api_base_url=api_base_url,
        api_key=api_key,
        model=model,
        reviewer_provider=None,
        timeout_seconds=120.0,
        max_retries=0,
        transport_max_retries=2,
    )
    control = ContentControlService(
        PostgresContentControlRepository(str(arguments.database_url)),
        LocalObjectStore(str(object_root)),
    )
    private_cards: list[dict[str, Any]] = []
    for card in contract.cards:
        repository = OperatorBoundRepository(str(arguments.database_url), card.product_ids)
        service = ContentService(repository, generator, control)
        controls = (
            RequestedControls(
                material_ids=tuple(matrix_id(f"media-master:{binding.media_id}") for binding in card.master_bindings),
                product_media_intent=True,
            )
            if card.master_bindings
            else None
        )
        generator.begin_card(card.card_id)
        try:
            result = service.create_from_weak_seed(
                _scope(card),
                card.input_text,
                target=cast(Any, card.target),
                controls=controls,
                primary_product_override=cast(Any, card.content_product),
            )
            if result.get("kind") != "content":
                raise RuntimeError(f"{card.card_id} did not produce one completed artifact")
            persisted = _persisted_artifact(str(arguments.database_url), result)
            snapshot = cast(dict[str, Any], persisted["snapshot"])
            card_evidence = {
                "card_id": card.card_id,
                "input": card.input_text,
                "operator_bindings": {
                    "product_ids": list(card.product_ids),
                    "master_bindings": [
                        {"product_id": item.product_id, "media_id": item.media_id} for item in card.master_bindings
                    ],
                    "series_id": card.series_id,
                },
                "provider_requests": 1,
                "result": {
                    "kind": result["kind"],
                    "outline": result["outline"],
                    "body": result["body"],
                },
                "task_id": str(result["task_id"]),
                "run_id": persisted["run_id"],
                "version_id": str(result["version_id"]),
                "artifact_digest": persisted["artifact_digest"],
                "snapshot": snapshot,
                "projection_scope_evidence": _scope_evidence(snapshot),
            }
        except Exception as exc:
            generator.abort_card(exc)
            raise
        generator.finish_card()
        private_cards.append(card_evidence)
        _write_private_json(evidence_root / f"{card.card_id}.artifact.json", card_evidence)
    if generator.request_count != 3 or generator.cumulative_request_count != _FINAL_PROVIDER_REQUESTS:
        raise RuntimeError("the public regression provider ledger is not exactly 76→79")
    private_document = {
        "suite_version": "brand-matrix-gatee-public-regression-v2",
        "runtime_candidate_sha": candidate_sha,
        "model": model,
        "temperature": 0,
        "content_retries": 0,
        "transport_max_retries": 2,
        "prior_provider_request_count": _PRIOR_PROVIDER_REQUESTS,
        "provider_request_count": generator.request_count,
        "cumulative_provider_request_count": generator.cumulative_request_count,
        "transport_retry_count": generator.transport_retry_count,
        "ledger": generator.ledger,
        "cards": private_cards,
    }
    private_path = evidence_root / "three-card-evidence.json"
    _write_private_json(private_path, private_document)
    oracle = evaluate(cast(Path, arguments.contract), private_path)
    oracle_cards = {str(item["card_id"]): item for item in cast(list[dict[str, Any]], oracle["cards"])}
    public_cards = [_public_card(item, oracle_cards[str(item["card_id"])]) for item in private_cards]
    public_document = {
        "suite_version": private_document["suite_version"],
        "runtime_candidate_sha": candidate_sha,
        "model": model,
        "temperature": 0,
        "content_retries": 0,
        "transport_max_retries": 2,
        "prior_provider_request_count": _PRIOR_PROVIDER_REQUESTS,
        "provider_request_count": generator.request_count,
        "cumulative_provider_request_count": generator.cumulative_request_count,
        "transport_retry_count": generator.transport_retry_count,
        "ledger": generator.ledger,
        "cards": public_cards,
        "oracle_status": oracle["status"],
        "first_draft_usable": "PENDING_HUMAN",
        "private_evidence_root": str(evidence_root),
        "private_evidence_sha256": hashlib.sha256(private_path.read_bytes()).hexdigest(),
    }
    public_dir = cast(Path, arguments.public_dir)
    _write_public_json(public_dir / "三卡公开回归-判定.json", public_document)
    (public_dir / "三卡公开回归-成品与判定.md").write_text(
        _markdown_report(public_document),
        encoding="utf-8",
    )
    if oracle["status"] != "PASS":
        raise RuntimeError("one or more public regression cards failed a frozen automated gate")
    return public_document


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--readiness-only", action="store_true")
    parser.add_argument("--candidate-sha")
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--database-url")
    parser.add_argument("--evidence-root", type=Path)
    parser.add_argument("--public-dir", type=Path)
    arguments = parser.parse_args()
    if arguments.readiness_only:
        readiness = readiness_document(
            repository_root=_ROOT,
            contract_path=cast(Path, arguments.contract).resolve(),
        )
        print(
            json.dumps(
                {
                    "cards": len(cast(list[object], readiness["cards"])),
                    "provider_requests": readiness["provider_requests"],
                    "status": readiness["status"],
                },
                sort_keys=True,
            )
        )
        return 0
    if not all(
        (
            arguments.candidate_sha,
            arguments.database_url,
            arguments.evidence_root,
            arguments.public_dir,
        )
    ):
        parser.error("a live regression needs candidate, database, evidence root, and public directory")
    result = run(arguments)
    print(
        json.dumps(
            {
                "cards": len(cast(list[object], result["cards"])),
                "cumulative_provider_requests": result["cumulative_provider_request_count"],
                "status": result["oracle_status"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
