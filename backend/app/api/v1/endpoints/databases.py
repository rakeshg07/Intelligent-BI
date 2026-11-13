"""Database Connections API Endpoints."""
import uuid
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_db_session, require_permission
from app.connectors.duckdb_connector import DuckDBConnector
from app.connectors.factory import get_connector
from app.connectors.sql_connector import SQLAlchemyConnector
from app.core.errors import ConflictError, NotFoundError, PermissionDeniedError
from app.core.security import encrypt_secret
from app.db.models import DatabaseConnection, User
from app.schemas.database import (
    ConnectionTestRequest,
    ConnectionTestResponse,
    DatabaseConnectionCreate,
    DatabaseConnectionOut,
    DatabaseConnectionUpdate,
)

router = APIRouter(prefix="/databases", tags=["Databases"])


def _mask_connection(conn: DatabaseConnection) -> DatabaseConnectionOut:
    """Mask credentials and return safe DTO."""
    return DatabaseConnectionOut(
        id=conn.id,
        name=conn.name,
        description=conn.description,
        dialect=conn.dialect,
        host=conn.host,
        port=conn.port,
        database_name=conn.database_name,
        username=conn.username,
        ssl_mode=conn.ssl_mode,
        allow_dml=conn.allow_dml,
        allow_file_uploads=conn.allow_file_uploads,
        allow_sqllab=conn.allow_sqllab,
        row_limit=conn.row_limit,
        statement_timeout_seconds=conn.statement_timeout_seconds,
        cache_timeout_seconds=conn.cache_timeout_seconds,
        is_system=conn.is_system,
        ai_allowed_schemas=conn.ai_allowed_schemas or [],
        ai_allowed_tables=conn.ai_allowed_tables or [],
        extra_params=conn.extra_params or {},
        has_encrypted_password=bool(conn.password_encrypted or conn.sqlalchemy_uri_encrypted),
    )


@router.get("/", response_model=List[DatabaseConnectionOut])
async def list_databases(
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_permission("databases:read")),
) -> Any:
    """List all registered database connections."""
    stmt = (
        select(DatabaseConnection)
        .where(DatabaseConnection.deleted_at.is_(None))
        .order_by(DatabaseConnection.is_system.desc(), DatabaseConnection.name.asc())
    )
    result = await session.execute(stmt)
    conns = result.scalars().all()
    return [_mask_connection(c) for c in conns]


@router.post("/", response_model=DatabaseConnectionOut, status_code=status.HTTP_201_CREATED)
async def create_database(
    payload: DatabaseConnectionCreate,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_permission("databases:write")),
) -> Any:
    """Create a new encrypted database connection."""
    existing = await session.execute(
        select(DatabaseConnection).where(
            DatabaseConnection.name == payload.name,
            DatabaseConnection.deleted_at.is_(None),
        )
    )
    if existing.scalar_one_or_none():
        raise ConflictError(f"Database connection with name '{payload.name}' already exists.")

    encrypted_pw = encrypt_secret(payload.password) if payload.password else None
    encrypted_uri = encrypt_secret(payload.raw_uri) if payload.raw_uri else None

    db_conn = DatabaseConnection(
        name=payload.name,
        description=payload.description,
        dialect=payload.dialect.lower(),
        host=payload.host,
        port=payload.port,
        database_name=payload.database_name,
        username=payload.username,
        password_encrypted=encrypted_pw,
        sqlalchemy_uri_encrypted=encrypted_uri,
        ssl_mode=payload.ssl_mode,
        allow_dml=payload.allow_dml,
        allow_file_uploads=payload.allow_file_uploads,
        allow_sqllab=payload.allow_sqllab,
        row_limit=payload.row_limit,
        statement_timeout_seconds=payload.statement_timeout_seconds,
        cache_timeout_seconds=payload.cache_timeout_seconds,
        ai_allowed_schemas=payload.ai_allowed_schemas,
        ai_allowed_tables=payload.ai_allowed_tables,
        extra_params=payload.extra_params,
        created_by_id=current_user.id,
    )
    session.add(db_conn)
    await session.commit()
    await session.refresh(db_conn)
    return _mask_connection(db_conn)


