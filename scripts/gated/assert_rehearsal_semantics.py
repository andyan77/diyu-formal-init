from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import cast
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
from src.brain.platform_directions import direction_for  # noqa: E402
from src.infrastructure.postgres_repository import PostgresContentRepository  # noqa: E402
from src.shared.brand_publication import brand_context_packet_document  # noqa: E402
from src.shared.errors import DomainError  # noqa: E402
from src.shared.product_value import (  # noqa: E402
    build_product_decision_basis_v2,
    product_value_contract_document,
)
from src.shared.publication_scope import (  # noqa: E402
    AuthorizationContractV1,
    authorization_contract_document,
)
from src.shared.types import (  # noqa: E402
    BrandContext,
    BrandRelevanceQualificationV1,
    TrustedScope,
)

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
_ALLOWED_LOCAL_PREFIXES = {
    "H01": (),
    "R01": ("RK-EC-",),
    "R02": ("RK-SW-",),
    "S01": ("RK-EC-", "SK-HZ-"),
    "S02": ("RK-EC-", "SK-HZ-"),
    "S03": ("RK-EC-", "SK-HuZ-"),
    "S04": ("RK-SW-", "SK-CD-"),
}


def _scope(account_code: str) -> TrustedScope:
    organization_code = _ACCOUNT_ORGANIZATIONS[account_code]
    return TrustedScope(
        TENANT_ID,
        OPERATOR_IDS[organization_code],
        BRAND_ID,
        matrix_id(f"account:{account_code}"),
    )


def _context(account_code: str) -> BrandContext:
    return BrandContext(
        brand_name="笛语",
        positioning="真实穿衣问题",
        decision_order="先事实后判断",
        tone="真实自然",
        account_name=account_code,
        operator_name="Gate D 隔离操作人",
        organization_name=_ACCOUNT_ORGANIZATIONS[account_code],
        content_role_name="正式内容角色",
        content_role_boundary="只消费当前账号及组织合法资料",
        audience_description="本地家庭",
        strategy_version="v2-amd-2026-0808-01",
        platform="抖音",
        media_format="视频",
        production_conditions="Gate D 隔离零模型验证",
    )


def _select(
    repository: PostgresContentRepository,
    account_code: str,
) -> BrandContext:
    return repository.select_brand_context_for_task(
        _scope(account_code),
        _context(account_code),
        "今天本地穿衣怎么回应",
        "local_response",
        (),
    )


def _local_claims(context: BrandContext) -> tuple[str, ...]:
    if context.context_packet is None:
        raise AssertionError("the formal consumer returned no context packet")
    return tuple(
        segment.claim_key
        for segment in context.context_packet.segments
        if segment.claim_key is not None
        and (segment.claim_key.startswith("RK-") or segment.claim_key.startswith("SK-"))
    )


