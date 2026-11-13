"""Database Connections and Uploaded Files Models."""

import uuid
from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class DatabaseConnection(BaseModel):
    """External or Internal database connection credentials and settings."""

    __tablename__ = "database_connections"

    name: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dialect: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # postgres, mysql, sqlite, duckdb, clickhouse, mssql

    # Credentials encrypted at rest using Fernet
    sqlalchemy_uri_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    database_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    password_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    # Operational Security & Connection Settings
    ssl_mode: Mapped[str] = mapped_column(String(20), default="prefer")
    allow_dml: Mapped[bool] = mapped_column(Boolean, default=False)
    allow_file_uploads: Mapped[bool] = mapped_column(Boolean, default=False)
    allow_sqllab: Mapped[bool] = mapped_column(Boolean, default=True)
    row_limit: Mapped[int] = mapped_column(Integer, default=10000)
    statement_timeout_seconds: Mapped[int] = mapped_column(Integer, default=30)
    cache_timeout_seconds: Mapped[int] = mapped_column(Integer, default=300)
    is_system: Mapped[bool] = mapped_column(
        Boolean, default=False
    )  # True for built-in DuckDB 'Uploads'

    # AI Allow-lists (Default empty until admin enables)
    ai_allowed_schemas: Mapped[list[str]] = mapped_column(JSON, default=list)
    ai_allowed_tables: Mapped[list[str]] = mapped_column(JSON, default=list)

    # Ownership & Auditing
    owners: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )


class UploadedFile(BaseModel):
    """Metadata tracking file uploads (CSV, TSV, XLSX, Parquet, JSON) into DuckDB."""

    __tablename__ = "uploaded_files"

    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_format: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # csv, tsv, xlsx, json, parquet
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)

    target_database_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("database_connections.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_table_name: Mapped[str] = mapped_column(String(100), nullable=False)

    total_rows: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_columns: Mapped[int | None] = mapped_column(Integer, nullable=True)
    schema_inferred: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    status: Mapped[str] = mapped_column(
        String(50), default="pending"
    )  # pending, parsing, completed, failed
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    uploaded_by_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
