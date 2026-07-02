from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from common.config import Settings, load_settings
from common.llm_client import LLMClient

from .postprocess import PostProcessor
from .query_rewriter import QueryRewriter
from .retriever import HybridRetriever, SearchResult
from .session_store import ChatStore


@dataclass
class ChatResponse:
    answer: str
    sources: list[dict]
    session_id: str = ""
    rewritten_query: str = ""


@dataclass
class RAGChat:
    settings: Settings | None = None
    retriever: HybridRetriever | None = None
    llm_client: LLMClient | None = None
    postprocessor: PostProcessor | None = None
    rewriter: QueryRewriter | None = None
    store: ChatStore | None = None
    history: list[dict[str, str]] = field(default_factory=list)
    max_history: int = 6

    def __post_init__(self) -> None:
        self.settings = self.settings or load_settings()
        self.retriever = self.retriever or HybridRetriever(self.settings)
        self.llm_client = self.llm_client or LLMClient.from_settings(self.settings)
        self.postprocessor = self.postprocessor or PostProcessor(self.settings)
        self.rewriter = self.rewriter or QueryRewriter(self.settings, self.llm_client)
        self.store = self.store or ChatStore(self.settings)

    def complete_query(self, query: str, history: list[dict[str, str]] | None = None) -> str:
        return self.rewriter.rewrite(query, history if history is not None else self.history)

    def ask(self, query: str, top_k: int = 5, session_id: str = "") -> ChatResponse:
        session_id = self._ensure_session(session_id, query)
        history = self._load_history(session_id)
        rewritten = self.complete_query(query, history)
        results = self.retriever.search(rewritten, top_k=top_k * 2)
        reranked, context = self.postprocessor.process(rewritten, results, top_k=top_k)
        answer = self.llm_client.complete(query, context)
        if reranked:
            answer += "\n\n引用：" + ", ".join(
                f"[{idx + 1}]({Path(result.path).as_posix()}#{result.heading})"
                for idx, result in enumerate(reranked)
            )
        sources = [self._source_dict(result) for result in reranked]
        self.store.add_message(session_id, "user", query)
        self.store.add_message(session_id, "assistant", answer, sources)
        self._remember("user", query)
        self._remember("assistant", answer)
        return ChatResponse(answer=answer, sources=sources, session_id=session_id, rewritten_query=rewritten)

    def stream_ask(self, query: str, top_k: int = 5, session_id: str = "") -> Iterator[str]:
        session_id = self._ensure_session(session_id, query)
        history = self._load_history(session_id)
        rewritten = self.complete_query(query, history)
        results = self.retriever.search(rewritten, top_k=top_k * 2)
        reranked, context = self.postprocessor.process(rewritten, results, top_k=top_k)
        buffer: list[str] = []
        for token in self.llm_client.stream_complete(query, context):
            buffer.append(token)
            yield token
        citation = ""
        if reranked:
            citation = "\n\n引用：" + ", ".join(
                f"[{idx + 1}]({Path(result.path).as_posix()}#{result.heading})"
                for idx, result in enumerate(reranked)
            )
            yield citation
        answer = "".join(buffer) + citation
        sources = [self._source_dict(result) for result in reranked]
        self.store.add_message(session_id, "user", query)
        self.store.add_message(session_id, "assistant", answer, sources)
        self._remember("user", query)
        self._remember("assistant", answer)

    def _ensure_session(self, session_id: str, query: str) -> str:
        if session_id and self.store.get_session(session_id):
            return session_id
        title = query.strip()[:30] or "新对话"
        return self.store.create_session(title)["id"]

    def _load_history(self, session_id: str) -> list[dict[str, str]]:
        messages = self.store.list_messages(session_id, limit=self.max_history * 2)
        return [{"role": m["role"], "content": m["content"]} for m in messages[-self.max_history * 2 :]]

    def _remember(self, role: str, content: str) -> None:
        self.history.append({"role": role, "content": content})
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history :]

    @staticmethod
    def _source_dict(result: SearchResult) -> dict:
        return {
            "doc_id": result.doc_id,
            "chunk_id": result.chunk_id,
            "path": result.path,
            "title": result.title,
            "heading": result.heading,
            "score": result.score,
            "snippet": result.snippet,
        }
