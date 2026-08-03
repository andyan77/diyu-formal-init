from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import asdict, dataclass
from importlib import import_module
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import psycopg
from fastapi.testclient import TestClient

from src.brain.content_control_service import ContentControlService
from src.brain.content_service import ContentService
from src.brain.workbench_service import WorkbenchService
from src.gateway.api.app import create_app
from src.infrastructure.content_control_repository import (
    PostgresContentControlRepository,
)
from src.infrastructure.local_object_store import LocalObjectStore
from src.infrastructure.postgres_repository import PostgresContentRepository
from src.infrastructure.production_auth import ProductionAuthRepository
from src.infrastructure.workbench_repository import PostgresWorkbenchRepository
from src.shared.errors import GenerationFailed
from src.shared.narrative import visible_digest
from src.shared.product_value import build_product_decision_basis_v2
from src.shared.types import ContentTarget, ProductFact
from src.tool.execution_control import verify_runtime_action
from src.tool.run_gate_c_final_suite import (
    _current_head,
    _EvidenceDeepSeekGenerator,
    _git_status,
    _persistence_ids,
    _settings,
    _task_snapshot,
    _write_private_json,
)
from src.tool.tenant01_evidence import (
    TENANT01_CARD_IDS,
    TENANT01_COMPARISON_FIELDS,
    TENANT01_DEMONSTRATION_CHECKS,
    TENANT01_GENERALIZATION_CASE_IDS,
    TENANT01_GENERALIZATION_CONFIG_SHA256,
    TENANT01_GENERATION_LEDGER_FILE,
    TENANT01_GENERATION_LEDGER_VERSION,
    TENANT01_HARD_BOUNDARIES,
    TENANT01_PROVIDER_MODEL,
    TENANT01_RAW_BUNDLE_VERSION,
    TENANT01_REVIEW_DIMENSIONS,
    TENANT01_SUITE_VERSION,
    Tenant01ArtifactInput,
    Tenant01EvidenceError,
    Tenant01GeneralizationReview,
    Tenant01HumanReview,
    compile_tenant01_snapshot_delivery,
    sha256_file,
    write_tenant01_evidence,
)

_SUITE_VERSION = TENANT01_SUITE_VERSION
_MODEL = TENANT01_PROVIDER_MODEL
_FINAL_OUTPUT_FILES = ("human-review.json", "manifest.json", "SHA256SUMS")
_FAILURE_MARKER_FILES = ("suite-failure.json", "human-review-failure.json")
_MINIMUM_FINAL_SUITE_SESSION_LEASE_SECONDS = 15 * 60
_EVIDENCE_SERIES_TITLE = "把选择留给人的三篇观察"
_PROTECTED_PROJECT_MEMORY_STATUS = " M docs/项目记忆.md"


def _canonical_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    ).hexdigest()


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _has_disallowed_worktree_change(status: str) -> bool:
    lines = tuple(line for line in status.splitlines() if line)
    return any(line != _PROTECTED_PROJECT_MEMORY_STATUS for line in lines)


