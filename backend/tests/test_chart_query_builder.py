"""Unit tests for Chart Query Builder."""
import uuid
import pytest
from app.db.models import Dataset
from app.query.chart_query_builder import build_chart_sql


@pytest.fixture
def sample_dataset():
    return Dataset(
        id=uuid.uuid4(),
        name="Sales Dataset",
        table_name="sales",
        schema_name="main",
        database_id=uuid.uuid4(),
        is_virtual=False,
    )


def test_build_chart_sql_simple_bar(sample_dataset):
    sql = build_chart_sql(
        dataset=sample_dataset,
        dimensions=["region"],
        metrics=[{"label": "total_sales", "expression": "SUM(amount)"}],
        row_limit=50,
        dialect="duckdb",
    )
    assert "SELECT" in sql
    assert "region" in sql
    assert "SUM(amount) AS total_sales" in sql
    assert "GROUP BY" in sql
    assert "LIMIT 50" in sql


def test_build_chart_sql_with_time_grain_and_filter(sample_dataset):
    sql = build_chart_sql(
        dataset=sample_dataset,
        dimensions=["category"],
        metrics=[{"label": "revenue", "expression": "SUM(total_revenue)"}],
        time_column="order_date",
        time_grain="month",
        filters=[
            {"col": "region", "op": "==", "val": "North America"},
            {"col": "units_sold", "op": ">=", "val": 5},
        ],
        row_limit=100,
        dialect="duckdb",
    )
    assert "date_trunc('month', order_date)" in sql.lower()
    assert "region = 'North America'" in sql
    assert "units_sold >= 5" in sql
    assert "LIMIT 100" in sql


def test_build_chart_sql_virtual_dataset():
    virtual_ds = Dataset(
        id=uuid.uuid4(),
        name="Virtual View",
        database_id=uuid.uuid4(),
        is_virtual=True,
        sql_expression="SELECT id, amount, city FROM raw_orders WHERE active = 1",
    )
    sql = build_chart_sql(
        dataset=virtual_ds,
        dimensions=["city"],
        metrics=[{"label": "city_sales", "expression": "SUM(amount)"}],
        row_limit=20,
        dialect="duckdb",
    )
    assert "(SELECT id, amount, city FROM raw_orders WHERE active = 1)" in sql
    assert "city" in sql
    assert "LIMIT 20" in sql
