from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from common.config import Settings, load_settings
from common.db import connect_db

from .models import ALLOWED_LEVELS


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AlertStore:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()
        self._init_db()

    def _connect(self):
        return connect_db(self.settings)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS alerts (
                    id TEXT PRIMARY KEY,
                    level TEXT NOT NULL,
                    event TEXT NOT NULL,
                    message TEXT NOT NULL,
                    data_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    resolved INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_level ON alerts(level)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_resolved ON alerts(resolved)")

    def create(self, level: str, event: str, message: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        if level not in ALLOWED_LEVELS:
            level = "P2"
        alert_id = uuid.uuid4().hex
        created_at = _now_iso()
        payload = data or {}
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO alerts (id, level, event, message, data_json, created_at, resolved)
                VALUES (?, ?, ?, ?, ?, ?, 0)
                """,
                (alert_id, level, event, message, json.dumps(payload, ensure_ascii=False), created_at),
            )
        return {
            "id": alert_id,
            "level": level,
            "event": event,
            "message": message,
            "data": payload,
            "created_at": created_at,
            "resolved": False,
        }

    def list(
        self,
        level: str | None = None,
        resolved: bool | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM alerts"
        clauses: list[str] = []
        params: list[Any] = []
        if level is not None:
            clauses.append("level = ?")
            params.append(level)
        if resolved is not None:
            clauses.append("resolved = ?")
            params.append(1 if resolved else 0)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def resolve(self, alert_id: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE alerts SET resolved = 1 WHERE id = ?", (alert_id,))

    def stats(self) -> dict[str, Any]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT level, COUNT(*) AS cnt FROM alerts WHERE resolved = 0 GROUP BY level"
            ).fetchall()
        counts = {level: 0 for level in ALLOWED_LEVELS}
        total = 0
        for row in rows:
            counts[row["level"]] = row["cnt"]
            total += row["cnt"]
        return {"open_total": total, "open_by_level": counts}

    @staticmethod
    def _row_to_dict(row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "level": row["level"],
            "event": row["event"],
            "message": row["message"],
            "data": json.loads(row["data_json"] or "{}"),
            "created_at": row["created_at"],
            "resolved": bool(row["resolved"]),
        }
