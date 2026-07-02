from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from common.config import Settings, load_settings
from common.db import connect_db


@dataclass
class LLMCache:
    settings: Settings | None = None

    def __post_init__(self) -> None:
        self.settings = self.settings or load_settings()
        with connect_db(self.settings) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS llm_response_cache (
                    cache_key TEXT PRIMARY KEY,
                    purpose TEXT,
                    model TEXT,
                    response TEXT,
                    hit_count INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
                """
            )

    @staticmethod
    def make_key(purpose: str, model: str, prompt: str, context: str = "") -> str:
        raw = f"{purpose}|{model}|{prompt}|{context}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def get(self, cache_key: str) -> str | None:
        now = datetime.now(timezone.utc).isoformat()
        with connect_db(self.settings) as conn:
            row = conn.execute(
                "SELECT response, expires_at FROM llm_response_cache WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()
            if row is None:
                return None
            if row["expires_at"] <= now:
                return None
            conn.execute(
                "UPDATE llm_response_cache SET hit_count = hit_count + 1 WHERE cache_key = ?",
                (cache_key,),
            )
            return row["response"]

    def set(
        self,
        cache_key: str,
        purpose: str,
        model: str,
        response: str,
        ttl_seconds: int | None = None,
    ) -> None:
        if ttl_seconds is None:
            ttl_seconds = int(getattr(self.settings, "llm_cache_ttl_seconds", 3600))
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=max(0, int(ttl_seconds)))
        with connect_db(self.settings) as conn:
            conn.execute(
                """
                INSERT INTO llm_response_cache (cache_key, purpose, model, response, hit_count, created_at, expires_at)
                VALUES (?, ?, ?, ?, 0, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    purpose = excluded.purpose,
                    model = excluded.model,
                    response = excluded.response,
                    created_at = excluded.created_at,
                    expires_at = excluded.expires_at
                """,
                (cache_key, purpose, model, response, now.isoformat(), expires.isoformat()),
            )

    def clear_expired(self) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with connect_db(self.settings) as conn:
            cur = conn.execute(
                "DELETE FROM llm_response_cache WHERE expires_at <= ?",
                (now,),
            )
            return int(cur.rowcount or 0)

    def stats(self) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        with connect_db(self.settings) as conn:
            total = conn.execute("SELECT COUNT(*) AS c FROM llm_response_cache").fetchone()["c"]
            expired = conn.execute(
                "SELECT COUNT(*) AS c FROM llm_response_cache WHERE expires_at <= ?",
                (now,),
            ).fetchone()["c"]
        return {"total": int(total), "expired": int(expired)}
