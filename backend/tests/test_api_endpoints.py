"""End-to-End API Integration Tests for Core BI Platform Modules."""

import pytest
from httpx import AsyncClient

from app.core.config import settings


async def get_admin_auth_headers(client: AsyncClient) -> dict[str, str]:
    """Helper to authenticate as admin and obtain authorization headers."""
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": settings.ADMIN_EMAIL, "password": settings.ADMIN_PASSWORD},
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_api_databases_list(client: AsyncClient) -> None:
    """Test listing database connections."""
    headers = await get_admin_auth_headers(client)
    res = await client.get("/api/v1/databases/", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert any(d["name"] == "Uploads" for d in data)


@pytest.mark.asyncio
async def test_api_datasets_lifecycle(client: AsyncClient) -> None:
    """Test listing and querying datasets."""
    headers = await get_admin_auth_headers(client)
    res = await client.get("/api/v1/datasets/", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_api_charts_list(client: AsyncClient) -> None:
    """Test listing charts."""
    headers = await get_admin_auth_headers(client)
    res = await client.get("/api/v1/charts/", headers=headers)
    assert res.status_code == 200
    assert isinstance(res.json(), list)


@pytest.mark.asyncio
async def test_api_dashboards_list(client: AsyncClient) -> None:
    """Test listing dashboards."""
    headers = await get_admin_auth_headers(client)
    res = await client.get("/api/v1/dashboards/", headers=headers)
    assert res.status_code == 200
    assert isinstance(res.json(), list)


@pytest.mark.asyncio
async def test_api_sqllab_execute_query(client: AsyncClient) -> None:
    """Test SQL Lab query execution on analytical engine."""
    headers = await get_admin_auth_headers(client)

    # Fetch default DuckDB database connection ID
    db_res = await client.get("/api/v1/databases/", headers=headers)
    assert db_res.status_code == 200
    db_id = db_res.json()[0]["id"]

    payload = {
        "database_id": db_id,
        "sql": "SELECT category, total_revenue FROM global_sales ORDER BY total_revenue DESC LIMIT 5",
        "limit": 10,
    }
    res = await client.post("/api/v1/sqllab/execute", json=payload, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "columns" in data
    assert "rows" in data
    assert len(data["rows"]) > 0


@pytest.mark.asyncio
async def test_api_ai_status(client: AsyncClient) -> None:
    """Test AI assistant status endpoint."""
    headers = await get_admin_auth_headers(client)
    res = await client.get("/api/v1/ai/status", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "enabled" in data
    assert "provider" in data


@pytest.mark.asyncio
async def test_api_admin_audit_log(client: AsyncClient) -> None:
    """Test retrieving system audit log as admin."""
    headers = await get_admin_auth_headers(client)
    res = await client.get("/api/v1/admin/audit-log", headers=headers)
    assert res.status_code == 200
    assert "data" in res.json()
