from pathlib import Path

from content_refinement.markdown_index import MarkdownIndexer, build_markdown_indexes
from data_parsing.processor import dump_front_matter


def _write_wiki(settings, category: str, filename: str, metadata: dict, body: str) -> Path:
    path = Path(settings.wiki_dir) / category / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_front_matter(metadata) + body, encoding="utf-8")
    return path


def test_markdown_indexer_update_generates_three_indexes(settings):
    _write_wiki(
        settings,
        "python",
        "rag.md",
        {
            "core_topic": "RAG 检索",
            "knowledge": {
                "topics": ["检索增强"],
                "entities": [{"name": "RAG", "type": "concept"}, {"name": "向量", "type": "concept"}],
            },
        },
        "# RAG 检索\n\n内容",
    )
    _write_wiki(
        settings,
        "ai",
        "llm.md",
        {
            "core_topic": "LLM 综述",
            "knowledge": {
                "topics": ["检索增强", "语言模型"],
                "entities": [{"name": "RAG", "type": "concept"}, {"name": "LLM", "type": "concept"}],
            },
        },
        "# LLM\n\n内容",
    )

    stats = MarkdownIndexer(settings).update()

    assert stats["master"] == 2
    assert stats["topic"] >= 2
    assert stats["longtail"] == 3

    index_dir = Path(settings.wiki_dir) / "_index"
    master = (index_dir / "master-index.md").read_text(encoding="utf-8")
    topic = (index_dir / "topic-index.md").read_text(encoding="utf-8")
    longtail = (index_dir / "longtail-index.md").read_text(encoding="utf-8")

    assert "## python" in master
    assert "## ai" in master
    assert "RAG 检索" in master
    assert "## 检索增强" in topic
    assert "RAG (2)" in longtail


def test_build_markdown_indexes_helper(settings):
    _write_wiki(
        settings,
        "python",
        "note.md",
        {"core_topic": "笔记", "knowledge": {"topics": ["Python"], "entities": [{"name": "Python"}]}},
        "# 笔记\n",
    )
    stats = build_markdown_indexes(settings)
    assert stats["master"] == 1
    assert stats["topic"] == 1
    assert stats["longtail"] == 1
