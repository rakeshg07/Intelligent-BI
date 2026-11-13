"""Tests for Authentication Endpoints."""

import pytest
from httpx import AsyncClient

from app.core.config import settings


@pytest.mark.asyncio
async def test_admin_login_success(client: AsyncClient) -> None:
    """Test successful login with seeded admin credentials."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": settings.ADMIN_EMAIL, "password": settings.ADMIN_PASSWORD},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["user"]["email"] == settings.ADMIN_EMAIL
    assert data["user"]["is_superuser"] is True
    assert "admin:access" in data["user"]["permissions"]
    assert "access_token" in response.cookies


@pytest.mark.asyncio
async def test_login_invalid_password(client: AsyncClient) -> None:
    """Test login failure with wrong password."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": settings.ADMIN_EMAIL, "password": "wrongpassword123"},
    )
    assert response.status_code == 401
    data = response.json()
    assert data["code"] == "AUTHENTICATION_FAILED"


@pytest.mark.asyncio
async def test_get_me_endpoint(client: AsyncClient) -> None:
    """Test /api/v1/auth/me returns user profile when authenticated."""
    # 1. Login to get cookie
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": settings.ADMIN_EMAIL, "password": settings.ADMIN_PASSWORD},
    )
    token = login_res.json()["access_token"]

    # 2. Call /me with Bearer token
    me_res = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_res.status_code == 200
    user_data = me_res.json()
    assert user_data["email"] == settings.ADMIN_EMAIL
    assert user_data["is_active"] is True


@pytest.mark.asyncio
async def test_logout_endpoint(client: AsyncClient) -> None:
    """Test /api/v1/auth/logout clears auth cookies."""
    response = await client.post("/api/v1/auth/logout")
    assert response.status_code == 200
    assert response.json()["message"] == "Successfully logged out"
