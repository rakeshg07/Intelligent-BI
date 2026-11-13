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
    "hour": "hour",
    "day": "day",
    "week": "week",
    "month": "month",
    "quarter": "quarter",
    "year": "year",
}


RESERVED_KEYWORDS = {
    "select", "from", "where", "group", "order", "by", "limit", "as", "join",
    "on", "in", "is", "not", "null", "and", "or", "case", "when", "then",
    "else", "end", "table", "user", "primary", "foreign", "key", "check"
}


def quote_identifier(ident: str) -> str:
    """Safely quote a SQL identifier (column/table) only when needed."""
    cleaned = ident.strip()
    if not cleaned or cleaned == "*":
        return cleaned
    if cleaned.startswith('"') and cleaned.endswith('"'):
        return cleaned
    if "(" in cleaned or " " in cleaned and any(kw in cleaned.upper() for kw in ("AS ", "OVER ", "CASE ", "THEN ", "ELSE ", "END")):
        # It's an expression or complex clause, do not quote
        return cleaned
    if "." in cleaned:
        parts = cleaned.split(".")
        return ".".join(quote_identifier(p) for p in parts)
    # If it's a standard alphanumeric identifier and not a reserved keyword, leave unquoted
    if re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", cleaned) and cleaned.lower() not in RESERVED_KEYWORDS:
        return cleaned
    safe = cleaned.replace('"', '""')
    return f'"{safe}"'


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
        schema_prefix = f"{quote_identifier(dataset.schema_name)}." if dataset.schema_name else ""
        from_clause = f"{schema_prefix}{quote_identifier(source_table)}"

    select_items: List[str] = []
    group_by_items: List[str] = []

    # 1. Handle Time Dimension with grain
    if time_column and time_grain:
        norm_grain = TIME_GRAIN_MAP.get(time_grain.lower(), "day")
        time_col_quoted = quote_identifier(time_column)
        clean_time_alias = re.sub(r"[^a-zA-Z0-9_]+", "_", str(time_column)).strip("_").lower() or "time_col"
        alias = f"{clean_time_alias}_{norm_grain}"
        time_expr = f"date_trunc('{norm_grain}', {time_col_quoted}) AS {quote_identifier(alias)}"
        select_items.append(time_expr)
        group_by_items.append(quote_identifier(alias))
    elif time_column:
        time_col_quoted = quote_identifier(time_column)
        select_items.append(time_col_quoted)
        group_by_items.append(time_col_quoted)

    # 2. Add regular dimensions
    for dim in dimensions:
        if not dim:
            continue
        dim_quoted = quote_identifier(dim)
        if dim_quoted not in select_items and dim not in select_items:
            select_items.append(dim_quoted)
            group_by_items.append(dim_quoted)

    # 3. Add metrics (aggregations)
    for m in metrics:
        expr = m.get("expression") or m.get("sql_expression")
        raw_label = m.get("name") or m.get("label") or "metric"
        clean_alias = re.sub(r"[^a-zA-Z0-9_]+", "_", str(raw_label)).strip("_").lower() or "metric"
        if expr:
            select_items.append(f"{expr} AS {quote_identifier(clean_alias)}")

    # Fallback if no select items
    if not select_items:
        select_items.append("*")

    # 4. Build WHERE clauses from filters
    where_clauses: List[str] = []

    # Time range filter
    if time_column and time_range:
        time_col_quoted = quote_identifier(time_column)
        start_date = time_range.get("start")
        end_date = time_range.get("end")
        if start_date:
            where_clauses.append(f"{time_col_quoted} >= '{start_date}'")
        if end_date:
            where_clauses.append(f"{time_col_quoted} <= '{end_date}'")

    # Ad-hoc filters
    if filters:
        for f in filters:
            col = f.get("col")
            op = (f.get("op") or "==").strip()
            val = f.get("val")

            if not col:
                continue

            col_quoted = quote_identifier(col)

            if op in ("==", "="):
                if isinstance(val, (int, float)):
                    where_clauses.append(f"{col_quoted} = {val}")
                else:
                    where_clauses.append(f"{col_quoted} = '{val}'")
            elif op == "!=":
                if isinstance(val, (int, float)):
                    where_clauses.append(f"{col_quoted} != {val}")
                else:
                    where_clauses.append(f"{col_quoted} != '{val}'")
            elif op in (">", ">=", "<", "<="):
                where_clauses.append(f"{col_quoted} {op} {val}")
            elif op.upper() == "IN" and isinstance(val, list):
                val_list = ", ".join(f"'{v}'" if isinstance(v, str) else str(v) for v in val)
                where_clauses.append(f"{col_quoted} IN ({val_list})")
            elif op.upper() == "NOT IN" and isinstance(val, list):
                val_list = ", ".join(f"'{v}'" if isinstance(v, str) else str(v) for v in val)
                where_clauses.append(f"{col_quoted} NOT IN ({val_list})")
            elif op.upper() == "LIKE":
                where_clauses.append(f"{col_quoted} LIKE '{val}'")
            elif op.upper() == "IS NULL":
                where_clauses.append(f"{col_quoted} IS NULL")
            elif op.upper() == "IS NOT NULL":
                where_clauses.append(f"{col_quoted} IS NOT NULL")

    # 5. Assemble SQL string
    query_parts = [f"SELECT {', '.join(select_items)}", f"FROM {from_clause}"]

    if where_clauses:
        query_parts.append(f"WHERE {' AND '.join(where_clauses)}")

    if group_by_items and metrics:
        query_parts.append(f"GROUP BY {', '.join(group_by_items)}")

    # 6. ORDER BY
    if order_by:
        order_clauses = [
            f"{quote_identifier(o.get('col', '1')) if not o.get('col', '1').isdigit() else o.get('col', '1')} {o.get('direction', 'ASC').upper()}"
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
        query_parts.append(f"ORDER BY {quote_identifier(clean_alias)} DESC")

    raw_sql = " ".join(query_parts)

    # 7. Validate and format through AST guardrail
    safe_sql = validate_and_format_sql(
        raw_sql=raw_sql,
        dialect=dialect,
        allow_dml=False,
        row_limit=row_limit,
    )
    return safe_sql

