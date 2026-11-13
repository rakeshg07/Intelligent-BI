"""AI Conversations, Messages, Tool Calls, and Feedback Models."""

import uuid
from typing import Any, Optional

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel


class AIConversation(BaseModel):
    """Chat conversation thread with the AI assistant."""

    __tablename__ = "ai_conversations"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(200), default="New Conversation")

    messages: Mapped[list["AIMessage"]] = relationship(
        "AIMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
    )


class AIMessage(BaseModel):
    """Individual message in an AI conversation."""

    __tablename__ = "ai_messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("ai_conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user, assistant, system, tool
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Grounding & Guardrail Audit
    grounding_status: Mapped[str] = mapped_column(
        String(50), default="not_applicable"
    )  # verified, failed, suppressed, bypassed
    ungrounded_numbers: Mapped[list[str]] = mapped_column(JSON, default=list)
    chart_spec: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # Cost & Performance metrics
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    conversation: Mapped["AIConversation"] = relationship(
        "AIConversation", back_populates="messages"
    )
    tool_calls: Mapped[list["AIToolCall"]] = relationship(
        "AIToolCall",
        back_populates="message",
        cascade="all, delete-orphan",
    )
    feedback: Mapped[Optional["AIFeedback"]] = relationship(
        "AIFeedback",
        back_populates="message",
        uselist=False,
        cascade="all, delete-orphan",
    )


class AIToolCall(BaseModel):
    """Tool invocation by the model (run_sql, list_tables, etc.)."""

    __tablename__ = "ai_tool_calls"

    message_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("ai_messages.id", ondelete="CASCADE"),
        nullable=False,
    )
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    arguments: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    execution_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=True)

    message: Mapped["AIMessage"] = relationship("AIMessage", back_populates="tool_calls")


class AIFeedback(BaseModel):
    """User rating and review of an AI response."""

    __tablename__ = "ai_feedback"

    message_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("ai_messages.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    rating: Mapped[str] = mapped_column(String(20), nullable=False)  # positive, negative
    feedback_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    message: Mapped["AIMessage"] = relationship("AIMessage", back_populates="feedback")
