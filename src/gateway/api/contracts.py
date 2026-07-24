from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.shared.types import ContentTarget


class CreateContentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    weak_seed: str = Field(min_length=1, max_length=1000)
    reuse_version_id: UUID | None = None
    target: ContentTarget | None = None


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


class CreateTenantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_name: str = Field(min_length=2, max_length=120)
    administrator_name: str = Field(min_length=1, max_length=80)
    administrator_username: str = Field(min_length=3, max_length=80)
