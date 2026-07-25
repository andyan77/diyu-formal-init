from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.shared.types import ContentTarget


class CreativeDirectionRequest(BaseModel):
    """The optional five-axis panel for this request only; saving a default is a separate call."""

    model_config = ConfigDict(extra="forbid")

    catalog_version: str | None = Field(default=None, max_length=80)
    selections: dict[str, str] = Field(default_factory=dict)
    # Axes explicitly switched off for this task.  Saying nothing keeps a saved default; only
    # this list turns one off, and it never edits the saved default itself.
    cleared_axes: list[str] = Field(default_factory=list, max_length=5)
    custom_text: str = Field(default="", max_length=500)
    body_related_opt_in: bool = False


class CreateContentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    weak_seed: str = Field(min_length=1, max_length=1000)
    reuse_version_id: UUID | None = None
    target: ContentTarget | None = None
    creative_direction: CreativeDirectionRequest | None = None
    use_personal_preferences: bool = True
    material_ids: list[UUID] = Field(default_factory=list, max_length=5)


class RevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instruction: str = Field(min_length=2, max_length=1000)
    target: ContentTarget | None = None
    source_target: ContentTarget | None = None


class ContentVersionResponse(BaseModel):
    kind: str = "content"
    task_id: UUID
    version_id: UUID
    version: int
    outline: str
    body: str
    ai_generated: bool
    aigc_label: str | None = None
    aigc_release_reminder: str | None = None
    target: str | None = None
    target_key: ContentTarget | None = None
    adapted_from: str | None = None
    translation_notice: str | None = None
    applied_direction: list[str] = Field(default_factory=list)


class AccountExpressionVersionRequest(BaseModel):
    """Five plain-language segments; saving forms the next immutable version."""

    model_config = ConfigDict(extra="forbid")

    identity_position: str = Field(min_length=1, max_length=800)
    authority_boundary: str = Field(min_length=1, max_length=800)
    audience_relationship: str = Field(min_length=1, max_length=800)
    content_territories: str = Field(min_length=1, max_length=800)
    default_production_conditions: str = Field(min_length=1, max_length=800)


class CreationPreferenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    direction_defaults: dict[str, str] = Field(default_factory=dict)
    # Sending no defaults keeps the ones already saved; forgetting them is its own explicit act.
    clear_direction_defaults: bool = False
    collaboration_note: str = Field(default="", max_length=500)
    body_related_opt_in: bool = False


class ControlOrganizationRequest(BaseModel):
    """Which organization controls a publishing account, declared once by a tenant authority."""

    model_config = ConfigDict(extra="forbid")

    organization_id: UUID


class MaterialReferenceNoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference_note: str = Field(min_length=2, max_length=500)


class UnmetCapabilityResponseRequest(BaseModel):
    """笛语运维's minimum classification and reply; it changes nothing else."""

    model_config = ConfigDict(extra="forbid")

    gap_type: Literal[
        "unclassified",
        "knowledge",
        "generation_method",
        "media_tool",
        "product_scope",
        "policy_conflict",
        "source_gap",
    ]
    status: Literal["received", "classified", "answered"]
    response_text: str = Field(default="", max_length=1000)


class ContentPlanItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=120)
    note: str = Field(default="", max_length=500)
    selections: dict[str, str] = Field(default_factory=dict)


class ContentPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ContentPlanItem] = Field(default_factory=list, max_length=20)


class UnmetCapabilityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_text: str = Field(min_length=4, max_length=1000)
    creative_direction: CreativeDirectionRequest | None = None


class GreetingResponse(BaseModel):
    kind: str = "greeting"
    message: str


class ContentQuestionResponse(BaseModel):
    kind: str = "question"
    message: str


class SavedVersionResponse(BaseModel):
    version_id: UUID
    saved_at: datetime


class CreateDisplayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    inventory_text: str = Field(min_length=4, max_length=2000)


class DisplayRevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    feedback: str = Field(min_length=2, max_length=2000)


class DisplayVersionResponse(BaseModel):
    kind: str = "display"
    task_id: UUID
    version_id: UUID
    version: int
    body: str


class DisplayQuestionResponse(BaseModel):
    kind: str = "question"
    message: str


class ApplicationHandoffResponse(BaseModel):
    kind: str = "handoff"
    message: str


class BrandExpressionConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft: str = Field(min_length=8, max_length=4000)


class CreateSeriesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=100)
    premise: str = Field(default="", max_length=500)


class AddSeriesItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: UUID
    position: int | None = Field(default=None, ge=1)


class ReorderSeriesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_ids: list[UUID]


class MaterialUploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=120)
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=3, max_length=100)
    content_base64: str = Field(min_length=1, max_length=70_000_000)
    declares_identifiable_minor: bool = False
    # The only readable description of an image or video original; the system never looks at
    # the bytes, so an unread original can carry no meaning into a task without this note.
    reference_note: str = Field(default="", max_length=500)


class DefaultPersonaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    boundary: str = Field(min_length=1, max_length=500)


class CreateOperatorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=80)
    account_id: UUID
    default_persona_name: str = Field(default="", max_length=80)
    default_persona_boundary: str = Field(default="", max_length=500)


class CreatePublishingAccountRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    channel: Literal["抖音", "小红书", "微信视频号"]
    content_role_name: str = Field(min_length=1, max_length=80)
    voice_boundary: str = Field(min_length=1, max_length=500)
    operator_id: UUID
    # Which organization controls this account; defaults to the creating administrator's own.
    control_organization_id: UUID | None = None


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=12, max_length=512)


class OpsLoginRequest(LoginRequest):
    totp_code: str = Field(pattern=r"^[0-9]{6}$")


class SetPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: str = Field(min_length=12, max_length=512)


class ChangePasswordRequest(SetPasswordRequest):
    current_password: str = Field(min_length=12, max_length=512)


class CreateTenantUserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=80)
    username: str = Field(min_length=3, max_length=80)
    organization_id: UUID | None = None
    account_id: UUID | None = None
    grants_tenant_management: bool = False
    grants_material_maintenance: bool = False
    # Account use never implies profile maintenance; this is the separate, explicit grant.
    grants_expression_profile_maintenance: bool = False


class CreateTenantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_name: str = Field(min_length=2, max_length=120)
    administrator_name: str = Field(min_length=1, max_length=80)
    administrator_username: str = Field(min_length=3, max_length=80)
