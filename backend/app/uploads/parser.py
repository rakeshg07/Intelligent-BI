"""File Parsing, Column Sanitization, and Schema Inference Engine."""

import io
import re
from typing import Any

import pandas as pd

from app.core.errors import AppException


def sanitize_column_name(name: str) -> str:
    """Sanitize column name to valid SQL identifier."""
    # Convert spaces and hyphens to underscores first
    clean = re.sub(r"[\s\-]+", "_", str(name).strip().lower())
    # Remove any non-alphanumeric/non-underscore characters
    clean = re.sub(r"[^\w]", "", clean).strip("_")
    if not clean or clean[0].isdigit():
        clean = f"col_{clean}"
    return clean


def infer_duckdb_type(dtype: str, sample_series: pd.Series) -> str:
    """Map pandas dtype and series contents to DuckDB SQL types."""
    dtype_str = str(dtype).lower()
    if "int" in dtype_str:
        return "BIGINT"
    elif "float" in dtype_str:
        return "DOUBLE"
    elif "bool" in dtype_str:
        return "BOOLEAN"
    elif "datetime" in dtype_str:
        return "TIMESTAMP"
    else:
        # Check if strings are parseable as datetimes
        non_null = sample_series.dropna()
        if len(non_null) > 0 and len(non_null) <= 100:
            try:
                pd.to_datetime(non_null)
                return "TIMESTAMP"
            except Exception:
                pass
        return "VARCHAR"


def parse_file_preview(
    content: bytes,
    filename: str,
    max_rows: int = 100,
) -> tuple[str, list[dict[str, str]], list[dict[str, Any]], int]:
    """Parse file preview and infer column types."""
    ext = filename.lower().split(".")[-1] if "." in filename else ""

    try:
        if ext in ("csv", "txt"):
            # Try comma delimiter, then sniff or fallback
            try:
                df = pd.read_csv(io.BytesIO(content), nrows=max_rows)
            except Exception:
                df = pd.read_csv(io.BytesIO(content), sep=None, engine="python", nrows=max_rows)
            file_format = "csv"
        elif ext == "tsv":
            df = pd.read_csv(io.BytesIO(content), sep="\t", nrows=max_rows)
            file_format = "tsv"
        elif ext in ("xlsx", "xls"):
            df = pd.read_excel(io.BytesIO(content), nrows=max_rows)
            file_format = "xlsx"
        elif ext == "parquet":
            df = pd.read_parquet(io.BytesIO(content))
            df = df.head(max_rows)
            file_format = "parquet"
        elif ext in ("json", "jsonl"):
            try:
                df = pd.read_json(io.BytesIO(content), lines=True, nrows=max_rows)
            except Exception:
                df = pd.read_json(io.BytesIO(content))
                df = df.head(max_rows)
            file_format = "json"
        else:
            raise AppException(
                f"Unsupported file format '.{ext}'. Supported: CSV, TSV, XLSX, Parquet, JSON."
            )
    except AppException:
        raise
    except Exception as e:
        raise AppException(f"Failed to read file preview: {str(e)}") from e

    original_columns = list(df.columns)
    sanitized_columns = [sanitize_column_name(c) for c in original_columns]
    df.columns = sanitized_columns

    column_meta = []
    for col in sanitized_columns:
        duck_type = infer_duckdb_type(str(df[col].dtype), df[col])
        column_meta.append(
            {
                "name": col,
                "type": duck_type,
                "original_name": str(original_columns[sanitized_columns.index(col)]),
            }
        )

    # Prepare JSON serializable preview rows as dicts for UI table rendering
    preview_rows: list[dict[str, Any]] = []
    for _, row in df.head(max_rows).iterrows():
        row_dict: dict[str, Any] = {}
        for col in sanitized_columns:
            val = row[col]
            if pd.isna(val):
                row_dict[col] = None
            elif hasattr(val, "isoformat"):
                row_dict[col] = val.isoformat()
            elif isinstance(val, (int, float, str, bool)):
                row_dict[col] = val
            else:
                row_dict[col] = str(val)
        preview_rows.append(row_dict)

    return file_format, column_meta, preview_rows, len(df)
