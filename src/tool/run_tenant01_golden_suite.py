from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
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
from src.shared.product_value import build_product_value_contract
from src.shared.types import ContentTarget, ProductFact
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
    TENANT01_HARD_BOUNDARIES,
    TENANT01_REVIEW_DIMENSIONS,
    Tenant01ArtifactInput,
    Tenant01HumanReview,
    write_tenant01_evidence,
)

_SUITE_VERSION = "TENANT-01-GOLDEN-V1"
_MODEL = "deepseek-v4-flash"


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


@dataclass(frozen=True)
class _Card:
    card_id: str
    message: str
    target: str
    series_position: int | None = None


def _config_cards(config_path: Path, *, p2_sku: str) -> tuple[_Card, ...]:
    document = _json_object(config_path)
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
    if {card.card_id for card in cards} != TENANT01_CARD_IDS or len(cards) != len(
        TENANT01_CARD_IDS
    ):
        raise ValueError("TENANT-01 golden card coverage drifted")
    return tuple(cards)


def _assert_p2_product_ready(products: tuple[ProductFact, ...]) -> None:
    """Reject an ineligible golden P2 fixture before the first provider call."""
    try:
        contract = build_product_value_contract(
            primary_product="product_truth",
            products=products,
        )
    except GenerationFailed as exc:
        raise RuntimeError(
            "TENANT-01 P2 fixture lacks a frozen product-specific value contract"
        ) from exc
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
        "production": result.get("production"),
        "ai_generated": result.get("ai_generated"),
        "aigc_label": result.get("aigc_label"),
        "aigc_release_reminder": result.get("aigc_release_reminder"),
        "formal_snapshot": {
            key: snapshot.get(key)
            for key in (
                "brand_context_packet",
                "account_editorial_lens",
                "account_editorial_lens_digest",
                "profile_version",
                "content_role",
                "publishing_target",
                "product_facts",
                "media_capability_envelope",
                "media_program",
                "series_context",
            )
        },
    }


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
    if (
        not questions
        or any(event.get("event") == "completed" for event in events)
        or before != after
    ):
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
    if _git_status():
        raise RuntimeError("TENANT-01 final suite requires a clean worktree")
    if root.exists():
        raise RuntimeError("TENANT-01 evidence directory already exists")
    database_url = os.environ.get("DIYU_APP_DATABASE_URL", "")
    if not database_url:
        raise RuntimeError("formal application database is unavailable")
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
    generator = _EvidenceDeepSeekGenerator(
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
                "title": f"把选择留给人的三篇观察 · {implementation_sha[:12]}",
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
        },
    )


def _reviews(path: Path) -> tuple[Tenant01HumanReview, ...]:
    document = _json_object(path)
    if document.get("review_contract") != "TENANT-01-HUMAN-REVIEW-V1":
        raise ValueError("TENANT-01 human-review contract drifted")
    raw_reviews = document.get("reviews")
    if not isinstance(raw_reviews, list):
        raise ValueError("TENANT-01 human reviews are unavailable")
    reviews: list[Tenant01HumanReview] = []
    for raw in raw_reviews:
        if not isinstance(raw, dict):
            raise ValueError("TENANT-01 human review is invalid")
        scores = raw.get("scores")
        excerpts = raw.get("excerpts")
        boundaries = raw.get("hard_boundaries")
        demonstration_checks = raw.get("demonstration_checks")
        comparison = raw.get("comparison")
        if not isinstance(scores, dict) or not isinstance(excerpts, dict) or not isinstance(
            boundaries, dict
        ) or not isinstance(demonstration_checks, dict) or not isinstance(
            comparison, dict
        ):
            raise ValueError("TENANT-01 human review evidence is incomplete")
        if set(scores) != set(TENANT01_REVIEW_DIMENSIONS) or any(
            type(value) is not int for value in scores.values()
        ):
            raise ValueError("TENANT-01 human review scores are invalid")
        if set(boundaries) != set(TENANT01_HARD_BOUNDARIES) or any(
            type(value) is not bool for value in boundaries.values()
        ):
            raise ValueError("TENANT-01 human review boundaries are invalid")
        if set(excerpts) != {"title", "body", "media", "caption"} or any(
            not isinstance(value, str) for value in excerpts.values()
        ):
            raise ValueError("TENANT-01 human review excerpts are invalid")
        if set(demonstration_checks) != set(TENANT01_DEMONSTRATION_CHECKS) or any(
            type(value) is not bool for value in demonstration_checks.values()
        ):
            raise ValueError("TENANT-01 demonstration checks are invalid")
        if set(comparison) != set(TENANT01_COMPARISON_FIELDS) or any(
            not isinstance(value, str) for value in comparison.values()
        ):
            raise ValueError("TENANT-01 cross-card comparison is invalid")
        reviews.append(
            Tenant01HumanReview(
                card_id=str(raw.get("card_id", "")),
                artifact_file=str(raw.get("artifact_file", "")),
                scores={str(key): cast(int, value) for key, value in scores.items()},
                excerpts={str(key): str(value) for key, value in excerpts.items()},
                hard_boundaries={str(key): cast(bool, value) for key, value in boundaries.items()},
                demonstration_checks={
                    str(key): cast(bool, value)
                    for key, value in demonstration_checks.items()
                },
                comparison={str(key): str(value) for key, value in comparison.items()},
                brand_basis=str(raw.get("brand_basis", "")),
                verdict=str(raw.get("verdict", "")),
                notes=str(raw.get("notes", "")),
            )
        )
    return tuple(reviews)


def _finalize(args: argparse.Namespace) -> None:
    root = Path(args.evidence_root).resolve()
    implementation_sha = _current_head()
    if implementation_sha != args.implementation_sha:
        raise RuntimeError("current HEAD is not the frozen implementation SHA")
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
        p5_preflight_file="p5-no-media.json",
        dm01_file="dm01.json",
    )


def _json_object(path: Path) -> dict[str, object]:
    if path.stat().st_mode & 0o077:
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
    finalize.add_argument("--schema-revision", required=True)
    finalize.add_argument("--image-digest", required=True)
    finalize.add_argument("--source-manifest-digest", required=True)
    finalize.set_defaults(action=_finalize)
    return parser


def main() -> None:
    os.umask(0o077)
    args = _parser().parse_args()
    cast(Any, args.action)(args)


if __name__ == "__main__":
    main()