def _assert_scope_consumption(
    repository: PostgresContentRepository,
    app_database_url: str,
) -> dict[str, object]:
    observed: dict[str, list[str]] = {}
    frozen_tasks: list[dict[str, object]] = []
    for account_code, allowed_prefixes in _ALLOWED_LOCAL_PREFIXES.items():
        selected = _select(repository, account_code)
        claims = _local_claims(selected)
        if account_code == "H01":
            if claims or selected.context_packet is None or len(selected.context_packet.segments) != 4:
                raise AssertionError("headquarters did not consume exactly the four global entries")
        elif not claims:
            raise AssertionError(f"{account_code} consumed no current organization knowledge")
        if any(not claim.startswith(allowed_prefixes) for claim in claims):
            raise AssertionError(f"{account_code} consumed a sibling organization claim")
        if "RK-EC-08" in claims:
            raise AssertionError("the expired RK-EC-08 sample entered a new task")
        observed[account_code] = list(claims)
        if selected.context_packet is None or selected.task_context_as_of is None:
            raise AssertionError("the formal task context is incomplete")
        snapshot: dict[str, object] = {
            "task_context_as_of": selected.task_context_as_of,
            "brand_context_packet": brand_context_packet_document(
                selected.context_packet,
                include_text=True,
            ),
        }
        task_id, run_id, _ = repository.create_task_and_running_run(
            _scope(account_code),
            "Gate D 组织资料正式任务快照验证",
            "local_response",
            None,
            "gate-d-zero-model-stub",
            (),
            selected,
            (),
            "douyin_video",
            "video",
            direction_for("douyin_video"),
            None,
            "Gate D 隔离零模型验证",
            snapshot=snapshot,
        )
        repository.fail_run(
            _scope(account_code),
            task_id,
            run_id,
            "Gate D zero-provider snapshot proof complete",
        )
        with psycopg.connect(app_database_url) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
            cursor.execute(
                "SELECT content_context_snapshot FROM business_tasks WHERE tenant_id=%s AND id=%s",
                (TENANT_ID, task_id),
            )
            row = cursor.fetchone()
        if row is None or not isinstance(row[0], dict):
            raise AssertionError("the formal task did not freeze a readable snapshot")
        frozen_packet = row[0].get("brand_context_packet")
        if not isinstance(frozen_packet, dict):
            raise AssertionError("the formal task snapshot lost its projection packet")
        frozen_segments = frozen_packet.get("segments")
        if not isinstance(frozen_segments, list) or not frozen_segments:
            raise AssertionError("the formal task snapshot contains no projection item")
        frozen_tasks.append(
            {
                "account_code": account_code,
                "task_id": str(task_id),
                "run_id": str(run_id),
                "run_status": "failed_after_snapshot_proof",
                "provider_requests": 0,
                "projection_item_ids": [
                    str(segment["segment_id"])
                    for segment in frozen_segments
                    if isinstance(segment, dict) and segment.get("segment_id")
                ],
                "claim_keys": [
                    str(segment["claim_key"])
                    for segment in frozen_segments
                    if isinstance(segment, dict) and segment.get("claim_key")
                ],
            }
        )
    return {
        "headquarters_global_positive": True,
        "east_positive": bool(observed["R01"]),
        "sichuan_positive": bool(observed["R02"]),
        "hangzhou_positive": bool(observed["S01"]),
        "huzhou_positive": bool(observed["S03"]),
        "chengdu_positive": bool(observed["S04"]),
        "sibling_scope_leaks": 0,
        "expired_rk_ec_08_consumptions": 0,
        "observed_claims": observed,
        "formal_task_snapshots": frozen_tasks,
    }


def _assert_judgments(repository: PostgresContentRepository) -> dict[str, object]:
    scope = _scope("H03")
    results: list[dict[str, str]] = []
    for sku in ("DIYU-CSPU-001", "DIYU-CSPU-006", "DIYU-CSPU-008", "DIYU-CSPU-013"):
        products = repository.load_product_facts(scope, sku)
        if len(products) != 1:
            raise AssertionError(f"{sku} did not resolve to exactly one formal ProductFact")
        product = products[0]
        if not (
            product.judgment_ref
            and product.judgment_version
            and product.judgment_digest
            and product.judgment_applicability_conditions
        ):
            raise AssertionError(f"{sku} did not carry its frozen J judgment")
        for content_product in ("dressing_decision", "product_truth"):
            basis = build_product_decision_basis_v2(
                primary_product=content_product,
                products=products,
            )
            if basis is None:
                raise AssertionError(f"{sku} did not produce the {content_product} decision basis")
            document = product_value_contract_document(basis)
            if (
                document.get("judgment_ref") != product.judgment_ref
                or document.get("judgment_digest") != product.judgment_digest
            ):
                raise AssertionError(f"{sku} lost its J reference in {content_product}")
        results.append(
            {
                "sku": sku,
                "judgment_ref": product.judgment_ref,
                "judgment_version": product.judgment_version,
                "judgment_digest": product.judgment_digest,
            }
        )
    return {"judgments": results, "p1_consumers": 4, "p2_consumers": 4}


def _person_qualification(context: BrandContext) -> BrandRelevanceQualificationV1:
    matches = tuple(
        qualification
        for qualification in context.relevance_qualifications
        if qualification.path_family == "organization_people"
    )
    if len(matches) != 1 or matches[0].authorization is None:
        raise AssertionError("person content did not resolve one formal authorization")
    return matches[0]


def _authorization_snapshot(context: BrandContext, authorization: AuthorizationContractV1) -> dict[str, object]:
    if context.task_context_as_of is None:
        raise AssertionError("formal context omitted the server-frozen task time")
    return {
        "task_context_as_of": context.task_context_as_of,
        "version_authorization": "deterministic-dual-track-v1",
        "creative_kernel_v2": {},
        "narrative_frame": {},
        "visible_provenance": {},
        "publication_contract": {
            "brand_relevance_evidence": {
                "authorization": authorization_contract_document(authorization),
            }
        },
    }


