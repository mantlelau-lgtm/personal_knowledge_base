from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from common.config import Settings, load_settings
from common.db import connect_db


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def init_access_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            name TEXT,
            email TEXT,
            api_key TEXT UNIQUE,
            is_admin INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS scope_groups (
            id TEXT PRIMARY KEY,
            name TEXT,
            topics_json TEXT DEFAULT '[]',
            users_json TEXT DEFAULT '[]',
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS access_clients (
            client_id TEXT PRIMARY KEY,
            name TEXT,
            hmac_secret TEXT,
            callback_url TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS access_requests (
            id TEXT PRIMARY KEY,
            client_id TEXT,
            user_id TEXT,
            scope TEXT,
            status TEXT,
            purpose TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS access_grants (
            id TEXT PRIMARY KEY,
            request_id TEXT,
            client_id TEXT,
            user_id TEXT,
            scope TEXT,
            expires_at TEXT,
            created_at TEXT NOT NULL
        )
        """
    )


class AccessStore:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()
        with connect_db(self.settings) as conn:
            init_access_tables(conn)

    # -------------------- users --------------------
    def _user_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "email": row["email"],
            "api_key": row["api_key"],
            "is_admin": bool(row["is_admin"]),
            "created_at": row["created_at"],
        }

    def create_user(self, name: str, email: str = "", is_admin: bool = False) -> dict[str, Any]:
        user_id = _new_id("usr")
        api_key = f"pkb_{uuid.uuid4().hex}"
        now = _now()
        with connect_db(self.settings) as conn:
            init_access_tables(conn)
            conn.execute(
                "INSERT INTO users (id, name, email, api_key, is_admin, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, name, email, api_key, 1 if is_admin else 0, now),
            )
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return self._user_row_to_dict(row)

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        with connect_db(self.settings) as conn:
            init_access_tables(conn)
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return self._user_row_to_dict(row) if row else None

    def get_user_by_api_key(self, key: str) -> dict[str, Any] | None:
        if not key:
            return None
        with connect_db(self.settings) as conn:
            init_access_tables(conn)
            row = conn.execute("SELECT * FROM users WHERE api_key = ?", (key,)).fetchone()
        return self._user_row_to_dict(row) if row else None

    def list_users(self, limit: int = 100) -> list[dict[str, Any]]:
        with connect_db(self.settings) as conn:
            init_access_tables(conn)
            rows = conn.execute(
                "SELECT * FROM users ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._user_row_to_dict(row) for row in rows]

    # -------------------- scope_groups --------------------
    def _group_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "topics": json.loads(row["topics_json"] or "[]"),
            "users": json.loads(row["users_json"] or "[]"),
            "created_at": row["created_at"],
        }

    def create_scope_group(
        self, name: str, topics: list[str] | None = None, users: list[str] | None = None
    ) -> dict[str, Any]:
        gid = _new_id("sg")
        now = _now()
        with connect_db(self.settings) as conn:
            init_access_tables(conn)
            conn.execute(
                "INSERT INTO scope_groups (id, name, topics_json, users_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (
                    gid,
                    name,
                    json.dumps(topics or [], ensure_ascii=False),
                    json.dumps(users or [], ensure_ascii=False),
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM scope_groups WHERE id = ?", (gid,)).fetchone()
        return self._group_row_to_dict(row)

    def get_scope_group(self, gid: str) -> dict[str, Any] | None:
        with connect_db(self.settings) as conn:
            init_access_tables(conn)
            row = conn.execute("SELECT * FROM scope_groups WHERE id = ?", (gid,)).fetchone()
        return self._group_row_to_dict(row) if row else None

    def list_scope_groups(self, limit: int = 100) -> list[dict[str, Any]]:
        with connect_db(self.settings) as conn:
            init_access_tables(conn)
            rows = conn.execute(
                "SELECT * FROM scope_groups ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._group_row_to_dict(row) for row in rows]

    def update_scope_group(self, gid: str, **fields: Any) -> dict[str, Any] | None:
        if not fields:
            return self.get_scope_group(gid)
        columns: list[str] = []
        values: list[Any] = []
        for key, value in fields.items():
            if key == "topics":
                columns.append("topics_json = ?")
                values.append(json.dumps(value or [], ensure_ascii=False))
            elif key == "users":
                columns.append("users_json = ?")
                values.append(json.dumps(value or [], ensure_ascii=False))
            else:
                columns.append(f"{key} = ?")
                values.append(value)
        values.append(gid)
        with connect_db(self.settings) as conn:
            init_access_tables(conn)
            conn.execute(
                f"UPDATE scope_groups SET {', '.join(columns)} WHERE id = ?", tuple(values)
            )
        return self.get_scope_group(gid)

    # -------------------- access_clients --------------------
    def _client_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "client_id": row["client_id"],
            "name": row["name"],
            "hmac_secret": row["hmac_secret"],
            "callback_url": row["callback_url"],
            "created_at": row["created_at"],
        }

    def register_client(self, name: str, callback_url: str = "") -> dict[str, Any]:
        client_id = _new_id("cli")
        hmac_secret = uuid.uuid4().hex + uuid.uuid4().hex
        now = _now()
        with connect_db(self.settings) as conn:
            init_access_tables(conn)
            conn.execute(
                "INSERT INTO access_clients (client_id, name, hmac_secret, callback_url, created_at) VALUES (?, ?, ?, ?, ?)",
                (client_id, name, hmac_secret, callback_url, now),
            )
            row = conn.execute(
                "SELECT * FROM access_clients WHERE client_id = ?", (client_id,)
            ).fetchone()
        return self._client_row_to_dict(row)

    def get_client(self, cid: str) -> dict[str, Any] | None:
        with connect_db(self.settings) as conn:
            init_access_tables(conn)
            row = conn.execute(
                "SELECT * FROM access_clients WHERE client_id = ?", (cid,)
            ).fetchone()
        return self._client_row_to_dict(row) if row else None

    def list_clients(self, limit: int = 100) -> list[dict[str, Any]]:
        with connect_db(self.settings) as conn:
            init_access_tables(conn)
            rows = conn.execute(
                "SELECT * FROM access_clients ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._client_row_to_dict(row) for row in rows]

    # -------------------- access_requests --------------------
    def _request_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "client_id": row["client_id"],
            "user_id": row["user_id"],
            "scope": row["scope"],
            "status": row["status"],
            "purpose": row["purpose"],
            "created_at": row["created_at"],
        }

    def create_request(
        self, client_id: str, user_id: str, scope: str, purpose: str = ""
    ) -> dict[str, Any]:
        rid = _new_id("req")
        now = _now()
        with connect_db(self.settings) as conn:
            init_access_tables(conn)
            conn.execute(
                "INSERT INTO access_requests (id, client_id, user_id, scope, status, purpose, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (rid, client_id, user_id, scope, "pending", purpose, now),
            )
            row = conn.execute("SELECT * FROM access_requests WHERE id = ?", (rid,)).fetchone()
        return self._request_row_to_dict(row)

    def get_request(self, rid: str) -> dict[str, Any] | None:
        with connect_db(self.settings) as conn:
            init_access_tables(conn)
            row = conn.execute("SELECT * FROM access_requests WHERE id = ?", (rid,)).fetchone()
        return self._request_row_to_dict(row) if row else None

    def list_requests(
        self, user_id: str | None = None, status: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        values: list[Any] = []
        if user_id:
            clauses.append("user_id = ?")
            values.append(user_id)
        if status:
            clauses.append("status = ?")
            values.append(status)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        values.append(limit)
        with connect_db(self.settings) as conn:
            init_access_tables(conn)
            rows = conn.execute(
                f"SELECT * FROM access_requests{where} ORDER BY created_at DESC LIMIT ?",
                tuple(values),
            ).fetchall()
        return [self._request_row_to_dict(row) for row in rows]

    def update_request(self, rid: str, **fields: Any) -> dict[str, Any] | None:
        if not fields:
            return self.get_request(rid)
        columns: list[str] = []
        values: list[Any] = []
        for key, value in fields.items():
            columns.append(f"{key} = ?")
            values.append(value)
        values.append(rid)
        with connect_db(self.settings) as conn:
            init_access_tables(conn)
            conn.execute(
                f"UPDATE access_requests SET {', '.join(columns)} WHERE id = ?", tuple(values)
            )
        return self.get_request(rid)

    # -------------------- access_grants --------------------
    def _grant_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "request_id": row["request_id"],
            "client_id": row["client_id"],
            "user_id": row["user_id"],
            "scope": row["scope"],
            "expires_at": row["expires_at"],
            "created_at": row["created_at"],
        }

    def create_grant(
        self,
        request_id: str,
        client_id: str,
        user_id: str,
        scope: str,
        ttl_days: int = 7,
    ) -> dict[str, Any]:
        gid = _new_id("grt")
        now_dt = datetime.now(timezone.utc)
        expires_at = (now_dt + timedelta(days=ttl_days)).isoformat()
        now = now_dt.isoformat()
        with connect_db(self.settings) as conn:
            init_access_tables(conn)
            conn.execute(
                "INSERT INTO access_grants (id, request_id, client_id, user_id, scope, expires_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (gid, request_id, client_id, user_id, scope, expires_at, now),
            )
            row = conn.execute("SELECT * FROM access_grants WHERE id = ?", (gid,)).fetchone()
        return self._grant_row_to_dict(row)

    def get_grant(self, gid: str) -> dict[str, Any] | None:
        with connect_db(self.settings) as conn:
            init_access_tables(conn)
            row = conn.execute("SELECT * FROM access_grants WHERE id = ?", (gid,)).fetchone()
        return self._grant_row_to_dict(row) if row else None

    def list_grants(
        self,
        user_id: str | None = None,
        client_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        values: list[Any] = []
        if user_id:
            clauses.append("user_id = ?")
            values.append(user_id)
        if client_id:
            clauses.append("client_id = ?")
            values.append(client_id)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        values.append(limit)
        with connect_db(self.settings) as conn:
            init_access_tables(conn)
            rows = conn.execute(
                f"SELECT * FROM access_grants{where} ORDER BY created_at DESC LIMIT ?",
                tuple(values),
            ).fetchall()
        return [self._grant_row_to_dict(row) for row in rows]

    def revoke_grant(self, gid: str) -> None:
        with connect_db(self.settings) as conn:
            init_access_tables(conn)
            conn.execute("DELETE FROM access_grants WHERE id = ?", (gid,))
