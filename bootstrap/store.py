from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from common.config import Settings, load_settings
from common.db import connect_db


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return f"bs_{uuid.uuid4().hex[:12]}"


def init_bootstrap_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS bootstrap_plans (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            sources_json TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL,
            total_files INTEGER DEFAULT 0,
            total_chars INTEGER DEFAULT 0,
            estimated_tokens INTEGER DEFAULT 0,
            estimated_cost_usd REAL DEFAULT 0,
            approved_by TEXT DEFAULT '',
            job_ids_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


class BootstrapStore:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()
        with connect_db(self.settings) as conn:
            init_bootstrap_tables(conn)

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "sources": json.loads(row["sources_json"] or "[]"),
            "status": row["status"],
            "total_files": row["total_files"],
            "total_chars": row["total_chars"],
            "estimated_tokens": row["estimated_tokens"],
            "estimated_cost_usd": row["estimated_cost_usd"],
            "approved_by": row["approved_by"],
            "job_ids": json.loads(row["job_ids_json"] or "[]"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def create_plan(self, name: str, sources: list[str]) -> dict[str, Any]:
        plan_id = _new_id()
        now = _now()
        with connect_db(self.settings) as conn:
            init_bootstrap_tables(conn)
            conn.execute(
                """
                INSERT INTO bootstrap_plans (id, name, sources_json, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (plan_id, name or plan_id, json.dumps(sources, ensure_ascii=False), "draft", now, now),
            )
            row = conn.execute("SELECT * FROM bootstrap_plans WHERE id = ?", (plan_id,)).fetchone()
        return self._row_to_dict(row)

    def list_plans(self, limit: int = 50) -> list[dict[str, Any]]:
        with connect_db(self.settings) as conn:
            init_bootstrap_tables(conn)
            rows = conn.execute(
                "SELECT * FROM bootstrap_plans ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def get_plan(self, plan_id: str) -> dict[str, Any] | None:
        with connect_db(self.settings) as conn:
            init_bootstrap_tables(conn)
            row = conn.execute("SELECT * FROM bootstrap_plans WHERE id = ?", (plan_id,)).fetchone()
        return self._row_to_dict(row) if row else None

    def update_plan(self, plan_id: str, **fields: Any) -> dict[str, Any]:
        if not fields:
            return self.get_plan(plan_id) or {}
        columns: list[str] = []
        values: list[Any] = []
        for key, value in fields.items():
            if key == "sources":
                columns.append("sources_json = ?")
                values.append(json.dumps(value, ensure_ascii=False))
            elif key == "job_ids":
                columns.append("job_ids_json = ?")
                values.append(json.dumps(value, ensure_ascii=False))
            else:
                columns.append(f"{key} = ?")
                values.append(value)
        columns.append("updated_at = ?")
        values.append(_now())
        values.append(plan_id)
        with connect_db(self.settings) as conn:
            init_bootstrap_tables(conn)
            conn.execute(f"UPDATE bootstrap_plans SET {', '.join(columns)} WHERE id = ?", tuple(values))
        return self.get_plan(plan_id) or {}

    def delete_plan(self, plan_id: str) -> None:
        with connect_db(self.settings) as conn:
            init_bootstrap_tables(conn)
            conn.execute("DELETE FROM bootstrap_plans WHERE id = ?", (plan_id,))
