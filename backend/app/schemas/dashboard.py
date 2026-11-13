"""Pydantic Schemas for Dashboards, Placements, and Native Filters."""

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DashboardChartPlacement(BaseModel):
    chart_id: uuid.UUID
    position: dict[str, Any] = Field(default_factory=dict)


class DashboardFilterSchema(BaseModel):
    name: str
    filter_type: str  # value_select, time_range, numeric_range, time_grain
    target_charts: list[str] = Field(default_factory=list)
    default_value: Any | None = None


class DashboardBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    slug: str | None = None
    is_published: bool = False
    layout: dict[str, Any] = Field(default_factory=dict)


class DashboardCreate(DashboardBase):
    chart_ids: list[uuid.UUID] = Field(default_factory=list)


class DashboardUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    is_published: bool | None = None
    layout: dict[str, Any] | None = None
    chart_ids: list[uuid.UUID] | None = None
    filters: list[DashboardFilterSchema] | None = None


class DashboardOut(DashboardBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    owners: list[str] = Field(default_factory=list)
    created_by_id: uuid.UUID | None = None
    charts: list[dict[str, Any]] = Field(default_factory=list)
    filters: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None
