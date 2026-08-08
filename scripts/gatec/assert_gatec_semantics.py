#!/usr/bin/env python3
"""Fail-closed structural assertions for Gate C's durable semantics."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from src.shared.publication_scope import (  # noqa: E402
    PUBLICATION_ITEM_SCOPE_V2_CONTRACT,
    PUBLICATION_PROJECTION_V2_CONTRACT,
)

_MIGRATION = "alembic/versions/20260818_45_brand_scope_authorization.py"
_NEW_TABLES = (
    "brand_feedback_observations",
    "content_authorizations",
    "content_authorization_reservations",
    "content_authorization_events",
    "brand_relevance_qualifications",
    "brand_publication_claim_conflicts",
)
_REQUIRED_TESTS = (
    "test_projection_v2_digest_is_deterministic_and_scope_sensitive",
    "test_lifecycle_uses_closed_open_server_time_interval",
    "test_headquarters_product_fact_wins_without_local_pollution",
    "test_same_level_same_claim_conflict_fails_only_when_consumed",
    "test_institutional_local_trust_does_not_require_person_authorization",
    "test_people_paths_require_a_matching_full_authorization_contract",
    "test_revision_replays_frozen_v2_scope_version_and_server_time",
    "test_root_logical_account_drives_headquarters_region_and_store_scope",
    "test_structured_conflict_records_needs_review_and_blocks_confirmation",
    "test_feedback_observation_is_append_only_and_cannot_become_formal_source",
    "test_single_use_authorization_is_consumed_once_per_task_lineage",
    "test_two_users_share_logical_account_but_not_each_others_tasks",
    "test_historical_upgrade_validates_organization_parent_fk_as_non_bypass_owner",
)


def _source(path: str) -> str:
    return (_ROOT / path).read_text(encoding="utf-8")


def _require(source: str, markers: tuple[str, ...], label: str) -> None:
    missing = [marker for marker in markers if marker not in source]
    if missing:
        raise SystemExit(f"Gate C semantics FAIL ({label}): missing {missing}")


def _downgrade_raises(source: str) -> bool:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "downgrade":
            return any(isinstance(child, ast.Raise) for child in ast.walk(node))
    return False


def main() -> None:
    if PUBLICATION_PROJECTION_V2_CONTRACT != "brand-publication-projection-v2":
        raise SystemExit("Gate C semantics FAIL: projection V2 contract missing")
    if PUBLICATION_ITEM_SCOPE_V2_CONTRACT != "publication-item-scope-v2":
        raise SystemExit("Gate C semantics FAIL: item scope V2 contract missing")

    migration = _source(_MIGRATION)
    repository = _source("src/infrastructure/postgres_repository.py")
    queries = _source("src/infrastructure/gatec_queries.py")
    publication_scope = _source("src/shared/publication_scope.py")
    publication = _source("src/shared/brand_publication.py")
    service = _source("src/brain/content_service.py")
    semantic_tests = _source("tests/test_gatec_semantics.py")
    postgres_tests = _source("tests/test_gatec_postgres.py")
    migration_tests = _source("tests/test_ux03_gate_d.py")

    _require(
        migration,
        (
            'revision = "20260818_45"',
            'down_revision = "20260817_44"',
            "scope_organization_ids uuid[]",
            "effective_at timestamptz",
            "expires_at timestamptz",
            "authority_class text",
            "claim_key text",
            "scope_contract_version text",
            "feedback observation cannot be a formal projection source",
            "publication projection has claims needing review",
        ),
        "migration contracts",
    )
    if not _downgrade_raises(migration):
        raise SystemExit("Gate C semantics FAIL: downgrade is not fail-closed")
    for table in _NEW_TABLES:
        _require(
            migration,
            (
                f"CREATE TABLE {table}",
                f'_tenant_rls("{table}"',
            ),
            f"RLS {table}",
        )

    _require(
        repository,
        (
            "PROJECTION_TASK_CONTEXT_SQL",
            "publication_projection_v2_digest(projection_v2_items)",
            'visibility_scope=str(row["visibility_scope"])',
            'task_context_as_of=self._time(rows[0]["task_context_as_of"])',
            "resolve_claim_authority(",
            "task_lineage_id=task_lineage_id",
        ),
        "formal read and authorization path",
    )
    _require(
        queries,
        (
            "COALESCE(\n       target_account.carrier_of_account_id",
            "root_account.control_organization_id",
            "item.visibility_scope = 'brand_all'",
            "item.visibility_scope = 'headquarters'",
            "item.visibility_scope = 'organizations'",
            "item.effective_at <= transaction_timestamp()",
            "transaction_timestamp() < item.expires_at",
            "organization_is_same_or_descendant(",
        ),
        "formal task SQL",
    )
    if 'visibility_scope="brand_all"' in repository:
        raise SystemExit("Gate C semantics FAIL: BrandContextSegment still rewrites database scope")
    _require(
        publication_scope,
        (
            "publication_projection_v2_digest",
            "publication_item_is_effective",
            "resolve_claim_authority",
            "AuthorizationContractV1",
        ),
        "typed contracts",
    )
    _require(
        publication,
        (
            'segment.scope_contract_version == "publication-item-scope-v2"',
            '"scope_organization_ids"',
            '"authority_class"',
            '"claim_key"',
        ),
        "frozen packet",
    )
    _require(service, ('snapshot.get("task_context_as_of")', "frozen_task_context_as_of"), "revision freeze")
    test_source = "\n".join((semantic_tests, postgres_tests, migration_tests))
    _require(test_source, _REQUIRED_TESTS, "Gate C tests")
    print(
        "GATEC_SEMANTICS_OK scope_fields=7 rls_tables=6 conflict=structured "
        "authorization=lineage observation=formal_source_blocked"
    )


if __name__ == "__main__":
    main()
