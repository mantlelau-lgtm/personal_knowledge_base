from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from common.checkpoint import Checkpoint
from common.config import Settings, load_settings
from common.file_ops import copy_unique, download_unique, ensure_dir, file_sha256, text_hash, unique_path
from common.logging_config import setup_logger

from .parsers import parse_to_markdown


SUPPORTED_EXTENSIONS = {
    ".md",
    ".markdown",
    ".txt",
    ".log",
    ".csv",
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".bmp",
    ".tiff",
}


@dataclass
class CollectionResult:
    raw_path: str
    parsed_path: str
    source: str
    status: str = "ok"


@dataclass
class DataCollector:
    settings: Settings | None = None

    def __post_init__(self) -> None:
        self.settings = self.settings or load_settings()
        self.logger = setup_logger("data_collection", self.settings)
        self.checkpoint = Checkpoint("collection", self.settings)

    def _raw_today_dir(self) -> Path:
        return ensure_dir(Path(self.settings.raw_dir) / datetime.now().strftime("%Y%m%d"))

    def collect_one(self, source: str | Path) -> CollectionResult:
        source_str = str(source)
        parsed_url = urlparse(source_str)
        if parsed_url.scheme in {"http", "https"}:
            raw_path = download_unique(source_str, self._raw_today_dir())
            key = text_hash(source_str + file_sha256(raw_path))
        else:
            src = Path(source_str)
            key = file_sha256(src)
            existing = self.checkpoint.get(key)
            if existing and Path(existing.get("parsed_path", "")).exists():
                return CollectionResult(existing["raw_path"], existing["parsed_path"], source_str, "skipped")
            raw_path = copy_unique(src, self._raw_today_dir())
        md_text = parse_to_markdown(raw_path)
        md_name = f"{raw_path.stem}.md"
        parsed_path = unique_path(self.settings.parsed_md_dir, md_name)
        parsed_path.write_text(md_text, encoding="utf-8")
        result = CollectionResult(str(raw_path), str(parsed_path), source_str)
        self.checkpoint.mark_done(key, result.__dict__)
        self.logger.info("collected %s -> %s", source_str, parsed_path)
        return result

    def collect(self, sources: list[str | Path]) -> list[CollectionResult]:
        results: list[CollectionResult] = []
        for source in sources:
            source_str = str(source)
            parsed_url = urlparse(source_str)
            if parsed_url.scheme in {"http", "https"}:
                results.append(self.collect_one(source_str))
                continue
            path = Path(source_str).expanduser()
            if path.is_dir():
                results.extend(self.collect_directory(path))
            else:
                results.append(self.collect_one(path))
        return results

    def collect_directory(self, directory: str | Path, recursive: bool = True) -> list[CollectionResult]:
        root = Path(directory).expanduser()
        pattern = "**/*" if recursive else "*"
        files = [path for path in root.glob(pattern) if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS]
        return [self.collect_one(path) for path in sorted(files)]

    def collect_uploaded_file(self, filename: str, content: bytes) -> CollectionResult:
        raw_path = unique_path(self._raw_today_dir(), Path(filename).name)
        raw_path.write_bytes(content)
        key = text_hash(f"upload:{filename}:{file_sha256(raw_path)}")
        existing = self.checkpoint.get(key)
        if existing and Path(existing.get("parsed_path", "")).exists():
            return CollectionResult(existing["raw_path"], existing["parsed_path"], filename, "skipped")
        md_text = parse_to_markdown(raw_path)
        parsed_path = unique_path(self.settings.parsed_md_dir, f"{raw_path.stem}.md")
        parsed_path.write_text(md_text, encoding="utf-8")
        result = CollectionResult(str(raw_path), str(parsed_path), filename)
        self.checkpoint.mark_done(key, result.__dict__)
        self.logger.info("uploaded %s -> %s", filename, parsed_path)
        return result
