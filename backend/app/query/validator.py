"""SQL Validation and AST Guardrails using sqlglot (ADR-003)."""

import re

import sqlglot
from sqlglot import exp

from app.core.errors import SQLGuardrailError

# Blacklisted dangerous functions by pattern
DANGEROUS_FUNCTIONS = {
    # System / file / process calls
    "pg_sleep",
    "pg_read_file",
    "pg_write_file",
    "pg_read_binary_file",
    "lo_import",
    "lo_export",
    "xp_cmdshell",
    "sp_configure",
    "load_extension",
    # DuckDB file reading bypasses
    "read_csv",
    "read_csv_auto",
    "read_parquet",
    "read_json",
    "read_json_auto",
    "scan_parquet",
    "scan_csv",
}


def sanitize_sql_comments(sql: str) -> str:
    """Strip comments to prevent obfuscated payloads."""
    # Remove block comments /* ... */
    no_block = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    # Remove line comments -- ...
    lines = [re.sub(r"--.*$", "", line) for line in no_block.splitlines()]
    return " ".join(lines).strip()


def validate_and_format_sql(
    raw_sql: str,
    dialect: str = "postgres",
    allow_dml: bool = False,
    row_limit: int = 10000,
) -> str:
    """Validate SQL query with AST safety guardrails and enforce row limit."""
    cleaned = sanitize_sql_comments(raw_sql)
    if not cleaned:
        raise SQLGuardrailError("Query is empty.")

    # 1. Parse into AST using sqlglot
    glot_dialect = dialect.lower()
    if glot_dialect in ("postgresql", "postgres"):
        glot_dialect = "postgres"
    elif glot_dialect == "duckdb":
        glot_dialect = "duckdb"
    elif glot_dialect in ("sqlite", "mysql", "clickhouse"):
        glot_dialect = glot_dialect
    else:
        glot_dialect = "postgres"

    try:
        expressions = sqlglot.parse(cleaned, read=glot_dialect)
    except Exception as e:
        raise SQLGuardrailError(f"SQL Syntax Error: {str(e)}") from e

    if not expressions:
        raise SQLGuardrailError("Could not parse query.")

    # 2. Enforce exactly one statement (disallow multi-statement injections)
    if len(expressions) > 1:
        raise SQLGuardrailError("Multiple SQL statements in a single execution are prohibited.")

    ast = expressions[0]
    if ast is None:
        raise SQLGuardrailError("Empty SQL AST.")

    # 3. Permitted root statements
    if not allow_dml:
        is_select = isinstance(ast, exp.Select)
        is_with = isinstance(ast, exp.Expression) and ast.key == "with"
        is_union = isinstance(ast, exp.Union)

        if not (is_select or is_with or is_union):
            raise SQLGuardrailError(
                f"Prohibited SQL statement type: '{type(ast).__name__}'. "
                "Only read-only SELECT or WITH...SELECT queries are allowed."
            )

    # 4. Dangerous function check
    for func in ast.find_all(exp.Func, exp.Anonymous):
        candidate_names = {
            (func.name or "").lower(),
            (func.sql_name() if hasattr(func, "sql_name") else "").lower(),
            (func.key if hasattr(func, "key") else "").lower(),
        }
        matched = candidate_names & DANGEROUS_FUNCTIONS
        if matched:
            prohibited_name = sorted(matched)[0]
            raise SQLGuardrailError(f"Prohibited function detected: '{prohibited_name}'.")

    # 5. Enforce or clamp LIMIT
    if isinstance(ast, exp.Select):
        limit_node = ast.args.get("limit")
        if limit_node:
            try:
                current_limit = int(limit_node.expression.this)
                if current_limit > row_limit:
                    ast.set("limit", exp.Limit(expression=exp.Literal.number(row_limit)))
            except Exception:
                ast.set("limit", exp.Limit(expression=exp.Literal.number(row_limit)))
        else:
            ast.set("limit", exp.Limit(expression=exp.Literal.number(row_limit)))

    # Return transpiled SQL in target dialect
    return ast.sql(dialect=glot_dialect)
