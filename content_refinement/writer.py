from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from common.file_ops import read_text
from data_parsing.processor import dump_front_matter, parse_front_matter

from .merge_engine import merge_metadata


def add_wiki_links(text: str, entities: list[str]) -> str:
    linked: list[str] = []
    for entity in entities[:10]:
        entity = str(entity).strip()
        if len(entity) < 2 or entity in linked:
            continue
        pattern = re.compile(rf"(?<!\[)({re.escape(entity)})(?!\]\])", re.IGNORECASE)
        text, count = pattern.subn(r"[[\1]]", text, count=1)
        if count:
            linked.append(entity)
    return text


class WikiWriter:
    def write(
        self,
        wiki_path: Path,
        metadata: dict[str, Any],
        body: str,
        category: str,
        source_path: Path,
        match_reason: str = "",
    ) -> Path:
        if wiki_path.exists():
            current = read_text(wiki_path)
            merged_metadata = merge_metadata(current, metadata)
            _, current_body = parse_front_matter(current)
            source_marker = f"processed_md/{source_path.name}"
            if source_marker in current_body:
                return wiki_path
            new_body = current_body.rstrip() + "\n\n" + self._source_section(metadata, body, source_path)
            wiki_path.write_text(dump_front_matter(merged_metadata) + new_body.strip() + "\n", encoding="utf-8")
            return wiki_path

        wiki_path.parent.mkdir(parents=True, exist_ok=True)
        initial_metadata = dict(metadata)
        initial_metadata["category"] = category
        initial_metadata["match_reason"] = match_reason
        article = self._article_body(metadata, body, source_path)
        wiki_path.write_text(dump_front_matter(initial_metadata) + article, encoding="utf-8")
        return wiki_path

    def _article_body(self, metadata: dict[str, Any], body: str, source_path: Path) -> str:
        topic = str(metadata.get("core_topic") or source_path.stem)
        knowledge = metadata.get("knowledge") or {}
        entities = [str(x) for x in metadata.get("related_entities", [])]
        return "\n".join(
            [
                f"# {topic}",
                "",
                "## 摘要",
                str(knowledge.get("summary") or topic),
                "",
                "## 核心概念",
                self._list_dicts(knowledge.get("concepts", []), "name", "description"),
                "",
                "## 关键事实 / Claims",
                self._list_dicts(knowledge.get("claims", []), "text", "evidence"),
                "",
                "## 决策记录",
                self._list_dicts(knowledge.get("decisions", []), "what", "why"),
                "",
                "## 行动项",
                self._list_dicts(knowledge.get("action_items", []), "task", "owner"),
                "",
                "## 相关实体",
                "\n".join(f"- [[{entity}]]" for entity in entities[:30]) or "- 暂无",
                "",
                "## 关联主题",
                "\n".join(f"- [[{topic}]]" for topic in knowledge.get("topics", [])[:20]) or "- 暂无",
                self._source_section(metadata, body, source_path),
            ]
        ).strip() + "\n"

    def _source_section(self, metadata: dict[str, Any], body: str, source_path: Path) -> str:
        entities = [str(x) for x in metadata.get("related_entities", [])]
        linked_body = add_wiki_links(body.strip(), entities)
        return f"\n## 来源：{source_path.stem}\n\n{linked_body}\n\n> 源文档：[{source_path.name}](../../processed_md/{source_path.name})\n"

    @staticmethod
    def _list_dicts(items: list[Any], title_key: str, detail_key: str) -> str:
        lines: list[str] = []
        for item in items[:30]:
            if isinstance(item, dict):
                title = str(item.get(title_key, "")).strip()
                detail = str(item.get(detail_key, "")).strip()
                if title:
                    lines.append(f"- {title}" + (f"：{detail}" if detail else ""))
            elif str(item).strip():
                lines.append(f"- {item}")
        return "\n".join(lines) or "- 暂无"
