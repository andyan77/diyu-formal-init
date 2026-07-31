from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import cast

from src.shared.errors import DomainError, GenerationFailed

DM01_RULE_BUNDLE_VERSION = "dm01-rule-bundle-v1"
DM01_RULE_SCHEMA_VERSION = "diyu_global_asset_v0.2"

_RULE_DIGESTS: dict[str, tuple[str, str]] = {
    "G-TASK-003": ("inventory_scope", "433876f42ec49ff64c58d7592e901b10bfc3c1b8d1bb8015dd97fabde0fef6a0"),
    "G-TASK-004": ("reference_plan_boundary", "2c26e657f4b242e53a1c44e84f3bbd2ec1034583dc6e544ab0ab0fb74b3f23f9"),
    "G-FIXTURE-001": ("double_rail_structure", "44972bca3f7832e305dde6844b7bb5537a7c70938bd7c159b038f2ffbb862ee7"),
    "G-FIXTURE-002": ("fixed_front_points", "16582beba89f21d2ef5bbde63fd0907c474fdbafa35b4a37a543a14f438ed5ff"),
    "G-GROUP-001": ("upper_lower_grouping", "b3101afe2f204dd78d1a38f6290e1e2e64d4aa6f492c7c229271bf7d0066a1b6"),
    "G-FOCUS-001": ("focus_and_response", "f5eacf756e3748264b55935435f49c7ddc167e5893b2c6eba1d6dc8084786412"),
    "G-DENSITY-002": ("comfortable_density", "fd92f6994018b0b14805ea93d19122c42d35e0c152d414a76b78f1180f8e0533"),
    "G-SUB-001": ("same_product_substitution", "7c16049ead9807d304d64fd92ea4b8461ca942d95ebf74105ab6e55746aa5486"),
    "G-SUB-003": ("local_density_reduction", "edff654428d71d4118dab3865e2485b7ff8b6f8c42876d204ddb5ab3e1298bd7"),
    "G-REV-003": ("partial_revision", "fd05349f0dc40187142591f2069395be1ffcbc5acfe4a87dd6cab61268019140"),
    "GM-LAYOUT-001": ("layout_compilation", "8a15158ab7dc563cee47e71f0739d9a2e106e3514271e931152f6654313456fa"),
    "GM-EXEC-001": ("execution_projection", "ba27b4d46f5e3a6118a4b8e2c15ac5c2d0c78d4e4260ea60273f11c076ebcb4a"),
    "GM-REVISE-001": ("revision_compilation", "720d9eafee27b556abff902f2a4ccb935b3b6a481025bae2e823ffcb265bc880"),
}
_REVISION_ONLY = frozenset({"G-REV-003", "GM-REVISE-001"})


