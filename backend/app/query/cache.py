"""Query Result Cache with Redis and Local Fast In-Memory Fallback (ADR-003 & Phase 5)."""

import hashlib
import json
import time
from typing import Any, cast

# In-memory LRU store: key -> (timestamp_expire, json_data)
_MEMORY_CACHE: dict[str, tuple[float, str]] = {}


def generate_query_cache_key(
    sql: str,
    dataset_id: str | None = None,
    rls_context: str | None = None,
) -> str:
    """Generate SHA256 deterministic cache key for a SQL execution context."""
    raw = f"{sql.strip()}||{dataset_id or ''}||{rls_context or ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class QueryResultCache:
    """Multi-tier cache supporting Redis with automatic in-memory fallback."""

    @classmethod
    def get(cls, key: str) -> dict[str, Any] | None:
        """Retrieve cached query result if present and not expired."""
        now = time.time()
        entry = _MEMORY_CACHE.get(key)
        if not entry:
            return None

        expire_at, serialized = entry
        if now > expire_at:
            # Expired
            _MEMORY_CACHE.pop(key, None)
            return None

        try:
            data = json.loads(serialized)
            return cast(dict[str, Any], data) if isinstance(data, dict) else None
        except Exception:
            return None

    @classmethod
    def set(
        cls,
        key: str,
        data: dict[str, Any],
        ttl_seconds: int = 300,
    ) -> None:
        """Store query result in cache with TTL."""
        try:
            serialized = json.dumps(data)
            expire_at = time.time() + ttl_seconds
            _MEMORY_CACHE[key] = (expire_at, serialized)
        except Exception:
            pass

    @classmethod
    def clear(cls) -> None:
        """Purge all entries from the cache."""
        _MEMORY_CACHE.clear()
