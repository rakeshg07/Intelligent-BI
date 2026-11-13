"""Dashboard, Dashboard Chart Placements, and Native Filters."""

import uuid
from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel


class Dashboard(BaseModel):
    """Dashboard layout and presentation container."""

    __tablename__ = "dashboards"

    title: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    slug: Mapped[str] = mapped_column(String(200), unique=True, index=True, nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)

    # Grid layout tree / position dictionary (react-grid-layout)
    layout: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    owners: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    charts: Mapped[list["DashboardChart"]] = relationship(
        "DashboardChart",
        back_populates="dashboard",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    filters: Mapped[list["DashboardFilter"]] = relationship(
        "DashboardFilter",
        back_populates="dashboard",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class DashboardChart(BaseModel):
    """Positioned chart within a dashboard."""

    __tablename__ = "dashboard_charts"

    dashboard_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("dashboards.id", ondelete="CASCADE"),
        nullable=False,
    )
    chart_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("charts.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # x, y, w, h

    dashboard: Mapped["Dashboard"] = relationship("Dashboard", back_populates="charts")


class DashboardFilter(BaseModel):
    """Native dashboard filter scoped to charts."""

    __tablename__ = "dashboard_filters"

    dashboard_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("dashboards.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    filter_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # value_select, time_range, numeric_range, time_grain
    target_charts: Mapped[list[str]] = mapped_column(
        JSON, default=list
    )  # list of chart UUIDs scoped
    default_value: Mapped[Any] = mapped_column(JSON, nullable=True)

    dashboard: Mapped["Dashboard"] = relationship("Dashboard", back_populates="filters")
