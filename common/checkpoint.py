from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import Settings, load_settings
from .file_ops import read_json, write_json


@dataclass
class Checkpoint:
    name: str
    settings: Settings | None = None

    def __post_init__(self) -> None:
        self.settings = self.settings or load_settings()
        self.path = Path(self.settings.checkpoint_dir) / f"{self.name}.json"
        self._data: dict[str, Any] = dict(read_json(self.path, default={}))

    def key(self, value: str) -> str:
        return value

    def is_done(self, key: str) -> bool:
        return key in self._data

    def mark_done(self, key: str, payload: Any | None = None) -> None:
        self._data[key] = payload if payload is not None else {"done": True}
        write_json(self.path, self._data)

    def get(self, key: str, default: Any | None = None) -> Any:
        return self._data.get(key, default)

    def all(self) -> dict[str, Any]:
        return dict(self._data)
