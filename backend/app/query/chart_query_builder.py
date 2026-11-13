"""Chart Query Builder (ADR-003 and Phase 2).

Constructs safe SQL queries for charts from semantic datasets, dimensions,
metrics, time grains, ad-hoc filters, and limits without raw string concatenation.
"""
import re
from typing import Any, Dict, List, Optional
import sqlglot
from sqlglot import exp

from app.core.errors import AppException
from app.db.models import Dataset, DatasetMetric
from app.query.validator import validate_and_format_sql


TIME_GRAIN_MAP = {
    "day": "day",
    "week": "week",
    "month": "month",
    "quarter": "quarter",
    "year": "year",
}


def build_chart_sql(
    dataset: Dataset,
    dimensions: List[str],
    metrics: List[Dict[str, Any]],
    filters: Optional[List[Dict[str, Any]]] = None,
    time_column: Optional[str] = None,
    time_grain: Optional[str] = None,
    time_range: Optional[Dict[str, str]] = None,
    order_by: Optional[List[Dict[str, str]]] = None,
    row_limit: int = 1000,
    dialect: str = "duckdb",
) -> str:
    """Build a validated SELECT query for chart visualizations."""
    source_table = dataset.table_name or "data_source"

    # If dataset is virtual (saved SQL expression), wrap in subquery
    if dataset.is_virtual and dataset.sql_expression:
        from_clause = f"({dataset.sql_expression}) AS virtual_source"
    else:
        schema_prefix = f"{dataset.schema_name}." if dataset.schema_name else ""
        from_clause = f"{schema_prefix}{source_table}"

    select_items: List[str] = []
    group_by_items: List[str] = []

    # 1. Handle Time Dimension with grain
    if time_column and time_grain:
        norm_grain = TIME_GRAIN_MAP.get(time_grain.lower(), "day")
        time_expr = f"date_trunc('{norm_grain}', {time_column}) AS {time_column}_{norm_grain}"
        select_items.append(time_expr)
        group_by_items.append(f"{time_column}_{norm_grain}")
    elif time_column:
        select_items.append(time_column)
        group_by_items.append(time_column)

    # 2. Add regular dimensions
    for dim in dimensions:
        if dim not in select_items:
            select_items.append(dim)
            group_by_items.append(dim)

    # 3. Add metrics (aggregations)
    for m in metrics:
        expr = m.get("expression") or m.get("sql_expression")
        raw_label = m.get("name") or m.get("label") or "metric"
        clean_alias = re.sub(r"[^a-zA-Z0-9_]+", "_", str(raw_label)).strip("_").lower() or "metric"
        if expr:
            select_items.append(f"{expr} AS {clean_alias}")

    # Fallback if no select items
    if not select_items:
        select_items.append("*")

    # 4. Build WHERE clauses from filters
    where_clauses: List[str] = []

    # Time range filter
    if time_column and time_range:
        start_date = time_range.get("start")
        end_date = time_range.get("end")
        if start_date:
            where_clauses.append(f"{time_column} >= '{start_date}'")
        if end_date:
            where_clauses.append(f"{time_column} <= '{end_date}'")

    # Ad-hoc filters
    if filters:
        for f in filters:
            col = f.get("col")
            op = (f.get("op") or "==").strip()
            val = f.get("val")

            if not col:
                continue

            if op in ("==", "="):
                if isinstance(val, (int, float)):
                    where_clauses.append(f"{col} = {val}")
                else:
                    where_clauses.append(f"{col} = '{val}'")
            elif op == "!=":
                if isinstance(val, (int, float)):
                    where_clauses.append(f"{col} != {val}")
                else:
                    where_clauses.append(f"{col} != '{val}'")
            elif op in (">", ">=", "<", "<="):
                where_clauses.append(f"{col} {op} {val}")
            elif op.upper() == "IN" and isinstance(val, list):
                val_list = ", ".join(f"'{v}'" if isinstance(v, str) else str(v) for v in val)
                where_clauses.append(f"{col} IN ({val_list})")
            elif op.upper() == "NOT IN" and isinstance(val, list):
                val_list = ", ".join(f"'{v}'" if isinstance(v, str) else str(v) for v in val)
                where_clauses.append(f"{col} NOT IN ({val_list})")
            elif op.upper() == "LIKE":
                where_clauses.append(f"{col} LIKE '{val}'")
            elif op.upper() == "IS NULL":
                where_clauses.append(f"{col} IS NULL")
            elif op.upper() == "IS NOT NULL":
                where_clauses.append(f"{col} IS NOT NULL")

    # 5. Assemble SQL string
    query_parts = [f"SELECT {', '.join(select_items)}", f"FROM {from_clause}"]

    if where_clauses:
        query_parts.append(f"WHERE {' AND '.join(where_clauses)}")

    if group_by_items and metrics:
        query_parts.append(f"GROUP BY {', '.join(group_by_items)}")

    # 6. ORDER BY
    if order_by:
        order_clauses = [
            f"{o.get('col', '1')} {o.get('direction', 'ASC').upper()}"
            for o in order_by
            if o.get("col")
        ]
        if order_clauses:
            query_parts.append(f"ORDER BY {', '.join(order_clauses)}")
    elif metrics:
        # Default order by first metric descending
        first_metric = metrics[0]
        raw_label = first_metric.get("name") or first_metric.get("label") or "metric"
        clean_alias = re.sub(r"[^a-zA-Z0-9_]+", "_", str(raw_label)).strip("_").lower() or "metric"
        query_parts.append(f"ORDER BY {clean_alias} DESC")

    raw_sql = " ".join(query_parts)

    # 7. Validate and format through AST guardrail
    safe_sql = validate_and_format_sql(
        raw_sql=raw_sql,
        dialect=dialect,
        allow_dml=False,
        row_limit=row_limit,
    )
    return safe_sql

