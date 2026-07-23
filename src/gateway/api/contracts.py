from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CreateContentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    weak_seed: str = Field(min_length=1, max_length=1000)
    reuse_version_id: UUID | None = None


class RevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instruction: str = Field(min_length=2, max_length=1000)


class ContentVersionResponse(BaseModel):
    kind: str = "content"
    task_id: UUID
    version_id: UUID
    version: int
    outline: str
    body: str


class GreetingResponse(BaseModel):
    kind: str = "greeting"
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
