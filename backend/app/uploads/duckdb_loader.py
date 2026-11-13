"""DuckDB File Loader and Automatic Dataset Registrar."""

import io
import os

import duckdb
import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.connectors.duckdb_connector import duckdb_write_lock
from app.core.config import settings
from app.core.errors import AppException, ConflictError
from app.db.models import DatabaseConnection, Dataset, DatasetColumn, UploadedFile, User
from app.uploads.dashboard_generator import generate_dashboard_for_dataset
from app.uploads.parser import sanitize_column_name


async def load_file_into_duckdb_and_register_dataset(
    session: AsyncSession,
    content: bytes,
    filename: str,
    table_name: str,
    user: User,
    column_type_overrides: dict[str, str] | None = None,
    conflict_mode: str = "replace",  # 'fail', 'replace', 'append'
) -> Dataset:
    """Ingest tabular file into DuckDB under write lock and auto-register Dataset."""
    ext = filename.lower().split(".")[-1] if "." in filename else ""
    table_identifier = sanitize_column_name(table_name)

    # 1. Read full DataFrame
    try:
        if ext in ("csv", "txt"):
            try:
                df = pd.read_csv(io.BytesIO(content))
            except Exception:
                df = pd.read_csv(io.BytesIO(content), sep=None, engine="python")
            file_format = "csv"
        elif ext == "tsv":
            df = pd.read_csv(io.BytesIO(content), sep="\t")
            file_format = "tsv"
        elif ext in ("xlsx", "xls"):
            df = pd.read_excel(io.BytesIO(content))
            file_format = "xlsx"
        elif ext == "parquet":
            df = pd.read_parquet(io.BytesIO(content))
            file_format = "parquet"
        elif ext in ("json", "jsonl"):
            try:
                df = pd.read_json(io.BytesIO(content), lines=True)
            except Exception:
                df = pd.read_json(io.BytesIO(content))
            file_format = "json"
        else:
            raise AppException(f"Unsupported format '.{ext}'")
    except Exception as e:
        raise AppException(f"Failed to parse upload data: {str(e)}") from e

    # Sanitize dataframe column names
    df.columns = [sanitize_column_name(c) for c in df.columns]

    # Apply type overrides if provided
    if column_type_overrides:
        for col, target_type in column_type_overrides.items():
            if col in df.columns:
                try:
                    if target_type.upper() in ("BIGINT", "INTEGER", "INT"):
                        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
                    elif target_type.upper() in ("DOUBLE", "FLOAT", "NUMERIC"):
                        df[col] = pd.to_numeric(df[col], errors="coerce").astype(float)
                    elif target_type.upper() in ("TIMESTAMP", "DATETIME", "DATE"):
                        df[col] = pd.to_datetime(df[col], errors="coerce")
                    elif target_type.upper() == "BOOLEAN":
                        df[col] = df[col].astype(bool)
                    else:
                        df[col] = df[col].astype(str)
                except Exception:
                    pass

    # 2. Acquire writer lock and write to DuckDB
    db_path = settings.DUCKDB_DATABASE_PATH
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)

    with duckdb_write_lock:
        write_conn = duckdb.connect(db_path, read_only=False)
        try:
            # Check existing table
            check_res = write_conn.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?",
                [table_identifier],
            ).fetchall()
            table_exists = bool(check_res and check_res[0][0] > 0)

            if table_exists:
                if conflict_mode == "fail":
                    raise ConflictError(f"Table '{table_identifier}' already exists in DuckDB.")
                elif conflict_mode == "append":
                    write_conn.execute(f"INSERT INTO {table_identifier} SELECT * FROM df")
                else:  # replace
                    write_conn.execute(
                        f"CREATE OR REPLACE TABLE {table_identifier} AS SELECT * FROM df"
                    )
            else:
                write_conn.execute(f"CREATE TABLE {table_identifier} AS SELECT * FROM df")

            # Inspect actual columns in DuckDB
            cols_info = write_conn.execute(f"PRAGMA table_info('{table_identifier}')").fetchall()
            row_count_res = write_conn.execute(
                f"SELECT COUNT(*) FROM {table_identifier}"
            ).fetchall()
            total_rows = row_count_res[0][0] if row_count_res else len(df)
        finally:
            write_conn.close()

    # 3. Locate DuckDB System Connection
    conn_stmt = select(DatabaseConnection).where(DatabaseConnection.name == "Uploads")
    conn_result = await session.execute(conn_stmt)
    uploads_conn = conn_result.scalar_one_or_none()
    if not uploads_conn:
        raise AppException("Built-in DuckDB 'Uploads' connection is not registered.")

    # 4. Record UploadedFile metadata
    file_record = UploadedFile(
        filename=filename,
        original_name=filename,
        file_size_bytes=len(content),
        mime_type=f"application/{file_format}",
        file_format=file_format,
        storage_path=f"duckdb://{table_identifier}",
        target_database_id=uploads_conn.id,
        target_table_name=table_identifier,
        total_rows=total_rows,
        total_columns=len(df.columns),
        status="completed",
        uploaded_by_id=user.id,
    )
    session.add(file_record)

    # 5. Automatically create or update semantic Dataset
    existing_dataset_stmt = select(Dataset).where(
        Dataset.database_id == uploads_conn.id,
        Dataset.table_name == table_identifier,
        Dataset.deleted_at.is_(None),
    )
    existing_dataset_res = await session.execute(existing_dataset_stmt)
    dataset = existing_dataset_res.scalar_one_or_none()

    if not dataset:
        dataset = Dataset(
            name=table_name.replace("_", " ").title(),
            description=f"Auto-generated dataset from uploaded file '{filename}'",
            database_id=uploads_conn.id,
            schema_name="main",
            table_name=table_identifier,
            is_virtual=False,
            created_by_id=user.id,
        )
        session.add(dataset)
        await session.flush()
    else:
        # Clear existing column records if replaced
        if conflict_mode == "replace":
            await session.execute(
                delete(DatasetColumn).where(DatasetColumn.dataset_id == dataset.id)
            )
            await session.flush()

    # Add DatasetColumn records
    created_cols: list[DatasetColumn] = []
    for col_row in cols_info:
        col_name = str(col_row[1])
        col_type = str(col_row[2]).upper()
        is_dt = "TIME" in col_type or "DATE" in col_type
        dataset_col = DatasetColumn(
            dataset_id=dataset.id,
            name=col_name,
            verbose_name=col_name.replace("_", " ").title(),
            data_type=col_type,
            is_datetime=is_dt,
            is_dimension=not any(
                t in col_type for t in ("INT", "DOUBLE", "FLOAT", "DECIMAL", "NUMERIC")
            ),
            is_filterable=True,
            is_groupable=True,
            is_hidden_from_ai=False,
        )
        session.add(dataset_col)
        created_cols.append(dataset_col)

    await session.flush()
    await generate_dashboard_for_dataset(
        session=session,
        dataset=dataset,
        columns=created_cols,
        user=user,
        filename=filename,
    )

    await session.commit()
    refreshed_stmt = (
        select(Dataset)
        .options(selectinload(Dataset.columns), selectinload(Dataset.metrics))
        .where(Dataset.id == dataset.id)
    )
    refreshed_res = await session.execute(refreshed_stmt)
    return refreshed_res.scalar_one()
