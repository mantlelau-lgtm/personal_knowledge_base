from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from common.checkpoint import Checkpoint
from common.config import Settings, load_settings
from common.file_ops import file_sha256, read_text, unique_path
from common.llm_client import LLMClient
from common.logging_config import setup_logger

from .extractor import KnowledgeExtractor


_FRONT_MATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
PROCESS_STATUS: dict[str, Any] = {"state": "idle"}


def split_markdown(text: str, max_size: int) -> list[str]:
    max_size = max(1, max_size)
    sections = re.split(r"(?=^#{1,6}\s+)", text, flags=re.MULTILINE)
    chunks: list[str] = []
    for section in sections:
        section = section.strip()
        if not section:
            continue
        if len(section) <= max_size:
            chunks.append(section)
            continue
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", section) if p.strip()]
        current = ""
        for paragraph in paragraphs:
            if len(paragraph) > max_size:
                if current:
                    chunks.append(current.strip())
                    current = ""
                for i in range(0, len(paragraph), max_size):
                    chunks.append(paragraph[i : i + max_size])
            elif len(current) + len(paragraph) + 2 <= max_size:
                current = f"{current}\n\n{paragraph}" if current else paragraph
            else:
                chunks.append(current.strip())
                current = paragraph
        if current:
            chunks.append(current.strip())
    return chunks or [text[:max_size]]


def _yaml_scalar(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def dump_front_matter(metadata: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in metadata.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                if isinstance(item, (dict, list)):
                    lines.append("  - " + json.dumps(item, ensure_ascii=False))
                else:
                    lines.append(f"  - {_yaml_scalar(item)}")
        elif isinstance(value, dict):
            lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
        else:
            lines.append(f"{key}: {_yaml_scalar(value)}")
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def parse_front_matter(text: str) -> tuple[dict[str, Any], str]:
    match = _FRONT_MATTER_RE.match(text)
    if not match:
        return {}, text
    body = text[match.end() :]
    meta_text = match.group(1)
    metadata: dict[str, Any] = {}
    current_key: str | None = None
    for raw in meta_text.splitlines():
        if not raw.strip():
            continue
        if raw.startswith("  - ") and current_key:
            item = raw[4:].strip()
            try:
                parsed_item = json.loads(item)
            except Exception:
                parsed_item = item.strip('"\'')
            metadata.setdefault(current_key, []).append(parsed_item)
            continue
        if ":" in raw:
            key, value = raw.split(":", 1)
            key = key.strip()
            value = value.strip()
            current_key = key
            if not value:
                metadata[key] = []
            else:
                try:
                    metadata[key] = json.loads(value)
                except Exception:
                    metadata[key] = value.strip('"\'')
    return metadata, body


@dataclass
class ProcessResult:
    source_path: str
    processed_path: str
    chunks: int
    status: str = "ok"


@dataclass
class MarkdownProcessor:
    settings: Settings | None = None
    llm_client: LLMClient | None = None

    def __post_init__(self) -> None:
        self.settings = self.settings or load_settings()
        self.llm_client = self.llm_client or LLMClient.from_settings(self.settings)
        self.extractor = KnowledgeExtractor(self.llm_client)
        self.logger = setup_logger("data_parsing", self.settings)
        self.checkpoint = Checkpoint("parsing", self.settings)

    def process_file(self, path: str | Path) -> ProcessResult:
        src = Path(path)
        started_at = time.time()
        PROCESS_STATUS.update({"state": "processing", "file": str(src), "chunk_index": 0, "chunk_total": 0, "started_at": started_at})
        key = file_sha256(src)
        existing = self.checkpoint.get(key)
        if existing and Path(existing.get("processed_path", "")).exists():
            PROCESS_STATUS.update({"state": "skipped", "file": str(src), "finished_at": time.time()})
            return ProcessResult(existing["source_path"], existing["processed_path"], existing.get("chunks", 0), "skipped")
        text = read_text(src)
        _, body = parse_front_matter(text)
        max_size = int(self.settings.llm_context_window / 4)
        chunks = split_markdown(body, max_size)
        PROCESS_STATUS.update({"chunk_total": len(chunks), "chunk_index": 0})
        extracted_chunks = []
        for index, chunk in enumerate(chunks, start=1):
            PROCESS_STATUS.update({"state": "llm_extracting", "file": str(src), "chunk_index": index, "chunk_total": len(chunks)})
            extracted_chunks.append(self.extractor.extract_chunk(chunk))
        knowledge = self.extractor.merge_chunks(extracted_chunks)
        key_points = [claim.get("text", "") for claim in knowledge.get("claims", []) if claim.get("text")]
        entities = []
        for entity in knowledge.get("entities", []):
            name = str(entity.get("name", "")).strip()
            if name and name not in entities:
                entities.append(name)
        topics = [str(x) for x in knowledge.get("topics", []) if str(x).strip()]
        metadata = {
            "source_file": src.name,
            "core_topic": topics[0] if topics else str(knowledge.get("summary") or src.stem),
            "key_points": key_points[:20],
            "related_entities": entities[:30],
            "knowledge": knowledge,
            "chunks": [{"index": i, "knowledge": item} for i, item in enumerate(extracted_chunks)],
        }
        dest = unique_path(self.settings.processed_md_dir, src.name)
        dest.write_text(dump_front_matter(metadata) + body.strip() + "\n", encoding="utf-8")
        try:
            src.unlink()
        except FileNotFoundError:
            pass
        result = ProcessResult(str(src), str(dest), len(chunks))
        self.checkpoint.mark_done(key, result.__dict__)
        PROCESS_STATUS.update({"state": "done", "file": str(src), "processed_path": str(dest), "finished_at": time.time(), "elapsed": round(time.time() - started_at, 3)})
        self.logger.info("processed %s -> %s", src, dest)
        return result

    def process_all(self) -> list[ProcessResult]:
        results: list[ProcessResult] = []
        for path in sorted(Path(self.settings.parsed_md_dir).glob("*.md")):
            results.append(self.process_file(path))
        return results
