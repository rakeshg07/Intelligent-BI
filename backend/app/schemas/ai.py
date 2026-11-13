"""Pydantic Schemas for AI Assistant."""

import uuid
from typing import Any

from pydantic import BaseModel, Field


class AIChatRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=2000)
    conversation_id: uuid.UUID | None = None
    dataset_id: uuid.UUID | None = None
    database_id: uuid.UUID | None = None


class AIChatResponse(BaseModel):
    conversation_id: str
    message_id: str
    answer: str
    sql: str | None = None
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    row_count: int = 0
    duration_ms: int = 0
    grounding: dict[str, Any] = Field(default_factory=dict)
    recommended_chart: dict[str, Any] = Field(default_factory=dict)
    steps: list[dict[str, Any]] = Field(default_factory=list)
    latency_ms: int = 0


class AIVerifyRequest(BaseModel):
    text: str
    rows: list[list[Any]] = Field(default_factory=list)
    columns: list[str] | None = None


class AIStatusResponse(BaseModel):
    enabled: bool
    provider: str | None = None
    model: str | None = None
    has_api_key: bool = False
