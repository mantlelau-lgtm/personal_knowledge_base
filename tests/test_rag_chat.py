from pathlib import Path

from content_refinement.refiner import ContentRefiner
from content_refinement.indexer import Indexer
from data_parsing.processor import dump_front_matter
from rag_chat.api import ChatRequest, chat as api_chat, stream_chat
from rag_chat.chat import RAGChat
from rag_chat.retriever import HybridRetriever


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


def test_hybrid_retriever(settings):
    _build_wiki(settings)
    results = HybridRetriever(settings).search("RAG 向量检索", top_k=3)
    assert results
    assert results[0].chunk_id
    assert results[0].heading
    assert "RAG" in results[0].snippet or "检索" in results[0].snippet


def test_indexer_generates_chunk_indexes(settings):
    _build_wiki(settings)
    stats = Indexer(settings).update_indexes()
    assert stats["chunks"] >= 1


def test_rag_chat_stream(settings):
    _build_wiki(settings)
    chat = RAGChat(settings)
    response = chat.ask("RAG 如何检索？")
    assert response.sources
    assert response.session_id
    assert response.rewritten_query
    assert response.sources[0]["chunk_id"]
    assert response.sources[0]["heading"]
    assert "引用" in response.answer
    streamed = "".join(chat.stream_ask("向量呢？", session_id=response.session_id))
    assert streamed


def test_chat_session_persistence(settings):
    _build_wiki(settings)
    chat = RAGChat(settings)
    first = chat.ask("RAG 检索是什么？")
    second = chat.ask("向量呢？", session_id=first.session_id)
    assert first.session_id == second.session_id
    messages = chat.store.list_messages(first.session_id)
    roles = [m["role"] for m in messages]
    assert roles.count("user") == 2
    assert roles.count("assistant") == 2


def test_query_rewriter_expands_short_followup(settings):
    from rag_chat.query_rewriter import QueryRewriter

    rewriter = QueryRewriter(settings)
    history = [{"role": "user", "content": "RAG 检索是怎样的？"}]
    rewritten = rewriter.rewrite("它的优点？", history=history)
    assert "RAG" in rewritten or len(rewritten) > len("它的优点？")


def test_chat_api_functions(settings, monkeypatch):
    _build_wiki(settings)
    monkeypatch.setattr("rag_chat.api._chat", RAGChat(settings))
    result = api_chat(ChatRequest(query="RAG", top_k=1))
    assert result["sources"]
    stream = stream_chat(ChatRequest(query="RAG", top_k=1))
    assert stream.media_type == "text/plain"
