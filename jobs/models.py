from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4


UTC = timezone.utc


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class Job:
    id: str
    type: str
    status: str
    stage: str
    total: int = 0
    current: int = 0
    input: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    retry_count: int = 0
    max_retries: int = 2
    lease_until: str = ""
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    @classmethod
    def new(cls, job_type: str, input_data: dict[str, Any] | None = None) -> "Job":
        return cls(
            id=uuid4().hex,
            type=job_type,
            status="pending",
            stage="pending",
            input=input_data or {},
        )

    def leased(self, seconds: int = 900) -> "Job":
        self.lease_until = (datetime.now(UTC) + timedelta(seconds=seconds)).isoformat()
        return self
