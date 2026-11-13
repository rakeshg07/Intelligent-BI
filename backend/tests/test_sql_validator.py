"""Tests for SQL Validation and AST Guardrails."""

import pytest

from app.core.errors import SQLGuardrailError
from app.query.validator import sanitize_sql_comments, validate_and_format_sql


def test_sanitize_comments():
    raw = "SELECT 1 -- this is a comment\nFROM employees /* block comment */ WHERE id = 1"
    cleaned = sanitize_sql_comments(raw)
    assert "--" not in cleaned
    assert "/*" not in cleaned
    assert "employees" in cleaned


def test_valid_select_queries():
    sql = "SELECT id, name FROM users WHERE active = true"
    formatted = validate_and_format_sql(sql, dialect="postgres", row_limit=100)
    assert "SELECT" in formatted
    assert "LIMIT 100" in formatted


def test_with_select_query():
    sql = "WITH regional_sales AS (SELECT region, SUM(amount) AS total FROM sales GROUP BY region) SELECT * FROM regional_sales"
    formatted = validate_and_format_sql(sql, dialect="postgres", row_limit=50)
    assert "WITH regional_sales AS" in formatted
    assert "LIMIT 50" in formatted


def test_reject_multiple_statements():
    sql = "SELECT 1; DROP TABLE users;"
    with pytest.raises(SQLGuardrailError, match="Multiple SQL statements"):
        validate_and_format_sql(sql, dialect="postgres")


def test_reject_dml_statements():
    dml_queries = [
        "DROP TABLE users",
        "DELETE FROM users WHERE id = 1",
        "UPDATE users SET name = 'hacked'",
        "INSERT INTO users (id) VALUES (1)",
        "ALTER TABLE users ADD COLUMN pass VARCHAR",
    ]
    for q in dml_queries:
        with pytest.raises(SQLGuardrailError):
            validate_and_format_sql(q, dialect="postgres", allow_dml=False)


def test_reject_dangerous_functions():
    dangerous = [
        "SELECT pg_sleep(10)",
        "SELECT pg_read_file('/etc/passwd')",
        "SELECT xp_cmdshell('whoami')",
        "SELECT * FROM read_csv('secret.csv')",
    ]
    for q in dangerous:
        with pytest.raises(SQLGuardrailError, match="Prohibited function"):
            validate_and_format_sql(q, dialect="duckdb")


def test_clamp_limit():
    sql = "SELECT id FROM large_table LIMIT 50000"
    formatted = validate_and_format_sql(sql, dialect="postgres", row_limit=5000)
    assert "LIMIT 5000" in formatted
