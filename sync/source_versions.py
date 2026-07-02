from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common.config import Settings, load_settings
from common.db import connect_db
from common.file_ops import file_sha256
from data_collection.collector import SUPPORTED_EXTENSIONS


UTC = timezone.utc


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def init_sync_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS source_versions (
            source_id TEXT PRIMARY KEY,
            path TEXT NOT NULL,
            hash TEXT NOT NULL,
            size INTEGER NOT NULL DEFAULT 0,
            last_seen_at TEXT NOT NULL,
            last_processed_at TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.commit()


class SourceVersionStore:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()
        with self._connect() as conn:
            init_sync_tables(conn)

    def _connect(self) -> sqlite3.Connection:
        return connect_db(self.settings)

    def upsert(self, source_id: str, path: str, hash: str, size: int) -> dict[str, Any]:
        now = _now_iso()
        with self._connect() as conn:
            init_sync_tables(conn)
            existing = conn.execute(
                "SELECT * FROM source_versions WHERE source_id = ?",
                (source_id,),
            ).fetchone()
            if existing is None:
                conn.execute(
                    """
                    INSERT INTO source_versions (source_id, path, hash, size, last_seen_at, last_processed_at)
                    VALUES (?, ?, ?, ?, ?, '')
                    """,
                    (source_id, path, hash, size, now),
                )
            else:
                conn.execute(
                    """
                    UPDATE source_versions
                    SET path = ?, hash = ?, size = ?, last_seen_at = ?
                    WHERE source_id = ?
                    """,
                    (path, hash, size, now, source_id),
                )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM source_versions WHERE source_id = ?",
                (source_id,),
            ).fetchone()
        return _row_to_dict(row)

    def get(self, source_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            init_sync_tables(conn)
            row = conn.execute(
                "SELECT * FROM source_versions WHERE source_id = ?",
                (source_id,),
            ).fetchone()
        return _row_to_dict(row) if row else None

    def list_changed(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            init_sync_tables(conn)
            rows = conn.execute(
                """
                SELECT * FROM source_versions
                WHERE last_seen_at > last_processed_at
                ORDER BY last_seen_at ASC
                """
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def mark_processed(self, source_id: str) -> None:
        with self._connect() as conn:
            init_sync_tables(conn)
            conn.execute(
                "UPDATE source_versions SET last_processed_at = ? WHERE source_id = ?",
                (_now_iso(), source_id),
            )
            conn.commit()

    def touch_seen(self, source_id: str) -> None:
        with self._connect() as conn:
            init_sync_tables(conn)
            conn.execute(
                "UPDATE source_versions SET last_seen_at = ? WHERE source_id = ?",
                (_now_iso(), source_id),
            )
            conn.commit()


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any]:
    if row is None:
        return {}
    return {key: row[key] for key in row.keys()}


class IncrementalSync:
    def __init__(self, settings: Settings | None = None, store: SourceVersionStore | None = None) -> None:
        self.settings = settings or load_settings()
        self.store = store or SourceVersionStore(self.settings)

    def scan(self, roots: list[str]) -> dict[str, Any]:
        scanned = 0
        changes: list[str] = []
        for root in roots:
            root_path = Path(root).expanduser()
            if not root_path.exists():
                continue
            if root_path.is_file():
                files = [root_path]
            else:
                files = [
                    p
                    for p in root_path.rglob("*")
                    if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
                ]
            for file_path in files:
                scanned += 1
                source_id = hashlib.sha1(str(file_path.resolve()).encode("utf-8")).hexdigest()
                hash_val = file_sha256(file_path)
                size = file_path.stat().st_size
                existing = self.store.get(source_id)
                if not existing or existing.get("hash") != hash_val:
                    self.store.upsert(source_id, str(file_path.resolve()), hash_val, size)
                    changes.append(source_id)
                else:
                    self.store.touch_seen(source_id)
        return {"scanned": scanned, "changed": len(changes), "changes": changes}

    def get_changed_paths(self) -> list[str]:
        return [item["path"] for item in self.store.list_changed()]

    def mark_processed(self, source_ids: list[str]) -> None:
        for source_id in source_ids:
            self.store.mark_processed(source_id)
