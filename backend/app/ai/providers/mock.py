"""Deterministic Test / Fallback Provider for Local Offline Testing (ADR-004 & Phase 4)."""

import json
import uuid
from typing import Any

from app.ai.providers.base import BaseLLMProvider, LLMMessage, LLMResponse, ToolCall


class MockProvider(BaseLLMProvider):
    """Deterministic local AI provider executing grounded SQL generation without cloud API keys."""

    def __init__(self, model: str = "mock-analyst"):
        super().__init__(model=model, api_key="mock", base_url="local")

    async def generate(
        self,
        messages: list[LLMMessage],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse:
        # Check if the last message is a tool response
        last_msg = messages[-1] if messages else None

        if last_msg and last_msg.role == "tool":
            # Tool has returned executed data! Generate final grounded answer from the real query rows.
            try:
                tool_data = json.loads(last_msg.content or "{}")
            except Exception:
                tool_data = {}

            if not tool_data.get("success", False):
                err = tool_data.get("error", "Unknown query execution failure")
                return LLMResponse(
                    content=f"I encountered an error querying the data: {err}. Please verify table schema.",
                    tool_calls=[],
                    finish_reason="stop",
                    provider="mock",
                    model=self.model,
                )

            columns = tool_data.get("columns", [])
            rows = tool_data.get("rows", [])
            row_count = tool_data.get("row_count", 0)

            if not rows:
                return LLMResponse(
                    content="The query executed successfully but returned 0 rows matching the specified criteria.",
                    tool_calls=[],
                    finish_reason="stop",
                    provider="mock",
                    model=self.model,
                )

            # Synthesize answer using the actual returned figures
            lines = [
                f"### Analysis Results ({row_count} records returned)\n",
                "Based on the verified query results from your dataset:\n",
            ]

            # If single aggregate (e.g. Total Revenue)
            if len(rows) == 1 and len(columns) == 1:
                col_name = columns[0].replace("_", " ").title()
                val = rows[0][0]
                lines.append(
                    f"- **{col_name}**: **${val:,.2f}**"
                    if isinstance(val, (int, float))
                    else f"- **{col_name}**: **{val}**"
                )
            elif len(columns) >= 2:
                # Grouped breakdown (e.g. Category, Revenue)
                for r in rows[:8]:
                    dim_val = str(r[0])
                    metric_val = r[1]
                    if isinstance(metric_val, (int, float)):
                        lines.append(
                            f"- **{dim_val}**: ${metric_val:,.2f}"
                            if "revenue" in columns[1].lower() or "profit" in columns[1].lower()
                            else f"- **{dim_val}**: {metric_val:,}"
                        )
                    else:
                        lines.append(f"- **{dim_val}**: {metric_val}")

            lines.append(
                "\n**Visual Recommendation**: A bar or pie chart provides the clearest visual breakdown for this metric."
            )

            return LLMResponse(
                content="\n".join(lines),
                tool_calls=[],
                finish_reason="stop",
                provider="mock",
                model=self.model,
            )

        # First turn: synthesize a real SQL query based on user prompt
        user_text = ""
        for m in reversed(messages):
            if m.role == "user" and m.content:
                user_text = m.content.lower()
                break

        # Select appropriate query based on user keywords
        if "profit" in user_text:
            sql = "SELECT category, ROUND(SUM(net_profit), 2) AS total_profit FROM global_sales GROUP BY category ORDER BY total_profit DESC"
        elif "region" in user_text:
            sql = "SELECT region, ROUND(SUM(total_revenue), 2) AS revenue FROM global_sales GROUP BY region ORDER BY revenue DESC"
        elif "customer" in user_text:
            sql = "SELECT customer_name, ROUND(SUM(total_revenue), 2) AS total_revenue FROM global_sales GROUP BY customer_name ORDER BY total_revenue DESC LIMIT 5"
        elif "unit" in user_text or "quantity" in user_text:
            sql = "SELECT category, SUM(units_sold) AS total_units FROM global_sales GROUP BY category ORDER BY total_units DESC"
        else:
            # Default aggregate revenue or category breakdown
            if "total" in user_text and "category" not in user_text:
                sql = "SELECT ROUND(SUM(total_revenue), 2) AS total_revenue FROM global_sales"
            else:
                sql = "SELECT category, ROUND(SUM(total_revenue), 2) AS total_revenue FROM global_sales GROUP BY category ORDER BY total_revenue DESC"

        # Return tool call to execute_sql_query
        return LLMResponse(
            content="I will query the dataset to answer your question.",
            tool_calls=[
                ToolCall(
                    id=f"call_{uuid.uuid4().hex[:8]}",
                    name="execute_sql_query",
                    arguments={"sql": sql},
                )
            ],
            finish_reason="tool_calls",
            provider="mock",
            model=self.model,
        )
