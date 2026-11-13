"""Integration tests for AI Assistant Orchestrator with real data execution."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.orchestrator import AIOrchestrator
from app.ai.providers.mock import MockProvider
from app.core.config import settings
from app.db.models import User


@pytest.mark.asyncio
async def test_ai_orchestrator_end_to_end_query(db_session: AsyncSession):
    # Get admin user
    user_res = await db_session.execute(select(User).where(User.email == settings.ADMIN_EMAIL))
    admin = user_res.scalar_one_or_none()
    assert admin is not None

    orchestrator = AIOrchestrator(provider=MockProvider())
    result = await orchestrator.run(
        session=db_session,
        user=admin,
        prompt="What is our total revenue breakdown by category?",
    )

    assert result["answer"] is not None
    assert "global_sales" in (result["sql"] or "").lower()
    assert len(result["rows"]) > 0
    assert result["row_count"] > 0
    assert result["grounding"]["is_grounded"] is True
    assert len(result["steps"]) >= 1
    assert result["recommended_chart"]["viz_type"] in ("bar", "pie", "table", "big_number")
