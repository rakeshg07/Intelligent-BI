"""Datasets Semantic Layer API Endpoints."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.deps import get_db_session, require_permission
from app.connectors.factory import get_connector
from app.core.errors import NotFoundError
from app.db.models import (
    DatabaseConnection,
    Dataset,
    DatasetColumn,
    DatasetMetric,
    RLSRule,
    User,
)
from app.schemas.dataset import (
    DatasetCreate,
    DatasetMetricBase,
    RLSRuleBase,
)

router = APIRouter(prefix="/datasets", tags=["Datasets"])


@router.get("/")
async def list_datasets(
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_permission("datasets:read")),
) -> Any:
    """List all physical and virtual datasets."""
    stmt = (
        select(Dataset)
        .options(
            selectinload(Dataset.columns),
            selectinload(Dataset.metrics),
            selectinload(Dataset.rls_rules),
        )
        .where(Dataset.deleted_at.is_(None))
        .order_by(Dataset.created_at.desc())
    )
    result = await session.execute(stmt)
    datasets = result.scalars().all()

    # Preload database names
    db_ids = {d.database_id for d in datasets}
    db_stmt = select(DatabaseConnection).where(DatabaseConnection.id.in_(db_ids))
    db_res = await session.execute(db_stmt)
    db_map = {d.id: d.name for d in db_res.scalars().all()}

    output = []
    for d in datasets:
        d_dict = {
            "id": str(d.id),
            "name": d.name,
            "description": d.description,
            "database_id": str(d.database_id),
            "database_name": db_map.get(d.database_id, "Unknown"),
            "schema_name": d.schema_name,
            "table_name": d.table_name,
            "is_virtual": d.is_virtual,
            "sql_expression": d.sql_expression,
            "columns": [
                {
                    "id": str(c.id),
                    "name": c.name,
                    "column_name": c.name,
                    "verbose_name": c.verbose_name or c.name,
                    "data_type": c.data_type,
                    "is_datetime": c.is_datetime,
                    "is_dimension": c.is_dimension,
                    "is_filterable": c.is_filterable,
                    "is_groupable": c.is_groupable,
                    "is_hidden_from_ai": c.is_hidden_from_ai,
                    "description": c.description,
                }
                for c in (d.columns or [])
            ],
            "metrics": [
                {
                    "id": str(m.id),
                    "name": m.name,
                    "metric_name": m.name,
                    "verbose_name": m.verbose_name or m.name,
                    "sql_expression": m.sql_expression,
                    "metric_type": m.metric_type,
                    "number_format": m.number_format,
                    "description": m.description,
                }
                for m in (d.metrics or [])
            ],
            "columns_count": len(d.columns or []),
            "metrics_count": len(d.metrics or []),
            "rls_rules_count": len(d.rls_rules or []),
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        output.append(d_dict)

    return output


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_dataset(
    payload: DatasetCreate,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_permission("datasets:write")),
) -> Any:
    """Create a dataset. If physical, automatically inspects source table to populate columns."""
    conn_stmt = select(DatabaseConnection).where(
        DatabaseConnection.id == payload.database_id,
        DatabaseConnection.deleted_at.is_(None),
    )
    conn_res = await session.execute(conn_stmt)
    db_conn = conn_res.scalar_one_or_none()
    if not db_conn:
        raise NotFoundError("Associated database connection not found.")

    dataset = Dataset(
        name=payload.name,
        description=payload.description,
        database_id=payload.database_id,
        schema_name=payload.schema_name or "main",
        table_name=payload.table_name,
        is_virtual=payload.is_virtual,
        sql_expression=payload.sql_expression,
        created_by_id=current_user.id,
    )
    session.add(dataset)
    await session.flush()

    # If physical table, auto-populate columns from source schema
    if not payload.is_virtual and payload.table_name:
        try:
            connector = get_connector(db_conn)
            cols = connector.get_columns(
                table_name=payload.table_name,
                schema_name=payload.schema_name or "main",
            )
            for c in cols:
                c_type = c.data_type.upper()
                is_dt = "TIME" in c_type or "DATE" in c_type
                is_dim = not any(
                    t in c_type for t in ("INT", "DOUBLE", "FLOAT", "DECIMAL", "NUMERIC")
                )
                col_record = DatasetColumn(
                    dataset_id=dataset.id,
                    name=c.name,
                    verbose_name=c.name.replace("_", " ").title(),
                    data_type=c.data_type,
                    is_datetime=is_dt,
                    is_dimension=is_dim,
                    is_filterable=True,
                    is_groupable=True,
                    is_hidden_from_ai=False,
                )
                session.add(col_record)
        except Exception:
            # Continue even if automatic inspection encounters an issue
            pass

    await session.commit()
    await session.refresh(dataset)
    return {"message": "Dataset created successfully.", "id": str(dataset.id), "name": dataset.name}


@router.get("/{id}")
async def get_dataset(
    id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_permission("datasets:read")),
) -> Any:
    """Get complete dataset definition with columns, metrics, and RLS rules."""
    stmt = (
        select(Dataset)
        .options(
            selectinload(Dataset.columns),
            selectinload(Dataset.metrics),
            selectinload(Dataset.rls_rules),
        )
        .where(Dataset.id == id, Dataset.deleted_at.is_(None))
    )
    result = await session.execute(stmt)
    dataset = result.scalar_one_or_none()
    if not dataset:
        raise NotFoundError("Dataset not found.")

    conn_stmt = select(DatabaseConnection).where(DatabaseConnection.id == dataset.database_id)
    conn_res = await session.execute(conn_stmt)
    db_conn = conn_res.scalar_one_or_none()

    return {
        "id": str(dataset.id),
        "name": dataset.name,
        "description": dataset.description,
        "database_id": str(dataset.database_id),
        "database_name": db_conn.name if db_conn else "Unknown",
        "schema_name": dataset.schema_name,
        "table_name": dataset.table_name,
        "is_virtual": dataset.is_virtual,
        "sql_expression": dataset.sql_expression,
        "columns": [
            {
                "id": str(c.id),
                "name": c.name,
                "verbose_name": c.verbose_name,
                "data_type": c.data_type,
                "is_datetime": c.is_datetime,
                "is_dimension": c.is_dimension,
                "is_filterable": c.is_filterable,
                "is_groupable": c.is_groupable,
                "is_hidden_from_ai": c.is_hidden_from_ai,
                "description": c.description,
            }
            for c in dataset.columns
        ],
        "metrics": [
            {
                "id": str(m.id),
                "name": m.name,
                "verbose_name": m.verbose_name,
                "sql_expression": m.sql_expression,
                "metric_type": m.metric_type,
                "number_format": m.number_format,
                "description": m.description,
            }
            for m in dataset.metrics
        ],
        "rls_rules": [
            {
                "id": str(r.id),
                "role_id": str(r.role_id),
                "clause": r.clause,
                "description": r.description,
                "is_active": r.is_active,
            }
            for r in dataset.rls_rules
        ],
    }


@router.delete("/{id}")
async def delete_dataset(
    id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_permission("datasets:write")),
) -> dict[str, str]:
    """Delete a semantic dataset."""
    stmt = select(Dataset).where(Dataset.id == id, Dataset.deleted_at.is_(None))
    result = await session.execute(stmt)
    dataset = result.scalar_one_or_none()
    if not dataset:
        raise NotFoundError("Dataset not found.")

    await session.delete(dataset)
    await session.commit()
    return {"message": "Dataset deleted successfully."}


@router.post("/{id}/metrics", status_code=status.HTTP_201_CREATED)
async def add_dataset_metric(
    id: uuid.UUID,
    payload: DatasetMetricBase,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_permission("datasets:write")),
) -> dict[str, Any]:
    """Add a calculated aggregation metric to the dataset."""
    stmt = select(Dataset).where(Dataset.id == id, Dataset.deleted_at.is_(None))
    result = await session.execute(stmt)
    dataset = result.scalar_one_or_none()
    if not dataset:
        raise NotFoundError("Dataset not found.")

    metric = DatasetMetric(
        dataset_id=dataset.id,
        name=payload.name,
        verbose_name=payload.verbose_name or payload.name.replace("_", " ").title(),
        sql_expression=payload.sql_expression,
        metric_type=payload.metric_type,
        number_format=payload.number_format,
        description=payload.description,
    )
    session.add(metric)
    await session.commit()
    await session.refresh(metric)
    return {"message": "Metric created successfully.", "id": str(metric.id)}


@router.delete("/{id}/metrics/{metric_id}")
async def delete_dataset_metric(
    id: uuid.UUID,
    metric_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_permission("datasets:write")),
) -> dict[str, str]:
    """Delete a metric from a dataset."""
    stmt = select(DatasetMetric).where(
        DatasetMetric.id == metric_id,
        DatasetMetric.dataset_id == id,
    )
    result = await session.execute(stmt)
    metric = result.scalar_one_or_none()
    if not metric:
        raise NotFoundError("Metric not found.")

    await session.delete(metric)
    await session.commit()
    return {"message": "Metric deleted successfully."}


@router.post("/{id}/rls", status_code=status.HTTP_201_CREATED)
async def add_dataset_rls_rule(
    id: uuid.UUID,
    payload: RLSRuleBase,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_permission("datasets:write")),
) -> dict[str, Any]:
    """Add a row-level security rule to the dataset."""
    stmt = select(Dataset).where(Dataset.id == id, Dataset.deleted_at.is_(None))
    result = await session.execute(stmt)
    dataset = result.scalar_one_or_none()
    if not dataset:
        raise NotFoundError("Dataset not found.")

    rule = RLSRule(
        dataset_id=dataset.id,
        role_id=payload.role_id,
        clause=payload.clause,
        description=payload.description,
        is_active=payload.is_active,
    )
    session.add(rule)
    await session.commit()
    await session.refresh(rule)
    return {"message": "RLS rule created successfully.", "id": str(rule.id)}
