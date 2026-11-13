"""Authentication API Endpoints (Login, Logout, Me, Refresh)."""
from typing import Any, List, Literal
from fastapi import APIRouter, Cookie, Depends, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.deps import get_current_active_user, get_db_session
from app.core.config import settings
from app.core.errors import AuthenticationError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.db.models import AuditLog, Role, User
from app.schemas.auth import LoginRequest, RoleOut, TokenResponse, UserProfileOut

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _extract_user_permissions(user: User) -> List[str]:
    """Helper to compile flat list of unique permission codes for a user."""
    perms = set()
    for role in user.roles:
        for perm in role.permissions:
            perms.add(perm.code)
    return sorted(list(perms))


@router.post("/login", response_model=TokenResponse)
async def login(
    credentials: LoginRequest,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
) -> Any:
    """Authenticate user with email and password, setting secure httpOnly cookies."""
    stmt = (
        select(User)
        .options(selectinload(User.roles).selectinload(Role.permissions))
        .where(User.email == credentials.email, User.deleted_at.is_(None))
    )
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not verify_password(credentials.password, user.hashed_password):
        raise AuthenticationError("Invalid email or password")

    if not user.is_active:
        raise AuthenticationError("User account is inactive")

    # Generate tokens
    token_data = {"sub": str(user.id), "email": user.email}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    # Set secure httpOnly cookies
    samesite_val: Literal["lax", "strict", "none"] = (
        "strict" if settings.COOKIE_SAMESITE.lower() == "strict"
        else "none" if settings.COOKIE_SAMESITE.lower() == "none"
        else "lax"
    )

    response.set_cookie(
        key="access_token",
        value=access_token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=samesite_val,
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=samesite_val,
        path="/",
    )

    # Record login audit log
    audit_entry = AuditLog(
        user_id=user.id,
        action="login",
        resource_type="user",
        resource_id=str(user.id),
        details={"email": user.email},
    )
    session.add(audit_entry)
    await session.commit()

    user_out = UserProfileOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        is_superuser=user.is_superuser,
        roles=[RoleOut.model_validate(r) for r in user.roles],
        permissions=_extract_user_permissions(user),
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=user_out,
    )


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(response: Response) -> dict[str, str]:
    """Clear authentication cookies."""
    response.delete_cookie(key="access_token", path="/")
    response.delete_cookie(key="refresh_token", path="/")
    return {"message": "Successfully logged out"}


@router.get("/me", response_model=UserProfileOut)
async def get_my_profile(
    current_user: User = Depends(get_current_active_user),
) -> UserProfileOut:
    """Return profile, roles, and granular permissions for currently authenticated user."""
    return UserProfileOut(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        is_active=current_user.is_active,
        is_superuser=current_user.is_superuser,
        roles=[RoleOut.model_validate(r) for r in current_user.roles],
        permissions=_extract_user_permissions(current_user),
    )


@router.post("/refresh")
async def refresh_token(
    response: Response,
    refresh_token: str | None = Cookie(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    """Issue a new access token using a valid refresh token cookie."""
    if not refresh_token:
        raise AuthenticationError("Refresh token missing")

    payload = decode_token(refresh_token)
    if payload.get("type") != "refresh":
        raise AuthenticationError("Invalid token type for refresh")

    user_id = payload.get("sub")
    stmt = select(User).where(User.id == user_id, User.deleted_at.is_(None))
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise AuthenticationError("User not found or inactive")

    new_access_token = create_access_token({"sub": str(user.id), "email": user.email})

    samesite_val: Literal["lax", "strict", "none"] = (
        "strict" if settings.COOKIE_SAMESITE.lower() == "strict"
        else "none" if settings.COOKIE_SAMESITE.lower() == "none"
        else "lax"
    )

    response.set_cookie(
        key="access_token",
        value=new_access_token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=samesite_val,
        path="/"
    )

    return {"message": "Token refreshed successfully"}

