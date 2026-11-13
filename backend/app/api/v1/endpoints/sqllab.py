"""SQL Lab Execution and Saved Queries Router."""

import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_db_session, require_permission
from app.connectors.factory import get_connector
from app.core.errors import NotFoundError, PermissionDeniedError
from app.db.models import DatabaseConnection, QueryHistory, SavedQuery, User
from app.query.jinja import render_template_sql
from app.query.validator import validate_and_format_sql

router = APIRouter(prefix="/sqllab", tags=["SQL Lab"])


class SQLExecuteRequest(BaseModel):
    database_id: uuid.UUID
    sql: str = Field(..., min_length=1)
    schema_name: str | None = "main"
    parameters: dict[str, Any] = {}
    row_limit: int = 1000


class SavedQueryCreate(BaseModel):
    database_id: uuid.UUID
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    schema_name: str | None = "main"
    sql: str = Field(..., min_length=1)


@router.post("/execute")
async def execute_sql(
    payload: SQLExecuteRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_permission("sqllab:use")),
) -> dict[str, Any]:
    """Validate and execute a SQL query in SQL Lab with limits, timeouts, and history logging."""
    conn_stmt = select(DatabaseConnection).where(
        DatabaseConnection.id == payload.database_id,
        DatabaseConnection.deleted_at.is_(None),
    )
    conn_res = await session.execute(conn_stmt)
    db_conn = conn_res.scalar_one_or_none()
    if not db_conn:
        raise NotFoundError("Database connection not found.")

    if not db_conn.allow_sqllab:
        raise PermissionDeniedError(f"SQL Lab is disabled for connection '{db_conn.name}'.")

    # 1. Render Jinja parameters if any
    rendered_sql = render_template_sql(payload.sql, payload.parameters)

    # 2. Validate and enforce AST Guardrails
    max_limit = min(payload.row_limit, db_conn.row_limit or 10000)
    safe_sql = validate_and_format_sql(
        raw_sql=rendered_sql,
        dialect=db_conn.dialect,
        allow_dml=db_conn.allow_dml,
        row_limit=max_limit,
    )

    # 3. Create initial query history record
    history_record = QueryHistory(
        user_id=current_user.id,
        database_id=db_conn.id,
        sql=safe_sql,
        status="running",
    )
    session.add(history_record)
    await session.commit()
    await session.refresh(history_record)

    # 4. Execute via connector
    connector = get_connector(db_conn)
    start_time = time.time()
    try:
        query_result = connector.execute_query(
            sql=safe_sql,
            limit=max_limit,
            timeout_seconds=db_conn.statement_timeout_seconds or 30,
        )
        duration_ms = query_result.duration_ms

        history_record.status = "success"
        history_record.row_count = query_result.row_count
        history_record.duration_ms = duration_ms
        await session.commit()

        return {
            "query_id": str(history_record.id),
            "status": "success",
            "columns": query_result.columns,
            "column_types": query_result.column_types,
            "rows": query_result.rows,
            "row_count": query_result.row_count,
            "duration_ms": duration_ms,
            "truncated": query_result.truncated,
            "executed_sql": safe_sql,
        }
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        history_record.status = "failed"
        history_record.error_message = str(e)
        history_record.duration_ms = duration_ms
        await session.commit()
        raise


@router.get("/history")
async def get_query_history(
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_permission("sqllab:use")),
) -> dict[str, Any]:
    """Retrieve execution history for SQL Lab."""
    stmt = (
        select(QueryHistory)
        .where(QueryHistory.user_id == current_user.id)
        .order_by(QueryHistory.executed_at.desc())
        .limit(50)
    )
    result = await session.execute(stmt)
    records = result.scalars().all()

    return {
        "data": [
            {
                "id": str(r.id),
                "database_id": str(r.database_id),
                "sql": r.sql,
                "status": r.status,
                "row_count": r.row_count,
                "duration_ms": r.duration_ms,
                "error_message": r.error_message,
                "executed_at": r.executed_at.isoformat() if r.executed_at else None,
            }
            for r in records
        ]
    }


@router.get("/saved")
async def list_saved_queries(
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_permission("sqllab:use")),
) -> dict[str, Any]:
    """List saved queries for the current user."""
    stmt = (
        select(SavedQuery)
        .where(SavedQuery.user_id == current_user.id, SavedQuery.deleted_at.is_(None))
        .order_by(SavedQuery.created_at.desc())
    )
    result = await session.execute(stmt)
    queries = result.scalars().all()

    return {
        "data": [
            {
                "id": str(q.id),
                "database_id": str(q.database_id),
                "title": q.title,
                "description": q.description,
                "schema_name": q.schema_name,
                "sql": q.sql,
                "created_at": q.created_at.isoformat() if q.created_at else None,
            }
            for q in queries
        ]
    }


@router.post("/saved", status_code=status.HTTP_201_CREATED)
async def create_saved_query(
    payload: SavedQueryCreate,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_permission("sqllab:use")),
) -> dict[str, Any]:
    """Save a query in SQL Lab."""
    saved = SavedQuery(
        user_id=current_user.id,
        database_id=payload.database_id,
        title=payload.title,
        description=payload.description,
        schema_name=payload.schema_name,
        sql=payload.sql,
    )
    session.add(saved)
    await session.commit()
    await session.refresh(saved)
    return {"message": "Query saved successfully.", "id": str(saved.id)}


@router.delete("/saved/{id}")
async def delete_saved_query(
    id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_permission("sqllab:use")),
) -> dict[str, str]:
    """Delete a saved query."""
    stmt = select(SavedQuery).where(
        SavedQuery.id == id,
        SavedQuery.user_id == current_user.id,
    )
    result = await session.execute(stmt)
    saved = result.scalar_one_or_none()
    if not saved:
        raise NotFoundError("Saved query not found.")

    await session.delete(saved)
    await session.commit()
    return {"message": "Saved query deleted successfully."}