def _create_run(
    repository: PostgresContentRepository,
    account_code: str,
    context: BrandContext,
    snapshot: dict[str, object],
    *,
    parent_version_id: UUID | None = None,
) -> tuple[UUID, UUID]:
    task_id, run_id, _ = repository.create_task_and_running_run(
        _scope(account_code),
        "人物授权单次核销正式消费者验证",
        "local_response",
        parent_version_id,
        "gate-d-zero-model-stub",
        (),
        context,
        (),
        "douyin_video",
        "video",
        direction_for("douyin_video"),
        None,
        "Gate D 隔离零模型验证",
        snapshot=snapshot,
    )
    return task_id, run_id


def _complete(
    repository: PostgresContentRepository,
    account_code: str,
    task_id: UUID,
    run_id: UUID,
    suffix: str,
) -> UUID:
    result = repository.complete_run_with_version(
        _scope(account_code),
        task_id,
        run_id,
        f"人物授权验证 {suffix}",
        f"这是一条只用于隔离库核销机制验证的确定性内容版本 {suffix}。",
        "gate-d-zero-model-stub",
        0,
        0,
        None,
        {},
        (),
    )
    return UUID(str(result["version_id"]))


def _assert_single_use_authorizations(
    repository: PostgresContentRepository,
    app_database_url: str,
) -> dict[str, object]:
    evidence: list[dict[str, object]] = []
    for account_code, subject_ref in (("S02", "PS-S02-05"), ("S04", "PS-S04-03")):
        context = _select(repository, account_code)
        qualification = _person_qualification(context)
        authorization = cast(AuthorizationContractV1, qualification.authorization)
        if authorization.subject_ref != subject_ref:
            raise AssertionError(f"{account_code} resolved the wrong person authorization")
        snapshot = _authorization_snapshot(context, authorization)

        failed_task, failed_run = _create_run(repository, account_code, context, snapshot)
        repository.fail_run(_scope(account_code), failed_task, failed_run, "Gate D controlled failure")

        first_task, first_run = _create_run(repository, account_code, context, snapshot)
        first_version = _complete(repository, account_code, first_task, first_run, "V1")
        revision_task, revision_run = _create_run(
            repository,
            account_code,
            context,
            snapshot,
            parent_version_id=first_version,
        )
        _complete(repository, account_code, revision_task, revision_run, "V2")
        try:
            _create_run(repository, account_code, context, snapshot)
        except DomainError:
            independent_rejected = True
        else:
            raise AssertionError("a consumed single-use authorization opened an independent task")

        with psycopg.connect(app_database_url) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
            cursor.execute(
                "SELECT event_type,count(*) FROM content_authorization_events "
                "WHERE tenant_id=%s AND brand_id=%s AND authorization_id=%s "
                "GROUP BY event_type ORDER BY event_type",
                (TENANT_ID, BRAND_ID, UUID(authorization.authorization_id)),
            )
            event_counts = {str(row[0]): int(row[1]) for row in cursor.fetchall()}
        if event_counts != {"consumed": 1, "released": 1, "reserved": 2}:
            raise AssertionError(f"unexpected authorization events for {subject_ref}: {event_counts}")
        evidence.append(
            {
                "subject_ref": subject_ref,
                "authorization_id": authorization.authorization_id,
                "failed_run_released": True,
                "v1_consumed_once": True,
                "same_lineage_v2_without_second_consumption": True,
                "independent_task_rejected": independent_rejected,
                "event_counts": event_counts,
            }
        )
    return {"authorization_fixtures": evidence}


def verify(app_database_url: str) -> dict[str, object]:
    repository = PostgresContentRepository(app_database_url)
    return {
        "scope_consumption": _assert_scope_consumption(repository, app_database_url),
        "judgment_consumption": _assert_judgments(repository),
        "authorization_consumption": _assert_single_use_authorizations(repository, app_database_url),
        "provider_requests": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-database-url", required=True)
    parser.add_argument("--evidence-output", type=Path, required=True)
    arguments = parser.parse_args()
    evidence = verify(arguments.app_database_url)
    arguments.evidence_output.parent.mkdir(parents=True, exist_ok=True)
    arguments.evidence_output.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"provider_requests": 0, "status": "passed"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
