"""Semantic Datasets, Columns, Metrics, and Row-Level Security Rules."""

import uuid

from sqlalchemy import JSON, Boolean, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel


class Dataset(BaseModel):
    """Semantic Dataset representation (Physical table/view or Virtual SQL)."""

    __tablename__ = "datasets"

    name: Mapped[str] = mapped_column(String(150), index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    database_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("database_connections.id", ondelete="CASCADE"),
        nullable=False,
    )
    schema_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    table_name: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Virtual datasets use custom SQL
    is_virtual: Mapped[bool] = mapped_column(Boolean, default=False)
    sql_expression: Mapped[str | None] = mapped_column(Text, nullable=True)

    owners: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    columns: Mapped[list["DatasetColumn"]] = relationship(
        "DatasetColumn",
        back_populates="dataset",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    metrics: Mapped[list["DatasetMetric"]] = relationship(
        "DatasetMetric",
        back_populates="dataset",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    rls_rules: Mapped[list["RLSRule"]] = relationship(
        "RLSRule",
        back_populates="dataset",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class DatasetColumn(BaseModel):
    """Column definition within a dataset."""

    __tablename__ = "dataset_columns"

    dataset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    verbose_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    data_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    is_datetime: Mapped[bool] = mapped_column(Boolean, default=False)
    is_dimension: Mapped[bool] = mapped_column(Boolean, default=True)
    is_filterable: Mapped[bool] = mapped_column(Boolean, default=True)
    is_groupable: Mapped[bool] = mapped_column(Boolean, default=True)
    is_hidden_from_ai: Mapped[bool] = mapped_column(Boolean, default=False)

    dataset: Mapped["Dataset"] = relationship("Dataset", back_populates="columns")


class DatasetMetric(BaseModel):
    """Calculated metric or aggregation definition."""

    __tablename__ = "dataset_metrics"

    dataset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    verbose_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    sql_expression: Mapped[str] = mapped_column(Text, nullable=False)  # e.g. SUM(sales_amount)
    metric_type: Mapped[str] = mapped_column(String(50), default="aggregate")
    number_format: Mapped[str | None] = mapped_column(String(50), nullable=True)  # e.g. $, .2f, %
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    dataset: Mapped["Dataset"] = relationship("Dataset", back_populates="metrics")


class RLSRule(BaseModel):
    """Row-Level Security Rule attached to a dataset and role."""

    __tablename__ = "rls_rules"

    dataset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False,
    )
    clause: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # e.g. "tenant_id = 10" or "country = 'US'"
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    dataset: Mapped["Dataset"] = relationship("Dataset", back_populates="rls_rules")
