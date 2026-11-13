"""Celery Async Tasks for Long Queries, Large Uploads, and Export (Phase 5)."""

from typing import Any

from app.connectors.duckdb_connector import DuckDBConnector
from app.workers.celery_app import HAS_CELERY, celery_app

if HAS_CELERY and celery_app:

    @celery_app.task(bind=True, name="execute_async_query_task")  # type: ignore[untyped-decorator]
    def execute_async_query_task(
        self: Any,
        sql: str,
        limit: int = 10000,
        timeout_seconds: int = 120,
    ) -> dict[str, Any]:
        """Execute a long-running analytical query asynchronously in a Celery worker."""
        connector = DuckDBConnector()
        query_res = connector.execute_query(sql, limit=limit, timeout_seconds=timeout_seconds)
        return {
            "status": "completed",
            "columns": query_res.columns,
            "column_types": query_res.column_types,
            "rows": query_res.rows,
            "row_count": query_res.row_count,
            "duration_ms": query_res.duration_ms,
            "truncated": query_res.truncated,
        }

    @celery_app.task(bind=True, name="export_data_csv_task")  # type: ignore[untyped-decorator]
    def export_data_csv_task(
        self: Any,
        sql: str,
        filename: str = "export.csv",
    ) -> dict[str, Any]:
        """Generate a CSV export file asynchronously."""
        connector = DuckDBConnector()
        query_res = connector.execute_query(sql, limit=50000)

        # Convert to CSV formatted string
        import csv
        import io

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(query_res.columns)
        for r in query_res.rows:
            writer.writerow(r)

        return {
            "status": "ready",
            "filename": filename,
            "row_count": query_res.row_count,
            "csv_content": output.getvalue(),
        }
