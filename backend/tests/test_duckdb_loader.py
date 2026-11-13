"""Tests for File Parser and DuckDB Ingestion."""

import io

import pandas as pd

from app.uploads.parser import parse_file_preview, sanitize_column_name


def test_sanitize_column_name():
    assert sanitize_column_name("First Name") == "first_name"
    assert sanitize_column_name("Total Sales ($)") == "total_sales"
    assert sanitize_column_name("123 Count") == "col_123_count"
    assert sanitize_column_name("user-email_address") == "user_email_address"


def test_parse_csv_preview():
    csv_data = b"order_id,customer_name,amount,created_at\n1,Alice,150.50,2026-01-01\n2,Bob,75.00,2026-01-02\n"
    fmt, cols, rows, count = parse_file_preview(csv_data, "orders.csv")

    assert fmt == "csv"
    assert count == 2
    assert len(cols) == 4
    col_names = [c["name"] for c in cols]
    assert "order_id" in col_names
    assert "amount" in col_names
    assert len(rows) == 2
    assert rows[0]["customer_name"] == "Alice"


def test_parse_json_lines_preview():
    json_lines = (
        b'{"id": 1, "product": "Chair", "stock": 10}\n{"id": 2, "product": "Desk", "stock": 5}\n'
    )
    fmt, cols, rows, count = parse_file_preview(json_lines, "inventory.jsonl")

    assert fmt == "json"
    assert count == 2
    assert len(cols) == 3
    assert rows[0]["product"] == "Chair"


def test_parse_parquet_preview():
    df = pd.DataFrame({"metric_id": [101, 102], "score": [98.5, 87.2], "category": ["A", "B"]})
    buf = io.BytesIO()
    df.to_parquet(buf, index=False)
    parquet_bytes = buf.getvalue()

    fmt, cols, rows, count = parse_file_preview(parquet_bytes, "metrics.parquet")
    assert fmt == "parquet"
    assert count == 2
    assert len(cols) == 3
