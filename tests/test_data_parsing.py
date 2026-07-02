from pathlib import Path

from data_parsing.extract_schema import merge_extracted_knowledge, normalize_extracted_knowledge
from data_parsing.processor import MarkdownProcessor, parse_front_matter, split_markdown


def test_split_markdown_respects_size():
    text = "# Title\n\n" + ("abc " * 400)
    chunks = split_markdown(text, 120)
    assert chunks
    assert all(len(chunk) <= 120 for chunk in chunks)


def test_process_file_writes_front_matter(settings):
    src = Path(settings.parsed_md_dir) / "note.md"
    src.write_text("# Python\n\nPython pytest RAG content.", encoding="utf-8")
    result = MarkdownProcessor(settings).process_file(src)
    processed = Path(result.processed_path)
    assert processed.exists()
    assert not src.exists()
    metadata, body = parse_front_matter(processed.read_text(encoding="utf-8"))
    assert metadata["core_topic"]
    assert "key_points" in metadata
    assert "knowledge" in metadata
    assert "concepts" in metadata["knowledge"]
    assert "claims" in metadata["knowledge"]
    assert "Python" in body


def test_extract_schema_normalizes_legacy_summary():
    data = normalize_extracted_knowledge(
        {
            "core_topic": "RAG",
            "key_points": ["混合检索"],
            "related_entities": ["向量", {"name": "LLM", "type": "model"}],
        }
    )
    assert data["summary"] == "RAG"
    assert data["claims"][0]["text"] == "混合检索"
    assert data["entities"][0]["name"] == "向量"


def test_merge_extracted_knowledge_deduplicates_items():
    merged = merge_extracted_knowledge(
        [
            {"summary": "A", "topics": ["RAG"], "claims": [{"text": "事实", "evidence": "文档"}]},
            {"summary": "B", "topics": ["RAG"], "claims": [{"text": "事实", "evidence": "文档"}]},
        ]
    )
    assert merged["summary"] == "A"
    assert merged["topics"] == ["RAG"]
    assert len(merged["claims"]) == 1
