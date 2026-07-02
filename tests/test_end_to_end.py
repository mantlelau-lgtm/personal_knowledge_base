from pathlib import Path

from content_refinement.refiner import ContentRefiner
from data_collection.collector import DataCollector
from data_parsing.processor import MarkdownProcessor
from rag_chat.chat import RAGChat


def test_end_to_end(settings, tmp_path):
    source = tmp_path / "python_note.txt"
    source.write_text("Python pytest 可用于本地测试。RAG 检索需要索引。", encoding="utf-8")

    collected = DataCollector(settings).collect([source])
    assert collected and Path(collected[0].parsed_path).exists()

    processed = MarkdownProcessor(settings).process_all()
    assert processed and Path(processed[0].processed_path).exists()

    refined = ContentRefiner(settings).refine_all()
    assert refined and Path(refined[0].wiki_path).exists()

    response = RAGChat(settings).ask("pytest 和 RAG", top_k=2)
    assert response.sources
    assert "引用" in response.answer
