# utils/rate_limiter.py
# ─────────────────────────────────────────────────────────────────────────────
# Simple in-memory sliding-window rate limiter for API endpoints.
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Dict

from loguru import logger

from config import RATE_LIMIT_ENABLED, RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW


class RateLimiter:
    """Sliding-window rate limiter keyed by client IP."""

    def __init__(
        self,
        max_requests: int = RATE_LIMIT_REQUESTS,
        window_secs: int = RATE_LIMIT_WINDOW,
        enabled: bool = RATE_LIMIT_ENABLED,
    ):
        self._requests: Dict[str, list] = defaultdict(list)
        self._lock = threading.Lock()
        self.max_requests = max_requests
        self.window_secs = window_secs
        self.enabled = enabled

    def _cleanup(self, client_id: str) -> None:
        """Remove expired timestamps for a client."""
        cutoff = time.time() - self.window_secs
        self._requests[client_id] = [
            ts for ts in self._requests[client_id] if ts > cutoff
        ]

    def is_allowed(self, client_id: str) -> bool:
        """Check if a request from client_id is allowed."""
        if not self.enabled:
            return True

        with self._lock:
            self._cleanup(client_id)
            if len(self._requests[client_id]) >= self.max_requests:
                logger.warning(
                    f"Rate limit exceeded for {client_id}: "
                    f"{len(self._requests[client_id])}/{self.max_requests}"
                )
                return False
            self._requests[client_id].append(time.time())
            return True

    def remaining(self, client_id: str) -> int:
        """Return remaining requests for client_id in the current window."""
        with self._lock:
            self._cleanup(client_id)
            return max(0, self.max_requests - len(self._requests[client_id]))

    def reset(self) -> None:
        """Clear all rate limit data."""
        with self._lock:
            self._requests.clear()


# Module-level singleton
rate_limiter = RateLimiter()
