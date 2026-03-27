# utils/sessions.py
# ─────────────────────────────────────────────────────────────────────────────
# Persistent chat sessions using SQLite for cross-browser session persistence.
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger

from config import SQLITE_DB_PATH


class SessionManager:
    """Manages persistent chat sessions in SQLite."""

    def __init__(self, db_path: str = str(SQLITE_DB_PATH)):
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """Per-thread SQLite connection."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA foreign_keys = ON")
        return self._local.conn

    def _init_db(self) -> None:
        """Create tables if they don't exist."""
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id           TEXT PRIMARY KEY,
                title        TEXT NOT NULL DEFAULT 'Untitled',
                created_at   TEXT NOT NULL,
                updated_at   TEXT NOT NULL,
                metadata     TEXT DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS messages (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id   TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                role         TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
                content      TEXT NOT NULL,
                sources      TEXT DEFAULT '[]',
                created_at   TEXT NOT NULL,
                mode         TEXT DEFAULT 'qa'
            );

            CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
            CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at);
        """)
        conn.commit()
        logger.info(f"Session database ready: {self.db_path}")

    def create_session(self, title: str = "Untitled") -> Dict[str, Any]:
        """Create a new chat session."""
        session_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO sessions (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (session_id, title, now, now),
        )
        conn.commit()
        logger.info(f"Created session: {session_id} — '{title}'")
        return {"id": session_id, "title": title, "created_at": now}

    def list_sessions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """List recent sessions sorted by last update."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT id, title, created_at, updated_at FROM sessions "
            "ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get a session by ID, including message count."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT s.*, COUNT(m.id) as message_count FROM sessions s "
            "LEFT JOIN messages m ON m.session_id = s.id WHERE s.id = ?",
            (session_id,),
        ).fetchone()
        return dict(row) if row and row["id"] else None

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        sources: Optional[List[Dict]] = None,
        mode: str = "qa",
    ) -> Dict[str, Any]:
        """Add a message to a session."""
        now = datetime.utcnow().isoformat()
        sources_json = json.dumps(sources or [])
        conn = self._get_conn()
        cursor = conn.execute(
            "INSERT INTO messages (session_id, role, content, sources, created_at, mode) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, role, content, sources_json, now, mode),
        )
        conn.execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id)
        )
        conn.commit()
        return {"id": cursor.lastrowid, "role": role, "content": content, "created_at": now}

    def get_messages(
        self, session_id: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get messages for a session, ordered chronologically."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT role, content, sources, created_at, mode FROM messages "
            "WHERE session_id = ? ORDER BY created_at ASC LIMIT ?",
            (session_id, limit),
        ).fetchall()
        results = []
        for r in rows:
            msg = dict(r)
            msg["sources"] = json.loads(msg["sources"]) if msg["sources"] else []
            results.append(msg)
        return results

    def get_chat_history(self, session_id: str, last_n: int = 5) -> List[Dict[str, str]]:
        """Get last N messages formatted for LLM context."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE session_id = ? "
            "ORDER BY created_at DESC LIMIT ?",
            (session_id, last_n),
        ).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    def delete_session(self, session_id: str) -> bool:
        """Delete a session and its messages."""
        conn = self._get_conn()
        conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        result = conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        conn.commit()
        return result.rowcount > 0

    def update_title(self, session_id: str, title: str) -> bool:
        """Update session title."""
        conn = self._get_conn()
        now = datetime.utcnow().isoformat()
        result = conn.execute(
            "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?",
            (title, now, session_id),
        )
        conn.commit()
        return result.rowcount > 0

    def get_stats(self) -> Dict[str, Any]:
        """Get session statistics."""
        conn = self._get_conn()
        total = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        msgs = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        return {"total_sessions": total, "total_messages": msgs}


# Module-level singleton
session_manager = SessionManager()
