"""Unit tests for AI SQL Security Guardrail."""

import pytest

from app.ai.guardrails.sql_guard import AISQLGuard
from app.core.errors import ValidationError


def test_ai_sql_guard_valid_select():
    sql = "SELECT category, SUM(total_revenue) AS revenue FROM global_sales GROUP BY category"
    validated = AISQLGuard.validate_and_constrain(sql, dialect="duckdb", max_rows=500)
    assert "SELECT" in validated
    assert "LIMIT 500" in validated.upper()


def test_ai_sql_guard_preserves_lower_limit():
    sql = "SELECT * FROM global_sales LIMIT 50"
    validated = AISQLGuard.validate_and_constrain(sql, dialect="duckdb", max_rows=500)
    assert "LIMIT 50" in validated.upper()


def test_ai_sql_guard_caps_excessive_limit():
    sql = "SELECT * FROM global_sales LIMIT 50000"
    validated = AISQLGuard.validate_and_constrain(sql, dialect="duckdb", max_rows=250)
    assert "LIMIT 250" in validated.upper()


def test_ai_sql_guard_blocks_dml_and_ddl():
    # DROP
    with pytest.raises(ValidationError, match="only permitted to execute SELECT"):
        AISQLGuard.validate_and_constrain("DROP TABLE global_sales")

    # DELETE
    with pytest.raises(ValidationError, match="only permitted to execute SELECT"):
        AISQLGuard.validate_and_constrain("DELETE FROM global_sales WHERE 1=1")

    # INSERT
    with pytest.raises(ValidationError, match="only permitted to execute SELECT"):
        AISQLGuard.validate_and_constrain("INSERT INTO global_sales VALUES (1, 2, 3)")

    # UPDATE
    with pytest.raises(ValidationError, match="only permitted to execute SELECT"):
        AISQLGuard.validate_and_constrain("UPDATE global_sales SET revenue = 0")


def test_ai_sql_guard_allowed_tables():
    sql = "SELECT * FROM secret_financials"
    with pytest.raises(ValidationError, match="unauthorized table"):
        AISQLGuard.validate_and_constrain(
            sql,
            allowed_tables={"global_sales", "customers"},
        )
