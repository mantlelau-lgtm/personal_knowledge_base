from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from common.config import Settings, load_settings
from common.db import connect_db, row_to_dict
from common.prompt_registry import PromptRegistry


@dataclass
class PromptRouter:
    settings: Settings | None = None
    registry: PromptRegistry | None = None
    prompts: PromptRegistry | None = None

    def __post_init__(self) -> None:
        self.settings = self.settings or load_settings()
        # Support both `registry=` and `prompts=` naming for backwards compatibility.
        self.registry = self.registry or self.prompts or PromptRegistry(self.settings)
        self.prompts = self.registry

    def register(
        self,
        name: str,
        version: str,
        content: str = "",
        traffic_percent: int = 100,
        active: bool = True,
    ) -> dict[str, Any]:
        body = content
        if not body:
            body = self.registry.get(name, version) or ""
        now = datetime.now(timezone.utc).isoformat()
        with connect_db(self.settings) as conn:
            existing = conn.execute(
                "SELECT created_at FROM prompts WHERE name = ? AND version = ?",
                (name, version),
            ).fetchone()
            created_at = existing["created_at"] if existing else now
            conn.execute(
                """
                INSERT INTO prompts (name, version, content, active, traffic_percent, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(name, version) DO UPDATE SET
                    content = excluded.content,
                    active = excluded.active,
                    traffic_percent = excluded.traffic_percent
                """,
                (name, version, body, 1 if active else 0, int(traffic_percent), created_at),
            )
            row = conn.execute(
                "SELECT * FROM prompts WHERE name = ? AND version = ?",
                (name, version),
            ).fetchone()
        return row_to_dict(row)

    def list(self, name: str) -> list[dict[str, Any]]:
        with connect_db(self.settings) as conn:
            rows = conn.execute(
                "SELECT * FROM prompts WHERE name = ? ORDER BY version",
                (name,),
            ).fetchall()
        return [row_to_dict(row) for row in rows]

    def set_traffic(self, name: str, splits: dict[str, int]) -> None:
        if not splits:
            return
        with connect_db(self.settings) as conn:
            for version, percent in splits.items():
                conn.execute(
                    "UPDATE prompts SET traffic_percent = ? WHERE name = ? AND version = ?",
                    (int(percent), name, str(version)),
                )

    def pick(self, name: str) -> str:
        rows = self.list(name)
        active_rows = [r for r in rows if int(r.get("active") or 0) == 1]
        if not active_rows:
            return "v1"
        total = sum(max(0, int(r.get("traffic_percent") or 0)) for r in active_rows)
        if total <= 0:
            return str(active_rows[0]["version"])
        roll = random.random() * total
        cumulative = 0.0
        for row in active_rows:
            cumulative += max(0, int(row.get("traffic_percent") or 0))
            if roll < cumulative:
                return str(row["version"])
        return str(active_rows[-1]["version"])

    def render(self, name: str, **kwargs: str) -> tuple[str, str]:
        version = self.pick(name)
        text = self.registry.render(name, version, **kwargs) if self.registry else ""
        if not text:
            return ("v1", "")
        return (version, text)
