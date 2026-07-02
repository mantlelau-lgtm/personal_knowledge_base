from pathlib import Path

from content_refinement.classifier import Classifier
from content_refinement.indexer import Indexer
from content_refinement.refiner import ContentRefiner
from content_refinement.topic_matcher import TopicMatcher
from data_parsing.processor import dump_front_matter


def test_classifier_uses_rules(settings):
    classifier = Classifier(settings)
    result = classifier.classify_text("This document is about Python", {"key_points": []})
    assert result.category == "python"


def test_classifier_uses_structured_knowledge(settings):
    classifier = Classifier(settings)
    result = classifier.classify_text(
        "",
        {
            "knowledge": {
                "summary": "测试知识",
                "topics": ["pytest"],
                "concepts": [{"name": "Python", "description": "语言"}],
            }
        },
    )
    assert result.category == "python"


def test_topic_matcher_merges_similar_topic(settings):
    category_dir = Path(settings.wiki_dir) / "python"
    category_dir.mkdir(parents=True)
    existing = category_dir / "Python_pytest.md"
    existing.write_text(
        dump_front_matter(
            {
                "core_topic": "Python pytest",
                "knowledge": {
                    "summary": "Python pytest testing",
                    "topics": ["Python pytest"],
                    "concepts": [{"name": "pytest", "description": "测试框架"}],
                    "entities": [],
                    "claims": [],
                    "decisions": [],
                    "action_items": [],
                    "connections": [],
                },
            }
        )
        + "# Python pytest\n\nPython pytest testing",
        encoding="utf-8",
    )
    decision = TopicMatcher(settings).decide(
        category_dir,
        "Python testing",
        {"core_topic": "Python testing", "key_points": ["pytest testing"], "related_entities": ["Python", "pytest"]},
        "pytest testing with Python",
    )
    assert decision.action == "merge"
    assert decision.target_path == existing


def test_refine_and_index(settings):
    processed = Path(settings.processed_md_dir) / "note.md"
    processed.write_text(
        dump_front_matter(
            {
                "core_topic": "Python pytest",
                "key_points": ["Python testing"],
                "related_entities": ["Python", "pytest"],
                "knowledge": {
                    "summary": "Python pytest testing",
                    "concepts": [{"name": "Python", "description": "语言"}],
                    "entities": [{"name": "Python", "type": "concept"}],
                    "decisions": [],
                    "action_items": [],
                    "claims": [{"text": "Python testing", "evidence": "note"}],
                    "topics": ["Python pytest"],
                    "connections": [],
                },
            }
        )
        + "# Python pytest\n\nPython and pytest are useful.",
        encoding="utf-8",
    )
    results = ContentRefiner(settings).refine_all()
    assert results[0].category == "python"
    wiki_path = Path(results[0].wiki_path)
    assert wiki_path.exists()
    wiki_text = wiki_path.read_text(encoding="utf-8")
    assert "## 核心概念" in wiki_text
    assert "## 关键事实 / Claims" in wiki_text
    assert "[[Python]]" in wiki_text
    stats = Indexer(settings).update_indexes()
    assert stats["documents"] >= 1
    assert (Path(settings.index_dir) / "fulltext_index.json").exists()
    assert (Path(settings.index_dir) / "vector_index.json").exists()
