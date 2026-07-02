from pathlib import Path

from content_refinement.refiner import ContentRefiner
from data_parsing.processor import dump_front_matter
from rag_chat.iterative_search import IterativeSearch


def _build_wiki(settings):
    processed = Path(settings.processed_md_dir) / "rag.md"
    processed.write_text(
        dump_front_matter(
            {
                "core_topic": "RAG 检索",
                "key_points": ["RAG combines vector search and keyword search"],
                "related_entities": ["RAG", "向量"],
            }
        )
        + "# RAG 检索\n\nRAG 使用向量语义检索和关键词检索融合回答。",
        encoding="utf-8",
    )
    ContentRefiner(settings).refine_all()


def test_iterative_search_returns_results_and_trace(settings):
    _build_wiki(settings)
    results, trace = IterativeSearch(settings).search("RAG 向量检索", top_k=3)
    assert results
    assert trace
    assert trace[0]["query"] == "RAG 向量检索"
    assert trace[0]["hits"] >= 1
    assert "top_score" in trace[0]


def test_iterative_search_dedupes_across_rounds(settings):
    _build_wiki(settings)
    search = IterativeSearch(settings, max_rounds=3)
    results, trace = search.search("RAG", top_k=2)
    chunk_ids = [r.chunk_id for r in results]
    assert len(chunk_ids) == len(set(chunk_ids))
    assert len(trace) >= 1
