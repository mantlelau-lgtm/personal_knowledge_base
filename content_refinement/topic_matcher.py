from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from common.config import Settings, load_settings
from common.embedding import EmbeddingTool, tokenize
from common.file_ops import read_text
from data_parsing.processor import parse_front_matter


def slugify(value: str) -> str:
    value = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", value).strip("_")
    return value[:80] or "untitled"


@dataclass
class TopicDecision:
    action: str
    target_path: Path
    score: float
    reason: str


@dataclass
class TopicMatcher:
    settings: Settings | None = None
    embedding_tool: EmbeddingTool | None = None
    overlap_threshold: float = 0.30
    vector_threshold: float = 0.72
    max_cluster_size: int = 8

    def __post_init__(self) -> None:
        self.settings = self.settings or load_settings()
        self.embedding_tool = self.embedding_tool or EmbeddingTool.from_settings(self.settings)

    def decide(self, category_dir: Path, topic: str, metadata: dict[str, Any], body: str) -> TopicDecision:
        desired_path = category_dir / f"{slugify(topic)}.md"
        if desired_path.exists():
            if self._cluster_size(desired_path) < self.max_cluster_size:
                return TopicDecision("merge", desired_path, 1.0, "same_slug")

        query_text = self._topic_text(topic, metadata, body)
        query_tokens = set(tokenize(query_text))
        query_embedding = self.embedding_tool.embed(query_text)
        best_path: Path | None = None
        best_score = 0.0
        best_reason = "new_topic"

        for candidate in sorted(category_dir.glob("*.md")):
            if self._cluster_size(candidate) >= self.max_cluster_size:
                continue
            candidate_text = read_text(candidate)
            candidate_meta, candidate_body = parse_front_matter(candidate_text)
            candidate_topic = str(candidate_meta.get("core_topic") or candidate.stem)
            candidate_knowledge = candidate_meta.get("knowledge") or {}
            candidate_text_for_match = self._topic_text(candidate_topic, candidate_meta, candidate_body)
            overlap = self._overlap(query_tokens, set(tokenize(candidate_text_for_match)))
            vector = self.embedding_tool.cosine(query_embedding, self.embedding_tool.embed(candidate_text_for_match))
            score = max(overlap, vector)
            reason = f"overlap={overlap:.3f}, vector={vector:.3f}"
            if score > best_score:
                best_path = candidate
                best_score = score
                best_reason = reason

        if best_path and best_score >= self.vector_threshold:
            return TopicDecision("merge", best_path, best_score, best_reason)
        if best_path and best_score >= self.overlap_threshold and "overlap" in best_reason:
            return TopicDecision("merge", best_path, best_score, best_reason)
        create_path = desired_path
        if create_path.exists():
            counter = 2
            while True:
                alt = category_dir / f"{slugify(topic)}_{counter}.md"
                if not alt.exists():
                    create_path = alt
                    break
                counter += 1
        return TopicDecision("create", create_path, best_score, best_reason)

    def _cluster_size(self, path: Path) -> int:
        try:
            text = read_text(path)
        except FileNotFoundError:
            return 0
        metadata, body = parse_front_matter(text)
        knowledge = metadata.get("knowledge") or {}
        claims = knowledge.get("claims") or []
        source_sections = body.count("## 来源：")
        return max(len(claims), source_sections)

    @staticmethod
    def _topic_text(topic: str, metadata: dict[str, Any], body: str) -> str:
        knowledge = metadata.get("knowledge") or {}
        parts = [topic, str(metadata.get("core_topic", "")), " ".join(map(str, metadata.get("key_points", []))), " ".join(map(str, metadata.get("related_entities", []))), str(knowledge.get("summary", "")), " ".join(map(str, knowledge.get("topics", []))), body[:1000]]
        for key in ("concepts", "entities", "claims", "decisions", "action_items", "connections"):
            for item in knowledge.get(key, []):
                if isinstance(item, dict):
                    parts.extend(str(v) for v in item.values())
                else:
                    parts.append(str(item))
        return "\n".join(parts)

    @staticmethod
    def _overlap(a: set[str], b: set[str]) -> float:
        if not a or not b:
            return 0.0
        return len(a & b) / max(1, min(len(a), len(b)))
