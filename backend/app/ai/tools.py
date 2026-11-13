"""AI Assistant Tools (ADR-004 & Phase 4).

Standard tool interfaces and implementations for schema inspection and safe SQL execution.
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai.guardrails.sql_guard import AISQLGuard
from app.connectors.duckdb_connector import DuckDBConnector
from app.connectors.factory import get_connector
from app.core.config import settings
from app.db.models import DatabaseConnection, Dataset, User

# Tool definitions in standard JSON Schema format compatible with OpenAI and Claude
AI_TOOLS_SPEC = [
    {
        "type": "function",
        "function": {
            "name": "list_datasets_and_tables",
            "description": "Lists all available semantic datasets and database tables accessible to the user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "search": {
                        "type": "string",
                        "description": "Optional search filter string for dataset or table names.",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_table_schema",
            "description": "Retrieves the detailed column schema, data types, descriptions, and pre-defined metrics for a table or dataset.",
            "parameters": {
                "type": "object",
                "properties": {
                    "table_name": {
                        "type": "string",
                        "description": "The exact name of the table to inspect (e.g. 'global_sales').",
                    },
                    "dataset_id": {
                        "type": "string",
                        "description": "Optional UUID of the dataset if known.",
                    },
                },
                "required": ["table_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_sql_query",
            "description": "Executes a safe, read-only SELECT query against the user's data and returns the resulting rows, column headers, and execution metrics.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "The read-only SELECT SQL query to execute.",
                    },
                    "database_id": {
                        "type": "string",
                        "description": "Optional UUID of the database connection. If omitted, queries the internal DuckDB analytics engine.",
                    },
                },
                "required": ["sql"],
            },
        },
    },
]


async def tool_list_datasets_and_tables(
    session: AsyncSession,
    user: User,
    search: str | None = None,
    scoped_dataset_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """Execute list_datasets_and_tables tool."""
    stmt = (
        select(Dataset)
        .options(selectinload(Dataset.columns), selectinload(Dataset.metrics))
        .where(Dataset.deleted_at.is_(None))
    )
    if scoped_dataset_id:
        stmt = stmt.where(Dataset.id == scoped_dataset_id)

    res = await session.execute(stmt)
    datasets = res.scalars().all()

    items = []
    for d in datasets:
        if (
            search
            and search.lower() not in d.name.lower()
            and search.lower() not in (d.table_name or "").lower()
        ):
            continue
        items.append(
            {
                "dataset_id": str(d.id),
                "name": d.name,
                "table_name": d.table_name,
                "description": d.description,
                "is_virtual": d.is_virtual,
                "columns": [c.name for c in d.columns if not c.is_hidden_from_ai],
                "metrics": [{"name": m.name, "expression": m.sql_expression} for m in d.metrics],
            }
        )

    # If scoped to a specific dataset, do not leak other raw DuckDB tables
    if scoped_dataset_id:
        raw_tables = [d.table_name for d in datasets if d.table_name]
    else:
        duckdb_connector = DuckDBConnector()
        raw_tables = duckdb_connector.get_tables()

    return {
        "datasets": items,
        "internal_duckdb_tables": raw_tables,
        "count": len(items),
    }


async def tool_get_table_schema(
    session: AsyncSession,
    table_name: str,
    dataset_id: str | None = None,
    allowed_table: str | None = None,
) -> dict[str, Any]:
    """Execute get_table_schema tool with optional dataset scoping."""
    if allowed_table and table_name.strip().lower() != allowed_table.strip().lower():
        return {
            "found": False,
            "error": (
                f"Access restricted: Active dataset scope is restricted to table '{allowed_table}'. "
                f"Table '{table_name}' cannot be accessed in this session."
            ),
        }

    # 1. First check if a registered Dataset exists for this table
    stmt = (
        select(Dataset)
        .options(selectinload(Dataset.columns), selectinload(Dataset.metrics))
        .where(Dataset.deleted_at.is_(None))
    )
    if dataset_id:
        try:
            uid = uuid.UUID(dataset_id)
            stmt = stmt.where(Dataset.id == uid)
        except ValueError:
            stmt = stmt.where(Dataset.table_name == table_name)
    else:
        stmt = stmt.where(Dataset.table_name == table_name)

    res = await session.execute(stmt)
    dataset = res.scalars().first()

    if dataset:
        return {
            "found": True,
            "source_type": "semantic_dataset",
            "dataset_id": str(dataset.id),
            "table_name": dataset.table_name,
            "name": dataset.name,
            "description": dataset.description,
            "columns": [
                {
                    "name": c.name,
                    "type": c.data_type,
                    "is_datetime": c.is_datetime,
                    "is_numeric": any(
                        t in (c.data_type or "").upper()
                        for t in ("INT", "DOUBLE", "FLOAT", "DECIMAL", "NUMERIC")
                    ),
                    "description": c.description,
                }
                for c in dataset.columns
                if not c.is_hidden_from_ai
            ],
            "predefined_metrics": [
                {
                    "name": m.name,
                    "label": m.verbose_name or m.name,
                    "sql_expression": m.sql_expression,
                    "number_format": m.number_format,
                    "description": m.description,
                }
                for m in dataset.metrics
            ],
        }

    # 2. Fall back to inspecting DuckDB table directly (only if not restricted by active scope)
    if allowed_table and table_name.strip().lower() != allowed_table.strip().lower():
        return {
            "found": False,
            "error": f"Access restricted: Table '{table_name}' is not authorized.",
        }

    try:
        duckdb_connector = DuckDBConnector()
        cols = duckdb_connector.get_columns(table_name)
        return {
            "found": True,
            "source_type": "physical_table",
            "table_name": table_name,
            "columns": [
                {"name": c.name, "type": c.data_type, "nullable": c.nullable} for c in cols
            ],
            "predefined_metrics": [],
        }
    except Exception as e:
        return {
            "found": False,
            "error": f"Table '{table_name}' not found: {str(e)}",
        }


async def tool_execute_sql_query(
    session: AsyncSession,
    sql: str,
    database_id: str | None = None,
    max_rows: int = 500,
    allowed_tables: set[str] | None = None,
) -> dict[str, Any]:
    """Execute execute_sql_query tool with full AST security guardrails and optional table isolation."""
    # 1. Enforce AST security constraints
    try:
        validated_sql = AISQLGuard.validate_and_constrain(
            sql=sql,
            dialect="duckdb",
            max_rows=max_rows,
            allowed_tables=allowed_tables,
        )
    except Exception as e:
        return {
            "success": False,
            "error": f"Security Guardrail Violation: {str(e)}",
            "sql": sql,
        }

    # 2. Execute on specified database or default internal DuckDB
    try:
        if database_id:
            try:
                db_uid = uuid.UUID(database_id)
                db_res = await session.execute(
                    select(DatabaseConnection).where(
                        DatabaseConnection.id == db_uid,
                        DatabaseConnection.deleted_at.is_(None),
                    )
                )
                db_conn = db_res.scalar_one_or_none()
                if not db_conn:
                    return {"success": False, "error": f"Database {database_id} not found."}
                connector = get_connector(db_conn)
            except Exception as e:
                return {"success": False, "error": f"Invalid database ID: {str(e)}"}
        else:
            connector = DuckDBConnector()

        result = connector.execute_query(
            sql=validated_sql,
            limit=max_rows,
            timeout_seconds=settings.STATEMENT_TIMEOUT_SECONDS,
        )

        return {
            "success": True,
            "sql": validated_sql,
            "columns": result.columns,
            "column_types": result.column_types,
            "rows": result.rows,
            "row_count": result.row_count,
            "duration_ms": result.duration_ms,
            "truncated": result.truncated,
        }
    except Exception as e:
        return {
            "success": False,
            "sql": validated_sql,
            "error": f"Execution Error: {str(e)}",
        }
