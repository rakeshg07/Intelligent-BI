"""File Uploads and DuckDB Ingestion Router."""

import json
import uuid
from typing import Any

import duckdb
from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_db_session, require_permission
from app.connectors.duckdb_connector import duckdb_write_lock
from app.core.config import settings
from app.core.errors import AppException, NotFoundError
from app.db.models import UploadedFile, User
from app.uploads.duckdb_loader import load_file_into_duckdb_and_register_dataset
from app.uploads.parser import parse_file_preview, sanitize_column_name

router = APIRouter(prefix="/uploads", tags=["Uploads"])


@router.post("/preview")
async def preview_upload_file(
    file: UploadFile = File(...),
    current_user: User = Depends(require_permission("uploads:use")),
) -> dict[str, Any]:
    """Parse uploaded file and return inferred columns, types, and first 100 rows."""
    content = await file.read()
    filename = file.filename or "uploaded_data.csv"

    # Check file size limit
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise AppException(
            f"File exceeds maximum allowed size of {settings.MAX_UPLOAD_SIZE_MB} MB."
        )

    file_format, columns, rows, count = parse_file_preview(content, filename, max_rows=100)
    suggested_table = sanitize_column_name(filename.rsplit(".", 1)[0])

    return {
        "filename": filename,
        "format": file_format,
        "size_bytes": len(content),
        "suggested_table_name": suggested_table,
        "columns": columns,
        "preview_rows": rows,
        "preview_count": count,
    }


@router.post("/import", status_code=status.HTTP_201_CREATED)
async def import_upload_file(
    file: UploadFile = File(...),
    table_name: str = Form(...),
    conflict_mode: str = Form("replace"),  # fail, replace, append
    column_types: str | None = Form(None),  # JSON string of {col_name: target_type}
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_permission("uploads:use")),
) -> dict[str, Any]:
    """Ingest file directly into DuckDB and create queryable Dataset."""
    content = await file.read()
    filename = file.filename or "data.csv"

    type_overrides = None
    if column_types:
        try:
            type_overrides = json.loads(column_types)
        except Exception:
            type_overrides = None

    dataset = await load_file_into_duckdb_and_register_dataset(
        session=session,
        content=content,
        filename=filename,
        table_name=table_name,
        column_type_overrides=type_overrides,
        conflict_mode=conflict_mode,
        user=current_user,
    )

    return {
        "message": f"Table '{dataset.table_name}' successfully imported into DuckDB.",
        "dataset_id": str(dataset.id),
        "dataset_name": dataset.name,
        "table_name": dataset.table_name,
        "columns_count": len(dataset.columns)
        if hasattr(dataset, "columns") and dataset.columns
        else 0,
    }


@router.get("/")
async def list_uploads(
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_permission("uploads:use")),
) -> dict[str, Any]:
    """List uploaded files."""
    stmt = (
        select(UploadedFile)
        .where(UploadedFile.deleted_at.is_(None))
        .order_by(UploadedFile.created_at.desc())
    )
    result = await session.execute(stmt)
    files = result.scalars().all()
    return {
        "data": [
            {
                "id": str(f.id),
                "filename": f.filename,
                "original_name": f.original_name,
                "file_format": f.file_format,
                "file_size_bytes": f.file_size_bytes,
                "table_name": f.target_table_name,
                "total_rows": f.total_rows,
                "total_columns": f.total_columns,
                "status": f.status,
                "created_at": f.created_at.isoformat() if f.created_at else None,
            }
            for f in files
        ]
    }


@router.delete("/{id}")
async def delete_upload(
    id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_permission("uploads:use")),
) -> dict[str, str]:
    """Delete uploaded file record and drop table in DuckDB."""
    stmt = select(UploadedFile).where(UploadedFile.id == id, UploadedFile.deleted_at.is_(None))
    result = await session.execute(stmt)
    file_record = result.scalar_one_or_none()
    if not file_record:
        raise NotFoundError("Upload record not found.")

    # Drop table in DuckDB
    table_name = file_record.target_table_name
    db_path = settings.DUCKDB_DATABASE_PATH
    with duckdb_write_lock:
        conn = duckdb.connect(db_path, read_only=False)
        try:
            conn.execute(f"DROP TABLE IF EXISTS {table_name}")
        finally:
            conn.close()

    await session.delete(file_record)
    await session.commit()
    return {"message": f"File and table '{table_name}' deleted successfully."}
