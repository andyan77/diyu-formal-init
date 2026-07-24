from __future__ import annotations

import ast
import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_GOVERNANCE = _PROJECT_ROOT / "首批领域数据库知识数据" / "第五批：评测与导入包" / "12-系统资产运行治理-v1.json"
_GOVERNANCE_SCHEMA = "diyu_system_asset_governance_v1"
_CANDIDATE_SCHEMA_VERSIONS = frozenset({"diyu_global_asset_v0.2"})
_LIFECYCLES = frozenset({"review_candidate", "active", "deprecated"})


@dataclass(frozen=True)
class GovernedAsset:
    asset_id: str
    consumer: str
    applicability: str
    lifecycle: str
    valid_until: date | None
    superseded_by: str | None


@dataclass(frozen=True)
class FixtureBinding:
    fixture_id: str
    boundary: str
    test_node: str


@dataclass(frozen=True)
class AssetGovernance:
    candidate_source: Path
    candidate_sha256: str
    assets: tuple[GovernedAsset, ...]
    fixture_bindings: tuple[FixtureBinding, ...]


def import_system_asset_catalog(governance_path: Path = _GOVERNANCE) -> int:
    database_url = os.environ.get("DIYU_MIGRATOR_DATABASE_URL")
    if not database_url:
        raise RuntimeError("DIYU_MIGRATOR_DATABASE_URL is required to import system assets")
    governance, records = validate_system_asset_governance(governance_path)
    governed_assets = {asset.asset_id: asset for asset in governance.assets}
    active_assets = tuple(asset for asset in governance.assets if asset.lifecycle == "active")
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        for record in records:
            asset_id = str(record["asset_id"])
            governed = governed_assets.get(asset_id)
            cursor.execute(
                """
                INSERT INTO system_domain_assets
                    (asset_id, asset_type, schema_version, source_batch, display_name, structured_body,
                     supported_products, applicability, status, valid_until, superseded_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (asset_id) DO UPDATE SET
                    asset_type = EXCLUDED.asset_type,
                    schema_version = EXCLUDED.schema_version,
                    source_batch = EXCLUDED.source_batch,
                    display_name = EXCLUDED.display_name,
                    structured_body = EXCLUDED.structured_body,
                    supported_products = EXCLUDED.supported_products,
                    applicability = EXCLUDED.applicability,
                    status = EXCLUDED.status,
                    valid_until = EXCLUDED.valid_until,
                    superseded_by = EXCLUDED.superseded_by
                """,
                (
                    asset_id,
                    str(record["asset_type"]),
                    str(record["schema_version"]),
                    str(record["source_batch"]),
                    str(record.get("title") or record.get("name") or asset_id),
                    Jsonb(record),
                    Jsonb(record.get("supported_products") or record.get("applies_to") or []),
                    Jsonb(_boundaries(record)),
                    governed.lifecycle if governed is not None else "review_candidate",
                    governed.valid_until if governed is not None else None,
                    None,
                ),
            )
        for asset in governance.assets:
            cursor.execute(
                """
                UPDATE system_domain_assets
                SET status = %s, valid_until = %s, superseded_by = %s
                WHERE asset_id = %s
                """,
                (asset.lifecycle, asset.valid_until, asset.superseded_by, asset.asset_id),
            )
        active_ids = [asset.asset_id for asset in active_assets]
        cursor.execute("DELETE FROM system_asset_activations WHERE NOT asset_id = ANY(%s)", (active_ids,))
        for asset in active_assets:
            cursor.execute(
                """
                INSERT INTO system_asset_activations (asset_id, consumer, applicability)
                VALUES (%s, %s, %s)
                ON CONFLICT (asset_id) DO UPDATE SET consumer = EXCLUDED.consumer, applicability = EXCLUDED.applicability
                """,
                (asset.asset_id, asset.consumer, asset.applicability),
            )
    return len(records)


def validate_system_asset_governance(
    governance_path: Path = _GOVERNANCE,
    project_root: Path = _PROJECT_ROOT,
) -> tuple[AssetGovernance, list[dict[str, Any]]]:
    governance = _load_governance(governance_path, project_root)
    source = _resolve_project_path(project_root, governance.candidate_source)
    if _sha256(source) != governance.candidate_sha256:
        raise RuntimeError("system asset candidate source SHA-256 does not match governance")
    records = _load_records(source)
    asset_ids = _validate_candidate_records(records)
    _validate_governed_assets(governance.assets, asset_ids)
    _validate_fixture_bindings(governance.fixture_bindings, project_root)
    return governance, records


