from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, TypeVar

from common.config import Settings, load_settings
from common.db import connect_db, row_to_dict

T = TypeVar("T")


@dataclass
class LLMGateway:
    settings: Settings | None = None

    def __post_init__(self) -> None:
        self.settings = self.settings or load_settings()

    def record_call(
        self,
        provider: str,
        model: str,
        purpose: str,
        fn: Callable[[], T],
        prompt_tokens: int = 0,
    ) -> T:
        started = time.time()
        status = "ok"
        error = ""
        completion_tokens = 0
        try:
            result = fn()
            completion_tokens = self._estimate_tokens(result)
            return result
        except Exception as exc:
            status = "error"
            error = str(exc)
            raise
        finally:
            latency_ms = int((time.time() - started) * 1000)
            self.log_call(
                provider=provider,
                model=model,
                purpose=purpose,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                latency_ms=latency_ms,
                status=status,
                error=error,
            )

    def log_call(
        self,
        provider: str,
        model: str,
        purpose: str,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: int,
        status: str,
        error: str = "",
    ) -> None:
        with connect_db(self.settings) as conn:
            conn.execute(
                """
                INSERT INTO llm_call_logs (
                    provider, model, purpose, prompt_tokens, completion_tokens,
                    cost_usd, latency_ms, status, error, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    provider,
                    model,
                    purpose,
                    prompt_tokens,
                    completion_tokens,
                    self._estimate_cost(prompt_tokens, completion_tokens),
                    latency_ms,
                    status,
                    error,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def recent_calls(self, limit: int = 20) -> list[dict]:
        with connect_db(self.settings) as conn:
            rows = conn.execute("SELECT * FROM llm_call_logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [row_to_dict(row) for row in rows]

    @staticmethod
    def _estimate_tokens(value) -> int:
        if isinstance(value, str):
            return max(1, len(value) // 4)
        return max(1, len(str(value)) // 4)

    @staticmethod
    def _estimate_cost(prompt_tokens: int, completion_tokens: int) -> float:
        return round((prompt_tokens + completion_tokens) / 1_000_000 * 0.5, 8)
