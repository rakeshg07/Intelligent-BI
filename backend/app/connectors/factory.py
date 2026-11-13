"""Connector Factory for Instantiating Database Connectors."""

from app.connectors.base import BaseConnector
from app.connectors.duckdb_connector import DuckDBConnector
from app.connectors.sql_connector import SQLAlchemyConnector
from app.core.security import decrypt_secret
from app.db.models import DatabaseConnection


def build_uri_from_connection(conn: DatabaseConnection) -> str:
    """Build or decrypt SQLAlchemy connection URI."""
    if conn.sqlalchemy_uri_encrypted:
        return decrypt_secret(conn.sqlalchemy_uri_encrypted)

    dialect = (conn.dialect or "").lower()
    user = conn.username or ""
    password = decrypt_secret(conn.password_encrypted) if conn.password_encrypted else ""
    auth = f"{user}:{password}@" if user or password else ""
    host = conn.host or "localhost"
    port = f":{conn.port}" if conn.port else ""
    db = conn.database_name or ""

    if dialect == "postgres" or dialect == "postgresql":
        return f"postgresql://{auth}{host}{port}/{db}"
    elif dialect == "mysql":
        return f"mysql+pymysql://{auth}{host}{port}/{db}"
    elif dialect == "sqlite":
        return f"sqlite:///{db or ':memory:'}"
    elif dialect == "clickhouse":
        return f"clickhouse+connect://{auth}{host}{port}/{db}"
    elif dialect == "mssql":
        return f"mssql+pyodbc://{auth}{host}{port}/{db}?driver=ODBC+Driver+17+for+SQL+Server"
    else:
        # Default fallback
        return f"{dialect}://{auth}{host}{port}/{db}"


def get_connector(conn: DatabaseConnection) -> BaseConnector:
    """Instantiate appropriate connector for DatabaseConnection entity."""
    if conn.is_system or (conn.dialect or "").lower() == "duckdb":
        return DuckDBConnector()

    uri = build_uri_from_connection(conn)
    return SQLAlchemyConnector(
        uri=uri,
        statement_timeout_seconds=conn.statement_timeout_seconds or 30,
    )
