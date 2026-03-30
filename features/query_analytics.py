# features/query_analytics.py
# ─────────────────────────────────────────────────────────────────────────────
# v3.1 — Query Analytics Tracker (F10)
#
# Tracks query frequency, response times, popular documents, failed queries.
# Provides data for the analytics dashboard.
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import json
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from loguru import logger

from config import QUERY_ANALYTICS_ENABLED, QUERY_ANALYTICS_PATH


class QueryAnalytics:
    """Tracks and reports query usage analytics."""

    def __init__(self):
        self._lock = threading.Lock()
        self._queries: List[Dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        """Load analytics from disk."""
        if QUERY_ANALYTICS_PATH.exists():
            try:
                with open(QUERY_ANALYTICS_PATH, "r", encoding="utf-8") as f:
                    self._queries = json.load(f)
                logger.info(f"Loaded {len(self._queries)} query analytics records")
            except Exception as e:
                logger.warning(f"Failed to load query analytics: {e}")

    def _save(self) -> None:
        """Persist analytics to disk."""
        try:
            with open(QUERY_ANALYTICS_PATH, "w", encoding="utf-8") as f:
                json.dump(self._queries, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save query analytics: {e}")

    def record_query(
        self,
        question: str,
        mode: str = "qa",
        response_time_ms: int = 0,
        sources_used: Optional[List[str]] = None,
        success: bool = True,
        cached: bool = False,
    ) -> None:
        """Record a query for analytics tracking."""
        if not QUERY_ANALYTICS_ENABLED:
            return

        with self._lock:
            self._queries.append({
                "question": question[:500],  # Cap length
                "mode": mode,
                "response_time_ms": response_time_ms,
                "sources_used": sources_used or [],
                "success": success,
                "cached": cached,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

            # Keep last 2000 records
            if len(self._queries) > 2000:
                self._queries = self._queries[-2000:]

            self._save()

    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive query analytics."""
        with self._lock:
            if not self._queries:
                return {
                    "total_queries": 0,
                    "successful_queries": 0,
                    "failed_queries": 0,
                    "cached_queries": 0,
                    "avg_response_time_ms": 0,
                    "popular_questions": [],
                    "popular_sources": [],
                    "queries_by_mode": {},
                    "queries_today": 0,
                    "trend": [],
                }

            total = len(self._queries)
            successful = sum(1 for q in self._queries if q.get("success", True))
            failed = total - successful
            cached = sum(1 for q in self._queries if q.get("cached", False))

            response_times = [q.get("response_time_ms", 0) for q in self._queries if q.get("response_time_ms", 0) > 0]
            avg_time = round(sum(response_times) / max(len(response_times), 1))

            # Popular questions (by frequency)
            question_freq: Dict[str, int] = defaultdict(int)
            for q in self._queries:
                short_q = q.get("question", "")[:100].lower().strip()
                if short_q:
                    question_freq[short_q] += 1
            popular_questions = sorted(question_freq.items(), key=lambda x: x[1], reverse=True)[:10]

            # Popular sources
            source_freq: Dict[str, int] = defaultdict(int)
            for q in self._queries:
                for src in q.get("sources_used", []):
                    source_freq[src] += 1
            popular_sources = sorted(source_freq.items(), key=lambda x: x[1], reverse=True)[:10]

            # Queries by mode
            mode_counts: Dict[str, int] = defaultdict(int)
            for q in self._queries:
                mode_counts[q.get("mode", "qa")] += 1

            # Queries today
            today = datetime.now(timezone.utc).date().isoformat()
            queries_today = sum(1 for q in self._queries if q.get("timestamp", "").startswith(today))

            # Trend (last 20 data points)
            recent = self._queries[-20:]
            trend = [
                {
                    "time": q.get("timestamp", ""),
                    "response_ms": q.get("response_time_ms", 0),
                    "success": q.get("success", True),
                }
                for q in recent
            ]

            return {
                "total_queries": total,
                "successful_queries": successful,
                "failed_queries": failed,
                "cached_queries": cached,
                "avg_response_time_ms": avg_time,
                "popular_questions": [
                    {"question": q, "count": c} for q, c in popular_questions
                ],
                "popular_sources": [
                    {"source": s, "count": c} for s, c in popular_sources
                ],
                "queries_by_mode": dict(mode_counts),
                "queries_today": queries_today,
                "trend": trend,
            }

    def clear(self) -> int:
        """Clear all analytics data. Returns count cleared."""
        with self._lock:
            count = len(self._queries)
            self._queries.clear()
            if QUERY_ANALYTICS_PATH.exists():
                QUERY_ANALYTICS_PATH.unlink()
            return count


# Module-level singleton
query_analytics = QueryAnalytics()
