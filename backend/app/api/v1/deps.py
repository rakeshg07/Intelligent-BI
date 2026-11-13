"""FastAPI Dependency Injection Providers."""

import uuid
from collections.abc import AsyncGenerator, Callable
from typing import Any

from fastapi import Cookie, Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.errors import AuthenticationError, PermissionDeniedError
from app.core.security import decode_token
from app.db.models import Role, User
from app.db.session import AsyncSessionLocal


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a scoped async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    access_token: str | None = Cookie(default=None),
    authorization: str | None = Header(default=None),
) -> User:
    """Extract authenticated user from httpOnly cookie or Authorization header."""
    token: str | None = None

    if access_token:
        token = access_token
    elif authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()

    if not token:
        if not settings.AUTH_REQUIRED:
            # Fallback to default superuser/admin in dev bypass mode
            admin_stmt = (
                select(User)
                .options(selectinload(User.roles).selectinload(Role.permissions))
                .where(User.deleted_at.is_(None))
                .order_by(User.is_superuser.desc())
            )
            admin_res = await session.execute(admin_stmt)
            default_user = admin_res.scalars().first()
            if default_user:
                return default_user
        raise AuthenticationError("Not authenticated: Missing token")

    payload = decode_token(token)
    user_id_raw = payload.get("sub")
    if not user_id_raw:
        raise AuthenticationError("Invalid token: Missing subject")

    try:
        user_uuid = uuid.UUID(str(user_id_raw))
    except (ValueError, TypeError) as e:
        raise AuthenticationError("Invalid token: Malformed subject UUID") from e

    # Fetch user with eager loaded roles and their permissions
    stmt = (
        select(User)
        .options(
            selectinload(User.roles).selectinload(Role.permissions),
        )
        .where(User.id == user_uuid, User.deleted_at.is_(None))
    )
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise AuthenticationError("User not found or deleted")

    if not user.is_active:
        raise AuthenticationError("User account is inactive")

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Ensure current user is active."""
    if not current_user.is_active:
        raise AuthenticationError("User is inactive")
    return current_user


def require_permission(permission_code: str) -> Callable[..., Any]:
    """Dependency factory checking if current user possesses permission or is superuser."""

    async def permission_checker(current_user: User = Depends(get_current_active_user)) -> User:
        if current_user.is_superuser:
            return current_user

        # Collect user permissions from assigned roles
        user_permissions = set()
        for role in current_user.roles:
            for perm in role.permissions:
                user_permissions.add(perm.code)

        if permission_code not in user_permissions:
            raise PermissionDeniedError(
                f"Missing required permission: '{permission_code}'",
                details={"required_permission": permission_code},
            )

        return current_user

    return permission_checker
