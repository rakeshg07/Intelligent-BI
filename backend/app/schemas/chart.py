"""Pydantic Schemas for Charts and Chart Data Queries."""

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ChartBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    dataset_id: uuid.UUID
    viz_type: str = Field(..., min_length=1, max_length=50)
    params: dict[str, Any] = Field(default_factory=dict)
    query_context: dict[str, Any] = Field(default_factory=dict)


class ChartCreate(ChartBase):
    dashboard_id: uuid.UUID | None = None


class ChartUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    viz_type: str | None = None
    params: dict[str, Any] | None = None
    query_context: dict[str, Any] | None = None


class ChartOut(ChartBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owners: list[str] = Field(default_factory=list)
    created_by_id: uuid.UUID | None = None
    created_at: str | None = None
    updated_at: str | None = None


class ChartDataRequest(BaseModel):
    dataset_id: uuid.UUID
    viz_type: str = "bar"
    dimensions: list[str] = Field(default_factory=list)
    metrics: list[dict[str, Any]] = Field(default_factory=list)
    filters: list[dict[str, Any]] = Field(default_factory=list)
    time_column: str | None = None
    time_grain: str | None = None
    time_range: dict[str, str] | None = None
    order_by: list[dict[str, str]] | None = None
    row_limit: int = 1000


class ChartDataResponse(BaseModel):
    columns: list[str]
    column_types: list[str]
    rows: list[list[Any]]
    row_count: int
    sql: str
    duration_ms: int