def _load_governance(governance_path: Path, project_root: Path) -> AssetGovernance:
    try:
        raw: object = json.loads(governance_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("system asset governance file is unreadable") from error
    root = _mapping(raw, "system asset governance")
    if _required_string(root, "schema_version") != _GOVERNANCE_SCHEMA:
        raise RuntimeError("system asset governance schema is unknown")
    candidate = _mapping(root.get("candidate_source"), "candidate_source")
    assets = _sequence(root.get("assets"), "assets")
    bindings = _sequence(root.get("fixture_bindings"), "fixture_bindings")
    return AssetGovernance(
        candidate_source=Path(_required_string(candidate, "path")),
        candidate_sha256=_required_string(candidate, "sha256"),
        assets=tuple(_governed_asset(value) for value in assets),
        fixture_bindings=tuple(_fixture_binding(value) for value in bindings),
    )


def _governed_asset(value: object) -> GovernedAsset:
    raw = _mapping(value, "governed asset")
    lifecycle = _required_string(raw, "lifecycle")
    if lifecycle not in _LIFECYCLES:
        raise RuntimeError("system asset governance lifecycle is invalid")
    valid_until = _optional_date(raw.get("valid_until"))
    superseded_by = _optional_string(raw.get("superseded_by"), "superseded_by")
    return GovernedAsset(
        asset_id=_required_string(raw, "asset_id"),
        consumer=_required_string(raw, "consumer"),
        applicability=_required_string(raw, "applicability"),
        lifecycle=lifecycle,
        valid_until=valid_until,
        superseded_by=superseded_by,
    )


def _fixture_binding(value: object) -> FixtureBinding:
    raw = _mapping(value, "fixture binding")
    return FixtureBinding(
        fixture_id=_required_string(raw, "fixture_id"),
        boundary=_required_string(raw, "boundary"),
        test_node=_required_string(raw, "test_node"),
    )


def _load_records(source: Path) -> list[dict[str, Any]]:
    try:
        lines = source.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise RuntimeError("system asset candidate source is unreadable") from error
    records: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            value: object = json.loads(line)
        except json.JSONDecodeError as error:
            raise RuntimeError("system asset candidate source contains invalid JSONL") from error
        record = _mapping(value, "candidate asset")
        records.append(dict(record))
    return records


def _validate_candidate_records(records: list[dict[str, Any]]) -> set[str]:
    asset_ids: set[str] = set()
    for record in records:
        asset_id = _required_string(record, "asset_id")
        if asset_id in asset_ids:
            raise RuntimeError("system asset candidate source has duplicate asset_id")
        asset_ids.add(asset_id)
        _required_string(record, "asset_type")
        schema_version = _required_string(record, "schema_version")
        if schema_version not in _CANDIDATE_SCHEMA_VERSIONS:
            raise RuntimeError("system asset candidate schema is unknown")
        _required_string(record, "source_batch")
    if not asset_ids:
        raise RuntimeError("system asset candidate source is empty")
    return asset_ids


def _validate_governed_assets(assets: tuple[GovernedAsset, ...], asset_ids: set[str]) -> None:
    governed_ids: set[str] = set()
    for asset in assets:
        if asset.asset_id in governed_ids:
            raise RuntimeError("system asset governance has duplicate asset_id")
        if asset.asset_id not in asset_ids:
            raise RuntimeError("system asset governance references an unknown asset")
        governed_ids.add(asset.asset_id)
        if asset.superseded_by is not None and asset.superseded_by not in asset_ids:
            raise RuntimeError("system asset governance superseded_by references an unknown asset")
        if asset.superseded_by == asset.asset_id:
            raise RuntimeError("system asset cannot supersede itself")
        if asset.lifecycle == "active":
            if asset.valid_until is not None and asset.valid_until < date.today():
                raise RuntimeError("an expired system asset cannot remain active")
            if asset.superseded_by is not None:
                raise RuntimeError("a superseded system asset cannot remain active")


def _validate_fixture_bindings(bindings: tuple[FixtureBinding, ...], project_root: Path) -> None:
    fixture_ids: set[str] = set()
    for binding in bindings:
        if binding.fixture_id in fixture_ids:
            raise RuntimeError("system asset governance has duplicate fixture binding")
        fixture_ids.add(binding.fixture_id)
        relative_file, separator, test_name = binding.test_node.partition("::")
        if not separator or not relative_file or not test_name:
            raise RuntimeError("fixture binding test node is invalid")
        test_path = _resolve_project_path(project_root, Path(relative_file))
        try:
            module = ast.parse(test_path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError) as error:
            raise RuntimeError("fixture binding test module is unreadable") from error
        if test_name not in {node.name for node in module.body if isinstance(node, ast.FunctionDef)}:
            raise RuntimeError("fixture binding test function does not exist")


def _resolve_project_path(project_root: Path, relative_path: Path) -> Path:
    root = project_root.resolve()
    path = (root / relative_path).resolve()
    if root not in path.parents and path != root:
        raise RuntimeError("system asset governance path escapes the project root")
    return path


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise RuntimeError("system asset candidate source is unreadable") from error


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise RuntimeError(f"{label} must be an object")
    return value


def _sequence(value: object, label: str) -> tuple[object, ...]:
    if not isinstance(value, list):
        raise RuntimeError(f"{label} must be an array")
    return tuple(value)


def _required_string(value: Mapping[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise RuntimeError(f"{key} is required")
    return item


def _optional_string(value: object, key: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"{key} must be a non-empty string or null")
    return value


def _optional_date(value: object) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise RuntimeError("valid_until must be an ISO date or null")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise RuntimeError("valid_until must be an ISO date or null") from error


def _boundaries(record: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "when",
        "not_when",
        "tradeoffs",
        "anti_misuse",
        "applicability",
        "use_when",
        "avoid_when",
    )
    return {key: record[key] for key in keys if key in record}


if __name__ == "__main__":
    import_system_asset_catalog()
