from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from common.config import Settings, load_settings
from common.file_ops import ensure_dir


def connect_db(settings: Settings | None = None) -> sqlite3.Connection:
    settings = settings or load_settings()
    db_path = Path(settings.storage_dir) / "pkb.sqlite3"
    ensure_dir(db_path.parent)
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    init_observability_tables(conn)
    return conn


def init_observability_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS llm_call_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            purpose TEXT NOT NULL,
            prompt_tokens INTEGER NOT NULL DEFAULT 0,
            completion_tokens INTEGER NOT NULL DEFAULT 0,
            cost_usd REAL NOT NULL DEFAULT 0,
            latency_ms INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL,
            error TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS prompts (
            name TEXT NOT NULL,
            version INTEGER NOT NULL,
            content TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            traffic_percent INTEGER NOT NULL DEFAULT 100,
            created_at TEXT NOT NULL,
            PRIMARY KEY (name, version)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_call_logs_created_at ON llm_call_logs(created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_call_logs_purpose ON llm_call_logs(purpose)")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_messages (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            sources_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id ON chat_messages(session_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_sessions_updated_at ON chat_sessions(updated_at)")


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}