def canonical_json_digest(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DM01RuleAssetV1:
    asset_id: str
    schema_version: str
    body_digest: str
    invariant_id: str

    def document(self) -> dict[str, str]:
        return {
            "asset_id": self.asset_id,
            "schema_version": self.schema_version,
            "body_digest": self.body_digest,
            "invariant_id": self.invariant_id,
        }


@dataclass(frozen=True)
class DM01RuleBundleV1:
    bundle_version: str
    generation_assets: tuple[DM01RuleAssetV1, ...]
    revision_assets: tuple[DM01RuleAssetV1, ...]
    bundle_digest: str

    def document(self) -> dict[str, object]:
        return {
            "bundle_version": self.bundle_version,
            "generation_assets": [asset.document() for asset in self.generation_assets],
            "revision_assets": [asset.document() for asset in self.revision_assets],
            "bundle_digest": self.bundle_digest,
        }


def build_dm01_rule_bundle(rows: tuple[dict[str, object], ...]) -> DM01RuleBundleV1:
    resolved: list[DM01RuleAssetV1] = []
    for row in rows:
        asset_id = str(row.get("asset_id", ""))
        expected = _RULE_DIGESTS.get(asset_id)
        if expected is None:
            continue
        schema_version = str(row.get("schema_version", ""))
        body = row.get("structured_body")
        if schema_version != DM01_RULE_SCHEMA_VERSION or not isinstance(body, dict):
            raise DomainError("纯文字陈列规则版本不完整，请联系笛语运维。")
        invariant_id, expected_digest = expected
        body_digest = canonical_json_digest(body)
        if body_digest != expected_digest:
            raise DomainError("纯文字陈列规则版本不完整，请联系笛语运维。")
        resolved.append(DM01RuleAssetV1(asset_id, schema_version, body_digest, invariant_id))
    by_id = {asset.asset_id: asset for asset in resolved}
    if set(by_id) != set(_RULE_DIGESTS):
        raise DomainError("纯文字陈列规则暂不完整，请稍后再试。")
    ordered = tuple(by_id[asset_id] for asset_id in _RULE_DIGESTS)
    generation = tuple(asset for asset in ordered if asset.asset_id not in _REVISION_ONLY)
    document = {
        "bundle_version": DM01_RULE_BUNDLE_VERSION,
        "generation_assets": [asset.document() for asset in generation],
        "revision_assets": [asset.document() for asset in ordered],
    }
    return DM01RuleBundleV1(
        DM01_RULE_BUNDLE_VERSION,
        generation,
        ordered,
        canonical_json_digest(document),
    )


def dm01_rule_bundle_from_document(value: object) -> DM01RuleBundleV1:
    if not isinstance(value, dict):
        raise DomainError("历史方案缺少可重放的正式规则快照。")
    raw = cast(dict[str, object], value)
    generation = _assets_from_document(raw.get("generation_assets"))
    revision = _assets_from_document(raw.get("revision_assets"))
    bundle = DM01RuleBundleV1(
        str(raw.get("bundle_version", "")),
        generation,
        revision,
        str(raw.get("bundle_digest", "")),
    )
    assert_dm01_rule_bundle(bundle, revision=True, error_type=DomainError)
    return bundle


def assert_dm01_rule_bundle(
    bundle: DM01RuleBundleV1 | None,
    *,
    revision: bool,
    error_type: type[DomainError] | type[GenerationFailed] = GenerationFailed,
) -> None:
    if bundle is None or bundle.bundle_version != DM01_RULE_BUNDLE_VERSION:
        raise error_type("本次方案缺少可验证的正式陈列规则束。")
    expected_ids = tuple(_RULE_DIGESTS) if revision else tuple(
        asset_id for asset_id in _RULE_DIGESTS if asset_id not in _REVISION_ONLY
    )
    selected = bundle.revision_assets if revision else bundle.generation_assets
    if tuple(asset.asset_id for asset in selected) != expected_ids:
        raise error_type("本次方案的正式陈列规则束不完整。")
    for asset in selected:
        expected = _RULE_DIGESTS.get(asset.asset_id)
        if (
            expected is None
            or asset.schema_version != DM01_RULE_SCHEMA_VERSION
            or (asset.invariant_id, asset.body_digest) != expected
        ):
            raise error_type("本次方案的正式陈列规则版本不匹配。")
    document = {
        "bundle_version": bundle.bundle_version,
        "generation_assets": [asset.document() for asset in bundle.generation_assets],
        "revision_assets": [asset.document() for asset in bundle.revision_assets],
    }
    if canonical_json_digest(document) != bundle.bundle_digest:
        raise error_type("本次方案的正式陈列规则摘要不一致。")


def _assets_from_document(value: object) -> tuple[DM01RuleAssetV1, ...]:
    if not isinstance(value, list):
        raise DomainError("历史方案规则清单无效。")
    assets: list[DM01RuleAssetV1] = []
    for raw in value:
        if not isinstance(raw, dict):
            raise DomainError("历史方案规则条目无效。")
        item = cast(dict[str, object], raw)
        assets.append(
            DM01RuleAssetV1(
                str(item.get("asset_id", "")),
                str(item.get("schema_version", "")),
                str(item.get("body_digest", "")),
                str(item.get("invariant_id", "")),
            )
        )
    return tuple(assets)
