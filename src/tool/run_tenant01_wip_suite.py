from __future__ import annotations

import argparse
import os
from importlib import import_module
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

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
from src.infrastructure.workbench_repository import PostgresWorkbenchRepository
from src.tool.execution_control import verify_runtime_action
from src.tool.run_gate_c_final_suite import (
    _EvidenceDeepSeekGenerator,
    _persistence_ids,
    _settings,
    _task_snapshot,
    _write_private_json,
)
from src.tool.run_tenant01_golden_suite import (
    _MODEL,
    _SUITE_VERSION,
    _artifact,
    _Card,
    _config_cards,
    _Journey,
    _preflight_p2_product,
    _stream_card,
)


def _selected_cards(
    args: argparse.Namespace,
    journey: _Journey,
) -> tuple[_Card, ...]:
    all_cards = _config_cards(Path(args.config).resolve(), p2_sku=journey.p2_sku)
    requested = tuple(dict.fromkeys(args.card))
    known = {card.card_id for card in all_cards}
    if not requested or any(card_id not in known for card_id in requested):
        raise ValueError("TENANT-01 WIP cards are empty or unknown")
    selected = tuple(card for card in all_cards if card.card_id in requested)
    selected_ids = {card.card_id for card in selected}
    if selected_ids & {"series2", "series3"} and "P4_series1" not in selected_ids:
        raise ValueError("TENANT-01 WIP continuation requires its first frozen series entry")
    if "series3" in selected_ids and "series2" not in selected_ids:
        raise ValueError("TENANT-01 WIP series3 requires series2")
    return selected


def _run(args: argparse.Namespace) -> None:
    os.umask(0o077)
    if len(args.implementation_sha) != 40 or any(
        character not in "0123456789abcdef"
        for character in args.implementation_sha
    ):
        raise ValueError("TENANT-01 WIP implementation SHA is invalid")
    root = Path(args.evidence_root).resolve()
    if root.exists():
        raise ValueError("TENANT-01 WIP evidence directory already exists")
    journey = _Journey.from_file(Path(args.journey_file).resolve())
    cards = _selected_cards(args, journey)
    database_url = os.environ.get("DIYU_APP_DATABASE_URL", "")
    if not database_url:
        raise RuntimeError("formal application database is unavailable")
    if any(card.card_id == "P2" for card in cards):
        _preflight_p2_product(database_url, journey, cards)
    root.mkdir(mode=0o700, parents=True)
    root.chmod(0o700)
    object_store = LocalObjectStore(str(root / "object-store"))
    settings = _settings(
        database_url=database_url,
        object_store_root=root / "object-store",
    )
    control_service = ContentControlService(
        PostgresContentControlRepository(database_url),
        object_store,
    )
    generator = _EvidenceDeepSeekGenerator(
        evidence_root=root,
        allowed_card_ids=frozenset(card.card_id for card in cards),
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
    failures: list[dict[str, str]] = []
    with TestClient(app, base_url="https://diyu.example") as client:
        client.cookies.set("diyu_session", journey.session_token)
        series_id: UUID | None = None
        if any(card.card_id in {"P4_series1", "series2", "series3"} for card in cards):
            wip_run_id = uuid4()
            response = client.post(
                "/api/v1/content/series",
                params={
                    "target": "xiaohongshu_graphic",
                    "publishing_identity_id": str(journey.publishing_identity_id),
                },
                json={
                    "title": (
                        "TENANT-01 WIP 连续观察 · "
                        f"{args.implementation_sha[:12]} · {str(wip_run_id)[:8]}"
                    ),
                    "premise": "从不打扰，推进到回应，再推进到留出选择。",
                },
            )
            if response.status_code != 201:
                raise RuntimeError("TENANT-01 WIP formal series could not be created")
            series_id = UUID(str(response.json()["id"]))
        for card in cards:
            try:
                result = _stream_card(
                    client,
                    generator,
                    card,
                    publishing_identity_id=journey.publishing_identity_id,
                    series_id=series_id or uuid4(),
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
            except (KeyError, RuntimeError, TypeError, ValueError) as exc:
                failures.append(
                    {
                        "card_id": card.card_id,
                        "failure": str(exc),
                    }
                )
    _write_private_json(
        root / "suite-config.json",
        {
            "suite_version": _SUITE_VERSION,
            "evidence_kind": "wip_shared_root_diagnosis_only",
            "implementation_sha": args.implementation_sha,
            "provider_config": {
                "model": _MODEL,
                "temperature": 0,
                "max_retries": 0,
            },
            "cards": [card.card_id for card in cards],
            "failures": failures,
        },
    )
    if failures:
        failed_ids = ", ".join(item["card_id"] for item in failures)
        raise RuntimeError(
            f"TENANT-01 WIP cards did not all commit: {failed_ids}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a bounded TENANT-01 WIP card subset without finalizing evidence."
    )
    parser.add_argument("--implementation-sha", required=True)
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--journey-file", required=True)
    parser.add_argument("--config", default="config/tenant01/golden-v1.json")
    parser.add_argument("--card", action="append", required=True)
    arguments = parser.parse_args()
    verify_runtime_action("model_runner")
    _run(arguments)


if __name__ == "__main__":
    main()
