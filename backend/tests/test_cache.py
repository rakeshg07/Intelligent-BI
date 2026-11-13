"""Unit tests for Query Result Cache."""

from app.query.cache import QueryResultCache, generate_query_cache_key


def test_query_cache_set_and_get():
    QueryResultCache.clear()
    sql = "SELECT category, SUM(total_revenue) FROM global_sales GROUP BY category"
    key = generate_query_cache_key(sql, "ds-123")

    data = {
        "columns": ["category", "revenue"],
        "column_types": ["VARCHAR", "DOUBLE"],
        "rows": [["Electronics", 125000.0]],
        "row_count": 1,
        "sql": sql,
        "duration_ms": 12,
    }

    # Verify initial cache miss
    assert QueryResultCache.get(key) is None

    # Set cache with 10s TTL
    QueryResultCache.set(key, data, ttl_seconds=10)

    # Verify hit
    cached = QueryResultCache.get(key)
    assert cached is not None
    assert cached["row_count"] == 1
    assert cached["rows"][0][0] == "Electronics"


def test_query_cache_expiry():
    QueryResultCache.clear()
    key = "test_expire_key"
    data = {"hello": "world"}

    # Set 0s TTL (already expired)
    QueryResultCache.set(key, data, ttl_seconds=-1)
    assert QueryResultCache.get(key) is None
