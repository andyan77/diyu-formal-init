from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class TrustedScope:
    tenant_id: UUID
    user_id: UUID
    brand_id: UUID
    account_id: UUID


@dataclass(frozen=True)
class BrandContext:
    brand_name: str
    positioning: str
    decision_order: str
    tone: str
    account_name: str
    operator_name: str
    organization_name: str
    content_role_name: str
    content_role_boundary: str
    audience_description: str
    strategy_version: str
    platform: str
    media_format: str
    production_conditions: str


@dataclass(frozen=True)
class ActiveAsset:
    asset_id: str
    schema_version: str
    asset_type: str
    display_name: str
    body: str


@dataclass(frozen=True)
class P1SemanticContract:
    choice: str
    boundary: str
    next_action: str


@dataclass(frozen=True)
class P1ProductionBundle:
    natural_guide: str
    spoken_lines: str
    visual_actions: str
    subtitles: str
    sound_and_production: str


@dataclass(frozen=True)
class GenerationInput:
    run_id: UUID
    task_id: UUID
    weak_seed: str
    revision_instruction: str | None
    brand: BrandContext
    active_domain_assets: tuple[ActiveAsset, ...] = ()
    prior_saved_body: str | None = None


@dataclass(frozen=True)
class GeneratedArtifact:
    outline: str
    body: str
    model: str
    latency_ms: int
    retry_count: int
    provider_usage: dict[str, int] | None
    semantic_contract: P1SemanticContract
    production: P1ProductionBundle


@dataclass(frozen=True)
class DisplayScope:
    """Trusted internal merchandising scope; deliberately has no publishing account."""

    tenant_id: UUID
    user_id: UUID
    brand_id: UUID
    organization_id: UUID


@dataclass(frozen=True)
class DisplayContext:
    brand_name: str
    organization_name: str
    operator_name: str
    policy_version: str
    policy: str
    store_name: str
    store_profile_version: str
    rail_profile: str
    products: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class DisplayGenerationInput:
    run_id: UUID
    task_id: UUID
    inventory: tuple[tuple[str, int], ...]
    context: DisplayContext
    active_domain_assets: tuple[ActiveAsset, ...]
    feedback: str | None = None
    prior_plan: dict[str, object] | None = None


@dataclass(frozen=True)
class GeneratedDisplayArtifact:
    body: str
    plan: dict[str, object]
    model: str
    latency_ms: int
    retry_count: int
    provider_usage: dict[str, int] | None
