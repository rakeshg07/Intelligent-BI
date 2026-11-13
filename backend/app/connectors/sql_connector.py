"""Generic SQLAlchemy Database Connector (Postgres, MySQL, SQLite, MSSQL, ClickHouse)."""

import time
from typing import Any

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from app.connectors.base import BaseConnector, ColumnMetadata, QueryResult
from app.core.errors import AppException


class SQLAlchemyConnector(BaseConnector):
    """Connector using SQLAlchemy Engine and Inspector for generic relational engines."""

    def __init__(self, uri: str, statement_timeout_seconds: int = 30):
        self.uri = uri
        self.timeout_seconds = statement_timeout_seconds
        self._engine: Engine | None = None

    def _get_engine(self) -> Engine:
        if self._engine is None:
            engine_args: dict[str, Any] = {
                "pool_pre_ping": True,
            }
            if "sqlite" in self.uri:
                engine_args["connect_args"] = {"check_same_thread": False}
            self._engine = create_engine(self.uri, **engine_args)
        return self._engine

    def test_connection(self) -> tuple[bool, str]:
        try:
            engine = self._get_engine()
            with engine.connect() as conn:
                res = conn.execute(text("SELECT 1"))
                if res.scalar() == 1:
                    return True, "Connection successful."
            return False, "Database connected but test query returned unexpected result."
        except Exception as e:
            return False, f"Connection failed: {str(e)}"

    def get_schemas(self) -> list[str]:
        try:
            engine = self._get_engine()
            inspector = inspect(engine)
            schemas = inspector.get_schema_names()
            # Filter standard system schemas
            filtered = [
                s for s in schemas if s not in ("information_schema", "pg_catalog", "pg_toast")
            ]
            return filtered if filtered else ["public"]
        except Exception:
            return ["public"]

    def get_tables(self, schema_name: str | None = None) -> list[str]:
        try:
            engine = self._get_engine()
            inspector = inspect(engine)
            schema = schema_name or ("public" if "postgres" in self.uri else None)
            tables = inspector.get_table_names(schema=schema)
            views = inspector.get_view_names(schema=schema)
            return sorted(set(tables + views))
        except Exception as e:
            raise AppException(f"Failed to fetch tables: {str(e)}") from e

    def get_columns(self, table_name: str, schema_name: str | None = None) -> list[ColumnMetadata]:
        try:
            engine = self._get_engine()
            inspector = inspect(engine)
            schema = schema_name or ("public" if "postgres" in self.uri else None)
            columns = inspector.get_columns(table_name, schema=schema)
            return [
                ColumnMetadata(
                    name=col["name"],
                    data_type=str(col["type"]),
                    nullable=col.get("nullable", True),
                    is_primary_key=bool(col.get("primary_key", False)),
                )
                for col in columns
            ]
        except Exception as e:
            raise AppException(
                f"Failed to inspect columns for table '{table_name}': {str(e)}"
            ) from e

    def execute_query(
        self,
        sql: str,
        limit: int = 10000,
        timeout_seconds: int = 30,
    ) -> QueryResult:
        start_time = time.time()
        try:
            engine = self._get_engine()
            with engine.connect() as conn:
                result = conn.execute(text(sql))
                columns = list(result.keys()) if result.returns_rows else []
                raw_rows = result.fetchmany(limit + 1) if result.returns_rows else []

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
                column_types=[
                    str(type(rows[0][i]).__name__) if rows and rows[0][i] is not None else "string"
                    for i in range(len(columns))
                ],
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
