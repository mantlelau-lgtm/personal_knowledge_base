from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from common.config import Settings, load_settings
from common.file_ops import ensure_dir, read_text
from common.logging_config import setup_logger
from data_parsing.processor import parse_front_matter


INDEX_SUBDIR = "_index"


@dataclass
class MarkdownIndexer:
    settings: Settings | None = None

    def __post_init__(self) -> None:
        self.settings = self.settings or load_settings()
        self.logger = setup_logger("content_refinement", self.settings)
        self.wiki_dir = Path(self.settings.wiki_dir)
        self.index_dir = ensure_dir(self.wiki_dir / INDEX_SUBDIR)

    def _iter_wiki_files(self) -> list[Path]:
        results: list[Path] = []
        for path in sorted(self.wiki_dir.glob("**/*.md")):
            try:
                path.relative_to(self.index_dir)
            except ValueError:
                results.append(path)
        return results

    def _load_docs(self) -> list[tuple[Path, dict[str, Any], str]]:
        docs: list[tuple[Path, dict[str, Any], str]] = []
        for path in self._iter_wiki_files():
            text = read_text(path)
            metadata, body = parse_front_matter(text)
            docs.append((path, metadata, body))
        return docs

    def _rel_link(self, path: Path) -> str:
        rel = Path("..") / path.relative_to(self.wiki_dir)
        return rel.as_posix()

    def _title(self, path: Path, metadata: dict[str, Any]) -> str:
        return str(metadata.get("core_topic") or path.stem)

    def update(self) -> dict[str, int]:
        docs = self._load_docs()

        # master: 按分类目录（相对 wiki_dir 的第一层目录）分组
        master_groups: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for path, metadata, _body in docs:
            rel_parts = path.relative_to(self.wiki_dir).parts
            category = rel_parts[0] if len(rel_parts) > 1 else "_root"
            master_groups[category].append((self._title(path, metadata), self._rel_link(path)))

        master_lines: list[str] = ["# Master Index", ""]
        master_count = 0
        for category in sorted(master_groups):
            master_lines.append(f"## {category}")
            master_lines.append("")
            for title, link in sorted(master_groups[category]):
                master_lines.append(f"- [{title}]({link})")
                master_count += 1
            master_lines.append("")
        (self.index_dir / "master-index.md").write_text("\n".join(master_lines).rstrip() + "\n", encoding="utf-8")

        # topic-index: 按 knowledge.topics 分组
        topic_groups: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for path, metadata, _body in docs:
            knowledge = metadata.get("knowledge") or {}
            topics = [str(t).strip() for t in knowledge.get("topics", []) if str(t).strip()]
            if not topics:
                topics = ["未分类"]
            for topic in topics:
                topic_groups[topic].append((self._title(path, metadata), self._rel_link(path)))

        topic_lines: list[str] = ["# Topic Index", ""]
        topic_count = 0
        for topic in sorted(topic_groups):
            topic_lines.append(f"## {topic}")
            topic_lines.append("")
            seen: set[tuple[str, str]] = set()
            for title, link in sorted(topic_groups[topic]):
                if (title, link) in seen:
                    continue
                seen.add((title, link))
                topic_lines.append(f"- [{title}]({link})")
                topic_count += 1
            topic_lines.append("")
        (self.index_dir / "topic-index.md").write_text("\n".join(topic_lines).rstrip() + "\n", encoding="utf-8")

        # longtail-index: 按 knowledge.entities 出现频次排序
        entity_counts: Counter[str] = Counter()
        entity_docs: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for path, metadata, _body in docs:
            knowledge = metadata.get("knowledge") or {}
            for entity in knowledge.get("entities", []):
                if isinstance(entity, dict):
                    name = str(entity.get("name", "")).strip()
                else:
                    name = str(entity).strip()
                if not name:
                    continue
                entity_counts[name] += 1
                entry = (self._title(path, metadata), self._rel_link(path))
                if entry not in entity_docs[name]:
                    entity_docs[name].append(entry)

        longtail_lines: list[str] = ["# Longtail Index", ""]
        longtail_count = 0
        for name, count in sorted(entity_counts.items(), key=lambda item: (-item[1], item[0])):
            if count < 1:
                continue
            longtail_lines.append(f"## {name} ({count})")
            longtail_lines.append("")
            for title, link in entity_docs[name]:
                longtail_lines.append(f"- [{title}]({link})")
            longtail_lines.append("")
            longtail_count += 1
        (self.index_dir / "longtail-index.md").write_text("\n".join(longtail_lines).rstrip() + "\n", encoding="utf-8")

        stats = {"master": master_count, "topic": topic_count, "longtail": longtail_count}
        self.logger.info("markdown indexes updated: %s", stats)
        return stats


def build_markdown_indexes(settings: Settings | None = None) -> dict[str, int]:
    return MarkdownIndexer(settings).update()
