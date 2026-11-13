"""AI Assistant Agent Orchestrator (ADR-004 & Phase 4).

Coordinates schema discovery, tool-calling loop, query execution with AST safety,
numeric anti-hallucination verification, and chart visualization recommendation.
"""

import json
import time
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai.guardrails.grounding import GroundingGuardrail, GroundingResult
from app.ai.prompts import SYSTEM_PROMPT
from app.ai.providers.base import BaseLLMProvider, LLMMessage
from app.ai.providers.factory import get_llm_provider
from app.ai.tools import (
    AI_TOOLS_SPEC,
    tool_execute_sql_query,
    tool_get_table_schema,
    tool_list_datasets_and_tables,
)
from app.db.models import AIConversation, AIMessage, AIToolCall, Dataset, User


def recommend_chart_for_results(
    columns: list[str],
    column_types: list[str],
    rows: list[list[Any]],
    row_count: int,
) -> dict[str, Any]:
    """Determine the optimal visual chart configuration based on result schema."""
    if not columns or not rows:
        return {"viz_type": "table", "options": {}}

    # Single aggregate KPI
    if len(columns) == 1 and row_count == 1:
        return {
            "viz_type": "big_number",
            "metric": columns[0],
            "options": {
                "prefix": "$"
                if "revenue" in columns[0].lower() or "profit" in columns[0].lower()
                else ""
            },
        }

    # Two columns: dimension and metric
    if len(columns) == 2:
        col1_lower = columns[0].lower()
        # Time progression
        if (
            "date" in col1_lower
            or "time" in col1_lower
            or "month" in col1_lower
            or "year" in col1_lower
        ):
            return {
                "viz_type": "line",
                "time_column": columns[0],
                "metrics": [columns[1]],
                "options": {},
            }
        # Proportional share
        if "region" in col1_lower or "status" in col1_lower or row_count <= 6:
            return {
                "viz_type": "pie",
                "dimensions": [columns[0]],
                "metrics": [columns[1]],
                "options": {"isDonut": True},
            }
        # Standard categorical bar
        return {
            "viz_type": "bar",
            "dimensions": [columns[0]],
            "metrics": [columns[1]],
            "options": {},
        }

    # Three columns: two dimensions and metric (e.g. heatmap or multi-bar)
    if len(columns) == 3 and row_count <= 50:
        return {
            "viz_type": "heatmap",
            "dimensions": [columns[0], columns[1]],
            "metrics": [columns[2]],
            "options": {},
        }

    # Multi-column table
    return {
        "viz_type": "table",
        "dimensions": columns,
        "options": {},
    }


