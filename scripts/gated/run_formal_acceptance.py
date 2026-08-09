#!/usr/bin/env python3
"""Run the frozen Gate D 8-scenario/8-anomaly suite exactly once."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import psycopg

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from scripts.gated.assert_rehearsal_semantics import (  # noqa: E402
    _assert_single_use_authorizations,
    _context,
    _local_claims,
    _select,
)
from scripts.gated.brand_matrix_importer import (  # noqa: E402
    ADMIN_USER_ID,
    BRAND_ID,
    OPERATOR_IDS,
    SECOND_HANGZHOU_OPERATOR_ID,
    TENANT_ID,
    matrix_id,
)
from scripts.gated.freeze_runtime_candidate import (  # noqa: E402
    REGISTRATION_VERSION,
    database_input_fingerprint,
)
from scripts.gated.provider_env import (  # noqa: E402
    AUTHORIZED_KEYS,
    parse_authorized_deepseek_env,
)
from src.brain.content_control_service import ContentControlService  # noqa: E402
from src.brain.content_service import ContentService  # noqa: E402
from src.brain.platform_directions import direction_for  # noqa: E402
from src.brain.workbench_service import WorkbenchService  # noqa: E402
from src.infrastructure.content_control_repository import (  # noqa: E402
    PostgresContentControlRepository,
)
from src.infrastructure.local_object_store import LocalObjectStore  # noqa: E402
from src.infrastructure.postgres_repository import (  # noqa: E402
    PostgresContentRepository,
)
from src.infrastructure.workbench_repository import (  # noqa: E402
    PostgresWorkbenchRepository,
)
from src.shared.brand_publication import brand_context_packet_document  # noqa: E402
from src.shared.errors import DomainError, GenerationFailed  # noqa: E402
from src.shared.publication_scope import resolve_claim_authority  # noqa: E402
from src.shared.types import (  # noqa: E402
    ContentProduct,
    ContentTarget,
    RequestedControls,
    TenantManagementScope,
    TrustedScope,
)
from src.tool.llm_gateway.deepseek import DeepSeekGenerator  # noqa: E402

SUITE_VERSION = "brand-matrix-gate-d-formal-suite-v4"
MAX_PROVIDER_REQUESTS = 80
INITIAL_RUNTIME_CANDIDATE_SHA = "997e6b55c1c40dacd44a46ff6617b28766011958"
FIRST_RERUN_RUNTIME_CANDIDATE_SHA = "f7e8e81c80ebc8552794f82aab81ef509e242b14"
PRIOR_RUNTIME_CANDIDATE_SHA = "ba4208a6ea96775683ecd89f41b6cd869b45eead"
_ENV_PATH = Path("/home") / "faye" / "workspace" / "diyu-formal-init" / ".env"
_ACCOUNT_ORGANIZATIONS = {
    "H01": "DIYU-HQ-001",
    "H03": "DIYU-HQ-001",
    "R01": "DIYU-REGION-001",
    "R02": "DIYU-REGION-002",
    "S01": "DIYU-STORE-001",
    "S02": "DIYU-STORE-001",
    "S03": "DIYU-STORE-002",
    "S04": "DIYU-STORE-003",
}


def _canonical_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain one JSON object")
    return cast(dict[str, Any], value)


def _write_private_json(path: Path, value: object) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as target:
        json.dump(value, target, ensure_ascii=False, indent=2, sort_keys=True)
        target.write("\n")


def _write_public_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


@dataclass(frozen=True)
class Card:
    card_id: str
    scenario_id: str
    account_code: str
    content_product: ContentProduct
    seed: str
    target: ContentTarget
    media_ids: tuple[str, ...]


class EvidenceGenerator(DeepSeekGenerator):
    """Bind every real provider response to exactly one frozen Gate D card."""

    def __init__(
        self,
        *,
        evidence_root: Path,
        prior_request_count: int,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._evidence_root = evidence_root
        self._prior_request_count = prior_request_count
        self._active_card: str | None = None
        self._active_responses: list[dict[str, Any]] = []
        self._ledger: list[dict[str, Any]] = []

    @property
    def request_count(self) -> int:
        return len(self._ledger)

    @property
    def cumulative_request_count(self) -> int:
        return self._prior_request_count + self.request_count

    @property
    def ledger(self) -> list[dict[str, Any]]:
        return list(self._ledger)

    def begin_card(self, card_id: str) -> None:
        if self._active_card is not None:
            raise RuntimeError("a provider card is already active")
        self._active_card = card_id
        self._active_responses = []

    def finish_card(self) -> None:
        if self._active_card is None or len(self._active_responses) != 1:
            raise RuntimeError("each formal card must receive exactly one Writer response")
        _write_private_json(
            self._evidence_root / f"{self._active_card}.raw.json",
            {
                "card_id": self._active_card,
                "raw_bundle_version": "brand-matrix-gate-d-provider-response-v1",
                "responses": self._active_responses,
            },
        )
        self._active_card = None
        self._active_responses = []

    def abort_card(self, error_type: str) -> None:
        if self._active_card is None:
            return
        _write_private_json(
            self._evidence_root / f"{self._active_card}.failed.raw.json",
            {
                "card_id": self._active_card,
                "error_type": error_type,
                "raw_bundle_version": "brand-matrix-gate-d-provider-failure-v1",
                "responses": self._active_responses,
            },
        )
        self._active_card = None
        self._active_responses = []

    def _request(
        self,
        system: str,
        prompt: str,
        max_tokens: int,
        *,
        thinking_disabled: bool = True,
        timeout_seconds: float | None = None,
    ) -> tuple[dict[str, Any], int]:
        card_id = self._active_card
        if card_id is None:
            raise RuntimeError("provider request is not bound to a frozen card")
        if self.cumulative_request_count >= MAX_PROVIDER_REQUESTS:
            raise RuntimeError("Gate D provider request budget is exhausted")
        request_document: dict[str, object] = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.0,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        if thinking_disabled:
            request_document["thinking"] = {"type": "disabled"}
        response, retries = super()._request(
            system,
            prompt,
            max_tokens,
            thinking_disabled=thinking_disabled,
            timeout_seconds=timeout_seconds,
        )
        if retries != 0:
            raise RuntimeError("formal Gate D transport retries are forbidden")
        record = {
            "card_id": card_id,
            "model": self.model_name,
            "request_index": self.cumulative_request_count + 1,
            "request_sha256": _canonical_digest(request_document),
            "response_sha256": _canonical_digest(response),
            "response": response,
            "temperature": 0,
            "transport_retries": retries,
        }
        self._active_responses.append(record)
        self._ledger.append(
            {
                key: value
                for key, value in record.items()
                if key != "response"
            }
        )
        return response, retries


def _parse_cards(contract: dict[str, Any]) -> tuple[Card, ...]:
    if contract.get("suite_version") != SUITE_VERSION:
        raise ValueError("formal suite version differs")
    counts = contract.get("expected_counts")
    if counts != {"anomalies": 8, "cards": 15, "content_products": 5, "scenarios": 8}:
        raise ValueError("formal suite expected counts differ")
    raw_cards = contract.get("cards")
    if not isinstance(raw_cards, list) or len(raw_cards) != 15:
        raise ValueError("formal suite must contain exactly 15 cards")
    products = {
        "dressing_decision",
        "product_truth",
        "brand_life_narrative",
        "local_response",
        "visual_styling_story",
    }
    targets = {
        "douyin_video",
        "xiaohongshu_video",
        "xiaohongshu_graphic",
        "wechat_channels_video",
    }
    cards: list[Card] = []
    for raw in cast(list[dict[str, Any]], raw_cards):
        content_product = str(raw.get("content_product"))
        target = str(raw.get("target"))
        if content_product not in products or target not in targets:
            raise ValueError("formal suite card has an unsupported product or target")
        cards.append(
            Card(
                card_id=str(raw["id"]),
                scenario_id=str(raw["scenario_id"]),
                account_code=str(raw["account_code"]),
                content_product=cast(ContentProduct, content_product),
                seed=str(raw["seed"]),
                target=cast(ContentTarget, target),
                media_ids=tuple(str(value) for value in raw.get("media_ids", [])),
            )
        )
    if (
        len({card.card_id for card in cards}) != 15
        or {card.scenario_id for card in cards}
        != {f"SCENARIO-{index:02d}" for index in range(1, 9)}
        or {card.content_product for card in cards} != products
    ):
        raise ValueError("formal suite card coverage differs")
    return tuple(cards)


def _load_prior_ledger(
    path: Path,
    *,
    expected_count: int,
) -> tuple[str, list[dict[str, Any]]]:
    document = _load_object(path)
    records = document.get("records")
    runtime_candidate_sha = str(document.get("runtime_candidate_sha", ""))
    if (
        runtime_candidate_sha != PRIOR_RUNTIME_CANDIDATE_SHA
        or document.get("prior_runtime_candidate_sha")
        != FIRST_RERUN_RUNTIME_CANDIDATE_SHA
        or document.get("initial_runtime_candidate_sha")
        != INITIAL_RUNTIME_CANDIDATE_SHA
        or document.get("prior_record_range") != [1, 7]
        or document.get("prior_provider_request_count") != 7
        or document.get("current_provider_request_count") != 1
        or document.get("status") != "FAILED_SAFE"
        or document.get("provider_request_count") != expected_count
        or not isinstance(records, list)
        or len(records) != expected_count
        or [item.get("request_index") for item in records]
        != list(range(1, expected_count + 1))
    ):
        raise RuntimeError("prior failed-safe provider ledger differs")
    normalized: list[dict[str, Any]] = []
    for raw_record in cast(list[dict[str, Any]], records):
        request_index = int(raw_record["request_index"])
        expected_candidate = (
            INITIAL_RUNTIME_CANDIDATE_SHA
            if request_index <= 6
            else (
                FIRST_RERUN_RUNTIME_CANDIDATE_SHA
                if request_index == 7
                else PRIOR_RUNTIME_CANDIDATE_SHA
            )
        )
        recorded_candidate = str(
            raw_record.get("runtime_candidate_sha", expected_candidate)
        )
        if recorded_candidate != expected_candidate:
            raise RuntimeError("prior provider ledger candidate lineage differs")
        normalized.append(
            raw_record | {"runtime_candidate_sha": expected_candidate}
        )
    return runtime_candidate_sha, normalized


def _scope(
    account_code: str,
    *,
    user_id: UUID | None = None,
    target: ContentTarget = "douyin_video",
) -> TrustedScope:
    organization = _ACCOUNT_ORGANIZATIONS[account_code]
    account_id = matrix_id(f"account:{account_code}")
    if target in {"xiaohongshu_graphic", "xiaohongshu_video"}:
        account_id = matrix_id(f"account:{account_code}:carrier:xiaohongshu")
    elif target == "wechat_channels_video":
        account_id = matrix_id(f"account:{account_code}:carrier:wechat_video")
    return TrustedScope(
        TENANT_ID,
        user_id or OPERATOR_IDS[organization],
        BRAND_ID,
        account_id,
    )


def _task_artifact(database_url: str, result: dict[str, object]) -> dict[str, Any]:
    task_id = UUID(str(result["task_id"]))
    version_id = UUID(str(result["version_id"]))
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
        cursor.execute(
            """
            SELECT task.content_context_snapshot, task.created_by, task.account_id,
                   task.logical_account_id, version.run_id, version.artifact_digest
              FROM content_versions version
              JOIN business_tasks task
                ON task.tenant_id=version.tenant_id AND task.id=version.task_id
             WHERE version.tenant_id=%s AND version.id=%s AND task.id=%s
            """,
            (TENANT_ID, version_id, task_id),
        )
        row = cursor.fetchone()
    if row is None or not isinstance(row[0], dict):
        raise RuntimeError("formal content did not persist one readable task snapshot")
    return {
        "snapshot": row[0],
        "created_by": str(row[1]),
        "account_id": str(row[2]),
        "logical_account_id": str(row[3]),
        "run_id": str(row[4]),
        "artifact_digest": str(row[5]),
    }


def _validate_artifact(
    card: Card,
    result: dict[str, object],
    persisted: dict[str, Any],
    model: str,
) -> dict[str, Any]:
    if (
        result.get("kind") != "content"
        or result.get("ai_generated") is not True
        or result.get("aigc_label") != "AI 辅助生成"
        or not str(result.get("outline", "")).strip()
        or not str(result.get("body", "")).strip()
    ):
        raise RuntimeError(f"{card.card_id} did not return one complete disclosed artifact")
    context_basis = result.get("context_basis")
    if not isinstance(context_basis, dict) or (
        context_basis.get("account_editorial_state") != "applied"
        or context_basis.get("brand_relevance_state") != "applied"
    ):
        raise RuntimeError(f"{card.card_id} lacks observable applied semantic state")
    snapshot = cast(dict[str, Any], persisted["snapshot"])
    publication = snapshot.get("publication_contract")
    assembly = snapshot.get("task_value_assembly")
    resolution = snapshot.get("account_editorial_resolution")
    writer_request = snapshot.get("writer_request_v3")
    relevance = publication.get("brand_relevance_evidence") if isinstance(publication, dict) else None
    if (
        not isinstance(publication, dict)
        or publication.get("contract_version") != "publication-contract-v3"
        or publication.get("content_product") != card.content_product
        or not isinstance(assembly, dict)
        or assembly.get("brand_relevance_state") != "applied"
        or assembly.get("demonstration_eligible") is not True
        or not isinstance(relevance, dict)
        or not relevance.get("actual_consumed_refs")
        or not isinstance(resolution, dict)
        or resolution.get("applied") is not True
        or not isinstance(writer_request, dict)
        or writer_request.get("content_product") != card.content_product
        or snapshot.get("writer_model") != model
    ):
        raise RuntimeError(f"{card.card_id} did not freeze the common formal runtime chain")
    if card.content_product in {"dressing_decision", "product_truth", "visual_styling_story"}:
        product_basis = publication.get("product_decision_basis")
        product_packet = snapshot.get("product_fact_packet")
        if not isinstance(product_basis, dict) or not isinstance(product_packet, dict):
            raise RuntimeError(f"{card.card_id} lost the formal product decision basis")
    if card.content_product == "visual_styling_story":
        envelope = snapshot.get("media_capability_envelope")
        media_program = snapshot.get("media_program")
        materials = snapshot.get("material_refs")
        if (
            not isinstance(envelope, dict)
            or not isinstance(media_program, dict)
            or not isinstance(materials, list)
            or len(materials) != 2
        ):
            raise RuntimeError("formal P5 did not freeze two registered master resources")
    lens = snapshot.get("account_editorial_lens")
    packet = snapshot.get("brand_context_packet")
    if not isinstance(lens, dict) or not isinstance(packet, dict):
        raise RuntimeError(f"{card.card_id} lost lens or projection packet")
    return {
        "card_id": card.card_id,
        "scenario_id": card.scenario_id,
        "account_code": card.account_code,
        "content_product": card.content_product,
        "target": card.target,
        "task_id": str(result["task_id"]),
        "run_id": persisted["run_id"],
        "version_id": str(result["version_id"]),
        "version": result["version"],
        "publishing_identity_id": persisted["account_id"],
        "logical_account_id": persisted["logical_account_id"],
        "artifact_digest": persisted["artifact_digest"],
        "body_digest": hashlib.sha256(str(result["body"]).encode()).hexdigest(),
        "publication_contract_digest": snapshot.get("publication_contract_digest"),
        "account_editorial_resolution_digest": snapshot.get("account_editorial_resolution_digest"),
        "account_profile_id": lens.get("source_profile_id"),
        "account_profile_version": lens.get("source_profile_version"),
        "lens_dimensions": {
            key: lens.get(key)
            for key in (
                "observation_angle",
                "judgment_order",
                "audience_relation",
                "closure_method",
            )
        },
        "brand_relevance_family": relevance.get("path_family"),
        "brand_relevance_consumed_refs": relevance.get("actual_consumed_refs"),
        "product_fact_packet_digest": (
            snapshot.get("product_fact_packet", {}).get("packet_digest")
            if isinstance(snapshot.get("product_fact_packet"), dict)
            else None
        ),
        "product_value_contract_digest": snapshot.get("product_value_contract_digest"),
        "projection_claim_keys": [
            str(item["claim_key"])
            for item in packet.get("segments", [])
            if isinstance(item, dict) and item.get("claim_key")
        ],
        "snapshot": snapshot,
    }


def _legacy_state(database_url: str) -> dict[str, Any]:
    task_id = matrix_id("fixture:legacy-task")
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
        cursor.execute(
            """
            SELECT task.content_context_snapshot, version.version_audit_snapshot,
                   version.artifact_digest, version.body
              FROM business_tasks task
              JOIN content_versions version
                ON version.tenant_id=task.tenant_id AND version.task_id=task.id
             WHERE task.tenant_id=%s AND task.id=%s
            """,
            (TENANT_ID, task_id),
        )
        row = cursor.fetchone()
    if row is None:
        raise RuntimeError("legacy AMD v1 fixture is unavailable")
    result = {
        "task_id": str(task_id),
        "task_snapshot": row[0],
        "version_snapshot": row[1],
        "artifact_digest": str(row[2]),
        "body_digest": hashlib.sha256(str(row[3]).encode()).hexdigest(),
    }
    if (
        not isinstance(row[0], dict)
        or row[0].get("amendment_version") != "v1"
        or not isinstance(row[1], dict)
        or row[1].get("amendment_version") != "v1"
    ):
        raise RuntimeError("legacy AMD fixture no longer freezes v1")
    return result


def _pre_provider_anomalies(database_url: str) -> tuple[dict[str, Any], dict[str, Any]]:
    repository = PostgresContentRepository(database_url)
    legacy = _legacy_state(database_url)
    results: dict[str, Any] = {}
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
        cursor.execute(
            "SELECT facts,source_kind,source_note FROM brand_products "
            "WHERE tenant_id=%s AND brand_id=%s AND sku='DIYU-CSPU-008'",
            (TENANT_ID, BRAND_ID),
        )
        product = cursor.fetchone()
        cursor.execute(
            "SELECT count(*) FROM brand_publication_projection_items "
            "WHERE tenant_id=%s AND brand_id=%s AND (source_ref='DEMO-QCX-2608-003' "
            "OR published_text LIKE '%%DEMO-QCX-2608-003%%')",
            (TENANT_ID, BRAND_ID),
        )
        wrong_projection_row = cursor.fetchone()
        if wrong_projection_row is None:
            raise RuntimeError("ANOM-02 projection count is unavailable")
        wrong_projection_count = int(wrong_projection_row[0])
    if (
        product is None
        or not isinstance(product[0], dict)
        or set(product[0]) != {"entity_kind", "category", "main_color"}
        or product[1] != "gatea_verified_visual"
        or wrong_projection_count != 0
    ):
        raise RuntimeError("ANOM-02: ordinary store composition polluted formal product facts")
    results["ANOM-02"] = {
        "result": "PASS",
        "provider_requests": 0,
        "evidence": "formal ProductFact keeps only Gate A V fields; DEMO-QCX source absent from projection",
    }

    conflicting = (
        {
            "position": 1,
            "semantic_subject_type": "product",
            "semantic_subject_id": "DIYU-CSPU-013",
            "claim_key": "composition",
            "authority_class": "headquarters_formal",
            "published_text": "正式值 A",
            "source_digest": "a" * 64,
        },
        {
            "position": 2,
            "semantic_subject_type": "product",
            "semantic_subject_id": "DIYU-CSPU-013",
            "claim_key": "composition",
            "authority_class": "headquarters_formal",
            "published_text": "正式值 B",
            "source_digest": "b" * 64,
        },
    )
    try:
        resolve_claim_authority(conflicting)
    except DomainError as exc:
        if "needs_review" not in str(exc):
            raise RuntimeError("ANOM-03 returned the wrong conflict state") from exc
    else:
        raise RuntimeError("ANOM-03 did not fail closed for a structured same-level conflict")
    results["ANOM-03"] = {
        "result": "PASS",
        "provider_requests": 0,
        "evidence": "structured claim resolver returned needs_review before Writer",
    }

    east = _select(repository, "R01")
    east_claims = _local_claims(east)
    if "RK-EC-08" in east_claims:
        raise RuntimeError("ANOM-04 expired RK-EC-08 entered a new task context")
    results["ANOM-04"] = {
        "result": "PASS",
        "provider_requests": 0,
        "evidence": "RK-EC-08 absent from current R01 selection",
    }

    hangzhou_claims = _local_claims(_select(repository, "S01"))
    huzhou_claims = _local_claims(_select(repository, "S03"))
    if (
        not any(value.startswith("SK-HZ-") for value in hangzhou_claims)
        or any(value.startswith("SK-HuZ-") for value in hangzhou_claims)
        or not any(value.startswith("SK-HuZ-") for value in huzhou_claims)
        or any(value.startswith("SK-HZ-") for value in huzhou_claims)
    ):
        raise RuntimeError("ANOM-05 sibling store isolation failed")
    results["ANOM-05"] = {
        "result": "PASS",
        "provider_requests": 0,
        "evidence": "Hangzhou/Huzhou positive scope and sibling-store negative scope both held",
    }

    scopes = (
        _scope("S01"),
        _scope("S01", user_id=SECOND_HANGZHOU_OPERATOR_ID),
    )
    runs: list[UUID] = []
    tasks: list[UUID] = []
    for index, scope in enumerate(scopes, start=1):
        context = repository.select_brand_context_for_task(
            scope,
            _context("S01"),
            "两名自然人同账号归属验证",
            "local_response",
            (),
        )
        if context.context_packet is None:
            raise RuntimeError("ANOM-06 formal account context is unavailable")
        task_id, run_id, _ = repository.create_task_and_running_run(
            scope,
            f"Gate D 双用户归属验证 {index}",
            "local_response",
            None,
            "gate-d-zero-provider-anomaly",
            (),
            context,
            (),
            "douyin_video",
            "video",
            direction_for("douyin_video"),
            None,
            "Gate D isolated ownership proof",
            snapshot={
                "brand_context_packet": brand_context_packet_document(
                    context.context_packet,
                    include_text=True,
                )
            },
        )
        repository.fail_run(scope, task_id, run_id, "Gate D zero-provider ownership proof")
        tasks.append(task_id)
        runs.append(run_id)
    try:
        repository.load_content_context_snapshot(scopes[0], tasks[1])
    except DomainError:
        cross_user_rejected = True
    else:
        raise RuntimeError("ANOM-06 cross-user task read was allowed")
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
        cursor.execute(
            "SELECT actor_id FROM activity_events WHERE tenant_id=%s "
            "AND event_type='generation.started' AND entity_id=ANY(%s)",
            (TENANT_ID, runs),
        )
        actors = {UUID(str(row[0])) for row in cursor.fetchall()}
        cursor.execute(
            "SELECT created_by,logical_account_id FROM business_tasks "
            "WHERE tenant_id=%s AND id=ANY(%s)",
            (TENANT_ID, tasks),
        )
        ownership = cursor.fetchall()
    if (
        actors != {scope.user_id for scope in scopes}
        or {UUID(str(row[0])) for row in ownership} != {scope.user_id for scope in scopes}
        or {UUID(str(row[1])) for row in ownership} != {matrix_id("account:S01")}
        or not cross_user_rejected
    ):
        raise RuntimeError("ANOM-06 actor, logical account or ownership evidence differs")
    results["ANOM-06"] = {
        "result": "PASS",
        "provider_requests": 0,
        "evidence": "two actors, one S01 logical account, cross-user read rejected",
        "task_ids": [str(value) for value in tasks],
    }

    results["ANOM-07"] = {
        "result": "PENDING_ZERO_PROVIDER_CHECK",
        "provider_requests": 0,
        "evidence": "reserved for execution after scenario artifacts so its one-time fixtures cannot pre-consume them",
    }
    results["ANOM-01"] = {
        "result": "PASS",
        "provider_requests": 0,
        "evidence": "legacy v1 frozen; current DIYU-CSPU-008 remains V-only pending final task comparison",
    }
    results["ANOM-08"] = {
        "result": "PASS",
        "provider_requests": 0,
        "evidence": "legacy AMD v1 snapshot frozen pending current v2 task comparison",
    }
    return results, legacy


def _register_feedback(
    database_url: str,
    object_root: Path,
    source: dict[str, Any],
) -> str:
    service = WorkbenchService(
        PostgresWorkbenchRepository(database_url),
        LocalObjectStore(str(object_root)),
    )
    observation = service.create_brand_feedback_observation(
        TenantManagementScope(TENANT_ID, ADMIN_USER_ID, BRAND_ID),
        UUID(str(source["task_id"])),
        UUID(str(source["version_id"])),
        UUID(str(source["logical_account_id"])),
        {
            "gate_d_feedback_marker": "GATED-OBSERVATION-NOT-FORMAL-SOURCE",
            "candidate_note": "到店前希望先知道如何准备",
        },
    )
    observation_id = str(observation["id"])
    visible = service.brand_feedback_observations(
        TenantManagementScope(TENANT_ID, ADMIN_USER_ID, BRAND_ID)
    )
    if observation_id not in {str(item.get("id")) for item in visible}:
        raise RuntimeError("SCENARIO-08 feedback observation is not readable")
    return observation_id


def _scenario_assertions(
    artifacts: dict[str, dict[str, Any]],
    anomaly_results: dict[str, Any],
    legacy_before: dict[str, Any],
    database_url: str,
    feedback_observation_id: str,
    *,
    require_model_differences: bool = True,
) -> list[dict[str, Any]]:
    scenario_results: list[dict[str, Any]] = []
    scenario_one = [artifacts[key] for key in ("S01-P1", "S01-P2", "S01-P5")]
    if (
        scenario_one[0]["brand_relevance_family"] != "product_expertise"
        or scenario_one[1]["brand_relevance_family"] != "product_expertise"
        or scenario_one[2]["brand_relevance_family"] != "brand_visual"
        or not scenario_one[0]["snapshot"]["publication_contract"]["product_decision_basis"].get(
            "judgment_ref"
        )
    ):
        raise RuntimeError("SCENARIO-01 F/J/G or P5 evidence differs")
    scenario_results.append({"id": "SCENARIO-01", "result": "PASS", "card_count": 3})

    east = artifacts["S02-R01-P4"]["projection_claim_keys"]
    if not any(value.startswith("RK-EC-") for value in east) or any(
        value.startswith("RK-SW-") for value in east
    ):
        raise RuntimeError("SCENARIO-02 did not consume only the East region context")
    scenario_results.append({"id": "SCENARIO-02", "result": "PASS", "card_count": 1})

    hangzhou = artifacts["S03-S01-P4"]["projection_claim_keys"]
    if not any(value.startswith("SK-HZ-") for value in hangzhou) or any(
        value.startswith(("SK-HuZ-", "SK-CD-")) for value in hangzhou
    ):
        raise RuntimeError("SCENARIO-03 did not consume only legal Hangzhou store context")
    scenario_results.append({"id": "SCENARIO-03", "result": "PASS", "card_count": 1})

    scenario_four = artifacts["S04-S04-P2"]
    facts = scenario_four["snapshot"].get("product_facts")
    serialized = json.dumps(facts, ensure_ascii=False, sort_keys=True)
    if "DEMO-QCX-2608-003" in serialized or "exact_composition" in serialized:
        raise RuntimeError("SCENARIO-04 content facts were polluted by the ordinary store file")
    scenario_results.append({"id": "SCENARIO-04", "result": "PASS", "card_count": 1})

    scenario_five = [
        artifacts[f"S05-{account}-P1"] for account in ("H01", "R01", "S01", "S04")
    ]
    if (
        len({item["product_fact_packet_digest"] for item in scenario_five}) != 1
        or (
            require_model_differences
            and len({item["body_digest"] for item in scenario_five}) != 4
        )
        or len({tuple(item["projection_claim_keys"]) for item in scenario_five}) < 3
    ):
        raise RuntimeError("SCENARIO-05 same-SKU four-node evidence lacks fact stability or expression difference")
    scenario_results.append({"id": "SCENARIO-05", "result": "PASS", "card_count": 4})

    scenario_six = [artifacts[f"S06-{account}-P3"] for account in ("H01", "S02", "S04")]
    if (
        require_model_differences
        and len({item["body_digest"] for item in scenario_six}) != 3
    ) or len({item["account_profile_id"] for item in scenario_six}) != 3:
        raise RuntimeError("SCENARIO-06 same-seed artifacts or source profiles did not differ")
    dimensions = ("observation_angle", "judgment_order", "audience_relation", "closure_method")
    for left_index in range(len(scenario_six)):
        for right_index in range(left_index + 1, len(scenario_six)):
            changed = sum(
                scenario_six[left_index]["lens_dimensions"][key]
                != scenario_six[right_index]["lens_dimensions"][key]
                for key in dimensions
            )
            if changed < 2:
                raise RuntimeError("SCENARIO-06 account semantics differ in fewer than two dimensions")
    scenario_results.append({"id": "SCENARIO-06", "result": "PASS", "card_count": 3})

    legacy_after = _legacy_state(database_url)
    current = artifacts["S07-H01-P3"]
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
        cursor.execute(
            "SELECT strategy_version FROM brands WHERE tenant_id=%s AND id=%s",
            (TENANT_ID, BRAND_ID),
        )
        strategy_row = cursor.fetchone()
        if strategy_row is None:
            raise RuntimeError("SCENARIO-07 current brand version is unavailable")
        strategy_version = str(strategy_row[0])
    if (
        legacy_after != legacy_before
        or strategy_version != "v2-amd-2026-0808-01"
        or not current["publication_contract_digest"]
    ):
        raise RuntimeError("SCENARIO-07 AMD v1/v2 freeze evidence differs")
    scenario_results.append({"id": "SCENARIO-07", "result": "PASS", "card_count": 1})
    anomaly_results["ANOM-01"]["evidence"] = (
        "legacy v1 digest stayed byte-identical; current CSPU-008 task used only frozen V/J refs"
    )
    anomaly_results["ANOM-08"]["evidence"] = (
        "legacy AMD v1 task and digest stayed unchanged; new task froze current projection v2"
    )

    post_feedback = artifacts["S08-S01-P4"]
    snapshot_text = json.dumps(post_feedback["snapshot"], ensure_ascii=False, sort_keys=True)
    if (
        feedback_observation_id in snapshot_text
        or "GATED-OBSERVATION-NOT-FORMAL-SOURCE" in snapshot_text
    ):
        raise RuntimeError("SCENARIO-08 unconfirmed feedback entered the next task")
    scenario_results.append({"id": "SCENARIO-08", "result": "PASS", "card_count": 1})
    return scenario_results


def _assert_runtime_freeze(
    candidate_sha: str,
    registration: dict[str, Any],
    contract_path: Path,
    database_url: str,
    model: str,
) -> None:
    if (
        registration.get("registration_version") != REGISTRATION_VERSION
        or registration.get("runtime_candidate_sha") != candidate_sha
        or registration.get("provider_requests_at_freeze") != 0
        or registration.get("model") != model
        or registration.get("temperature") != 0
        or registration.get("max_retries") != 0
    ):
        raise RuntimeError("runtime candidate registration differs")
    claimed = str(registration.get("registration_digest", ""))
    unsigned = dict(registration)
    unsigned.pop("registration_digest", None)
    if claimed != _canonical_digest(unsigned):
        raise RuntimeError("runtime candidate registration digest differs")
    prompt_contracts = registration.get("prompt_contracts")
    if not isinstance(prompt_contracts, dict) or prompt_contracts.get(
        "formal_suite_contract_sha256"
    ) != _file_sha256(contract_path):
        raise RuntimeError("formal suite contract changed after candidate freeze")
    database_digest, counts, projection_digest = database_input_fingerprint(database_url)
    if (
        database_digest != registration.get("local_isolated_database_input_fingerprint")
        or counts != registration.get("local_isolated_database_counts")
        or projection_digest != registration.get("publication_projection_digest")
    ):
        raise RuntimeError("frozen isolated database inputs changed")
    if subprocess.run(
        ("git", "merge-base", "--is-ancestor", candidate_sha, "HEAD"),
        cwd=_ROOT,
        check=False,
    ).returncode:
        raise RuntimeError("runtime candidate is not an ancestor of documentation HEAD")
    changed = subprocess.run(
        ("git", "diff", "--name-only", candidate_sha, "HEAD"),
        cwd=_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    if any(not path.startswith("docs/BRAND-MATRIX-01/GateD-记录/") for path in changed):
        raise RuntimeError("post-candidate committed diff is not Gate D docs-only")
    tracked_dirty = subprocess.run(
        ("git", "status", "--porcelain", "--untracked-files=no"),
        cwd=_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if tracked_dirty:
        raise RuntimeError("tracked worktree changed after runtime freeze")


def _write_checksums(root: Path) -> str:
    rows = []
    for path in sorted(root.iterdir(), key=lambda item: item.name):
        if path.is_file() and path.name != "SHA256SUMS":
            rows.append(f"{_file_sha256(path)}  {path.name}")
    target = root / "SHA256SUMS"
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        output.write("\n".join(rows) + "\n")
    return _file_sha256(target)


def _internal_run(arguments: argparse.Namespace) -> int:
    candidate_sha = str(arguments.candidate_sha)
    expected_root = Path.home() / f"diyu-evidence-brand-matrix-gated-{candidate_sha}"
    evidence_root = cast(Path, arguments.evidence_root).resolve()
    if evidence_root != expected_root or evidence_root.exists():
        raise RuntimeError("private evidence root must be the new candidate-bound 0700 directory")
    evidence_root.mkdir(mode=0o700, parents=False)
    evidence_root.chmod(0o700)
    contract_path = cast(Path, arguments.contract)
    registration = _load_object(cast(Path, arguments.registration))
    contract = _load_object(contract_path)
    cards = _parse_cards(contract)
    constraints = contract.get("constraints")
    if not isinstance(constraints, dict):
        raise RuntimeError("formal suite constraints are missing")
    prior_request_count = int(constraints.get("prior_provider_requests", -1))
    prior_candidate_sha, prior_ledger = _load_prior_ledger(
        cast(Path, arguments.prior_ledger),
        expected_count=prior_request_count,
    )
    model = os.environ.get("DEEPSEEK_MODEL", "")
    api_base_url = os.environ.get("DEEPSEEK_API_BASE_URL", "")
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not model or not api_base_url or not api_key:
        raise RuntimeError("authorized provider environment is incomplete")
    _assert_runtime_freeze(
        candidate_sha,
        registration,
        contract_path,
        str(arguments.app_database_url),
        model,
    )
    anomaly_results, legacy = _pre_provider_anomalies(str(arguments.app_database_url))
    # Deterministic anomaly work may add only acceptance tasks/events/reservations;
    # the frozen input projection, accounts, products and media must remain identical.
    _assert_runtime_freeze(
        candidate_sha,
        registration,
        contract_path,
        str(arguments.app_database_url),
        model,
    )
    object_root = evidence_root / "object-store"
    object_root.mkdir(mode=0o700)
    generator = EvidenceGenerator(
        evidence_root=evidence_root,
        prior_request_count=prior_request_count,
        api_base_url=api_base_url,
        api_key=api_key,
        model=model,
        reviewer_provider=None,
        timeout_seconds=120.0,
        max_retries=0,
    )
    control = ContentControlService(
        PostgresContentControlRepository(str(arguments.app_database_url)),
        LocalObjectStore(str(object_root)),
    )
    service = ContentService(
        PostgresContentRepository(str(arguments.app_database_url)),
        generator,
        control,
    )
    artifacts: dict[str, dict[str, Any]] = {}
    feedback_observation_id = ""
    try:
        for card in cards:
            if card.card_id == "S08-S01-P4":
                feedback_observation_id = _register_feedback(
                    str(arguments.app_database_url),
                    object_root,
                    artifacts["S03-S01-P4"],
                )
            controls = (
                RequestedControls(
                    material_ids=tuple(
                        matrix_id(f"media-master:{media_id}") for media_id in card.media_ids
                    ),
                    product_media_intent=True,
                )
                if card.media_ids
                else None
            )
            generator.begin_card(card.card_id)
            try:
                result = service.create_from_weak_seed(
                    _scope(card.account_code, target=card.target),
                    card.seed,
                    target=card.target,
                    controls=controls,
                    primary_product_override=card.content_product,
                )
                persisted = _task_artifact(str(arguments.app_database_url), result)
                artifact = _validate_artifact(card, result, persisted, model)
            except Exception as exc:
                generator.abort_card(type(exc).__name__)
                raise
            generator.finish_card()
            artifacts[card.card_id] = artifact
            private = dict(artifact)
            private["outline"] = result["outline"]
            private["body"] = result["body"]
            _write_private_json(evidence_root / f"{card.card_id}.artifact.json", private)
        anomaly_results["ANOM-07"] = {
            "result": "PASS",
            "provider_requests": 0,
            "evidence": _assert_single_use_authorizations(
                PostgresContentRepository(str(arguments.app_database_url)),
                str(arguments.app_database_url),
            ),
        }
        scenario_results = _scenario_assertions(
            artifacts,
            anomaly_results,
            legacy,
            str(arguments.app_database_url),
            feedback_observation_id,
        )
        if (
            generator.request_count != len(cards)
            or generator.cumulative_request_count > MAX_PROVIDER_REQUESTS
        ):
            raise RuntimeError("formal provider ledger count differs")
        public_artifacts = [
            {
                key: value
                for key, value in artifact.items()
                if key != "snapshot"
            }
            for artifact in artifacts.values()
        ]
        current_public_ledger = [
            entry
            | {
                "runtime_candidate_sha": candidate_sha,
                "task_id": artifacts[str(entry["card_id"])]["task_id"],
                "run_id": artifacts[str(entry["card_id"])]["run_id"],
                "version_id": artifacts[str(entry["card_id"])]["version_id"],
                "binary_result": "PASS",
            }
            for entry in generator.ledger
        ]
        cumulative_public_ledger = prior_ledger + current_public_ledger
        private_manifest = {
            "suite_version": SUITE_VERSION,
            "runtime_candidate_sha": candidate_sha,
            "runtime_candidate_chain": [
                INITIAL_RUNTIME_CANDIDATE_SHA,
                FIRST_RERUN_RUNTIME_CANDIDATE_SHA,
                PRIOR_RUNTIME_CANDIDATE_SHA,
                candidate_sha,
            ],
            "registration_digest": registration["registration_digest"],
            "provider_request_count": generator.request_count,
            "cumulative_provider_request_count": generator.cumulative_request_count,
            "scenario_results": scenario_results,
            "anomaly_results": [anomaly_results[key] for key in sorted(anomaly_results)],
            "artifact_ids": [
                {
                    "card_id": item["card_id"],
                    "task_id": item["task_id"],
                    "run_id": item["run_id"],
                    "version_id": item["version_id"],
                }
                for item in public_artifacts
            ],
            "status": "PASS",
        }
        _write_private_json(evidence_root / "manifest.json", private_manifest)
        _write_private_json(
            evidence_root / "provider-ledger.json",
            cumulative_public_ledger,
        )
        checksum_digest = _write_checksums(evidence_root)
        public_evidence = {
            "suite_version": SUITE_VERSION,
            "runtime_candidate_sha": candidate_sha,
            "runtime_candidate_chain": [
                INITIAL_RUNTIME_CANDIDATE_SHA,
                FIRST_RERUN_RUNTIME_CANDIDATE_SHA,
                PRIOR_RUNTIME_CANDIDATE_SHA,
                candidate_sha,
            ],
            "registration_digest": registration["registration_digest"],
            "model": model,
            "temperature": 0,
            "max_retries": 0,
            "provider_request_count": generator.request_count,
            "prior_provider_request_count": prior_request_count,
            "cumulative_provider_request_count": generator.cumulative_request_count,
            "provider_request_budget": MAX_PROVIDER_REQUESTS,
            "provider_transport_retries": 0,
            "scenario_results": scenario_results,
            "anomaly_results": [anomaly_results[key] for key in sorted(anomaly_results)],
            "artifact_index": public_artifacts,
            "private_evidence_path": f"~/{evidence_root.name}",
            "private_sha256s_digest": checksum_digest,
            "raw_responses_in_git": 0,
            "formal_binary_completion": True,
            "status": "PASS",
        }
        _write_public_json(cast(Path, arguments.public_evidence), public_evidence)
        _write_public_json(
            cast(Path, arguments.public_ledger),
            {
                "ledger_version": "brand-matrix-gate-d-provider-ledger-v4",
                "runtime_candidate_sha": candidate_sha,
                "prior_runtime_candidate_sha": prior_candidate_sha,
                "runtime_candidate_chain": [
                    INITIAL_RUNTIME_CANDIDATE_SHA,
                    FIRST_RERUN_RUNTIME_CANDIDATE_SHA,
                    PRIOR_RUNTIME_CANDIDATE_SHA,
                    candidate_sha,
                ],
                "prior_provider_request_count": prior_request_count,
                "current_provider_request_count": generator.request_count,
                "provider_request_count": generator.cumulative_request_count,
                "provider_request_budget": MAX_PROVIDER_REQUESTS,
                "transport_retry_count": 0,
                "records": cumulative_public_ledger,
                "status": "PASS",
            },
        )
    except Exception as exc:
        if not (evidence_root / "suite-failure.json").exists():
            _write_private_json(
                evidence_root / "suite-failure.json",
                {
                    "error_type": type(exc).__name__,
                    "provider_request_count": generator.request_count if "generator" in locals() else 0,
                    "runtime_candidate_sha": candidate_sha,
                    "status": "FAILED_SAFE",
                },
            )
        if not (evidence_root / "SHA256SUMS").exists():
            _write_checksums(evidence_root)
        raise
    print(
        "GATED_FORMAL_SUITE_OK scenarios=8 anomalies=8 "
        f"provider_requests={generator.request_count} retries=0 candidate={candidate_sha}"
    )
    return 0


def _launcher(arguments: argparse.Namespace) -> int:
    env_file = cast(Path, arguments.env_file).resolve()
    if env_file != _ENV_PATH:
        raise RuntimeError("only the authorized project dotenv path may be parsed")
    protected = parse_authorized_deepseek_env(env_file)
    child_environment = os.environ.copy()
    for key in tuple(child_environment):
        if key.startswith("DEEPSEEK_"):
            child_environment.pop(key)
    child_environment.update(protected)
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--internal-run",
        "--candidate-sha",
        str(arguments.candidate_sha),
        "--app-database-url",
        str(arguments.app_database_url),
        "--registration",
        str(arguments.registration),
        "--contract",
        str(arguments.contract),
        "--prior-ledger",
        str(arguments.prior_ledger),
        "--evidence-root",
        str(arguments.evidence_root),
        "--public-evidence",
        str(arguments.public_evidence),
        "--public-ledger",
        str(arguments.public_ledger),
    ]
    completed = subprocess.run(command, cwd=_ROOT, env=child_environment, check=False)
    return completed.returncode


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--internal-run", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--app-database-url", required=True)
    parser.add_argument("--registration", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--prior-ledger", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--public-evidence", type=Path, required=True)
    parser.add_argument("--public-ledger", type=Path, required=True)
    parser.add_argument("--env-file", type=Path)
    arguments = parser.parse_args()
    if arguments.internal_run:
        if arguments.env_file is not None:
            raise RuntimeError("internal acceptance child never reads dotenv")
        if any(not os.environ.get(key) for key in AUTHORIZED_KEYS):
            raise RuntimeError("internal acceptance child lacks authorized DeepSeek environment")
        return _internal_run(arguments)
    if arguments.env_file is None:
        raise RuntimeError("formal acceptance launcher requires the authorized dotenv path")
    return _launcher(arguments)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (DomainError, GenerationFailed, RuntimeError, ValueError) as error:
        print(f"GATED_FORMAL_SUITE_FAILED_SAFE error_type={type(error).__name__}", file=sys.stderr)
        raise SystemExit(1) from error
