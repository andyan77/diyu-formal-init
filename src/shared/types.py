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
class TenantManagementScope:
    """Trusted tenant/brand administration scope with no publishing identity."""

    tenant_id: UUID
    user_id: UUID
    brand_id: UUID


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
    business_data_kind: str = "formal_business_data"


@dataclass(frozen=True)
class PlatformDirectionProvenance:
    resource_schema_version: str
    metadata_revision: str
    source_kind: str
    source_refs: tuple[str, ...]
    official_platform_rule_version: str | None
    official_version_note: str
    observed_or_effective_at: str
    last_verified_at: str
    verification_status: str
    freshness_status: str
    supersedes: tuple[str, ...]
    superseded_by: str | None
    maintenance_owner: str


@dataclass(frozen=True)
class PlatformDirection:
    version: str
    rule_id: str
    rule_kind: str
    platform: str
    media_format: MediaFormat
    applicability: str
    platform_capability_source_ref: str
    platform_capability_source_scope: str
    direction_digest: str
    direction: str
    provenance: PlatformDirectionProvenance


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
    P1SemanticContract | P2SemanticContract | P3SemanticContract | P4SemanticContract | P5SemanticContract
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
    display_name: str = ""
    source_kind: str = "legacy_seed"
    source_note: str = ""
    fact_version: int = 1
    applicability: str = "legacy_scope"


@dataclass(frozen=True)
class SeriesEntry:
    """One immutable prior version actually compiled for a new series episode."""

    task_id: UUID
    version_id: UUID
    version: int
    position: int
    outline: str
    body: str


@dataclass(frozen=True)
class SeriesContext:
    """A bounded projection of one explicitly selected account series."""

    series_id: UUID
    revision: int
    title: str
    premise: str
    target_position: int
    prior_entries: tuple[SeriesEntry, ...] = ()
    user_asserted_published_continuity: bool = False


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
class DirectionSelection:
    """One axis choice: what the user picked, and what the brand boundary let it become.

    `origin` keeps the three per-axis states apart: an explicit choice for this task, a saved
    default carried over, or the person's own words matching a declared label or alias.
    """

    axis: str
    stable_id: str
    label: str
    applied_label: str
    translated: bool
    preserved_aspect: str
    origin: str = "explicit"


@dataclass(frozen=True)
class CreativeDirection:
    catalog_version: str
    selections: tuple[DirectionSelection, ...]
    custom_text: str
    body_related_opt_in: bool
    translation_notice: str | None
    # Axes the person switched off for this task; a saved default must not creep back in.
    cleared_axes: tuple[str, ...] = ()


@dataclass(frozen=True)
class AccountExpression:
    """The publishing account's five plain-language segments actually used this time."""

    profile_id: UUID | None
    version: int | None
    identity_position: str
    authority_boundary: str
    audience_relationship: str
    content_territories: str
    default_production_conditions: str
    is_draft: bool


@dataclass(frozen=True)
class ReferenceMaterial:
    """A reference the user explicitly selected for this task only."""

    asset_id: UUID
    title: str
    media_type: str
    reference_version: int
    text_body: str = ""
    reference_note: str = ""


@dataclass(frozen=True)
class RequestedControls:
    """Raw, untrusted client control input for one request; scopes are never sent by clients."""

    catalog_version: str | None = None
    selections: tuple[tuple[str, str], ...] = ()
    # Axes explicitly switched off for this task; distinct from "the person said nothing".
    cleared_axes: tuple[str, ...] = ()
    custom_text: str = ""
    body_related_opt_in: bool = False
    use_personal_preferences: bool = True
    material_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True)
class ContentControlContext:
    """What this task actually froze about how the user steered it.

    A later change to the catalog, the account profile, a private preference or a material must
    never rewrite an existing task, so a revision replays this and nothing else.
    """

    catalog_version: str | None
    direction: CreativeDirection | None
    account_expression: AccountExpression | None
    materials: tuple[ReferenceMaterial, ...]
    preference_mode: str
    preference_version: int | None
    # The expression identity this run really spoke from, frozen with the task.
    content_role: str = ""
    content_role_boundary: str = ""
    # The acting person's own soft collaboration input.  It reaches the generator and stays out
    # of the tenant-visible task snapshot and the ordinary run receipt.
    collaboration_note: str = ""


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
    creative_direction: CreativeDirection | None = None
    account_expression: AccountExpression | None = None
    reference_materials: tuple[ReferenceMaterial, ...] = ()
    collaboration_note: str = ""
    series_context: SeriesContext | None = None


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
    actor_organization_id: UUID | None = None


@dataclass(frozen=True)
class DisplayContext:
    """Everything one reference plan may read: reusable wall structure plus this task's own input."""

    brand_name: str
    organization_name: str
    operator_name: str
    task_expression_version: str
    task_expression: dict[str, object]
    store_name: str
    store_profile_version: str
    rail_profile: dict[str, object]
    products: tuple[tuple[str, dict[str, object]], ...]


@dataclass(frozen=True)
class DisplayGenerationInput:
    run_id: UUID
    task_id: UUID
    inventory: tuple[tuple[str, int], ...]
    context: DisplayContext
    active_domain_assets: tuple[ActiveAsset, ...]
    feedback: str | None = None
    prior_plan: dict[str, object] | None = None
    revision_target: tuple[str, str, str] | None = None
    hard_requirements: frozenset[str] = frozenset()


@dataclass(frozen=True)
class GeneratedDisplayArtifact:
    body: str
    plan: dict[str, object]
    model: str
    latency_ms: int
    retry_count: int
    provider_usage: dict[str, int] | None
