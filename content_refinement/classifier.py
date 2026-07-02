from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from common.config import Settings, load_categories, load_settings
from common.file_ops import ensure_dir, read_text
from data_parsing.processor import parse_front_matter


@dataclass
class Classification:
    category: str
    matched_rule: str | None = None


@dataclass
class Classifier:
    settings: Settings | None = None

    def __post_init__(self) -> None:
        self.settings = self.settings or load_settings()
        self.categories = load_categories(self.settings.categories_file)

    def classify_text(self, text: str, metadata: dict) -> Classification:
        knowledge = metadata.get("knowledge") or {}
        haystack_parts = [
            text,
            str(metadata.get("core_topic", "")),
            " ".join(map(str, metadata.get("key_points", []))),
            " ".join(map(str, metadata.get("related_entities", []))),
            str(knowledge.get("summary", "")),
            " ".join(map(str, knowledge.get("topics", []))),
        ]
        for key in ("concepts", "entities", "claims", "decisions", "action_items", "connections"):
            for item in knowledge.get(key, []):
                if isinstance(item, dict):
                    haystack_parts.extend(str(v) for v in item.values())
                else:
                    haystack_parts.append(str(item))
        haystack = " ".join(haystack_parts).lower()
        for category, rules in self.categories.items():
            for rule in rules:
                if rule and str(rule).lower() in haystack:
                    return Classification(category=category, matched_rule=str(rule))
        topic = str(metadata.get("core_topic") or "temp").strip()
        safe = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", topic)[:30].strip("_") or "temp"
        return Classification(category=f"temp/{safe}", matched_rule=None)

    def classify_file(self, path: str | Path) -> Classification:
        text = read_text(path)
        metadata, body = parse_front_matter(text)
        return self.classify_text(body, metadata)

    def category_dir(self, classification: Classification) -> Path:
        return ensure_dir(Path(self.settings.wiki_dir) / classification.category)
