from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias
from uuid import UUID

ContentProduct: TypeAlias = Literal[
    "dressing_decision",
    "product_truth",
    "brand_life_narrative",
    "local_response",
    "visual_styling_story",
]

MediaFormat: TypeAlias = Literal["video", "graphic"]
ContentTarget: TypeAlias = Literal[
    "douyin_video",
    "xiaohongshu_video",
    "xiaohongshu_graphic",
    "wechat_channels_video",
]


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
class PlatformDirection:
    version: str
    platform: str
    media_format: MediaFormat
    direction: str


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
class P2SemanticContract:
    product_insight: str
    tradeoff_or_limit: str
    validity_condition: str


@dataclass(frozen=True)
class P3SemanticContract:
    persona_observation: str
    audience_return: str
    brand_account_link: str


@dataclass(frozen=True)
class P4SemanticContract:
    local_reality_or_signal: str
    legitimate_account_response: str
    public_relationship_return: str


@dataclass(frozen=True)
class P5SemanticContract:
    real_product_anchor: str
    visible_styling_proposition: str
    visual_dependency: str


ContentSemanticContract: TypeAlias = (
    P1SemanticContract
    | P2SemanticContract
    | P3SemanticContract
    | P4SemanticContract
    | P5SemanticContract
)


@dataclass(frozen=True)
class P1ProductionBundle:
    natural_guide: str
    spoken_lines: str
    visual_actions: str
    subtitles: str
    sound_and_production: str


@dataclass(frozen=True)
class VideoProductionBundle(P1ProductionBundle):
    """The complete, visible viewing chain for the current video target."""

    cover_or_first_frame: str
    viewing_flow: str
    natural_duration: str
    release_caption_and_interaction: str


@dataclass(frozen=True)
class GraphicProductionBundle:
    """The complete, visible reading chain for the current graphic target."""

    natural_guide: str
    hero_image: str
    image_sequence: str
    full_body: str
    layout_and_production: str
    release_caption_and_interaction: str


ContentProductionBundle: TypeAlias = VideoProductionBundle | GraphicProductionBundle


@dataclass(frozen=True)
class ProductFact:
    sku: str
    facts: dict[str, object]


@dataclass(frozen=True)
class RecompileSource:
    task_id: UUID
    weak_seed: str
    primary_product: ContentProduct
    products: tuple[ProductFact, ...]
    body: str
    source_description: str
    source_target: ContentTarget


@dataclass(frozen=True)
class RoutingInput:
    weak_seed: str
    brand: BrandContext
    products: tuple[ProductFact, ...]
    prior_saved_body: str | None = None


@dataclass(frozen=True)
class GenerationInput:
    run_id: UUID
    task_id: UUID
    weak_seed: str
    primary_product: ContentProduct
    revision_instruction: str | None
    brand: BrandContext
    target: ContentTarget
    media_format: MediaFormat
    platform_direction: PlatformDirection
    active_domain_assets: tuple[ActiveAsset, ...] = ()
    products: tuple[ProductFact, ...] = ()
    prior_saved_body: str | None = None
    source_version_description: str | None = None


@dataclass(frozen=True)
class FactRepairReceipt:
    """Auditable fact-boundary repair evidence, never model reasoning."""

    field: str
    fragments: tuple[str, ...]


@dataclass(frozen=True)
class GeneratedArtifact:
    outline: str
    body: str
    model: str
    latency_ms: int
    retry_count: int
    provider_usage: dict[str, int] | None
    primary_product: ContentProduct
    semantic_contract: ContentSemanticContract
    production: ContentProductionBundle
    fact_repair_receipts: tuple[FactRepairReceipt, ...] = ()


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
