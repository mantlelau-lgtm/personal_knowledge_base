from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from common.config import Settings, load_settings
from common.file_ops import read_text
from common.logging_config import setup_logger
from data_parsing.processor import parse_front_matter

from .classifier import Classifier
from .indexer import Indexer
from .markdown_index import MarkdownIndexer
from .topic_matcher import TopicMatcher
from .writer import WikiWriter


@dataclass
class RefinementResult:
    processed_path: str
    wiki_path: str
    category: str
    status: str = "ok"


@dataclass
class ContentRefiner:
    settings: Settings | None = None

    def __post_init__(self) -> None:
        self.settings = self.settings or load_settings()
        self.classifier = Classifier(self.settings)
        self.matcher = TopicMatcher(self.settings)
        self.writer = WikiWriter()
        self.indexer = Indexer(self.settings)
        self.logger = setup_logger("content_refinement", self.settings)

    def refine_file(self, path: str | Path) -> RefinementResult:
        src = Path(path)
        text = read_text(src)
        metadata, body = parse_front_matter(text)
        classification = self.classifier.classify_text(body, metadata)
        category_dir = self.classifier.category_dir(classification)
        topic = str(metadata.get("core_topic") or src.stem)
        decision = self.matcher.decide(category_dir, topic, metadata, body)
        wiki_path = self.writer.write(
            decision.target_path,
            metadata,
            body,
            classification.category,
            src,
            decision.reason,
        )
        self.logger.info("refined %s -> %s (%s %.3f)", src, wiki_path, decision.action, decision.score)
        return RefinementResult(str(src), str(wiki_path), classification.category)

    def refine_all(self) -> list[RefinementResult]:
        results = [self.refine_file(path) for path in sorted(Path(self.settings.processed_md_dir).glob("*.md"))]
        self.indexer.update_indexes()
        MarkdownIndexer(self.settings).update()
        return results
