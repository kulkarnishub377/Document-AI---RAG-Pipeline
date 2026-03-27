# utils/cache.py
# ─────────────────────────────────────────────────────────────────────────────
# In-memory LRU query cache with TTL expiration.
# Avoids redundant LLM calls for identical queries.
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import hashlib
import threading
import time
from collections import OrderedDict
from typing import Any, Dict, Optional

from loguru import logger

from config import CACHE_ENABLED, CACHE_MAX_SIZE, CACHE_TTL_SECS


class QueryCache:
    """Thread-safe LRU cache with TTL for query responses."""

    def __init__(
        self,
        max_size: int = CACHE_MAX_SIZE,
        ttl_secs: int = CACHE_TTL_SECS,
        enabled: bool = CACHE_ENABLED,
    ):
        self._cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._lock = threading.Lock()
        self.max_size = max_size
        self.ttl_secs = ttl_secs
        self.enabled = enabled
        self._hits = 0
        self._misses = 0

    @staticmethod
    def _make_key(query: str, mode: str = "qa") -> str:
        """Create a cache key from query text and mode."""
        raw = f"{mode}:{query.strip().lower()}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

    def get(self, query: str, mode: str = "qa") -> Optional[Dict[str, Any]]:
        """Retrieve a cached response. Returns None on miss."""
        if not self.enabled:
            return None

        key = self._make_key(query, mode)
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._misses += 1
                return None

            # Check TTL
            if time.time() - entry["timestamp"] > self.ttl_secs:
                del self._cache[key]
                self._misses += 1
                logger.debug(f"Cache expired for key: {key[:8]}…")
                return None

            # Move to end (LRU)
            self._cache.move_to_end(key)
            self._hits += 1
            logger.debug(f"Cache HIT for key: {key[:8]}…")
            return entry["data"]

    def put(self, query: str, data: Dict[str, Any], mode: str = "qa") -> None:
        """Store a response in cache."""
        if not self.enabled:
            return

        key = self._make_key(query, mode)
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                self._cache[key] = {"data": data, "timestamp": time.time()}
            else:
                if len(self._cache) >= self.max_size:
                    self._cache.popitem(last=False)
                self._cache[key] = {"data": data, "timestamp": time.time()}

    def invalidate(self) -> int:
        """Clear all cache entries. Returns count of cleared entries."""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            logger.info(f"Cache cleared: {count} entries removed.")
            return count

    def stats(self) -> Dict[str, Any]:
        """Return cache statistics."""
        total = self._hits + self._misses
        with self._lock:
            return {
                "enabled": self.enabled,
                "size": len(self._cache),
                "max_size": self.max_size,
                "ttl_secs": self.ttl_secs,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(self._hits / max(total, 1) * 100, 1),
            }


# Module-level singleton
query_cache = QueryCache()
