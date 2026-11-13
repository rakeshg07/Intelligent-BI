"""AI Assistant API Endpoints (ADR-004 & Phase 4)."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai.guardrails.grounding import GroundingGuardrail
from app.ai.orchestrator import AIOrchestrator
from app.api.v1.deps import get_db_session, require_permission
from app.core.config import settings
from app.db.models import AIConversation, AIMessage, Dataset, User
from app.schemas.ai import AIChatRequest, AIChatResponse, AIStatusResponse, AIVerifyRequest

router = APIRouter(prefix="/ai", tags=["AI Assistant"])


@router.get("/status", response_model=AIStatusResponse)
async def get_ai_status(
    current_user: User = Depends(require_permission("ai:use")),
) -> Any:
    """Return whether the AI Assistant is enabled and configured."""
    has_key = bool(
        settings.GROQ_API_KEY
        or settings.GEMINI_API_KEY
        or settings.OPENAI_API_KEY
        or settings.ANTHROPIC_API_KEY
    )
    return AIStatusResponse(
        enabled=settings.AI_ENABLED,
        provider=settings.LLM_PROVIDER,
        model=settings.LLM_MODEL,
        has_api_key=has_key,
    )


@router.post("/chat", response_model=AIChatResponse)
async def chat_with_ai(
    payload: AIChatRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_permission("ai:use")),
) -> Any:
    """Execute grounded natural language question against connected business data."""
    if not settings.AI_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="AI Assistant is disabled. Enable AI_ENABLED=true in settings.",
        )

    # Validate dataset authorization and existence if dataset_id provided
    if payload.dataset_id:
        if not current_user.is_superuser:
            user_perms = {p.code for r in current_user.roles for p in r.permissions}
            if "datasets:read" not in user_perms:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Missing required permission to access datasets: 'datasets:read'",
                )

        ds_stmt = select(Dataset).where(
            Dataset.id == payload.dataset_id,
            Dataset.deleted_at.is_(None),
        )
        ds_res = await session.execute(ds_stmt)
        if not ds_res.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Dataset '{payload.dataset_id}' not found or deleted.",
            )

    orchestrator = AIOrchestrator()
    result = await orchestrator.run(
        session=session,
        user=current_user,
        prompt=payload.prompt,
        conversation_id=payload.conversation_id,
        dataset_id=payload.dataset_id,
        database_id=payload.database_id,
    )
    return AIChatResponse(**result)


@router.post("/verify")
async def verify_grounding(
    payload: AIVerifyRequest,
    current_user: User = Depends(require_permission("ai:use")),
) -> dict[str, Any]:
    """Ad-hoc endpoint to verify numeric grounding of text against query rows."""
    res = GroundingGuardrail.verify(
        response_text=payload.text,
        query_rows=payload.rows,
        columns=payload.columns,
    )
    return res.to_dict()


@router.get("/conversations")
async def list_conversations(
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_permission("ai:use")),
) -> list[dict[str, Any]]:
    """List recent AI conversations for current user."""
    stmt = (
        select(AIConversation)
        .where(AIConversation.user_id == current_user.id, AIConversation.deleted_at.is_(None))
        .order_by(AIConversation.created_at.desc())
        .limit(20)
    )
    res = await session.execute(stmt)
    convs = res.scalars().all()

    return [
        {
            "id": str(c.id),
            "title": c.title,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in convs
    ]


@router.get("/conversations/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_permission("ai:use")),
) -> list[dict[str, Any]]:
    """Get message history for an AI conversation thread."""
    stmt = (
        select(AIMessage)
        .options(selectinload(AIMessage.tool_calls))
        .where(
            AIMessage.conversation_id == conversation_id,
            AIMessage.deleted_at.is_(None),
        )
        .order_by(AIMessage.created_at.asc())
    )
    res = await session.execute(stmt)
    messages = res.scalars().all()

    return [
        {
            "id": str(m.id),
            "role": m.role,
            "content": m.content,
            "grounding_status": m.grounding_status,
            "ungrounded_numbers": m.ungrounded_numbers or [],
            "chart_spec": m.chart_spec,
            "tool_calls": [
                {
                    "tool_name": tc.tool_name,
                    "arguments": tc.arguments,
                    "success": tc.success,
                    "execution_time_ms": tc.execution_time_ms,
                }
                for tc in m.tool_calls
            ],
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in messages
    ]