@router.post("/test", response_model=ConnectionTestResponse)
async def test_database_connection(
    payload: ConnectionTestRequest,
    current_user: User = Depends(require_permission("databases:read")),
) -> Any:
    """Test connection credentials without saving."""
    dialect = payload.dialect.lower()
    if dialect == "duckdb":
        connector = DuckDBConnector()
        success, msg = connector.test_connection()
        return ConnectionTestResponse(success=success, message=msg)

    # Build transient URI
    if payload.raw_uri:
        uri = payload.raw_uri
    else:
        user = payload.username or ""
        password = payload.password or ""
        auth = f"{user}:{password}@" if user or password else ""
        host = payload.host or "localhost"
        port = f":{payload.port}" if payload.port else ""
        db = payload.database_name or ""

        if dialect in ("postgres", "postgresql"):
            uri = f"postgresql://{auth}{host}{port}/{db}"
        elif dialect == "mysql":
            uri = f"mysql+pymysql://{auth}{host}{port}/{db}"
        elif dialect == "sqlite":
            uri = f"sqlite:///{db or ':memory:'}"
        elif dialect == "clickhouse":
            uri = f"clickhouse+connect://{auth}{host}{port}/{db}"
        elif dialect == "mssql":
            uri = f"mssql+pyodbc://{auth}{host}{port}/{db}?driver=ODBC+Driver+17+for+SQL+Server"
        else:
            uri = f"{dialect}://{auth}{host}{port}/{db}"

    try:
        sql_connector = SQLAlchemyConnector(uri=uri, statement_timeout_seconds=10)
        success, msg = sql_connector.test_connection()
        return ConnectionTestResponse(success=success, message=msg)
    except Exception as e:
        return ConnectionTestResponse(success=False, message=str(e))


@router.get("/{id}", response_model=DatabaseConnectionOut)
async def get_database(
    id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_permission("databases:read")),
) -> Any:
    """Get connection metadata by ID."""
    stmt = select(DatabaseConnection).where(
        DatabaseConnection.id == id,
        DatabaseConnection.deleted_at.is_(None),
    )
    result = await session.execute(stmt)
    conn = result.scalar_one_or_none()
    if not conn:
        raise NotFoundError("Database connection not found.")
    return _mask_connection(conn)


@router.delete("/{id}", status_code=status.HTTP_200_OK)
async def delete_database(
    id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_permission("databases:write")),
) -> dict[str, str]:
    """Delete a database connection (system connections cannot be deleted)."""
    stmt = select(DatabaseConnection).where(
        DatabaseConnection.id == id,
        DatabaseConnection.deleted_at.is_(None),
    )
    result = await session.execute(stmt)
    conn = result.scalar_one_or_none()
    if not conn:
        raise NotFoundError("Database connection not found.")
    if conn.is_system:
        raise PermissionDeniedError("System connections (e.g. built-in DuckDB 'Uploads') cannot be deleted.")

    await session.delete(conn)
    await session.commit()
    return {"message": "Database connection deleted successfully."}


@router.get("/{id}/schemas")
async def get_database_schemas(
    id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_permission("databases:read")),
) -> List[str]:
    """List schemas in the database."""
    stmt = select(DatabaseConnection).where(
        DatabaseConnection.id == id,
        DatabaseConnection.deleted_at.is_(None),
    )
    result = await session.execute(stmt)
    conn = result.scalar_one_or_none()
    if not conn:
        raise NotFoundError("Database connection not found.")

    connector = get_connector(conn)
    return connector.get_schemas()


@router.get("/{id}/tables")
@router.get("/{id}/schemas/{schema}/tables")
async def get_database_tables(
    id: uuid.UUID,
    schema: Optional[str] = None,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_permission("databases:read")),
) -> List[str]:
    """List tables and views in a schema."""
    stmt = select(DatabaseConnection).where(
        DatabaseConnection.id == id,
        DatabaseConnection.deleted_at.is_(None),
    )
    result = await session.execute(stmt)
    conn = result.scalar_one_or_none()
    if not conn:
        raise NotFoundError("Database connection not found.")

    connector = get_connector(conn)
    return connector.get_tables(schema_name=schema)


@router.get("/{id}/tables/{table}/columns")
@router.get("/{id}/schemas/{schema}/tables/{table}/columns")
async def get_database_columns(
    id: uuid.UUID,
    table: str,
    schema: Optional[str] = None,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_permission("databases:read")),
) -> List[dict[str, Any]]:
    """Inspect columns and data types for a table."""
    stmt = select(DatabaseConnection).where(
        DatabaseConnection.id == id,
        DatabaseConnection.deleted_at.is_(None),
    )
    result = await session.execute(stmt)
    conn = result.scalar_one_or_none()
    if not conn:
        raise NotFoundError("Database connection not found.")

    connector = get_connector(conn)
    columns = connector.get_columns(table_name=table, schema_name=schema)
    return [c.to_dict() for c in columns]
