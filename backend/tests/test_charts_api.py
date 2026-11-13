"""Integration tests for Charts API Endpoints and Validation."""
import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Dataset, DatasetColumn, DatabaseConnection, User


@pytest.mark.asyncio
async def test_chart_data_rejects_numeric_time_column(client: AsyncClient, db_session: AsyncSession):
    # 1. Create a dummy connection, dataset and columns
    conn = DatabaseConnection(
        name="TestDuckDB",
        dialect="duckdb",
        is_system=True,
    )
    db_session.add(conn)
    await db_session.flush()

    ds = Dataset(
        name="Employees Test",
        table_name="employees_test",
        database_id=conn.id,
    )
    db_session.add(ds)
    await db_session.flush()

    col_numeric = DatasetColumn(
        dataset_id=ds.id,
        name="job_rate",
        data_type="DOUBLE",
        is_datetime=False,
        is_dimension=False,
    )
    col_date = DatasetColumn(
        dataset_id=ds.id,
        name="start_date",
        data_type="TIMESTAMP",
        is_datetime=True,
        is_dimension=True,
    )
    col_dept = DatasetColumn(
        dataset_id=ds.id,
        name="department",
        data_type="VARCHAR",
        is_datetime=False,
        is_dimension=True,
    )
    db_session.add_all([col_numeric, col_date, col_dept])
    await db_session.commit()

    # 2. Attempt to query with job_rate as time_column
    response = await client.post(
        "/api/v1/charts/data",
        json={
            "dataset_id": str(ds.id),
            "viz_type": "line",
            "dimensions": ["department"],
            "metrics": [{"name": "count", "expression": "COUNT(*)"}],
            "time_column": "job_rate",
            "time_grain": "week",
        },
    )

    assert response.status_code == 400
    err_json = response.json()
    assert "cannot be used as a Time Column" in err_json.get("message", "")
    assert "DOUBLE" in err_json.get("message", "")

