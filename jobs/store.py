from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from common.config import Settings, load_settings
from common.file_ops import ensure_dir

from .models import Job, now_iso


UTC = timezone.utc


class JobStore:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()
        self.db_path = Path(self.settings.storage_dir) / "pkb.sqlite3"
        ensure_dir(self.db_path.parent)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    total INTEGER NOT NULL DEFAULT 0,
                    current INTEGER NOT NULL DEFAULT 0,
                    input_json TEXT NOT NULL DEFAULT '{}',
                    result_json TEXT NOT NULL DEFAULT '{}',
                    error TEXT NOT NULL DEFAULT '',
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    max_retries INTEGER NOT NULL DEFAULT 2,
                    lease_until TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS job_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    level TEXT NOT NULL,
                    event TEXT NOT NULL,
                    message TEXT NOT NULL,
                    data_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_job_events_job_id ON job_events(job_id)")

    def create_job(self, job_type: str, input_data: dict[str, Any] | None = None) -> Job:
        job = Job.new(job_type, input_data)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    id, type, status, stage, total, current, input_json, result_json, error,
                    retry_count, max_retries, lease_until, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._job_values(job),
            )
        self.add_event(job.id, "info", "created", f"任务已创建：{job.type}")
        return job

    def get_job(self, job_id: str) -> Job | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return self._row_to_job(row) if row else None

    def list_jobs(self, limit: int = 20) -> list[Job]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [self._row_to_job(row) for row in rows]

    def list_pending_or_stale(self, now_iso: str) -> list[Job]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM jobs
                WHERE status = 'pending'
                   OR (status = 'running' AND lease_until != '' AND lease_until < ?)
                ORDER BY created_at ASC
                """,
                (now_iso,),
            ).fetchall()
        return [self._row_to_job(row) for row in rows]

    def acquire_lease(self, job_id: str, seconds: int = 900) -> Job | None:
        now = datetime.now(UTC)
        now_str = now.isoformat()
        lease_until = (now + timedelta(seconds=seconds)).isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE jobs
                SET status = 'running',
                    lease_until = ?,
                    updated_at = ?
                WHERE id = ?
                  AND (
                        status = 'pending'
                     OR (status = 'running' AND lease_until != '' AND lease_until < ?)
                  )
                """,
                (lease_until, now_str, job_id, now_str),
            )
            if cursor.rowcount == 0:
                return None
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return self._row_to_job(row) if row else None

    def release_lease(self, job_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE jobs SET lease_until = '', updated_at = ? WHERE id = ?",
                (now_iso(), job_id),
            )

    def update_job(self, job_id: str, **changes: Any) -> Job:
        job = self.get_job(job_id)
        if not job:
            raise KeyError(f"job not found: {job_id}")
        for key, value in changes.items():
            if hasattr(job, key):
                setattr(job, key, value)
        job.updated_at = now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE jobs SET
                    type = ?, status = ?, stage = ?, total = ?, current = ?, input_json = ?,
                    result_json = ?, error = ?, retry_count = ?, max_retries = ?, lease_until = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    job.type,
                    job.status,
                    job.stage,
                    job.total,
                    job.current,
                    json.dumps(job.input, ensure_ascii=False),
                    json.dumps(job.result, ensure_ascii=False),
                    job.error,
                    job.retry_count,
                    job.max_retries,
                    job.lease_until,
                    job.updated_at,
                    job.id,
                ),
            )
        return job

    def add_event(self, job_id: str, level: str, event: str, message: str, data: dict[str, Any] | None = None) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO job_events (job_id, level, event, message, data_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (job_id, level, event, message, json.dumps(data or {}, ensure_ascii=False), now_iso()),
            )

    def list_events(self, job_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM job_events WHERE job_id = ? ORDER BY id ASC LIMIT ?",
                (job_id, limit),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "job_id": row["job_id"],
                "level": row["level"],
                "event": row["event"],
                "message": row["message"],
                "data": json.loads(row["data_json"] or "{}"),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    @staticmethod
    def to_dict(job: Job) -> dict[str, Any]:
        return {
            "id": job.id,
            "type": job.type,
            "status": job.status,
            "stage": job.stage,
            "total": job.total,
            "current": job.current,
            "input": job.input,
            "result": job.result,
            "error": job.error,
            "retry_count": job.retry_count,
            "max_retries": job.max_retries,
            "lease_until": job.lease_until,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
        }

    @staticmethod
    def _job_values(job: Job) -> tuple[Any, ...]:
        return (
            job.id,
            job.type,
            job.status,
            job.stage,
            job.total,
            job.current,
            json.dumps(job.input, ensure_ascii=False),
            json.dumps(job.result, ensure_ascii=False),
            job.error,
            job.retry_count,
            job.max_retries,
            job.lease_until,
            job.created_at,
            job.updated_at,
        )

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> Job:
        return Job(
            id=row["id"],
            type=row["type"],
            status=row["status"],
            stage=row["stage"],
            total=row["total"],
            current=row["current"],
            input=json.loads(row["input_json"] or "{}"),
            result=json.loads(row["result_json"] or "{}"),
            error=row["error"],
            retry_count=row["retry_count"],
            max_retries=row["max_retries"],
            lease_until=row["lease_until"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
