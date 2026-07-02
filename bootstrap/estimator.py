from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from common.config import Settings, load_settings
from data_collection.collector import SUPPORTED_EXTENSIONS


TEXT_EXTS = {".md", ".markdown", ".txt", ".log", ".csv"}


@dataclass
class CostEstimator:
    settings: Settings | None = None
    price_per_million_tokens: float = 0.5

    def __post_init__(self) -> None:
        self.settings = self.settings or load_settings()

    def estimate(self, sources: list[str]) -> dict[str, Any]:
        files = self._collect_files(sources)
        total_chars = 0
        for path in files:
            total_chars += self._file_chars(path)
        estimated_tokens = total_chars // 3
        estimated_cost_usd = round(estimated_tokens / 1_000_000 * self.price_per_million_tokens, 6)
        return {
            "total_files": len(files),
            "total_chars": total_chars,
            "estimated_tokens": estimated_tokens,
            "estimated_cost_usd": estimated_cost_usd,
            "files": [str(p) for p in files[:20]],
        }

    def _collect_files(self, sources: list[str]) -> list[Path]:
        files: list[Path] = []
        for source in sources or []:
            source_str = str(source)
            parsed = urlparse(source_str)
            if parsed.scheme in {"http", "https"}:
                continue
            path = Path(source_str).expanduser()
            if path.is_dir():
                for candidate in path.rglob("*"):
                    if candidate.is_file() and candidate.suffix.lower() in SUPPORTED_EXTENSIONS:
                        files.append(candidate)
            elif path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
                files.append(path)
        return files

    @staticmethod
    def _file_chars(path: Path) -> int:
        suffix = path.suffix.lower()
        try:
            if suffix in TEXT_EXTS:
                return len(path.read_text(encoding="utf-8", errors="ignore"))
            return max(0, path.stat().st_size // 2)
        except Exception:
            return 0
