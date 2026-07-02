from __future__ import annotations

from dataclasses import dataclass, replace

from common.config import Settings, load_settings
from common.embedding import EmbeddingTool
from rag_chat.retriever import SearchResult


@dataclass
class Reranker:
    settings: Settings | None = None
    embedding_tool: EmbeddingTool | None = None

    def __post_init__(self) -> None:
        self.settings = self.settings or load_settings()
        self.embedding_tool = self.embedding_tool or EmbeddingTool.from_settings(self.settings)

    def rerank(self, query: str, results: list[SearchResult], top_k: int = 5) -> list[SearchResult]:
        if not results:
            return []

        query_vec = self.embedding_tool.embed(query)
        sims = [
            self.embedding_tool.cosine(query_vec, self.embedding_tool.embed(r.snippet))
            for r in results
        ]
        scores = [r.score for r in results]

        max_score = max(scores) if scores else 0.0
        max_sim = max(sims) if sims else 0.0

        norm_scores = [s / max_score if max_score else 0.0 for s in scores]
        norm_sims = [s / max_sim if max_sim else 0.0 for s in sims]

        combined = [0.5 * ns + 0.5 * ni for ns, ni in zip(norm_scores, norm_sims)]

        ordered = sorted(range(len(results)), key=lambda i: combined[i], reverse=True)
        return [replace(results[i], score=combined[i]) for i in ordered[:top_k]]


@dataclass
class ContextCompressor:
    max_chars: int = 4000

    def compress(self, results: list[SearchResult], max_chars: int | None = None) -> str:
        limit = max_chars if max_chars is not None else self.max_chars

        seen: set[str] = set()
        entries: list[str] = []
        for r in results:
            if r.snippet in seen:
                continue
            seen.add(r.snippet)
            heading = r.heading or r.title
            entries.append(f"[{len(entries)}] {r.title} / {heading}: {r.snippet}")

        parts: list[str] = []
        total = 0
        for entry in entries:
            sep_len = 2 if parts else 0  # length of "\n\n"
            if total + sep_len + len(entry) > limit:
                break
            parts.append(entry)
            total += sep_len + len(entry)

        return "\n\n".join(parts)


@dataclass
class PostProcessor:
    settings: Settings | None = None

    def __post_init__(self) -> None:
        self.settings = self.settings or load_settings()
        self.reranker = Reranker(settings=self.settings)
        self.compressor = ContextCompressor()

    def process(
        self,
        query: str,
        results: list[SearchResult],
        top_k: int = 5,
        max_chars: int = 4000,
    ) -> tuple[list[SearchResult], str]:
        reranked = self.reranker.rerank(query, results, top_k=top_k)
        context = self.compressor.compress(reranked, max_chars=max_chars)
        return reranked, context
