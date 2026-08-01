from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, TypeAlias
from uuid import UUID

from src.shared.creative_plan import CreativePlanV2
from src.shared.narrative import NarrativeFrame, NarrativeMode, UserFactCandidate

if TYPE_CHECKING:
    from src.shared.creative_kernel import CreativeKernelV1
    from src.shared.dm01_rules import DM01RuleBundleV1
    from src.shared.media_program import (
        MediaCapabilityEnvelope,
        MediaProgramSelectionV1,
    )
    from src.shared.product_value import ProductValueContract

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
SpeakerKind: TypeAlias = Literal[
    "institutional_account",
    "personal_ip_account",
    "unknown",
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
class MaterialMaintenanceScope:
    """Trusted tenant-user scope for maintaining their own organization assets."""

    tenant_id: UUID
    user_id: UUID
    brand_id: UUID
    organization_id: UUID


@dataclass(frozen=True)
class BrandContextSegment:
    segment_id: str
    source_document_id: str
    source_document_version_id: str
    source_id: str
    source_version: str
    semantic_kind: str
    evidence_level: str
    visibility_scope: str
    digest: str
    exact_text: str


@dataclass(frozen=True)
class BrandContextPacketV1:
    packet_version: str
    packet_digest: str
    segments: tuple[BrandContextSegment, ...]


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
    brand_reference_context: tuple[str, ...] = ()
    speaker_kind: SpeakerKind = "unknown"
    expression_constraint_context: tuple[str, ...] = ()
    creative_method_context: tuple[str, ...] = ()
    candidate_product_guidance_context: tuple[str, ...] = ()
    context_packet: BrandContextPacketV1 | None = None


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
    optional_capture_suggestion: str | None = None


@dataclass(frozen=True)
class GraphicProductionBundle:
    """The complete, visible reading chain for the current graphic target."""

    natural_guide: str
    hero_image: str
    image_sequence: str
    full_body: str
    layout_and_production: str
    release_caption_and_interaction: str
    optional_capture_suggestion: str | None = None


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
    product_id: UUID | None = None
    product_version_id: UUID | None = None


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


ConversationDisposition: TypeAlias = Literal["chat", "question", "ready"]
ConversationRole: TypeAlias = Literal["user", "assistant"]


@dataclass(frozen=True)
class ConversationTurn:
    """One bounded, user-visible turn used only to understand the current request."""

    role: ConversationRole
    content: str


@dataclass(frozen=True)
class ConversationInput:
    """The semantic collaboration input before a durable content task exists."""

    message: str
    history: tuple[ConversationTurn, ...]
    brand: BrandContext
    products: tuple[ProductFact, ...]
    target: ContentTarget
    selected_direction: str = ""
    explicit_narrative_mode: NarrativeMode | None = None
    prior_series_summary: str = ""
    creation_committed: bool = False
    allowed_tone_ids: tuple[str, ...] = ()
    allowed_mechanism_ids: tuple[str, ...] = ()
    platform_shape: str = ""
    user_fact_candidates: tuple[UserFactCandidate, ...] = ()


@dataclass(frozen=True)
class ConversationDecision:
    """A model decision that either continues the conversation or starts one task."""

    disposition: ConversationDisposition
    message: str
    user_premises: tuple[str, ...] = ()
    user_fact_spans: tuple[str, ...] = ()
    user_fact_source_ids: tuple[str, ...] = ()
    narrative_mode: NarrativeMode | None = None
    creative_plan: CreativePlanV2 | None = None
    primary_product: ContentProduct | None = None
    creation_proposal: bool = False
    proposed_intent_span: str = ""


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
class BoundProductMedia:
    """One explicitly selected, scope-checked product/media binding.

    Product facts and media bytes remain separate trusted sources.  This record
    only freezes their explicit administrative relationship and the precise
    current versions that were legal for this task.
    """

    binding_id: UUID
    product_id: UUID
    product_version_id: UUID
    product: ProductFact
    asset_id: UUID
    asset_version_id: UUID
    asset_version: int
    media_type: str
    source_ref: str
    source_checksum_sha256: str
    root_account_id: UUID
    control_organization_id: UUID


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
    # An explicit product-story route request; it never grants media capability.
    product_media_intent: bool = False


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
    bound_product_media: tuple[BoundProductMedia, ...] = ()
    # The expression identity this run really spoke from, frozen with the task.
    content_role: str = ""
    content_role_boundary: str = ""
    speaker_kind: SpeakerKind = "unknown"
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
    narrative_frame: NarrativeFrame | None = None
    creative_plan: CreativePlanV2 | None = None
    delivery_compiler_version: str | None = None
    prior_creative_kernel: CreativeKernelV1 | None = None
    media_capability_envelope: MediaCapabilityEnvelope | None = None
    media_program: MediaProgramSelectionV1 | None = None
    product_value_contract: ProductValueContract | None = None


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
    provider_usage: dict[str, int | str] | None
    primary_product: ContentProduct
    semantic_contract: ContentSemanticContract
    production: ContentProductionBundle
    fact_repair_receipts: tuple[FactRepairReceipt, ...] = ()
    reviewed_digest: str | None = None
    completion_snapshot_patch: dict[str, object] | None = None


@dataclass(frozen=True)
class DisplayScope:
    """Trusted internal merchandising scope; deliberately has no publishing account."""

    tenant_id: UUID
    user_id: UUID
    brand_id: UUID
    organization_id: UUID
    actor_organization_id: UUID | None = None
    store_id: UUID | None = None


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
    product_snapshots: tuple[dict[str, object], ...] = ()
    rule_bundle: DM01RuleBundleV1 | None = None


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
