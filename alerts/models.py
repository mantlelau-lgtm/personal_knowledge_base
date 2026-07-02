from __future__ import annotations

from dataclasses import dataclass, field


LEVEL_P1 = "P1"
LEVEL_P2 = "P2"
LEVEL_INFO = "INFO"

ALLOWED_LEVELS = (LEVEL_P1, LEVEL_P2, LEVEL_INFO)


@dataclass
class Alert:
    id: str
    level: str
    event: str
    message: str
    data: dict = field(default_factory=dict)
    created_at: str = ""
    resolved: bool = False
