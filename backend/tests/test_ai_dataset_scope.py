"""Tests for Dataset-Scoped AI Assistant, isolation, authorization, and switching."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.guardrails.sql_guard import AISQLGuard
from app.ai.orchestrator import AIOrchestrator
from app.ai.providers.mock import MockProvider
from app.ai.tools import (
    tool_execute_sql_query,
    tool_get_table_schema,
    tool_list_datasets_and_tables,
)
from app.core.config import settings
from app.core.errors import ValidationError
from app.db.models import Dataset, User
from tests.test_api_endpoints import get_admin_auth_headers


@pytest.mark.asyncio
async def test_ai_chat_dataset_not_found(client: AsyncClient) -> None:
    """Validate that passing an unverified or nonexistent dataset_id raises HTTP 404."""
    headers = await get_admin_auth_headers(client)
    random_id = str(uuid.uuid4())
    res = await client.post(
        "/api/v1/ai/chat",
        headers=headers,
        json={"prompt": "Summarize this dataset", "dataset_id": random_id},
    )
    assert res.status_code == 404
    assert f"Dataset '{random_id}' not found" in res.json()["detail"]


def test_ai_sql_guard_table_isolation() -> None:
    """Verify that AISQLGuard strictly restricts queries to allowed_tables."""
    allowed = {"global_sales"}

    # 1. Allowed table should pass
    clean_sql = AISQLGuard.validate_and_constrain(
        sql="SELECT category, SUM(sales) FROM global_sales GROUP BY category",
        allowed_tables=allowed,
    )
    assert "global_sales" in clean_sql.lower()

    # 2. Query against unauthorized table must be rejected
    with pytest.raises(ValidationError) as exc:
        AISQLGuard.validate_and_constrain(
            sql="SELECT * FROM users",
            allowed_tables=allowed,
        )
    assert "unauthorized table" in str(exc.value).lower()

    # 3. Query joining unauthorized table must also be rejected
    with pytest.raises(ValidationError) as exc_join:
        AISQLGuard.validate_and_constrain(
            sql="SELECT * FROM global_sales JOIN confidential_data ON global_sales.id = confidential_data.id",
            allowed_tables=allowed,
        )
    assert "unauthorized table" in str(exc_join.value).lower()


@pytest.mark.asyncio
async def test_ai_tools_table_schema_scoping(db_session: AsyncSession) -> None:
    """Verify tool_get_table_schema restricts inspection to authorized scope."""
    # When scoped to global_sales, requesting global_sales schema succeeds
    res_allowed = await tool_get_table_schema(
        session=db_session,
        table_name="global_sales",
        allowed_table="global_sales",
    )
    assert res_allowed["found"] is True

    # When scoped to global_sales, requesting another table is rejected with access restricted
    res_disallowed = await tool_get_table_schema(
        session=db_session,
        table_name="system_secrets",
        allowed_table="global_sales",
    )
    assert res_disallowed["found"] is False
    assert "Access restricted" in res_disallowed["error"]


@pytest.mark.asyncio
async def test_ai_tools_execute_sql_scoping(db_session: AsyncSession) -> None:
    """Verify tool_execute_sql_query blocks disallowed tables when scoped."""
    allowed = {"global_sales"}

    # Permitted query
    good_res = await tool_execute_sql_query(
        session=db_session,
        sql="SELECT category, SUM(total_revenue) as total_sales FROM global_sales GROUP BY category",
        allowed_tables=allowed,
    )
    assert good_res["success"] is True
    assert len(good_res["rows"]) > 0

    # Disallowed query
    bad_res = await tool_execute_sql_query(
        session=db_session,
        sql="SELECT * FROM unauthorized_table",
        allowed_tables=allowed,
    )
    assert bad_res["success"] is False
    assert "Security Guardrail Violation" in bad_res["error"]


@pytest.mark.asyncio
async def test_ai_tools_list_datasets_scoping(db_session: AsyncSession) -> None:
    """Verify tool_list_datasets_and_tables restricts returned datasets when scoped."""
    user_res = await db_session.execute(select(User).where(User.email == settings.ADMIN_EMAIL))
    admin = user_res.scalar_one_or_none()
    assert admin is not None

    # Get a dataset
    ds_res = await db_session.execute(select(Dataset).where(Dataset.deleted_at.is_(None)).limit(1))
    dataset = ds_res.scalar_one_or_none()
    if dataset:
        scoped_res = await tool_list_datasets_and_tables(
            session=db_session,
            user=admin,
            scoped_dataset_id=dataset.id,
        )
        assert scoped_res["count"] == 1
        assert scoped_res["datasets"][0]["dataset_id"] == str(dataset.id)


@pytest.mark.asyncio
async def test_ai_orchestrator_dataset_scoped_run(db_session: AsyncSession) -> None:
    """Verify that AIOrchestrator properly accepts dataset_id and executes grounded query."""
    user_res = await db_session.execute(select(User).where(User.email == settings.ADMIN_EMAIL))
    admin = user_res.scalar_one_or_none()
    assert admin is not None

    ds_res = await db_session.execute(
        select(Dataset).where(Dataset.table_name == "global_sales", Dataset.deleted_at.is_(None))
    )
    dataset = ds_res.scalar_one_or_none()
    dataset_id = dataset.id if dataset else None

    orchestrator = AIOrchestrator(provider=MockProvider())
    result = await orchestrator.run(
        session=db_session,
        user=admin,
        prompt="Show total sales by category",
        dataset_id=dataset_id,
    )

    assert result["answer"] is not None
    assert "global_sales" in (result["sql"] or "").lower()
    assert result["grounding"]["is_grounded"] is True