class AIOrchestrator:
    """Agentic Orchestrator managing end-to-end grounded query execution."""

    def __init__(self, provider: BaseLLMProvider | None = None):
        self.provider = provider or get_llm_provider()

    async def run(
        self,
        session: AsyncSession,
        user: User,
        prompt: str,
        conversation_id: uuid.UUID | None = None,
        dataset_id: uuid.UUID | None = None,
        database_id: uuid.UUID | None = None,
        max_turns: int = 5,
    ) -> dict[str, Any]:
        """Execute agentic conversational turn with grounded SQL execution."""
        start_time = time.time()

        # 1. Fetch or create conversation
        if conversation_id:
            try:
                conv_uuid = (
                    conversation_id
                    if isinstance(conversation_id, uuid.UUID)
                    else uuid.UUID(str(conversation_id))
                )
            except ValueError:
                conv_uuid = None
        else:
            conv_uuid = None

        if conv_uuid:
            conv_res = await session.execute(
                select(AIConversation).where(
                    AIConversation.id == conv_uuid,
                    AIConversation.user_id == user.id,
                    AIConversation.deleted_at.is_(None),
                )
            )
            conversation = conv_res.scalar_one_or_none()
        else:
            conversation = None

        if not conversation:
            conversation = AIConversation(
                user_id=user.id,
                title=prompt[:80] if len(prompt) > 80 else prompt,
            )
            session.add(conversation)
            await session.flush()

        # Load prior conversation history before appending the new user turn
        history_messages: list[LLMMessage] = []
        hist_res = await session.execute(
            select(AIMessage)
            .where(AIMessage.conversation_id == conversation.id, AIMessage.deleted_at.is_(None))
            .order_by(AIMessage.created_at.asc())
        )
        for hm in hist_res.scalars().all()[-20:]:
            if hm.role in ("user", "assistant") and hm.content:
                history_messages.append(LLMMessage(role=hm.role, content=hm.content))

        # 2. Record User Message
        user_message_record = AIMessage(
            conversation_id=conversation.id,
            role="user",
            content=prompt,
        )
        session.add(user_message_record)
        await session.flush()

        # 3. Contextual prompt enrichment if dataset_id provided
        context_hint = ""
        if dataset_id:
            ds_res = await session.execute(
                select(Dataset)
                .options(selectinload(Dataset.columns), selectinload(Dataset.metrics))
                .where(Dataset.id == dataset_id, Dataset.deleted_at.is_(None))
            )
            ds = ds_res.scalar_one_or_none()
            if ds:
                col_list = ", ".join([f"{c.name} ({c.data_type})" for c in (ds.columns or [])])
                context_hint = (
                    f"\n\n### ACTIVE DATASET CONTEXT (STRICT SCOPE):\n"
                    f"- The user is specifically exploring dataset: '{ds.name}'\n"
                    f"- Target Table: '{ds.table_name}'\n"
                    f"- Columns: {col_list or 'Inspect with get_table_schema'}\n"
                    f"- IMPORTANT: You MUST focus your analysis, queries, and answers ONLY on table '{ds.table_name}' unless the user explicitly asks about other tables."
                )

        # 4. Initialize message context for LLM (system + prior turns + current prompt)
        messages: list[LLMMessage] = (
            [LLMMessage(role="system", content=SYSTEM_PROMPT + context_hint)]
            + history_messages
            + [LLMMessage(role="user", content=prompt)]
        )

        # Execution tracking
        steps: list[dict[str, Any]] = []
        executed_query_data: dict[str, Any] | None = None
        all_query_rows: list[list[Any]] = []
        all_query_columns: list[str] = []

        turn_count = 0
        final_answer = ""

        while turn_count < max_turns:
            turn_count += 1

            # Call provider
            response = await self.provider.generate(messages=messages, tools=AI_TOOLS_SPEC)

            if not response.tool_calls:
                # Model generated final natural language response
                final_answer = response.content or ""
                break

            # Handle tool calls
            for tc in response.tool_calls:
                step_record = {
                    "step": len(steps) + 1,
                    "tool": tc.name,
                    "arguments": tc.arguments,
                }

                tool_start = time.time()
                tool_output: dict[str, Any] = {}
                success = True

                if tc.name == "list_datasets_and_tables":
                    tool_output = await tool_list_datasets_and_tables(
                        session=session,
                        user=user,
                        search=tc.arguments.get("search"),
                    )

                elif tc.name == "get_table_schema":
                    tool_output = await tool_get_table_schema(
                        session=session,
                        table_name=tc.arguments.get("table_name", ""),
                        dataset_id=tc.arguments.get("dataset_id"),
                    )

                elif tc.name == "execute_sql_query":
                    sql = tc.arguments.get("sql", "")
                    tool_output = await tool_execute_sql_query(
                        session=session,
                        sql=sql,
                        database_id=str(database_id) if database_id else None,
                    )
                    success = tool_output.get("success", False)

                    if success:
                        executed_query_data = tool_output
                        all_query_rows.extend(tool_output.get("rows", []))
                        all_query_columns = tool_output.get("columns", [])

                else:
                    tool_output = {"error": f"Unknown tool '{tc.name}'."}
                    success = False

                tool_elapsed_ms = int((time.time() - tool_start) * 1000)
                step_record["output"] = tool_output
                step_record["elapsed_ms"] = tool_elapsed_ms
                steps.append(step_record)

                # Persist AIToolCall audit in db
                db_tool_call = AIToolCall(
                    message_id=user_message_record.id,
                    tool_name=tc.name,
                    arguments=tc.arguments,
                    result=tool_output,
                    execution_time_ms=tool_elapsed_ms,
                    success=success,
                )
                session.add(db_tool_call)

                # Feed result back into conversation loop
                messages.append(
                    LLMMessage(
                        role="assistant",
                        tool_calls=[tc],
                    )
                )
                messages.append(
                    LLMMessage(
                        role="tool",
                        tool_call_id=tc.id,
                        name=tc.name,
                        content=json.dumps(tool_output),
                    )
                )

        # 5. Verification & Anti-Hallucination Guardrail
        grounding_result: GroundingResult = GroundingGuardrail.verify(
            response_text=final_answer,
            query_rows=all_query_rows,
            columns=all_query_columns,
        )

        # 6. Recommendation for Visual Chart
        chart_recommendation = {}
        if executed_query_data and executed_query_data.get("rows"):
            chart_recommendation = recommend_chart_for_results(
                columns=executed_query_data.get("columns", []),
                column_types=executed_query_data.get("column_types", []),
                rows=executed_query_data.get("rows", []),
                row_count=executed_query_data.get("row_count", 0),
            )

        total_latency_ms = int((time.time() - start_time) * 1000)

        # 7. Persist Assistant AIMessage
        assistant_message_record = AIMessage(
            conversation_id=conversation.id,
            role="assistant",
            content=final_answer,
            grounding_status="verified" if grounding_result.is_grounded else "failed",
            ungrounded_numbers=[u["token"] for u in grounding_result.unmatched_figures],
            chart_spec=chart_recommendation,
            latency_ms=total_latency_ms,
        )
        session.add(assistant_message_record)
        await session.commit()

        return {
            "conversation_id": str(conversation.id),
            "message_id": str(assistant_message_record.id),
            "answer": final_answer,
            "sql": executed_query_data.get("sql") if executed_query_data else None,
            "columns": executed_query_data.get("columns", []) if executed_query_data else [],
            "column_types": executed_query_data.get("column_types", [])
            if executed_query_data
            else [],
            "rows": executed_query_data.get("rows", []) if executed_query_data else [],
            "row_count": executed_query_data.get("row_count", 0) if executed_query_data else 0,
            "duration_ms": executed_query_data.get("duration_ms", 0) if executed_query_data else 0,
            "grounding": grounding_result.to_dict(),
            "recommended_chart": chart_recommendation,
            "steps": steps,
            "latency_ms": total_latency_ms,
        }
