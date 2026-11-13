"""Tests for Connectors Layer (DuckDB and SQLite)."""

import os
import sqlite3
import tempfile

import duckdb
import pytest

from app.connectors.duckdb_connector import DuckDBConnector
from app.connectors.sql_connector import SQLAlchemyConnector


@pytest.fixture
def temp_duckdb_file():
    fd, path = tempfile.mkstemp(suffix=".duckdb")
    os.close(fd)
    if os.path.exists(path):
        os.remove(path)
    conn = duckdb.connect(path, read_only=False)
    conn.execute("CREATE TABLE products (id INTEGER, name VARCHAR, price DOUBLE);")
    conn.execute("INSERT INTO products VALUES (1, 'Widget', 19.99), (2, 'Gadget', 49.99);")
    conn.close()
    yield path
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


@pytest.fixture
def temp_sqlite_file():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT, active INTEGER);")
    cur.execute("INSERT INTO users VALUES (1, 'alice@example.com', 1), (2, 'bob@example.com', 0);")
    conn.commit()
    conn.close()
    yield path
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


def test_duckdb_connector(temp_duckdb_file):
    connector = DuckDBConnector(db_path=temp_duckdb_file)
    ok, msg = connector.test_connection()
    assert ok is True

    schemas = connector.get_schemas()
    assert "main" in schemas

    tables = connector.get_tables("main")
    assert "products" in tables

    columns = connector.get_columns("products", "main")
    col_names = [c.name for c in columns]
    assert "id" in col_names
    assert "name" in col_names
    assert "price" in col_names

    res = connector.execute_query("SELECT id, name, price FROM products ORDER BY id")
    assert res.row_count == 2
    assert res.columns == ["id", "name", "price"]
    # rows is list of lists
    assert res.rows[0][1] == "Widget"
    assert res.rows[1][2] == 49.99


def test_sqlite_connector(temp_sqlite_file):
    uri = f"sqlite:///{temp_sqlite_file.replace(os.sep, '/')}"
    connector = SQLAlchemyConnector(uri=uri)
    ok, msg = connector.test_connection()
    assert ok is True

    tables = connector.get_tables()
    assert "users" in tables

    columns = connector.get_columns("users")
    col_names = [c.name for c in columns]
    assert "email" in col_names

    res = connector.execute_query("SELECT id, email, active FROM users WHERE active = 1")
    assert res.row_count == 1
    assert res.columns == ["id", "email", "active"]
    assert res.rows[0][1] == "alice@example.com"
