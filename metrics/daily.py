from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from common.config import Settings, load_settings
from common.db import connect_db, row_to_dict


def init_daily_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS kb_daily_stats (
            day TEXT PRIMARY KEY,
            total_calls INTEGER NOT NULL DEFAULT 0,
            total_prompt_tokens INTEGER NOT NULL DEFAULT 0,
            total_completion_tokens INTEGER NOT NULL DEFAULT 0,
            total_cost_usd REAL NOT NULL DEFAULT 0,
            avg_latency_ms REAL NOT NULL DEFAULT 0,
            error_count INTEGER NOT NULL DEFAULT 0,
            purpose_breakdown_json TEXT NOT NULL DEFAULT '{}',
            updated_at TEXT NOT NULL
        )
        """
    )


@dataclass
class DailyStatsAggregator:
    settings: Settings | None = None

    def __post_init__(self) -> None:
        self.settings = self.settings or load_settings()
        self._initialized = False

    def _connect(self) -> sqlite3.Connection:
        conn = connect_db(self.settings)
        if not self._initialized:
            init_daily_tables(conn)
            self._initialized = True
        return conn

    def aggregate(self, day: str | None = None) -> dict[str, Any]:
        target_day = day or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        prefix = f"{target_day}%"
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT purpose, prompt_tokens, completion_tokens, cost_usd, latency_ms, status
                FROM llm_call_logs
                WHERE created_at LIKE ?
                """,
                (prefix,),
            ).fetchall()

            total_calls = len(rows)
            total_prompt = 0
            total_completion = 0
            total_cost = 0.0
            total_latency = 0
            error_count = 0
            purpose_stats: dict[str, dict[str, float]] = {}
            for r in rows:
                total_prompt += int(r["prompt_tokens"] or 0)
                total_completion += int(r["completion_tokens"] or 0)
                total_cost += float(r["cost_usd"] or 0)
                total_latency += int(r["latency_ms"] or 0)
                if str(r["status"]) != "ok":
                    error_count += 1
                purpose = str(r["purpose"] or "unknown")
                bucket = purpose_stats.setdefault(purpose, {"calls": 0, "cost": 0.0})
                bucket["calls"] = int(bucket["calls"]) + 1
                bucket["cost"] = float(bucket["cost"]) + float(r["cost_usd"] or 0)

            avg_latency = (total_latency / total_calls) if total_calls else 0.0
            total_cost = round(total_cost, 8)
            purpose_breakdown = {k: {"calls": int(v["calls"]), "cost": round(float(v["cost"]), 8)} for k, v in purpose_stats.items()}

            result: dict[str, Any] = {
                "day": target_day,
                "total_calls": total_calls,
                "total_prompt_tokens": total_prompt,
                "total_completion_tokens": total_completion,
                "total_cost_usd": total_cost,
                "avg_latency_ms": round(avg_latency, 3),
                "error_count": error_count,
                "purpose_breakdown": purpose_breakdown,
            }
            updated_at = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """
                INSERT INTO kb_daily_stats (
                    day, total_calls, total_prompt_tokens, total_completion_tokens,
                    total_cost_usd, avg_latency_ms, error_count, purpose_breakdown_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(day) DO UPDATE SET
                    total_calls = excluded.total_calls,
                    total_prompt_tokens = excluded.total_prompt_tokens,
                    total_completion_tokens = excluded.total_completion_tokens,
                    total_cost_usd = excluded.total_cost_usd,
                    avg_latency_ms = excluded.avg_latency_ms,
                    error_count = excluded.error_count,
                    purpose_breakdown_json = excluded.purpose_breakdown_json,
                    updated_at = excluded.updated_at
                """,
                (
                    target_day,
                    total_calls,
                    total_prompt,
                    total_completion,
                    total_cost,
                    round(avg_latency, 3),
                    error_count,
                    json.dumps(purpose_breakdown, ensure_ascii=False),
                    updated_at,
                ),
            )
            result["updated_at"] = updated_at
        return result

    def list_recent(self, days: int = 7) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM kb_daily_stats ORDER BY day DESC LIMIT ?",
                (int(days),),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            data = row_to_dict(row)
            try:
                data["purpose_breakdown"] = json.loads(data.pop("purpose_breakdown_json") or "{}")
            except Exception:
                data["purpose_breakdown"] = {}
                data.pop("purpose_breakdown_json", None)
            result.append(data)
        return result


def run_daily_aggregation(settings: Settings | None = None) -> dict[str, Any]:
    return DailyStatsAggregator(settings).aggregate()
