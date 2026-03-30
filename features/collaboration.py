# features/collaboration.py
# ─────────────────────────────────────────────────────────────────────────────
# Real-time WebSocket collaboration — multi-user Q&A sessions.
# v3.1 — Fixed datetime.utcnow(), added room cleanup for stale connections
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Set

from loguru import logger

from config import WS_ENABLED


class ConnectionManager:
    """Manages active WebSocket connections for real-time collaboration."""

    def __init__(self):
        self._active: Dict[str, Any] = {}  # ws_id → websocket
        self._rooms: Dict[str, Set[str]] = {}  # room_id → set of ws_ids
        self._usernames: Dict[str, str] = {}  # ws_id → display name

    async def connect(self, websocket: Any, room_id: str = "default", username: str = "Anonymous") -> str:
        """Register a new WebSocket connection."""
        ws_id = str(uuid.uuid4())[:8]
        await websocket.accept()
        self._active[ws_id] = websocket
        self._usernames[ws_id] = username

        if room_id not in self._rooms:
            self._rooms[room_id] = set()
        self._rooms[room_id].add(ws_id)

        logger.info(f"WS connected: {ws_id} ({username}) in room {room_id}")

        # Notify room
        await self.broadcast(room_id, {
            "type": "user_joined",
            "user": username,
            "users_count": len(self._rooms[room_id]),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }, exclude=ws_id)

        return ws_id

    def disconnect(self, ws_id: str) -> None:
        """Remove a WebSocket connection."""
        username = self._usernames.pop(ws_id, "Unknown")
        self._active.pop(ws_id, None)

        for room_id, members in list(self._rooms.items()):
            if ws_id in members:
                members.discard(ws_id)
                # v3.1: Clean up empty rooms
                if not members:
                    del self._rooms[room_id]
                    logger.info(f"Room {room_id} cleaned up (empty)")
                logger.info(f"WS disconnected: {ws_id} ({username}) from room {room_id}")
                break

    async def broadcast(
        self, room_id: str, message: Dict[str, Any], exclude: str = ""
    ) -> None:
        """Send a message to all connections in a room."""
        members = self._rooms.get(room_id, set())
        disconnected = []

        for ws_id in members:
            if ws_id == exclude:
                continue
            ws = self._active.get(ws_id)
            if ws:
                try:
                    await ws.send_json(message)
                except Exception:
                    disconnected.append(ws_id)

        for ws_id in disconnected:
            self.disconnect(ws_id)

    async def send_to(self, ws_id: str, message: Dict[str, Any]) -> None:
        """Send a message to a specific connection."""
        ws = self._active.get(ws_id)
        if ws:
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect(ws_id)

    def get_room_users(self, room_id: str) -> List[str]:
        """Get list of usernames in a room."""
        members = self._rooms.get(room_id, set())
        return [self._usernames.get(ws_id, "Unknown") for ws_id in members]

    def get_stats(self) -> Dict[str, Any]:
        """Return connection statistics."""
        return {
            "active_connections": len(self._active),
            "rooms": {
                room_id: len(members)
                for room_id, members in self._rooms.items()
            },
            "enabled": WS_ENABLED,
        }

    async def cleanup_stale(self) -> int:
        """Remove stale/dead connections. Returns count removed."""
        stale = []
        for ws_id, ws in list(self._active.items()):
            try:
                # Try sending a ping — if it fails, the connection is dead
                await ws.send_json({"type": "ping"})
            except Exception:
                stale.append(ws_id)

        for ws_id in stale:
            self.disconnect(ws_id)

        if stale:
            logger.info(f"Cleaned up {len(stale)} stale WebSocket connections")
        return len(stale)


# Module-level singleton
collab_manager = ConnectionManager()
