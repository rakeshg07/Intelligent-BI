"""Authentication Schemas."""

import uuid

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """User login credential payload."""

    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=6)


class PermissionOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    resource: str

    model_config = {"from_attributes": True}


class RoleOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None = None
    is_system: bool
    permissions: list[PermissionOut] = []

    model_config = {"from_attributes": True}


class UserProfileOut(BaseModel):
    """User profile response with roles and granular permissions."""

    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    is_superuser: bool
    roles: list[RoleOut] = []
    permissions: list[str] = []

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    """Token response returned upon successful authentication."""

    access_token: str
    token_type: str = "bearer"
    user: UserProfileOut
