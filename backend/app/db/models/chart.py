"""Chart Entity Model."""

import uuid
from typing import Any

from sqlalchemy import JSON, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class Chart(BaseModel):
    """Saved Chart definition."""

    __tablename__ = "charts"

    title: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    dataset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
    )
    viz_type: Mapped[str] = mapped_column(String(50), nullable=False)  # bar, line, table, pie, etc.

    # Form parameters: metrics, dimensions, filters, time_range, group_by, sort, etc.
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # Query context / cached query configuration
    query_context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    owners: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