class _Tenant01EvidenceGenerator(_EvidenceDeepSeekGenerator):
    """Add stage and request bindings to the inherited raw provider trace."""

    def _request(
        self,
        system: str,
        prompt: str,
        max_tokens: int,
        *,
        thinking_disabled: bool = True,
        timeout_seconds: float | None = None,
    ) -> tuple[dict[str, Any], int]:
        payload, retries = super()._request(
            system,
            prompt,
            max_tokens,
            thinking_disabled=thinking_disabled,
            timeout_seconds=timeout_seconds,
        )
        request_index = len(self._responses)
        if request_index not in {1, 2} or payload.get("model") != _MODEL:
            raise RuntimeError("TENANT-01 provider stage or model drifted")
        stages = ("intake", "writer")
        request_payload: dict[str, object] = {
            "model": _MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.0,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        if thinking_disabled:
            request_payload["thinking"] = {"type": "disabled"}
        self._responses[-1].update(
            {
                "stage": stages[request_index - 1],
                "model": _MODEL,
                "request_sha256": _canonical_digest(request_payload),
                "response_sha256": _canonical_digest(payload),
            }
        )
        return payload, retries


@dataclass(frozen=True)
class _Journey:
    tenant_id: UUID
    session_token: str
    publishing_identity_id: UUID
    p2_sku: str

    @classmethod
    def from_file(cls, path: Path) -> _Journey:
        document = _json_object(path)
        required = {
            "tenant_id",
            "session_token",
            "publishing_identity_id",
            "p2_sku",
        }
        if set(document) != required:
            raise ValueError("TENANT-01 journey fields drifted")
        session_token = str(document["session_token"])
        p2_sku = str(document["p2_sku"]).strip()
        if not session_token or not p2_sku:
            raise ValueError("TENANT-01 journey is incomplete")
        return cls(
            tenant_id=UUID(str(document["tenant_id"])),
            session_token=session_token,
            publishing_identity_id=UUID(str(document["publishing_identity_id"])),
            p2_sku=p2_sku,
        )


def _assert_final_suite_session_lease(
    database_url: str,
    journey: _Journey,
) -> None:
    token_digest = hashlib.sha256(journey.session_token.encode("utf-8")).hexdigest()
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1
              FROM tenant_sessions
             WHERE tenant_id = %s
               AND token_digest = %s
               AND audience = 'tenant-user'
               AND revoked_at IS NULL
               AND expires_at >= now() + make_interval(secs => %s)
            """,
            (
                journey.tenant_id,
                token_digest,
                _MINIMUM_FINAL_SUITE_SESSION_LEASE_SECONDS,
            ),
        )
        row = cursor.fetchone()
    if row is None:
        raise RuntimeError("TENANT-01 final suite requires a fresh tenant-user session lease")


@dataclass(frozen=True)
class _FormalPublicationSummary:
    public_brand_name: str
    projection_status: str
    source_document_count: int
    source_segment_count: int
    source_bound_writer_item_count: int
    publication_roles: frozenset[str]


@dataclass(frozen=True)
class _FormalAccountSummary:
    logical_account_id: UUID
    account_name: str
    business_data_kind: str
    enabled: bool
    control_organization_declared: bool
    content_role: str
    profile_id: UUID
    profile_version: int
    complete_segment_count: int
    profile_confirmed_by_enabled_manager: bool


def _assert_formal_publication_summary(
    summary: _FormalPublicationSummary,
) -> None:
    required_roles = frozenset({"public_brand_fact", "expression_constraint"})
    if (
        summary.public_brand_name != "笛语"
        or summary.projection_status != "confirmed"
        or summary.source_document_count != 21
        or summary.source_segment_count != 5_046
        or summary.source_bound_writer_item_count < len(required_roles)
        or not required_roles.issubset(summary.publication_roles)
    ):
        raise RuntimeError("TENANT-01 final suite requires the confirmed source-bound 笛语 publication projection")


def _formal_publication_summary(
    database_url: str,
    *,
    tenant_id: UUID,
    brand_id: UUID,
) -> _FormalPublicationSummary:
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT set_config('app.tenant_id', %s, true)",
            (str(tenant_id),),
        )
        cursor.execute(
            """
            SELECT brand.public_name, projection.status,
                   (SELECT count(*)
                     FROM brand_source_documents source
                     WHERE source.tenant_id = brand.tenant_id
                       AND source.brand_id = brand.id
                       AND source.status = 'active'),
                   (SELECT count(*)
                      FROM brand_source_segments segment
                      JOIN brand_source_documents source
                        ON source.tenant_id = segment.tenant_id
                       AND source.brand_id = segment.brand_id
                       AND source.id = segment.document_id
                       AND source.current_version_id = segment.document_version_id
                       AND source.status = 'active'
                     WHERE segment.tenant_id = brand.tenant_id
                       AND segment.brand_id = brand.id),
                   count(*) FILTER (
                       WHERE item.source_kind = 'brand_source_segment'
                         AND item.publication_role <> 'internal_only'
                   ),
                   array_agg(DISTINCT item.publication_role) FILTER (
                       WHERE item.publication_role <> 'internal_only'
                   )
              FROM brands brand
              JOIN brand_publication_projections projection
                ON projection.tenant_id = brand.tenant_id
               AND projection.brand_id = brand.id
               AND projection.id = brand.current_publication_projection_id
              LEFT JOIN brand_publication_projection_items item
                ON item.tenant_id = projection.tenant_id
               AND item.brand_id = projection.brand_id
               AND item.projection_id = projection.id
             WHERE brand.tenant_id = %s AND brand.id = %s
             GROUP BY brand.tenant_id, brand.id, brand.public_name,
                      projection.id, projection.status
            """,
            (tenant_id, brand_id),
        )
        row = cursor.fetchone()
    if row is None:
        raise RuntimeError("TENANT-01 final suite requires a current publication projection")
    roles = row[5] if isinstance(row[5], list) else []
    return _FormalPublicationSummary(
        public_brand_name=str(row[0] or ""),
        projection_status=str(row[1]),
        source_document_count=int(row[2]),
        source_segment_count=int(row[3]),
        source_bound_writer_item_count=int(row[4]),
        publication_roles=frozenset(str(value) for value in roles),
    )


def _assert_formal_account_summary(summary: _FormalAccountSummary) -> None:
    if (
        not summary.account_name.strip()
        or summary.business_data_kind != "formal_business_data"
        or not summary.enabled
        or not summary.control_organization_declared
        or not summary.content_role.strip()
        or summary.profile_version < 1
        or summary.complete_segment_count != 5
        or not summary.profile_confirmed_by_enabled_manager
    ):
        raise RuntimeError(
            "TENANT-01 final suite requires a current administrator-confirmed formal logical-account profile"
        )


def _formal_account_summary(
    database_url: str,
    *,
    tenant_id: UUID,
    brand_id: UUID,
    publishing_identity_id: UUID,
) -> _FormalAccountSummary:
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT set_config('app.tenant_id', %s, true)",
            (str(tenant_id),),
        )
        cursor.execute(
            """
            SELECT root.id, root.name, root.business_data_kind, root.enabled,
                   (root.control_organization_id IS NOT NULL
                    AND root.control_organization_source = 'declared'),
                   role.name, profile.id, profile.version,
                   (CASE WHEN btrim(profile.identity_position) <> '' THEN 1 ELSE 0 END
                    + CASE WHEN btrim(profile.authority_boundary) <> '' THEN 1 ELSE 0 END
                    + CASE WHEN btrim(profile.audience_relationship) <> '' THEN 1 ELSE 0 END
                    + CASE WHEN btrim(profile.content_territories) <> '' THEN 1 ELSE 0 END
                    + CASE WHEN btrim(profile.default_production_conditions) <> '' THEN 1 ELSE 0 END),
                   EXISTS (
                       SELECT 1
                         FROM tenant_management_grants management_grant
                         JOIN users manager
                           ON manager.tenant_id = management_grant.tenant_id
                          AND manager.id = management_grant.user_id
                          AND manager.enabled = true
                        WHERE management_grant.tenant_id = root.tenant_id
                          AND management_grant.user_id = profile.created_by
                          AND management_grant.enabled = true
                   )
              FROM content_accounts selected
              JOIN content_accounts root
                ON root.tenant_id = selected.tenant_id
               AND root.id = COALESCE(selected.carrier_of_account_id, selected.id)
              JOIN brands brand
                ON brand.tenant_id = root.tenant_id
               AND brand.id = root.brand_id
              JOIN brand_publication_projections projection
                ON projection.tenant_id = brand.tenant_id
               AND projection.brand_id = brand.id
               AND projection.id = brand.current_publication_projection_id
               AND projection.status = 'confirmed'
              JOIN account_expression_profile_versions profile
                ON profile.tenant_id = root.tenant_id
               AND profile.account_id = root.id
               AND profile.id = root.current_expression_profile_id
              JOIN account_content_roles account_role
                ON account_role.tenant_id = root.tenant_id
               AND account_role.account_id = root.id
              JOIN content_roles role
                ON role.tenant_id = account_role.tenant_id
               AND role.id = account_role.content_role_id
             WHERE selected.tenant_id = %s
               AND selected.brand_id = %s
               AND selected.id = %s
               AND selected.enabled = true
               AND selected.platform_enabled = true
               AND selected.business_data_kind = 'formal_business_data'
               AND root.brand_id = %s
               AND root.carrier_of_account_id IS NULL
            """,
            (tenant_id, brand_id, publishing_identity_id, brand_id),
        )
        rows = cursor.fetchall()
    if len(rows) != 1:
        raise RuntimeError("TENANT-01 final suite requires one formal logical-account identity")
    row = rows[0]
    return _FormalAccountSummary(
        logical_account_id=UUID(str(row[0])),
        account_name=str(row[1]),
        business_data_kind=str(row[2]),
        enabled=bool(row[3]),
        control_organization_declared=bool(row[4]),
        content_role=str(row[5]),
        profile_id=UUID(str(row[6])),
        profile_version=int(row[7]),
        complete_segment_count=int(row[8]),
        profile_confirmed_by_enabled_manager=bool(row[9]),
    )


@dataclass(frozen=True)
class _Card:
    card_id: str
    message: str
    target: str
    series_position: int | None = None


def _config_cards(config_path: Path, *, p2_sku: str) -> tuple[_Card, ...]:
    document = _json_object(config_path, require_private=False)
    if document.get("suite_version") != _SUITE_VERSION:
        raise ValueError("TENANT-01 golden contract version drifted")
    raw_cards = document.get("cards")
    if not isinstance(raw_cards, list):
        raise ValueError("TENANT-01 golden cards are unavailable")
    cards: list[_Card] = []
    for raw in raw_cards:
        if not isinstance(raw, dict):
            raise ValueError("TENANT-01 golden card is invalid")
        card_id = str(raw.get("card_id", ""))
        message = str(raw.get("message", "")).replace("{p2_sku}", p2_sku)
        target = str(raw.get("target", ""))
        raw_position = raw.get("series_position")
        position = int(raw_position) if raw_position is not None else None
        if not card_id or not message or not target:
            raise ValueError("TENANT-01 golden card is incomplete")
        cards.append(_Card(card_id, message, target, position))
    if {card.card_id for card in cards} != TENANT01_CARD_IDS or len(cards) != len(TENANT01_CARD_IDS):
        raise ValueError("TENANT-01 golden card coverage drifted")
    return tuple(cards)


def _assert_p2_product_ready(products: tuple[ProductFact, ...]) -> None:
    """Reject an ineligible golden P2 fixture before the first provider call."""
    try:
        contract = build_product_decision_basis_v2(
            primary_product="product_truth",
            products=products,
        )
    except GenerationFailed as exc:
        raise RuntimeError("TENANT-01 P2 fixture lacks a frozen product-specific value contract") from exc
    if contract is None:
        raise RuntimeError("TENANT-01 P2 fixture did not produce a product value contract")


def _preflight_p2_product(
    database_url: str,
    journey: _Journey,
    cards: tuple[_Card, ...],
) -> None:
    p2_cards = tuple(card for card in cards if card.card_id == "P2")
    if len(p2_cards) != 1:
        raise RuntimeError("TENANT-01 golden suite requires exactly one P2 card")
    card = p2_cards[0]
    if card.target != "xiaohongshu_graphic":
        raise RuntimeError("TENANT-01 P2 target drifted")
    auth_repository = ProductionAuthRepository(database_url)
    identity = auth_repository.load_tenant_session(journey.session_token)
    if identity is None or identity.tenant_id != journey.tenant_id:
        raise RuntimeError("TENANT-01 P2 formal session is unavailable")
    scope = auth_repository.content_scope(
        identity,
        cast(ContentTarget, card.target),
        journey.publishing_identity_id,
    )
    _assert_formal_publication_summary(
        _formal_publication_summary(
            database_url,
            tenant_id=journey.tenant_id,
            brand_id=scope.brand_id,
        )
    )
    _assert_formal_account_summary(
        _formal_account_summary(
            database_url,
            tenant_id=journey.tenant_id,
            brand_id=scope.brand_id,
            publishing_identity_id=journey.publishing_identity_id,
        )
    )
    products = PostgresContentRepository(database_url).load_product_facts(
        scope,
        card.message,
    )
    if len(products) != 1 or products[0].sku != journey.p2_sku:
        raise RuntimeError("TENANT-01 P2 fixture does not resolve one frozen product")
    _assert_p2_product_ready(products)


def _persistence_counts(database_url: str, tenant_id: UUID) -> tuple[int, int, int]:
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),))
        cursor.execute(
            "SELECT "
            "(SELECT count(*) FROM business_tasks WHERE tenant_id = %s), "
            "(SELECT count(*) FROM generation_runs WHERE tenant_id = %s), "
            "(SELECT count(*) FROM content_versions WHERE tenant_id = %s)",
            (tenant_id, tenant_id, tenant_id),
        )
        row = cursor.fetchone()
    if row is None:
        raise RuntimeError("TENANT-01 persistence counts are unavailable")
    return int(row[0]), int(row[1]), int(row[2])


def _next_evidence_series_title(
    database_url: str,
    *,
    tenant_id: UUID,
    created_by: UUID,
) -> str:
    """Keep failed-suite series immutable while choosing a natural unique title."""

    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT set_config('app.tenant_id', %s, true)",
            (str(tenant_id),),
        )
        cursor.execute(
            "SELECT count(*) FROM content_series WHERE tenant_id = %s AND created_by = %s",
            (tenant_id, created_by),
        )
        row = cursor.fetchone()
    if row is None:
        raise RuntimeError("TENANT-01 evidence series count is unavailable")
    return f"{_EVIDENCE_SERIES_TITLE} · 第{int(row[0]) + 1}组"


def _stream_card(
    client: TestClient,
    generator: _EvidenceDeepSeekGenerator,
    card: _Card,
    *,
    publishing_identity_id: UUID,
    series_id: UUID,
) -> dict[str, object]:
    series_card = card.card_id in {"P4_series1", "series2", "series3"}
    generator.begin_card(card.card_id)
    response = client.post(
        "/api/v1/content/stream",
        json={
            "message": card.message,
            "conversation": [],
            "publishing_identity_id": str(publishing_identity_id),
            "target": card.target,
            "material_ids": [],
            "interaction_mode": "generate",
            "direct_generate": True,
            "request_id": str(uuid4()),
            "series_id": str(series_id) if series_card else None,
            "series_position": card.series_position,
        },
    )
    if response.status_code != 200:
        generator.abort_card(event_names=(f"http_{response.status_code}",))
        raise RuntimeError(f"{card.card_id}: formal content API failed")
    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    completed = [event for event in events if event.get("event") == "completed"]
    if len(completed) != 1:
        generator.abort_card(
            event_names=tuple(str(event.get("event", "")) for event in events),
        )
        raise RuntimeError(f"{card.card_id}: formal content API did not commit once")
    generator.end_card()
    result = completed[0].get("result")
    if not isinstance(result, dict):
        raise RuntimeError(f"{card.card_id}: completed artifact is unavailable")
    return cast(dict[str, object], result)


def _artifact(
    card: _Card,
    result: dict[str, object],
    snapshot: dict[str, object],
    *,
    run_id: UUID,
    version_id: UUID,
) -> dict[str, object]:
    outline = result.get("outline")
    body = result.get("body")
    if not isinstance(outline, str) or not outline.strip():
        raise RuntimeError(f"{card.card_id}: visible title is unavailable")
    if not isinstance(body, str) or not body.strip():
        raise RuntimeError(f"{card.card_id}: visible body is unavailable")
    formal_snapshot = {
        key: snapshot.get(key)
        for key in (
            "brand_context_packet",
            "account_expression_profile_id",
            "account_expression_profile_version",
            "account_expression",
            "original_direction",
            "user_premise",
            "content_role",
            "product_facts",
            "product_value_contract",
            "product_value_contract_digest",
            "publication_contract",
            "publication_contract_digest",
            "delivery_compiler_version",
            "writer_model",
            "immutable_product_fact_blocks",
            "visible_provenance",
            "delivery_resource_refs",
            "media_capability_envelope",
            "media_capability_envelope_digest",
            "media_program",
            "media_program_digest",
            "series_context",
            "narrative_frame",
            "creative_plan_v2",
            "writer_request_v3",
            "writer_request_v3_digest",
            "writer_output_v3",
            "writer_output_v3_digest",
            "creative_kernel_v5",
            "creative_kernel_v2",
            "expression_plan_digest",
            "deterministic_checked_kernel_digest",
            "reviewed_kernel_digest",
            "reviewed_creative_digest",
        )
    }
    formal_snapshot["publishing_target"] = card.target
    if formal_snapshot.get("user_premise") != card.message:
        raise RuntimeError(f"{card.card_id}: frozen premise drifted from the golden card")
    try:
        compiled = compile_tenant01_snapshot_delivery(
            formal_snapshot,
            card_id=card.card_id,
        )
    except Tenant01EvidenceError as exc:
        raise RuntimeError(f"{card.card_id}: frozen snapshot cannot rebuild production") from exc
    if compiled.outline != outline or compiled.body != body:
        raise RuntimeError(f"{card.card_id}: API result drifted from deterministic delivery")
    expected_provenance = {field: list(sources) for field, sources in compiled.visible_provenance.items()}
    if formal_snapshot.get("visible_provenance") != expected_provenance or formal_snapshot.get(
        "delivery_resource_refs"
    ) != list(compiled.resource_refs):
        raise RuntimeError(f"{card.card_id}: persisted delivery bindings drifted from compilation")
    return {
        "suite_version": _SUITE_VERSION,
        "card_id": card.card_id,
        "task_id": str(UUID(str(result.get("task_id")))),
        "run_id": str(run_id),
        "version_id": str(version_id),
        "version": result.get("version"),
        "outline": outline,
        "body": body,
        "visible_digest": visible_digest(outline, body),
        "production": asdict(compiled.production),
        "ai_generated": result.get("ai_generated"),
        "aigc_label": result.get("aigc_label"),
        "aigc_release_reminder": result.get("aigc_release_reminder"),
        "formal_snapshot": formal_snapshot,
    }


def _write_generation_ledger(
    root: Path,
    *,
    implementation_sha: str,
    cards: tuple[_Card, ...],
) -> str:
    records: list[dict[str, object]] = []
    identifiers: dict[str, list[str]] = {
        "task_id": [],
        "run_id": [],
        "version_id": [],
    }
    for card in cards:
        artifact_file = f"{card.card_id}.artifact.json"
        raw_response_file = f"{card.card_id}.raw.json"
        artifact_path = root / artifact_file
        raw_path = root / raw_response_file
        artifact = _json_object(artifact_path)
        raw = _json_object(raw_path)
        version = artifact.get("version")
        responses = raw.get("responses")
        if (
            artifact.get("suite_version") != _SUITE_VERSION
            or artifact.get("card_id") != card.card_id
            or raw.get("raw_bundle_version") != TENANT01_RAW_BUNDLE_VERSION
            or raw.get("card_id") != card.card_id
            or type(version) is not int
            or version < 1
            or not _is_sha256(artifact.get("visible_digest"))
            or type(raw.get("request_count")) is not int
            or not isinstance(responses, list)
            or raw.get("request_count") != len(responses)
            or len(responses) != 2
        ):
            raise RuntimeError(f"{card.card_id}: cannot freeze generation ledger")
        for field in identifiers:
            value = str(UUID(str(artifact.get(field))))
            identifiers[field].append(value)
        stages: list[str] = []
        request_hashes: list[str] = []
        response_hashes: list[str] = []
        expected_stages = ("intake", "writer")
        for request_index, response in enumerate(responses, start=1):
            payload = response.get("response") if isinstance(response, dict) else None
            if (
                not isinstance(response, dict)
                or set(response)
                != {
                    "request_index",
                    "transport_retries",
                    "stage",
                    "model",
                    "request_sha256",
                    "response_sha256",
                    "response",
                }
                or response.get("request_index") != request_index
                or response.get("transport_retries") != 0
                or response.get("stage") != expected_stages[request_index - 1]
                or response.get("model") != _MODEL
                or not _is_sha256(response.get("request_sha256"))
                or not _is_sha256(response.get("response_sha256"))
                or not isinstance(payload, dict)
                or not payload
                or payload.get("model") != _MODEL
                or _canonical_digest(payload) != response.get("response_sha256")
            ):
                raise RuntimeError(f"{card.card_id}: raw stage cannot enter generation ledger")
            choices = payload.get("choices")
            first_choice = choices[0] if isinstance(choices, list) and choices else None
            message = first_choice.get("message") if isinstance(first_choice, dict) else None
            if (
                not isinstance(message, dict)
                or not isinstance(message.get("content"), str)
                or not str(message["content"]).strip()
            ):
                raise RuntimeError(f"{card.card_id}: empty raw response cannot enter generation ledger")
            stages.append(str(response.get("stage", "")))
            request_hashes.append(str(response.get("request_sha256", "")))
            response_hashes.append(str(response.get("response_sha256", "")))
        records.append(
            {
                "card_id": card.card_id,
                **{field: values[-1] for field, values in identifiers.items()},
                "version": version,
                "artifact_file": artifact_file,
                "artifact_sha256": sha256_file(artifact_path),
                "visible_digest": artifact.get("visible_digest"),
                "raw_response_file": raw_response_file,
                "raw_response_sha256": sha256_file(raw_path),
                "provider_stages": stages,
                "request_hashes": request_hashes,
                "response_hashes": response_hashes,
            }
        )
    if any(len(set(values)) != len(values) for values in identifiers.values()):
        raise RuntimeError("TENANT-01 generation reused persistence identifiers")
    ledger_path = root / TENANT01_GENERATION_LEDGER_FILE
    _write_private_json(
        ledger_path,
        {
            "ledger_version": TENANT01_GENERATION_LEDGER_VERSION,
            "suite_version": _SUITE_VERSION,
            "implementation_sha": implementation_sha,
            "provider_config": {
                "model": _MODEL,
                "temperature": 0,
                "max_retries": 0,
            },
            "cards": records,
        },
    )
    ledger_path.chmod(0o400)
    return sha256_file(ledger_path)


def _p5_preflight(
    client: TestClient,
    *,
    database_url: str,
    journey: _Journey,
) -> dict[str, object]:
    before = _persistence_counts(database_url, journey.tenant_id)
    response = client.post(
        "/api/v1/content/stream",
        json={
            "message": "请用两件商品做一条商品视觉关系图文。",
            "conversation": [],
            "publishing_identity_id": str(journey.publishing_identity_id),
            "target": "xiaohongshu_graphic",
            "material_ids": [],
            "product_media_intent": True,
            "interaction_mode": "generate",
            "direct_generate": True,
            "request_id": str(uuid4()),
        },
    )
    if response.status_code != 200:
        raise RuntimeError("P5 no-media preflight API failed")
    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    questions = [event for event in events if event.get("kind") == "question"]
    after = _persistence_counts(database_url, journey.tenant_id)
    if not questions or any(event.get("event") == "completed" for event in events) or before != after:
        raise RuntimeError("P5 no-media preflight did not fail before persistence")
    return {
        "card_id": "P5_no_media",
        "provider_calls": 0,
        "persistence_delta": [after[index] - before[index] for index in range(3)],
        "result_kind": "question",
        "message_category": "缺少本次明确选择的正式商品媒体",
    }


def _generate(args: argparse.Namespace) -> None:
    root = Path(args.evidence_root).resolve()
    journey = _Journey.from_file(Path(args.journey_file).resolve())
    implementation_sha = _current_head()
    if implementation_sha != args.implementation_sha:
        raise RuntimeError("current HEAD is not the frozen implementation SHA")
    if _has_disallowed_worktree_change(_git_status()):
        raise RuntimeError("TENANT-01 final suite requires a clean worktree")
    if root.exists():
        raise RuntimeError("TENANT-01 evidence directory already exists")
    database_url = os.environ.get("DIYU_APP_DATABASE_URL", "")
    if not database_url:
        raise RuntimeError("formal application database is unavailable")
    _assert_final_suite_session_lease(database_url, journey)
    identity = ProductionAuthRepository(database_url).load_tenant_session(journey.session_token)
    if identity is None or identity.tenant_id != journey.tenant_id:
        raise RuntimeError("TENANT-01 final suite formal session is unavailable")
    cards = _config_cards(Path(args.config).resolve(), p2_sku=journey.p2_sku)
    _preflight_p2_product(database_url, journey, cards)
    root.mkdir(mode=0o700, parents=True)
    root.chmod(0o700)
    object_store_root = root / "object-store"
    settings = _settings(database_url=database_url, object_store_root=object_store_root)
    object_store = LocalObjectStore(str(object_store_root))
    control_service = ContentControlService(
        PostgresContentControlRepository(database_url),
        object_store,
    )
    generator = _Tenant01EvidenceGenerator(
        evidence_root=root,
        allowed_card_ids=TENANT01_CARD_IDS,
        api_base_url=cast(str, settings.deepseek_api_base_url),
        api_key=cast(Any, settings.deepseek_api_key).get_secret_value(),
        model=_MODEL,
        reviewer_provider=None,
        timeout_seconds=120.0,
        max_retries=0,
    )
    content_service = ContentService(
        PostgresContentRepository(database_url),
        generator,
        control_service,
    )
    api_runtime = cast(Any, import_module("src.gateway.api.app"))
    api_runtime.build_content_control_service = lambda _: control_service
    api_runtime.build_content_service = lambda _: content_service
    api_runtime.build_workbench_service = lambda _: WorkbenchService(
        PostgresWorkbenchRepository(database_url),
        object_store,
    )
    app = create_app(settings)
    with TestClient(app, base_url="https://diyu.example") as client:
        client.cookies.set("diyu_session", journey.session_token)
        series_response = client.post(
            "/api/v1/content/series",
            params={
                "target": "xiaohongshu_graphic",
                "publishing_identity_id": str(journey.publishing_identity_id),
            },
            json={
                "title": _next_evidence_series_title(
                    database_url,
                    tenant_id=journey.tenant_id,
                    created_by=identity.user_id,
                ),
                "premise": "从不打扰，推进到回应，再推进到留出选择。",
            },
        )
        if series_response.status_code != 201:
            raise RuntimeError("TENANT-01 formal series could not be created")
        series_id = UUID(str(series_response.json()["id"]))
        for card in cards:
            result = _stream_card(
                client,
                generator,
                card,
                publishing_identity_id=journey.publishing_identity_id,
                series_id=series_id,
            )
            task_id = UUID(str(result["task_id"]))
            version_number = int(cast(int, result["version"]))
            run_id, version_id = _persistence_ids(
                database_url,
                journey.tenant_id,
                task_id,
                version_number,
            )
            snapshot = _task_snapshot(database_url, journey.tenant_id, task_id)
            _write_private_json(
                root / f"{card.card_id}.artifact.json",
                _artifact(
                    card,
                    result,
                    snapshot,
                    run_id=run_id,
                    version_id=version_id,
                ),
            )
        _write_private_json(
            root / "p5-no-media.json",
            _p5_preflight(client, database_url=database_url, journey=journey),
        )
    ledger_sha256 = _write_generation_ledger(
        root,
        implementation_sha=implementation_sha,
        cards=cards,
    )
    _write_private_json(
        root / "suite-config.json",
        {
            "suite_version": _SUITE_VERSION,
            "implementation_sha": implementation_sha,
            "provider_config": {
                "model": _MODEL,
                "temperature": 0,
                "max_retries": 0,
            },
            "cards": [card.card_id for card in cards],
            "generation_ledger": {
                "file": TENANT01_GENERATION_LEDGER_FILE,
                "sha256": ledger_sha256,
            },
        },
    )


def _reviews(path: Path) -> tuple[Tenant01HumanReview, ...]:
    document = _json_object(path)
    if document.get("review_contract") != "TENANT-01-HUMAN-REVIEW-V2":
        raise ValueError("TENANT-01 human-review contract drifted")
    raw_reviews = document.get("reviews")
    if not isinstance(raw_reviews, list):
        raise ValueError("TENANT-01 human reviews are unavailable")
    reviews: list[Tenant01HumanReview] = []
    for raw in raw_reviews:
        if not isinstance(raw, dict) or set(raw) != {
            "card_id",
            "artifact_file",
            "artifact_sha256",
            "visible_digest",
            "hard_boundary",
            "product_usable",
            "quality_dimensions",
            "dimension_rationales",
            "title_excerpt",
            "body_excerpt",
            "media_excerpt",
            "caption_excerpt",
            "quality_observations",
            "residual_risks",
            "reviewer_scope",
            "reviewer_kind",
            "reviewed_at",
            "verdict",
        }:
            raise ValueError("TENANT-01 human review is invalid")
        dimensions = raw.get("quality_dimensions")
        rationales = raw.get("dimension_rationales")
        observations = raw.get("quality_observations")
        residual_risks = raw.get("residual_risks")
        if (
            not isinstance(dimensions, dict)
            or not isinstance(rationales, dict)
            or not isinstance(observations, list)
            or not isinstance(residual_risks, list)
        ):
            raise ValueError("TENANT-01 human review evidence is incomplete")
        if set(dimensions) != set(TENANT01_REVIEW_DIMENSIONS) or any(
            type(value) is not int for value in dimensions.values()
        ):
            raise ValueError("TENANT-01 human review scores are invalid")
        if set(rationales) != set(TENANT01_REVIEW_DIMENSIONS) or any(
            not isinstance(value, str) or not value.strip() for value in rationales.values()
        ):
            raise ValueError("TENANT-01 human review rationales are invalid")
        excerpts = {
            "title": raw.get("title_excerpt"),
            "body": raw.get("body_excerpt"),
            "media": raw.get("media_excerpt"),
            "caption": raw.get("caption_excerpt"),
        }
        if any(not isinstance(value, str) for value in excerpts.values()):
            raise ValueError("TENANT-01 human review excerpts are invalid")
        if any(not isinstance(value, str) for value in observations) or any(
            not isinstance(value, str) for value in residual_risks
        ):
            raise ValueError("TENANT-01 human review observations are invalid")
        artifact_sha256 = raw.get("artifact_sha256")
        visible_digest_value = raw.get("visible_digest")
        if not _is_sha256(artifact_sha256) or not _is_sha256(visible_digest_value):
            raise ValueError("TENANT-01 human review is not artifact-bound")
        reviews.append(
            Tenant01HumanReview(
                card_id=str(raw.get("card_id", "")),
                artifact_file=str(raw.get("artifact_file", "")),
                artifact_sha256=cast(str, artifact_sha256),
                visible_digest=cast(str, visible_digest_value),
                scores={str(key): cast(int, value) for key, value in dimensions.items()},
                excerpts={str(key): str(value) for key, value in excerpts.items()},
                hard_boundaries={boundary: raw.get("hard_boundary") == "PASS" for boundary in TENANT01_HARD_BOUNDARIES},
                demonstration_checks={
                    check: raw.get("product_usable") == "PASS" for check in TENANT01_DEMONSTRATION_CHECKS
                },
                comparison={field: str(rationales.get("platform_fit", "")) for field in TENANT01_COMPARISON_FIELDS},
                brand_basis=str(rationales.get("brand_relation", "")),
                verdict=str(raw.get("verdict", "")),
                notes="\n".join(
                    (
                        *cast(list[str], observations),
                        *cast(list[str], residual_risks),
                    )
                )
                or "逐篇全文审阅，未记录额外质量观察或残余风险。",
                hard_boundary=str(raw.get("hard_boundary", "")),
                product_usable=str(raw.get("product_usable", "")),
                quality_dimensions={str(key): cast(int, value) for key, value in dimensions.items()},
                dimension_rationales={str(key): str(value) for key, value in rationales.items()},
                title_excerpt=str(raw.get("title_excerpt", "")),
                body_excerpt=str(raw.get("body_excerpt", "")),
                media_excerpt=str(raw.get("media_excerpt", "")),
                caption_excerpt=str(raw.get("caption_excerpt", "")),
                quality_observations=tuple(cast(list[str], observations)),
                residual_risks=tuple(cast(list[str], residual_risks)),
                reviewer_scope=str(raw.get("reviewer_scope", "")),
                reviewer_kind=str(raw.get("reviewer_kind", "")),
                reviewed_at=str(raw.get("reviewed_at", "")),
            )
        )
    return tuple(reviews)


def _generalization_reviews(path: Path) -> tuple[Tenant01GeneralizationReview, ...]:
    document = _json_object(path)
    if (
        document.get("review_contract") != "TENANT-01-GENERALIZATION-REVIEW-V1"
        or document.get("set_kind") != "frozen_generalization_regression"
    ):
        raise ValueError("TENANT-01 generalization review contract drifted")
    raw_reviews = document.get("reviews")
    if not isinstance(raw_reviews, list):
        raise ValueError("TENANT-01 generalization reviews are unavailable")
    reviews: list[Tenant01GeneralizationReview] = []
    required = {
        "case_id",
        "result_file",
        "result_sha256",
        "hard_boundary",
        "structure_complete",
        "product_usable",
        "excerpts",
        "quality_observations",
        "residual_risks",
        "reviewer_scope",
        "reviewer_kind",
        "reviewed_at",
    }
    for raw in raw_reviews:
        if not isinstance(raw, dict) or set(raw) != required:
            raise ValueError("TENANT-01 generalization review is invalid")
        excerpts = raw.get("excerpts")
        observations = raw.get("quality_observations")
        residual_risks = raw.get("residual_risks")
        if (
            not isinstance(excerpts, dict)
            or any(not isinstance(key, str) or not isinstance(value, str) for key, value in excerpts.items())
            or not isinstance(observations, list)
            or any(not isinstance(value, str) for value in observations)
            or not isinstance(residual_risks, list)
            or any(not isinstance(value, str) for value in residual_risks)
            or not _is_sha256(raw.get("result_sha256"))
        ):
            raise ValueError("TENANT-01 generalization review evidence is incomplete")
        reviews.append(
            Tenant01GeneralizationReview(
                case_id=str(raw.get("case_id", "")),
                result_file=str(raw.get("result_file", "")),
                result_sha256=cast(str, raw["result_sha256"]),
                hard_boundary=str(raw.get("hard_boundary", "")),
                structure_complete=str(raw.get("structure_complete", "")),
                product_usable=str(raw.get("product_usable", "")),
                excerpts={str(key): str(value) for key, value in excerpts.items()},
                quality_observations=tuple(cast(list[str], observations)),
                residual_risks=tuple(cast(list[str], residual_risks)),
                reviewer_scope=str(raw.get("reviewer_scope", "")),
                reviewer_kind=str(raw.get("reviewer_kind", "")),
                reviewed_at=str(raw.get("reviewed_at", "")),
            )
        )
    if {review.case_id for review in reviews} != TENANT01_GENERALIZATION_CASE_IDS:
        raise ValueError("TENANT-01 generalization review coverage drifted")
    return tuple(reviews)


def _assert_finalizable_evidence_root(
    root: Path,
    *,
    implementation_sha: str,
) -> None:
    if not root.is_dir() or root.stat().st_mode & 0o077:
        raise RuntimeError("TENANT-01 evidence root is unavailable or not private")
    failure_markers = sorted(
        {
            *(path.name for path in root.glob("*.failed.raw.json")),
            *(filename for filename in _FAILURE_MARKER_FILES if (root / filename).exists()),
        }
    )
    if failure_markers:
        raise RuntimeError("TENANT-01 failed evidence root is immutable and cannot be finalized")
    if any((root / filename).exists() for filename in _FINAL_OUTPUT_FILES):
        raise RuntimeError("TENANT-01 final evidence outputs already exist")
    config_path = root / "suite-config.json"
    if not config_path.is_file():
        raise RuntimeError("TENANT-01 final suite config is unavailable")
    config = _json_object(config_path)
    if config.get("evidence_kind") is not None:
        raise RuntimeError("TENANT-01 WIP evidence cannot be finalized")
    if set(config) != {
        "suite_version",
        "implementation_sha",
        "provider_config",
        "cards",
        "generation_ledger",
    }:
        raise RuntimeError("TENANT-01 final suite config fields drifted")
    provider = config.get("provider_config")
    cards = config.get("cards")
    ledger = config.get("generation_ledger")
    if (
        config.get("suite_version") != _SUITE_VERSION
        or config.get("implementation_sha") != implementation_sha
        or not isinstance(provider, dict)
        or set(provider) != {"model", "temperature", "max_retries"}
        or provider.get("model") != _MODEL
        or type(provider.get("temperature")) is not int
        or provider.get("temperature") != 0
        or type(provider.get("max_retries")) is not int
        or provider.get("max_retries") != 0
        or not isinstance(cards, list)
        or any(not isinstance(card_id, str) for card_id in cards)
        or set(cards) != TENANT01_CARD_IDS
        or len(cards) != len(TENANT01_CARD_IDS)
        or not isinstance(ledger, dict)
        or set(ledger) != {"file", "sha256"}
        or ledger.get("file") != TENANT01_GENERATION_LEDGER_FILE
        or not _is_sha256(ledger.get("sha256"))
    ):
        raise RuntimeError("TENANT-01 final suite config is not authoritative")
    ledger_path = root / TENANT01_GENERATION_LEDGER_FILE
    if (
        not ledger_path.is_file()
        or ledger_path.stat().st_mode & 0o077
        or ledger_path.stat().st_mode & 0o222
        or sha256_file(ledger_path) != ledger["sha256"]
    ):
        raise RuntimeError("TENANT-01 generation ledger is unavailable or mutable")


def _finalize(args: argparse.Namespace) -> None:
    root = Path(args.evidence_root).resolve()
    implementation_sha = _current_head()
    if implementation_sha != args.implementation_sha:
        raise RuntimeError("current HEAD is not the frozen implementation SHA")
    if _has_disallowed_worktree_change(_git_status()):
        raise RuntimeError("TENANT-01 finalization requires a clean worktree")
    _assert_finalizable_evidence_root(
        root,
        implementation_sha=implementation_sha,
    )
    generalization_config = Path(args.generalization_config).resolve()
    if sha256_file(generalization_config) != TENANT01_GENERALIZATION_CONFIG_SHA256:
        raise RuntimeError("TENANT-01 frozen generalization regression set drifted")
    write_tenant01_evidence(
        root,
        implementation_sha=implementation_sha,
        schema_revision=args.schema_revision,
        image_digest=args.image_digest,
        source_manifest_digest=args.source_manifest_digest,
        artifacts=tuple(
            Tenant01ArtifactInput(
                card_id,
                f"{card_id}.artifact.json",
                f"{card_id}.raw.json",
            )
            for card_id in sorted(TENANT01_CARD_IDS)
        ),
        reviews=_reviews(Path(args.review_file).resolve()),
        generalization_reviews=_generalization_reviews(
            Path(args.generalization_review_file).resolve()
        ),
        p5_preflight_file="p5-no-media.json",
        dm01_file="dm01.json",
    )


def _json_object(
    path: Path,
    *,
    require_private: bool = True,
) -> dict[str, object]:
    if require_private and path.stat().st_mode & 0o077:
        raise ValueError(f"{path.name} must be private")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain one JSON object")
    return cast(dict[str, object], value)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the formal TENANT-01 golden suite.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate = subparsers.add_parser("generate")
    generate.add_argument("--implementation-sha", required=True)
    generate.add_argument("--evidence-root", required=True)
    generate.add_argument("--journey-file", required=True)
    generate.add_argument("--config", default="config/tenant01/golden-v1.json")
    generate.set_defaults(action=_generate)
    finalize = subparsers.add_parser("finalize")
    finalize.add_argument("--implementation-sha", required=True)
    finalize.add_argument("--evidence-root", required=True)
    finalize.add_argument("--review-file", required=True)
    finalize.add_argument("--generalization-review-file", required=True)
    finalize.add_argument(
        "--generalization-config",
        default="config/tenant01/semantic-holdout-v1.json",
    )
    finalize.add_argument("--schema-revision", required=True)
    finalize.add_argument("--image-digest", required=True)
    finalize.add_argument("--source-manifest-digest", required=True)
    finalize.set_defaults(action=_finalize)
    return parser


def main() -> None:
    os.umask(0o077)
    args = _parser().parse_args()
    verify_runtime_action(
        "model_runner" if args.command == "generate" else "evidence_finalizer"
    )
    cast(Any, args.action)(args)


if __name__ == "__main__":
    main()
