"""Database Connection Schemas."""

import uuid
from typing import Any

from pydantic import BaseModel, Field


class DatabaseConnectionBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(None, max_length=255)
    dialect: str = Field(..., max_length=50)

    host: str | None = None
    port: int | None = None
    database_name: str | None = None
    username: str | None = None

    ssl_mode: str = "prefer"
    allow_dml: bool = False
    allow_file_uploads: bool = False
    allow_sqllab: bool = True
    row_limit: int = 10000
    statement_timeout_seconds: int = 30
    cache_timeout_seconds: int = 300

    ai_allowed_schemas: list[str] = []
    ai_allowed_tables: list[str] = []
    extra_params: dict[str, Any] = {}


class DatabaseConnectionCreate(DatabaseConnectionBase):
    password: str | None = None
    raw_uri: str | None = None


class DatabaseConnectionUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    host: str | None = None
    port: int | None = None
    database_name: str | None = None
    username: str | None = None
    password: str | None = None
    raw_uri: str | None = None

    ssl_mode: str | None = None
    allow_dml: bool | None = None
    allow_file_uploads: bool | None = None
    allow_sqllab: bool | None = None
    row_limit: int | None = None
    statement_timeout_seconds: int | None = None
    cache_timeout_seconds: int | None = None

    ai_allowed_schemas: list[str] | None = None
    ai_allowed_tables: list[str] | None = None


class DatabaseConnectionOut(DatabaseConnectionBase):
    id: uuid.UUID
    is_system: bool
    has_encrypted_password: bool = False

    model_config = {"from_attributes": True}


class ConnectionTestRequest(BaseModel):
    dialect: str
    host: str | None = None
    port: int | None = None
    database_name: str | None = None
    username: str | None = None
    password: str | None = None
    raw_uri: str | None = None


class ConnectionTestResponse(BaseModel):
    success: bool
    message: str
