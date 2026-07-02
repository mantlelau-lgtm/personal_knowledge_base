from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone


def sign(secret: str, method: str, path: str, timestamp: str, body: str) -> str:
    payload = f"{method}\n{path}\n{timestamp}\n{body}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def _parse_timestamp(timestamp: str) -> float | None:
    if not timestamp:
        return None
    ts = timestamp.strip()
    try:
        return float(ts)
    except ValueError:
        pass
    try:
        # Support ISO-8601 timestamps, allowing trailing 'Z'
        iso = ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        return None


def verify(
    secret: str,
    method: str,
    path: str,
    timestamp: str,
    body: str,
    signature: str,
    max_skew_seconds: int = 300,
) -> bool:
    ts = _parse_timestamp(timestamp)
    if ts is None:
        return False
    now = datetime.now(timezone.utc).timestamp()
    if abs(now - ts) >= max_skew_seconds:
        return False
    expected = sign(secret, method, path, timestamp, body)
    try:
        return hmac.compare_digest(expected, signature or "")
    except Exception:
        return False
