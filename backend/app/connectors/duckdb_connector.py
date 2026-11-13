"""DuckDB Analytical Connector for Internal File Storage."""

import os
import threading
import time
from typing import Any

import duckdb

from app.connectors.base import BaseConnector, ColumnMetadata, QueryResult
from app.core.config import settings
from app.core.errors import AppException

# Global single-writer mutex for DuckDB writes
duckdb_write_lock = threading.Lock()


class DuckDBConnector(BaseConnector):
    """DuckDB Connector with read-only concurrent access and locked writes."""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or settings.DUCKDB_DATABASE_PATH
        # Ensure target folder exists
        target_dir = os.path.dirname(self.db_path) or "."
        os.makedirs(target_dir, exist_ok=True)

    def _get_read_connection(self) -> duckdb.DuckDBPyConnection:
        """Create a read-only connection to allow unlimited concurrent readers."""
        if not os.path.exists(self.db_path):
            # Touch / initialize file if brand new
            with duckdb_write_lock:
                init_conn = duckdb.connect(self.db_path, read_only=False)
                init_conn.close()
        return duckdb.connect(self.db_path, read_only=True)

    def test_connection(self) -> tuple[bool, str]:
        conn = None
        try:
            conn = self._get_read_connection()
            res = conn.execute("SELECT 1 AS status").fetchone()
            if res and res[0] == 1:
                return True, "DuckDB engine operational."
            return False, "Unexpected response from DuckDB."
        except Exception as e:
            return False, f"DuckDB connection error: {str(e)}"
        finally:
            if conn is not None:
                conn.close()

    def get_schemas(self) -> list[str]:
        conn = None
        try:
            conn = self._get_read_connection()
            rows = conn.execute(
                "SELECT DISTINCT schema_name FROM information_schema.schemata ORDER BY schema_name"
            ).fetchall()
            unique_schemas = sorted(
                {r[0] for r in rows if r[0] not in ("information_schema", "pg_catalog")}
            )
            return unique_schemas or ["main"]
        except Exception:
            return ["main"]
        finally:
            if conn is not None:
                conn.close()

    def get_tables(self, schema_name: str | None = None) -> list[str]:
        schema = schema_name or "main"
        conn = None
        try:
            conn = self._get_read_connection()
            query = (
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = ? ORDER BY table_name"
            )
            rows = conn.execute(query, [schema]).fetchall()
            return [r[0] for r in rows]
        except Exception as e:
            raise AppException(f"Failed to list tables in schema '{schema}': {str(e)}") from e
        finally:
            if conn is not None:
                conn.close()

    def get_columns(self, table_name: str, schema_name: str | None = None) -> list[ColumnMetadata]:
        schema = schema_name or "main"
        conn = None
        try:
            conn = self._get_read_connection()
            query = """
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = ? AND table_schema = ?
                ORDER BY ordinal_position
            """
            rows = conn.execute(query, [table_name, schema]).fetchall()
            return [
                ColumnMetadata(
                    name=r[0],
                    data_type=str(r[1]),
                    nullable=(str(r[2]).upper() == "YES"),
                )
                for r in rows
            ]
        except Exception as e:
            raise AppException(
                f"Failed to inspect columns for table '{table_name}': {str(e)}"
            ) from e
        finally:
            if conn is not None:
                conn.close()

    def execute_query(
        self,
        sql: str,
        limit: int = 10000,
        timeout_seconds: int = 30,
    ) -> QueryResult:
        start_time = time.time()
        conn = None
        try:
            conn = self._get_read_connection()
            cursor = conn.cursor()

            # Execute query
            cursor.execute(sql)
            description = cursor.description or []
            columns = [col[0] for col in description]
            column_types = [str(col[1]) for col in description]

            # Fetch rows up to limit + 1 to detect truncation
            raw_rows = cursor.fetchmany(limit + 1)

            truncated = len(raw_rows) > limit
            rows = raw_rows[:limit]

            # Format rows for JSON serialization
            formatted_rows: list[list[Any]] = []
            for row in rows:
                formatted_row = []
                for val in row:
                    if hasattr(val, "isoformat"):
                        formatted_row.append(val.isoformat())
                    elif val is None or isinstance(val, (int, float, str, bool)):
                        formatted_row.append(val)
                    else:
                        formatted_row.append(str(val))
                formatted_rows.append(formatted_row)

            duration_ms = int((time.time() - start_time) * 1000)
            return QueryResult(
                columns=columns,
                column_types=column_types,
                rows=formatted_rows,
                row_count=len(formatted_rows),
                duration_ms=duration_ms,
                sql=sql,
                truncated=truncated,
            )
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            raise AppException(
                f"Query execution failed: {str(e)}",
                code="QUERY_EXECUTION_ERROR",
                details={"sql": sql, "duration_ms": duration_ms},
            ) from e
        finally:
            if conn is not None:
                conn.close()
