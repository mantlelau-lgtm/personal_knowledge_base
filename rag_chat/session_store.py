from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from common.config import Settings, load_settings
from common.db import connect_db, row_to_dict


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class ChatStore:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()

    def create_session(self, title: str = "") -> dict[str, Any]:
        session_id = _new_id("sess")
        now = _now()
        with connect_db(self.settings) as conn:
            conn.execute(
                "INSERT INTO chat_sessions (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (session_id, title, now, now),
            )
        return {"id": session_id, "title": title, "created_at": now, "updated_at": now}

    def list_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        with connect_db(self.settings) as conn:
            rows = conn.execute(
                "SELECT * FROM chat_sessions ORDER BY updated_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [row_to_dict(row) for row in rows]

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with connect_db(self.settings) as conn:
            row = conn.execute("SELECT * FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
        return row_to_dict(row) if row else None

    def touch_session(self, session_id: str, title: str | None = None) -> None:
        now = _now()
        if title:
            with connect_db(self.settings) as conn:
                conn.execute(
                    "UPDATE chat_sessions SET title = ?, updated_at = ? WHERE id = ?",
                    (title, now, session_id),
                )
        else:
            with connect_db(self.settings) as conn:
                conn.execute("UPDATE chat_sessions SET updated_at = ? WHERE id = ?", (now, session_id))

    def delete_session(self, session_id: str) -> None:
        with connect_db(self.settings) as conn:
            conn.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        sources: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        message_id = _new_id("msg")
        now = _now()
        sources_json = json.dumps(sources or [], ensure_ascii=False)
        with connect_db(self.settings) as conn:
            conn.execute(
                "INSERT INTO chat_messages (id, session_id, role, content, sources_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (message_id, session_id, role, content, sources_json, now),
            )
            conn.execute("UPDATE chat_sessions SET updated_at = ? WHERE id = ?", (now, session_id))
        return {
            "id": message_id,
            "session_id": session_id,
            "role": role,
            "content": content,
            "sources": sources or [],
            "created_at": now,
        }

    def list_messages(self, session_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with connect_db(self.settings) as conn:
            rows = conn.execute(
                "SELECT * FROM chat_messages WHERE session_id = ? ORDER BY id ASC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        messages = []
        for row in rows:
            item = row_to_dict(row)
            item["sources"] = json.loads(item.pop("sources_json") or "[]")
            messages.append(item)
        return messages
